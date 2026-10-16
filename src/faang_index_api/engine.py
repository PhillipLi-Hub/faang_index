"""Daily, prior-close market-cap-weighted company index. No network calls."""
import math


class DataError(ValueError):
    pass


def build_index(bundle, top_n=10):
    days = bundle['sessions']
    snapshots = bundle['snapshots']
    if not days or days != sorted(set(days)):
        raise DataError('Expected nonempty, unique, ascending trading sessions.')
    baskets = {}
    for day in days:
        rows = snapshots.get(day, [])
        if len(rows) < top_n:
            raise DataError(f'{day}: fewer than {top_n} eligible companies.')
        companies = {}
        symbols = set()
        for row in rows:
            if row['symbol'] in symbols:
                raise DataError(f'{day}: duplicate symbol {row["symbol"]}.')
            symbols.add(row['symbol'])
            for field in ('market_cap', 'close'):
                if not math.isfinite(row[field]) or row[field] <= 0:
                    raise DataError(f'{day}: invalid {field} for {row["symbol"]}.')
            # Provider's company market cap can be repeated for multiple share
            # classes. Count the company once; use its lexicographically first
            # eligible ticker as the investable representative.
            company = row['company_id']
            if not company:
                raise DataError(f'{day}: missing company identity.')
            if company not in companies or row['symbol'] < companies[company]['symbol']:
                companies[company] = row
        selected = sorted(companies.values(), key=lambda r: (-r['market_cap'], r['symbol']))[:top_n]
        if len(selected) != top_n:
            raise DataError(f'{day}: fewer than {top_n} distinct companies.')
        total = sum(r['market_cap'] for r in selected)
        baskets[day] = [dict(r, weight=r['market_cap'] / total) for r in selected]
    level, history = 100.0, []
    for i, day in enumerate(days):
        contributions = []
        daily_return = 0.0
        if i:
            previous = days[i - 1]
            for row in baskets[previous]:
                # Prices include exiting constituents, not only today's universe.
                current = bundle['prices'].get(row['symbol'], {}).get(day)
                if current is None or not math.isfinite(current) or current <= 0:
                    raise DataError(f'{day}: missing valid price for held stock {row["symbol"]}.')
                stock_return = current / row['close'] - 1
                contribution = row['weight'] * stock_return
                daily_return += contribution
                contributions.append({'symbol': row['symbol'], 'weight': row['weight'],
                                      'return': stock_return, 'contribution': contribution})
            level *= 1 + daily_return
        if not math.isfinite(level) or level <= 0:
            raise DataError(f'{day}: invalid index level.')
        history.append({'date': day, 'level': level, 'daily_return': daily_return,
                        'ytd_return': level / 100 - 1, 'contributions': contributions})
    return {'name': 'FAANG Index', 'source': bundle['source'], 'is_demo': bundle.get('is_demo', False),
            'universe': 'Point-in-time S&P 500 companies', 'base_date': days[0], 'base_level': 100,
            'as_of': days[-1], 'level': level, 'ytd_return': level / 100 - 1,
            'daily_return': history[-1]['daily_return'],
            'return_type': 'split-adjusted price return; dividends excluded',
            'rebalance': 'Daily at close; previous close weights earn next session return',
            'costs': 'Transaction costs and taxes excluded',
            'next_session_holdings': baskets[days[-1]], 'history': history}
