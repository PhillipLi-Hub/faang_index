import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from faang_index_api import main
from faang_index_api.engine import DataError, build_index
from faang_index_api.provider import completed_sessions, demo_bundle, membership_on


class IndexTests(unittest.TestCase):
    def test_public_refresh_requires_secret(self):
        with patch.dict(os.environ, {'REQUIRE_REFRESH_TOKEN': 'true', 'REFRESH_TOKEN': 'test-secret', 'FMP_API_KEY': ''}):
            with TestClient(main.app) as client:
                self.assertEqual(client.post('/api/refresh').status_code, 401)
                self.assertEqual(client.post('/api/refresh', headers={'X-Refresh-Token': 'wrong'}).status_code, 401)
                response = client.post('/api/refresh', headers={'X-Refresh-Token': 'test-secret'})
                self.assertEqual(response.status_code, 503)
                self.assertIn('FMP_API_KEY', response.json()['detail'])

    def test_public_refresh_disabled_without_configured_secret(self):
        with patch.dict(os.environ, {'REQUIRE_REFRESH_TOKEN': 'true', 'REFRESH_TOKEN': ''}):
            with TestClient(main.app) as client:
                self.assertEqual(client.post('/api/refresh').status_code, 503)

    def test_lagged_weights_rebalance_and_compounding(self):
        days = ['2026-01-02', '2026-01-05', '2026-01-06']
        def row(symbol, cap, close):
            return {'symbol': symbol, 'company_id': symbol, 'market_cap': cap, 'close': close}
        bundle = {'sessions': days, 'source': 'test', 'snapshots': {
            days[0]: [row('A', 200, 100), row('B', 100, 100)],
            days[1]: [row('A', 220, 110), row('B', 400, 200)],
            days[2]: [row('A', 198, 99), row('B', 200, 100)]},
            'prices': {'A': dict(zip(days, [100, 110, 99])), 'B': dict(zip(days, [100, 200, 100]))}}
        result = build_index(bundle, top_n=1)
        self.assertAlmostEqual(result['history'][1]['level'], 110)
        self.assertAlmostEqual(result['level'], 55)
        self.assertEqual(result['history'][1]['contributions'][0]['symbol'], 'A')
        self.assertEqual(result['history'][2]['contributions'][0]['symbol'], 'B')

    def test_contributions_weights_and_base(self):
        result = build_index(demo_bundle())
        self.assertEqual(result['history'][0]['level'], 100)
        self.assertAlmostEqual(sum(r['weight'] for r in result['next_session_holdings']), 1)
        for row in result['history']:
            self.assertAlmostEqual(sum(r['contribution'] for r in row['contributions']), row['daily_return'])
        self.assertTrue(result['is_demo'])

    def test_missing_held_price_fails(self):
        bundle = demo_bundle()
        del bundle['prices']['DEMO01']['2026-01-05']
        with self.assertRaisesRegex(DataError, 'held stock'):
            build_index(bundle)

    def test_nan_cap_fails(self):
        bundle = demo_bundle()
        bundle['snapshots']['2026-01-02'][0]['market_cap'] = float('nan')
        with self.assertRaisesRegex(DataError, 'invalid market_cap'):
            build_index(bundle)

    def test_share_classes_do_not_double_count(self):
        bundle = demo_bundle()
        for rows in bundle['snapshots'].values():
            duplicate = copy.deepcopy(rows[0])
            duplicate['symbol'] = 'ZZZ'
            rows.append(duplicate)
        result = build_index(bundle)
        ids = [r['company_id'] for r in result['next_session_holdings']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_point_in_time_membership(self):
        events = [{'date': '2026-02-02', 'added': 'NEW', 'removed': 'OLD'}]
        self.assertEqual(membership_on({'A', 'NEW'}, events, '2026-01-02'), {'A', 'OLD'})
        self.assertEqual(membership_on({'A', 'NEW'}, events, '2026-02-02'), {'A', 'NEW'})

    def test_exchange_calendar_base(self):
        self.assertEqual(completed_sessions(2025)[0], '2025-01-02')
        self.assertNotIn('2025-01-20', completed_sessions(2025))

    def test_api_without_key_and_invalid_year(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(main, 'DATA', Path(directory)), patch.dict(os.environ, {'FMP_API_KEY': ''}):
            with TestClient(main.app) as client:
                self.assertEqual(client.get('/health').status_code, 200)
                self.assertEqual(client.get('/docs').status_code, 200)
                self.assertTrue(client.get('/api/demo').json()['is_demo'])
                self.assertEqual(client.get('/api/index').status_code, 503)
                self.assertEqual(client.post('/api/refresh').status_code, 503)
                self.assertEqual(client.get('/api/index?year=1').status_code, 422)

    def test_background_refresh_persists_result(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(main, 'DATA', Path(directory)), patch.dict(os.environ, {'FMP_API_KEY': 'test-placeholder'}), patch.object(main, 'FMP') as provider:
            provider.return_value.load.return_value = demo_bundle()
            with TestClient(main.app) as client:
                self.assertEqual(client.post('/api/refresh?year=2026').status_code, 202)
                self.assertEqual(client.get('/api/refresh/status').json()['status'], 'complete')
                self.assertEqual(client.get('/api/index?year=2026').status_code, 200)


if __name__ == '__main__':
    unittest.main()
