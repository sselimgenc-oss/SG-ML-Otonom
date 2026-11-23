"""Cikis kipleri (basa-bas / kismi kar alma) motor testleri (docs/cikis-kipleri-spec.md). Yalniz sentetik veri; var/history yok.
Kapaliyken eski davranis, basa-bas tetigi, kismi kapanis muhasebesi, kagit = geri test paritesi."""
from __future__ import annotations

import numpy as np
import pytest
from test_engine_05_spec import BTC, H, M1, T0, Env, make_cfg  # noqa: F401  (sentetik motor duzenegi)

from trader_core import exit_modes as XM
from trader_engine import position_manager as PM
from trader_engine.errors import ConfigError
from trader_engine.position_manager import ExitContext

D1 = T0 + H


def _ctx(high, last, D=D1):
    return ExitContext(bar_close_ts=D, highs=np.array([high]), lows=np.array([100.5]), atrs=np.array([1.0]),
                       regime_last="trend_up", last_close=last, n_closed=1)


def _run(tmp, *, mode="paper", modes=None, high=104.0, price=104.0, drop_low=None):
    """Giris -> D1 karar adimi (en iyi uc `high`) -> dolumlar -> istege bagli dusus. (env, trade_id, ledger_trade)."""
    over = {"exit_modes": modes} if modes is not None else {}
    tmp.mkdir(parents=True, exist_ok=True)
    env = Env(tmp, mode=mode, **over)
    env.start()
    p = env.open_pos(BTC, T0, entry=100.0, stop=98.0)
    for k in range(1, 60):
        env.step(T0 + k * M1, pairs=(BTC,), price=price, hi=price, lo=price)
    env.src.ctx[(BTC, D1)] = _ctx(high, price)
    env.decide(D1)
    env.step(D1, pairs=(BTC,), price=price, hi=price, lo=price)
    if drop_low is not None:
        env.step(D1 + M1, pairs=(BTC,), price=drop_low, hi=price, lo=drop_low)
    t = env.real_ledger.get_trade(p.trade_id)
    return env, p.trade_id, t


def _snap(env, t):
    return (t.exit_reason, t.exit_price, t.fee_exit, t.realized_pnl, t.r_multiple, round(env.broker.account().wallet, 9))


# ----------------------------------------------------------------------------------------------- yapilandirma
def test_config_defaults_off_and_validation(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    cfg = make_cfg(tmp_path)
    assert cfg.exit_modes == {}
    cfg = make_cfg(tmp_path / "a", exit_modes={"default": {"breakeven": True, "partial": {"trigger_r": 2.0, "frac": 0.3}}})
    assert cfg.exit_modes["default"]["breakeven"] == {"trigger_r": 1.0, "offset_bps": 15.0}
    assert cfg.exit_modes["default"]["partial"] == {"trigger_r": 2.0, "frac": 0.3}
    for bad in ({"default": {"breakeven": {"trigger_r": 0.1}}}, {"default": {"partial": {"frac": 1.0}}},
                {"default": {"nope": True}}, {"T1@2h": {"breakeven": True}}, {"default": {"breakeven": {"x": 1}}}):
        with pytest.raises(ConfigError):
            make_cfg(tmp_path / "b", exit_modes=bad)


def test_exit_modes_rejected_outside_paper_and_backtest(tmp_path):
    with pytest.raises(ConfigError, match="exit_modes"):
        make_cfg(tmp_path, mode="testnet", exit_modes={"default": {"breakeven": True}})


def test_resolve_precedence_and_lesson_flags():
    cm = XM.build_config({"default": {"breakeven": True}, "T1": {"partial": True}, "T1@1h": {"breakeven": {"trigger_r": 2.0}}})
    m = XM.resolve(cm, "T1", "1h")
    assert m.breakeven and m.be_trigger_r == 2.0 and not m.partial        # en dar anahtar kazanir (tam yerine koyar)
    m = XM.resolve(cm, "T1", "15m")
    assert m.partial and not m.breakeven
    m = XM.resolve(cm, "R1", "1h")
    assert m.breakeven and not m.partial
    assert XM.resolve({}, "T1", "1h") is None
    f = XM.resolve({}, "T1", "1h", {XM.PARAM_BREAKEVEN: 1, XM.PARAM_PARTIAL: 0})     # ders bayragi: yalniz T1
    assert f.breakeven and not f.partial
    assert XM.resolve({}, "R1", "1h", {XM.PARAM_BREAKEVEN: 1}) is None


def test_partial_qty_rounding_and_min_limits():
    assert XM.partial_qty(6.369, 0.5, 0.001, 0.001, 5.0, 100.0) == pytest.approx(3.184)
    assert XM.partial_qty(0.003, 0.5, 0.001, 0.001, 5.0, 100.0) is None            # kalan/kapanan min adet altinda
    assert XM.partial_qty(0.05, 0.5, 0.001, 0.001, 5.0, 100.0) is None              # notional 2.5 < 5
    assert XM.blend_exit(3.0, 110.0, 1.0, 100.0) == pytest.approx(107.5)


# ----------------------------------------------------------------------------------------------- saf karar katmani
def _pos(env):
    return env.state.position_for_pair(BTC)


def test_apply_exit_modes_breakeven_pure(tmp_path):
    env = Env(tmp_path)
    env.start()
    pos = env.open_pos(BTC, T0, entry=100.0, stop=98.0)
    none = PM.ExitDecision("none")
    modes = XM.from_flags(True, False)
    assert PM.apply_exit_modes(pos, _ctx(102.0, 101.0), none, None) is none            # kip yok: ayni nesne
    assert PM.apply_exit_modes(pos, _ctx(102.0, 101.0), none, modes) is none           # 102,02 (=+1R) altinda
    d = PM.apply_exit_modes(pos, _ctx(103.0, 102.5), none, modes)
    assert d.kind == "stop_update" and d.new_stop == pytest.approx(pos.entry_price * 1.0015)
    ex = PM.ExitDecision("exit", "regime_flip")
    assert PM.apply_exit_modes(pos, _ctx(103.0, 102.5), ex, modes) is ex                # cikis kararina dokunmaz
    trail = PM.ExitDecision("stop_update", None, 101.5, None)                           # iz stopu BE'den siki: iz kazanir
    assert PM.apply_exit_modes(pos, _ctx(103.0, 102.5), trail, modes) is trail
    loose = PM.ExitDecision("stop_update", None, 99.0, None)                            # BE daha siki: BE kazanir
    assert PM.apply_exit_modes(pos, _ctx(103.0, 102.5), loose, modes).new_stop == pytest.approx(pos.entry_price * 1.0015)
    env.close()


def test_apply_exit_modes_short_mirror(tmp_path):
    env = Env(tmp_path)
    env.start()
    pos = env.open_pos(BTC, T0, side="short", entry=100.0, stop=102.0)
    modes = XM.from_flags(True, False)
    ctx = ExitContext(bar_close_ts=D1, highs=np.array([99.5]), lows=np.array([97.5]), atrs=np.array([1.0]),
                      regime_last="trend_down", last_close=98.0, n_closed=1)
    d = PM.apply_exit_modes(pos, ctx, PM.ExitDecision("none"), modes)
    assert d.kind == "stop_update" and d.new_stop == pytest.approx(pos.entry_price * (1 - 0.0015))
    env.close()


# ----------------------------------------------------------------------------------------------- kapaliyken ayni
def _snap_of(tmp, **kw):
    env, tid, _ = _run(tmp, **kw)
    out = _snap(env, env.real_ledger.get_trade(tid))
    env.close()
    return out


def test_modes_off_or_unreached_is_byte_identical(tmp_path):
    base = _snap_of(tmp_path / "base", modes=None, drop_low=97.0)
    off = _snap_of(tmp_path / "off", modes={}, drop_low=97.0)
    far = {"default": {"breakeven": {"trigger_r": 5.0}, "partial": {"trigger_r": 5.0}}}   # tetik ulasilmaz
    unreached = _snap_of(tmp_path / "far", modes=far, drop_low=97.0)
    assert base == off == unreached


# ----------------------------------------------------------------------------------------------- basa-bas
def test_breakeven_moves_stop_and_exits_above_entry(tmp_path):
    env, tid, _ = _run(tmp_path, modes={"default": {"breakeven": True}}, high=103.0, price=103.0)
    p = env.state.get_position(tid)
    assert p.status == "open"
    assert p.entry_price == pytest.approx(100.02)
    assert p.current_stop > p.entry_price and p.current_stop == pytest.approx(p.entry_price * 1.0015, abs=0.011)
    stops = [o for o in env.broker.open_orders(BTC) if o.role == "stop"]
    assert len(stops) == 1 and stops[0].trigger_price == pytest.approx(p.current_stop)
    env.step(D1 + M1, pairs=(BTC,), price=103.0, hi=103.0, lo=100.0)                     # mum ici dusus: BE stopu vurur (bosluk yok)
    t = env.real_ledger.get_trade(tid)
    assert t.exit_reason == "trail_stop"                                                  # defter semasi: yeni neden yok
    assert t.exit_price > t.entry_price * 1.0005                                          # +15 bps - 5 bps stop kaymasi
    assert env.engine.counters().get("partial_fills", 0) == 0
    env.close()


def test_breakeven_not_triggered_below_threshold(tmp_path):
    env, tid, _ = _run(tmp_path, modes={"default": {"breakeven": True}}, high=102.0, price=102.0)   # +0,98 R
    p = env.state.get_position(tid)
    assert p.current_stop == pytest.approx(98.0)
    env.close()


# ----------------------------------------------------------------------------------------------- kismi kapanis
PT = {"default": {"partial": {"trigger_r": 1.5, "frac": 0.5}}}


def test_partial_fill_keeps_position_open_and_resizes_stop(tmp_path):
    env, tid, _ = _run(tmp_path, modes=PT)
    p = env.state.get_position(tid)
    assert p.status == "open" and p.qty == pytest.approx(6.369 - 3.184)
    pk = env.state.kv_get(f"partial:{tid}")
    assert pk["state"] == "done" and pk["qty"] == pytest.approx(3.184) and pk["price"] < 104.0
    bp = [x for x in env.broker.positions() if x.pair == BTC][0]
    assert bp.qty == pytest.approx(p.qty)                                                 # state = broker
    stops = [o for o in env.broker.open_orders(BTC) if o.role == "stop" and o.status == "new"]
    assert len(stops) == 1 and stops[0].qty == pytest.approx(p.qty)                       # stop kalan adede gore
    assert env.real_ledger.get_trade(tid).exit_ts is None                                  # defter: kapanmadi
    assert env.engine.counters()["partial_fills"] == 1
    # ikinci karar adimi: kismi bir kez
    D2 = D1 + H
    env.src.ctx[(BTC, D2)] = _ctx(105.0, 104.0, D2)
    env.decide(D2)
    assert env.engine.counters()["partial_submitted"] == 1
    env.close()


def test_open_extra_fields_explain_wallet_with_partial_fill(tmp_path):
    """Durum dosyasi acik pozisyonda giris komisyonu, fonlama ve kismi cikis K/Z+komisyonunu verir; kasa = baslangic - bunlar."""
    env, tid, _ = _run(tmp_path, modes=PT)
    ex = env.engine._open_extra()[tid]                                                    # noqa: SLF001
    pk = env.state.kv_get(f"partial:{tid}")
    t = env.real_ledger.get_trade(tid)
    assert ex["partial_fee_usd"] == pytest.approx(pk["fee"]) and ex["partial_realized_usd"] == pytest.approx(
        (pk["price"] - t.entry_price) * pk["qty"]) and ex["partial_realized_usd"] > 0
    assert ex["fee_paid_entry"] == pytest.approx(t.fee_entry)
    beklenen = (1000.0 - ex["fee_paid_entry"] - ex["funding_paid"] + ex["partial_realized_usd"] - ex["partial_fee_usd"])
    assert env.broker.account().wallet == pytest.approx(beklenen, abs=1e-6)
    from trader_core import mutabakat as M
    pos = [{"trade_id": tid, "side": "long", **ex}]
    k = M.kontrol_kasa(baslangic=1000.0, net_sql=0.0, net_motor=0.0, status={"wallet": env.broker.account().wallet, "open_positions": pos})
    assert k["sonuc"] == "geçti", k
    env.close()


def test_partial_accounting_equals_wallet_and_legs(tmp_path):
    env, tid, _ = _run(tmp_path, modes=PT, drop_low=97.0)                                 # kalan parca ilk stopta kapanir
    t = env.real_ledger.get_trade(tid)
    pk = env.state.kv_get(f"partial:{tid}")
    assert t.exit_ts is not None and t.exit_reason == "trail_stop"                        # +1R'de iz stopu (101) kuruldu, 97'de bosluk
    q1, p1 = pk["qty"], pk["price"]
    q2 = t.qty - q1
    entry = t.entry_price
    # ikinci parca fiyati: karma fiyattan geri cozulur
    p2 = (t.exit_price * t.qty - q1 * p1) / q2
    assert p2 < 98.0 < p1                                                                  # kalan parca zararla kapandi
    gross = q1 * (p1 - entry) + q2 * (p2 - entry)
    assert t.gross_pnl == pytest.approx(gross, abs=1e-6)
    f2 = q2 * p2 * 0.0005
    assert t.fee_exit == pytest.approx(pk["fee"] + f2, abs=1e-6)
    assert t.realized_pnl == pytest.approx(gross - t.fee_entry - t.fee_exit - t.funding_paid, abs=1e-6)
    assert env.broker.account().wallet == pytest.approx(1000.0 + t.realized_pnl, abs=1e-6)  # defter = broker cuzdani
    assert t.r_multiple == pytest.approx(t.realized_pnl / t.planned_risk, abs=1e-9)
    env.close()


def test_partial_skipped_when_below_min_qty(tmp_path):
    from trader_engine.types import SymbolRules
    env = Env(tmp_path, exit_modes=PT)
    env.start()
    p = env.open_pos(BTC, T0, entry=100.0, stop=98.0)
    env.broker.rules = lambda pair: SymbolRules(pair, pair.replace("/", ""), 0.01, 0.001, 4.0, 1e9, 5.0)   # min adet 4 > 3,18
    for k in range(1, 60):
        env.step(T0 + k * M1, pairs=(BTC,), price=104.0, hi=104.0, lo=104.0)
    env.src.ctx[(BTC, D1)] = _ctx(104.0, 104.0)
    env.decide(D1)
    assert env.state.kv_get(f"partial:{p.trade_id}")["state"] == "skipped"
    assert env.engine.counters()["partial_skipped"] == 1
    assert env.state.get_position(p.trade_id).qty == pytest.approx(6.369)               # pozisyon tek parca surer
    env.close()


# ----------------------------------------------------------------------------------------------- parite
@pytest.mark.parametrize("modes", [PT, {"default": {"breakeven": True}}, {"default": {"breakeven": True, "partial": True}}])
def test_paper_equals_backtest(tmp_path, modes):
    a_env, a_id, ta = _run(tmp_path / "paper", mode="paper", modes=modes, drop_low=97.0)
    b_env, b_id, tb = _run(tmp_path / "bt", mode="backtest", modes=modes, drop_low=97.0)
    ta, tb = a_env.real_ledger.get_trade(a_id), b_env.real_ledger.get_trade(b_id)
    assert _snap(a_env, ta) == _snap(b_env, tb)
    assert a_env.engine.counters().get("partial_fills", 0) == b_env.engine.counters().get("partial_fills", 0)


def test_paper_config_modes_are_open_and_paper_equals_backtest(tmp_path):
    """19.11 kullanici karari: kagit yapilandirmasinda cikis kipleri ACIK (spec varsayilanlari); kagit = geri test paritesi bu
    yapilandirmayla (kip acik) korunur. Testnet/canli/geri test varsayilani degismez (bos)."""
    import json
    from pathlib import Path
    cfgdir = Path(__file__).resolve().parents[2] / "config"
    raw = json.loads((cfgdir / "engine.paper.json").read_text())["exit_modes"]
    assert raw == {"default": {"breakeven": True, "partial": True}}
    for other in ("engine.base.json", "engine.testnet.json", "engine.learner.json"):
        assert "exit_modes" not in json.loads((cfgdir / other).read_text())
    # 23.11 kullanici karari: canli = kagit (canli yapilandirma exit_modes'i tasir ama motor FAZ 2'ye kadar yok sayar)
    assert json.loads((cfgdir / "engine.live.json").read_text())["exit_modes"] == raw
    a_env, a_id, _ = _run(tmp_path / "paper", mode="paper", modes=raw, drop_low=97.0)
    b_env, b_id, _ = _run(tmp_path / "bt", mode="backtest", modes=raw, drop_low=97.0)
    assert _snap(a_env, a_env.real_ledger.get_trade(a_id)) == _snap(b_env, b_env.real_ledger.get_trade(b_id))


def test_lesson_flags_enable_modes_from_active_params(tmp_path):
    """Defter etkin surumunde `exit_breakeven=1` -> kip T1 icin acilir (yapilandirma bos)."""
    env = Env(tmp_path)
    env.start()
    assert env.engine._exit_modes(env.state.position_for_pair(BTC) or type("P", (), {"setup": "T1", "trigger_tf": "1h"})) is None
    env.engine._mode_flags = {XM.PARAM_BREAKEVEN: 1, XM.PARAM_PARTIAL: 0}
    pos = type("P", (), {"setup": "T1", "trigger_tf": "1h"})
    m = env.engine._exit_modes(pos)
    assert m.breakeven and not m.partial
    env.close()
