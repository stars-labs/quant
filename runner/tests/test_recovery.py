import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from starslab_runner.config import DEFAULT, private_json
from starslab_runner.journal import Journal
from starslab_runner.recovery import backup, diagnose, verify_backup, restore


class RecoveryTest(unittest.TestCase):
    def test_backup_includes_wal_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            private_json(home/'config.json',DEFAULT)
            store = Journal(home/'htx-dry_run.sqlite')
            try:
                store.bind(json.dumps(['htx','dry_run',None,None]))
                store.fund('2026-10-01',100,100)
                target = home/'saved.sqlite'
                backup(home/'htx-dry_run.sqlite',target)
                self.assertEqual(verify_backup(target),{'integrity':'ok','orders':0,'funding':1})
                self.assertEqual(target.stat().st_mode & 0o777,0o600)
                with self.assertRaises(ValueError):
                    backup(home/'htx-dry_run.sqlite',target)
                restored = Journal(target)
                try:
                    restored.bind(json.dumps(['htx','dry_run',None,None]))
                    self.assertEqual(restored.cash(),200)
                finally:
                    restored.close()
                with target.open('ab') as handle:
                    handle.write(b'corruption')
                with self.assertRaises(ValueError):
                    verify_backup(target)
            finally:
                store.close()

    def test_restore_requires_stopped_confirmation_matching_identity_and_empty_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            store = Journal(home/'source.sqlite')
            store.bind(json.dumps(['htx','dry_run',None,None]))
            store.fund('2026-10-01',100,100)
            backup(home/'source.sqlite',home/'backup.sqlite')
            store.close()
            target = home/'restored'
            with self.assertRaises(ValueError):
                restore(home/'backup.sqlite',target,DEFAULT)
            self.assertFalse(target.exists())
            with self.assertRaises(ValueError):
                restore(home/'backup.sqlite',target,{**DEFAULT,'account_uid':'wrong'},True)
            self.assertFalse(target.exists())
            restore(home/'backup.sqlite',target,DEFAULT,True)
            recovered = Journal(target/'htx-dry_run.sqlite')
            try:
                self.assertEqual(recovered.cash(),200)
            finally:
                recovered.close()
            with self.assertRaises(ValueError):
                restore(home/'backup.sqlite',target,DEFAULT,True)

    def test_doctor_reads_locked_journal_without_mutating_or_leaking(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            private_json(home/'config.json',DEFAULT)
            store = Journal(home/'htx-dry_run.sqlite')
            try:
                store.bind(json.dumps(['htx','dry_run',None,None]))
                store.fund('2026-10-01',100,100)
                result = diagnose(home)
                self.assertEqual(next(row for row in result if row['check']=='journal')['status'],'ok')
                self.assertEqual(next(row for row in result if row['check']=='heartbeat')['status'],'attention')
                self.assertEqual(store.cash(),200)
            finally:
                store.close()

    def test_doctor_invalid_config_has_actionable_safe_output(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            (home/'config.json').write_text('secret-key-in-invalid-json')
            result = diagnose(home)
            self.assertEqual(result[0]['status'],'attention')
            self.assertNotIn('secret-key',json.dumps(result))
