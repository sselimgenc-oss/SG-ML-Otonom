"""Dayaniklilik portu (1L3A): 4a hata siniflandirma, 4b kurulum karantinasi + /karantina_kaldir, 4c tur koruyucusu,
4f saatlik sembol izleyicisi."""
import json
import types
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from test_telegram_ladder_impl import CHAT, Rig
from trader_core import telegram as T
from trader_engine import errors as E
from trader_engine import tur_koruyucu as TK
from trader_engine.engine import Engine
from trader_engine.marketdata.rest_public import ExchangeError
from trader_engine.sembol_izleme import SembolIzleyici
from trader_engine.strategies.lab import PriceActionLab

UTC = timezone.utc
T0 = datetime(2026, 12, 30, 10, 0, tzinfo=UTC)


# ------------------------------------------------------------------------------------------------ 4a
def test_error_classification():
    assert E.is_code_error(TypeError("x")) and E.is_code_error(ZeroDivisionError())
    assert not E.is_code_error(E.DataError("x")) and not E.is_code_error(OSError())
    assert not E.is_code_error(ExchangeError("net"))
    assert not E.is_code_error(json.JSONDecodeError("m", "d", 0))
    assert not E.is_code_error(ValueError("v"))                # veri yolunda ValueError gecici kalir
    assert E.is_strategy_error(ValueError("v")) and E.is_strategy_error(KeyError("k"))
    assert not E.is_strategy_error(E.ConfigError("c"))         # ConfigError ValueError ama motor hatasi
    assert not E.is_strategy_error(ExchangeError("net"))


# ------------------------------------------------------------------------------------------------ 4b: kod hatasi yalitimi
def test_lab_compute_tf_hooks():
    lab = PriceActionLab(("T1@1h", "R1@1h"))
    ctx = types.SimpleNamespace(tf="1h")
    lab.compute = lambda c: (_ for _ in ()).throw(TypeError("bozuk"))
    errs = []
    out = lab.compute_tf(ctx, on_error=lambda k, e: errs.append(k))
    assert out == {} and errs == ["core"]                      # kod hatasi kancaya gider, tur dusmez
    with pytest.raises(TypeError):
        lab.compute_tf(ctx)                                    # kanca yoksa eski davranis
    lab.compute = lambda c: (_ for _ in ()).throw(ExchangeError("net"))
    with pytest.raises(ExchangeError):
        lab.compute_tf(ctx, on_error=lambda k, e: None)        # gecici hata asla yutulmaz


# ------------------------------------------------------------------------------------------------ 4c
class _Clock:
    def __init__(self):
        self.slept = []

    def sleep(self, s):
        self.slept.append(s)


def _eng(paper=True, mode="paper"):
    blocks = []
    state = types.SimpleNamespace(block_has=lambda r: r in blocks, kv_get=lambda k, d=None: None)
    e = types.SimpleNamespace(strict=False, is_paper=paper, cfg=types.SimpleNamespace(mode=mode), clock=_Clock(), state=state,
                              _c=Counter(), _last_minute=1, _adv_errors=0, _consec={}, _consec_errors=0,
                              _block=blocks.append, blocks=blocks, _restore_broker=lambda s: None)
    return e


def test_tur_transient_unbounded_backoff_paper_never_blocks():
    e = _eng()
    k = TK.TurKoruyucu(e)
    for _ in range(12):
        k.calistir(lambda: (_ for _ in ()).throw(E.DataError("kesinti")))
    assert e.blocks == [] and len(e.clock.slept) == 12 and max(e.clock.slept) == TK.BACKOFF_CAP_S
    k.calistir(lambda: None)
    assert k.transient == 0


def test_tur_transient_live_blocks_entries_after_limit():
    e = _eng(paper=False, mode="live")
    k = TK.TurKoruyucu(e)
    for _ in range(TK.HATA_TEKRAR_SINIRI):
        k.calistir(lambda: (_ for _ in ()).throw(OSError("net")))
    assert e.blocks == ["engine_errors"]


def test_tur_code_error_restores_memory_and_stops_after_limit():
    e = _eng()

    def bozuk():
        e._last_minute = 99
        e._c["steps"] += 5
        raise TypeError("yari islenmis")
    k = TK.TurKoruyucu(e)
    for i in range(TK.KOD_HATASI_SINIRI - 1):
        k.calistir(bozuk)
        assert e._last_minute == 1 and e._c["steps"] == 0       # yari islenmis tur geri alindi
    with pytest.raises(E.EngineExit) as ei:
        k.calistir(bozuk)
    assert ei.value.code == 4


def test_tur_code_error_live_raises_immediately_and_state_error_passes():
    e = _eng(paper=False, mode="testnet")
    with pytest.raises(TypeError):
        TK.TurKoruyucu(e).calistir(lambda: (_ for _ in ()).throw(TypeError("k")))
    e2 = _eng()
    with pytest.raises(E.StateError):
        TK.TurKoruyucu(e2).calistir(lambda: (_ for _ in ()).throw(E.StateError("s")))


# ------------------------------------------------------------------------------------------------ 4f
def _info(**status):
    def sym(name, st):
        return {"symbol": name, "status": st, "contractType": "PERPETUAL",
                "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
                            {"filterType": "MIN_NOTIONAL", "notional": "5"}]}
    return {"symbols": [sym(n, s) for n, s in status.items()]}


def test_symbol_watcher_blocks_warns_crit_and_recovers():
    cur = {"v": _info(BTCUSDT="TRADING", ETHUSDT="TRADING")}
    held = {"ETH/USDT"}
    w = SembolIzleyici(["BTC/USDT", "ETH/USDT"], lambda: cur["v"], has_open_fn=lambda p: p in held)
    assert w.check(T0) is False and not w.blocked
    cur["v"] = _info(BTCUSDT="SETTLING", ETHUSDT="BREAK")
    assert w.check(T0 + timedelta(minutes=30)) is False         # saatte bir: erken
    assert w.check(T0 + timedelta(hours=1)) is True
    assert w.is_blocked("BTC/USDT") and w.is_blocked("ETH/USDT")
    assert {(s, p) for s, p, _ in w.events} == {("WARN", "BTC/USDT"), ("CRIT", "ETH/USDT")}
    w.events.clear()
    cur["v"] = _info(BTCUSDT="TRADING", ETHUSDT="TRADING")
    assert w.check(T0 + timedelta(hours=2)) is True and not w.blocked
    assert [s for s, _, _ in w.events] == ["INFO", "INFO"]


def test_symbol_watcher_fetch_error_and_missing_symbol():
    def boom():
        raise ExchangeError("net")
    w = SembolIzleyici(["BTC/USDT"], boom)
    assert w.check(T0) is False and not w.blocked              # hata durumu degistirmez
    w2 = SembolIzleyici(["BTC/USDT"], lambda: _info(XUSDT="TRADING"))
    assert w2.check(T0) and w2.is_blocked("BTC/USDT")           # exchangeInfo'da yok = engel


def test_gate_symbol_blocked_hook_exists():
    import inspect
    from trader_engine import gates
    assert "symbol_not_trading" in inspect.getsource(gates.EntryGate.decide)


# ------------------------------------------------------------------------------------------------ Telegram
def test_telegram_dayaniklilik_tick_alerts_once(tmp_path):
    r = Rig(tmp_path, build=lambda x: None, with_ladders=False)
    sent = []

    class N:
        kayit = T.TS.Kayit(tmp_path / "k.json", r.clk)

        def send_text(self, text, sev, key, **k):
            sent.append((sev, text))
            return True
    r.status_path.write_text(json.dumps({"dayaniklilik": {"sembol": [
        {"cift": "ETH/USDT", "alert": "CRIT", "open": True}]}}))
    assert T.dayaniklilik_tick(r.cfg, N(), T0) == 1
    assert T.dayaniklilik_tick(r.cfg, N(), T0) == 0              # ayni durum tekrar bildirilmez
    r.status_path.write_text(json.dumps({"dayaniklilik": {"sembol": []}}))
    assert T.dayaniklilik_tick(r.cfg, N(), T0) == 1 and [s for s, _ in sent][1:] == ["INFO"]


def test_symbol_watcher_background_does_not_block_loop():
    import threading
    gate = threading.Event()

    def slow():
        gate.wait(5)
        return _info(BTCUSDT="BREAK")
    w = SembolIzleyici(["BTC/USDT"], slow, arka_plan=True)
    assert w.check(T0) is False and w._thread is not None      # istek ayri iplikte; dongu beklemez
    assert w.check(T0 + timedelta(seconds=1)) is False and not w.blocked
    gate.set()
    w._thread.join(5)
    assert w.check(T0 + timedelta(seconds=2)) is True and w.is_blocked("BTC/USDT")
