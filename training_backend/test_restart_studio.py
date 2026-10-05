import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from restart_studio import choose_artifacts, stop_studio

class RestartChecks(unittest.TestCase):
    def save_run(self, root, name, status):
        folder = root / name
        folder.mkdir(parents=True)
        (folder / 'run.json').write_text(json.dumps({'id': name, 'status': status, 'artifacts': []}))

    def test_completed_runs_reused_without_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            root = local / 'private-runs'
            self.save_run(root, 'previous', 'COMPLETED')
            before = (root / 'previous/run.json').read_bytes()
            self.assertEqual(choose_artifacts([local], local / 'fallback'), root)
            self.assertEqual((root / 'previous/run.json').read_bytes(), before)

    def test_active_and_ambiguous_runs_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            self.save_run(local / 'one', 'active', 'RUNNING')
            with self.assertRaisesRegex(ValueError, 'RUNNING'):
                choose_artifacts([local], local / 'fallback')
            (local / 'one/active/run.json').unlink()
            self.save_run(local / 'one', 'first', 'COMPLETED')
            self.save_run(local / 'two', 'second', 'COMPLETED')
            with self.assertRaisesRegex(ValueError, 'Multiple'):
                choose_artifacts([local], local / 'fallback')
            self.assertEqual(choose_artifacts([local], local / 'fallback', local / 'two'), local / 'two')

    def test_changed_listener_is_never_stopped(self):
        with patch('restart_studio.listener', return_value={999}), patch('restart_studio.os.kill') as kill:
            with self.assertRaisesRegex(ValueError, 'expected PID'):
                stop_studio(8767, 55608)
            kill.assert_not_called()

if __name__ == '__main__':
    unittest.main()
