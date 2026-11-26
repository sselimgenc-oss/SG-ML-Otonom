"""Strateji verisi (strateji_veri_run.py + trader_core/strateji_veri.py): bolumler + veri zamani, tek seferlik gonderim, sessiz belge,
kilitli donem korumasi, telegram sendDocument, birim ve install.sh kurallari. Ag yok (sahte HTTP)."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

from panel_support import PARAMS, ROOT
from trader_core import ledger as L
from trader_core import panel_data as P
from trader_core import strateji_veri as SV
from trader_core import telegram as T

UTC = timezone.utc
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


R = _load("strateji_veri_run")
ARMS = ["T1@1h", "T1@4h", "R1@1h", "R1@4h", "B1@1h"]
D0 = datetime(2026, 11, 3, 6, 0, tzinfo=UTC)


def _dec(led, i, arm, side, regime, entered, bar, skip=None, risk_reason=None, veto_reason=None):
    setup, tf = arm.split("@")
    feats = {"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "pullback_ema": 1.0, "ema_value": 2000.0, "body_ratio": 0.6,
             "wick_ratio": 0.5, "rr": 2.5, "edge_dist_atr": 0.1}
    rng = regime == "range"
    long = side == "long"
    kw = dict(veto_status="allowed", veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=0.3, size_notional=600.0,
              size_margin=200.0, size_risk_amount=13.188, leverage=3, final_action="entered", skip_reason=None)
    if not entered:
        kw = dict(veto_status="not_evaluated", veto_reason=veto_reason, risk_allowed=None, risk_reason=risk_reason, size_qty=None, size_notional=None,
                  size_margin=None, size_risk_amount=None, leverage=None, final_action="skipped", skip_reason=skip)
    if skip == "risk_denied":
        kw["risk_allowed"] = False
    return led.record_decision(L.DecisionEvent(
        bar_close_ts=bar, trigger_tf=tf, pair="ETH/USDT" if i % 2 else "BTC/USDT", side=side, setup=setup, regime=regime, atr_ratio=1.1,
        rh=2100.0 if rng else None, rl=1980.0 if rng else None, rh_touches=2 if rng else 0, rl_touches=3 if rng else 0, features=feats,
        planned_entry=2000.0, planned_stop=1960.0 if long else 2040.0, planned_target=(2100.0 if long else 1900.0) if setup == "R1" else None,
        param_version_id=1, arm_id=arm, **kw))


def mk(path, extra=None):
    """(arm, side, regime, win|loss|open) islemleri + atlanan kararlar. extra: [(arm, side, regime, sonuc, bar)]."""
    led = L.open_ledger(path, "learner", clock=lambda: NOW)
    led.init_params(PARAMS, reason="x")
    plan = ([("T1@1h", "long", "trend_up", "win")] * 3 + [("T1@1h", "long", "trend_up", "loss")]
            + [("T1@4h", "short", "trend_down", "loss")] * 2 + [("T1@4h", "short", "trend_down", "win")]
            + [("R1@1h", "long", "range", "win")] * 2 + [("R1@1h", "short", "range", "loss")] + [("T1@1h", "long", "unclear", "open")])
    plan = [(a, s, r, o, D0 + timedelta(hours=3 * k)) for k, (a, s, r, o) in enumerate(plan)] + list(extra or [])
    for i, item in enumerate(plan, start=1):
        arm, side, regime, out, bar = item[:5]
        did = _dec(led, i, arm, side, regime, True, bar)
        long = side == "long"
        led.record_trade_entry(L.TradeEntry(i, did, bar + timedelta(seconds=3), 2001.0 if long else 1999.0, 0.3, 3, 0.30015))
        if out != "open":
            win = out == "win"
            px = (2079.0 if win else 1960.0) if long else (1921.0 if win else 2040.0)
            led.record_trade_exit(L.TradeExit(i, bar + timedelta(hours=1), px, "target" if win else "stop", 2100.0 if long else 1900.0, 0.3, 0.1))
    n = len(plan)
    for j in range(3):
        _dec(led, n + 1 + j, "R1@4h", "short", "range", False, D0 + timedelta(days=2, hours=j), "ml_filter")
    _dec(led, n + 4, "R1@4h", "short", "range", False, D0 + timedelta(days=2, hours=5), "max_positions")
    _dec(led, n + 5, "T1@1h", "long", "trend_up", False, D0 + timedelta(days=3, hours=1), "max_positions")
    # risk_denied / arm_conflict / max_positions ornekleri: eski (tum kayit) ve yeni (son 12 saat) pencereler
    _dec(led, n + 6, "R1@4h", "short", "range", False, D0 + timedelta(days=1), "risk_denied", "toplam açık risk sınırı aşılır")
    _dec(led, n + 7, "R1@4h", "short", "range", False, D0 + timedelta(days=3, hours=2), "risk_denied", "aynı yön (short) risk sınırı aşılır")
    _dec(led, n + 8, "R1@4h", "short", "range", False, D0 + timedelta(days=3, hours=2), "arm_conflict", veto_reason="gate:arm_conflict:T1@1h")
    _dec(led, n + 9, "R1@4h", "short", "range", False, D0 + timedelta(days=3, hours=3), "max_positions", veto_reason="gate:max_positions")
    led.close()


@pytest.fixture
def root(tmp_path):
    for d in ("var/learner", "var/durum", "config"):
        (tmp_path / d).mkdir(parents=True)
    mk(tmp_path / "var/learner/ledger.sqlite")
    (tmp_path / "config/panel.json").write_text(json.dumps({
        "schema": "panel/1", "host": "127.0.0.1", "port": 18787, "status_path": "var/learner/status.json",
        "ledger_path": "var/learner/ledger.sqlite", "budget_config": "config/budget.json",
        "health_state": str(tmp_path / "state.json"), "kill_file": "shared/KILL", "engine_config": "config/engine.base.json"}))
    (tmp_path / "config/engine.paper.json").write_text(json.dumps({"arms": ARMS}))
    return tmp_path


class Poster:
    def __init__(self, ok=True):
        self.calls, self.ok = [], ok

    def __call__(self, url, json=None, timeout=None, files=None):
        self.calls.append({"url": url, "data": json, "files": files})
        return (200, {"ok": True, "result": {"message_id": 77}}) if self.ok else (500, {"ok": False, "description": "x"})


ENV = {"TELEGRAM_BOT_TOKEN": "123456:" + "A" * 35, "TELEGRAM_CHAT_ID": "42"}


def _md(root):
    return R.rapor_uret(root, NOW)


# ------------------------------------------------------------------------------------------------ bolumler
def test_markdown_has_every_section_with_data_timestamps(root):
    md = _md(root)
    for h in ("## Ortak 1", "## Ortak 2", "## Ortak 3", "## Ortak 6", "## Ortak 7", "## ML 8", "## ML 10", "## ML 11", "## ML 12"):
        assert h in md, h
    assert md.startswith("# [ML] Strateji verisi (beyin fırtınası için)")
    # her tablo satiri veri zamani tasir (TSI)
    for blk in re.split(r"\n## ", md)[1:]:
        rows = [ln for ln in blk.splitlines() if "veri:" in ln]
        assert rows, blk[:30]
        for ln in blk.splitlines():                                   # tablo satirlari (ust baslik/ayirici haric) veri zamani tasir
            if ln.startswith("| ") and "---" not in ln and "okuma:" not in ln and not ln.startswith(("| Ölçü", "| Kalem", "| Rejim", "| Hedef", "| Kol", "| Yön", "| Mekanizma", "| Kurulum", "| CT yönü")):
                assert "veri:" in ln, ln
    assert re.search(r"veri: \d\d\.\d\d\.\d{4} \d\d:\d\d TSİ", md)
    assert "Yorum/öneri yok" in md


def test_numbers_ortak1_2_3_6_7(root):
    kap = _kap(root)
    assert len(kap) == 10
    o1 = SV.ortak1(kap)
    assert o1["n"] == 10 and o1["kazanan"] == 6 and o1["net"] == pytest.approx(sum(t["net"] for t in kap))
    assert o1["ort_kazanc_r"] > 0 > o1["ort_kayip_r"]
    o2 = SV.ortak2(kap)
    s = sorted(t["net"] for t in kap)
    assert o2["en_iyi3_cikar"] == pytest.approx(sum(s[:-3])) and o2["en_kotu3_cikar"] == pytest.approx(sum(s[3:]))
    assert o2["ikisi_cikar"] == pytest.approx(sum(s[3:-3]))
    assert o2["pay1"] == pytest.approx(s[-1] / o1["net"])
    o3 = SV.ortak3(kap)
    assert o3["komisyon"] == pytest.approx(10 * (0.30015 + 0.3)) and o3["fonlama"] == pytest.approx(1.0)
    assert o3["kom_fon_oran"] == pytest.approx((o3["komisyon"] + o3["fonlama"]) / o3["brut_kar"])
    rej = {r["rejim"]: r for r in SV.ortak6(kap)}
    assert rej["trend_up"]["n"] == 4 and rej["trend_down"]["n"] == 3 and rej["range"]["n"] == 3 and rej["unclear"]["n"] == 0
    o7 = SV.ortak7(kap, kap, D0, NOW, ARMS)
    assert o7["n"] == 10 and o7["gun"] > 0 and o7["satirlar"][0]["hedef"] == 30 and "gün" in o7["satirlar"][0]["genel"]
    assert o7["kol_sayisi_islemli"] == 3 and o7["kol_sayisi_yapilandirma"] == 5


def _kap(root):
    led = P.open_ledger_ro(str(root / "var/learner/ledger.sqlite"), "learner")
    try:
        dec = led.list_decisions(since_ts=SV.KILIT[1])
        by = {d.id: d for d in dec}
        return [t for t in SV.islem_satirlari(led.list_closed_trades(since=SV.KILIT[1], limit=100), led.list_open_trades(), by) if t["kapali"]]
    finally:
        led.close()


def test_ml8_arms_without_trades_and_skip_reasons(root):
    md = _md(root)
    sec = md.split("## ML 8")[1].split("## ML 10")[0]
    assert "Yapılandırılmış kol: 5 · ≥1 işlem açan: 3 · hiç açmayan: 2" in sec
    assert "ml_filter=3" in sec and "max_positions=2" in sec and "R1@4h" in sec
    assert "B1@1h" in sec and "aday üretmedi" in sec


def test_ml8_per_arm_skip_breakdown_and_windows(root):
    sec = _md(root).split("## ML 8")[1].split("## ML 10")[0]
    row = [x for x in sec.split("### Kol bazında")[1].splitlines() if x.startswith("| R1@4h |")][0]
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert "risk_denied=2 (max_open_risk=1, max_same_dir_risk=1)" in cells[3]       # tum kayit
    assert "arm_conflict=1 (T1@1h=1)" in cells[3] and "max_positions=2 (max_positions=2)" in cells[3]
    assert "ml_filter=3" in cells[3]
    assert "risk_denied=1 (max_same_dir_risk=1)" in cells[6] and "ml_filter" not in cells[6] and "max_open_risk" not in cells[6]   # son 12 saat
    assert cells[4] == "3" and cells[1] == "8"
    assert "Aday üretmedi (sinyal tarafı, filtre değil): tüm kayıtta B1@1h" in sec
    d = SV.ml8(ARMS, [], [], None)
    assert d["aday_yok_tum"] == list(ARMS)


def test_risk_limiti_names():
    assert SV.risk_limiti("günlük zarar bütçesi aşılır") == "daily_max_loss"
    assert SV.risk_limiti("toplam teminat özsermayeyi aşar") == "margin_total" and SV.risk_limiti(None) == "?"
    assert SV.risk_limiti("bilinmeyen") == "diğer"


def test_rerun_refreshes_file_without_resending(root):
    p = Poster()
    R.kos(root, NOW, ENV, p)
    f = root / "var/durum/strateji-veri-ml.md"
    f.write_text("eski")
    assert R.kos(root, NOW + timedelta(hours=6), ENV, p) == 0 and len(p.calls) == 1
    assert b"## Ortak 1" in f.read_bytes()


def test_ml10_flags_losing_arms_and_lists_mechanisms(root):
    md = _md(root)
    sec = md.split("## ML 10")[1].split("## ML 11")[0]
    assert "T1@4h" in sec and "ZARARDA" in sec
    assert "Kol kapatma kaydı (arms_off)" in sec and "10 R freni" not in sec and "Kol bazında otomatik karantina" in sec
    assert "giriş ENGELLENMEZ" in sec


def test_ml11_long_short_and_current_regime(root):
    d = SV.ml11(_kararlar(root), ARMS)
    assert d["rejim"] in ("trend_up", "range", "trend_down", "unclear")
    md = _md(root)
    sec = md.split("## ML 11")[1].split("## ML 12")[0]
    assert "| long |" in sec and "| short |" in sec and "Güncel rejim" in sec and "Long aday (güncel rejim)" in sec


def _kararlar(root):
    led = P.open_ledger_ro(str(root / "var/learner/ledger.sqlite"), "learner")
    try:
        return SV.karar_satirlari(led.list_decisions(since_ts=SV.KILIT[1]))
    finally:
        led.close()


def test_ct_bilgisi_bolumu_yok(root):
    """CT/ML ayriligi: strateji verisinde CT bolumu ve `ct_ozet` yoktur."""
    md = _md(root)
    assert "CT bilgisi" not in md and "ct_yon" not in md
    assert not hasattr(SV, "ct_ozet") and not hasattr(SV, "ct_yon_of")


def test_ml12_band_and_tutarlilik_or_veri_yok(root):
    sec = _md(root).split("## ML 12")[1]
    assert "veri yok" in sec and "yetersiz" in sec                      # n=10 < 20: band yok; tutarlilik raporu yok
    (root / "var/durum/tutarlilik_v1.json").write_text(json.dumps({
        "sema": "ml.tutarlilik.v1", "uretim": "2026-11-16T00:40:00Z", "donem": {"bas": "2026-11-09", "bit": "2026-11-16"}, "uyari": False,
        "kurulumlar": [{"ad": "T1", "kagit_islem": 4, "bt_islem": 5, "kagit_R": 2.0, "bt_R": 1.0, "eslesme_orani": 0.8}]}))
    sec = _md(root).split("## ML 12")[1]
    assert "| T1 | 4 |" in sec and "veri: 16.11.2026 03:40 TSİ" in sec
    assert SV.bant_satiri(100, 5.0)["etiket"].endswith("(bant içinde)") and SV.bant_satiri(60, -50.0)["etiket"] == "%2,5 altında"


# ------------------------------------------------------------------------------------------------ gonderim
def test_sends_once_silent_document_and_marker_blocks_resend(root):
    p = Poster()
    assert R.kos(root, NOW, ENV, p) == 0
    assert len(p.calls) == 1
    c = p.calls[0]
    assert c["url"].endswith("/sendDocument") and c["data"]["disable_notification"] is True and c["data"]["chat_id"] == 42
    assert c["data"]["caption"] == "[ML] Strateji verisi (beyin fırtınası için)"
    name, body, _ = c["files"]["document"]
    assert name == "strateji-veri-ml.md" and b"## Ortak 1" in body
    m = json.loads((root / "var/durum/strateji_veri_gonderildi.json").read_text())
    assert m["surum"] == 1 and m["mesaj_no"] == 77
    assert (root / "var/durum/strateji-veri-ml.md").read_bytes() == body
    assert R.kos(root, NOW + timedelta(hours=1), ENV, p) == 0 and len(p.calls) == 1          # tekrar gonderilmez
    assert R.main(["--once", "--root", str(root)], now_fn=lambda: NOW, env=ENV, http_post=p) == 0 and len(p.calls) == 1


def test_higher_version_would_resend(root, monkeypatch):
    p = Poster()
    R.kos(root, NOW, ENV, p)
    monkeypatch.setattr(R, "SURUM", 2)
    R.kos(root, NOW, ENV, p)
    assert len(p.calls) == 2


def test_failed_send_writes_no_marker_and_missing_keys_skip(root):
    assert R.kos(root, NOW, ENV, Poster(ok=False)) == 1
    assert not (root / "var/durum/strateji_veri_gonderildi.json").exists()
    p = Poster()
    assert R.kos(root, NOW, {}, p) == 0 and p.calls == []
    assert not (root / "var/durum/strateji_veri_gonderildi.json").exists()


def test_dry_run_prints_without_send_or_marker(root, capsys):
    p = Poster()
    assert R.main(["--dry-run", "--root", str(root)], now_fn=lambda: NOW, env=ENV, http_post=p) == 0
    assert "## Ortak 1" in capsys.readouterr().out and p.calls == []
    assert not (root / "var/durum/strateji_veri_gonderildi.json").exists()


def test_missing_ledger_is_noop(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/panel.json").write_text(json.dumps({"schema": "panel/1", "ledger_path": "var/learner/ledger.sqlite"}))
    assert R.kos(tmp_path, NOW, ENV, Poster()) == 0


def test_telegram_send_document_multipart_default_post(monkeypatch):
    seen = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"ok": True, "result": {"message_id": 5}}

    import requests
    monkeypatch.setattr(requests, "post", lambda url, **kw: seen.update(url=url, **kw) or Resp())
    c = T.TelegramClient("123456:" + "B" * 35)
    assert c.send_document(1, "a.md", b"x", "t")["message_id"] == 5
    assert seen["data"]["disable_notification"] == "true" and seen["files"]["document"][0] == "a.md" and "json" not in seen
    # mevcut sendMessage yolu degismez: json govdesi, files yok
    seen.clear()
    c.send_message(1, "m")
    assert "files" not in seen and seen["json"]["text"] == "m"


# ------------------------------------------------------------------------------------------------ kilitli donem
def test_lock_constant_matches_engine_holdout_and_filters(monkeypatch):
    from trader_engine.holdout import HOLDOUT, KILIT_ACIK
    assert SV.KILIT == HOLDOUT and SV.KILIT_ACIK == KILIT_ACIK is True
    # 23.11.2026: kilit acik -> zamani olan her kayit "kilit disi" (okunur); zamansiz kayit yine okunmaz
    assert SV.kilit_disi(datetime(2026, 5, 1, tzinfo=UTC)) and SV.kilit_disi(datetime(2026, 10, 31, 23, 45, tzinfo=UTC))
    assert SV.kilit_disi(datetime(2026, 11, 1, tzinfo=UTC)) and SV.kilit_disi(datetime(2026, 4, 30, 23, 45, tzinfo=UTC))
    assert not SV.kilit_disi(None)
    monkeypatch.setattr(SV, "KILIT_ACIK", False)                 # kapali kilit: eski davranis
    assert not SV.kilit_disi(datetime(2026, 5, 1, tzinfo=UTC)) and not SV.kilit_disi(datetime(2026, 10, 31, 23, 45, tzinfo=UTC))
    assert SV.kilit_disi(datetime(2026, 11, 1, tzinfo=UTC)) and SV.kilit_disi(datetime(2026, 4, 30, 23, 45, tzinfo=UTC))


def test_holdout_guard_queries_after_lock_and_drops_lock_rows(root, monkeypatch):
    """Defter SQL'inde bile kilitli donem istenmez; sizan kayit olsa adaptor atar."""
    calls = {}
    orig = P.open_ledger_ro

    def spy(path, bot):
        led = orig(path, bot)
        ld, lc = led.list_decisions, led.list_closed_trades
        led.list_decisions = lambda **kw: calls.setdefault("dec", kw) and ld(**kw)
        led.list_closed_trades = lambda *a, **kw: calls.setdefault("closed", kw) and lc(*a, **kw)
        return led
    monkeypatch.setattr(P, "open_ledger_ro", spy)
    _md(root)
    assert calls["dec"]["since_ts"] == SV.KILIT[1] and calls["closed"]["since"] == SV.KILIT[1]
    # kilitli doneme dusen yapay kayit (veri degil, sentetik) ledger'da varsa rapora girmez
    L2 = root / "var/learner/ledger.sqlite"
    led = L.open_ledger(L2, "learner", clock=lambda: NOW)
    bar = datetime(2026, 9, 1, 6, 0, tzinfo=UTC)
    did = _dec(led, 99, "T1@1h", "long", "trend_up", True, bar)
    led.record_trade_entry(L.TradeEntry(99, did, bar + timedelta(seconds=3), 2001.0, 0.3, 3, 0.3))
    led.record_trade_exit(L.TradeExit(99, bar + timedelta(hours=1), 2079.0, "target", 2100.0, 0.3, 0.1))
    led.close()
    monkeypatch.setattr(P, "open_ledger_ro", orig)
    assert "Kapanan işlem: 10 " in _md(root)
    assert SV.islem_satirlari([], [], {}) == []


def test_source_never_references_history_or_lock_data():
    for f in (ROOT / "scripts/strateji_veri_run.py", ROOT / "src/trader_core/strateji_veri.py"):
        t = f.read_text(encoding="utf-8")
        assert "var/" + "history" not in t and "market." + "sqlite" not in t and "holdout_degerlendir" not in t
    assert "since_ts=SV.KILIT[1]" in (ROOT / "scripts/strateji_veri_run.py").read_text(encoding="utf-8")


def test_ledger_opened_read_only_no_migrate():
    t = (ROOT / "scripts/strateji_veri_run.py").read_text(encoding="utf-8")
    assert "P.open_ledger_ro(" in t and "open_ledger(" not in t.replace("open_ledger_ro(", "")


# ------------------------------------------------------------------------------------------------ birim / kurulum
def _kv(path):
    out = {}
    for ln in (ROOT / "deploy" / path).read_text(encoding="utf-8").splitlines():
        if "=" in ln and not ln.startswith("#"):
            k, _, v = ln.partition("=")
            out[k.strip()] = v.strip()
    return out


def test_unit_sandboxed_like_mutabakat_and_reads_telegram_env():
    kv, mu = _kv("trader-strateji-veri.service"), _kv("trader-mutabakat.service")
    assert kv["Type"] == "oneshot" and kv["User"] == "trader" and kv["Slice"] == "trader.slice"
    assert kv["EnvironmentFile"] == "/etc/trader-telegram.env"                      # telegram servisiyle ayni anahtar dosyasi
    assert kv["ExecStart"] == "/usr/bin/python3 -I /opt/trader/scripts/strateji_veri_run.py --once"
    for k in ("ProtectSystem", "ProtectHome", "NoNewPrivileges", "PrivateTmp", "Nice", "IOSchedulingClass", "MemoryMax", "Slice"):
        assert kv[k] == mu[k], k
    assert kv["ReadWritePaths"] == "/opt/trader/var/durum"                          # var/durum disinda yazma yok
    assert "PrivateNetwork" not in kv and "AF_INET" in kv["RestrictAddressFamilies"]    # Telegram'a cikis gerekir
    tm = (ROOT / "deploy/trader-strateji-veri.timer").read_text(encoding="utf-8")        # rapor dosyasi 6 saatte bir yenilenir
    assert "OnCalendar=*-*-* 00/6:20:00 UTC" in tm and "WantedBy=timers.target" in tm


def test_install_starts_unit_once_after_restarts_non_fatal():
    t = (ROOT / "deploy/install.sh").read_text(encoding="utf-8")
    i = t.index('if [ -e "${UNIT_DIR}/trader-strateji-veri.service" ]')
    blok = t[i:i + 420]
    assert "systemctl start --no-block trader-strateji-veri.service" in blok and "fail " not in blok and "exit " not in blok
    assert i > t.index("enable_now trader-engine@learner.service") and i > t.index("systemctl restart trader-telegram.service")
    assert "enable_now trader-strateji-veri.timer" in t and "enable_now trader-strateji-veri.service" not in t


def test_kaldirilan_kol_arm_conflict_kazanani_gosterilmez_sayi_kalir():
    kol = ["T1@1h", "R1@4h"]
    def d(w):
        return {"arm": "R1@4h", "girdi": False, "skip": "arm_conflict", "veto": f"gate:arm_conflict:{w}", "ts": D0}
    assert SV.skip_detay(d("C1@1h"), kol) == ("arm_conflict", None)
    assert SV.skip_detay(d("T1@1h"), kol) == ("arm_conflict", "T1@1h")
    assert SV.skip_detay(d("T1"), kol) == ("arm_conflict", "T1")                       # kurulum adi yapilandirmada var
    assert SV.skip_detay(d("C1@1h")) == ("arm_conflict", "C1@1h")                      # kollar verilmezse filtre yok
    w = SV._pencere("R1@4h", [d("C1@1h"), d("C1@4h"), d("T1@1h")], kol)
    assert w["skip"]["arm_conflict"] == 3 and dict(w["detay"]["arm_conflict"]) == {"T1@1h": 1}
    m = SV.ml8(kol, [], [d("C1@1h"), d("T1@1h")], None)
    assert "C1" not in json.dumps(m["kol_detay"], default=str)


def test_stop_genislik_dar_genis_medyan_ve_pencere():
    """stop_width olcumu: dar/genis ayrimi features.stop_dist_atr ile bant sinirlarindan turetilir; son 12s ve tum kayit."""
    t = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)

    def r(sda, ago_h, skip="stop_width", arm="T1@1h"):
        return {"arm": arm, "skip": skip, "girdi": False, "ts": t - timedelta(hours=ago_h), "sda": sda}

    rows = [r(0.3, 1), r(0.4, 2), r(3.0, 5), r(0.2, 30), r(2.5, 40), r(1.0, 1, skip="rr_below_min"), r(5.0, 1, arm="R1@1h")]
    out = {x["arm"]: x for x in SV.stop_genislik(["T1@1h", "R1@1h", "B1@1h"], rows, t)}
    a = out["T1@1h"]
    assert a["son"]["n"] == 3 and a["son"]["dar"] == 2 and a["son"]["genis"] == 1 and a["son"]["medyan"] == 0.4
    assert a["tum"]["n"] == 5 and a["tum"]["dar"] == 3 and a["tum"]["genis"] == 2 and a["tum"]["medyan"] == 0.4
    assert out["R1@1h"]["son"]["genis"] == 1 and out["B1@1h"]["tum"]["n"] == 0 and out["B1@1h"]["tum"]["medyan"] is None
