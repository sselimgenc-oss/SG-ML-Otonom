"""Sahip karari (Paket 2): kullanicinin gordugu HICBIR cikti 15 dakikalik zaman dilimini gostermez (pano, Telegram, raporlar, durum yayini).
15m yalniz motor ic isleyisinde (karar adimi, cikis/veri beslemesi) kalir; bu testin kapsami KULLANICI YUZU modulleridir."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESEN = re.compile(r"15m|15 ?dk|15 ?dakika|15dk|15 min", re.IGNORECASE)

KAPSAM = (
    sorted((ROOT / "src/trader_panel").rglob("*.py")) + sorted((ROOT / "src/trader_panel/static").glob("*"))
    + sorted((ROOT / "src/trader_reports").glob("*.py"))
    + [ROOT / "src/trader_core" / n for n in ("telegram.py", "tg_sade.py", "ml1_gorunum.py", "panel_pano.py", "panel_data.py", "mutabakat.py")]
    + [ROOT / "scripts" / n for n in ("mutabakat_run.py", "tur1_olcum_run.py", "tur1_haftalik_yorum_run.py", "gunluk_ozet.py", "telegram_run.py")]
    + [ROOT / "deploy" / n for n in ("panel_worker.js", "durum_yayinla.sh")]
)
# GOSTERIM DISI veri kodu: motorun 15 dk cikis/veri izgarasini okuyan raporlama girdileri (ekrana/rapora metin olarak CIKMAZ)
IZIN = {"src/trader_reports/inputs.py": "15m mum okuyucu (karar/cikis izgarasi verisi)",
        "src/trader_reports/exits.py": "cikis benzetimi 15m adim verisi"}


def test_kullanici_yuzunde_15dk_yok():
    bulunan = []
    for p in KAPSAM:
        if not p.is_file() or p.suffix in (".pyc", ".png", ".ico"):
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel in IZIN:
            continue
        for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if DESEN.search(ln):
                bulunan.append(f"{rel}:{i}: {ln.strip()[:100]}")
    assert not bulunan, "\n".join(bulunan)


def test_izin_listesi_dosyalari_var():
    for rel in IZIN:
        assert (ROOT / rel).is_file(), rel


def test_ml1_zd_sirasi_ve_tg_zd_adi_15m_icermez():
    from trader_core import ml1_gorunum as MG
    from trader_core import tg_sade as TG
    assert MG.ZD_SIRA == ("1h", "4h", "1d")
    assert "15m" not in TG._TF_TR
