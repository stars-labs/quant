import copy
import json
import sys
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from starslab_runner.account_lock import acquire_local

from starslab_runner.config import DEFAULT, private_json
from starslab_runner.journal import Journal
from starslab_runner.setup import initialize, local_owner, upgrade


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        original_acquire = acquire_local
        self.account_directory = self.home/'account-locks'
        self.patch = patch('starslab_runner.account_lock.acquire_local',
                           side_effect=lambda config, directory=None: original_acquire(config, self.account_directory))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def legacy(self, live=False):
        config = copy.deepcopy(DEFAULT)
        config.pop('account_lock_owner')
        if live:
            config.update(mode='live', allow_live=True, account_uid='123', spot_account_id='456')
        private_json(self.home/'config.json', config)
        return config

    def test_staged_installer_preserves_existing_configuration(self):
        self.legacy()
        before = (self.home/'config.json').read_bytes()
        bindir = self.home/'bin'
        bindir.mkdir()
        runner = bindir/'starslab-runner'
        runner.write_text('#!/bin/sh\n[ "$1" = "--help" ]\n')
        runner.chmod(0o700)
        uv = bindir/'uv'
        uv.write_text('#!/bin/sh\ncase "$1" in\nrun) shift 5; exec python "$@" ;;\ntool) case "$2" in install) exit 0 ;; dir) dirname "$0" ;; esac ;;\nesac\n')
        uv.chmod(0o700)
        systemctl = bindir/'systemctl'
        systemctl.write_text('#!/bin/sh\nexit 3\n')
        systemctl.chmod(0o700)
        env = dict(os.environ, PATH=str(bindir)+os.pathsep+os.environ['PATH'],
                   STARSLAB_RUNNER_HOME=str(self.home))
        installer = Path(__file__).resolve().parents[1]/'install.sh'
        result = subprocess.run(['sh', str(installer)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home/'config.json').read_bytes(), before)

    def test_installer_refuses_foreground_executor_in_another_home(self):
        if not Path('/proc').exists():
            self.skipTest('Linux process inspection')
        bindir = self.home/'bin'
        bindir.mkdir()
        runner = bindir/'starslab-runner'
        runner.write_text('#!/bin/sh\nsleep 30\n')
        runner.chmod(0o700)
        uv = bindir/'uv'
        uv.write_text('#!/bin/sh\nshift 5; exec python "$@"\n')
        uv.chmod(0o700)
        systemctl = bindir/'systemctl'
        systemctl.write_text('#!/bin/sh\nexit 3\n')
        systemctl.chmod(0o700)
        executor = subprocess.Popen([str(runner), '--home', str(self.home/'other')],
                                    start_new_session=True)
        try:
            env = dict(os.environ, PATH=str(bindir)+os.pathsep+os.environ['PATH'],
                       STARSLAB_RUNNER_HOME=str(self.home/'selected'))
            installer = Path(__file__).resolve().parents[1]/'install.sh'
            result = subprocess.run(['sh', str(installer)], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Stop all runner processes', result.stderr)
        finally:
            import signal
            os.killpg(executor.pid, signal.SIGTERM)
            executor.wait()

    def test_fresh_simulation(self):
        config = initialize(self.home)
        self.assertEqual(config['mode'], 'dry_run')
        self.assertFalse(config['allow_live'])
        self.assertEqual(config['account_lock_owner']['home'], str(self.home))
        self.assertEqual((self.home/'config.json').stat().st_mode & 0o777, 0o600)

    def test_running_journal_refuses_upgrade(self):
        self.legacy()
        store = Journal(self.home/'htx-dry_run.sqlite')
        try:
            with self.assertRaises(RuntimeError):
                upgrade(self.home, original_stopped=True, original_owner=local_owner(self.home))
        finally:
            store.close()

    def test_preserves_live_configuration_and_ledger(self):
        legacy = self.legacy(True)
        credentials = self.home/'credentials.env'
        credentials.write_text('private placeholder')
        credentials.chmod(0o600)
        ledger = self.home/'htx-live.sqlite'
        ledger.write_bytes(b'ledger bytes including pending intents')
        ledger.chmod(0o600)
        config = upgrade(self.home, original_stopped=True, original_owner=local_owner(self.home))
        self.assertEqual({k:v for k,v in config.items() if k!='account_lock_owner'}, legacy)
        self.assertEqual(credentials.read_text(), 'private placeholder')
        self.assertEqual(ledger.read_bytes(), b'ledger bytes including pending intents')

    def test_running_account_refuses_upgrade(self):
        config = self.legacy(True)
        handle = acquire_local(config, self.account_directory)
        try:
            with self.assertRaises(RuntimeError):
                upgrade(self.home, original_stopped=True, original_owner=local_owner(self.home))
        finally:
            handle.close()

    def test_requires_explicit_ownership_and_stopped_confirmation(self):
        self.legacy()
        with self.assertRaises(ValueError):
            upgrade(self.home)
        with self.assertRaises(ValueError):
            upgrade(self.home, original_stopped=True)

    def test_foreign_or_invalid_owner_refused_without_mutation(self):
        self.legacy(True)
        before = (self.home/'config.json').read_bytes()
        for identity in ('0'*64, 'invalid'):
            owner = local_owner(self.home)
            owner['machine_id'] = identity
            with self.assertRaises(ValueError):
                upgrade(self.home, original_stopped=True, original_owner=owner)
            self.assertEqual((self.home/'config.json').read_bytes(), before)


if __name__=='__main__':
    unittest.main()
