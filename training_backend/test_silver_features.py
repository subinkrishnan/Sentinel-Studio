import hashlib
import json
from pathlib import Path
import unittest
from prepare_silver_features import prepare, cutoff_literal, FROZEN_SQL_SHA256

ROOT = Path(__file__).parent / 'sql'


class SilverFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.sql = (ROOT / 'com01_v05_frozen_features.sql').read_text()
        self.manifest = (ROOT / 'com01_v05_source_manifest.json').read_bytes()

    def test_adaptation_preserves_feature_logic(self):
        files = prepare(self.manifest, self.sql)
        contract = json.loads(files['contract.json'])
        transformed = files['features.sql'].split('\n', 3)[3]
        for original, physical in contract['source_mapping'].items():
            transformed = transformed.replace(physical, original)
        transformed = transformed.replace(contract['coverage_relation'], 'com01_source_coverage')
        transformed = transformed.replace('\n       AND COUNT(DISTINCT c.source_table) = 13', '')
        self.assertEqual(transformed, self.sql)
        self.assertEqual(hashlib.sha256(transformed.encode()).hexdigest(), FROZEN_SQL_SHA256)
        self.assertFalse(contract['production_publication_allowed'])
        self.assertFalse(contract['coverage_fixture_is_attestation'])
        self.assertEqual(len(contract['source_mapping']), 13)
        self.assertEqual(files['source_checks.sql'].count('AS expected_rows'), 13)

    def test_cutoff_is_explicit_utc(self):
        files = prepare(self.manifest, self.sql, '2025-01-01T08:00:00+08:00')
        self.assertIn("CAST('2025-01-01T00:00:00+00:00' AS TIMESTAMPTZ)", files['features.sql'])
        self.assertNotIn(':as_of', files['features.sql'])
        with self.assertRaises(ValueError):
            cutoff_literal('2025-01-01')
        with self.assertRaises(ValueError):
            cutoff_literal("2025-01-01'; DROP TABLE x; --")

    def test_changed_inputs_blocked(self):
        with self.assertRaises(ValueError):
            prepare(self.manifest + b' ', self.sql)
        with self.assertRaises(ValueError):
            prepare(self.manifest, self.sql + '\n')


if __name__ == '__main__':
    unittest.main()
