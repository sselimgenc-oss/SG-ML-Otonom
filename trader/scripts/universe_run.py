#!/usr/bin/env python3
"""Aylik kagit evreni guncellemesi (DD-12 WP-16; D-T28). Ag cagrisi YOK.

SAHIP KARARI: evren 14 cift SABIT (config/engine.{paper,live}.json); hicbir sey bunu otomatik degistiremez. Bu betik yalniz
KURU KOSU raporu verir (bilgi amacli); `--apply` REDDEDILIR (cikis 1) ve hicbir dosya yazilmaz.
Kripto siralamasi: `--marketcap FILE` (JSON: {"items": [{"base"|"pair", "market_cap"}]}) verilirse o; verilmezse yedek:
market DB'deki `bars` tablosunda son 720 saatlik (1h) kapanis*hacim toplami (Binance quote-volume yaklasimi). Yedekte
evren yalniz market DB'de bar bulunan ciftlerle sinirlidir (yeni listelemeler gorunmez; rapora yazilir).
Hisse ve emtia sirasi config/universe.json'dan gelir. Cikis: 0 basarili, 1 kullanim/yapilandirma, 2 veri eksik.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
ROOT = _HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_core import universe as U  # noqa: E402
from trader_engine.errors import ConfigError  # noqa: E402

VOLUME_BARS = 720   # 1h bar: 30 gun


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def trading_pairs(market_db: Path) -> set[str]:
    """`rules` tablosunda kurali olan ciftler (feed yalniz TRADING + PERPETUAL/TRADIFI kurallarini yazar)."""
    with _ro(market_db) as c:
        return {r[0] for r in c.execute("SELECT pair FROM rules")}


def volume_candidates(market_db: Path, pairs: set[str]) -> list[dict]:
    out = []
    with _ro(market_db) as c:
        for pair in sorted(pairs):
            row = c.execute(
                "SELECT COALESCE(SUM(c*v),0) FROM (SELECT c, v FROM bars WHERE kind='last' AND tf='1h' AND pair=? "
                "ORDER BY open_ms DESC LIMIT ?)", (pair, VOLUME_BARS)).fetchone()
            out.append({"pair": pair, "score": float(row[0] or 0.0), "trading": True})
    return out


def marketcap_candidates(path: Path, trading: set[str]) -> list[dict]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    items = doc.get("items") if isinstance(doc, dict) else None
    if not isinstance(items, list):
        raise ConfigError("marketcap dosyasi {\"items\": [...]} bicimde olmali")
    out = []
    for it in items:
        pair = it.get("pair") or (f"{str(it.get('base', '')).upper()}/USDT" if it.get("base") else None)
        if not pair or not U._PAIR_RE.match(pair):
            continue
        out.append({"pair": pair, "score": float(it.get("market_cap") or 0.0), "trading": pair in trading})
    return out


def open_pairs(state_db: Path, bot: str = "learner") -> set[str]:
    if not state_db.is_file():
        return set()
    with _ro(state_db) as c:
        return {r[0] for r in c.execute(
            "SELECT DISTINCT pair FROM positions WHERE bot=? AND status IN ('opening','open','closing')", (bot,))}


def build(config_dir: Path, var_dir: Path, marketcap: Path | None, now: datetime) -> tuple[dict, dict]:
    cfg = json.loads((config_dir / "universe.json").read_text(encoding="utf-8"))
    paper = json.loads((config_dir / "engine.paper.json").read_text(encoding="utf-8"))
    market_db = var_dir / "market.sqlite"
    if not market_db.is_file():
        raise FileNotFoundError(f"market DB yok: {market_db}")
    trading = trading_pairs(market_db)
    if marketcap is not None:
        source = "marketcap"
        cands = marketcap_candidates(marketcap, trading)
    else:
        source = "volume_fallback"
        cands = volume_candidates(market_db, trading)
    crypto = U.select_crypto(cands, exclude_bases=cfg["exclude_bases"], n=int(cfg["n_crypto"]))
    stocks = U.select_stocks(cfg["stocks_ordered"], trading, n=int(cfg["n_stocks"]))
    comm = list(cfg["commodities"])
    cur = var_dir / "universe" / "paper_pairs.json"
    effective_old = list(paper["pairs"])
    if cur.is_file():
        try:
            effective_old = list(json.loads(cur.read_text(encoding="utf-8"))["pairs"])
        except (ValueError, KeyError, TypeError):
            effective_old = list(paper["pairs"])   # bozuk eski kaplama: karsilastirma temeli engine.paper.json
    held = sorted(open_pairs(var_dir / "learner" / "state.sqlite") - set(crypto) - set(stocks) - set(comm))
    composed = U.compose(crypto, stocks, comm, keep=held)
    notes = []
    if source == "volume_fallback":
        notes.append("kripto siralamasi: market DB 30 gunluk hacim yedegi (piyasa degeri kaynagi yok)")
    dropped_stocks = [p for p in cfg["stocks_ordered"] if p not in stocks]
    if dropped_stocks:
        notes.append(f"TRADING degil / yedek yok, evrenden cikti: {dropped_stocks}")
    if held:
        notes.append(f"acik pozisyonlu, evrende tutulan (yeni giris kapisi motorda dogrulanmali): {held}")
    not_trading_comm = [p for p in comm if p not in trading]
    if not_trading_comm:
        notes.append(f"emtia TRADING degil (listede kalir, o cift bekler): {not_trading_comm}")
    doc = U.overlay_document(composed["pairs"], composed["optional_pairs"], generated_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             source=source, notes=notes, retired=held)
    d = U.diff_pairs(effective_old, composed["pairs"])
    report = {"source": source, "pairs_count": len(doc["pairs"]), "added": d["added"], "removed": d["removed"],
              "crypto": crypto, "stocks": stocks, "notes": notes}
    return doc, report


def main(argv=None, *, now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(description="Aylik kagit evreni (WP-16). Varsayilan kuru kosu.")
    ap.add_argument("--config-dir", type=Path, default=ROOT / "config")
    ap.add_argument("--var-dir", type=Path, default=ROOT / "var")
    ap.add_argument("--marketcap", type=Path, default=None, help="piyasa degeri JSON (yoksa hacim yedegi)")
    ap.add_argument("--apply", action="store_true", help="REDDEDILIR: evren 14 cift sabittir, kaplama yazilmaz")
    a = ap.parse_args(argv)
    if a.apply:
        print("HATA: --apply reddedildi. Evren 14 cift SABIT (sahip karari); aylik evren kaplamasi kaldirildi, "
              "var/universe/paper_pairs.json yazilmaz. Liste yalniz sahibi tarafindan config/engine.{paper,live}.json'da degistirilir.",
              file=sys.stderr)
        return 1
    now = now or datetime.now(timezone.utc)
    try:
        doc, report = build(a.config_dir, a.var_dir, a.marketcap, now)
    except (OSError, ValueError, KeyError, ConfigError, sqlite3.Error) as e:
        print(f"HATA: {e}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("KURU KOSU: hicbir sey yazilmadi (evren sabit; bu rapor yalniz bilgidir).")
    return 0

if __name__ == "__main__":
    sys.exit(main())
