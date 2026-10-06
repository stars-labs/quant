from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from starslab_runner.account_lock import acquire


class AccountLockTest(unittest.TestCase):
    def test_same_account_blocks_independent_journals_and_releases(self):
        with tempfile.TemporaryDirectory() as folder:
            config = {'mode':'live','venue':'htx','account_uid':'123','spot_account_id':'456'}
            directory = Path(folder)/'locks'
            first = acquire(config,directory)
            try:
                with self.assertRaises(RuntimeError):
                    acquire(config,directory)
                other = acquire({**config,'account_uid':'789'},directory)
                other.close()
            finally:
                first.close()
            recovered = acquire(config,directory)
            recovered.close()

    def test_dry_run_does_not_claim_live_account(self):
        self.assertIsNone(acquire({'mode':'dry_run'}))
