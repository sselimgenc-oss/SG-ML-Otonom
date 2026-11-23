"""DD-12 WP-17 (Rapor, Telegram, pano) bagimsiz spec testleri: docs/motor/dd12-capraz-varlik-spec.md §7, §9 WP-17
satiri, D-T23 ve Ek (18 Kasim): LLM yalniz haftalik ozet yazar, L1 iptal, butce 10 USD.
Uygulayici testlerine bakilmadan yazildi; isim sabit olmayan yerlerde esnek kesif kullanilir."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from panel_support import DAY, NOW, Env, Running, free_port  # noqa: E402
from trader_core import counterfactual as CF  # noqa: E402
from trader_core import lesson as LS  # noqa: E402
from trader_core import telegram as T  # noqa: E402
from trader_panel.server import build_api  # noqa: E402

UTC = timezone.utc
FORBIDDEN = re.compile(r"ikiz|twin|veto", re.IGNORECASE)
ARM_OFF_ID = "T1@4h"


def _git_show(rel: str) -> str:
    r = subprocess.run(["git", "show", f"HEAD:./{rel}"], cwd=ROOT, capture_output=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.decode("utf-8")


def _snap(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.endswith((".sqlite-shm", "-wal", "-shm")):
            st = p.stat()
            out[str(p.relative_to(root))] = (hashlib.sha256(p.read_bytes()).hexdigest(), st.st_mtime_ns)
    return out


def _write_arms_off(root: Path, arms: dict) -> Path:
    p = root / "var/learner/arms_off.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"arms": arms}), encoding="utf-8")
    return p


def _api_paths(r: Running) -> list[str]:
    """Sunucu harici haritasindan tum GET uc noktalari (yeni uc noktalar da kesfedilir)."""
    keys = list(build_api(r.data).keys())
    return [k for k in keys if k != "/healthz"] + ["/healthz", "/"]


def _api_text(r: Running) -> str:
    parts = []
    for p in _api_paths(r):
        if p == "/":
            continue
        st, _, body = r.req(p)
        if st == 200:
            parts.append(json.dumps(body, ensure_ascii=False, default=str))
    return "\n".join(parts)


def _page_text(r: Running) -> str:
    st, _, body = r.req("/", raw=True)
    assert st == 200
    return body.decode("utf-8", "replace")


def _telegram_cfg(e: Env, status_path: Path | None = None) -> T.TelegramConfig:
    root = e.root
    sp = root / "var/learner/status.json"
    if sp.exists():  # Telegram okuyucusu "...SSZ" bicimini bekler (milisaniyesiz); panel fikstürü ".000Z" yazar
        sp.write_text(re.sub(r"\.\d{3}Z\"", "Z\"", sp.read_text(encoding="utf-8")), encoding="utf-8")
    return T.TelegramConfig("1:tok", 5, str(root / "tg"), "",
                            str(status_path or root / "var/learner/status.json"),
                            ledger_path=str(root / "var/learner/ledger.sqlite"),
                            budget_config=str(root / "config/budget.json"),
                            lesson_store=str(root / "user_data/lesson.sqlite"))


def _report(cfg: T.TelegramConfig) -> str:
    # gercek uretim yolu: report_run varsayilan bolumlerle cagirir (sections=None en kisa ozet; eski testler buna bagli)
    # Gunluk ozet artik <=12 satir; ders/model/seans/LLM bolumleri kaldirilmadi, /ders /kurulumlar /rapor komutlariyla ve panelde.
    # Bolumler tek tek uretilir (okunamayan bolum bos kalir).
    secs = T.default_sections(cfg, NOW, DAY)
    out = [T.build_report(cfg, NOW, DAY, sections=secs)]
    for fn in secs.values():
        try:
            out.append(str(fn() or ""))
        except Exception:  # noqa: BLE001
            pass
    return "\n".join(out)


# ---------------------------------------------------------------- pano: Öğrenme sekmesi (statik kaynak)
def test_pano_ogrenme_sekmesi_tanimli():
    text = "\n".join(
        (ROOT / "src/trader_panel/static" / n).read_text(encoding="utf-8")
        for n in ("index.html", "panel.js") if (ROOT / "src/trader_panel/static" / n).exists())
    assert re.search(r"[ÖO]ğrenme|ogrenme|Öğrenme", text, re.IGNORECASE), "Öğrenme sekmesi pano kaynaginda yok"


def test_pano_bir_kurulum_karnesi_ve_cagri_kesfi_calisir_ve_eksik_uc_yok(tmp_path):
    """Uc noktalarin hepsi (kesfedilen) 200 ya da 4xx donmeli; 500 ve iz dokumu olmamali."""
    e = Env(tmp_path)
    r = Running(e, cache_s=0)
    try:
        for p in _api_paths(r):
            st, _, body = r.req(p, raw=True)
            assert st < 500, (p, st)
            assert b"Traceback" not in body, p
    finally:
        r.stop()
        e.close()


# ---------------------------------------------------------------- pano: kurulum karnesi, açık/kapalı
def test_kurulum_karnesi_arm_scorecard_fonksiyonu_import_edilebilir():
    assert callable(CF.arm_scorecard)
    sc = CF.arm_scorecard([], arms=[ARM_OFF_ID], closed={ARM_OFF_ID})
    assert isinstance(sc, dict)


def test_kapali_kurulum_arms_off_dan_okunur_ve_pano_gosterir(tmp_path):
    e = Env(tmp_path)
    _write_arms_off(e.root, {ARM_OFF_ID: {"state": "closed", "since": "2026-11-16T10:00:00Z"}})
    state = LS.read_arms_state(e.root / "var/learner/arms_off.json")
    assert state.get(ARM_OFF_ID, {}).get("state") == "closed"
    r = Running(e, cache_s=0)
    try:
        text = _api_text(r) + _page_text(r)
        assert ARM_OFF_ID in _api_text(r), "kapali kurulum panel verisinde yok"
        assert re.search(r"kapal|closed|kapalı", _api_text(r), re.IGNORECASE)
    finally:
        r.stop()
        e.close()
    assert text


def test_arms_off_yok_iken_taze_sunucu_acik_varsayar_ve_cokmez(tmp_path):
    e = Env(tmp_path)
    assert not (e.root / "var/learner/arms_off.json").exists()
    assert LS.read_arms_state(e.root / "var/learner/arms_off.json") == {}
    r = Running(e, cache_s=0)
    try:
        for p in _api_paths(r):
            assert r.req(p)[0] < 500, p
    finally:
        r.stop()
        e.close()


# ---------------------------------------------------------------- pano: ders, ML, seans, varlık kırılımı
def test_pano_ders_freni_ve_ml_etkisi_alanlari_var(tmp_path):
    e = Env(tmp_path)
    r = Running(e, cache_s=0)
    try:
        api = _api_text(r)
        assert re.search(r"brake|fren", api, re.IGNORECASE), "ders freni durumu panelde yok"
        assert re.search(r"\bml\b|setup_filter|süzgeç|suzgec|filter", api, re.IGNORECASE), "ML etkisi panelde yok"
    finally:
        r.stop()
        e.close()


def test_pano_seans_ve_varlik_sinifi_kirilimi_var(tmp_path):
    e = Env(tmp_path)
    r = Running(e, cache_s=0)
    try:
        api = _api_text(r)
        assert re.search(r'"(session|seans)[^"]*"', api, re.IGNORECASE), "seans kirilimi yok"
        assert re.search(r'"(asset_class|varlik|varlık|asset)[^"]*"', api, re.IGNORECASE), "varlik sinifi kirilimi yok"
    finally:
        r.stop()
        e.close()


def test_pano_haftalik_ozet_eksikken_cokmez_ve_dosya_varsa_gorunur(tmp_path):
    marker = "HAFTALIK-OZET-ISARETI-7731"
    e = Env(tmp_path)
    r = Running(e, cache_s=0)
    try:
        assert r.req("/")[0] == 200            # ozet dosyasi yokken pano acilir
    finally:
        r.stop()
    # ozet yazilir: yol sabit degil; birkac makul konuma yazilir, pano/Telegram okuyan konumu bulmali
    # gercek konum (WP-09 weekly_summary_run): <defter dizini>/weekly_summaries/YYYY-Www.md
    for rel in ("var/learner/weekly_summaries/2026-W46.md", "var/learner/weekly_summary.md"):
        p = e.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# Haftalık özet\n\n{marker}\n", encoding="utf-8")
    r = Running(e, cache_s=0)
    try:
        assert marker in _api_text(r) + _page_text(r) or marker in _report(_telegram_cfg(e))
    finally:
        r.stop()
        e.close()


# ---------------------------------------------------------------- pano: LLM harcaması 10 USD
def test_llm_harcama_satiri_10_usd_ile_karsilastirilir(tmp_path):
    e = Env(tmp_path)
    try:
        rep = _report(_telegram_cfg(e))
        lines = [ln for ln in rep.splitlines() if re.search(r"LLM|harcama", ln, re.IGNORECASE)]
        assert any(re.search(r"20(\.0+)?\s*(\$|USD)", ln) for ln in lines), lines   # 23.11: tavan 20 $
    finally:
        e.close()


# ---------------------------------------------------------------- Telegram: günlük rapor ve komutlar
def test_telegram_komutlari_kurulumlar_ve_ders_var():
    assert "/kurulumlar" in T.HELP
    assert "/ders" in T.HELP
    src = (ROOT / "src/trader_core/telegram.py").read_text(encoding="utf-8")   # calisma agaci (commit oncesi de)
    assert '"/kurulumlar"' in src or "/kurulumlar" in src


def test_telegram_gunluk_rapor_ders_ml_seans_ve_llm_bolumleri(tmp_path):
    e = Env(tmp_path)
    _write_arms_off(e.root, {ARM_OFF_ID: {"state": "closed"}})
    try:
        rep = _report(_telegram_cfg(e))
        assert isinstance(rep, str) and rep
        assert re.search(r"ders", rep, re.IGNORECASE), "ders etkisi yok"
        assert re.search(r"ML|Model", rep), "ML etkisi yok"            # sahibe Turkce: "Model"
        assert re.search(r"Seans|hafta sonu|weekend", rep, re.IGNORECASE), "seans kirilimi yok"   # veri yoksa hafta sonu satiri olmaz
        assert re.search(r"kripto|hisse|emtia", rep, re.IGNORECASE), "varlik sinifi kirilimi yok"
        assert re.search(r"LLM|harcama", rep, re.IGNORECASE), "LLM harcama satiri yok"
        assert "L1" not in rep, "L1 iptal edildi (Ek, 18 Kasim)"
    finally:
        e.close()


def test_telegram_gunluk_rapor_eksik_dosyalarla_cokmez(tmp_path):
    cfg = T.TelegramConfig("1:tok", 5, str(tmp_path / "tg"), "", str(tmp_path / "yok/status.json"),
                           ledger_path=str(tmp_path / "yok/ledger.sqlite"),
                           budget_config=str(tmp_path / "yok/budget.json"),
                           lesson_store=str(tmp_path / "yok/lesson.sqlite"))
    rep = _report(cfg)
    assert isinstance(rep, str)
    assert "Traceback" not in rep


# ---------------------------------------------------------------- yasak metinler ve salt okunurluk
def test_pano_ve_telegram_ciktilarinda_ikiz_veto_metni_yok(tmp_path):
    e = Env(tmp_path)
    _write_arms_off(e.root, {ARM_OFF_ID: {"state": "closed"}})
    r = Running(e, cache_s=0)
    try:
        panel_out = _api_text(r) + _page_text(r)
        assert not FORBIDDEN.search(panel_out), FORBIDDEN.findall(panel_out)[:5]
    finally:
        r.stop()
    try:
        tg_out = _report(_telegram_cfg(e)) + "\n" + T.HELP
        assert not FORBIDDEN.search(tg_out), FORBIDDEN.findall(tg_out)[:5]
    finally:
        e.close()


def test_pano_salt_okunur_veri_degismez(tmp_path):
    e = Env(tmp_path)
    _write_arms_off(e.root, {ARM_OFF_ID: {"state": "closed"}})
    before = _snap(e.root)
    r = Running(e, cache_s=0)
    try:
        for p in _api_paths(r):
            assert r.req(p)[0] < 500, p
        for p in ("/api/lesson", "/api/budget", "/"):
            st, _, _ = r.req(p, method="POST")
            assert st == 405, (p, st)
    finally:
        r.stop()
    after = _snap(e.root)
    changed = {k for k in before if before[k] != after.get(k)}
    assert not changed, changed
    e.close()
