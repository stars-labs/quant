from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from starslab_runner.launcher import installation_guard


class LauncherTest(unittest.TestCase):
    def test_running_processes_block_upgrade_and_new_processes_blocked_during_upgrade(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)
            with installation_guard(directory):
                with installation_guard(directory): pass
                with self.assertRaises(RuntimeError):
                    with installation_guard(directory,exclusive=True): pass
            with installation_guard(directory,exclusive=True):
                with self.assertRaises(RuntimeError):
                    with installation_guard(directory): pass
            with installation_guard(directory): pass
            self.assertEqual((directory/'installation.lock').stat().st_mode & 0o777,0o600)

    def test_macos_identity_uses_platform_uuid_instead_of_hostname(self):
        import hashlib
        from unittest.mock import patch
        from types import SimpleNamespace
        from starslab_runner.config import machine_identity
        value='12345678-1234-1234-1234-123456789ABC'
        with patch('starslab_runner.config.sys.platform','darwin'), patch('starslab_runner.config.subprocess.run',
            return_value=SimpleNamespace(stdout='"IOPlatformUUID" = "'+value+'"')):
            self.assertEqual(machine_identity(),hashlib.sha256(value.lower().encode()).hexdigest())
