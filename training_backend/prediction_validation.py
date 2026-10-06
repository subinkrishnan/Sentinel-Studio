"""Compare an imported Dev scoring export with immutable local predictions.

An imported export is evidence supplied by the operator, not a live SDK fetch.
No model execution, promotion or publication occurs.
"""
import csv
import hashlib
import io
import math
from datetime import datetime, timezone
from pathlib import Path

PROBABILITY_ATOL = 1e-7
MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 200000
KEYS = ['training_observation_id', 'service_instance_id', 'data_as_of_ts']
VALUES = ['probability', 'threshold', 'predicted_label']


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read_rows(text, dev=False):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Prediction CSV exceeds the 16 MiB limit')
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    required = KEYS + VALUES + (['model_name', 'model_version'] if dev else ['label'])
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError('CSV needs unique column names')
    if any(k not in reader.fieldnames for k in required):
        raise ValueError('Missing CSV columns: ' + ', '.join(k for k in required if k not in reader.fieldnames))
    indexed = {}; duplicates = 0; service_keys = set()
    for number, row in enumerate(reader, 2):
        if number > MAX_ROWS + 1:
            raise ValueError('Prediction CSV exceeds the row limit')
        if None in row or any(row.get(k) is None or not row[k].strip() for k in required):
            raise ValueError('Malformed prediction row at line ' + str(number))
        try:
            when = datetime.fromisoformat(row['data_as_of_ts'].strip().replace('Z', '+00:00'))
            if when.tzinfo is None:
                raise ValueError()
            when = when.astimezone(timezone.utc).isoformat()
            probability = float(row['probability']); threshold = float(row['threshold'])
            if not all(math.isfinite(x) and 0 <= x <= 1 for x in [probability, threshold]):
                raise ValueError()
            if row['predicted_label'].strip() not in ['0', '1']:
                raise ValueError()
            if not dev and row['label'].strip() not in ['0', '1']:
                raise ValueError()
        except (ValueError, OverflowError):
            raise ValueError('Invalid timestamp, probability or label at line ' + str(number)) from None
        key = (row['training_observation_id'].strip(), row['service_instance_id'].strip(), when)
        service_key = key[1:]
        if key in indexed or service_key in service_keys:
            duplicates += 1
        else:
            indexed[key] = {**row, 'probability': probability, 'threshold': threshold,
                            'predicted_label': int(row['predicted_label'])}
            service_keys.add(service_key)
    if not indexed:
        raise ValueError('Prediction CSV is empty')
    return indexed, duplicates


def summary(expected, actual, keys):
    tp = fp = tn = fn = 0; brier = 0.0
    for key in keys:
        label = int(expected[key]['label']); prediction = actual[key]['predicted_label']
        tp += int(label == 1 and prediction == 1); fp += int(label == 0 and prediction == 1)
        tn += int(label == 0 and prediction == 0); fn += int(label == 1 and prediction == 0)
        brier += (actual[key]['probability'] - label) ** 2
    count = len(keys)
    return {'observations': count, 'accuracy': (tp + tn) / count if count else None,
            'precision': tp / max(tp + fp, 1), 'recall': tp / max(tp + fn, 1),
            'brier': brier / count if count else None, 'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn}


def compare(local_csv, dev_csv, model_name, model_version):
    if not model_name or not model_version:
        raise ValueError('Recorded staging model name and version are required')
    expected, local_duplicates = read_rows(local_csv)
    if local_duplicates:
        raise ValueError('Local reference contains duplicate observations')
    actual, duplicates = read_rows(dev_csv, dev=True)
    local_thresholds = {r['threshold'] for r in expected.values()}
    if len(local_thresholds) != 1 or any(r['predicted_label'] != int(r['probability'] >= r['threshold']) for r in expected.values()):
        raise ValueError('Local reference has an inconsistent frozen threshold')
    keys = sorted(set(expected) & set(actual))
    checks = {'missing_observations': len(set(expected) - set(actual)),
              'unexpected_observations': len(set(actual) - set(expected)),
              'duplicate_observations': duplicates, 'model_identity_mismatches': 0,
              'probability_mismatches': 0, 'threshold_mismatches': 0,
              'classification_mismatches': 0, 'inconsistent_dev_decisions': 0}
    checks['model_identity_mismatches'] = sum(r['model_name'].strip() != model_name or r['model_version'].strip() != model_version for r in actual.values())
    checks['inconsistent_dev_decisions'] = sum(r['predicted_label'] != int(r['probability'] >= r['threshold']) for r in actual.values())
    maximum = 0.0
    for key in keys:
        a = actual[key]; e = expected[key]; delta = abs(a['probability'] - e['probability'])
        maximum = max(maximum, delta)
        checks['probability_mismatches'] += int(delta > PROBABILITY_ATOL)
        checks['threshold_mismatches'] += int(abs(a['threshold'] - e['threshold']) > 1e-12)
        checks['classification_mismatches'] += int(a['predicted_label'] != e['predicted_label'])
    return {'status': 'PREDICTION_PARITY_PASS' if not any(checks.values()) else 'PREDICTION_PARITY_FAIL',
            'evidence_type': 'OPERATOR_IMPORTED_DEV_SCORING_CSV', 'live_sdk_fetch_verified': False,
            'expected_model_name': model_name, 'expected_model_version': model_version,
            'expected_observations': len(expected), 'dev_unique_observations': len(actual),
            'matched_observations': len(keys), 'checks': checks,
            'absolute_probability_tolerance': PROBABILITY_ATOL, 'maximum_probability_difference': maximum if keys else None,
            'local_reference_sha256': digest(local_csv), 'dev_export_sha256': digest(dev_csv),
            'local_metrics_on_matched_rows': summary(expected, expected, keys),
            'dev_metrics_on_matched_rows': summary(expected, actual, keys),
            'feature_parity': 'SEPARATE_VERIFICATION_REQUIRED',
            'production_qualification': 'PENDING', 'production_publication_allowed': False,
            'created_utc': datetime.now(timezone.utc).isoformat()}
