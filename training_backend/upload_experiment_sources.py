"""Provisioning-gated, checkpointed upload into isolated COM01 development tables."""
import argparse
import csv
import getpass
import gzip
import json
from pathlib import Path
from submit_experiment_sources import build_plan
from check_engine_sources import safe_error


def count(client, name):
    return int(client.query('SELECT COUNT(*) AS row_count FROM public.bronze__' + name)[0]['row_count'])


def preflight(client, plan, state):
    datasets = client.datasets()
    if not isinstance(datasets, list):
        raise ValueError('Unexpected dataset catalogue response; no upload started')
    indexed = {d.get('name'): d for d in datasets}
    blocked = []
    for table in plan['tables']:
        name = table['name']
        dataset = indexed.get(name, {})
        status = str(dataset.get('status', 'NOT_VISIBLE')).upper()
        print(name + ': ' + status, flush=True)
        if status != 'PROVISIONED':
            blocked.append(name + ': ' + status)
    if blocked:
        raise ValueError('UPLOAD BLOCKED: checker provisioning not confirmed for '
                         + str(len(blocked)) + ' tables. No records uploaded.')
    for table in plan['tables']:
        name = table['name']
        expected = state.get('tables', {}).get(name, {}).get('accepted_rows', 0)
        actual = count(client, name)
        if actual != expected:
            raise ValueError('UPLOAD BLOCKED: engine row count differs from local checkpoint for '
                             + name + '. Reconcile before resuming; no automatic refresh.')


def save(path, state):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(state, indent=2) + '\n')
    temp.replace(path)


def upload(client, plan, state, checkpoint, chunk_size):
    for table in plan['tables']:
        name = table['name']
        progress = state['tables'].setdefault(name, {'accepted_rows': 0})
        accepted = progress['accepted_rows']
        if accepted == table['expected_rows']:
            continue
        with gzip.open(table['source_path'], 'rt', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for _ in range(accepted):
                next(reader)
            while True:
                batch = []
                for _ in range(chunk_size):
                    row = next(reader, None)
                    if row is None:
                        break
                    batch.append({table['payload_column_map'].get(k, k): v for k, v in row.items()})
                if not batch:
                    break
                # Never retry an uncertain write. A server/local count mismatch
                # blocks the next run until its outcome has been reconciled.
                result = client.ingest(name, batch, source_system='COM01_V05_DEVELOPMENT')
                if (int(result.get('accepted', -1)) != len(batch)
                        or int(result.get('duplicates', -1)) != 0
                        or int(result.get('dlq', -1)) != 0):
                    raise ValueError('Upload response has rejects, duplicates or unexpected counts for '
                                     + name + '. Stopped; checkpoint not advanced.')
                accepted += len(batch)
                progress['accepted_rows'] = accepted
                save(checkpoint, state)
                print(name + ': ' + str(accepted) + '/' + str(table['expected_rows']), flush=True)
        if accepted != table['expected_rows'] or count(client, name) != accepted:
            raise ValueError('Final source row count mismatch for ' + name)
        progress['row_count_verified'] = True
        save(checkpoint, state)
    state['status'] = 'UPLOAD_ROW_COUNTS_PASS_CONTENT_PARITY_PENDING'
    save(checkpoint, state)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--upload', action='store_true', help='Upload after all provisioning checks pass')
    p.add_argument('--chunk-size', type=int, default=1000)
    args = p.parse_args()
    if not 1 <= args.chunk_size <= 5000:
        raise SystemExit('Chunk size must be between 1 and 5000')
    plan = build_plan(args.data_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output_dir / 'source-upload-status.json'
    state = (json.loads(checkpoint.read_text()) if checkpoint.exists()
             else {'manifest_sha256': plan['manifest_sha256'], 'tables': {}, 'status': 'NOT_STARTED'})
    if state['manifest_sha256'] != plan['manifest_sha256']:
        raise SystemExit('Upload checkpoint belongs to another dataset')
    cid = getpass.getpass('Client ID: ').strip().removeprefix('client_id=').strip()
    secret = getpass.getpass('Client Secret: ').strip().removeprefix('client_secret=').strip()
    if not cid or not secret:
        raise SystemExit('Both credentials are required')
    from sentinel_client import Client
    client = Client('https://dev.sentinel.inalpha.ai', cid, secret)
    try:
        preflight(client, plan, state)
        print('PROVISIONING AND CHECKPOINT CHECK: PASS')
        if args.upload:
            upload(client, plan, state, checkpoint, args.chunk_size)
            print('Source upload complete; content and feature parity still required.')
        else:
            print('Check only. No records uploaded. Add --upload to load verified sources.')
    except Exception as exc:
        raise SystemExit(safe_error(exc, (cid, secret))) from None


if __name__ == '__main__':
    main()
