"""RK-1 Telegram parcasi (12 §9): /kademe, /kademe_devam (iki adimli kod), /durum ve rapor satiri, /devam ile iliskisi,
scripts/telegram_run.py build_ladders. Saat enjekte, ag yok (FakeTG), dosyalar tmp altinda."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import risk_ladder as rl
from trader_core import telegram as T
from trader_engine.killswitch import Killswitch
from trader_engine.pause import EntryPause

UTC = timezone.utc
CHAT = 555000111
T0 = datetime(2026, 12, 30, 10, 0, tzinfo=UTC)
D = timedelta(days=1)
H = timedelta(hours=1)


class Clk:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t

    def now(self):
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


def z(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class Rig:
    """TelegramDaemon + tek botluk kademe dosyalari (learner)."""

    def __init__(self, tmp, *, build=None, with_ladders=True):
        self.tmp, self.clk, self.fake = Path(tmp), Clk(), FakeTG()
        self.cfg = T.TelegramConfig(token="1:tok", chat_id=CHAT, var_dir=str(self.tmp / "tg"),
                                    kill_file=str(self.tmp / "KILL"), status_path=str(self.tmp / "status.json"))
        self.ks = Killswitch(self.cfg.kill_file, self.clk)
        self.log = rl.LadderLog(str(self.tmp / "risk_ladder.jsonl"))
        self.status_path = self.tmp / "status.json"
        self.pause = EntryPause(str(self.tmp / "PAUSE.learner"), self.clk, audit_path=str(self.tmp / "audit.jsonl"))
        if build is None:
            self.review()
        else:
            build(self)
        lf = {"learner": T.LadderFiles(self.log, str(self.status_path), self.pause)} if with_ladders else None
        self.d = T.TelegramDaemon(self.cfg, T.TelegramClient("1:tok", self.fake, lambda s: None), now_fn=self.clk,
                                  runner=lambda *a: (0, "{}"), sleep=lambda s: None, random_code=lambda: "0427",
                                  killswitch=self.ks, pauses={"learner": self.pause}, ladders=lf)
        self.uid = 0

    # -- tohumlar
    def ok(self, amount=1000.0):
        self.log.append("initial", "cli:t", T0 - 10 * D, amount=amount)

    def review(self, stopped_ago=timedelta(days=2), amount=1000.0, hold=True):
        self.ok(amount)
        self.log.append("review_stop", "engine:rk1", T0 - stopped_ago, equity=0.8 * amount, base=amount)
        if hold:
            self.pause.add("drawdown_review", "engine:rk1")

    def floor(self):
        self.review()
        self.log.append("floor_stop", "engine:rk1", T0 - H, equity=590.0, dep_net=1000.0)
        self.pause.add("capital_floor", "engine:rk1")

    def write_status(self, equity=790.0, age=5, **blk):
        try:
            lstate = self.log.state().status
        except Exception:  # noqa: BLE001
            lstate = None
        d = {"loop_at": z(T0 - timedelta(seconds=age)), "equity": equity, "mode": "testnet",
             "risk_ladder": {"enforce": True, "state": lstate, "gate_code": None, "counters": {"total_trades": 37, "step_trades": 37,
                                                                              "step_days": 21, "step_mean_r": 0.04,
                                                                              "consec_losses": 2, "last30_sum_r": 1.3},
                             **blk}}
        self.status_path.write_text(json.dumps(d))

    # -- konusma
    def msg(self, text, *, age=0, chat=CHAT):
        self.uid += 1
        return {"update_id": self.uid, "message": {"message_id": self.uid, "date": int(self.clk().timestamp()) - age,
                                                   "chat": {"id": chat, "type": "private"}, "from": {"id": chat},
                                                   "text": text}}

    def say(self, text, **kw):
        n = len(self.fake.texts())
        self.d.process_updates([self.msg(text, **kw)])
        t = self.fake.texts()
        return t[-1] if len(t) > n else None


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path)
    r.write_status()
    return r


def rows(r):
    return [x["kind"] for x in r.log.rows()]


# ------------------------------------------------------------------------------------------------ /kademe
def test_kademe_values(rig):
    t = rig.say("/kademe")
    assert "learner: risk %1,00 (sabit) | durum inceleme" in t
    assert "yatırılan 1000,00 | taban 1000,00 | tepe 1000,00 | özsermaye 790,00" in t
    assert "tabandan %21,0" in t and "durma seviyesi 800,00 USD | son taban 600,00 USD" in t
    assert "işlem 37" in t and "bayat" not in t


def test_kademe_unconfigured(tmp_path):
    r = Rig(tmp_path, with_ladders=False)
    assert "kademe denetimi yapılandırılmadı" in r.say("/kademe")
    assert "yapılandırılmadı" in r.say("/kademe_devam")


def test_kademe_stale_status_falls_back_to_log(rig):
    rig.write_status(age=121)
    t = rig.say("/kademe")
    assert "motor durumu bayat" in t and "özsermaye ?" in t and "risk %1,00 (sabit)" in t


def test_kademe_gate_code_shown_and_uninitialized(rig, tmp_path):
    rig.write_status(gate_code="capital_mismatch")
    assert "kapı: capital_mismatch" in rig.say("/kademe")
    r2 = Rig(tmp_path / "u", build=lambda r: None)
    assert "sermaye kaydı yok" in r2.say("/kademe")


def test_help_lists_new_commands(rig):
    assert "/kademe" in T.HELP and "/kademe_devam" in T.HELP


# ------------------------------------------------------------------------------------------------ ret kosullari
def test_refuse_no_review(tmp_path):
    r = Rig(tmp_path, build=lambda r: r.ok())
    r.write_status()
    assert "Bekleyen kademe incelemesi yok" in r.say("/kademe_devam")
    assert not r.d._pending_p.exists()


def test_refuse_floor(tmp_path):
    r = Rig(tmp_path, build=lambda r: r.floor())
    r.write_status(590.0)
    assert "Son taban: Telegram'dan açılamaz; yazılı karar + sunucu gerekir" in r.say("/kademe_devam")
    assert not r.d._pending_p.exists()


def test_refuse_kill(rig):
    rig.ks.set("cli", "manual")
    assert "Önce KILL: /devam" in rig.say("/kademe_devam")


@pytest.mark.parametrize("ago,ok", [(timedelta(seconds=86399), False), (timedelta(seconds=86400), True)])
def test_24h_boundary(tmp_path, ago, ok):
    r = Rig(tmp_path, build=lambda r: r.review(stopped_ago=ago))
    r.write_status()
    t = r.say("/kademe_devam")
    if ok:
        assert "0427" in t and not t.startswith("En erken")
    else:
        assert t.startswith("En erken 30.12.2026 13:00") and "kalan 1 saat" in t
        assert not r.d._pending_p.exists()


@pytest.mark.parametrize("age,ok", [(120, True), (121, False)])
def test_status_freshness_boundary(rig, age, ok):
    rig.write_status(age=age)
    t = rig.say("/kademe_devam")
    assert ("0427" in t) if ok else ("Motor durumu okunamıyor; sunucuda `ladder resume`" in t)


def test_refuse_status_missing_or_bad_equity(rig):
    rig.status_path.unlink()
    assert "Motor durumu okunamıyor" in rig.say("/kademe_devam")
    for bad in (None, 0, -3, "x"):
        rig.write_status(equity=bad)
        assert "Motor durumu okunamıyor" in rig.say("/kademe_devam")


def test_refuse_missing_or_mismatched_risk_ladder_block(rig):
    """RK-1 fix 5: status.json taze ama `risk_ladder` blogu yok / gunluk durumuyla uyusmuyor -> ret 5 (Motor durumu okunamiyor)."""
    d = json.loads(rig.status_path.read_text())
    d.pop("risk_ladder")
    rig.status_path.write_text(json.dumps(d))
    assert "Motor durumu okunamıyor" in rig.say("/kademe_devam")
    assert not rig.d._pending_p.exists()
    rig.write_status(state="ok")                                  # gunluk review diyor, blok ok diyor
    assert "Motor durumu okunamıyor" in rig.say("/kademe_devam")
    rig.write_status(state=None)
    assert "Motor durumu okunamıyor" in rig.say("/kademe_devam")
    rig.write_status()                                            # uyumlu blok: kod istenir
    assert "0427" in rig.say("/kademe_devam")


def test_refuse_gate_code(rig):
    rig.write_status(gate_code="capital_mismatch")
    assert "Önce sermaye kaydı sorunu çözülmeli: capital_mismatch" in rig.say("/kademe_devam")


def test_request_shows_outcome_beforehand(rig):
    rig.write_status(equity=790.0)
    t = rig.say("/kademe_devam")
    assert "yeni taban 790,00 USD" in t and "yeni durma seviyesi 632,00 USD" in t and "risk %1,00 (sabit)" in t
    assert "son taban 600,00 USD" in t and "0427" in t
    assert rows(rig) == ["initial", "review_stop"] and rig.pause.active()          # istek hicbir sey yazmaz


def test_request_shows_km1_stays(tmp_path):
    def build(r):
        r.ok()
        r.log.append("step_down", "engine:rk1", T0 - 3 * D, step=-1, trigger="dd_peak_10", equity=900.0, peak=1000.0)
        r.log.append("review_stop", "engine:rk1", T0 - 2 * D, equity=790.0, base=1000.0)
        r.pause.add("drawdown_review", "engine:rk1")
    r = Rig(tmp_path, build=build)
    r.write_status()
    assert "risk %1,00 (sabit)" in r.say("/kademe_devam")


# ------------------------------------------------------------------------------------------------ iki adim
def test_approval_writes_row_then_removes_hold(rig):
    seen = {}
    real_remove = rig.pause.remove

    def spy(reason, by):
        seen["rows_at_remove"] = rows(rig)                 # tutus kaldirilirken satir zaten yazilmis olmali
        seen["by"] = by
        return real_remove(reason, by)

    rig.pause.remove = spy
    rig.say("/kademe_devam")
    t = rig.say("0427")
    assert seen["rows_at_remove"][-1] == "review_resume" and seen["by"] == "telegram:111"
    r = rig.log.rows()[-1]
    assert r["kind"] == "review_resume" and r["rebase"] is True and r["by"] == "telegram:111" and r["decision"] == ""
    assert r["equity"] == 790.0 and rig.log.state().base == 790.0 and rig.log.state().status == "ok"
    assert not rig.pause.active() and "girişler açık" in t and not rig.d._pending_p.exists()


def test_wrong_code_and_unauthorized_write_nothing(rig):
    rig.say("/kademe_devam")
    assert "yanlis kod" in rig.say("9999")
    assert rows(rig) == ["initial", "review_stop"] and rig.pause.active() and not rig.d._pending_p.exists()
    rig.say("/kademe_devam")
    rig.d.process_updates([rig.msg("0427", chat=999)])                    # yetkisiz sohbet: yok sayilir
    assert rows(rig) == ["initial", "review_stop"] and rig.pause.active()


@pytest.mark.parametrize("wait,accepted", [(119, True), (120, True), (121, False)])
def test_code_ttl_boundaries(rig, wait, accepted):
    rig.say("/kademe_devam")
    rig.clk.t = T0 + timedelta(seconds=wait)
    rig.write_status(age=0)                                               # durum taze kalsin: yalniz kod TTL'i sinanir
    t = rig.say("0427")
    assert (rig.log.state().status == "ok") is accepted
    if not accepted:
        assert "sure doldu" in t and rig.pause.active() and rows(rig) == ["initial", "review_stop"]


def test_conditions_rechecked_at_code_time(rig):
    rig.say("/kademe_devam")
    rig.ks.set("cli", "manual")                             # istekten sonra KILL kuruldu
    assert "Önce KILL: /devam" in rig.say("0427")
    assert rows(rig) == ["initial", "review_stop"] and rig.pause.active()


def test_status_goes_stale_between_request_and_code(rig):
    rig.say("/kademe_devam")
    rig.clk.t = T0 + timedelta(seconds=116)                 # kod hala gecerli (< 120 sn) ama status 121 sn eski
    assert "Motor durumu okunamıyor" in rig.say("0427")
    assert rig.log.state().status == "review" and rig.pause.active()


def test_row_write_failure_keeps_hold_and_replies_crit(rig):
    class Boom(rl.LadderLog):
        def append(self, *a, **k):
            raise OSError("salt okunur")

    lf = rig.d.ladders["learner"]
    rig.d.ladders["learner"] = T.LadderFiles(Boom(rig.log.path), lf.status_path, lf.pause)
    rig.say("/kademe_devam")
    t = rig.say("0427")
    assert "YAZILAMADI" in t and rig.pause.active() and rows(rig) == ["initial", "review_stop"]
    sent = [p for m, p in rig.fake.calls if m == "sendMessage"][-1]
    assert sent.get("disable_notification") in (False, None)


def test_hold_removal_failure_then_repeat_removes_only_hold(rig):
    def boom(reason, by):
        raise OSError("izin")

    real = rig.pause.remove
    rig.pause.remove = boom
    rig.say("/kademe_devam")
    t = rig.say("0427")
    assert "KALDIRILAMADI" in t and rows(rig)[-1] == "review_resume" and rig.pause.active()
    n = len(rig.log.rows())
    rig.pause.remove = real
    rig.write_status()                                      # motor blogu guncel gunluk durumunu (ok) bildirir (RK-1 fix 5)
    t2 = rig.say("/kademe_devam")                           # durum artik ok + artik tutus: ret degil, 24 saat beklemez
    assert "0427" in t2
    rig.say("0427")
    assert len(rig.log.rows()) == n and not rig.pause.active()                    # ikinci satir yazilmaz


def test_residual_hold_in_ok_state_is_not_refused_without_wait(tmp_path):
    def build(r):
        r.ok()
        r.pause.add("drawdown_review", "engine:rk1")
    r = Rig(tmp_path, build=build)
    r.write_status()
    assert "0427" in r.say("/kademe_devam")
    r.say("0427")
    assert rows(r) == ["initial"] and not r.pause.active()


# ------------------------------------------------------------------------------------------------ /devam ile iliski
def test_devam_does_not_remove_ladder_holds(tmp_path):
    r = Rig(tmp_path, build=lambda r: r.floor())
    r.write_status(590.0)
    t = r.say("/devam")
    assert "kaldırılamaz" in t and "capital_floor" in t and "sunucuda, yazılı kararla" in t
    assert {h.reason for h in r.pause.holds()} == {"drawdown_review", "capital_floor"}
    r2 = Rig(tmp_path / "b")
    r2.write_status()
    t = r2.say("/devam")
    assert "kaldırılamaz" in t and "drawdown_review" in t and r2.pause.active()


# ------------------------------------------------------------------------------------------------ /durum ve rapor
def test_status_and_report_line_formats(tmp_path):
    r = Rig(tmp_path, build=lambda r: r.ok(250.0))
    r.write_status(equity=262.4)
    line = T.ladder_line("learner", T.ladder_view(r.d.ladders["learner"], T0))
    assert line == ("learner: Kademe: risk %1,00 (sabit) | özsermaye 262,40 | taban 250,00 (düşüş %0,0) | durma 200,00 | "
                    "son taban 150,00 | işlem 37")
    assert line in r.say("/durum")
    sec = T.default_sections(r.cfg, T0, "2026-12-30", None, r.d.ladders)
    assert "Risk kademesi" in sec and line in sec["Risk kademesi"]()
    assert "Kademe:" not in T.build_report(r.cfg, T0, "2026-12-30", sec)      # gunluk ozet kisa: kademe /kademe ve panelde
    assert "Risk kademesi" not in T.default_sections(r.cfg, T0, "2026-12-30", None, None)


def test_status_line_review_and_floor_prefix(tmp_path):
    r = Rig(tmp_path)
    r.write_status()
    assert "learner: İNCELEME Kademe: risk %1,00 (sabit)" in r.say("/durum")
    r2 = Rig(tmp_path / "f", build=lambda r: r.floor())
    r2.write_status(590.0)
    assert "learner: TABAN Kademe: risk %1,00 (sabit)" in r2.say("/durum")


def test_run_report_passes_ladders(tmp_path):
    r = Rig(tmp_path)
    r.write_status()
    sent = []

    class N:
        def send_text(self, text, sev, key, **k):
            sent.append(text)
            return True

    now = datetime(2026, 12, 30, 18, 1, tzinfo=UTC)                     # 21:01 Istanbul
    assert T.run_report(r.cfg, N(), now, pauses={"learner": r.pause}, ladders=r.d.ladders) == "sent"
    assert sent[0].startswith("[ML] ") and "Günlük özet" in sent[0] and "Kademe:" not in sent[0]


# ------------------------------------------------------------------------------------------------ calistirici
def test_build_ladders_from_env(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    try:
        import telegram_run as TR
    finally:
        sys.path.pop(0)
    clk = Clk()
    assert TR.build_ladders({}, clk, tmp_path) == {}                           # varsayilan bos: komutlar kapali
    env = {"LADDER_BOTS": "learner, twin", "ENGINE_VAR_DIR": "var", "PAUSE_FILE": "shared/PAUSE"}
    lad = TR.build_ladders(env, clk, tmp_path)
    assert set(lad) == {"learner", "twin"}
    lf = lad["learner"]
    assert lf.log.path == str(tmp_path / "var" / "learner" / "risk_ladder.jsonl")
    assert lf.status_path == str(tmp_path / "var" / "learner" / "status.json")
    assert lf.pause.path == str(tmp_path / "shared" / "PAUSE.learner")
    assert (Path(__file__).resolve().parents[1] / "deploy" / "trader-telegram.env.example").read_text().count("LADDER_BOTS=") == 1
