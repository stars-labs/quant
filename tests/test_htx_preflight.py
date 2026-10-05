"""Read-only onboarding checks using a fake exchange."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from htx_preflight import inspect_account


class Exchange:
    def spot_private_get_v2_user_uid(self):
        return {"data": 123}

    def fetch_accounts(self):
        return [{"id": "7", "type": "spot"}]

    def fetch_balance(self, params):
        assert params == {"type": "spot"}
        return {"free": {"USDT": 200}}

    def load_markets(self):
        pass

    def market(self, symbol):
        assert symbol == "BTC/USDT"
        return {"spot": True, "active": True, "limits": {"cost": {"min": 1}}}


def test_account_matches_expected_uid():
    assert inspect_account(Exchange(), "123") == {
        "uid": "123", "spot_account": "7", "free_usdt": 200, "btc_min_order_usdt": 1,
    }


def test_wrong_uid_stops_before_balance_read():
    class WrongAccount(Exchange):
        def fetch_balance(self, params):
            raise AssertionError("Must stop before inspecting the wrong account")

    try:
        inspect_account(WrongAccount(), "456")
    except ValueError:
        return
    raise AssertionError("Wrong UID accepted")
