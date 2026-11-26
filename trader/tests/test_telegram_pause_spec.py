"""WP-B6 bagimsiz sartname testi: Telegram `/durdur` ve `/devam` (docs/motor/11-canli-broker.md §9.5 +
docs/telegram-spec.md). Gerceklemeye (telegram.py / telegram_run.py) BAKILMADAN yazildi. Ag yok; sahte Telegram.

Duzenek tests/test_telegram_spec.py yardimcilarini yeniden kullanir (FakeTelegram, msg, write_status, ...).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trader_core import telegram as tg  # noqa: E402
from trader_engine.clock import SimClock  # noqa: E402
from trader_engine.killswitch import Killswitch  # noqa: E402
from trader_engine.pause import EntryPause  # noqa: E402

from test_telegram_spec import (CID, TOKEN, Clk, FakeTelegram, T0, _audit_text, _find, _ks_for, _next,  # noqa: E402
                                 code_of, msg, write_status)

OTHER_CHAT = 555000999
BOTS = ("learner", "twin")
SUFFIX = str(CID)[-3:]                 # "789"
BY = f"telegram:{SUFFIX}"
CLOCK0 = SimClock(T0)


class PEnv:
    pass


def hold_reasons(e, bot="learner"):
    return [h.reason for h in EntryPause(e.pause_paths[bot], CLOCK0).holds()]


def holds_of(e, bot="learner"):
    return EntryPause(e.pause_paths[bot], CLOCK0).holds()


def pause_audit_rows(tmp: Path):
    rows = []
    for p in tmp.rglob("pause_audit.jsonl"):
        rows += [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    return rows


@pytest.fixture
def penv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    e = PEnv()
    e.tmp = tmp_path
    e.fake = FakeTelegram()
    e.clk = Clk()
    e.clk_obj = type("_C", (), {"now": staticmethod(lambda: e.clk())})()     # EntryPause icin Clock (daemon saatiyle ayni)
    e.sleeps = []
    e.calls = []
    e.kill_file = str(tmp_path / "KILL")
    e.status_path = str(tmp_path / "status.json")
    e.pause_paths = {b: str(tmp_path / "shared" / f"PAUSE.{b}") for b in BOTS}
    # WP-B6 F4: FilePause silindi; daemon'a uretimdeki EntryPause siniflari enjekte edilir (bot -> EntryPause, §9.2 yolu).
    e.cfg = tg.TelegramConfig(token=TOKEN, chat_id=CID, var_dir=str(tmp_path / "var"), kill_file=e.kill_file,
                              status_path=e.status_path,
                              health_state=str(tmp_path / "health.json"))
    (tmp_path / "var").mkdir()
    e.client = tg.TelegramClient(TOKEN, http_post=e.fake.post, sleep=e.sleeps.append)
    e.ks = Killswitch(e.kill_file, SimClock(T0))
    e.pauses = {b: EntryPause(p, e.clk_obj, bot=b) for b, p in e.pause_paths.items()}
    e.new_daemon = lambda **kw: tg.TelegramDaemon(
        e.cfg, e.client, now_fn=e.clk, sleep=e.sleeps.append,
        random_code=kw.pop("random_code", lambda: "4821"), pauses=kw.pop("pauses", e.pauses),
        killswitch=kw.pop("killswitch", _ks_for(e.cfg, e.clk)), **kw)
    e.d = e.new_daemon()
    e.clk.advance(2)
    write_status(e.status_path)
    e.send = lambda text, uid=None, **kw: e.d.process_updates([msg(uid or _next(), text, kw.pop("date", e.clk()), **kw)])
    e.last = lambda: e.fake.texts[-1] if e.fake.texts else ""
    e.preload = lambda reason, by="x", note="", bot="learner": EntryPause(e.pause_paths[bot], CLOCK0).add(reason, by=by, note=note)
    return e


def durdur(e, code="4821"):
    e.send("/durdur")
    e.send(code)


def devam(e, code="4821"):
    e.send("/devam")
    e.send(code)


def kill_active(e):
    return Path(e.kill_file).exists()


# =====================================================================================================
# /durdur — iki adim, TTL, tek kullanim, kimlik
# =====================================================================================================
class TestDurdur:
    def test_step1_sends_code_and_pauses_nothing(self, penv):
        penv.send("/durdur")
        assert code_of(penv.fake.alltext()) == "4821"
        for b in BOTS:
            assert hold_reasons(penv, b) == []
        assert not kill_active(penv)

    def test_not_unsupported_anymore(self, penv):
        penv.send("/durdur")
        assert "desteklenm" not in penv.fake.alltext().lower()

    def test_code_adds_user_cmd_to_every_bot(self, penv):
        durdur(penv)
        for b in BOTS:
            (h,) = holds_of(penv, b)
            assert h.reason == "user_cmd" and h.by == BY
            assert h.at is not None
        assert not kill_active(penv)                       # KILL kurulmaz: pozisyonlar yasar

    def test_reply_text(self, penv):
        durdur(penv)
        t = penv.last()
        assert "Yeni işlem açma durduruldu" in t
        assert "Açık işlemler stoplarıyla açık kalır" in t
        assert "/hepsini_kapat" in t

    def test_pending_json_has_action_pause_and_no_plain_code(self, penv):
        penv.send("/durdur")
        p = _find(penv.tmp, "pending.json")
        assert p is not None
        txt = p.read_text()
        assert re.search(r'"action"\s*:\s*"pause"', txt)
        assert "4821" not in txt and "4821" not in _audit_text(penv.tmp)

    def test_ttl_119_accepted(self, penv):
        penv.send("/durdur")
        penv.clk.advance(119)
        penv.send("4821")
        assert hold_reasons(penv) == ["user_cmd"]

    def test_ttl_120_boundary(self, penv):
        # SPEC-AMBIGUOUS: "120 sn icinde" sinir degeri; bayatlik kurali `fark > 120` stale sayar, bu yuzden tam 120
        # gecerli kabul edildi (suresi `> 120`de dolar).
        penv.send("/durdur")
        penv.clk.advance(120)
        penv.send("4821")
        assert hold_reasons(penv) == ["user_cmd"]

    def test_ttl_121_rejected(self, penv):
        penv.send("/durdur")
        penv.clk.advance(121)
        penv.send("4821")
        assert hold_reasons(penv) == []
        assert not Path(penv.pause_paths["learner"]).exists()

    def test_expired_reply_says_expired(self, penv):
        penv.send("/durdur")
        penv.clk.advance(121)
        penv.send("4821")
        assert "süre doldu" in penv.last().lower() or "sure doldu" in penv.last().lower()

    def test_wrong_code_cancels(self, penv):
        penv.send("/durdur")
        penv.send("0000")
        penv.send("4821")
        assert hold_reasons(penv) == []

    def test_code_from_other_chat_does_nothing(self, penv):
        penv.send("/durdur")
        penv.send("4821", chat_id=OTHER_CHAT)
        assert hold_reasons(penv) == []

    def test_code_single_use(self, penv):
        durdur(penv)
        EntryPause(penv.pause_paths["learner"], CLOCK0).remove("user_cmd", by="cli")
        penv.send("4821")
        assert hold_reasons(penv) == []                    # ikinci kullanim yurutulmez

    def test_bare_code_without_pending_does_nothing(self, penv):
        penv.send("4821")
        assert hold_reasons(penv) == []
        assert "Bekleyen onay yok" in penv.last()

    def test_command_form_not_accepted(self, penv):
        penv.send("/durdur")
        penv.send("/onay 4821")
        assert hold_reasons(penv) == []

    def test_code_with_extra_text_not_accepted(self, penv):
        penv.send("/durdur")
        penv.send("4821 tamam")
        assert hold_reasons(penv) == []

    def test_new_pending_invalidates_old(self, penv):
        codes = iter(["1111", "2222"])
        d = penv.new_daemon(random_code=lambda: next(codes))
        penv.clk.advance(2)
        d.process_updates([msg(_next(), "/durdur", penv.clk())])
        d.process_updates([msg(_next(), "/hepsini_kapat", penv.clk())])
        d.process_updates([msg(_next(), "1111", penv.clk())])
        assert hold_reasons(penv) == [] and not kill_active(penv)

    def test_pending_survives_restart_within_ttl(self, penv):
        penv.send("/durdur")
        d2 = penv.new_daemon()
        penv.clk.advance(2)
        d2.process_updates([msg(_next(), "4821", penv.clk())])
        assert hold_reasons(penv) == ["user_cmd"]

    def test_pending_after_restart_expired(self, penv):
        penv.send("/durdur")
        d2 = penv.new_daemon()
        penv.clk.advance(130)
        d2.process_updates([msg(_next(), "4821", penv.clk())])
        assert hold_reasons(penv) == []

    def test_foreign_chat_cannot_pause(self, penv):
        penv.send("/durdur", chat_id=OTHER_CHAT)
        assert code_of(penv.fake.alltext()) is None
        assert hold_reasons(penv) == []

    def test_group_chat_cannot_pause(self, penv):
        penv.send("/durdur", chat_type="supergroup")
        assert hold_reasons(penv) == []

    def test_stale_command_not_executed(self, penv):
        penv.send("/durdur", date=penv.clk() - timedelta(seconds=130))
        assert code_of(penv.fake.alltext()) is None
        assert hold_reasons(penv) == []

    def test_accepted_while_kill_active(self, penv):
        penv.ks.set(by="me", reason="manual")
        durdur(penv)
        assert hold_reasons(penv) == ["user_cmd"]
        assert kill_active(penv)                           # KILL'e dokunulmaz

    def test_idempotent_when_already_paused_reports_who_and_when(self, penv):
        durdur(penv)
        first = holds_of(penv)[0]
        penv.clk.advance(300)
        penv.send("/durdur")
        # SPEC-AMBIGUOUS: "Zaten varsa idempotent yanici (kim, ne zaman)" — yanitin 1. adimda mi onayda mi geldigi
        # belirsiz; kod gelirse ikinci adim da surulur ve yanitlardan herhangi biri taranir.
        c = code_of(penv.last())
        if c:
            penv.send(c)
        txt = penv.fake.alltext()
        assert BY in txt or SUFFIX in txt
        assert first.at[:10] in txt or first.at[:16] in txt
        assert holds_of(penv)[0] == first                 # ilk kokenle degismedi
        assert hold_reasons(penv) == ["user_cmd"]

    def test_twin_unaffected_by_other_reason_but_gets_user_cmd(self, penv):
        penv.preload("drawdown_review", by="engine:rk1", bot="learner")
        durdur(penv)
        assert sorted(hold_reasons(penv, "learner")) == ["drawdown_review", "user_cmd"]
        assert hold_reasons(penv, "twin") == ["user_cmd"]

    def test_audit_log_written_for_command(self, penv):
        durdur(penv)
        assert "durdur" in _audit_text(penv.tmp)

    def test_pause_audit_rows_for_each_bot(self, penv):
        durdur(penv)
        rows = [r for r in pause_audit_rows(penv.tmp) if r["op"] == "add"]
        assert len(rows) == len(BOTS)
        assert all(r["reason"] == "user_cmd" and r["by"] == BY for r in rows)


# =====================================================================================================
# /devam — tek katman, koken kurali, drawdown_review reddi
# =====================================================================================================
class TestDevamPauseLayer:
    def test_two_step_removes_user_cmd_on_every_bot(self, penv):
        for b in BOTS:
            penv.preload("user_cmd", by=BY, bot=b)
        penv.send("/devam")
        assert code_of(penv.fake.alltext()) == "4821"
        for b in BOTS:
            assert hold_reasons(penv, b) == ["user_cmd"]              # 1. adimda kalkmaz
        penv.send("4821")
        for b in BOTS:
            assert hold_reasons(penv, b) == []
            assert not Path(penv.pause_paths[b]).exists()

    def test_reply_says_entries_open(self, penv):
        penv.preload("user_cmd", by=BY)
        devam(penv)
        assert "girişler açık" in penv.last()

    def test_remove_audited_with_telegram_by(self, penv):
        penv.preload("user_cmd", by=BY)
        devam(penv)
        rows = [r for r in pause_audit_rows(penv.tmp) if r["op"] == "remove"]
        assert rows and all(r["reason"] == "user_cmd" and r["by"] == BY for r in rows)

    def test_ttl_boundaries(self, penv):
        penv.preload("user_cmd", by=BY)
        penv.send("/devam")
        penv.clk.advance(121)
        penv.send("4821")
        assert hold_reasons(penv) == ["user_cmd"]
        penv.send("/devam")
        penv.clk.advance(119)
        penv.send("4821")
        assert hold_reasons(penv) == []

    def test_wrong_code_keeps_pause(self, penv):
        penv.preload("user_cmd", by=BY)
        penv.send("/devam")
        penv.send("0000")
        penv.send("4821")
        assert hold_reasons(penv) == ["user_cmd"]

    def test_only_user_cmd_removed_drawdown_review_stays(self, penv):
        penv.preload("user_cmd", by=BY)
        penv.preload("drawdown_review", by="engine:rk1", note="peak=1100 equity=870")
        devam(penv)
        assert hold_reasons(penv) == ["drawdown_review"]
        t = penv.last()
        assert "learner: drawdown_review" in t and "girişler hâlâ kapalı" in t

    def test_remaining_holds_listed_per_bot(self, penv):
        penv.preload("user_cmd", by=BY, bot="learner")
        penv.preload("user_cmd", by=BY, bot="twin")
        penv.preload("late_fill", by="engine:reconcile", bot="twin")
        devam(penv)
        t = penv.last()
        assert "twin: late_fill" in t and "girişler hâlâ kapalı" in t
        assert hold_reasons(penv, "learner") == []
        assert hold_reasons(penv, "twin") == ["late_fill"]

    def test_user_cmd_only_on_one_bot_still_removed_there(self, penv):
        penv.preload("user_cmd", by=BY, bot="twin")
        devam(penv)
        assert hold_reasons(penv, "twin") == []

    def test_second_devam_after_drawdown_review_refuses(self, penv):
        penv.preload("user_cmd", by=BY)
        penv.preload("drawdown_review", by="engine:rk1")
        devam(penv)
        n = len(penv.fake.texts)
        penv.send("/devam")
        assert hold_reasons(penv) == ["drawdown_review"]
        assert "Telegram'dan kaldırılamaz" in "\n".join(penv.fake.texts[n:])
        assert code_of("\n".join(penv.fake.texts[n:])) is None

    @pytest.mark.parametrize("reason", ["drawdown_review", "unknown_position", "late_fill", "exchange_ban",
                                        "exchange_auth", "manual"])
    def test_refuses_non_user_cmd_holds(self, penv, reason):
        penv.preload(reason, by="engine:x")
        devam(penv)
        t = penv.fake.alltext()
        assert "Bu durdurma Telegram'dan kaldırılamaz" in t and reason in t
        assert hold_reasons(penv) == [reason]

    def test_refuses_drawdown_review_even_with_valid_code_reply(self, penv):
        penv.preload("drawdown_review", by="engine:rk1", note="peak=1100 equity=870")
        penv.send("/devam")
        penv.send("4821")                                # kod gelmis olsa bile
        penv.send("4821")
        assert hold_reasons(penv) == ["drawdown_review"]

    def test_unreadable_pause_file_not_removable(self, penv):
        p = Path(penv.pause_paths["learner"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{bozuk")
        devam(penv)
        assert p.exists() and p.read_text() == "{bozuk"
        assert "kaldırılamaz" in penv.fake.alltext()

    def test_noop_when_nothing_to_resume(self, penv):
        penv.send("/devam")
        assert code_of(penv.fake.alltext()) is None
        assert penv.fake.texts                             # no-op yaniti verilir
        assert hold_reasons(penv) == []
        assert not kill_active(penv)

    def test_devam_foreign_chat_code_does_nothing(self, penv):
        penv.preload("user_cmd", by=BY)
        penv.send("/devam")
        penv.send("4821", chat_id=OTHER_CHAT)
        assert hold_reasons(penv) == ["user_cmd"]

    def test_pending_action_devam_not_interchangeable_with_pause(self, penv):
        # /durdur kodu bekliyorken /devam baslatilirsa yeni bekleyen eskiyi gecersiz kilar (tek bekleyen)
        penv.preload("user_cmd", by=BY)
        codes = iter(["1111", "2222"])
        d = penv.new_daemon(random_code=lambda: next(codes))
        penv.clk.advance(2)
        d.process_updates([msg(_next(), "/durdur", penv.clk())])
        d.process_updates([msg(_next(), "/devam", penv.clk())])
        d.process_updates([msg(_next(), "1111", penv.clk())])
        assert hold_reasons(penv) == ["user_cmd"]


class TestDevamKillInteraction:
    """Cagri basina TEK katman: KILL etkinse yalniz KILL akisi."""

    def test_kill_active_clears_only_kill_pause_stays(self, penv):
        write_status(penv.status_path, mode="paper", kill_state="flat")
        penv.ks.set(by="me", reason="manual")
        penv.preload("user_cmd", by=BY)
        devam(penv)
        assert not kill_active(penv)
        assert hold_reasons(penv) == ["user_cmd"]
        # SPEC-AMBIGUOUS: "yanit, duruyorsa duraklatmayi da bildirir" — tam metin belirsiz; duraklatmaya anan bir sozcuk
        txt = penv.last().lower()
        assert any(w in txt for w in ("duraklat", "durdur", "user_cmd", "girişler hâlâ kapalı"))

    def test_second_devam_removes_pause_layer(self, penv):
        write_status(penv.status_path, mode="paper", kill_state="flat")
        penv.ks.set(by="me", reason="manual")
        penv.preload("user_cmd", by=BY)
        devam(penv)
        assert hold_reasons(penv) == ["user_cmd"]
        devam(penv)
        assert hold_reasons(penv) == []

    def test_kill_present_pause_untouched_even_if_kill_flow_refused_exiting(self, penv):
        write_status(penv.status_path, mode="paper", kill_state="exiting")
        penv.ks.set(by="me", reason="manual")
        penv.preload("user_cmd", by=BY)
        devam(penv)
        assert kill_active(penv)
        assert hold_reasons(penv) == ["user_cmd"]
        assert "Kapanış sürüyor" in penv.fake.alltext()

    def test_live_other_origin_kill_refused_pause_untouched(self, penv):
        write_status(penv.status_path, mode="live", kill_state="flat")
        penv.ks.set(by="me", reason="manual")
        penv.preload("user_cmd", by=BY)
        devam(penv)
        assert kill_active(penv) and hold_reasons(penv) == ["user_cmd"]
        assert "yalnız sunucuda" in penv.fake.alltext() or "yalniz sunucuda" in penv.fake.alltext().lower()

    def test_live_telegram_kill_flat_cleared_pause_stays(self, penv):
        write_status(penv.status_path, mode="live", kill_state="flat")
        penv.ks.set(by="telegram:789", reason="user_cmd")
        penv.preload("user_cmd", by=BY)
        devam(penv)
        assert not kill_active(penv)
        assert hold_reasons(penv) == ["user_cmd"]

    def test_kill_cleared_then_drawdown_review_stays(self, penv):
        write_status(penv.status_path, mode="paper", kill_state="flat")
        penv.ks.set(by="me", reason="manual")
        penv.preload("drawdown_review", by="engine:rk1")
        devam(penv)
        assert not kill_active(penv) and hold_reasons(penv) == ["drawdown_review"]

    def test_kill_set_after_code_requested_for_pause_layer(self, penv):
        # kod pause katmani icin istendi, sonra KILL kuruldu: kod yurutulurken tek-katman kurali gecerli
        # SPEC-AMBIGUOUS: onay aninda KILL belirirse hangi katmanin calisacagi yazili degil; yalniz "KILL kalkmaz ve
        # kimsenin bilgisi disinda iki katman birden kalkmaz" korunur.
        penv.preload("user_cmd", by=BY)
        penv.send("/devam")
        penv.ks.set(by="me", reason="manual")
        penv.send("4821")
        assert kill_active(penv)                        # KILL bu yoldan kalkmaz (kendi iki adimli akisi vardir)

    def test_durdur_does_not_touch_kill(self, penv):
        penv.ks.set(by="telegram:789", reason="user_cmd")
        info_before = penv.ks.info()
        durdur(penv)
        assert penv.ks.info() == info_before


# =====================================================================================================
# /durum ve rapor
# =====================================================================================================
class TestStatusReply:
    def test_durum_shows_pause_line_per_bot(self, penv):
        penv.preload("user_cmd", by=BY, bot="learner")
        penv.preload("drawdown_review", by="engine:rk1", bot="twin")
        penv.send("/durum")
        t = penv.fake.alltext()
        # Satir sade Turkce: bot, neden (Turkce), kim (Telegram'dan / motor tarafindan), ne zaman; ham kod yok
        assert tg.NEDEN_TR["user_cmd"] in t and tg.NEDEN_TR["drawdown_review"] in t
        assert "Telegram'dan" in t and "motor tarafından" in t and "ana bot" in t and "twin" in t
        assert "user_cmd" not in t and "engine:rk1" not in t

    def test_durum_without_pause_has_no_pause_reasons(self, penv):
        penv.send("/durum")
        t = penv.fake.alltext()
        assert "user_cmd" not in t and "drawdown_review" not in t
        assert "duraklatıldı" not in t

    def test_durum_never_modifies_pause(self, penv):
        penv.preload("user_cmd", by=BY)
        before = Path(penv.pause_paths["learner"]).read_text()
        penv.send("/durum")
        assert Path(penv.pause_paths["learner"]).read_text() == before

    def test_yardim_lists_durdur_and_devam(self, penv):
        penv.send("/yardim")
        t = penv.fake.alltext()
        assert "/durdur" in t and "/devam" in t
