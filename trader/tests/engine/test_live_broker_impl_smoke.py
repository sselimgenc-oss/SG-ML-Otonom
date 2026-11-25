"""WP-B3 gerceklestirme duman testleri: LiveBroker + gercek SignedRestClient + sahte borsa (fake_exchange, HTTP duzeyi)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fake_exchange import KEY, SECRET, FakeExchange, FakeResp
from trader_engine.brokers.binance_futures import LiveBroker
from trader_engine.clock import SimClock
from trader_engine.config import LiveSettings
from trader_engine.errors import BrokerUncertain, EngineExit
from trader_engine.exchange.binance_rest import SignedRestClient
from trader_engine.order_manager import make_client_id
from trader_engine.types import OrderRequest

UTC = timezone.utc
T0 = datetime(2026, 12, 28, 9, 0, tzinfo=UTC)
XRP = "XRP/USDT"


DOGE = "DOGE/USDT"


def build(mode="algo", env="testnet", pre=None, startup=True, ex=None, clock=None, environ=None, **fake_kw):
    """pre(ex): baslatmadan once sahte borsa durumunu hazirla. ex/clock verilirse ayni borsada "yeniden baslatma"."""
    clock = clock or SimClock(T0)
    if ex is None:
        ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000), classic=(mode == "classic"))
        for k, v in fake_kw.items():
            setattr(ex, k, v)
    rest = SignedRestClient(env=env, api_key=KEY, api_secret=SECRET, session=ex.session,
                            now_ms=lambda: int(clock.now().timestamp() * 1000), sleep=clock.sleep, conditional_mode=mode)
    live = LiveSettings(account_tag="sub-acct", expected_wallet_max=1000.0, conditional_mode=mode)
    b = LiveBroker(live, env, 3, [XRP, DOGE], rest, clock, 0.0005, environ=environ)
    if pre:
        pre(ex)
    if startup:
        b.startup_check()
    return b, ex, clock


def req(role, qty, trigger=None, side="long", seq=0, pair=XRP):
    cid = make_client_id("learner", role, pair, side, T0, seq)
    osd = "buy" if role == "entry" else "sell"
    return OrderRequest(client_id=cid, pair=pair, role=role, order_side=osd, qty=qty, trigger_price=trigger,
                        reduce_only=role != "entry", leverage=3 if role == "entry" else None, created_ts=T0)


@pytest.mark.parametrize("mode", ["algo", "classic"])
def test_entry_stop_trigger_closes_via_closing_events(mode):
    b, ex, clock = build(mode)
    assert ex.margin_type["XRPUSDT"] == "isolated" and ex.lev["XRPUSDT"] == 3
    b.prepare(XRP, 3)
    r = b.market_order(req("entry", 10.0))
    assert r.status == "filled" and r.avg_price == 2.0
    assert [e.kind for e in b.poll(clock.now())] == ["fill"]
    s = b.place_stop(req("stop", 10.0, 1.9))
    assert s.status == "accepted"
    assert [o.role for o in b.open_orders(XRP)] == ["stop"]
    clock.advance(10)
    ex.set_mark("XRPUSDT", "1.85")
    clock.advance(10)
    evs = b.poll(clock.now())
    fills = [e for e in evs if e.kind == "fill"]
    assert len(fills) == 1 and fills[0].fill.reason == "stop" and fills[0].fill.client_id == s.client_id
    assert fills[0].fill.qty == 10.0 and b.positions() == []
    assert b.poll(clock.now() + timedelta(seconds=60)) == []


def test_exit_market_funding_and_liquidation_and_foreign():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    b.poll(clock.now())
    ex.add_funding("XRPUSDT", "-0.02")
    r = b.market_order(req("exit", 10.0))
    assert r.status == "accepted"
    evs = b.poll(clock.now())
    assert [e.kind for e in evs] == ["funding", "fill"] and evs[0].funding_paid == pytest.approx(0.02)
    assert evs[1].fill.reason == "market"
    # likidasyon
    b.market_order(req("entry", 10.0, seq=1))
    ex.liquidate("XRPUSDT", "1.5")
    clock.advance(31)
    evs = b.poll(clock.now())
    assert [e.kind for e in evs] == ["fill", "liquidation"]
    # yabanci kapanis
    b.market_order(req("entry", 10.0, seq=2))
    ex.external_close("XRPUSDT")
    clock.advance(31)
    f = [e for e in b.poll(clock.now()) if e.kind == "fill" and e.fill.role != "entry"]
    assert len(f) == 1 and f[0].detail == "foreign_close"


def test_would_trigger_and_entry_min_notional_and_duplicate_mapping():
    b, ex, _ = build()
    b.market_order(req("entry", 10.0))
    assert b.place_stop(req("stop", 10.0, 2.5)).reason == "would_trigger"
    assert b.market_order(req("entry", 1.0, seq=3)).reason == "min_notional"      # yerel: 1 x 2.0 < 5
    assert b.place_stop(req("stop", 10.0, 1.9)).status == "accepted"
    assert b.place_stop(req("stop", 10.0, 1.9)).reason == "duplicate_client_id"


def test_cancel_query_foreign_and_uncertain_order_not_resent():
    b, ex, _ = build()
    b.market_order(req("entry", 10.0))
    s = b.place_stop(req("stop", 10.0, 1.9))
    assert b.query(XRP, s.client_id).status == "new"
    b.cancel(XRP, s.client_id)
    b.cancel(XRP, s.client_id)                       # yok: no-op
    assert b.query(XRP, s.client_id).status == "canceled"
    ex.inject("/fapi/v1/order", FakeResp(503, {"code": -1001, "msg": "x"}))
    with pytest.raises(BrokerUncertain):
        b.market_order(req("entry", 10.0, seq=5))
    assert ex.count("/fapi/v1/order", "POST") == 2     # ilk giris + belirsiz olan; yeniden gonderim yok


def test_live_startup_checks_permissions_and_testnet_skips():
    b, ex, _ = build(env="live")
    assert ex.count("apiRestrictions") == 1
    b2, ex2, _ = build(env="testnet")
    assert ex2.count("apiRestrictions") == 0


# ====================================================================================== mentor duzeltmeleri (WP-B3 inceleme)
def _held(ex, symbol="XRPUSDT", qty="10", side="BUY"):
    ex.fill_market(symbol, side, qty, cid="web_open")


def _poll_fills(b, clock, secs=10):
    clock.advance(secs)
    return [e for e in b.poll(clock.now()) if e.kind in ("fill", "liquidation")]


# -- 1: acilista cift basina ExchangeReject -> hazirlanmamis, acilis surer
def test_startup_pair_reject_with_open_position_continues_and_marks_unprepared(caplog):
    def pre(e):
        e.margin_type["XRPUSDT"] = "cross"
        _held(e)
    with caplog.at_level(logging.WARNING, logger="engine.live_broker"):
        b, ex, _ = build(pre=pre)
    assert ex.margin_type["XRPUSDT"] == "cross"                       # -4048 gercekten reddetti
    assert b.counters()["prepare_failed"] == 1
    assert any(r.levelno == logging.CRITICAL and "prepare_failed:XRP/USDT" in r.getMessage() for r in caplog.records)
    assert b.market_order(req("entry", 10.0)).reason == "not_prepared"
    assert b.market_order(req("entry", 100.0, pair=DOGE)).status == "filled"        # diger cift hazir


def test_startup_leverage_reject_4161_and_open_orders_4047_continue():
    def pre(e):
        _held(e)                                   # isolated zaten; kaldirac 20 -> 3 dusurme acik pozisyonla -4161
        e.lev["XRPUSDT"] = 20
    b, ex, _ = build(pre=pre)
    assert ex.lev["XRPUSDT"] == 20 and b.counters()["prepare_failed"] == 1
    b2, ex2, _ = build(pre=lambda e: (e.margin_type.__setitem__("DOGEUSDT", "cross"),
                                      e.orders.__setitem__("o1", {"clientOrderId": "o1", "symbol": "DOGEUSDT", "status": "NEW",
                                                                  "side": "BUY", "type": "LIMIT", "origQty": "1"})))
    assert ex2.margin_type["DOGEUSDT"] == "cross" and b2.counters()["prepare_failed"] == 1     # -4047


def test_startup_auth_and_resync_failure_still_exit():
    with pytest.raises(EngineExit) as ei:
        build(pre=lambda e: e.inject("/fapi/v1/leverage", FakeResp(401, {"code": -2015, "msg": "bad key"})))
    assert ei.value.code == 8
    with pytest.raises(EngineExit) as ei:                          # -1021 + basarisiz yeniden esitleme: ag sorunu, kod 5
        build(pre=lambda e: [e.inject("/fapi/v1/marginType", FakeResp(400, {"code": -1021, "msg": "x"})) for _ in range(3)] and
              e.inject("/fapi/v1/time", FakeResp(503, {"code": -1001, "msg": "x"})))
    assert ei.value.code == 5


# -- 2: exchangeInfo
def test_startup_exchange_info_down_exits_5():
    def pre(e):
        for _ in range(20):
            e.inject("/fapi/v1/exchangeInfo", FakeResp(503, {"code": -1001, "msg": "x"}))
    with pytest.raises(EngineExit) as ei:
        build(pre=pre)
    assert ei.value.code == 5 and "exchange_unreachable" in str(ei.value)


def test_startup_exchange_info_transient_failure_retries_and_starts():
    def pre(e):
        for _ in range(4):
            e.inject("/fapi/v1/exchangeInfo", FakeResp(503, {"code": -1001, "msg": "x"}))
    b, ex, _ = build(pre=pre)
    assert b.rules(XRP).step > 0 and ex.count("exchangeInfo") == 5


def test_reduce_only_exit_not_blocked_by_missing_rules_and_critical_logged(caplog):
    def pre(e):
        e.hide_rules.add("XRPUSDT")
        _held(e)
    with caplog.at_level(logging.WARNING, logger="engine.live_broker"):
        b, ex, clock = build(pre=pre)
    assert any(r.levelno == logging.CRITICAL and "rules_missing:XRP/USDT" in r.getMessage() for r in caplog.records)
    assert b.market_order(req("entry", 10.0, seq=3)).reason == "rules_missing"
    r = b.market_order(req("exit", 10.0))                              # kural yok ama cikis yerel engellenmez
    assert r.status == "accepted" and ex.count("/fapi/v1/order", "POST") == 1
    assert ex.pos["XRPUSDT"]["amt"] == 0


def test_missing_rules_with_position_stop_rejected_and_marked_dirty():
    b, ex, clock = build(pre=lambda e: (e.hide_rules.add("XRPUSDT"), _held(e)))
    assert b.place_stop(req("stop", 10.0, 1.9)).reason == "rules_missing"
    ex.hide_rules.clear()
    b.poll(clock.now())                                                # kirli bayrak: sonraki _sync kurallari yeniler
    assert b.place_stop(req("stop", 10.0, 1.9)).status == "accepted"


# -- 3 / 15: koruyucu emir yanit dogrulamasi
@pytest.mark.parametrize("st", ["REJECTED", "EXPIRED", "CANCELED"])
def test_stop_response_terminal_status_is_definite_reject(st):
    b, ex, _ = build()
    b.market_order(req("entry", 10.0))
    ex.inject("/fapi/v1/algoOrder", FakeResp(200, {"algoId": 5, "clientAlgoId": "x", "algoStatus": st, "reduceOnly": True}))
    r = b.place_stop(req("stop", 10.0, 1.9))
    assert r.status == "rejected" and r.reason == f"exchange_status:{st}"
    assert b.open_orders(XRP) == []


def test_stop_response_empty_body_queries_once_then_uncertain_or_accepts():
    b, ex, _ = build()
    b.market_order(req("entry", 10.0))
    ex.inject("/fapi/v1/algoOrder", FakeResp(200, {}))
    n0 = ex.count("/fapi/v1/algoOrder", "GET")
    with pytest.raises(BrokerUncertain):
        b.place_stop(req("stop", 10.0, 1.9, seq=1))
    assert ex.count("/fapi/v1/algoOrder", "GET") - n0 == 1
    # govde bos ama borsada emir var: tek sorgu NEW der -> kabul
    q = req("stop", 10.0, 1.9, seq=2)
    ex._new_cond("XRPUSDT", "SELL", "STOP_MARKET", Decimal("10"), Decimal("1.9"), "MARK_PRICE", q.client_id)
    ex.inject("/fapi/v1/algoOrder", FakeResp(200, {}))
    assert b.place_stop(q).status == "accepted"


@pytest.mark.parametrize("bad", [{"reduceOnly": False}, {"closePosition": True}, {"clientAlgoId": "someone-else"}])
def test_stop_response_echo_mismatch_rejected_and_cancelled(bad):
    b, ex, _ = build()
    b.market_order(req("entry", 10.0))
    r0 = req("stop", 10.0, 1.9)
    body = {"algoId": 5, "clientAlgoId": r0.client_id, "algoStatus": "NEW", "reduceOnly": True, "workingType": "MARK_PRICE"}
    body.update(bad)
    ex.inject("/fapi/v1/algoOrder", FakeResp(200, body))
    r = b.place_stop(r0)
    assert r.status == "rejected" and r.reason.startswith("response_mismatch:")
    assert ex.count("/fapi/v1/algoOrder", "DELETE") == 1 and b.counters()["stop_response_mismatch"] == 1


def test_stop_response_working_type_missing_requery_then_unverified_blocks_entries(caplog):
    b, ex, _ = build()
    b.market_order(req("entry", 10.0))
    base = {"algoId": 5, "clientAlgoId": None, "algoStatus": "NEW", "reduceOnly": True}
    # (a) sorgu workingType'i dolduruyor: kabul, engel yok
    r1 = req("stop", 10.0, 1.9, seq=1)
    ex._new_cond("XRPUSDT", "SELL", "STOP_MARKET", Decimal("10"), Decimal("1.9"), "MARK_PRICE", r1.client_id)
    ex.inject("/fapi/v1/algoOrder", FakeResp(200, dict(base, clientAlgoId=r1.client_id)))
    assert b.place_stop(r1).status == "accepted" and b.entries_blocked_reason is None
    # (b) sorgu da vermiyor: kabul + CRITICAL + sayac + yapiskan engel
    r2 = req("stop", 10.0, 1.9, seq=2)
    row = dict(base, clientAlgoId=r2.client_id)
    ex.inject("/fapi/v1/algoOrder", FakeResp(200, row))
    ex.inject("/fapi/v1/algoOrder", FakeResp(200, row))
    with caplog.at_level(logging.CRITICAL, logger="engine.live_broker"):
        assert b.place_stop(r2).status == "accepted"
    assert b.counters()["working_type_unverified"] == 1 and b.entries_blocked_reason == "working_type_unverified"
    assert any("workingType dogrulanamadi" in r.getMessage() for r in caplog.records)


# -- 6: yapiskan engel nedenleri
def test_block_reasons_are_sticky_and_not_overwritten():
    b, ex, clock = build()
    ex.inject("/fapi/v1/order", FakeResp(400, {"code": -9999, "msg": "x"}))
    assert b.market_order(req("entry", 10.0)).reason == "exchange_-9999"
    assert b.entries_blocked_reason == "exchange_unknown_code"
    for _ in range(3):
        for _ in range(4):
            ex.inject("positionRisk", FakeResp(503, {"code": -1001, "msg": "x"}))
        clock.advance(40)
        b.poll(clock.now())
    assert b.entries_blocked_reason == "exchange_unknown_code"
    assert set(b.entries_blocked_reasons) == {"exchange_unknown_code", "exchange_unreachable"}
    clock.advance(40)
    b.poll(clock.now())                                               # ilk basarili esitleme: yalniz unreachable kalkar
    assert b.entries_blocked_reasons == ("exchange_unknown_code",)


# -- 4: yeniden baslatma + tetikleme (cocuk emir otomatik kimlik)
@pytest.mark.parametrize("child", ["auto", "same"])
def test_restart_then_stop_trigger_attributed_to_stop_not_foreign(child):
    b, ex, clock = build(child_cid_mode=child)
    b.market_order(req("entry", 10.0))
    s = b.place_stop(req("stop", 10.0, 1.9))
    b2, _, _ = build(ex=ex, clock=clock)                              # bellek kaybi
    assert b2.open_orders(XRP)[0].client_id == s.client_id           # kimlik open_orders()'tan ogrenilir
    b2.poll(clock.now())
    clock.advance(10)
    ex.set_mark("XRPUSDT", "1.85")
    f = _poll_fills(b2, clock)
    assert len(f) == 1 and f[0].fill.reason == "stop" and f[0].fill.client_id == s.client_id and f[0].detail is None
    assert b2.counters()["foreign_close"] == 0


def test_restart_register_position_hints_attribute_stop_without_reading_open_orders():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    s = b.place_stop(req("stop", 10.0, 1.9))
    b2, _, _ = build(ex=ex, clock=clock)
    b2.register_position(XRP, T0, [s.client_id])
    b2.poll(clock.now())
    clock.advance(10)
    ex.set_mark("XRPUSDT", "1.85")
    f = _poll_fills(b2, clock)
    assert len(f) == 1 and f[0].fill.client_id == s.client_id and f[0].fill.reason == "stop"


def test_unregistered_position_seen_only_by_positions_read_is_not_tracked_for_closings():
    b, ex, clock = build()
    _held(ex)
    assert len(b.positions()) == 1                                    # saf okuma: izleme baslatmaz
    ex.external_close("XRPUSDT")
    assert _poll_fills(b, clock, 40) == []                            # kapanisi L3 (mutabakat) turetir
    b2, ex2, clock2 = build()
    _held(ex2)
    b2.register_position(XRP, T0 - timedelta(seconds=5), [])
    ex2.external_close("XRPUSDT")
    f = _poll_fills(b2, clock2, 40)
    assert len(f) == 1 and f[0].detail == "foreign_close"


# -- 5: emir kimligiyle arama / forceOrders
def test_order_by_id_non_2013_reject_is_retry_not_foreign_then_resolves():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    b2, _, _ = build(ex=ex, clock=clock)
    b2.poll(clock.now())
    ex.external_close("XRPUSDT")
    clock.advance(10)
    ex.inject("/fapi/v1/order", FakeResp(400, {"code": -1102, "msg": "param"}))
    assert [e for e in b2.poll(clock.now()) if e.fill] == []           # yabanci ilan edilmedi
    assert b2.counters()["foreign_close"] == 0
    clock.advance(10)
    f = [e for e in b2.poll(clock.now()) if e.fill]
    assert len(f) == 1 and f[0].detail == "foreign_close" and f[0].fill.client_id == "web_manual"


def test_liquidation_not_queryable_resolved_via_force_orders():
    b, ex, clock = build(liquidation_queryable=False)
    b.market_order(req("entry", 10.0))
    b.poll(clock.now())
    ex.liquidate("XRPUSDT", "1.5")
    clock.advance(31)
    evs = b.poll(clock.now())
    assert [e.kind for e in evs] == ["liquidation"] and b.counters()["foreign_close"] == 0
    assert ex.count("forceOrders") >= 1


def test_foreign_close_declared_only_after_force_orders_empty():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    b.poll(clock.now())
    ex.external_close("XRPUSDT")
    clock.advance(31)
    f = [e for e in b.poll(clock.now()) if e.fill]
    assert f[0].detail == "foreign_close" and ex.count("forceOrders") == 2         # LIQUIDATION + ADL


def test_rest_wrappers_query_order_by_id_and_force_orders():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    rest = b._rest
    oid = ex.orders[req("entry", 10.0).client_id]["orderId"]
    assert rest.query_order_by_id("XRPUSDT", oid)["clientOrderId"] == req("entry", 10.0).client_id
    assert rest.query_order_by_id("XRPUSDT", 999999) is None                       # yalniz -2013
    ex.inject("/fapi/v1/order", FakeResp(400, {"code": -1102, "msg": "x"}))
    from trader_engine.exchange.binance_rest import ExchangeReject
    with pytest.raises(ExchangeReject):
        rest.query_order_by_id("XRPUSDT", oid)
    ex.liquidate("XRPUSDT", "1.5")
    rows = rest.force_orders("XRPUSDT", 0)
    assert len(rows) == 1 and rows[0]["clientOrderId"] == "autoclose-1234" and rest.force_orders("XRPUSDT", 0, "ADL") == []
    with pytest.raises(ValueError):
        rest.force_orders("XRPUSDT", 0, "FOO")


# -- 13: araya giren azaltma
@pytest.mark.parametrize("restart", [False, True])
def test_interleaved_external_reduce_exit_covers_all_reducing_trades(restart):
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    s = b.place_stop(req("stop", 10.0, 1.9))
    b.poll(clock.now())
    ex.fill_market("XRPUSDT", "SELL", "4", cid="web_reduce")
    clock.advance(10)
    if restart:
        b, _, _ = build(ex=ex, clock=clock)
        b.register_position(XRP, T0, [s.client_id])
    assert [e for e in b.poll(clock.now()) if e.fill] == []            # pozisyon 6: kapanis degil
    clock.advance(10)
    ex.set_mark("XRPUSDT", "1.85")
    f = _poll_fills(b, clock)
    assert len(f) == 1 and f[0].fill.reason == "stop" and f[0].fill.qty == pytest.approx(10.0)


def test_multi_trade_market_exit_sums_all_rows():
    b, ex, clock = build(market_parts=3)
    assert b.market_order(req("entry", 10.0)).filled_qty == pytest.approx(10.0)
    b.poll(clock.now())
    assert len([t for t in ex.trades if t["symbol"] == "XRPUSDT"]) == 3
    b.market_order(req("exit", 10.0))
    f = [e for e in b.poll(clock.now()) if e.kind == "fill" and e.fill.role == "exit"]
    assert len(f) == 1 and f[0].fill.qty == pytest.approx(10.0) and f[0].fill.reason == "market"


# -- 7: koruyucu yolda satir ici exchangeInfo yok
def test_filter_reject_on_stop_path_defers_rules_refresh_to_next_sync():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    ex.inject("/fapi/v1/algoOrder", FakeResp(400, {"code": -4003, "msg": "x"}))
    n0 = ex.count("exchangeInfo")
    assert b.place_stop(req("stop", 10.0, 1.9)).reason == "filter:-4003"
    assert ex.count("exchangeInfo") == n0
    clock.advance(10)
    b.poll(clock.now())
    assert ex.count("exchangeInfo") == n0 + 1


# -- 8 / 14
def test_startup_418_sleeps_retry_after_clamped_then_exits_5(caplog):
    clock = SimClock(T0)
    t0 = clock.now()
    with caplog.at_level(logging.CRITICAL, logger="engine.live_broker"):
        with pytest.raises(EngineExit) as ei:
            build(clock=clock, pre=lambda e: e.inject("/fapi/v1/time", FakeResp(418, {"code": -1003, "msg": "ban"},
                                                                                  {"Retry-After": "600"})))
    assert ei.value.code == 5 and (clock.now() - t0).total_seconds() == 300.0
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)


@pytest.mark.parametrize("bad", [{}, {"totalWalletBalance": "nan"}, {"totalWalletBalance": None}])
def test_live_wallet_unreadable_exits_8(bad):
    def pre(e):
        e.inject("/fapi/v2/account", FakeResp(200, dict({"canTrade": True}, **bad)))
    with pytest.raises(EngineExit) as ei:
        build(env="live", pre=pre)
    assert ei.value.code == 8 and "wallet_unreadable" in str(ei.value)


# -- 9: budama
def test_state_pruned_after_close_and_cancel():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    prev = None
    for i in range(12):
        s = b.place_stop(req("stop", 10.0, 1.5 + i * 0.01, seq=i))
        if prev:
            b.cancel(XRP, prev)
        prev = s.client_id
    assert len(b._stops) == 1 and len(b._cancelled[XRP]) == 3
    ex.external_close("XRPUSDT")
    clock.advance(10)
    b.poll(clock.now())
    assert not b._stops and not b._order_ids and not b._exit_cids and not b._cancelled and not b._pending_close
    assert len(b._delivered) >= 1


# -- 10: query attempts=1
def test_query_market_order_uses_single_attempt():
    b, ex, _ = build()
    r = req("entry", 10.0)
    b.market_order(r)
    n0 = ex.count("/fapi/v1/order", "GET")
    for _ in range(4):
        ex.inject("/fapi/v1/order", FakeResp(503, {"code": -1001, "msg": "x"}))
    with pytest.raises(BrokerUncertain):
        b.query(XRP, r.client_id)
    assert ex.count("/fapi/v1/order", "GET") - n0 == 1


# -- 11: cozulmemis kapanis kisitlamasi
def test_unresolved_close_is_throttled_and_raises_finding_after_60s():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    b.poll(clock.now())
    ex.external_close("XRPUSDT")
    ex.trades.pop()                                                   # islem satiri hic gorunmez
    clock.advance(10)
    b.poll(clock.now())
    n0 = ex.count("userTrades")
    for _ in range(30):
        clock.advance(1)
        b.poll(clock.now())
    assert ex.count("userTrades") - n0 <= 10                           # 30 turda 30 degil
    assert f"close_unresolved:{XRP}" not in b.findings
    clock.advance(60)
    b.poll(clock.now())
    assert f"close_unresolved:{XRP}" in b.findings and b.counters()["close_unresolved"] == 1


# -- 12: pozisyon kaydi / fonlama penceresi
def test_register_position_sets_funding_window_start():
    b, ex, clock = build()
    _held(ex)
    ex.add_funding("XRPUSDT", "-0.5", time_ms=int((T0 - timedelta(hours=8)).timestamp() * 1000))       # acilistan once: dahil degil
    ex.add_funding("XRPUSDT", "-0.02")
    b.register_position(XRP, T0 - timedelta(minutes=1), [])
    ex.external_close("XRPUSDT")
    clock.advance(10)
    evs = b.poll(clock.now())
    fund = [e.funding_paid for e in evs if e.kind == "funding"]
    assert fund == [pytest.approx(0.02)]


# -- 16 / 17
def test_query_triggered_algo_without_fill_reports_zero_filled_qty():
    b, ex, _ = build()
    b.market_order(req("entry", 10.0))
    s = b.place_stop(req("stop", 10.0, 1.9))
    ex.external_close("XRPUSDT")
    ex.set_mark("XRPUSDT", "1.8")
    o = b.query(XRP, s.client_id)
    assert o.status == "filled" and o.filled_qty == 0.0


def test_pending_new_entry_queried_every_poll_and_missing_order_dropped_with_finding():
    b, ex, clock = build()
    r = req("entry", 10.0)
    ex.orders[r.client_id] = {"clientOrderId": r.client_id, "symbol": "XRPUSDT", "side": "BUY", "type": "MARKET",
                              "reduceOnly": False, "origQty": "10", "time": 1, "orderId": 4242, "status": "NEW",
                              "executedQty": "0", "avgPrice": "0", "updateTime": 1}
    ex.inject("/fapi/v1/order", FakeResp(200, dict(ex.orders[r.client_id])))
    assert b.market_order(r).status == "accepted" and r.client_id in b._pending_market
    n0 = ex.count("/fapi/v1/order", "GET")
    for _ in range(3):
        clock.advance(1)                                               # poll_open_s icinde
        b.poll(clock.now())
    assert ex.count("/fapi/v1/order", "GET") - n0 == 3
    del ex.orders[r.client_id]
    clock.advance(1)
    b.poll(clock.now())
    assert r.client_id in b._pending_market and not b.findings         # tek -2013 dusurmez
    for _ in range(12):
        clock.advance(1)
        evs = b.poll(clock.now())
        if r.client_id not in b._pending_market:
            break
    assert r.client_id not in b._pending_market and f"pending_order_not_found:{r.client_id}" in b.findings
    assert [e.detail for e in evs if e.kind == "order_rejected"] == ["pending_not_found"]


def test_pending_not_found_streak_resets_when_order_reappears():
    b, ex, clock = build()
    r = req("entry", 10.0)
    row = {"clientOrderId": r.client_id, "symbol": "XRPUSDT", "side": "BUY", "type": "MARKET", "reduceOnly": False,
           "origQty": "10", "time": 1, "orderId": 4243, "status": "NEW", "executedQty": "0", "avgPrice": "0", "updateTime": 1}
    ex.orders[r.client_id] = dict(row)
    ex.inject("/fapi/v1/order", FakeResp(200, dict(row)))
    assert b.market_order(r).status == "accepted"
    del ex.orders[r.client_id]
    for _ in range(5):
        clock.advance(1)
        b.poll(clock.now())
    ex.orders[r.client_id] = dict(row)
    clock.advance(1)
    b.poll(clock.now())
    assert b._pending_nf == {} or r.client_id not in b._pending_nf
    del ex.orders[r.client_id]
    for _ in range(5):
        clock.advance(1)
        b.poll(clock.now())
    assert r.client_id in b._pending_market and not b.findings


def test_candidate_query_reject_skips_candidate_and_force_orders_reject_proceeds_with_finding():
    b, ex, clock = build()
    s_entry = b.market_order(req("entry", 10.0))
    b.poll(clock.now())
    stop_cid = req("stop", 10.0, 1.9).client_id
    b.register_position(XRP, clock.now(), [stop_cid])                              # aday: sorgulanamayan stop kimligi
    ex.external_close("XRPUSDT")
    clock.advance(31)
    ex.inject("/fapi/v1/algoOrder", FakeResp(400, {"code": -1102, "msg": "param"}))    # aday sorgusu (kesin ret)
    ex.inject("/fapi/v1/forceOrders", FakeResp(400, {"code": -4000, "msg": "bad"}))
    ex.inject("/fapi/v1/forceOrders", FakeResp(400, {"code": -4000, "msg": "bad"}))
    f = [e for e in b.poll(clock.now()) if e.fill]
    assert len(f) == 1 and f[0].detail == "foreign_close"
    assert any(x.startswith("force_orders_rejected:") for x in b.findings)
    assert ex.count("algoOrder") >= 1
    assert s_entry.status == "filled"


def test_force_orders_start_time_clamped_to_last_7_days():
    pos = T0 - timedelta(days=30)
    b, ex, clock = build()
    seen = []
    orig = b._rest.force_orders
    b._rest.force_orders = lambda sym, start, *a, **k: (seen.append(start), orig(sym, start, *a, **k))[1]
    b.market_order(req("entry", 10.0))
    b.poll(clock.now())
    b._pos_since[XRP] = pos
    ex.external_close("XRPUSDT")
    clock.advance(31)
    b._pending_close[XRP] = pos
    b.poll(clock.now())
    floor = int((clock.now() - timedelta(days=7)).timestamp() * 1000)
    assert seen and all(s >= floor for s in seen)


def test_margin_types_from_last_position_risk_read():
    b, ex, clock = build()
    assert b.margin_types() == {}
    b.positions()
    assert b.margin_types() == {XRP: "isolated", DOGE: "isolated"}
    ex.margin_type["XRPUSDT"] = "cross"
    b.positions()
    assert b.margin_types()[XRP] == "cross"


def test_entry_fill_pos_since_has_margin_on_immediate_fill():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    assert b._pos_since[XRP] == T0 - timedelta(seconds=2)


# -- 18
def test_order_post_auth_error_is_rejected_exchange_auth_and_blocks_entries():
    b, ex, _ = build()
    ex.inject("/fapi/v1/order", FakeResp(401, {"code": -2015, "msg": "bad key"}))
    r = b.market_order(req("entry", 10.0))
    assert r.status == "rejected" and r.reason == "exchange_auth" and b.entries_blocked_reason == "exchange_auth"


def test_sync_runtime_auth_error_exposes_exchange_auth_not_unreachable():
    b, ex, clock = build()
    for _ in range(4):
        ex.inject("positionRisk", FakeResp(401, {"code": -2015, "msg": "bad key"}))
    clock.advance(40)
    b.poll(clock.now())
    assert b.entries_blocked_reason == "exchange_auth" and "exchange_unreachable" not in b.entries_blocked_reasons
    assert b.counters()["exchange_auth"] == 1 and b.health()["reachable"] is True


def test_ban_counted_once_and_reachable_false_during_window():
    b, ex, clock = build()
    ex.inject("positionRisk", FakeResp(418, {"code": -1003, "msg": "ban"}, {"Retry-After": "120"}))
    for _ in range(5):
        clock.advance(10)
        b.poll(clock.now())
    assert b.counters()["exchange_bans"] == 1 and b.health()["reachable"] is False and b.last_ban == (418, pytest.approx(120, abs=60))
    clock.advance(200)
    b.poll(clock.now())
    assert b.health()["reachable"] is True


def test_funding_dedup_key_includes_symbol_for_equal_tran_ids():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    b.market_order(req("entry", 100.0, pair=DOGE))
    b.poll(clock.now())
    for sym in ("XRPUSDT", "DOGEUSDT"):
        ex.incomes.append({"symbol": sym, "incomeType": "FUNDING_FEE", "income": "-0.1", "asset": "USDT",
                           "time": ex.now_ms(), "tranId": 5})
    ex.external_close("XRPUSDT")
    ex.external_close("DOGEUSDT")
    clock.advance(40)
    evs = b.poll(clock.now())
    assert [e.pair for e in evs if e.kind == "funding"].count(XRP) == 1 and [e.pair for e in evs if e.kind == "funding"].count(DOGE) == 1


def test_malformed_trade_rows_return_empty_and_retry_later():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    b.poll(clock.now())
    ex.external_close("XRPUSDT")
    good = dict(ex.trades[-1])
    ex.trades[-1].pop("id")
    clock.advance(10)
    assert [e for e in b.poll(clock.now()) if e.fill] == [] and b.counters()["malformed_trades"] >= 1
    ex.trades[-1].update(good)
    clock.advance(10)
    assert len([e for e in b.poll(clock.now()) if e.fill]) == 1


def test_foreign_open_orders_includes_our_prefix_with_unknown_role_letter():
    b, ex, _ = build()
    for cid in ("trLz-unknown-role", "webx-1"):
        ex.orders[cid] = {"clientOrderId": cid, "symbol": "XRPUSDT", "status": "NEW", "side": "BUY", "type": "LIMIT",
                          "origQty": "1", "time": 1, "updateTime": 1}
    assert sorted(r["clientOrderId"] for r in b.foreign_open_orders()) == ["trLz-unknown-role", "webx-1"]
    assert b.open_orders(XRP) == []


def test_live_permission_attestation_no_longer_bypasses():
    """DD-8 O6 ile degisti (eski: beyan okunamayan yaniti geciyordu): beyan sonucu HIC etkilemez; okunamayan yanit beyanla da
    reddedilir (5xx -> ag sorunu, cikis 5)."""
    bad = lambda e: setattr(e, "restrictions_status", 500)           # noqa: E731
    for environ in ({}, {"LIVE_PERMISSION_ATTESTED": "2026-12-20"}):
        with pytest.raises(EngineExit) as ei:
            build(env="live", pre=bad, environ=environ)
        assert ei.value.code == 5


def test_entry_fill_position_since_has_margin_when_seen_by_sync_after_restart():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    b2, _, _ = build(ex=ex, clock=clock)
    b2.poll(clock.now())
    assert b2._pos_since[XRP] <= T0 - timedelta(seconds=1)


# ====================================================================================== sahte borsa anahtarlari
def test_fake_reduce_only_reject_vs_clip():
    b, ex, clock = build()
    b.market_order(req("entry", 10.0))
    assert b.market_order(req("exit", 12.0)).reason == "reduce_only_exceeds"
    assert ex.pos["XRPUSDT"]["amt"] == 10
    b2, ex2, clock2 = build(reduce_only_mode="clip")
    b2.market_order(req("entry", 10.0))
    b2.market_order(req("exit", 12.0))
    assert ex2.pos["XRPUSDT"]["amt"] == 0
    f = [e for e in b2.poll(clock2.now()) if e.kind == "fill" and e.fill.role == "exit"]
    assert len(f) == 1 and f[0].fill.qty == pytest.approx(10.0)


@pytest.mark.parametrize("mode,remains", [("keep", 1), ("expire", 0)])
def test_fake_resting_stop_after_close_keep_or_expire(mode, remains):
    b, ex, clock = build(stop_after_close=mode)
    b.market_order(req("entry", 10.0))
    b.place_stop(req("stop", 10.0, 1.9))
    ex.external_close("XRPUSDT")
    assert len(b.open_orders(XRP)) == remains


def test_fake_immediate_trigger_accept_then_trigger_yields_stop_event():
    b, ex, clock = build(immediate_trigger="accept_then_trigger")
    b.market_order(req("entry", 10.0))
    r = b.place_stop(req("stop", 10.0, 2.5))                           # isaret: mark 2.0 < 2.5 -> hemen tetiklenir
    assert r.status == "accepted" and ex.pos["XRPUSDT"]["amt"] == 0
    clock.advance(10)
    f = [e for e in b.poll(clock.now()) if e.kind == "fill" and e.fill.role != "entry"]
    assert len(f) == 1 and f[0].fill.reason == "stop" and f[0].fill.client_id == r.client_id


def test_fake_non_reduce_only_stop_opens_reverse_position():
    b, ex, _ = build()
    b.market_order(req("entry", 10.0))
    ex._new_cond("XRPUSDT", "SELL", "STOP_MARKET", Decimal("25"), Decimal("1.9"), "MARK_PRICE", "plain-stop", reduce=False)
    ex.set_mark("XRPUSDT", "1.85")
    assert ex.pos["XRPUSDT"]["amt"] == Decimal("-15")                    # reduceOnly olsaydi 10'a kirpilirdi


# -- 25.11 denetim #29: marjin/kaldirac dogrulamasinda her satir sayilir (son satir ezmez)
def test_prepare_her_satir_dogrulanir_ilk_satir_bozuksa_hazirlanmaz():
    b, ex, _ = build(startup=False)
    gercek = b._rest.position_risk

    def iki_satir(*a, **k):
        rows = list(gercek(*a, **k) or [])
        bozuk = [{**r, "marginType": "cross"} for r in rows if r.get("symbol") == "XRPUSDT"]
        return bozuk + rows                                    # bozuk satir ONDE, saglam satir SONDA
    b._rest.position_risk = iki_satir                          # type: ignore[method-assign]
    b.startup_check()
    assert XRP not in b._prepared and DOGE in b._prepared
    assert b.counters()["prepare_failed"] == 1


# -- 25.11 denetim #30: teslim kayitlari sinirli kalir, en eski atilir
def test_teslim_kayitlari_sinirli():
    from trader_engine.brokers import binance_futures as BF
    d = {i: None for i in range(BF.DELIVERED_MAX + 10)}
    LiveBroker._prune(d)
    assert len(d) == BF.DELIVERED_MAX and 0 not in d and BF.DELIVERED_MAX + 9 in d
