import contextlib
import copy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from starslab_runner.cli import main
from starslab_runner.config import DEFAULT, private_json, read_private_json, validate
from starslab_runner.journal import Journal


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.output = io.StringIO()

    def tearDown(self):
        self.tmp.cleanup()

    def command(self,*args):
        with contextlib.redirect_stdout(self.output),contextlib.redirect_stderr(self.output):
            return main(['--home',str(self.home),*args])

    def test_initialization_is_private_and_preserves_existing_settings(self):
        self.assertEqual(self.command('init'),0)
        config = read_private_json(self.home/'config.json')
        self.assertEqual(config['mode'],'dry_run')
        self.assertFalse(config['allow_live'])
        config['order_usdt']=10
        private_json(self.home/'config.json',config)
        self.assertEqual(self.command('init'),0)
        self.assertEqual(read_private_json(self.home/'config.json')['order_usdt'],10)
        self.assertEqual((self.home/'config.json').stat().st_mode & 0o777,0o600)

    def test_guided_setup_stays_simulation_without_funding_or_orders(self):
        with patch('starslab_runner.cli.exchange',side_effect=AssertionError('No exchange call expected')):
            self.assertEqual(self.command('setup'),0)
        config=read_private_json(self.home/'config.json')
        self.assertEqual(config['mode'],'dry_run')
        self.assertFalse(config['allow_live'])
        self.assertFalse((self.home/'htx-dry_run.sqlite').exists())

    def test_legacy_upgrade_requires_original_owner_and_stopped_attestations(self):
        self.command('init')
        config=read_private_json(self.home/'config.json')
        config.pop('account_lock_owner')
        config.update(monthly_trend_usdt=75,monthly_dca_usdt=25,order_usdt=10)
        private_json(self.home/'config.json',config)
        self.assertEqual(self.command('upgrade-owner','--confirm-original-stopped'),1)
        self.assertEqual(self.command('upgrade-owner','--confirm-original-stopped','--confirm-this-is-original-owner'),0)
        updated=read_private_json(self.home/'config.json')
        self.assertEqual({k:v for k,v in updated.items() if k!='account_lock_owner'},config)
        self.assertEqual(updated['account_lock_owner']['home'],str(self.home))

    def test_display_config_does_not_change_execution_settings(self):
        self.command('init')
        before = read_private_json(self.home/'config.json')
        file = self.home/'download.json'
        file.write_text(json.dumps({'api_base':'https://api.panda.qzz.io','upload_token':'1'*64}))
        file.chmod(0o644)
        self.assertEqual(self.command('connect-display',str(file)),0)
        after = read_private_json(self.home/'config.json')
        self.assertEqual({k:v for k,v in before.items() if k!='display_file'},
                         {k:v for k,v in after.items() if k!='display_file'})
        self.assertEqual(file.stat().st_mode & 0o777,0o600)

    def test_display_file_rejects_credentials(self):
        self.command('init')
        file = self.home/'download.json'
        file.write_text(json.dumps({'api_base':'https://api.panda.qzz.io','upload_token':'1'*64,'api_key':'secret-test'}))
        self.assertEqual(self.command('connect-display',str(file)),1)
        self.assertNotIn('secret-test',self.output.getvalue())

    def test_live_permission_is_not_implicitly_created_by_funding(self):
        self.command('init')
        self.assertEqual(self.command('fund'),0)
        self.assertEqual(self.command('fund'),0)
        self.assertFalse(read_private_json(self.home/'config.json')['allow_live'])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--home',str(self.home),'status']),0)
        self.assertEqual(json.loads(output.getvalue())['cash_usdt'],200)

    def test_cash_flow_command_is_idempotent_and_preserves_live_authorization(self):
        self.command('init')
        self.command('fund')
        for _ in range(2):
            self.assertEqual(self.command('cash-flow','--reference','withdraw-1','--trend','-20','--dca','-10'),0)
        store = Journal(self.home/'htx-dry_run.sqlite')
        try:
            self.assertEqual(store.cash(),170)
            self.assertEqual(store.net_funding(),170)
        finally:
            store.close()
        self.assertFalse(read_private_json(self.home/'config.json')['allow_live'])
        self.assertEqual(self.command('cash-flow','--reference','bad-deposit','--trend','10','--dca','0'),1)

    def test_live_cash_flow_rejects_unverified_exchange_balance(self):
        from unittest.mock import Mock
        self.command('init')
        config = read_private_json(self.home/'config.json')
        config.update(mode='live',allow_live=True,account_uid='123',spot_account_id='456')
        private_json(self.home/'config.json',config)
        store = Journal(self.home/'htx-live.sqlite')
        store.bind(json.dumps(['htx','live','123','456']))
        store.fund(datetime.now(timezone.utc).strftime('%Y-%m-01'),100,100)
        store.close()
        venue = Mock()
        venue.reconcile.return_value = True
        venue.balance.return_value = {'total':{'USDT':200}}
        with patch('starslab_runner.cli.exchange',return_value=venue):
            self.assertEqual(self.command('cash-flow','--reference','withdraw-live','--trend','-20','--dca','0'),1)
        store = Journal(self.home/'htx-live.sqlite')
        try:
            self.assertEqual(store.cash(),200)
            self.assertEqual(store.db.execute('SELECT count(*) FROM cash_flows').fetchone()[0],0)
        finally:
            store.close()
        venue.submit.assert_not_called()

    def test_history_reads_while_executor_holds_journal_lock(self):
        from starslab_runner.history import record_snapshot
        self.command('init')
        store = Journal(self.home/'htx-dry_run.sqlite')
        try:
            now = datetime.now(timezone.utc).isoformat()
            record_snapshot(store,1,now,now,200,100,200,.2)
            self.assertEqual(self.command('history'),0)
            self.assertIn('net_pnl_usdt',self.output.getvalue())
        finally:
            store.close()

    def test_status_available_while_executor_holds_journal_lock(self):
        self.command('init')
        private_json(self.home/'status.json',{'venue':'htx','environment':'dry_run',
            'observed_at':datetime.now(timezone.utc).isoformat(),'status':'healthy'})
        store = Journal(self.home/'htx-dry_run.sqlite')
        try:
            self.assertEqual(self.command('status'),0)
        finally:
            store.close()

    def test_exchange_exception_details_never_printed(self):
        self.command('init')
        with patch('starslab_runner.cli.exchange',side_effect=RuntimeError('private-access-key-in-signed-url')):
            self.assertEqual(self.command('run','--once'),1)
        self.assertNotIn('private-access-key',self.output.getvalue())

    def test_feed_url_and_local_boolean_limits_are_strict(self):
        for field,value in [('api_base','http://example.org'),('api_base','https://key:secret@example.org'),
                            ('allow_live','false'),('order_usdt',float('nan'))]:
            config = copy.deepcopy(DEFAULT)
            config[field]=value
            with self.assertRaises(ValueError):
                validate(config)
