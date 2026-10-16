import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.security import APIKeyHeader

from .engine import DataError, build_index
from .provider import FMP, demo_bundle

app = FastAPI(title='FAANG Index API', version='1.0.0', description=(
    'Custom top-10 S&P 500 company index. Base 100 at the first trading close of the year. '
    'Prior-close market-cap weights; daily compounding; price returns, no dividends or costs. '
    'GET /api/demo uses fictional data. Live data requires FMP_API_KEY and a successful refresh.'))
DATA = Path(__file__).resolve().parents[2] / 'data'
lock = Lock()
job = {'status': 'idle', 'message': 'No refresh requested since startup'}
refresh_header = APIKeyHeader(name='X-Refresh-Token', auto_error=False)


def authorize_refresh(token: str | None = Depends(refresh_header)):
    expected = os.environ.get('REFRESH_TOKEN', '').strip()
    required = os.environ.get('REQUIRE_REFRESH_TOKEN', '').lower() == 'true' or bool(os.environ.get('RENDER'))
    if not expected:
        if required:
            raise HTTPException(503, 'Refresh disabled: configure REFRESH_TOKEN on the server.')
        return
    if not token or not secrets.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(401, 'A valid X-Refresh-Token is required.')


def current_year():
    return datetime.now(ZoneInfo('Europe/London')).year


def update(year):
    client = None
    try:
        client = FMP(lambda message: job.update(message=message))
        result = build_index(client.load(year))
        result['fetched_at'] = datetime.now(timezone.utc).isoformat()
        DATA.mkdir(exist_ok=True)
        path = DATA / f'index-{year}.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
        temporary.replace(path)
        job.update(status='complete', message='Index refreshed', as_of=result['as_of'])
    except DataError as error:
        job.update(status='failed', message=str(error))
    except Exception:
        logging.exception('Index refresh failed')
        job.update(status='failed', message='Unexpected provider data or processing error; see server log.')
    finally:
        if client:
            client.close()
        lock.release()


@app.get('/', include_in_schema=False)
def home():
    return RedirectResponse('/docs')


@app.get('/health')
def health():
    return {'ok': True, 'service': 'FAANG Index API'}


@app.get('/api/demo')
def demo():
    """Exercise the full index calculation using explicitly fictional data."""
    return build_index(demo_bundle())


@app.get('/api/index')
def index(year: int | None = Query(None, ge=2000, le=2100)):
    """Return the last successfully calculated live series, with explicit as_of date."""
    year = year or current_year()
    path = DATA / f'index-{year}.json'
    if not path.exists():
        raise HTTPException(503, 'No live index yet. Set FMP_API_KEY and POST /api/refresh; '
                            'check /api/refresh/status. Use /api/demo for fictional test data.')
    result = json.loads(path.read_text(encoding='utf-8'))
    result['served_at'] = datetime.now(timezone.utc).isoformat()
    return result


@app.post('/api/refresh', status_code=202, dependencies=[Depends(authorize_refresh)])
def refresh(background: BackgroundTasks, year: int | None = Query(None, ge=2000, le=2100)):
    """Fetch historical data and rebuild. May use ~1,500+ provider calls initially.

    Run once after each completed trading day for a fresh daily series. Cached
    output remains readable during refresh; failures never overwrite good output.
    """
    if not os.environ.get('FMP_API_KEY', '').strip():
        raise HTTPException(503, 'Missing FMP_API_KEY. Set it in the server environment and restart.')
    year = year or current_year()
    if year > current_year():
        raise HTTPException(422, 'Year is in the future.')
    if not lock.acquire(blocking=False):
        raise HTTPException(409, 'A refresh is already running.')
    job.clear()
    job.update(status='running', year=year, message='Starting data refresh')
    background.add_task(update, year)
    return {'status': 'accepted', 'status_url': '/api/refresh/status'}


@app.get('/api/refresh/status')
def refresh_status():
    return dict(job)
