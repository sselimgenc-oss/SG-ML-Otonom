#!/usr/bin/env python3
"""Haftalik disk bakimi (yalniz temizlik; motor/karar/kol ayarlari degismez). Tek seferlik, hata tolere eder, cikis 0.

1) `var/` altindaki sqlite dosyalari: WAL checkpoint(TRUNCATE) + yalniz guvenliyse VACUUM. Motorun/feed'in surekli acik tuttugu defterlerde
   (LIVE_ACIK_AD: market.sqlite, ledger.sqlite, state.sqlite) VACUUM YOK; yalniz `PRAGMA wal_checkpoint(PASSIVE)` (kilit/cakisma riski yok).
   Diger dosyalarda VACUUM yalniz ozel kilit hemen alinirsa ve bos yer yeterliyse yapilir (yoksa atlanir).
2) Eski ciktilar: SILME_IZIN (acik glob listesi) disinda hicbir sey silinmez; KORUNAN ad/yol asla silinmez (izin listesi eslesse bile).
   Saklama suresi: koddaki mevcut kural yok -> 90 gun (mtime). Silinenler ozetle loglanir.
journald'a dokunulmaz."""
from __future__ import annotations

import argparse
import fnmatch
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

log = logging.getLogger("bakim")

SAKLAMA_GUN = 90
LIVE_ACIK_AD = ("market.sqlite", "ledger.sqlite", "state.sqlite")     # feed/motor/oi surekli acik: yalniz PASSIVE checkpoint
VACUUM_BOS_YER_CARPAN = 2.0                                          # VACUUM gecici kopya: dosya boyutunun >= 2 kati bos yer
# Silme izin listesi: (var'a gore glob, "dosya" | "dizin"). Yalniz bunlar silinebilir.
SILME_IZIN = (
    ("rapor/**/*.md", "dosya"), ("rapor/**/*.json", "dosya"), ("rapor/**/*.csv", "dosya"),
    ("rapor/**/*.txt", "dosya"), ("rapor/**/*.html", "dosya"), ("rapor/**/*.png", "dosya"),
    ("rapor/tutarlilik/.work/*", "dizin"),                    # tutarlilik geri test calisma dizinleri
    ("*/weekly_summaries/*.md", "dosya"), ("weekly_summaries/*.md", "dosya"),
    ("**/exitcf_bt_*", "dizin"),                              # exit_counterfactual gecici gocurulmus defter kopyasi
    ("snapshots/*", "dosya"), ("*/snapshots/*", "dosya"),
)
GECICI_DIZIN_AD = "exitcf_bt_*"                              # sistem gecici dizininde (tempfile.gettempdir) de aranir
# Asla silinmez: ad (fnmatch) ve var'a gore yol onekleri
KORUNAN_AD = ("ledger.sqlite*", "counterfactual.sqlite*", "exit_counterfactual.sqlite*", "market.sqlite*", "state.sqlite*",
              "*.sqlite", "*.sqlite-wal", "*.sqlite-shm", "*.feather", "PAUSE.*", "status.json", "pause_audit.jsonl")
KORUNAN_ONEK = ("history", "durum", "vision_raw")           # var/history*, var/durum/*.json, ...


def korunan_mi(yol: Path, var: Path) -> bool:
    try:
        rel = yol.resolve().relative_to(var.resolve())
    except ValueError:
        return True                                          # var disi: dokunma
    if any(rel.parts[0].startswith(p) for p in KORUNAN_ONEK):
        return True
    return any(fnmatch.fnmatch(yol.name, k) for k in KORUNAN_AD)


def _yas_gun(p: Path, now: float) -> float:
    return (now - p.stat().st_mtime) / 86400.0


def silme_adaylari(var: Path, now: float, saklama_gun: int = SAKLAMA_GUN, gecici_kok: Path | None = None) -> list[tuple[Path, str]]:
    """Saf (yan etkisiz): silinecek (yol, tur) listesi. Her dizindeki en yeni .md/.json dosya (pano 'son rapor') korunur."""
    out: dict[Path, str] = {}
    var = var.resolve()
    kokler = [(var, SILME_IZIN)]
    if gecici_kok is not None:
        kokler.append((gecici_kok, ((GECICI_DIZIN_AD, "dizin"),)))
    for kok, izin in kokler:
        if not kok.is_dir():
            continue
        for pat, tur in izin:
            for p in kok.glob(pat):
                try:
                    if p.is_symlink():
                        continue
                    if (tur == "dosya" and not p.is_file()) or (tur == "dizin" and not p.is_dir()):
                        continue
                    if kok == var and korunan_mi(p, var):
                        continue
                    if _yas_gun(p, now) > saklama_gun:
                        out[p] = tur
                except OSError:
                    continue
    # her dizinde en yeni dosya kalir (son rapor/ozet panoda gosterilir)
    by_dir: dict[Path, list[Path]] = {}
    for p, tur in out.items():
        if tur == "dosya":
            by_dir.setdefault(p.parent, []).append(p)
    for d, ps in by_dir.items():
        try:
            tum = [q for q in d.iterdir() if q.is_file() and q.suffix in {".md", ".json", ".csv", ".txt", ".html", ".png"}]
            en_yeni = max(tum, key=lambda q: q.stat().st_mtime, default=None)
        except OSError:
            continue
        if en_yeni in out:
            del out[en_yeni]
    return sorted(out.items())


def sil(adaylar, var: Path, dry_run: bool = False) -> dict:
    n_dosya = n_dizin = 0
    bayt = 0
    for p, tur in adaylar:
        try:
            if tur == "dosya":
                b = p.stat().st_size
                if not dry_run:
                    p.unlink()
                n_dosya += 1
            else:
                b = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                if not dry_run:
                    shutil.rmtree(p)
                n_dizin += 1
            bayt += b
            log.info("silindi%s: %s (%s)", " (kuru)" if dry_run else "", p, tur)
        except OSError as e:
            log.warning("silinemedi: %s (%s)", p, e)
    # bos kalan rapor alt dizinleri toplanmaz (dizin yapisi install.sh'e ait)
    return {"dosya": n_dosya, "dizin": n_dizin, "bayt": bayt}


def sqlite_dosyalari(var: Path) -> list[Path]:
    out = []
    for p in sorted(var.rglob("*.sqlite")):
        try:
            rel = p.relative_to(var).parts
            if p.is_file() and not p.is_symlink() and not rel[0].startswith(("history", "vision_raw")) \
                    and not any(x == ".work" or x.startswith("exitcf_bt_") for x in rel):
                out.append(p)
        except (OSError, ValueError):
            continue
    return out


def sqlite_bakim(p: Path, bos_yer_fn=None, vacuum_izin: bool = True) -> str:
    """Tek dosya. Donus: 'passive' | 'truncate' | 'vacuum' | 'atlandi:<neden>'. Hata disari cikmaz."""
    bos_yer_fn = bos_yer_fn or (lambda q: shutil.disk_usage(q.parent).free)
    live = p.name in LIVE_ACIK_AD
    try:
        con = sqlite3.connect(str(p), timeout=2.0, isolation_level=None)
    except sqlite3.Error as e:
        return f"atlandi:acilamadi({e})"
    try:
        con.execute("PRAGMA busy_timeout=2000")
        if live:
            con.execute("PRAGMA wal_checkpoint(PASSIVE)")
            return "passive"
        r = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if r and r[0] == 1:                                  # busy: baska baglanti var -> VACUUM deneme
            return "atlandi:kilitli(checkpoint)"
        if not vacuum_izin:
            return "truncate"
        if bos_yer_fn(p) < VACUUM_BOS_YER_CARPAN * p.stat().st_size:
            return "truncate"
        try:
            con.execute("BEGIN EXCLUSIVE")                   # kilit hemen alinamazsa (baska yazar/okuyucu) VACUUM yok
            con.execute("ROLLBACK")
        except sqlite3.Error:
            return "truncate"
        con.execute("VACUUM")
        return "vacuum"
    except sqlite3.Error as e:
        return f"atlandi:{type(e).__name__}({e})"
    finally:
        try:
            con.close()
        except sqlite3.Error:
            pass


def kos(var: Path, now: float | None = None, saklama_gun: int = SAKLAMA_GUN, gecici_kok: Path | None = None,
        dry_run: bool = False, bos_yer_fn=None) -> dict:
    now = time.time() if now is None else now
    ozet = {"sqlite": {}, "silinen": {}}
    for p in sqlite_dosyalari(var) if var.is_dir() else []:
        try:
            ozet["sqlite"][str(p)] = sqlite_bakim(p, bos_yer_fn, vacuum_izin=not dry_run) if not dry_run else "kuru"
        except Exception as e:  # noqa: BLE001  (bir dosyanin hatasi digerlerini durdurmaz)
            ozet["sqlite"][str(p)] = f"atlandi:{type(e).__name__}"
        log.info("sqlite %s -> %s", p, ozet["sqlite"][str(p)])
    try:
        ozet["silinen"] = sil(silme_adaylari(var, now, saklama_gun, gecici_kok), var, dry_run)
    except Exception as e:  # noqa: BLE001
        log.warning("temizlik hatasi: %s", e)
    log.info("ozet: sqlite=%d dosya, silinen=%s", len(ozet["sqlite"]), ozet["silinen"])
    return ozet


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--var-dir", default=str(Path(__file__).resolve().parent.parent / "var"))
    ap.add_argument("--saklama-gun", type=int, default=SAKLAMA_GUN)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(levelname)s %(message)s")
    try:
        kos(Path(a.var_dir), saklama_gun=a.saklama_gun, gecici_kok=Path(tempfile.gettempdir()), dry_run=a.dry_run)
    except Exception as e:  # noqa: BLE001
        log.warning("bakim beklenmeyen hata (yutuldu): %s", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
