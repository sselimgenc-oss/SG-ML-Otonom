"""WP-B6 Telegram duraklatma duman testleri (11 §9.5): /durdur, /devam katmanlari, /durum satiri."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import telegram as T
from trader_engine.clock import SimClock
from trader_engine.killswitch import Killswitch
from trader_engine.pause import EntryPause

UTC = timezone.utc
CHAT = 555000111
T0 = datetime(2026, 12, 30, 10, 0, tzinfo=UTC)


class Clk:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


class FakeTG:
    def __init__(self):
        self.calls = []

    def __call__(self, url, json=None, timeout=None):
        m = url.rsplit("/", 1)[1]
        self.calls.append((m, json))
        if m == "sendMessage":
            return 200, {"ok": True, "result": {"message_id": len(self.calls)}}
        return 200, {"ok": True, "result": []}

    def texts(self):
        return [p["text"] for m, p in self.calls if m == "sendMessage"]


class _Fn:
    def __init__(self, fn):
        self.fn = fn

    def now(self):
        return self.fn()


@pytest.fixture
def rig(tmp_path):
    clk, fake = Clk(), FakeTG()
    cfg = T.TelegramConfig(token="1:tok", chat_id=CHAT, var_dir=str(tmp_path / "tg"), kill_file=str(tmp_path / "KILL"),
                           status_path=str(tmp_path / "status.json"))
    ks = Killswitch(cfg.kill_file, _Fn(clk))
    pauses = {b: EntryPause(str(tmp_path / f"PAUSE.{b}"), _Fn(clk), audit_path=str(tmp_path / f"a.{b}.jsonl"))
              for b in ("learner", "twin")}
    d = T.TelegramDaemon(cfg, T.TelegramClient("1:tok", fake, lambda s: None), now_fn=clk,
                         sleep=lambda s: None, random_code=lambda: "0427",
                         killswitch=ks, pauses=pauses)
    d.r = type("R", (), {"clk": clk, "fake": fake, "tmp": tmp_path, "pauses": pauses})
    return d


def msg(d, text, uid, age=0):
    return {"update_id": uid, "message": {"message_id": uid, "date": int(d.r.clk().timestamp()) - age,
                                          "chat": {"id": CHAT, "type": "private"}, "from": {"id": CHAT}, "text": text}}


def say(d, text, uid):
    d.process_updates([msg(d, text, uid)])
    return d.r.fake.texts()[-1]


def status(d, **kw):
    st = {"mode": "paper", "kill_state": "flat"}
    st.update(kw)
    Path(d.cfg.status_path).write_text(json.dumps(st))


def test_durdur_two_steps_all_bots(rig):
    d = rig
    assert "0427" in say(d, "/durdur", 1)
    assert not any(p.active() for p in d.r.pauses.values())
    assert "Yeni işlem açma durduruldu" in say(d, "0427", 2) and "/hepsini_kapat" in d.r.fake.texts()[-1]
    for p in d.r.pauses.values():
        (h,) = p.holds()
        assert h.reason == "user_cmd" and h.by == "telegram:111"
    assert "zaten" in say(d, "/durdur", 3)          # idempotent, kod yok
    assert not d._pending_p.exists()


def test_durdur_ttl_boundaries(rig):
    d = rig
    for age, ok in ((119, True), (120, True), (121, False)):
        for p in d.r.pauses.values():
            p.remove("user_cmd", "t")
        d.r.clk.t = T0
        say(d, "/durdur", 10 + age)
        d.r.clk.t = T0 + timedelta(seconds=age)
        d.process_updates([msg(d, "0427", 1000 + age)])
        assert d.r.pauses["learner"].active() is ok, age


def test_durdur_wrong_code_cancels_and_works_with_kill(rig):
    d = rig
    d.killswitch.set("telegram:111", "user_cmd")
    say(d, "/durdur", 1)
    say(d, "9999", 2)
    assert not d.r.pauses["learner"].active() and not d._pending_p.exists()
    say(d, "/durdur", 3)
    say(d, "0427", 4)
    assert d.r.pauses["learner"].active() and d.killswitch.active()


def test_devam_one_layer_per_call(rig):
    d = rig
    status(d, mode="paper")
    d.killswitch.set("telegram:111", "user_cmd")
    for p in d.r.pauses.values():
        p.add("user_cmd", "telegram:111")
    t = say(d, "/devam", 1)
    assert "Acil durdurma kaldırılacak" in t and "duraklatma" in t
    assert "learner: user_cmd — girişler hâlâ kapalı" in say(d, "0427", 2)
    assert not d.killswitch.active() and d.r.pauses["learner"].active()
    assert "duraklatma" in say(d, "/devam", 3)
    t = say(d, "0427", 4)
    assert "learner: girişler açık" in t and "twin: girişler açık" in t
    assert not any(p.active() for p in d.r.pauses.values())
    assert "etkin değil" in say(d, "/devam", 5)


def test_devam_origin_rule_and_drawdown_review(rig):
    d = rig
    d.r.pauses["learner"].add("drawdown_review", "engine:rk1")
    d.r.pauses["twin"].add("unknown_position", "engine:reconcile")
    t = say(d, "/devam", 1)
    assert "kaldırılamaz" in t and "drawdown_review" in t and not d._pending_p.exists()
    d.r.pauses["learner"].add("user_cmd", "telegram:111")
    say(d, "/devam", 2)
    t = say(d, "0427", 3)
    assert "learner: drawdown_review — girişler hâlâ kapalı" in t and "twin: unknown_position" in t
    assert [h.reason for h in d.r.pauses["learner"].holds()] == ["drawdown_review"]
    assert d.r.pauses["twin"].active()
    assert "kaldırılamaz" in say(d, "/devam", 4)


def test_devam_kill_layer_still_refuses_exiting_and_live_rules(rig):
    d = rig
    d.r.pauses["learner"].add("user_cmd", "telegram:111")
    d.killswitch.set("telegram:111", "user_cmd")
    status(d, kill_state="exiting")
    assert "Kapanış" in say(d, "/devam", 1)
    assert d.r.pauses["learner"].active()


def test_status_line_and_legacy_durdur(rig, tmp_path):
    d = rig
    status(d)
    say(d, "/durdur", 1)
    say(d, "0427", 2)
    say(d, "/durum", 3)
    t = d.r.fake.texts()[-1]
    assert "ana bot: yeni işlemler duraklatıldı — senin /durdur komutun (Telegram'dan, 30.12 13:00)" in t
    d2 = T.TelegramDaemon(d.cfg, d.client, now_fn=d.r.clk, killswitch=d.killswitch)
    d2.r = d.r
    d2.process_updates([msg(d2, "/durdur", 9)])
    assert "Desteklenmiyor" in d.r.fake.texts()[-1]


# ---------------------------------------------------------------- F1 build_pauses == motor yollari
def test_build_pauses_match_engine_paths_learner_only(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    import telegram_run as TR
    from trader_engine.config import load_engine_config
    monkeypatch.chdir(tmp_path)                                  # cwd farkli: yollar yine kok-bagimli
    ps = TR.build_pauses({}, lambda: T0)
    assert list(ps) == ["learner"]                               # DD-12: ikiz kaldirildi
    for bot in ("learner",):
        cfg = load_engine_config(root / "config" / "engine.base.json", root / "config" / f"engine.{bot}.json")
        want_pause = str(root / (cfg.pause_file + "." + bot))
        want_audit = str(root / cfg.path("pause_audit.jsonl"))
        assert ps[bot].path == want_pause and Path(ps[bot].path).is_absolute()
        assert ps[bot].audit_path == want_audit and ps[bot].bot == bot
    ps2 = TR.build_pauses({"PAUSE_BOTS": "learner", "PAUSE_FILE": "/x/PAUSE", "ENGINE_VAR_DIR": "/x/var"}, lambda: T0)
    assert list(ps2) == ["learner"] and ps2["learner"].path == "/x/PAUSE.learner"
    assert ps2["learner"].audit_path == "/x/var/learner/pause_audit.jsonl"


def test_production_entrypause_durdur_devam_end_to_end(rig):
    status(rig)
    assert "Yeni işlem açma durduruldu" in (say(rig, "/durdur", 1) and say(rig, "0427", 2))
    for b, p in rig.r.pauses.items():
        assert p.active() and p.holds()[0].reason == "user_cmd" and p.holds()[0].by.startswith("telegram:")
    say(rig, "/devam", 3)
    assert "kaldırıldı" in say(rig, "0427", 4)
    assert not any(p.active() for p in rig.r.pauses.values())
    rows = [json.loads(x) for p in rig.r.pauses.values() for x in Path(p.audit_path).read_text().splitlines()]
    assert sorted(r["op"] for r in rows) == ["add", "add", "remove", "remove"]


# ---------------------------------------------------------------- F2
def test_durdur_confirm_reports_per_bot_failure_and_still_pauses_other(rig):
    status(rig)
    orig = rig.pauses["learner"].add

    def boom(*a, **k):
        raise OSError("disk")
    rig.pauses["learner"].add = boom
    say(rig, "/durdur", 1)
    t = say(rig, "0427", 2)
    assert "learner" in t and "YAZILAMADI" in t
    assert rig.pauses["twin"].active() and not rig.pauses["learner"].active()
    rig.pauses["learner"].add = orig


def test_devam_pause_removal_failure_per_bot_not_silent(rig):
    status(rig)
    for p in rig.pauses.values():
        p.add("user_cmd", "x")
    rig.pauses["learner"].remove = lambda *a, **k: (_ for _ in ()).throw(OSError("ro"))
    say(rig, "/devam", 1)
    t = say(rig, "0427", 2)
    assert "learner" in t and "kaldırılamadı" in t
    assert not rig.pauses["twin"].active()


# ---------------------------------------------------------------- F3
def test_report_has_per_bot_pause_line(rig, tmp_path):
    rig.pauses["learner"].add("drawdown_review", "engine:rk1")
    secs = T.default_sections(rig.cfg, T0, "2026-12-30", rig.pauses)
    assert "ana bot: yeni işlemler duraklatıldı — risk kademesi incelemesi bekliyor (motor tarafından, 30.12 13:00)" in secs["Duraklatma"]()
    status(rig, loop_at=T0.strftime("%Y-%m-%dT%H:%M:%SZ"), entries_open=True)
    out = T.build_report(rig.cfg, T0, "2026-12-30", {"Duraklatma": secs["Duraklatma"]})
    assert "Yeni işlemler duraklatıldı: risk kademesi incelemesi bekliyor." in out
    assert "ikiz bot" not in out and "drawdown_review" not in out
    assert "Duraklatma" not in T.default_sections(rig.cfg, T0, "2026-12-30")


# ---------------------------------------------------------------- F5
def test_pending_pause_devam_refused_when_kill_set_before_confirm(rig):
    status(rig)
    for p in rig.pauses.values():
        p.add("user_cmd", "x")
    say(rig, "/devam", 1)
    rig.killswitch.set(by="cli", reason="manual")
    t = say(rig, "0427", 2)
    assert "Acil durdurma etkin" in t
    assert all(p.active() for p in rig.pauses.values()) and rig.killswitch.active()


# ---------------------------------------------------------------- F6
def test_pause_remove_appears_once_with_pause_user():
    import ast
    root = Path(__file__).resolve().parents[1]
    calls = []
    for f in [root / "src/trader_core/telegram.py", *sorted((root / "scripts").glob("*.py"))]:
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "remove"
                    and not (isinstance(n.func.value, ast.Name) and n.func.value.id in ("os", "files"))):   # files: list.remove
                calls.append((f.name, ast.unparse(n.args[0]) if n.args else None))
    # 12 (RK-1) ile guncellendi: /kademe_devam onayi drawdown_review tutusunu (kademe satiri yazildiktan SONRA) kaldirir
    # capital_latch (kullanici karari): /devam ayni kodla ana para kilidini de kaldirir
    assert sorted(calls) == sorted([("telegram.py", "PAUSE_USER"), ("telegram.py", "PAUSE_LATCH"),
                                    ("telegram.py", "'drawdown_review'")]), calls


# ---------------------------------------------------------------- F9
def test_devam_refusal_drawdown_review_no_missing_command(rig):
    status(rig)
    rig.pauses["learner"].add("drawdown_review", "engine:rk1")
    t = say(rig, "/devam", 1)
    assert "kaldırılamaz" in t and "drawdown_review" in t and "/kademe_devam" not in t and "yalnız sunucuda" not in t


def test_durdur_confirm_unreadable_file_says_so(rig):
    status(rig)
    Path(rig.pauses["learner"].path).write_text("{bozuk")
    say(rig, "/durdur", 1)
    t = say(rig, "0427", 2)
    assert "learner" in t and "okunamıyor" in t and "user_cmd" in t
    assert rig.pauses["twin"].active()


# ---------------------------------------------------------------- /durum: bilinmeyen ve bayat durum (V-04)
def test_durum_fresh_unknown_and_stale(rig):
    d = rig
    status(d, loop_at=T0.strftime("%Y-%m-%dT%H:%M:%SZ"), entries_open=True, open_positions=[])
    fresh = say(d, "/durum", 1)
    assert fresh.splitlines()[0] == "[ML] Anlık durum (deneme parası)" and "Bot çalışıyor." in fresh
    assert "Son bilinen" not in fresh and "yanıt vermiyor" not in fresh and "doğrulanamadı" not in fresh
    status(d, entries_open=True, open_positions=[])                       # loop_at yok: zaman okunamadi -> "Bot çalışıyor." yazilmaz
    bilinmiyor = say(d, "/durum", 2)
    assert "Bot çalışıyor." not in bilinmiyor
    assert "Bot durumu doğrulanamadı (son sinyal zamanı okunamadı)." in bilinmiyor
    status(d, loop_at=(T0 - timedelta(minutes=180)).strftime("%Y-%m-%dT%H:%M:%SZ"), entries_open=True, open_positions=[])
    eski = say(d, "/durum", 3).splitlines()
    assert eski[0] == "[ML] Son bilinen durum · 180 dk önce (deneme parası)"
    assert eski[1] == "Bot yanıt vermiyor! (son sinyal 180 dk önce)"                 # uyari 2. satirda, rakamlardan once
    assert not any("Bot çalışıyor." in x for x in eski)
