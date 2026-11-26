"""Alarm turu basina baglam testi (kurulum sonrasi kararlilik plani, madde 4).

Her kirmizi (CRIT) alarm turu icin: (a) GERCEK kosulda ust uste 2 saglik turunda tam bir kirmizi uyari gider ve ilk turda
gitmez (cift dogrulama; yalniz RED_SINGLE_OK canli-para kodlari ilk turda gider), (b) ZARARSIZ (benign) benzer kosulda hic
uyari gitmez. Ayrica kurulum sonrasi sessizlik: FATAL kodlar gecer, digerleri tutulur."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from trader_core import health as H
from trader_core.health import Status

UTC = timezone.utc
NOW = datetime(2026, 11, 20, 12, 30, 0, tzinfo=UTC)
T = 3600
GIB = 1 << 30
MIB = 1 << 20
BOT = "learner"


def _api(**kw):
    base = dict(ping_ok=True, last_process_at=NOW - timedelta(seconds=30),
                last_candle_open=NOW.replace(minute=0, second=0), open_trade_ids=(), dry_run=True)
    base.update(kw)
    return H.ApiProbe(**base)


def _ledger(**kw):
    base = dict(last_write_at=NOW - timedelta(minutes=30), spool_lines=0, unledgered_ids=(), 
                schema_ok=True, has_active_params=True, spool_corrupt_lines=0)
    base.update(kw)
    return H.LedgerProbe(**base)


def _container(**kw):
    base = dict(state="running", restart_count=4, started_at=NOW - timedelta(days=2), oom_killed=False)
    base.update(kw)
    return H.ContainerProbe(**base)


def _snap(api=None, ledger=None, container=None, **over):
    base = dict(now=NOW, timeframe_s=T, api={BOT: api or _api()}, ledger={BOT: ledger or _ledger()},
                disk_free_bytes=20 * GIB, disk_total_bytes=100 * GIB, 
                
                containers={f"trader-{BOT}": container or _container()}, prev_restart_counts={f"trader-{BOT}": 4},
                last_backup_at=NOW - timedelta(hours=3))
    base.update(over)
    return H.HealthSnapshot(**base)


def _market(**kw):
    base = dict(feed_status_state="ok", feed_status_at=NOW - timedelta(seconds=30), db_state="ok", pairs=("BTC/USDT",),
                newest_bar_at={"BTC/USDT": NOW - timedelta(seconds=30)}, rules_count=10,
                rules_fetched_at=NOW - timedelta(hours=1), rules_missing={BOT: 0})
    base.update(kw)
    return H.MarketProbe(**base)


_SCFG = dataclasses.replace(H.DEFAULT_CFG, multiple_threshold=50)
_CFG = dataclasses.replace(H.DEFAULT_CFG, multiple_threshold=50)

# (kod, gercek kosul, zararsiz benzer kosul, cfg)
CASES = {
    "stale_loop": (dict(api=_api(last_process_at=NOW - timedelta(minutes=20))),
                   dict(api=_api(last_process_at=NOW - timedelta(seconds=90))), _CFG),       # 90 sn: yalniz esik alti
    "stale_candle": (dict(api=_api(last_candle_open=NOW - timedelta(seconds=11000))),
                     dict(api=_api(last_candle_open=NOW - timedelta(minutes=70))), _CFG),     # 1 saatlik mum: 70 dk normal
    "ledger_write_stale": (dict(ledger=_ledger(last_write_at=NOW - timedelta(hours=3))),
                           dict(ledger=_ledger(last_write_at=NOW - timedelta(minutes=50))), _CFG),
    "spool_pending": (dict(ledger=_ledger(spool_lines=3)), dict(ledger=_ledger(spool_lines=0)), _CFG),
    "unledgered_trades": (dict(ledger=_ledger(unledgered_ids=(9,))), dict(ledger=_ledger(unledgered_ids=())), _CFG),
    "no_active_params": (dict(ledger=_ledger(has_active_params=False)), dict(ledger=_ledger(has_active_params=True)), _CFG),
    "schema": (dict(ledger=_ledger(schema_ok=False)), dict(ledger=_ledger(schema_ok=True)), _CFG),
    "spool_corrupt": (dict(ledger=_ledger(spool_corrupt_lines=3)), dict(ledger=_ledger(spool_corrupt_lines=0)), _CFG),
    "engine_gate_closed": (dict(api=_api(gate_code="ledger_down")), dict(api=_api(gate_code="ok")), _CFG),
    "disk_low": (dict(disk_free_bytes=int(0.5 * GIB)), dict(disk_free_bytes=int(5 * GIB)), _CFG),   # 5 GiB: uyari bandi bile degil
    "oom_killed": (dict(container=_container(oom_killed=True)), dict(container=_container(oom_killed=False)), _CFG),
    "container_not_running": (dict(container=_container(state="exited")), dict(container=_container(state="running")), _CFG),
    "restart_loop": (dict(container=_container(restart_count=9)), dict(container=_container(restart_count=4)), _CFG),
    "backup_stale": (dict(last_backup_at=NOW - timedelta(hours=60)), dict(last_backup_at=NOW - timedelta(hours=20)), _CFG),
    "market_bars_stale": (dict(market=_market(newest_bar_at={"BTC/USDT": NOW - timedelta(minutes=30)})),
                          dict(market=_market(newest_bar_at={"BTC/USDT": NOW - timedelta(seconds=200)})), _CFG),
    "market_db_missing": (dict(market=_market(db_state="missing")), dict(market=_market()), _CFG),
}


def _red_codes(snap, cfg, turns):
    """Ust uste `turns` tur; son turun gonderilen KIRMIZI uyari kodlari (ilk turlarin kodlari ayri)."""
    state, per_turn = {}, []
    for i in range(turns):
        now = NOW + timedelta(minutes=5 * i)
        rep = H.evaluate(snap, cfg)
        alerts, state = H.plan_alerts(rep, state, now, cfg)
        per_turn.append([a.code for a in alerts if a.level in (Status.CRIT, Status.UNKNOWN)])
    return per_turn


@pytest.mark.parametrize("code", sorted(CASES))
def test_alarm_gercek_kosulda_2_turda_gider_zararsizda_gitmez(code):
    real, benign, cfg = CASES[code]
    per_turn = _red_codes(_snap(**real), cfg, 3)
    assert code not in per_turn[0], f"{code}: ilk turda kirmizi gitmemeli (cift dogrulama)"
    assert code in per_turn[1], f"{code}: ust uste 2. turda kirmizi uyari gitmeli ({per_turn})"
    assert per_turn[2].count(code) == 0                      # ayni sorun tekrar tekrar mesaj uretmez
    assert all(not t for t in _red_codes(_snap(**benign), cfg, 3)), f"{code}: zararsiz kosulda uyari gitmemeli"


def test_gercek_kosul_kirmizi_rapor_zararsiz_kosul_saglikli_rapor():
    for code, (real, benign, cfg) in CASES.items():
        rep = H.evaluate(_snap(**real), cfg)
        assert any(r.code == code and r.status in (Status.CRIT, Status.UNKNOWN) for r in rep.results), code
        okrep = H.evaluate(_snap(**benign), cfg)
        assert not any(r.code == code for r in okrep.results), code


def test_canli_para_kodlari_ilk_turda_gider_ve_kagit_modda_uretilmez():
    assert H.RED_SINGLE_OK == {"naked_position", "exchange_ban_open_positions", "account_mode_drift", "live_paths_mismatch"}
    # kagit mod (canli degil): stopsuz pozisyon denetimi hic uretilmez
    rep = H.evaluate(_snap(), _CFG)
    assert not any(r.code in H.RED_SINGLE_OK for r in rep.results)


def test_tek_basarisiz_olcum_sonra_duzelme_hic_mesaj_uretmez():
    real, benign, cfg = CASES["stale_loop"]
    state = {}
    for i, s in enumerate((_snap(**real), _snap(**benign), _snap(**real), _snap(**benign))):
        now = NOW + timedelta(minutes=5 * i)
        alerts, state = H.plan_alerts(H.evaluate(s, cfg), state, now, cfg)
        assert alerts == []                                   # kirmizi, ardisik olmadigi icin sari kalir; "duzeldi" de gitmez


# ----------------------------------------------------------------------------- kurulum sonrasi sessizlik
def _rep_with(*codes):
    rs = tuple(H.CheckResult(f"{c}:learner", Status.CRIT, c, "x") for c in codes)
    return H.HealthReport(NOW, rs, Status.CRIT, False)


def _alerts(*pairs):
    return [H.Alert(lvl, code, f"t-{code}", "b", f"{code}|{code}", NOW) for lvl, code in pairs]


def test_sessizlik_penceresinde_yalniz_olumcul_gider():
    until = NOW + timedelta(minutes=10)
    al = _alerts((Status.CRIT, "stale_loop"), (Status.CRIT, "stale_candle"), (Status.WARN, "backup_stale"),
                 (Status.OK, "stale_loop"))
    send, held = H.quiet_split(al, _rep_with("stale_loop", "stale_candle"), NOW, until)
    assert [(a.code, a.level) for a in send] == [("stale_loop", Status.CRIT)]
    assert {(a.code, a.level) for a in held} == {("stale_candle", Status.CRIT), ("backup_stale", Status.WARN),
                                                  ("stale_loop", Status.OK)}
    # pencere bitti ya da yok: hepsi gider
    assert H.quiet_split(al, _rep_with("stale_candle"), NOW, NOW - timedelta(seconds=1)) == (al, [])
    assert H.quiet_split(al, _rep_with("stale_candle"), NOW, None) == (al, [])


def test_sessizlikte_multiple_yalniz_olumcul_varken_gider():
    m = _alerts((Status.CRIT, "multiple"))
    until = NOW + timedelta(minutes=5)
    assert H.quiet_split(m, _rep_with("stale_candle", "disk_low"), NOW, until)[0] == []
    assert H.quiet_split(m, _rep_with("stale_candle", "oom_killed"), NOW, until)[0] == m


def test_fatal_kodlari_gercek_kontrol_kodlari():
    import re
    src = open(H.__file__, encoding="utf-8").read()
    for code in H.FATAL_CODES:
        assert re.search(rf'Status\.CRIT, "{code}"|add\(Status\.CRIT, "{code}"|_graded\([^\n]*"{code}"', src), code
    assert H.QUIET_MINUTES == 15 and H.RED_CONFIRM_RUNS == 2
