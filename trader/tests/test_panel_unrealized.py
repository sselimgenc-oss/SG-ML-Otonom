"""Acik pozisyon gerceklesmemis K/Z: status.json (eklemeli alanlar) + panel veri gecisi + statik kaynak guvenligi."""
import json
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from panel_support import NOW, ROOT, Env, status_doc
from trader_core import panel_data as P
from trader_engine import status as ST
from trader_engine.engine import Engine

UTC = timezone.utc
T0 = datetime(2026, 11, 16, 17, 59, tzinfo=UTC)


def _pos(tid, pair, side, qty, ep, status="open"):
    return NS(trade_id=tid, pair=pair, side=side, qty=qty, entry_price=ep, current_stop=ep * 0.9, status=status)


def _build(positions, marks):
    fields = {"open_positions": positions, "last_marks": marks, "last_minute_ts": T0, "last_decision_close": None,
              "last_candle_open": None, "tf": "1h", "param_version_id": 1, "strategy_name": "s", "strategy_version": "1",
              "entries_blocked_reason": None, "gate_code": "ok", "entries_open": True, "kill": False, "kill_state": "off",
              "wallet": 1000.0, "equity": 1000.0, "day_start_equity": 1000.0, "counters": {}, "ml": None}
    eng = NS(status_fields=lambda: fields, broker=None)
    w = ST.StatusWriter("x.json", NS(now=lambda: NOW), NS(bot="learner", mode="paper", loop_sleep_s=1))
    return w.build(eng)


def test_long_short_sign_and_totals():
    ts = T0 + timedelta(minutes=1)
    d = _build([_pos(1, "BTC/USDT", "long", 2.0, 100.0), _pos(2, "ETH/USDT", "short", 3.0, 50.0)],
               {"BTC/USDT": (103.0, ts), "ETH/USDT": (52.0, ts)})
    a, b = d["open_positions"]
    assert a["mark"] == 103.0 and a["notional_usd"] == 206.0
    assert a["unrealized_pnl_usd"] == pytest.approx(6.0) and a["unrealized_pct"] == pytest.approx(3.0)
    assert b["unrealized_pnl_usd"] == pytest.approx(-6.0) and b["unrealized_pct"] == pytest.approx(-4.0)   # short: fiyat yukseldi -> zarar
    assert d["unrealized_pnl_usd"] == pytest.approx(0.0)
    assert d["mark_ts"] == a["mark_ts"] and d["mark_ts"].endswith("Z")
    assert a["stop"] == 90.0 and a["entry_price"] == 100.0                       # eski alanlar degismedi
    json.dumps(d)


def test_short_profit_when_price_falls():
    d = _build([_pos(2, "ETH/USDT", "short", 3.0, 50.0)], {"ETH/USDT": (48.0, T0)})
    p = d["open_positions"][0]
    assert p["unrealized_pnl_usd"] == pytest.approx(6.0) and p["unrealized_pct"] == pytest.approx(4.0)


def test_null_when_no_price_never_faked():
    d = _build([_pos(1, "BTC/USDT", "long", 2.0, 100.0)], {})
    p = d["open_positions"][0]
    for k in ("mark", "notional_usd", "unrealized_pnl_usd", "unrealized_pct", "mark_ts"):
        assert p[k] is None
    assert d["unrealized_pnl_usd"] is None and d["mark_ts"] is None


def test_partial_price_total_only_known_and_no_positions_zero():
    d = _build([_pos(1, "BTC/USDT", "long", 1.0, 100.0), _pos(2, "ETH/USDT", "long", 1.0, 10.0)], {"BTC/USDT": (101.0, T0)})
    assert d["open_positions"][1]["unrealized_pnl_usd"] is None and d["unrealized_pnl_usd"] == pytest.approx(1.0)
    assert _build([], {})["unrealized_pnl_usd"] == 0.0


def test_remember_marks_uses_closed_1m_last_close():
    eng = NS(_last_marks={})
    bar = NS(last_c=42.5, close_ts=T0)
    Engine._remember_marks(eng, NS(bars={"BTC/USDT": bar, "X/USDT": NS(last_c=None, close_ts=T0)}))
    assert eng._last_marks == {"BTC/USDT": (42.5, T0)}
    Engine._remember_marks(eng, NS(bars=None))                                    # istisna sizmaz


def test_panel_passthrough(tmp_path):
    doc = _build([_pos(1, "BTC/USDT", "long", 2.0, 100.0)], {"BTC/USDT": (103.0, T0)})
    doc.update(loop_at=NOW.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    f = tmp_path / "status.json"
    f.write_text(json.dumps(doc))
    r = P.read_status(str(f), NOW)
    assert r["state"] == "live"
    assert r["data"]["unrealized_pnl_usd"] == pytest.approx(6.0) and r["data"]["mark_ts"] == doc["mark_ts"]
    assert r["data"]["open_positions"][0]["notional_usd"] == 206.0
    # eski status (alanlar yok) -> None, panel bozulmaz
    f.write_text(json.dumps(status_doc(NOW)))
    assert P.read_status(str(f), NOW)["data"]["unrealized_pnl_usd"] is None


def test_panel_js_safe_and_columns():
    js = (ROOT / "src/trader_panel/static/panel.js").read_text(encoding="utf-8")
    assert not re.search(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML", js)
    assert "'K/Z'" in js and "açık K/Z" in js and "'Giriş → şimdi'" in js        # yeni 4 sutunlu tablo; Mark/Tutar ayrintiya tasindi
    assert "'Büyüklük'" in js and "acik_kz" in js


def test_snapshot_embeds_unrealized(tmp_path):
    from trader_panel import snapshot as SN
    from trader_panel.data import PanelData, load_config
    e = Env(tmp_path)
    doc = status_doc(NOW - timedelta(seconds=5), unrealized_pnl_usd=7.61, mark_ts="2026-11-16T17:59:00.000Z")
    doc["open_positions"][0].update(mark=2010.0, notional_usd=603.0, unrealized_pnl_usd=2.7, unrealized_pct=0.45)
    (e.root / "var/learner/status.json").write_text(json.dumps(doc))
    html = SN.render(PanelData(load_config(e.cfg_path), clock=lambda: NOW))
    e.close()
    snap = json.loads(re.search(r'window\.__SNAPSHOT__=(\{.*?\});</script>', html, re.S).group(1))
    assert "/api/status" not in snap["data"]        # 9b-01: yalniz panel.js'in okudugu uclar gomulur
    pano = snap["data"]["/api/pano?bot=learner"]
    assert pano["serit"]["acik_kz"] == 7.61 and pano["acik"]["rows"][0]["kz_yuzde"] == 0.45
