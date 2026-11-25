"""Hazirlik 5: ariza tatbikatlari (sahte Binance REST + tmp 'sunucu' agaci; ag/systemd yok).
Her senaryo GORUNUR bir alarm (cikis kodu + CRITICAL log + birim `failed` -> OnFailure) ya da BELGELI 'giris kapali' durumu uretmeli;
asla sessizlik. Birim anlambilimi (RestartPreventExitStatus, OnFailure) test_readiness_units_render.py'de dogrulanir."""
from __future__ import annotations

import json
import os
import logging
import shutil
import sqlite3
import subprocess
import sys
from datetime import timedelta

import pytest

from readiness_support import FakeBinance, NOW0, ROOT, Resp, to_ms, write_config

from trader_engine.clock import SimClock
from trader_engine.config import load_engine_config
from trader_engine.engine import EXIT_STARTUP_GATE, EngineExit, build_engine
from trader_engine.marketdata import feed as F
from trader_engine.marketdata.feed import Feed, RulesFetchError, feed_config_from_base
from trader_engine.marketdata.rest_public import PublicRestClient
from trader_engine.marketdata.store import MarketStore

REAL_STARTUP_GATE = True       # tests/conftest.py: bu modulde acilis kapisi gercekten calisir
PAIRS10 = json.loads((ROOT / "config/engine.base.json").read_text())["pairs"]
SMALL = {"1m": 400, "15m": 100, "1h": 100, "4h": 100}      # backfill kucuk (hizli); kapi yalniz 1m last+mark ve kurallara bakar


def _rest(sess, clock):
    return PublicRestClient(session=sess, now_s=lambda: clock.now().timestamp(), sleep=clock.sleep, max_attempts=2)


def _feed(tmp_path, clock, sess, cfg_dir):
    import dataclasses
    fc = dataclasses.replace(feed_config_from_base(str(cfg_dir)), backfill_bars=SMALL)
    store = MarketStore(fc.db_path)
    return Feed(fc, _rest(sess, clock), store, clock), store


def _engine(cfg_dir, clock, bot="learner"):
    d = cfg_dir
    cfg = load_engine_config(d / "engine.base.json", d / f"engine.{bot}.json")
    return build_engine(cfg, clock=clock, env={})


# ------------------------------------------------------------------ 5.1 ag yok / 451
def test_drill_feed_451_exits_6_with_critical_message(tmp_path, caplog):
    cfgd = write_config(tmp_path)
    clock = SimClock(NOW0)
    sess = FakeBinance(clock, PAIRS10, "451")
    with caplog.at_level(logging.CRITICAL):
        rc = F.main(["--config-dir", str(cfgd)], rest=_rest(sess, clock), clock=clock, max_ticks=1)
    assert rc == F.EXIT_GEOBLOCK == 6                               # birim: RestartPreventExitStatus=6 -> 'failed' -> OnFailure
    assert any(r.levelno == logging.CRITICAL and "451" in r.getMessage() for r in caplog.records)


def test_drill_feed_no_network_fails_loudly_not_silently(tmp_path, caplog):
    """Ag yok (baglanti hatasi): main() ExchangeError'i yakalar, tek critical satir yazar, cikis 5 (451 -> 6 kalir; OPEN-7 kapandi).
    Sessizlik YOK, kural yazilmaz."""
    cfgd = write_config(tmp_path)
    clock = SimClock(NOW0)
    sess = FakeBinance(clock, PAIRS10, "down")
    with caplog.at_level(logging.WARNING):
        rc = F.main(["--config-dir", str(cfgd)], rest=_rest(sess, clock), clock=clock, max_ticks=1)
    assert rc == F.EXIT_RULES == 5
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)
    assert (clock.now() - NOW0).total_seconds() < 300               # sonsuz bekleme yok
    assert any("ağ hatası" in r.getMessage() for r in caplog.records)
    st = MarketStore(tmp_path / "var" / "market.sqlite", read_only=True)
    assert st.get_rules(PAIRS10[0]) is None                         # kural yazilmadi -> motor kapisi acilmaz (10/10 ya da hicbiri)


def test_drill_feed_exchangeinfo_5xx_exits_5(tmp_path, caplog):
    cfgd = write_config(tmp_path)
    clock = SimClock(NOW0)
    sess = FakeBinance(clock, PAIRS10, "ok")
    orig = sess.get

    def get(url, params=None, timeout=None):
        if url.endswith("/fapi/v1/exchangeInfo"):
            return Resp(500, None, "boom")
        return orig(url, params, timeout)
    sess.get = get
    with caplog.at_level(logging.WARNING):
        rc = F.main(["--config-dir", str(cfgd)], rest=_rest(sess, clock), clock=clock, max_ticks=1)
    assert rc == F.EXIT_RULES == 5
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)


# ------------------------------------------------------------------ 5.0 ilk baslatma provasi (runbook adimlari)
class _Sender:
    def __init__(self):
        self.calls = []

    def ok(self, rep):
        self.calls.append("ok")
        return True

    def fail(self, rep):
        self.calls.append("fail")
        return True


def _health_mod(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "health_run.py")
    hr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hr)
    return hr


def _bring_up(tmp_path, bots=("learner",)):
    """Bos sunucu -> feed (kurallar+backfill) -> init-ledger -> motor kapisi -> status.json. Doner: (cfgd, clock, sess, engines)."""
    from trader_engine import cli
    cfgd = write_config(tmp_path)
    clock = SimClock(NOW0)
    sess = FakeBinance(clock, PAIRS10)
    feed, store = _feed(tmp_path, clock, sess, cfgd)
    feed.start()                                                     # = systemctl start trader-feed (acilis: kurallar + backfill)
    for _ in range(3):
        clock.advance(60)
        feed.run_once()
    feed.close()
    engines = {}
    for b in bots:
        assert cli.main(["init-ledger", "--bot", b, "--config-dir", str(cfgd)]) == 0      # ExecStartPre
        e = engines[b] = _engine(cfgd, clock, b)
        e._startup_gate()                                            # 10/10: bekleme yok, EngineExit yok
        e.status.write(e, force=True)
    return cfgd, clock, sess, engines


def _health_env(tmp_path, cfgd):
    (tmp_path / "bk").mkdir(exist_ok=True)
    (tmp_path / "hs").mkdir(exist_ok=True)
    # M1 paketi: sunucuda paket dagitimdan hemen sonra tazedir. Depodaki models/pa_proposer kopyalanir ve created_at
    # benzetim saatine (NOW0) cekilir; aksi halde depo paketi (gercek tarihli) benzetim zamaninda 8 gunden eski sayilip
    # pa_proposer_stale WARN'i uretir ve bu tatbikatlarin beklenen alarm kumesini kirar.
    models = tmp_path / "models" / "pa_proposer"
    if not models.exists():
        shutil.copytree(ROOT / "models" / "pa_proposer", models)
        for mp in models.glob("*.json"):
            d = json.loads(mp.read_text(encoding="utf-8"))
            d["meta"]["created_at"] = NOW0.isoformat()
            mp.write_text(json.dumps(d), encoding="utf-8")
    return {"PA_PROPOSER_MODELS_DIR": str(models), "ENGINE_VAR_DIR": str(tmp_path / "var"), "BACKUP_DIR": str(tmp_path / "bk"), "HEARTBEAT_URL": "https://hb.invalid/x",
            "MARKET_DB": str(tmp_path / "var" / "market.sqlite"), "ENGINE_CONFIG_DIR": str(cfgd), "NOTIFIER": "log",
            "STATE_DIR": str(tmp_path / "hs")}


def test_rehearsal_empty_server_feed_rules_gate_status_health(tmp_path, capsys):
    """Bos sunucu: feed baslat+backfill -> kurallar 10/10 -> init-ledger -> motor kapisi gecer -> status.json -> health (ogrenen) OK/WARN."""
    from trader_core import health as H
    cfgd, clock, _, _e = _bring_up(tmp_path)
    db = tmp_path / "var" / "market.sqlite"
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    assert c.execute("select count(*) from rules").fetchone()[0] == 10          # runbook: sqlite3 var/market.sqlite 'select count(*) from rules'
    for kind in ("last", "mark"):
        n = c.execute("select count(distinct pair) from bars where kind=? and tf='1m'", (kind,)).fetchone()[0]
        assert n == 10, kind
    c.close()
    for bot in ("learner",):
        st = json.loads((tmp_path / "var" / bot / "status.json").read_text())
        assert st["counters"]["rules_missing"] == 0 and st["counters"]["data_stale"] == 0
        assert st["bot"] == bot and st["mode"] == "paper"
    hr = _health_mod("health_run_r")
    env, sender, notifier = _health_env(tmp_path, cfgd), _Sender(), H.NullNotifier()
    rc = hr.run_once(env, now=clock.now(), state_path=str(tmp_path / "hs" / "state.json"), notifier=notifier, sender=sender)
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0 and sender.calls == ["ok"] and out["overall"] in ("OK", "WARN")
    # ilk saatte yalniz 'ledger_write_stale_warmup' (uyari) beklenir; baska bozuk kontrol yok
    assert {f["code"] for f in out["failing"]} <= {"ledger_write_stale_warmup"}, out["failing"]


def test_OPEN_health_is_not_crit_in_learner_only_deployment(tmp_path, capsys):
    from trader_core import health as H
    cfgd, clock, _, _e = _bring_up(tmp_path, bots=("learner",))
    hr = _health_mod("health_run_r3")
    sender = _Sender()
    env = _health_env(tmp_path, cfgd)
    env["HEALTH_BOTS"] = "learner"
    hr.run_once(env, now=clock.now(), state_path=str(tmp_path / "hs" / "state.json"),
                notifier=H.NullNotifier(), sender=sender)
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["overall"] != "CRIT" and sender.calls == ["ok"]


# ------------------------------------------------------------------ 5.2 feed olur -> data_stale -> health CRIT
def test_drill_feed_killed_midrun_engine_data_stale_and_health_crit(tmp_path, capsys, monkeypatch):
    from trader_core import health as H
    import shutil
    # Disk uyarisi bu tatbikatin konusu degil: test makinesinin gercek disk dolulugu sonucu etkilemesin.
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(100, 10, 90))
    cfgd, clock, sess, engines = _bring_up(tmp_path)                  # feed calisti, sonra 'oldu' (artik yazan yok)
    eng = engines["learner"]
    sess.dead_at_ms = to_ms(clock.now())
    clock.advance(11 * 60)                                            # 11 dk gecer, kimse mum yazmaz
    missing, stale = eng.check_inputs()                               # motor dakikada bir bunu calistirir (_periodic_input_check)
    assert not missing and len(stale) == 10
    eng.status.write(eng, force=True)
    st = json.loads((tmp_path / "var" / "learner" / "status.json").read_text())
    assert st["counters"]["data_stale"] == 10                         # status.json: gorunur sayac
    # ---- health 5 dk'lik turu: piyasa mumu bayat -> CRIT; dis nabiz 'ok' DEGIL 'fail'
    hr = _health_mod("health_run_r2")
    sender, notifier = _Sender(), H.NullNotifier()
    rc = hr.run_once(_health_env(tmp_path, cfgd), now=clock.now(), state_path=str(tmp_path / "hs" / "state.json"),
                     notifier=notifier, sender=sender)
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    codes = {f["name"]: f["code"] for f in out["failing"]}
    assert codes.get("market_bar_age") == "market_bars_stale"
    assert out["overall"] == "CRIT" and rc == hr.EXIT_UNHEALTHY == 10
    assert sender.calls == ["fail"]                                   # dis nabiz hemen 'fail' (sessizlik yok)
    assert not notifier.sent                                          # bildirim 2 ardisik turda dogrulanir (confirm_runs): ilk turda yok
    clock.advance(5 * 60)                                             # bir sonraki 5 dk'lik tur
    hr.run_once(_health_env(tmp_path, cfgd), now=clock.now(), state_path=str(tmp_path / "hs" / "state.json"),
                notifier=notifier, sender=sender)
    assert sender.calls == ["fail", "fail"]
    assert any(a.level in (H.Status.CRIT, H.Status.UNKNOWN) for a in notifier.sent)   # Telegram/log bildirimi ~5-10 dk icinde


# ------------------------------------------------------------------ 5.3 bir cift kural eksik -> motor kapisi cikis 7 (surec duzeyi)
def _run_cli(tmp_path, *args, timeout=60):
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src"), "PYTHONUNBUFFERED": "1"}
    return subprocess.run([sys.executable, "-m", "trader_engine", *args], cwd=tmp_path, env=env, capture_output=True,
                          text=True, timeout=timeout)


def _seed_market(tmp_path, *, rules_for, stale=False):
    """tmp_path/var/market.sqlite: gercek zamana gore taze 1m last+mark (stale=True: 2 saat eski) + secilen ciftlerin kurallari."""
    from datetime import datetime, timezone
    from trader_engine.bars import to_ms as tms
    from trader_engine.exchange.rules import extract_all_rules, spec_to_json
    from trader_engine.types import Bar
    now = datetime.now(timezone.utc)
    last_open = (now - timedelta(minutes=2 if not stale else 120)).replace(second=0, microsecond=0)
    clk = SimClock(now)
    sess = FakeBinance(clk, PAIRS10)
    (tmp_path / "var").mkdir(exist_ok=True)
    st = MarketStore(tmp_path / "var" / "market.sqlite")
    res = extract_all_rules(sess.info, [p.replace("/", "") for p in rules_for])
    for p in rules_for:
        st.put_rules(p, spec_to_json(res[p.replace("/", "")]), tms(now))
    for p in PAIRS10:
        for i in range(4):
            t = last_open - timedelta(minutes=i)
            for kind in ("last", "mark"):
                st.put_bars([Bar(p, kind, "1m", t, 100, 101, 99, 100.5, 1.0 if kind == "last" else 0.0)], now_ms=tms(now))
    st.close()


def test_drill_one_pair_missing_rules_engine_gate_exit_7(tmp_path):
    write_config(tmp_path, startup_wait_s=0.0, relative=True)
    _seed_market(tmp_path, rules_for=PAIRS10[:-1])                   # AVAX kurali yok
    r = _run_cli(tmp_path, "init-ledger", "--bot", "learner", "--config-dir", "config")
    assert r.returncode == 0, r.stderr[-500:]                        # ExecStartPre
    r = _run_cli(tmp_path, "run", "--bot", "learner", "--config-dir", "config")
    assert r.returncode == EXIT_STARTUP_GATE == 7, r.stderr[-800:]
    crit = [ln for ln in r.stderr.splitlines() if "CRITICAL" in ln]
    assert len(crit) == 1 and "AVAX/USDT" in crit[0] and "kural eksik" in crit[0]     # journalctl'de tek, adli CRITICAL satir
    st = json.loads((tmp_path / "var" / "learner" / "status.json").read_text()) if (tmp_path / "var/learner/status.json").exists() else None
    if st is not None:
        assert st["counters"]["rules_missing"] == 1


def test_drill_stale_data_engine_gate_exit_7(tmp_path):
    write_config(tmp_path, startup_wait_s=0.0, relative=True)
    _seed_market(tmp_path, rules_for=PAIRS10, stale=True)
    assert _run_cli(tmp_path, "init-ledger", "--bot", "learner", "--config-dir", "config").returncode == 0
    r = _run_cli(tmp_path, "run", "--bot", "learner", "--config-dir", "config")
    assert r.returncode == 7 and "veri bayat" in r.stderr


def test_drill_gate_passes_with_all_rules_and_fresh_data_then_terminates_cleanly(tmp_path):
    """10/10 + taze veri: surec kalkar, status.json yazar, SIGTERM ile 0 cikar (birim: systemctl stop -> basarili)."""
    import signal
    import time
    write_config(tmp_path, startup_wait_s=30.0, relative=True)
    _seed_market(tmp_path, rules_for=PAIRS10)
    assert _run_cli(tmp_path, "init-ledger", "--bot", "learner", "--config-dir", "config").returncode == 0
    # init-ledger idempotent (ExecStartPre her baslatmada)
    r2 = _run_cli(tmp_path, "init-ledger", "--bot", "learner", "--config-dir", "config")
    assert r2.returncode == 0 and "dokunulmadi" in r2.stdout
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")}
    p = subprocess.Popen([sys.executable, "-m", "trader_engine", "run", "--bot", "learner", "--config-dir", "config"],
                         cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    sp = tmp_path / "var" / "learner" / "status.json"
    try:
        deadline = time.time() + 45
        while time.time() < deadline and not sp.exists() and p.poll() is None:
            time.sleep(0.5)
        assert sp.exists(), p.stderr.read() if p.poll() is not None else "status.json olusmadi"
        time.sleep(1.0)
        st = json.loads(sp.read_text())
        assert st["counters"]["rules_missing"] == 0 and st["counters"]["data_stale"] == 0
        assert st["bot"] == "learner" and st["mode"] == "paper" and st["kill"] is False
        # NOT: veto anahtari/belgesi yok iken de status.json `entries_open: true` der; veto reddi YALNIZ aday basina defterde
        # (skip_reason=veto_missing/veto_stale) gorunur. Gercek zamanli veto alarmi yok (docs/hazirlik-denetimi.md OPEN-5).
        assert st["gate"] == {"ok": True, "code": "ok"} and st["entries_open"] is True
    finally:
        p.send_signal(signal.SIGTERM)
        try:
            rc = p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
            rc = -9
    assert rc == 0


# ------------------------------------------------------------------ 5.5 Telegram anahtarlari yok -> CRIT nereye gider?
def test_drill_telegram_keys_missing_crit_goes_to_journal_not_silence(tmp_path):
    """`trader-health-fail@.service`: ExecStartPre (telegram send) '-' onekli: anahtar yoksa cikis 1 + stderr mesaji, zincir devam eder;
    ExecStart health_fail.sh: `logger -p daemon.crit` (journal) + varsa HEARTBEAT_FAIL_URL. Yani CRIT yalniz journal/panel/dis nabiz'da kalir."""
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/telegram_run.py"), "send", "--severity", "CRIT",
                        "--dedup-key", "health-fail:trader-feed.service", "Birim basarisiz: trader-feed.service"],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 1 and "telegram yapilandirilmamis" in r.stderr
    unit = (ROOT / "deploy/trader-health-fail@.service").read_text()
    assert "ExecStartPre=-" in unit and "EnvironmentFile=-/etc/trader-telegram.env" in unit
    r = subprocess.run(["bash", str(ROOT / "scripts/health_fail.sh"), "trader-feed.service"], env=env, capture_output=True, text=True)
    assert r.returncode == 0
    assert "HEARTBEAT_FAIL_URL yok" in r.stderr                       # dis bildirim 'atlandi' diye YAZILIR (sessiz degil)


def test_drill_telegram_send_with_keys_but_no_network_spools_not_drops(tmp_path):
    """Anahtar var, Telegram'a ulasilamiyor: mesaj outbox'a (spool) yazilir; daemon sonra bosaltir."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("telegram_run_r", ROOT / "scripts/telegram_run.py")
    tr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tr)

    def boom(*a, **k):
        raise OSError("network down")

    env = {"TELEGRAM_BOT_TOKEN": "123456:ABC-" + "x" * 30, "TELEGRAM_CHAT_ID": "42", "TELEGRAM_VAR_DIR": str(tmp_path / "tg")}
    rc = tr.main(["send", "--severity", "CRIT", "--dedup-key", "k1", "Birim basarisiz: trader-feed.service"],
                 env=env, http_post=boom, sleep=lambda s: None)
    assert rc == 0
    spool = list((tmp_path / "tg" / "outbox").glob("*"))
    assert [p for p in spool if p.is_file()], "mesaj spool'a yazilmadi (sessiz kayip)"


# ------------------------------------------------------------------ sandbox fizigi (mount namespace; root + unshare gerekir, yoksa atlanir)
def _can_unshare():
    import os
    import shutil
    if os.geteuid() != 0 or shutil.which("unshare") is None:
        return False
    return subprocess.run(["unshare", "-m", "true"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _can_unshare(), reason="mount namespace (root+unshare) yok")
def test_sandbox_file_level_rw_cannot_create_sqlite_journal_or_wal(tmp_path):
    """ProtectSystem=strict + `ReadWritePaths=<dosya>`: dizin salt okunur kalir; SQLite -journal/-wal/-shm OLUSTURAMAZ.
    Ders/Telegram birimleri budget.sqlite (journal_mode=DELETE) ve lesson.sqlite (WAL) icin yalniz dosya yollari listeler -> OPEN-2.
    Dizin duzeyinde RW verilince calisir (karsi kanit)."""
    ud = tmp_path / "ud"
    ud.mkdir()
    for n, mode in (("budget.sqlite", "DELETE"), ("lesson.sqlite", "WAL")):
        c = sqlite3.connect(ud / n)
        c.execute(f"pragma journal_mode={mode}")
        c.execute("create table t(x)")
        c.commit()
        c.close()
    probe = tmp_path / "probe.py"
    probe.write_text('''
import sqlite3, sys
res = []
for n, m in (("budget.sqlite", "DELETE"), ("lesson.sqlite", "WAL")):
    try:
        c = sqlite3.connect(sys.argv[1] + "/" + n, timeout=1, isolation_level=None)
        c.execute("pragma journal_mode=" + m); c.execute("begin immediate"); c.execute("insert into t values(1)"); c.execute("commit"); c.close()
        res.append(n + ":ok")
    except Exception as e:
        res.append(n + ":FAIL")
print(" ".join(res))
''')

    def run(dir_rw):
        extra = f'mount --bind {ud} {ud} && mount -o remount,bind,ro {ud}\n'
        if dir_rw:
            extra = f'mount --bind {ud} {ud}\n'
        else:
            extra += "".join(f'[ -e {ud}/{f} ] && {{ mount --bind {ud}/{f} {ud}/{f}; mount -o remount,bind,rw {ud}/{f}; }}\n'
                             for f in ("budget.sqlite", "lesson.sqlite", "lesson.sqlite-wal", "lesson.sqlite-shm"))
        r = subprocess.run(["unshare", "-m", "sh", "-c", extra + f'{sys.executable} {probe} {ud}'], capture_output=True, text=True)
        return r.stdout.strip()

    assert run(dir_rw=False) == "budget.sqlite:FAIL lesson.sqlite:FAIL"
    assert run(dir_rw=True) == "budget.sqlite:ok lesson.sqlite:ok"


# ------------------------------------------------------------------ yedek (backup timer'in calistirdigi kod): ledger+state yedegi, dogrulama
def _backup_mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("health_backup_r", ROOT / "scripts" / "health_backup.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_backup_of_running_engines_ledgers_is_ok_and_restorable(tmp_path):
    _cfgd, _clock, _sess, _engines = _bring_up(tmp_path)           # motorlar defteri/state'i ACIK tutar (WAL): canli yedek
    bm = _backup_mod()
    code, m = bm.run_backup(str(tmp_path / "bk"), str(tmp_path / "var"), 14)
    assert code == 0 and m["ok"] is True
    assert set(m["files"]) == {"ledger_learner.sqlite", "state_learner.sqlite"}
    day = next((tmp_path / "bk").iterdir())
    for n in m["files"]:
        c = sqlite3.connect(day / n)
        assert c.execute("pragma integrity_check").fetchone()[0] == "ok", n
        c.close()


def test_OPEN_backup_is_ok_in_learner_only_deployment(tmp_path):
    _bring_up(tmp_path, bots=("learner",))
    code, m = _backup_mod().run_backup(str(tmp_path / "bk"), str(tmp_path / "var"), 14, bots=_backup_mod().bots_from_env({"HEALTH_BOTS": "learner"}))
    assert code == 0 and m["ok"] is True


def test_drill_backup_of_closed_wal_ledger_in_writable_dir_via_mode_ro(tmp_path):
    """OPEN-10: temiz kapatilmis WAL defteri (-wal/-shm yok), yazilabilir dizinde, yedek betiginin mode=ro URI'siyle yedeklenir."""
    from trader_engine import cli
    cfgd = write_config(tmp_path)
    assert cli.main(["init-ledger", "--bot", "learner", "--config-dir", str(cfgd)]) == 0     # surec cikti -> defter temiz kapandi
    src = tmp_path / "var" / "learner" / "ledger.sqlite"
    assert src.is_file()
    assert not (tmp_path / "var" / "learner" / "ledger.sqlite-wal").exists()
    bm = _backup_mod()
    res = bm.backup_one("ledger", "learner", src, tmp_path / "out.sqlite")
    assert res["ok"] is True, res
    c = sqlite3.connect(f"file:{tmp_path / 'out.sqlite'}?mode=ro", uri=True)
    assert c.execute("pragma integrity_check").fetchone()[0] == "ok"
    c.close()


# ------------------------------------------------------------------ panel okur + KILL dosyasi (motor/panel ayni yol)
def test_panel_reads_status_ledger_health_and_kill_file_is_shared(tmp_path):
    from trader_core import health as H
    from trader_panel.data import PanelData, load_config
    cfgd, clock, _s, engines = _bring_up(tmp_path)
    hr = _health_mod("health_run_r4")
    env = _health_env(tmp_path, cfgd)
    hr.run_once(env, now=clock.now(), state_path=str(tmp_path / "hs" / "state.json"), notifier=H.NullNotifier(), sender=_Sender())
    pj = json.loads((cfgd / "panel.json").read_text())
    pj["health_state"] = str(tmp_path / "hs" / "state.json")
    pj["kill_file"] = str(tmp_path / "shared" / "KILL")                 # motorla ayni (write_config mutlaklastirir)
    (cfgd / "panel.json").write_text(json.dumps(pj))
    pd = PanelData(load_config(cfgd / "panel.json"), clock=clock.now)
    st = pd.status()
    assert st["ok"] and st["kill_file_exists"] is False
    assert {b: v["state"] for b, v in st["bots"].items()} == {"learner": "live"}
    assert pd.ledger("learner", None)["ok"] and pd.ledger("twin", None)["ok"] is False   # DD-12: ikiz yok
    assert pd.health()["ok"]
    # KILL: motorun kill_file'i ile panelinki ayni; dosya olusunca ikisi de gorur
    assert engines["learner"].cfg.kill_file == pj["kill_file"] == str(tmp_path / "shared" / "KILL")
    (tmp_path / "shared").mkdir(exist_ok=True)
    engines["learner"].kill.set("test", "hazirlik")
    assert engines["learner"].kill.active()
    assert PanelData(load_config(cfgd / "panel.json"), clock=clock.now).status()["kill_file_exists"] is True
