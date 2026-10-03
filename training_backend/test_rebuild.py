import unittest
import pandas as pd
from rebuild_development import available, window, contract_days, balances, validate_units


class AvailabilityChecks(unittest.TestCase):
    def setUp(self):
        self.t0 = pd.Timestamp('2026-07-02', tz='UTC')

    def test_late_created_ingested_and_missing_are_excluded(self):
        before, after = self.t0 - pd.Timedelta(days=1), self.t0 + pd.Timedelta(days=1)
        f = pd.DataFrame({'created_ts': [before, after, before, pd.NaT],
                          'ingested_ts': [before, before, after, before]})
        self.assertEqual(available(f, self.t0).index.tolist(), [0])

    def test_available_exactly_at_cutoff(self):
        f = pd.DataFrame({'created_ts': [self.t0], 'ingested_ts': [self.t0]})
        self.assertEqual(len(available(f, self.t0)), 1)

    def test_open_left_closed_right_window(self):
        f = pd.DataFrame({'event_ts': [self.t0 - pd.Timedelta(days=30), self.t0,
                                        self.t0 + pd.Timedelta(seconds=1)]})
        self.assertEqual(window(f, 'event_ts', self.t0, 30).index.tolist(), [1])

    def contracts(self):
        return pd.DataFrame({'service_instance_id': ['A', 'B'], 'contract_id': ['1', '2'],
                             'created_ts': [self.t0 - pd.Timedelta(days=10)] * 2,
                             'ingested_ts': [self.t0 - pd.Timedelta(days=9)] * 2,
                             'updated_ts': [self.t0 + pd.Timedelta(days=1), pd.NaT],
                             'contract_end_date': [self.t0 + pd.Timedelta(days=30), self.t0 - pd.Timedelta(hours=25)]})

    def test_future_contract_update_is_excluded(self):
        self.assertEqual(contract_days(self.contracts(), self.t0).index.tolist(), ['B'])

    def test_expired_contract_uses_sql_floor_without_clipping(self):
        self.assertEqual(contract_days(self.contracts(), self.t0).loc['B'], -2)

    def test_latest_balance_tie_uses_id_and_preserves_negative(self):
        f = pd.DataFrame({'customer_id': ['C'] * 3, 'invoice_id': ['I'] * 3,
                          'balance_history_id': ['1', '2', '3'],
                          'transaction_ts': [self.t0 - pd.Timedelta(days=1), self.t0, self.t0],
                          'outstanding_amount': [100, 50, -10]})
        self.assertEqual(balances(f).loc['C'], -10)

    def test_non_mb_data_requires_explicit_contract(self):
        f = pd.DataFrame({'usage_type': ['DATA'], 'usage_unit': ['GB']})
        with self.assertRaisesRegex(ValueError, 'unit conversion'):
            validate_units(f)


if __name__ == '__main__':
    unittest.main()
