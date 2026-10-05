"""Read-only HTX subaccount check. Never submits orders or transfers funds.

Run with SOPS-injected HTX_API_KEY, HTX_API_SECRET and HTX_SUBACCOUNT_UID:
  .venv-bots/bin/python scripts/htx_preflight.py
"""

import os
import sys


def inspect_account(exchange, expected_uid):
    uid = str(exchange.spot_private_get_v2_user_uid()["data"])
    if uid != str(expected_uid):
        raise ValueError("API key UID differs from the configured subaccount UID")
    accounts = exchange.fetch_accounts()
    spot = [a for a in accounts if a.get("type") == "spot"]
    if len(spot) != 1:
        raise ValueError("Expected exactly one spot account")
    balance = exchange.fetch_balance({"type": "spot"})
    exchange.load_markets()
    btc = exchange.market("BTC/USDT")
    if not btc.get("spot") or btc.get("active") is False:
        raise ValueError("BTC/USDT spot market unavailable")
    return {
        "uid": uid,
        "spot_account": spot[0]["id"],
        "free_usdt": balance["free"].get("USDT", 0),
        "btc_min_order_usdt": (btc.get("limits", {}).get("cost") or {}).get("min"),
    }


def main():
    names = ("HTX_API_KEY", "HTX_API_SECRET", "HTX_SUBACCOUNT_UID")
    if any(not os.environ.get(n) for n in names):
        print("Missing HTX_API_KEY, HTX_API_SECRET or HTX_SUBACCOUNT_UID", file=sys.stderr)
        return 2
    import ccxt

    exchange = ccxt.htx({
        "apiKey": os.environ["HTX_API_KEY"],
        "secret": os.environ["HTX_API_SECRET"],
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })
    try:
        result = inspect_account(exchange, os.environ["HTX_SUBACCOUNT_UID"])
    except Exception as exc:
        # Exchange exception strings can contain signed URLs. Do not print them.
        print(f"HTX preflight failed ({type(exc).__name__}); check UID, key permissions and IP binding",
              file=sys.stderr)
        return 1
    for key, value in result.items():
        print(f"{key}: {value}")
    print("Read-only checks passed. Trading permission and order execution remain unverified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
