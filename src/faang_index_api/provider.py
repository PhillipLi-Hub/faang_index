"""FMP adapter. Strict completeness checks; successful responses cached on disk."""
import hashlib
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import exchange_calendars as xcals
import httpx
import pandas as pd

from .engine import DataError

ROOT = Path(__file__).resolve().parents[2]


def completed_sessions(year):
    today = datetime.now(timezone.utc)
    end = min(date(year, 12, 31), today.date())
    if end < date(year, 1, 1):
        raise DataError('Year is in the future.')
    calendar = xcals.get_calendar('XNYS', start=f'{year - 1}-12-01', end=f'{year + 1}-01-31')
    return [s.strftime('%Y-%m-%d') for s in calendar.sessions_in_range(f'{year}-01-01', end)
            if calendar.session_close(s) <= pd.Timestamp(today)]


def membership_on(current, events, day):
    members = set(current)
    # Changes take effect on their date; reverse changes strictly after day.
    for event in sorted(events, key=lambda e: e['date'], reverse=True):
        if event['date'] > day:
            if event.get('added'):
                members.discard(event['added'])
            if event.get('removed'):
                members.add(event['removed'])
    return members


class FMP:
    def __init__(self, progress=lambda message: None):
        self.key = os.environ.get('FMP_API_KEY', '').strip()
        if not self.key:
            raise DataError('Set FMP_API_KEY, restart the server, then POST /api/refresh. '
                            'Your plan must allow historical caps, prices, profiles and S&P 500 membership changes.')
        self.progress = progress
        self.cache = ROOT / 'data' / 'provider_cache'
        self.cache.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(timeout=45, follow_redirects=False)

    def close(self):
        self.client.close()

    def get(self, endpoint, **params):
        # Daily UTC cache; neither credentials nor request URLs are persisted.
        signature = json.dumps([endpoint, params, datetime.now(timezone.utc).date().isoformat()], sort_keys=True)
        path = self.cache / (hashlib.sha256(signature.encode()).hexdigest() + '.json')
        if path.exists():
            return json.loads(path.read_text())
        time.sleep(0.3)
        for attempt in range(3):
            try:
                response = self.client.get('https://financialmodelingprep.com/stable/' + endpoint,
                                           params={**params, 'apikey': self.key})
            except httpx.HTTPError:
                raise DataError('Market-data network request failed. Retry refresh later.') from None
            if response.status_code == 429 and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            if response.status_code != 200:
                raise DataError(f'FMP {endpoint}: HTTP {response.status_code}. Check key, plan access and quota.')
            try:
                rows = response.json()
            except ValueError:
                raise DataError(f'FMP {endpoint}: invalid JSON.') from None
            if not isinstance(rows, list) or not rows:
                raise DataError(f'FMP {endpoint}: missing data or unsupported response. Nothing was substituted.')
            path.write_text(json.dumps(rows))
            return rows
        raise DataError('Market-data rate limit reached.')

    def load(self, year):
        days = completed_sessions(year)
        if not days:
            raise DataError('No completed trading sessions in this year yet.')
        self.progress('Loading current S&P 500 membership and historical changes')
        current = {r['symbol'] for r in self.get('sp500-constituent')}
        if not 490 <= len(current) <= 520:
            raise DataError('Unexpected S&P 500 membership coverage.')
        raw_events = self.get('historical-sp500-constituent')
        events = []
        for r in raw_events:
            effective = str(r.get('date', ''))[:10]
            try:
                date.fromisoformat(effective)
            except ValueError:
                raise DataError('Unrecognized membership effective date; refusing to infer it.') from None
            if effective < days[0]:
                continue
            added = r.get('symbol') if r.get('addedSecurity') else None
            removed = r.get('removedTicker') or None
            if not added and not removed:
                raise DataError('Unrecognized membership-change record.')
            events.append({'date': effective, 'added': added, 'removed': removed})
        members = {day: membership_on(current, events, day) for day in days}
        if any(not 490 <= len(m) <= 520 for m in members.values()):
            raise DataError('Reconstructed membership has incomplete coverage.')
        symbols = sorted(set().union(*members.values()))
        profiles, caps, prices = {}, {}, {}
        for i, symbol in enumerate(symbols, 1):
            self.progress(f'Loading {symbol} ({i}/{len(symbols)}); first refresh can take several minutes')
            profile = self.get('profile', symbol=symbol)[0]
            cik = str(profile.get('cik') or '').strip().lstrip('0')
            if not cik:
                raise DataError(f'{symbol}: missing company CIK; cannot safely deduplicate share classes.')
            if profile.get('currency') != 'USD':
                raise DataError(f'{symbol}: unsupported non-USD security.')
            profiles[symbol] = {'company_id': cik, 'company_name': profile.get('companyName', symbol)}
            params = {'symbol': symbol, 'from': days[0], 'to': days[-1], 'limit': 10000}
            cap_rows = self.get('historical-market-capitalization', **params)
            price_rows = self.get('historical-price-eod/full', **params)
            caps[symbol] = {r['date']: float(r['marketCap']) for r in cap_rows}
            prices[symbol] = {r['date']: float(r['close']) for r in price_rows}
        snapshots = {}
        for day in days:
            rows = []
            for symbol in sorted(members[day]):
                if day not in caps[symbol] or day not in prices[symbol]:
                    raise DataError(f'{day}: missing market cap or price for eligible stock {symbol}. '
                                    'Refresh stopped rather than silently changing the universe.')
                rows.append({'symbol': symbol, **profiles[symbol], 'market_cap': caps[symbol][day],
                             'close': prices[symbol][day]})
            snapshots[day] = rows
        return {'sessions': days, 'snapshots': snapshots, 'prices': prices,
                'source': 'Financial Modeling Prep', 'is_demo': False}


def demo_bundle():
    days = ['2026-01-02', '2026-01-05', '2026-01-06']
    snapshots, prices = {}, {}
    for i, day in enumerate(days):
        snapshots[day] = []
        for j in range(12):
            symbol = f'DEMO{j + 1:02}'
            close = 100 * (1 + (j + 1) / 1000) ** i
            cap = (12 - j) * 1e9 * (1 + 0.01 * i)
            if i and j == 11:
                cap = 20e9  # A new entrant demonstrates next-session selection.
            prices.setdefault(symbol, {})[day] = close
            snapshots[day].append({'symbol': symbol, 'company_id': symbol,
                                   'company_name': f'Fictional company {j + 1}',
                                   'market_cap': cap, 'close': close})
    return {'sessions': days, 'snapshots': snapshots, 'prices': prices,
            'source': 'Synthetic demonstration — not stock-market data', 'is_demo': True}
