"""Tests for strategies/health_check.py — the alert state machine and the IB probe.

Run: P=nautilus_equity/.venv/bin/python; $P -c "import sys; sys.path.insert(0,'tests'); import test_health_check as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
"""

from __future__ import annotations

import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))

import health_check as hc  # noqa: E402

H = 3600.0
DOWN = {"unit:x.service": (False, "服务 x.service", "failed")}
UP = {"unit:x.service": (True, "服务 x.service", "active")}


def run(state, results, t):
    return hc.evaluate(state, results, t)


def test_single_failure_does_not_alert():
    _, alerts, rec = run({}, DOWN, 100 * H)
    assert alerts == [] and rec == []


def test_second_consecutive_failure_alerts_once():
    s, _, _ = run({}, DOWN, 100 * H)
    s, alerts, _ = run(s, DOWN, 100 * H + 600)
    assert alerts == ["🔴 服务 x.service:failed"]
    s, alerts, _ = run(s, DOWN, 100 * H + 1200)
    assert alerts == []


def test_blip_then_recovery_is_silent():
    s, _, _ = run({}, DOWN, 100 * H)
    s, alerts, rec = run(s, UP, 100 * H + 600)
    assert alerts == [] and rec == [] and s["checks"] == {}


def test_recovery_announced_after_alert():
    s, _, _ = run({}, DOWN, 100 * H)
    s, _, _ = run(s, DOWN, 100 * H + 600)
    s, alerts, rec = run(s, UP, 100 * H + 1200)
    assert alerts == [] and rec == ["✅ 服务 x.service 已恢复"]
    assert s["checks"] == {}


def test_vanished_failed_unit_counts_as_recovered():
    s, _, _ = run({}, DOWN, 100 * H)
    s, _, _ = run(s, DOWN, 100 * H + 600)
    _, _, rec = run(s, {}, 100 * H + 1200)
    assert rec == ["✅ 服务 x.service 已恢复"]


def test_reminder_after_remind_hours():
    s, _, _ = run({}, DOWN, 100 * H)
    s, _, _ = run(s, DOWN, 100 * H + 600)
    s, alerts, _ = run(s, DOWN, 100 * H + 3 * H)
    assert alerts == []
    s, alerts, _ = run(s, DOWN, 100 * H + 600 + hc.REMIND_HOURS * H)
    assert alerts == ["🔴 服务 x.service:failed(仍未恢复)"]
    _, alerts, _ = run(s, DOWN, 100 * H + 1200 + hc.REMIND_HOURS * H)
    assert alerts == []


def test_state_survives_json_roundtrip():
    import json
    s, _, _ = run({}, DOWN, 100 * H)
    s = json.loads(json.dumps(s))
    _, alerts, _ = run(s, DOWN, 100 * H + 600)
    assert len(alerts) == 1


def test_format_message():
    msg = hc.format_message("desk", "game", ["🔴 a:b"], ["✅ c 已恢复"])
    assert msg == "🩺 健康检查 · desk(game)\n🔴 a:b\n✅ c 已恢复"


def _server(reply: bytes | None):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def handle():
        c, _ = srv.accept()
        c.recv(64)
        if reply:
            c.sendall(reply)
        else:
            threading.Event().wait(10)  # accept but never answer (stuck Gateway)
        c.close()

    threading.Thread(target=handle, daemon=True).start()
    return srv.getsockname()[1]


def test_ib_probe_ok_when_gateway_answers():
    port = _server(b"\x00\x00\x00\x1a187\x0020260926 12:00:00 UTC\x00")
    ok, _, detail = hc.probe_ib("127.0.0.1", port)["ib:api"]
    assert ok and detail == "握手成功"


def test_ib_probe_fails_when_connected_but_silent():
    port = _server(None)
    ok, _, _ = hc.probe_ib("127.0.0.1", port)["ib:api"]
    assert not ok


def test_ib_probe_fails_when_refused():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    ok, _, detail = hc.probe_ib("127.0.0.1", port)["ib:api"]
    assert not ok and "ConnectionRefusedError" in detail
