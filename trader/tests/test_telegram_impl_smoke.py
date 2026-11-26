"""Telegram gerceklemesi duman testleri: sahte Telegram (enjekte `http_post`), ag yok."""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import telegram as T

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
TOKEN = "123456:SECRET_TOKEN_abc"
CHAT = 555000111
T0 = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


class Clk:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


class FakeTG:
    def __init__(self):
        self.calls = []
        self.fail = []          # siradaki yanitlar (status, body); bos ise ok
        self.updates = []
        self.mid = 0

    def __call__(self, url, json=None, timeout=None):
        method = url.rsplit("/", 1)[1]
        self.calls.append((method, json))
        if self.fail:
            return self.fail.pop(0)
        if method == "sendMessage":
            self.mid += 1
            return 200, {"ok": True, "result": {"message_id": self.mid}}
        if method == "getUpdates":
            u, self.updates = self.updates, []
            return 200, {"ok": True, "result": u}
        return 200, {"ok": True, "result": True}

    def sent(self, method="sendMessage"):
        return [p for m, p in self.calls if m == method]


def env_for(tmp_path):
    return {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": str(CHAT), "TELEGRAM_VAR_DIR": str(tmp_path / "tg"),
            "KILL_FILE": str(tmp_path / "KILL"), "ENGINE_STATUS_PATH": str(tmp_path / "status.json")}


class _FnClk:
    def __init__(self, fn):
        self._fn = fn

    def now(self):
        return self._fn()


def _ks(cfg, now_fn):
    from trader_engine.killswitch import Killswitch
    return Killswitch(cfg.kill_file, _FnClk(now_fn)) if cfg.kill_file else None


@pytest.fixture
def rig(tmp_path):
    clk, fake, sleeps = Clk(), FakeTG(), []
    env = env_for(tmp_path)
    cfg = T.TelegramConfig.from_env(env)
    client = T.TelegramClient(TOKEN, fake, sleeps.append)
    d = T.TelegramDaemon(cfg, client, now_fn=clk, sleep=sleeps.append, random_code=lambda: "0427",
                         killswitch=_ks(cfg, clk))
    d.rig = type("R", (), {"clk": clk, "fake": fake, "sleeps": sleeps, "tmp": tmp_path, "env": env})
    return d


def msg(d, text, uid=1, chat=CHAT, ctype="private", frm=None, age=0):
    return {"update_id": uid, "message": {"message_id": uid, "date": int(d.rig.clk().timestamp()) - age,
                                          "chat": {"id": chat, "type": ctype}, "from": {"id": frm or chat},
                                          "text": text}}


def last_text(d):
    return d.rig.fake.sent()[-1]["text"]


def set_status(d, **kw):
    st = {"mode": "paper", "kill": True, "kill_state": "flat", "loop_at": "2026-11-16T12:00:00Z"}
    st.update(kw)
    Path(d.cfg.status_path).write_text(json.dumps(st))


def test_notifier_none_without_token():
    assert T.notifier_from_env({}) is None


def test_send_requires_dedup_and_ok_only(tmp_path):
    fake, clk = FakeTG(), Clk()
    n = T.notifier_from_env(env_for(tmp_path), fake, clk, lambda s: None)
    with pytest.raises(ValueError):
        n.send_text("x", "INFO", "")
    assert n.send_text("merhaba", "INFO", "k1") is True
    assert n.send_text("merhaba", "INFO", "k1") is True          # cift teslim yok
    assert len(fake.sent()) == 1
    fake.fail = [(500, {})] * 5
    assert n.send_text("b", "WARN", "k2") is False                # spool'a dustu = False
    assert len(n.outbox.list()) == 1
    assert n.send_text("b", "WARN", "k2") is True                 # dogrudan basarili, spool temizlenir
    assert n.outbox.list() == []


def test_retry_schedule_and_permanent(tmp_path):
    fake, clk, sl = FakeTG(), Clk(), []
    n = T.notifier_from_env(env_for(tmp_path), fake, clk, sl.append)
    fake.fail = [(500, {}), (429, {"parameters": {"retry_after": 7}})]
    assert n.send_text("a", "CRIT", "k") is True
    assert sl == [2, 7]
    fake.calls.clear()
    fake.fail = [(403, {"description": "x"})]
    assert n.send_text("a", "CRIT", "k9") is False
    assert len(fake.sent()) == 1                                  # kalici hata: yeniden deneme yok


def test_token_never_leaks(tmp_path, caplog):
    def boom(url, json=None, timeout=None):
        raise RuntimeError(url)
    n = T.notifier_from_env(env_for(tmp_path), boom, Clk(), lambda s: None)
    assert n.send_text("a", "WARN", "k") is False
    spooled = "".join(p.read_text() for p in n.outbox.list())
    assert TOKEN not in spooled and TOKEN not in caplog.text


def test_fit_text_pins_command():
    body = "\n".join(f"satir {i}" for i in range(2000))
    out = T.fit_text(body, "/durum")
    assert len(out) <= T.MAX_TEXT and out.endswith("/durum") and "kısaltıldı" in out
    assert " /gizli" in T.fit_text("/gizli")


def test_spool_expired_approval_not_sent_and_drain(tmp_path):
    fake, clk = FakeTG(), Clk()
    n = T.notifier_from_env(env_for(tmp_path), fake, clk, lambda s: None)
    fake.fail = [(500, {})] * 10
    exp = clk().timestamp() + 60
    n.send_text("onay", "WARN", "rid1", expires_at=exp)
    n.send_text("normal", "CRIT", "c1")
    assert len(n.outbox.list()) == 2
    clk.t += timedelta(seconds=120)
    fake.calls.clear()
    fake.fail = []
    n.outbox.drain(n.client, CHAT, lambda s: None)
    texts = [p["text"] for p in fake.sent()]
    assert texts == ["[ML] normal"] and n.outbox.list() == []


def test_unauthorized_and_group_ignored(rig):
    d = rig
    d.process_updates([msg(d, "/durum", 1, chat=999), msg(d, "/durum", 2, ctype="group"),
                       msg(d, "/durum", 3, frm=42)])
    assert d.rig.fake.sent() == []
    rows = [json.loads(x) for x in d._audit_p.read_text().splitlines()]
    assert len(rows) == 3 and all(r["event"] == "unauthorized" for r in rows)
    assert all("999" not in json.dumps(r) or r["chat_tail"] == "999" for r in rows)


def test_kill_two_step_bare_code(rig):
    d = rig
    d.process_updates([msg(d, "/hepsini_kapat", 1)])
    assert "0427" in last_text(d) and not d.killswitch.active()
    d.process_updates([msg(d, "/onay 0427", 2)])
    assert not d.killswitch.active()                              # /onay KOD tanimsiz komut
    d.process_updates([msg(d, "Hepsini  Kapat", 3)])
    d.process_updates([msg(d, "0427", 4)])
    assert d.killswitch.active()
    info = d.killswitch.info()
    assert info["by"].startswith("telegram:") and info["reason"] == "user_cmd"
    d.process_updates([msg(d, "0427", 5)])
    assert "Bekleyen onay yok" in last_text(d)
    assert "0427" not in d._pending_p.read_text() if d._pending_p.exists() else True


def test_kill_wrong_code_and_ttl(rig):
    d = rig
    d.process_updates([msg(d, "/hepsini_kapat", 1), msg(d, "1111", 2)])
    assert not d.killswitch.active() and not d._pending_p.exists()
    d.process_updates([msg(d, "/hepsini_kapat", 3)])
    d.rig.clk.t += timedelta(seconds=121)
    d.process_updates([msg(d, "0427", 4)])
    assert not d.killswitch.active() and "Süre doldu" in last_text(d)
    d.process_updates([msg(d, "/hepsini_kapat", 5)])
    d.rig.clk.t += timedelta(seconds=119)
    d.process_updates([msg(d, "0427", 6)])
    assert d.killswitch.active()


def test_stale_and_duplicate_update(rig):
    d = rig
    d.process_updates([msg(d, "/hepsini_kapat", 1, age=121)])
    assert "İşlenmedi" in last_text(d) and not d._pending_p.exists()
    d.process_updates([msg(d, "/yardim", 2), msg(d, "/yardim", 2)])
    assert len([p for p in d.rig.fake.sent() if "durdur" in p["text"]]) == 1
    assert d._get_offset() == 3


def test_devam_rules(rig):
    d = rig
    d.killswitch.set("telegram:111", "user_cmd")
    set_status(d, kill_state="exiting", mode="paper")
    d.process_updates([msg(d, "/devam", 1)])
    assert "Kapanış" in last_text(d) and not d._pending_p.exists()
    set_status(d, kill_state="flat", mode="live")
    d.killswitch.set("engine", "daily_loss")
    d.process_updates([msg(d, "/devam", 2)])
    assert "sunucuda" in last_text(d)
    d.killswitch.set("telegram:111", "user_cmd")
    d.process_updates([msg(d, "/devam", 3)])
    assert "0427" in last_text(d) and d.killswitch.active()
    d.process_updates([msg(d, "0427", 4)])
    assert not d.killswitch.active()
    d.process_updates([msg(d, "/devam", 5)])
    assert "etkin değil" in last_text(d)
    d.process_updates([msg(d, "/durdur", 6)])
    assert "Desteklenmiyor" in last_text(d)


def test_devam_unreadable_status_fail_closed(rig):
    d = rig
    d.killswitch.set("telegram:111", "user_cmd")
    d.process_updates([msg(d, "/devam", 1)])
    assert d.killswitch.active() and not d._pending_p.exists()


def test_kaldirilan_ders_komutlari_islem_yapmaz(rig):
    """Ders sistemi kaldirildi (25.11): /ders, /onayla, /reddet tek satirla yanitlanir; alt surec/depo yok."""
    d = rig
    d.process_updates([msg(d, "/onayla lr-2026-11-16-3", 1), msg(d, "/reddet lr-2026-11-16-3", 2), msg(d, "/ders", 3)])
    sent = [p["text"] for p in d.rig.fake.sent()]
    assert len(sent) == 3 and all("kaldırıldı" in x and "/ml1" in x for x in sent)


def cb(d, data, uid, mid=77, text="Oneri"):
    return {"update_id": uid, "callback_query": {"id": f"c{uid}", "from": {"id": CHAT}, "data": data,
            "message": {"message_id": mid, "chat": {"id": CHAT, "type": "private"}, "text": text}}}


def test_eski_ders_dugmeleri_islem_yapmaz(rig):
    d = rig
    exp = int(d.rig.clk().timestamp()) + 600
    d.process_updates([cb(d, f"ok:lr-2026-11-16-3:{exp}", 1), cb(d, f"ev:lr-2026-11-16-3:{exp}", 2)])
    assert d.rig.fake.sent("editMessageText") == []
    ans = d.rig.fake.sent("answerCallbackQuery")
    assert len(ans) == 2 and all("kaldirildi" in a["text"] for a in ans)


def test_report_schedule():
    tr = lambda h, m, day=16: datetime(2026, 11, day, h, m, tzinfo=T.TR).astimezone(UTC)
    assert T.report_decision(tr(21, 5), None) == ("normal", "2026-11-16")
    assert T.report_decision(tr(22, 0), None)[0] == "gecikmis"
    assert T.report_decision(tr(23, 29), None)[0] == "gecikmis"
    assert T.report_decision(tr(23, 31), None)[0] == "atla"
    assert T.report_decision(tr(21, 5), "2026-11-16")[0] == "atla"
    assert T.report_decision(tr(9, 0, 17), None)[0] == "atla"


def test_report_run_and_no_late_tag(tmp_path):
    fake = FakeTG()
    clk = Clk()
    clk.t = datetime(2026, 11, 16, 22, 0, tzinfo=T.TR).astimezone(UTC)
    env = env_for(tmp_path)
    cfg = T.TelegramConfig.from_env(env)
    n = T.notifier_from_env(env, fake, clk, lambda s: None)
    assert T.run_report(cfg, n, clk()) == "sent"
    assert fake.sent()[0]["text"].startswith("[ML] 🌙 Günlük özet") and "gecikmiş" not in fake.sent()[0]["text"]
    assert T.run_report(cfg, n, clk()) == "already"


def test_script_send_and_report(tmp_path, capsys):
    sys.path.insert(0, str(ROOT / "scripts"))
    import telegram_run as TR
    fake = FakeTG()
    env = env_for(tmp_path)
    assert TR.main(["send", "--severity", "CRIT", "--dedup-key", "h:1", "birim"], env=env, http_post=fake) == 0
    assert fake.sent()[0]["text"] == "[ML] birim"
    assert TR.main(["send", "--dedup-key", "h:1", "birim"], env={}, http_post=fake) == 1
    assert TOKEN not in capsys.readouterr().out
