"""RK-1 bagimsiz sartname testi: Telegram /kademe, /kademe_devam, /devam, /durum ve rapor satiri
(docs/motor/12-risk-kademe.md §9, T-54..T-59) + mentor karari rk_g5_review.md duzeltme 5 (status.json'da
`risk_ladder` blogu yok ya da blok durumu gunluk durumundan farkli -> ret 5 "Motor durumu okunamiyor") ve
duzeltme 2(a) (bekleyen durma yeniden denemesi -> gate_code `ladder_invalid` -> ret 6).
Gerceklemeye (telegram.py / ladder.py / risk_ladder.py ic kodu) BAKILMADAN yazildi. Ag yok, tmp_path.

Kullanilan genel arayuz: LadderLog(path).append(kind, by, now, **fields) (§4.4), LadderFiles(log, status_path, pause),
TelegramDaemon(..., ladders={bot: LadderFiles}), status.json `risk_ladder` blogu (§10).
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
from trader_core.risk_ladder import LadderLog, LadderLogError  # noqa: E402

from test_telegram_pause_spec import BY, BOTS, hold_reasons, penv  # noqa: E402,F401  (penv: fixture)
from test_telegram_spec import CID, T0, code_of, msg, _next, set_kill  # noqa: E402

OTHER_CHAT = 555000999
H24 = 86400


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(v):
    """Sayi gosterimi: 198 -> 198,00 ya da 198.00 (ondalik ayraci belirtimde 'virgul' ornegi; ikisi de kabul)."""
    return r"%s[,.]%s" % (str(int(v)), ("%.2f" % v).split(".")[1]) if v == int(v) else \
        re.escape(("%.2f" % v).replace(".", "@")).replace("@", "[,.]")


def has_num(text, v):
    return re.search(_num(v), text) is not None


class L:
    pass


@pytest.fixture
def lad(penv):
    """penv + canli bot `learner` icin kademe dosyalari. Varsayilan durum: review, 30 saat once durmus, ozsermaye 198."""
    e = penv
    e.lstatus = str(e.tmp / "ladder_status.json")
    e.llog = LadderLog(str(e.tmp / "var" / "learner" / "risk_ladder.jsonl"))
    (e.tmp / "var" / "learner").mkdir(parents=True, exist_ok=True)
    e.lf = tg.LadderFiles(e.llog, e.lstatus, e.pauses["learner"])

    def rebuild(ladders=None):
        e.d = e.new_daemon(ladders={"learner": e.lf} if ladders is None else ladders)
    e.rebuild = rebuild

    def seed(state="review", age=30 * 3600, hold=True, extra_rows=()):
        """Gunluk: initial 250 (10 gun once) -> state'e gore durma satiri (`age` sn once). hold: drawdown_review tutusu."""
        now = e.clk()
        e.llog.append("initial", "cli:op", now - timedelta(days=10), amount=250.0)
        for kind, fields, dt in extra_rows:
            e.llog.append(kind, "cli:op", dt, **fields)
        if state == "review":
            e.llog.append("review_stop", "engine:rk1", now - timedelta(seconds=age), equity=195.0, base=250.0)
            if hold:
                e.pauses["learner"].add("drawdown_review", by="engine:rk1", note="base=250 equity=195")
        elif state == "floor":
            e.llog.append("floor_stop", "engine:rk1", now - timedelta(seconds=age), equity=140.0, dep_net=250.0)
            if hold:
                e.pauses["learner"].add("capital_floor", by="engine:rk1", note="dep_net=250 equity=140")
        elif state == "ok":
            pass
        elif state == "ok_hold":                                  # durma + devam satiri yazildi, tutus kalmis
            e.llog.append("review_stop", "engine:rk1", now - timedelta(seconds=age), equity=195.0, base=250.0)
            e.llog.append("review_resume", "telegram:789", now - timedelta(seconds=age // 2), equity=198.0,
                          rebase=True, decision="")
            e.pauses["learner"].add("drawdown_review", by="engine:rk1")
    e.seed = seed

    def wstatus(state="review", equity=198.0, loop_age=0, gate=None, block=True, **over):
        """status.json (ladder_status): taze ya da `loop_age` sn bayat; `risk_ladder` blogu §10 bicimi."""
        d = {"schema": "engine-status/1", "bot": "learner", "mode": "live",
             "loop_at": _iso(e.clk() - timedelta(seconds=loop_age)), "kill": False, "equity": equity,
             "gate": {"ok": True, "code": gate or "ok"}}
        if block:
            try:
                rr = e.llog.rows()
                seq, hh = (rr[-1]["seq"], rr[-1]["hash"][:8]) if rr else (0, "")
            except Exception:
                seq, hh = 0, ""
            b = {"enforce": True, "state": state, "step": 0, "step_name": "K0", "step_risk": 0.005,
                 "effective_risk": 0.005, "lowest_step": 0, "dep_net": 250.0, "base": 250.0, "peak": 262.4,
                 "equity": equity, "dd_base_pct": 0.0, "dd_peak_pct": 0.0, "stop_at": 200.0, "floor_at": 150.0,
                 "near": False, "stopped_at": None, "last_down_at": None, "gate_code": gate, "gate_since": None,
                 "transfer": None, "pending": None, "would": None, "follow": None,
                 "counters": {"total_trades": 37, "step_trades": 37, "step_days": 21, "step_mean_r": 0.04,
                              "consec_losses": 2, "last30_sum_r": 1.3},
                 "log_seq": seq, "log_hash": hh}
            b.update(over)
            d["risk_ladder"] = b
        Path(e.lstatus).write_text(json.dumps(d))
    e.wstatus = wstatus
    e.rows = lambda: e.llog.rows()
    e.kinds = lambda: [r["kind"] for r in e.llog.rows()]
    e.holds = lambda: hold_reasons(e)
    e.tail = lambda n: "\n".join(e.fake.texts[n:])
    return e


def kademe_devam(e, code="4821"):
    e.send("/kademe_devam")
    e.send(code)


# =====================================================================================================
# T-54 /kademe
# =====================================================================================================
class TestKademe:
    def test_values_from_status_block(self, lad):
        lad.seed("review", extra_rows=[("peak", {"value": 262.4}, lad.clk() - timedelta(days=5))])
        lad.wstatus("review", equity=198.0, dd_base_pct=20.8, dd_peak_pct=24.5, peak=262.4, stop_at=200.0,
                    floor_at=150.0)
        lad.rebuild()
        lad.send("/kademe")
        t = lad.last()
        assert "risk %0,50 (sabit)" in t and "K0" not in t          # 24.11: etkin risk durum blogundan
        assert re.search(r"0[,.]5", t)                                 # risk %0,5
        for v in (250.0, 262.4, 198.0, 200.0, 150.0):                  # dep_net/base, peak, equity, durma, taban
            assert has_num(t, v), (v, t)
        assert "learner" in t
        assert re.search(r"inceleme|İNCELEME|inceleme", t, re.I) or "inceleme" in t.lower()
        assert "drawdown_review" in t or "inceleme" in t.lower()

    def test_state_words(self, lad):
        lad.seed("floor")
        lad.wstatus("floor", equity=140.0)
        lad.rebuild()
        lad.send("/kademe")
        assert "durum taban" in lad.last().lower()

    def test_state_word_ok(self, lad):
        lad.seed("ok")
        lad.wstatus("ok", equity=262.4)
        lad.rebuild()
        lad.send("/kademe")
        assert "durum ok" in lad.last().lower()

    def test_counters_and_gate_code_shown(self, lad):
        lad.seed("review")
        lad.wstatus("review", gate="capital_mismatch")
        lad.rebuild()
        lad.send("/kademe")
        t = lad.last()
        assert "capital_mismatch" in t
        assert "37" in t                                               # total_trades

    def test_read_only(self, lad):
        lad.seed("review")
        lad.wstatus("review")
        lad.rebuild()
        rows, holds = lad.rows(), lad.holds()
        lad.send("/kademe")
        assert lad.rows() == rows and lad.holds() == holds == ["drawdown_review"]

    def test_empty_ladders(self, lad):
        lad.rebuild(ladders={})
        lad.send("/kademe")
        assert "kademe denetimi yapılandırılmadı" in lad.last()

    def test_no_ladders_arg(self, lad):
        lad.d = lad.new_daemon()
        lad.send("/kademe")
        assert "kademe denetimi yapılandırılmadı" in lad.last()

    def test_stale_status_folds_log_with_note(self, lad):
        # taban 750 (250 + 500 yatirma) gunlukten katlanir; bayat blokta 111,11 yazar -> gunluk esas
        lad.seed("review", extra_rows=[("deposit", {"amount": 500.0}, lad.clk() - timedelta(days=9))])
        lad.wstatus("review", loop_age=300, dep_net=111.11, base=111.11, peak=111.11, stop_at=88.89, floor_at=66.67)
        lad.rebuild()
        lad.send("/kademe")
        t = lad.last()
        assert "bayat" in t.lower()
        assert has_num(t, 750.0) and not re.search(r"111[,.]11", t)

    def test_stale_boundary_120_fresh_121_stale(self, lad):
        lad.seed("review")
        lad.rebuild()
        lad.wstatus("review", loop_age=120, dep_net=111.11, base=111.11)
        lad.send("/kademe")
        assert "bayat" not in lad.last().lower()
        lad.wstatus("review", loop_age=121, dep_net=111.11, base=111.11)
        lad.send("/kademe")
        assert "bayat" in lad.last().lower()

    def test_help_lists_commands(self, lad):
        lad.rebuild()
        lad.send("/yardim")
        t = lad.fake.alltext()
        assert "/kademe" in t and "/kademe_devam" in t


# =====================================================================================================
# T-55 /kademe_devam retleri (istek anindaki ret; kod gonderilirse hicbir sey yazilmaz)
# =====================================================================================================
def refused(e, needle, rows_before=None, holds_before=None):
    """Istek reddedildi mi: yanit `needle` icerir, kod gonderilse de gunluk/tutus degismez."""
    rows_before = e.rows() if rows_before is None else rows_before
    holds_before = e.holds() if holds_before is None else holds_before
    n = len(e.fake.texts)
    e.send("/kademe_devam")
    t = e.tail(n)
    assert needle in t, t
    assert "Onaylarsan" not in t
    e.send("4821")
    assert e.rows() == rows_before and e.holds() == holds_before


class TestKademeDevamRefusals:
    def test_1_no_review_state_ok_no_hold(self, lad):
        lad.seed("ok_hold")
        lad.pauses["learner"].remove("drawdown_review", by="cli:x")
        lad.wstatus("ok", equity=198.0)
        lad.rebuild()
        refused(lad, "Bekleyen kademe incelemesi yok")

    def test_1_not_refusal_when_ok_but_hold_remains(self, lad):
        lad.seed("ok_hold")
        lad.wstatus("ok", equity=198.0)
        lad.rebuild()
        lad.send("/kademe_devam")
        assert code_of(lad.last()) == "4821" or "Onaylarsan" in lad.last()
        assert "Bekleyen kademe incelemesi yok" not in lad.last()

    def test_2_floor(self, lad):
        lad.seed("floor")
        lad.wstatus("floor", equity=140.0)
        lad.rebuild()
        refused(lad, "Telegram'dan açılamaz")
        assert "capital_floor" in lad.holds()

    def test_3_kill_active(self, lad):
        lad.seed("review")
        lad.wstatus("review")
        lad.rebuild()
        set_kill(lad)
        refused(lad, "Önce KILL")

    def test_4_wait_86399_refused(self, lad):
        lad.seed("review", age=H24 - 1)
        lad.wstatus("review")
        lad.rebuild()
        refused(lad, "En erken")

    def test_4_wait_86400_accepted(self, lad):
        lad.seed("review", age=H24)
        lad.wstatus("review")
        lad.rebuild()
        kademe_devam(lad)
        assert lad.kinds()[-1] == "review_resume" and lad.holds() == []

    def test_4_refusal_states_remaining_time(self, lad):
        lad.seed("review", age=H24 - 3600)                             # 1 saat kaldi
        lad.wstatus("review")
        lad.rebuild()
        lad.send("/kademe_devam")
        assert "kalan" in lad.last().lower() and "1" in lad.last()

    def test_5_status_missing(self, lad):
        lad.seed("review")
        lad.rebuild()                                                  # status dosyasi yok
        refused(lad, "Motor durumu okunamıyor")

    @pytest.mark.parametrize("age,ok", [(120, True), (121, False)])
    def test_5_staleness_boundary(self, lad, age, ok):
        lad.seed("review")
        lad.wstatus("review", loop_age=age)
        lad.rebuild()
        if ok:
            kademe_devam(lad)
            assert lad.kinds()[-1] == "review_resume"
        else:
            refused(lad, "Motor durumu okunamıyor")

    @pytest.mark.parametrize("eq", [0, -5.0, None, "x", float("nan"), float("inf"), True])
    def test_5_bad_equity(self, lad, eq):
        lad.seed("review")
        lad.wstatus("review")
        d = json.loads(Path(lad.lstatus).read_text())
        d["equity"] = eq if eq == eq else "NaN"
        if isinstance(eq, float) and eq != eq:
            Path(lad.lstatus).write_text(json.dumps(d).replace('"NaN"', "NaN"))
        elif eq == float("inf"):
            Path(lad.lstatus).write_text(json.dumps(d).replace("Infinity", "Infinity"))
        else:
            Path(lad.lstatus).write_text(json.dumps(d))
        lad.rebuild()
        refused(lad, "Motor durumu okunamıyor")

    def test_5_corrupt_status_file(self, lad):
        lad.seed("review")
        Path(lad.lstatus).write_text("{bozuk")
        lad.rebuild()
        refused(lad, "Motor durumu okunamıyor")

    # --- mentor karari, duzeltme 5 ---
    def test_5_fix5_missing_risk_ladder_block(self, lad):
        lad.seed("review")
        lad.wstatus("review", block=False)                             # taze status.json, blok yok
        lad.rebuild()
        refused(lad, "Motor durumu okunamıyor")

    def test_5_fix5_block_null(self, lad):
        lad.seed("review")
        lad.wstatus("review")
        d = json.loads(Path(lad.lstatus).read_text())
        d["risk_ladder"] = None
        Path(lad.lstatus).write_text(json.dumps(d))
        lad.rebuild()
        refused(lad, "Motor durumu okunamıyor")

    @pytest.mark.parametrize("blockstate", ["ok", "floor", "uninitialized", "invalid"])
    def test_5_fix5_block_state_differs_from_log(self, lad, blockstate):
        lad.seed("review")                                             # gunluk: review
        lad.wstatus(blockstate)
        lad.rebuild()
        refused(lad, "Motor durumu okunamıyor")

    def test_5_fix5_block_state_matches_log_ok(self, lad):
        lad.seed("review")
        lad.wstatus("review")
        lad.rebuild()
        kademe_devam(lad)
        assert lad.kinds()[-1] == "review_resume"

    def test_6_gate_code(self, lad):
        lad.seed("review")
        lad.wstatus("review", gate="capital_mismatch")
        lad.rebuild()
        refused(lad, "Önce sermaye kaydı sorunu çözülmeli: capital_mismatch")

    @pytest.mark.parametrize("code", ["capital_unverified", "capital_missing", "equity_unreadable"])
    def test_6_other_gate_codes(self, lad, code):
        lad.seed("review")
        lad.wstatus("review", gate=code)
        lad.rebuild()
        refused(lad, "Önce sermaye kaydı sorunu çözülmeli: " + code)

    # --- mentor karari, duzeltme 2(a): bekleyen durma yeniden denemesi -> ladder_invalid -> ret 6 ---
    def test_6_fix2a_ladder_invalid_blocks_resume(self, lad):
        lad.seed("ok_hold")                                            # durma satiri yazilamadi senaryosu: tutus var, durum ok
        lad.wstatus("ok", gate="ladder_invalid")
        lad.rebuild()
        refused(lad, "Önce sermaye kaydı sorunu çözülmeli: ladder_invalid")

    def test_6_fix2a_ladder_invalid_blocks_review_too(self, lad):
        lad.seed("review")
        lad.wstatus("review", gate="ladder_invalid")
        lad.rebuild()
        refused(lad, "ladder_invalid")

    # --- ilk tutan ---
    def test_precedence_floor_before_kill(self, lad):
        lad.seed("floor")
        lad.wstatus("floor", equity=140.0)
        lad.rebuild()
        set_kill(lad)
        lad.send("/kademe_devam")
        assert "Telegram'dan açılamaz" in lad.last() and "Önce KILL" not in lad.last()

    def test_precedence_kill_before_wait(self, lad):
        lad.seed("review", age=3600)
        lad.wstatus("review")
        lad.rebuild()
        set_kill(lad)
        lad.send("/kademe_devam")
        assert "Önce KILL" in lad.last() and "En erken" not in lad.last()

    def test_precedence_wait_before_status(self, lad):
        lad.seed("review", age=3600)
        lad.rebuild()                                                  # status yok
        lad.send("/kademe_devam")
        assert "En erken" in lad.last()

    def test_no_ladders_configured(self, lad):
        lad.rebuild(ladders={})
        lad.send("/kademe_devam")
        assert "kademe denetimi yapılandırılmadı" in lad.last() or "Bekleyen kademe incelemesi yok" in lad.last()
        assert code_of(lad.last()) is None


# =====================================================================================================
# T-56 iki adim
# =====================================================================================================
class TestTwoStep:
    def ready(self, lad, **seed):
        lad.seed("review", **seed)
        lad.wstatus("review", equity=198.0)
        lad.rebuild()

    def test_step1_writes_nothing_and_previews(self, lad):
        self.ready(lad)
        rows, holds = lad.rows(), lad.holds()
        lad.send("/kademe_devam")
        t = lad.last()
        assert code_of(t) == "4821" and "Onaylarsan" in t
        assert has_num(t, 198.0) and re.search(r"158[,.]4", t) and has_num(t, 150.0) and "(sabit)" in t
        assert lad.rows() == rows and lad.holds() == holds

    def test_pending_action_is_ladder_resume(self, lad):
        self.ready(lad)
        lad.send("/kademe_devam")
        found = list(Path(lad.tmp).rglob("pending.json"))
        assert found and re.search(r'"action"\s*:\s*"ladder_resume"', found[0].read_text())
        assert "4821" not in found[0].read_text()

    def test_correct_code_writes_row_then_removes_hold(self, lad):
        self.ready(lad)
        order = []
        orig = lad.llog.append

        def spy(kind, by, now, **kw):
            order.append(("append", kind, lad.holds()))
            return orig(kind, by, now, **kw)
        lad.llog.append = spy
        kademe_devam(lad)
        assert order and order[-1][1] == "review_resume"
        assert order[-1][2] == ["drawdown_review"]                     # satir yazilirken tutus HALA duruyor
        r = lad.rows()[-1]
        assert r["kind"] == "review_resume" and r["rebase"] is True and r["by"] == BY
        assert r["by"].startswith("telegram:") and r["equity"] == 198.0 and r["decision"] == ""
        assert lad.holds() == []

    def test_resume_audited_by_pause_remove(self, lad):
        self.ready(lad)
        kademe_devam(lad)
        rows = [json.loads(x) for p in lad.tmp.rglob("pause_audit.jsonl") for x in p.read_text().splitlines() if x.strip()]
        assert any(r["op"] == "remove" and r["reason"] == "drawdown_review" and r["by"] == BY for r in rows)

    def test_wrong_code_writes_nothing(self, lad):
        self.ready(lad)
        rows = lad.rows()
        lad.send("/kademe_devam")
        lad.send("0000")
        lad.send("4821")                                               # eski kod artik gecersiz
        assert lad.rows() == rows and lad.holds() == ["drawdown_review"]

    @pytest.mark.parametrize("adv,ok", [(119, True), (120, True), (121, False)])
    def test_code_ttl(self, lad, adv, ok):
        self.ready(lad)
        lad.send("/kademe_devam")
        lad.clk.advance(adv)
        lad.wstatus("review", equity=198.0)                            # durum taze kalsin
        n = len(lad.rows())
        lad.send("4821")
        if ok:
            assert len(lad.rows()) == n + 1 and lad.holds() == []
        else:
            assert len(lad.rows()) == n and lad.holds() == ["drawdown_review"]

    def test_single_use(self, lad):
        self.ready(lad)
        kademe_devam(lad)
        n = len(lad.rows())
        lad.send("4821")
        assert len(lad.rows()) == n

    def test_unauthorized_chat_request_gets_no_code(self, lad):
        self.ready(lad)
        rows = lad.rows()
        lad.send("/kademe_devam", chat_id=OTHER_CHAT)
        assert code_of(lad.fake.alltext()) is None
        lad.send("4821", chat_id=OTHER_CHAT)
        lad.send("4821")                                               # yetkili sohbet: bekleyen yok
        assert lad.rows() == rows and lad.holds() == ["drawdown_review"]

    def test_code_from_foreign_chat_ignored(self, lad):
        self.ready(lad)
        lad.send("/kademe_devam")
        rows = lad.rows()
        lad.send("4821", chat_id=OTHER_CHAT)
        assert lad.rows() == rows and lad.holds() == ["drawdown_review"]

    def test_recheck_kill_after_request(self, lad):
        self.ready(lad)
        lad.send("/kademe_devam")
        set_kill(lad)
        rows = lad.rows()
        lad.send("4821")
        assert lad.rows() == rows and lad.holds() == ["drawdown_review"]
        assert "KILL" in lad.last()

    def test_recheck_gate_code_after_request(self, lad):
        self.ready(lad)
        lad.send("/kademe_devam")
        lad.wstatus("review", equity=198.0, gate="capital_mismatch")
        rows = lad.rows()
        lad.send("4821")
        assert lad.rows() == rows and lad.holds() == ["drawdown_review"]
        assert "capital_mismatch" in lad.last()

    def test_recheck_ladder_invalid_after_request_fix2a(self, lad):
        self.ready(lad)
        lad.send("/kademe_devam")
        lad.wstatus("review", equity=198.0, gate="ladder_invalid")
        rows = lad.rows()
        lad.send("4821")
        assert lad.rows() == rows and lad.holds() == ["drawdown_review"]

    def test_recheck_status_goes_stale_after_request(self, lad):
        self.ready(lad)
        lad.send("/kademe_devam")
        lad.clk.advance(100)                                           # status yazilmadi; 100 + eski -> kod aninda bayat degil?
        lad.wstatus("review", equity=198.0, loop_age=121)
        rows = lad.rows()
        lad.send("4821")
        assert lad.rows() == rows and lad.holds() == ["drawdown_review"]

    def test_recheck_block_removed_after_request_fix5(self, lad):
        self.ready(lad)
        lad.send("/kademe_devam")
        lad.wstatus("review", equity=198.0, block=False)
        rows = lad.rows()
        lad.send("4821")
        assert lad.rows() == rows and lad.holds() == ["drawdown_review"]

    def test_recheck_wait_not_met_at_code_time_never_happens_but_floor_does(self, lad):
        self.ready(lad)
        lad.send("/kademe_devam")
        lad.llog.append("floor_stop", "engine:rk1", lad.clk(), equity=140.0, dep_net=250.0)
        lad.pauses["learner"].add("capital_floor", by="engine:rk1")
        lad.wstatus("floor", equity=140.0)
        n = len(lad.rows())
        lad.send("4821")
        assert len(lad.rows()) == n and "drawdown_review" in lad.holds()

    def test_other_bots_untouched(self, lad):
        self.ready(lad)
        lad.pauses["twin"].add("user_cmd", by=BY)
        kademe_devam(lad)
        assert hold_reasons(lad, "twin") == ["user_cmd"]

    def test_reply_counts_remaining_holds(self, lad):
        self.ready(lad)
        lad.pauses["learner"].add("user_cmd", by=BY)
        kademe_devam(lad)
        t = lad.last()
        assert "user_cmd" in t                                         # _remaining_lines: kalan tutuslar
        assert lad.holds() == ["user_cmd"]

    def test_ok_state_with_hold_only_removes_hold(self, lad):
        lad.seed("ok_hold")
        lad.wstatus("ok", equity=198.0)
        lad.rebuild()
        n = len(lad.rows())
        kademe_devam(lad)
        assert len(lad.rows()) == n and lad.holds() == []              # satir yazilmaz, yalniz tutus kalkar


# =====================================================================================================
# T-57 hata yollari
# =====================================================================================================
class FailingRemove:
    """EntryPause sarmalayici: remove hata verir."""
    def __init__(self, inner):
        self._i = inner
        self.fail = True

    def remove(self, *a, **k):
        if self.fail:
            raise OSError("disk")
        return self._i.remove(*a, **k)

    def __getattr__(self, n):
        return getattr(self._i, n)


class TestFailures:
    @pytest.mark.parametrize("exc", [LadderLogError("kotu"), OSError("disk dolu")])
    def test_row_write_failure_keeps_hold_and_crit(self, lad, exc):
        lad.seed("review")
        lad.wstatus("review", equity=198.0)
        lad.rebuild()
        lad.send("/kademe_devam")
        rows = lad.rows()

        def boom(*a, **k):
            raise exc
        lad.llog.append = boom
        lad.send("4821")
        assert lad.rows() == rows and lad.holds() == ["drawdown_review"]
        assert re.search(r"CRIT|KRİTİK|Kritik|kritik|YAZILAMADI|KALDIRILAMADI", lad.last()), lad.last()
        assert "girişler açık" not in lad.last()

    def test_hold_removal_failure_crit_then_repeat_removes_only_hold(self, lad):
        lad.seed("review")
        lad.wstatus("review", equity=198.0)
        fr = FailingRemove(lad.pauses["learner"])
        lad.lf = tg.LadderFiles(lad.llog, lad.lstatus, fr)
        lad.rebuild()
        kademe_devam(lad)
        assert lad.kinds()[-1] == "review_resume"                      # satir yazildi
        assert lad.holds() == ["drawdown_review"]                      # tutus kalkmadi
        assert re.search(r"CRIT|KRİTİK|Kritik|kritik|YAZILAMADI|KALDIRILAMADI", lad.last()), lad.last()
        assert "girişler açık" not in lad.last()
        n = len(lad.rows())
        fr.fail = False
        lad.wstatus("ok", equity=198.0)                                # motor satiri katladi: durum ok
        kademe_devam(lad)
        assert len(lad.rows()) == n                                    # ikinci satir yazilmaz
        assert lad.holds() == []


# =====================================================================================================
# T-58 /devam kademe tutuslarini kaldirmaz; floor'da /kademe_devam reddi
# =====================================================================================================
class TestDevamDoesNotLiftLadder:
    def test_devam_keeps_drawdown_review(self, lad):
        lad.seed("review")
        lad.wstatus("review")
        lad.rebuild()
        lad.send("/devam")
        lad.send("4821")
        lad.send("4821")
        assert lad.holds() == ["drawdown_review"]
        assert lad.kinds() == ["initial", "review_stop"]

    def test_devam_keeps_capital_floor_with_server_hint(self, lad):
        lad.seed("floor")
        lad.wstatus("floor", equity=140.0)
        lad.rebuild()
        lad.send("/devam")
        lad.send("4821")
        assert lad.holds() == ["capital_floor"]
        t = lad.fake.alltext()
        assert "capital_floor" in t and "sunucuda" in t and "yazılı" in t

    def test_devam_removes_user_cmd_only_beside_ladder_holds(self, lad):
        lad.seed("review")
        lad.pauses["learner"].add("user_cmd", by=BY)
        lad.wstatus("review")
        lad.rebuild()
        lad.send("/devam")
        lad.send("4821")
        assert lad.holds() == ["drawdown_review"]

    def test_floor_state_kademe_devam_refused_even_after_devam(self, lad):
        lad.seed("floor")
        lad.wstatus("floor", equity=140.0)
        lad.rebuild()
        refused(lad, "Telegram'dan açılamaz")
        assert lad.holds() == ["capital_floor"]

    def test_no_telegram_commands_for_capital(self, lad):
        lad.seed("review")
        lad.wstatus("review")
        lad.rebuild()
        rows = lad.rows()
        for c in ("/sermaye", "/capital", "/floor_restart", "/kademe_artir", "/step_up"):
            lad.send(c)
        assert lad.rows() == rows and lad.holds() == ["drawdown_review"]


# =====================================================================================================
# T-59 /durum ve gunluk rapor satiri
# =====================================================================================================
OK_LINE = "Kademe: risk %0,50 (sabit) | özsermaye 262,40 | taban 250,00 (düşüş %0,0) | durma 200,00 | son taban 150,00 | işlem 37"


class TestStatusAndReport:
    def _status_ok(self, lad, state="ok", **over):
        lad.seed("review" if state == "review" else "floor" if state == "floor" else "ok_hold")
        lad.wstatus(state, equity=262.4, peak=262.4, **over)
        lad.rebuild()

    def test_durum_line_ok(self, lad):
        lad.seed("ok")
        lad.wstatus("ok", equity=262.4)
        lad.rebuild()
        lad.send("/durum")
        t = lad.fake.alltext()
        assert OK_LINE in t
        assert "İNCELEME" not in t and "TABAN" not in t

    def test_durum_line_review_prefixed(self, lad):
        self._status_ok(lad, "review")
        lad.send("/durum")
        t = lad.fake.alltext()
        line = next(x for x in t.splitlines() if "Kademe:" in x)
        assert "İNCELEME" in line and "TABAN" not in line
        assert line.index("İNCELEME") < line.index("Kademe:")

    def test_durum_line_floor_prefixed(self, lad):
        self._status_ok(lad, "floor")
        lad.send("/durum")
        line = next(x for x in lad.fake.alltext().splitlines() if "Kademe:" in x)
        assert "TABAN" in line and "İNCELEME" not in line
        assert line.index("TABAN") < line.index("Kademe:")

    def test_durum_without_ladders_has_no_line(self, lad):
        lad.rebuild(ladders={})
        lad.send("/durum")
        assert "Kademe:" not in lad.fake.alltext()

    def _report(self, lad):
        now = lad.clk()
        # Kademe satiri artik gunluk ozette degil; /kademe ve panelde. Bolum ayri okunur.
        secs = tg.default_sections(lad.cfg, now, "2026-11-16", pauses=lad.pauses, ladders={"learner": lad.lf})
        assert "Kademe:" not in tg.build_report(lad.cfg, now, "2026-11-16", secs)
        return secs["Risk kademesi"]()

    def test_report_section_and_line_ok(self, lad):
        lad.seed("ok")
        lad.wstatus("ok", equity=262.4)
        Path(lad.cfg.status_path).write_text(Path(lad.lstatus).read_text())
        out = self._report(lad)
        assert "Kademe:" in out and OK_LINE in out

    def test_report_prefix_review_and_floor(self, lad):
        lad.seed("review")
        lad.wstatus("review", equity=198.0)
        Path(lad.cfg.status_path).write_text(Path(lad.lstatus).read_text())
        out = self._report(lad)
        line = next(x for x in out.splitlines() if "Kademe:" in x)
        assert "İNCELEME" in line

    def test_report_no_ladders_has_no_section(self, lad):
        now = lad.clk()
        Path(lad.cfg.status_path).write_text(json.dumps({"equity": 1000.0, "day_start_equity": 1000.0}))
        out = tg.build_report(lad.cfg, now, "2026-11-16", tg.default_sections(lad.cfg, now, "2026-11-16"))
        assert "Risk kademesi" not in out and "Kademe:" not in out
