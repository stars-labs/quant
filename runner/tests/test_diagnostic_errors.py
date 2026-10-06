import unittest
from types import SimpleNamespace
from starslab_runner.exchange import HTX, wallet_values
from starslab_runner.errors import (AccountIdentityMismatch, WalletCashMismatch,
    WalletHoldingsMismatch, InvalidWalletData, InvalidFeeQuote)


class DiagnosticTests(unittest.TestCase):
    def adapter(self, balance):
        return HTX(SimpleNamespace(fetch_balance=lambda params:balance), 'dry_run')

    def test_fixed_reasons_are_value_errors_and_contain_no_external_input(self):
        for cls in (AccountIdentityMismatch, WalletCashMismatch, WalletHoldingsMismatch,
                    InvalidWalletData, InvalidFeeQuote):
            error = cls()
            self.assertIsInstance(error, ValueError)
            self.assertTrue(error.reason)
            with self.assertRaises(TypeError):
                cls('secret signed URL')

    def test_account_identity_mismatch(self):
        ex = SimpleNamespace(spot_private_get_v2_user_uid=lambda:{'code':200,'data':'wrong'},
                             spot_private_get_v1_account_accounts=lambda:{'status':'ok','data':[]})
        with self.assertRaises(AccountIdentityMismatch):
            HTX(ex, 'live', '123', '456')

    def test_wallet_mismatch_reasons(self):
        store = SimpleNamespace(cash=lambda:10, holdings=lambda:[{'asset':'BTC','quantity':1}])
        for balance, error in (({'USDT':9},WalletCashMismatch),
                               ({'USDT':10,'BTC':2},WalletHoldingsMismatch)):
            adapter = self.adapter({'total':balance})
            adapter.mode = 'live'
            with self.assertRaises(error):
                adapter.check(store)

    def test_invalid_wallet_shapes_and_values(self):
        for balance in ({}, {'total':None}, {'total':{'USDT':'secret signed URL'}},
                        {'total':{'BTC':float('nan')}}, {'total':{'BTC':-1}}):
            with self.assertRaises(InvalidWalletData) as caught:
                wallet_values(balance, 'total')
            self.assertNotIn('secret', str(caught.exception))

    def test_bad_fee_quote_refuses_before_intent(self):
        for fee in (None, {'symbol':'BTC/USDT','taker':.0031},
                    {'symbol':'BTC/USDT','taker':'secret signed URL'},
                    {'symbol':'BTC/USDT','taker':None}):
            ex = SimpleNamespace(market=lambda symbol:{'spot':True},
                                 fetch_ticker=lambda symbol:{'ask':100},
                                 fetch_trading_fee=lambda symbol:fee)
            adapter = HTX(ex, 'dry_run')
            adapter.mode = 'live'
            with self.assertRaises(InvalidFeeQuote) as caught:
                adapter.submit(SimpleNamespace(), 'trend', 'BTC', 'buy', 'action', 'position',20)
            self.assertNotIn('secret',str(caught.exception))


if __name__=='__main__':
    unittest.main()
