"""Mac Studio launcher: preserve run folders and copy the matching login token."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen


def choose_artifacts(search_folders, fallback, explicit=None):
    roots = set()
    if explicit is not None:
        roots.add(explicit.expanduser().resolve())
        files = list(next(iter(roots)).glob('*/run.json'))
    else:
        files = []
        for folder in search_folders:
            if folder.is_dir():
                files.extend(folder.rglob('run.json'))
    for file in files:
        run = json.loads(file.read_text())
        if not isinstance(run, dict) or not {'id', 'status', 'artifacts'} <= run.keys():
            continue
        if run['id'] != file.parent.name:
            raise ValueError('Run folder does not match its saved identity: ' + str(file))
        if run['status'] == 'RUNNING':
            raise ValueError('A training run is marked RUNNING. Studio was not stopped: ' + str(file))
        roots.add(file.parent.parent.resolve())
    if len(roots) > 1:
        raise ValueError('Multiple run folders found. Studio was not stopped. Use --artifacts with the current folder:\n' + '\n'.join(str(p) for p in sorted(roots)))
    return next(iter(roots), fallback)


def listener(port):
    result = subprocess.run(['lsof', '-nP', '-a', f'-iTCP:{port}', '-sTCP:LISTEN', '-Fp'], capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise ValueError('Could not inspect the Studio listener')
    return {int(line[1:]) for line in result.stdout.splitlines() if line.startswith('p')}


def stop_studio(port, expected_pid):
    pids = listener(port)
    if not pids:
        return
    if expected_pid is None or pids != {expected_pid}:
        raise ValueError('Studio listener differs from the expected PID. Nothing was stopped. Current PIDs: ' + ', '.join(map(str, sorted(pids))))
    command = subprocess.check_output(['ps', '-p', str(expected_pid), '-o', 'command='], text=True).strip()
    executable = Path(command.split()[0]).name.lower()
    if not executable.startswith('python'):
        raise ValueError('Listener is not Python. Nothing was stopped.')
    with urlopen(f'http://127.0.0.1:{port}/', timeout=5) as response:
        page = response.read(65536)
    if b'id="token"' not in page or b'COM01' not in page and b'Sentinel Studio' not in page:
        raise ValueError('Listener is not the expected Studio sign-in service. Nothing was stopped.')
    if listener(port) != {expected_pid}:
        raise ValueError('Listener changed during inspection. Nothing was stopped.')
    os.kill(expected_pid, signal.SIGTERM)
    for _ in range(30):
        with socket.socket() as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(('127.0.0.1', port)) != 0:
                return
        time.sleep(0.1)
    raise ValueError('Studio did not release its port. No forced stop was attempted.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--expected-pid', type=int)
    args = parser.parse_args()
    if sys.platform != 'darwin' or not shutil.which('pbcopy') or not shutil.which('lsof'):
        raise ValueError('This launcher requires macOS with pbcopy and lsof')
    if not 1024 <= args.port <= 65535:
        raise ValueError('Choose a port between 1024 and 65535')
    home = Path.home()
    repo = Path(__file__).resolve().parent.parent
    local = home / 'Downloads/Sentinel-COM01-Local'
    config = (args.config or local / 'local.admin.json').expanduser().resolve()
    settings = json.loads(config.read_text())
    if not Path(settings['data_dir']).expanduser().is_dir():
        raise ValueError('Configured dataset folder is missing. Studio was not stopped.')
    artifacts = choose_artifacts([local, repo, home / 'local-artifacts'], home / 'local-artifacts', args.artifacts)
    # Load dependencies and config before stopping the existing listener.
    from admin_server import Admin, make_http_server
    admin = Admin(config, artifacts)
    stop_studio(args.port, args.expected_pid)
    token = secrets.token_urlsafe(40)
    server = make_http_server(admin, args.port, token)
    try:
        subprocess.run(['pbcopy'], input=token, text=True, check=True)
        print(f'Studio ready: http://127.0.0.1:{args.port}/', flush=True)
        print(f'Training runs: {artifacts}', flush=True)
        print('Sentinel client ID: ' + ('configured' if os.environ.get('SENTINEL_CLIENT_ID') else 'missing') + '; client secret: ' + ('configured' if os.environ.get('SENTINEL_CLIENT_SECRET') else 'missing'), flush=True)
        print('Matching token copied. Paste directly into the login field with Cmd+V. Keep this terminal open.', flush=True)
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nStudio stopped.')
    except Exception as error:
        print('Studio launcher stopped: ' + str(error), file=sys.stderr)
        sys.exit(1)
