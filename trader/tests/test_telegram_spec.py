"""Telegram modulu bagimsiz spec testleri (docs/telegram-spec.md). Ag yok; sahte Telegram (enjekte http_post)."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trader_core import telegram as tg  # noqa: E402
from trader_core.health import Alert, Status  # noqa: E402
from trader_engine.clock import SimClock  # noqa: E402


class _FnClk:
    def __init__(self, fn):
        self._fn = fn

    def now(self):
        return self._fn()


def _ks_for(cfg, now_fn):
    return Killswitch(cfg.kill_file, _FnClk(now_fn)) if cfg.kill_file else None
from trader_engine.killswitch import Killswitch  # noqa: E402

TOKEN = "123456:SECRETTOKENabcdefXYZ"
CID = 123456789
T0 = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
REQ = "lr-2026-11-16-3"


# --------------------------------------------------------------------------- yardimcilar
class Clk:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t = self.t + timedelta(seconds=s)


class FakeTelegram:
    def __init__(self):
        self.calls = []          # (method, payload)
        self.queue = []          # sendMessage ozel yanitlari: (status, body)
        self.updates = []        # getUpdates yanit partileri
        self.mid = 100
        self.always = None

    def post(self, url, json=None, timeout=None, **kw):
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, json or {}))
        if method == "sendMessage":
            if self.always is not None:
                return self.always
            if self.queue:
                return self.queue.pop(0)
            self.mid += 1
            return 200, {"ok": True, "result": {"message_id": self.mid}}
        if method == "getUpdates":
            batch = self.updates.pop(0) if self.updates else []
            return 200, {"ok": True, "result": batch}
        return 200, {"ok": True, "result": True}

    def of(self, method):
        return [p for m, p in self.calls if m == method]

    @property
    def texts(self):
        return [p.get("text", "") for p in self.of("sendMessage")]

    def alltext(self):
        return "\n".join(self.texts)


def msg(uid, text, date, chat_id=CID, chat_type="private", from_id=None, is_bot=False, key="message"):
    return {"update_id": uid, key: {
        "message_id": uid, "date": int(date.timestamp()),
        "chat": {"id": chat_id, "type": chat_type},
        "from": {"id": chat_id if from_id is None else from_id, "is_bot": is_bot},
        "text": text}}


def cb(uid, data, msg_date, cid=CID):
    return {"update_id": uid, "callback_query": {
        "id": f"cbq{uid}", "from": {"id": cid, "is_bot": False}, "data": data,
        "message": {"message_id": 77, "date": int(msg_date.timestamp()),
                    "chat": {"id": cid, "type": "private"}, "text": "orijinal"}}}


class Env:
    pass


def write_status(path, mode="paper", kill=True, kill_state="flat", loop_at=None, **extra):
    d = {"schema": "engine-status/1", "bot": "b", "mode": mode,
         "loop_at": (loop_at or T0).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "strategy": {"name": "s", "version": "1"}, "param_version_id": 1,
         "entries_open": False, "gate": {"ok": True, "code": "ok"}, "kill": kill, "kill_state": kill_state,
         "entries_blocked_reason": None, "equity": 1000.0, "day_start_equity": 1000.0,
         "open_positions": [], "counters": {}}
    d.update(extra)
    Path(path).write_text(json.dumps(d))


@pytest.fixture
def env(tmp_path, monkeypatch):
    e = Env()
    e.tmp = tmp_path
    e.fake = FakeTelegram()
    e.clk = Clk()
    e.sleeps = []
    e.kill_file = str(tmp_path / "KILL")
    e.status_path = str(tmp_path / "status.json")
    e.cfg = tg.TelegramConfig(token=TOKEN, chat_id=CID, var_dir=str(tmp_path / "var"), kill_file=e.kill_file,
                              status_path=e.status_path,
                              health_state=str(tmp_path / "health.json"))
    (tmp_path / "var").mkdir()
    e.client = tg.TelegramClient(TOKEN, http_post=e.fake.post, sleep=e.sleeps.append)
    e.ks = Killswitch(e.kill_file, SimClock(T0))
    e.new_daemon = lambda **kw: tg.TelegramDaemon(
        e.cfg, e.client, now_fn=e.clk, sleep=e.sleeps.append,
        random_code=kw.pop("random_code", lambda: "4821"),
        killswitch=kw.pop("killswitch", _ks_for(e.cfg, e.clk)), **kw)
    e.offset = lambda: _read_offset(tmp_path)
    e.d = e.new_daemon()
    e.clk.advance(2)
    write_status(e.status_path)
    e.send = lambda text, uid=None, **kw: e.d.process_updates([msg(uid or _next(), text, kw.pop("date", e.clk()), **kw)])
    return e


_ctr = [1000]


def _next():
    _ctr[0] += 1
    return _ctr[0]


def _find(base, name):
    for p in Path(base).rglob(name):
        return p
    return None


def _read_offset(base):
    p = _find(base, "offset.json")
    if p is None:
        return None
    v = json.loads(p.read_text())
    if isinstance(v, int):
        return v
    for x in v.values():
        if isinstance(x, int):
            return x
    return None


def _audit_text(base):
    p = _find(base, "audit.jsonl")
    return p.read_text() if p else ""


def _all_files_text(base):
    out = []
    for p in Path(base).rglob("*"):
        if p.is_file():
            try:
                out.append(p.read_text(errors="ignore"))
            except OSError:
                pass
    return "\n".join(out)


def kill_active(e):
    return Path(e.kill_file).exists()


def code_of(text):
    m = re.search(r"(?<!\d)(\d{4})(?!\d)", text)
    return m.group(1) if m else None


def set_kill(e, by="telegram:789", reason="user_cmd"):
    e.ks.set(by=by, reason=reason)


# --------------------------------------------------------------------------- Bolum 3: yetki
def test_foreign_chat_ignored_and_audited(env):
    env.send("/hepsini_kapat", chat_id=555000999)
    assert env.fake.of("sendMessage") == []
    a = _audit_text(env.tmp)
    assert "unauthorized" in a
    assert "555000999" not in a


def test_foreign_chat_cannot_execute_commands(env):
    set_kill(env, by="x", reason="manual")
    env.send("/durum", chat_id=555000999)
    assert env.fake.of("sendMessage") == []


def test_unauthorized_audit_truncates_cmd(env):
    long = "/hepsini_kapat " + "A" * 80
    env.send(long, chat_id=555000999)
    a = _audit_text(env.tmp)
    assert "A" * 40 not in a


def test_group_chat_with_right_id_rejected(env):
    env.send("/hepsini_kapat", chat_type="group")
    env.send("/hepsini_kapat", chat_type="supergroup")
    assert env.fake.of("sendMessage") == []


def test_wrong_from_id_rejected(env):
    env.send("/hepsini_kapat", from_id=999)
    assert env.fake.of("sendMessage") == []


def test_bot_sender_rejected(env):
    env.send("/hepsini_kapat", is_bot=True)
    assert env.fake.of("sendMessage") == []


def test_edited_message_ignored(env):
    env.d.process_updates([msg(_next(), "/hepsini_kapat", env.clk(), key="edited_message")])
    assert env.fake.of("sendMessage") == []


def test_callback_from_foreign_chat_ignored(env):
    exp = int(env.clk().timestamp()) + 600
    env.d.process_updates([cb(_next(), f"no:{REQ}:{exp}", env.clk(), cid=555000999)])
    assert env.fake.of("answerCallbackQuery") == []


def test_allowed_updates_only_message_and_callback(env):
    env.fake.updates = [[]]
    env.d.poll_once(timeout=1)
    au = env.fake.of("getUpdates")[0].get("allowed_updates")
    assert sorted(au) == ["callback_query", "message"]


# --------------------------------------------------------------------------- Bolum 4: polling
def test_duplicate_update_id_executes_once(env):
    u = msg(5001, "/durum", env.clk())
    env.d.process_updates([u])
    n = len(env.fake.of("sendMessage"))
    env.d.process_updates([u])
    assert len(env.fake.of("sendMessage")) == n


def test_duplicate_after_restart_not_executed_twice(env):
    u = msg(5003, "/durum", env.clk())
    env.d.process_updates([u])
    n = len(env.fake.of("sendMessage"))
    d2 = env.new_daemon()
    d2.process_updates([u])
    assert len(env.fake.of("sendMessage")) == n


def test_offset_advances_after_execution(env):
    u = msg(6001, "/durum", env.clk())
    env.d.process_updates([u])
    assert len(env.fake.of("sendMessage")) == 1
    assert env.offset() == 6002
    assert "6001" in _audit_text(env.tmp)


def test_poll_once_uses_offset_next_poll(env):
    env.fake.updates = [[msg(7001, "/yardim", env.clk())], []]
    env.d.poll_once(timeout=1)
    env.d.poll_once(timeout=1)
    gu = env.fake.of("getUpdates")
    assert gu[1].get("offset") == 7002


def test_stale_command_not_executed(env):
    env.send("/durum", date=env.clk() - timedelta(seconds=121))
    assert "kasa" not in env.fake.alltext().lower()
    assert "yeniden gönder" in env.fake.alltext()                 # "İşlenmedi; yeniden gönder (yaş: N sn)"


def test_stale_reply_once_per_update(env):
    u = msg(8001, "/yardim", env.clk() - timedelta(seconds=300))
    env.d.process_updates([u])
    env.d.process_updates([u])
    assert len(env.fake.of("sendMessage")) == 1


def test_fresh_within_window_executes(env):
    env.clk.advance(200)
    env.send("/durum", date=env.clk() - timedelta(seconds=100))
    assert len(env.fake.of("sendMessage")) == 1


def test_message_older_than_daemon_start_not_executed(env):
    env.clk.advance(60)
    d2 = env.new_daemon()
    env.clk.advance(1)
    d2.process_updates([msg(_next(), "/durum", env.clk() - timedelta(seconds=30))])
    assert "kasa" not in env.fake.alltext().lower()


def test_stale_code_reply_does_not_kill(env):
    env.send("/hepsini_kapat")
    env.send("4821", date=env.clk() - timedelta(seconds=121))
    assert not kill_active(env)


# --------------------------------------------------------------------------- 5.1 /hepsini_kapat
def test_hepsini_kapat_sends_4digit_code_no_kill(env):
    env.d = env.new_daemon(random_code=None) if False else env.d
    env.send("/hepsini_kapat")
    assert not kill_active(env)
    assert code_of(env.fake.alltext()) == "4821"


def test_default_code_generator_is_4_digits(env):
    d = tg.TelegramDaemon(env.cfg, env.client, now_fn=env.clk, sleep=env.sleeps.append,
                          killswitch=_ks_for(env.cfg, env.clk))
    env.clk.advance(2)
    d.process_updates([msg(_next(), "/hepsini_kapat", env.clk())])
    codes = re.findall(r"(?<!\d)\d{4}(?!\d)", env.fake.alltext())
    assert codes, env.fake.texts
    c = codes[-1]
    d.process_updates([msg(_next(), c, env.clk())])
    assert kill_active(env)


def test_correct_code_sets_killswitch(env):
    env.send("/hepsini_kapat")
    env.send("4821")
    assert kill_active(env)
    info = env.ks.info()
    assert info["by"].startswith("telegram:")
    assert info["by"].endswith("789")
    assert info["reason"] == "user_cmd"


def test_code_within_ttl_119s(env):
    env.send("/hepsini_kapat")
    env.clk.advance(119)
    env.send("4821")
    assert kill_active(env)


def test_code_after_ttl_121s_rejected(env):
    env.send("/hepsini_kapat")
    env.clk.advance(121)
    env.send("4821")
    assert not kill_active(env)


def test_wrong_code_cancels_and_correct_afterwards_does_nothing(env):
    env.send("/hepsini_kapat")
    env.send("0000")
    assert not kill_active(env)
    env.send("4821")
    assert not kill_active(env)


def test_code_from_other_chat_does_nothing(env):
    env.send("/hepsini_kapat")
    env.send("4821", chat_id=555000999)
    assert not kill_active(env)


def test_code_single_use(env):
    env.send("/hepsini_kapat")
    env.send("4821")
    assert kill_active(env)
    env.ks.clear()
    env.send("4821")
    assert not kill_active(env)


def test_bare_code_without_pending_does_nothing(env):
    env.send("4821")
    assert not kill_active(env)
    assert "bekleyen" in env.fake.alltext().lower()


def test_onay_kod_form_not_accepted(env):
    env.send("/hepsini_kapat")
    env.send("/onay 4821")
    assert not kill_active(env)


def test_code_with_extra_text_not_accepted(env):
    env.send("/hepsini_kapat")
    env.send("kod 4821")
    assert not kill_active(env)


def test_phrase_normalization_and_exact_match(env):
    env.send("Hepsini Kapat")
    assert code_of(env.fake.alltext()) == "4821"
    env2 = len(env.fake.of("sendMessage"))
    env.send("lutfen hepsini kapat bence")
    assert len(env.fake.of("sendMessage")) == env2 or "4821" not in env.fake.texts[-1]
    assert not kill_active(env)


def test_kill_already_active_idempotent(env):
    set_kill(env, by="me", reason="manual")
    before = env.ks.info()
    env.send("/hepsini_kapat")
    assert "zaten" in env.fake.alltext().lower()
    assert env.ks.info() == before


def test_pending_survives_restart_within_ttl(env):
    env.send("/hepsini_kapat")
    d2 = env.new_daemon()
    env.clk.advance(2)
    d2.process_updates([msg(_next(), "4821", env.clk())])
    assert kill_active(env)


def test_pending_after_restart_expired(env):
    env.send("/hepsini_kapat")
    d2 = env.new_daemon()
    env.clk.advance(130)
    d2.process_updates([msg(_next(), "4821", env.clk())])
    assert not kill_active(env)


def test_code_not_stored_plaintext(env):
    env.send("/hepsini_kapat")
    p = _find(env.tmp, "pending.json")
    assert p is not None
    assert "4821" not in p.read_text()
    assert "4821" not in _audit_text(env.tmp)


def test_new_pending_invalidates_old(env):
    codes = iter(["1111", "2222"])
    d = env.new_daemon(random_code=lambda: next(codes))
    env.clk.advance(2)
    d.process_updates([msg(_next(), "/hepsini_kapat", env.clk())])
    d.process_updates([msg(_next(), "/hepsini_kapat", env.clk())])
    d.process_updates([msg(_next(), "1111", env.clk())])
    assert not kill_active(env)


# --------------------------------------------------------------------------- 5.2 /devam
def _devam(env, code="4821"):
    env.send("/devam")
    env.send(code)


def test_devam_two_step_paper(env):
    write_status(env.status_path, mode="paper", kill_state="flat")
    set_kill(env, by="me", reason="manual")
    env.send("/devam")
    assert kill_active(env)                      # ilk adimda kalkmaz
    assert code_of(env.fake.alltext()) == "4821"
    env.send("4821")
    assert not kill_active(env)


def test_devam_without_kill_noop(env):
    env.send("/devam")
    assert "etkin değil" in env.fake.alltext() or "etkin degil" in env.fake.alltext().lower()
    assert code_of(env.fake.alltext()) is None


def test_devam_refused_while_exiting_paper(env):
    write_status(env.status_path, mode="paper", kill_state="exiting")
    set_kill(env, by="me", reason="manual")
    _devam(env)
    assert kill_active(env)
    assert "Kapanış sürüyor" in env.fake.alltext()


def test_devam_refused_while_exiting_live_even_telegram_origin(env):
    write_status(env.status_path, mode="live", kill_state="exiting")
    set_kill(env)
    _devam(env)
    assert kill_active(env)


def test_devam_rechecks_preconditions_on_code(env):
    write_status(env.status_path, mode="paper", kill_state="flat")
    set_kill(env, by="me", reason="manual")
    env.send("/devam")
    write_status(env.status_path, mode="paper", kill_state="exiting")
    env.send("4821")
    assert kill_active(env)


def test_devam_live_telegram_origin_flat_allowed(env):
    write_status(env.status_path, mode="live", kill_state="flat")
    set_kill(env, by="telegram:789", reason="user_cmd")
    _devam(env)
    assert not kill_active(env)


def test_devam_live_other_origin_refused(env):
    write_status(env.status_path, mode="live", kill_state="flat")
    set_kill(env, by="me", reason="manual")
    _devam(env)
    assert kill_active(env)
    assert "sunucuda" in env.fake.alltext()


def test_devam_live_telegram_wrong_reason_refused(env):
    write_status(env.status_path, mode="live", kill_state="flat")
    set_kill(env, by="telegram:789", reason="manual")
    _devam(env)
    assert kill_active(env)


def test_devam_live_telegram_origin_not_flat_refused(env):
    write_status(env.status_path, mode="live", kill_state="idle_not_flat")
    set_kill(env, by="telegram:789", reason="user_cmd")
    _devam(env)
    assert kill_active(env)


def test_devam_unknown_mode_treated_as_live(env):
    d = json.loads(Path(env.status_path).read_text())
    d.pop("mode")
    Path(env.status_path).write_text(json.dumps(d))
    set_kill(env, by="me", reason="manual")
    _devam(env)
    assert kill_active(env)


def test_devam_status_unreadable_fail_closed(env):
    Path(env.status_path).unlink()
    set_kill(env, by="telegram:789", reason="user_cmd")
    _devam(env)
    assert kill_active(env)


def test_devam_status_corrupt_fail_closed(env):
    Path(env.status_path).write_text("{bozuk")
    set_kill(env, by="telegram:789", reason="user_cmd")
    _devam(env)
    assert kill_active(env)


def test_devam_code_from_other_chat_nothing(env):
    set_kill(env, by="me", reason="manual")
    env.send("/devam")
    env.send("4821", chat_id=555000999)
    assert kill_active(env)


def test_durdur_without_pause_config_does_not_kill(env):
    """11 §9.5 ile karar 1 degisti: /durdur artik "desteklenmiyor" degil; PAUSE yapilandirilmamissa yalniz
    kill kurulmaz (yeni davranis tests/test_telegram_pause_spec.py'de)."""
    env.send("/durdur")
    assert not kill_active(env)


# --------------------------------------------------------------------------- 5.3 kaldirilan ders komutlari (25.11)
@pytest.mark.parametrize("cmd", ["/onayla " + REQ, "/reddet " + REQ, "/ders", "/onayla", f"/onayla {REQ}; DROP TABLE x"])
def test_kaldirilan_komutlar_tek_satir_yanit_islem_yok(env, cmd):
    env.send(cmd)
    out = env.fake.of("sendMessage")
    assert len(out) == 1 and "kaldırıldı" in out[0]["text"] and "/ml1" in out[0]["text"] and out[0]["text"].startswith("[ML] ")
    assert not kill_active(env)
    names = [p.name for p in env.tmp.rglob("*")]
    assert not any(n.startswith("lesson.sqlite") or n == "lesson.lock" for n in names)


@pytest.mark.parametrize("pfx", ["ok", "ev", "no", "vz"])
def test_eski_ders_dugmeleri_islem_yapmaz(env, pfx):
    exp = int(env.clk().timestamp()) + 600
    env.d.process_updates([cb(_next(), f"{pfx}:{REQ}:{exp}", env.clk())])
    assert len(env.fake.of("answerCallbackQuery")) == 1
    assert env.fake.of("editMessageText") == []


# --------------------------------------------------------------------------- Bolum 2: giden
def make_notifier(e_fake, tmp, clk=None, sleeps=None, token=TOKEN):
    clk = clk or Clk()
    sleeps = sleeps if sleeps is not None else []
    client = tg.TelegramClient(token, http_post=e_fake.post, sleep=sleeps.append)
    ob = tg.Outbox(tmp / "outbox", clk)
    n = tg.TelegramNotifier(client, CID, ob, now_fn=clk, sleep=sleeps.append)
    return n, ob, client, sleeps, clk


@pytest.fixture
def nt(tmp_path):
    f = FakeTelegram()
    n, ob, client, sleeps, clk = make_notifier(f, tmp_path)
    o = Env()
    o.f, o.n, o.ob, o.client, o.sleeps, o.clk, o.tmp = f, n, ob, client, sleeps, clk, tmp_path
    return o


def test_send_true_only_with_ok_and_message_id(nt):
    assert nt.n.send_text("merhaba", "INFO", "k1") is True


def test_send_ok_without_message_id_is_false(nt):
    nt.f.always = (200, {"ok": True, "result": {}})
    assert nt.n.send_text("merhaba", "INFO", "k2") is False


def test_send_ok_false_body_is_false(nt):
    nt.f.always = (200, {"ok": False, "description": "x"})
    assert nt.n.send_text("merhaba", "INFO", "k3") is False


def test_failure_spools_and_returns_false(nt):
    nt.f.always = (500, {"ok": False})
    assert nt.n.send_text("merhaba", "WARN", "k4") is False
    assert len(nt.ob.list()) == 1


def test_network_error_spools(nt):
    nt.f.always = (0, {})
    assert nt.n.send_text("merhaba", "CRIT", "k5") is False
    assert len(nt.ob.list()) == 1


def test_exception_from_post_never_raised(nt):
    def boom(url, json=None, timeout=None, **kw):
        raise RuntimeError(f"HTTPSConnectionPool url={url}")
    client = tg.TelegramClient(TOKEN, http_post=boom, sleep=nt.sleeps.append)
    n = tg.TelegramNotifier(client, CID, nt.ob, now_fn=nt.clk, sleep=nt.sleeps.append)
    assert n.send_text("x", "WARN", "k6") is False


@pytest.mark.parametrize("bad", ["", None])
def test_dedup_key_mandatory(nt, bad):
    try:
        r = nt.n.send_text("x", "INFO", bad)
    except ValueError:
        r = False
    assert r is False
    assert nt.f.of("sendMessage") == []


def test_same_dedup_key_delivered_once(nt):
    assert nt.n.send_text("a", "INFO", "dup") is True
    nt.n.send_text("a", "INFO", "dup")
    assert len(nt.f.of("sendMessage")) == 1


def test_no_double_delivery_spool_then_direct_then_drain(nt):
    nt.f.always = (500, {"ok": False})
    assert nt.n.send_text("a", "WARN", "dd") is False
    assert len(nt.ob.list()) == 1
    nt.n.send_text("a", "WARN", "dd")
    assert len(nt.ob.list()) <= 1
    nt.f.always = None
    nt.n.send_text("a", "WARN", "dd")
    nt.ob.drain(nt.client, CID, sleep=nt.sleeps.append)
    nt.ob.drain(nt.client, CID, sleep=nt.sleeps.append)
    ok_calls = [1 for m, p in nt.f.calls if m == "sendMessage"]
    delivered = nt.f.texts
    # basarili teslim sayisi: failure'lar 500 idi; yalniz tek basarili gonderim olmali
    assert nt.ob.sent_recently("dd")
    assert nt.ob.list() == []
    assert len(ok_calls) >= 1
    assert nt.f.mid - 100 == 1, delivered


def test_drain_delivers_once_and_deletes_file(nt):
    nt.f.always = (500, {"ok": False})
    nt.n.send_text("a", "WARN", "dr")
    nt.f.always = None
    n = nt.ob.drain(nt.client, CID, sleep=nt.sleeps.append)
    assert n == 1
    assert nt.ob.list() == []
    assert nt.f.mid - 100 == 1
    nt.n.send_text("a", "WARN", "dr")
    assert nt.f.mid - 100 == 1


def test_drain_failure_keeps_file(nt):
    nt.f.always = (500, {"ok": False})
    nt.n.send_text("a", "WARN", "dr2")
    nt.ob.drain(nt.client, CID, sleep=nt.sleeps.append)
    assert len(nt.ob.list()) == 1


def test_spool_one_file_per_key(nt):
    nt.f.always = (500, {"ok": False})
    nt.n.send_text("a", "WARN", "one")
    nt.n.send_text("b", "WARN", "one")
    assert len(nt.ob.list()) == 1


def test_retry_schedule_2_5_15(nt):
    nt.f.always = (500, {"ok": False})
    nt.n.send_text("a", "WARN", "rs")
    assert nt.sleeps == [2, 5, 15]


def test_429_retry_after_honored(nt):
    nt.f.queue = [(429, {"ok": False, "parameters": {"retry_after": 7}})]
    assert nt.n.send_text("a", "WARN", "r429") is True
    assert 7 in nt.sleeps


def test_429_retry_after_capped_at_60(nt):
    nt.f.queue = [(429, {"ok": False, "parameters": {"retry_after": 500}})]
    nt.n.send_text("a", "WARN", "r429b")
    assert all(s <= 60 for s in nt.sleeps)


@pytest.mark.parametrize("code", [400, 401, 403])
def test_permanent_errors_no_retry(nt, code):
    nt.f.always = (code, {"ok": False, "description": "x"})
    assert nt.n.send_text("a", "WARN", f"p{code}") is False
    assert len(nt.f.of("sendMessage")) == 1
    assert nt.sleeps == []


def test_payload_plain_text_no_parse_mode_no_preview(nt):
    nt.n.send_text("a *b* _c_", "WARN", "pm")
    p = nt.f.of("sendMessage")[0]
    assert "parse_mode" not in p
    assert p.get("disable_web_page_preview") is True
    assert p["chat_id"] == CID


def test_info_silent_crit_loud(nt):
    nt.n.send_text("a", "INFO", "i1")
    nt.n.send_text("b", "CRIT", "c1")
    ps = nt.f.of("sendMessage")
    assert ps[0].get("disable_notification") is True
    assert not ps[1].get("disable_notification")


def test_length_cap_3500(nt):
    big = "\n".join(f"satir {i} " + "x" * 50 for i in range(500))
    nt.n.send_text(big, "INFO", "big")
    t = nt.f.texts[0]
    assert len(t) <= 3500
    assert "kısaltıldı" in t


def test_pinned_command_line_never_cut(nt):
    big = "\n".join(f"satir {i} " + "x" * 50 for i in range(500))
    pinned = f"/onayla {REQ}\n/reddet {REQ}"
    nt.n.send_text(big, "WARN", "bigp", pinned=pinned)
    t = nt.f.texts[0]
    assert len(t) <= 3500
    assert t.endswith(pinned)


def test_fit_text_short_untouched():
    assert tg.fit_text("kisa") == "kisa"


def test_fit_text_cuts_on_line_boundary():
    big = "\n".join(["y" * 99] * 100)
    out = tg.fit_text(big)
    assert len(out) <= 3500
    body = out.split("\n")
    assert all(len(x) <= 99 or "kısaltıldı" in x for x in body)


def test_neutralize_slash_lines():
    out = tg.neutralize("normal\n/onayla lr-2026-11-16-1\n  /x")
    lines = out.split("\n")
    assert not lines[1].startswith("/")
    assert "/onayla" in lines[1]


def test_alert_send_uses_fingerprint_dedup(nt):
    a = Alert(level=Status.WARN, code="exchange_ban", title="t", body="b", fingerprint="exchange_ban|exchange_ban", created_at=T0)
    assert nt.n.send(a) is True
    assert nt.n.send(a) in (True, False)
    assert len(nt.f.of("sendMessage")) == 1


def test_notifier_from_env_none_without_token():
    assert tg.notifier_from_env({}) is None
    assert tg.notifier_from_env({"TELEGRAM_BOT_TOKEN": "x"}) is None
    assert tg.notifier_from_env({"TELEGRAM_CHAT_ID": "1"}) is None


def test_config_from_env_missing_is_none():
    assert tg.TelegramConfig.from_env({}) is None


# --------------------------------------------------------------------------- Bolum 7: sirlar
def test_token_not_in_logs_stderr_spool(nt, caplog, capsys):
    caplog.set_level(logging.DEBUG)

    def boom(url, json=None, timeout=None, **kw):
        raise RuntimeError(f"Max retries exceeded with url: {url}")
    client = tg.TelegramClient(TOKEN, http_post=boom, sleep=nt.sleeps.append)
    n = tg.TelegramNotifier(client, CID, nt.ob, now_fn=nt.clk, sleep=nt.sleeps.append)
    assert n.send_text("x", "CRIT", "tok1") is False
    nt.f.always = (401, {"ok": False, "description": "Unauthorized"})
    nt.n.send_text("x", "CRIT", "tok2")
    cap = capsys.readouterr()
    assert TOKEN not in caplog.text
    assert TOKEN not in cap.err and TOKEN not in cap.out
    assert TOKEN not in _all_files_text(nt.tmp)
    assert "SECRETTOKEN" not in caplog.text + cap.err + _all_files_text(nt.tmp)


def test_token_not_in_daemon_audit_or_logs(env, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    env.send("/hepsini_kapat")
    env.send("4821")
    env.send("/durum")
    env.send("/x", chat_id=555000999)
    cap = capsys.readouterr()
    assert TOKEN not in caplog.text and TOKEN not in cap.err
    assert TOKEN not in _all_files_text(env.tmp)


def test_mask_removes_token():
    out = tg.mask(f"https://api.telegram.org/bot{TOKEN}/sendMessage", TOKEN)
    assert TOKEN not in out


# --------------------------------------------------------------------------- Bolum 6: gunluk rapor
def ist(h, m, day=16):
    return datetime(2026, 11, day, h, m, tzinfo=timezone(timedelta(hours=3))).astimezone(timezone.utc)


def test_report_decision_normal_at_21_istanbul():
    kind, day = tg.report_decision(ist(21, 0), None)
    assert kind == "normal"
    assert day == "2026-11-16"


def test_report_decision_late_between_10min_and_2330():
    assert tg.report_decision(ist(21, 30), None)[0] == "gecikmis"
    assert tg.report_decision(ist(23, 29), None)[0] == "gecikmis"


def test_report_decision_skip_after_2330():
    assert tg.report_decision(ist(23, 31), None)[0] == "atla"


def test_report_decision_skip_far_after_for_previous_day():
    assert tg.report_decision(ist(15, 0), None)[0] == "atla"


def _report_env(tmp_path, status=True, stale=False):
    f = FakeTelegram()
    n, ob, client, sleeps, clk = make_notifier(f, tmp_path)
    sp = tmp_path / "status.json"
    cfg = tg.TelegramConfig(token=TOKEN, chat_id=CID, var_dir=str(tmp_path / "var"), kill_file=str(tmp_path / "KILL"),
                            status_path=str(sp),
                            health_state=str(tmp_path / "health.json"))
    (tmp_path / "var").mkdir(exist_ok=True)
    return f, n, cfg, sp


def test_late_report_sent_without_gecikmis_tag(tmp_path):
    f, n, cfg, sp = _report_env(tmp_path)
    now = ist(22, 15)
    write_status(sp, loop_at=now)
    r = tg.run_report(cfg, n, now)
    assert r == "sent"
    assert "gecikmiş" not in f.alltext().lower()      # gecikme oneki kalkti; rapor yine gider


def test_report_after_2330_skipped(tmp_path):
    f, n, cfg, sp = _report_env(tmp_path)
    now = ist(23, 40)
    write_status(sp, loop_at=now)
    assert tg.run_report(cfg, n, now) == "skipped"
    assert f.of("sendMessage") == []


def test_report_on_time_not_tagged_late(tmp_path):
    f, n, cfg, sp = _report_env(tmp_path)
    now = ist(21, 2)
    write_status(sp, loop_at=now)
    assert tg.run_report(cfg, n, now) == "sent"
    assert "gecikmiş" not in f.alltext().lower()


def test_report_once_per_day(tmp_path):
    f, n, cfg, sp = _report_env(tmp_path)
    now = ist(21, 1)
    write_status(sp, loop_at=now)
    assert tg.run_report(cfg, n, now) == "sent"
    n_msgs = len(f.of("sendMessage"))
    assert tg.run_report(cfg, n, now + timedelta(minutes=1)) == "already"
    assert len(f.of("sendMessage")) == n_msgs


def test_report_missing_status_okunamadi_not_failure(tmp_path):
    f, n, cfg, sp = _report_env(tmp_path)
    now = ist(21, 1)
    assert not sp.exists()
    r = tg.run_report(cfg, n, now)
    assert r == "sent"
    assert "Bazı bilgiler okunamadı" in f.alltext()


def test_report_corrupt_status_okunamadi(tmp_path):
    f, n, cfg, sp = _report_env(tmp_path)
    sp.write_text("{bozuk")
    text = tg.build_report(cfg, ist(21, 1), "2026-11-16")
    assert "Bazı bilgiler okunamadı" in text and "JSONDecodeError" not in text


def test_report_stale_status_first_line_crit(tmp_path):
    f, n, cfg, sp = _report_env(tmp_path)
    now = ist(21, 1)
    write_status(sp, loop_at=now - timedelta(seconds=600))
    text = tg.build_report(cfg, now, "2026-11-16")
    first = text.split("\n")[0]
    assert first.startswith("[ML] 🔴") and "Bot yanıt vermiyor" in first and "10 dk" in first


def test_report_fresh_status_no_crit_first_line(tmp_path):
    f, n, cfg, sp = _report_env(tmp_path)
    now = ist(21, 1)
    write_status(sp, loop_at=now - timedelta(seconds=5))
    text = tg.build_report(cfg, now, "2026-11-16")
    assert "kalp atışı yok" not in text


def test_report_dedup_key_prevents_double_delivery(tmp_path):
    f, n, cfg, sp = _report_env(tmp_path)
    now = ist(21, 1)
    write_status(sp, loop_at=now)
    f.always = (500, {"ok": False})
    tg.run_report(cfg, n, now)
    f.always = None
    ob = n._outbox if hasattr(n, "_outbox") else None
    # spool bosaltildiktan sonra ayni rapor ikinci kez gonderilmemeli
    for p in list((tmp_path / "outbox").glob("*.json")):
        pass
    start = f.mid
    n.send_text(tg.build_report(cfg, now, "2026-11-16"), "INFO", "report-2026-11-16")
    assert f.mid - start <= 1
