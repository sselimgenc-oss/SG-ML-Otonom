#!/usr/bin/env python3
"""Piyasa pozisyon verisi toplayici (YALNIZ KAYIT; docs/veri-toplama-spec.md). Saatlik, tek seferlik.

Binance USDⓈ-M herkese acik GET uclari (anahtar yok) -> `<var>/veri/piyasa/<uc>/<SEMBOL>.jsonl` (yalniz-ekleme). 19 kripto cifti
(engine.paper.json pairs - optional_pairs; yoksa engine.base.json). Ban dosyasi OI toplayicisiyla ortaktir. Cikis: 0 tamam; 2 kismi hata; 3 ban/429; 6 HTTP 451; 1 beklenmeyen.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core.ban_store import BanGuard, ban_dir_for, ban_path  # noqa: E402
from trader_engine.marketdata import oi_collector as C  # noqa: E402
from trader_engine.marketdata import veri_piyasa as V  # noqa: E402

log = logging.getLogger("trader.veri_piyasa.run")
EXIT_OK, EXIT_CRASH, EXIT_PARTIAL, EXIT_BAN, EXIT_GEO = 0, 1, 2, 3, 6


def kripto_ciftleri(config_dir: Path) -> tuple[list[str], str]:
    base = json.loads((config_dir / "engine.base.json").read_text(encoding="utf-8"))
    paper = config_dir / "engine.paper.json"                      # 19 kripto + hisse/emtia (optional_pairs); yalniz OKUNUR
    cfg = json.loads(paper.read_text(encoding="utf-8")) if paper.exists() else base
    opt = set(cfg.get("optional_pairs") or [])
    db = base["market_db"]
    if not Path(db).is_absolute():
        db = str(config_dir.resolve().parent / db)
    return [p for p in cfg["pairs"] if p not in opt], db


def main(argv=None, *, client=None, now_ms: int | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config-dir", default=str(_HERE.parent / "config"))
    ap.add_argument("--var-dir", default=str(_HERE.parent / "var"))
    ap.add_argument("--pairs", default=None)
    ap.add_argument("--max-requests", type=int, default=900)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        pairs, db_path = kripto_ciftleri(Path(a.config_dir))
        if a.pairs:
            pairs = [p.strip() for p in a.pairs.split(",") if p.strip()]
        now = int(time.time() * 1000) if now_ms is None else now_ms
        clock = (lambda: now) if now_ms is not None else (lambda: int(time.time() * 1000))
        guard = BanGuard(ban_path(ban_dir_for(db_path), C.BASE_URL), source="veri_piyasa", now_ms=clock)
        rec = guard.active()
        if rec is not None:
            log.warning("event=ban_skip host=%s", rec.host)
            return EXIT_OK
        if client is None:
            client = C.HttpClient(ban_guard=guard, now_ms=clock, min_interval_s=0.5)
        st = V.collect(Path(a.var_dir) / "veri" / "piyasa", client, pairs, now, max_requests=a.max_requests)
    except C.GeoBlockError as e:
        log.error("event=geoblock err=%s", e)
        return EXIT_GEO
    except C.BanError as e:
        log.error("event=ban err=%s", e)
        return EXIT_BAN
    except Exception:  # noqa: BLE001
        log.exception("event=crash")
        return EXIT_CRASH
    log.info("event=done pairs=%d rows=%d requests=%d errors=%d budget_hit=%s", len(pairs), st.rows, st.requests, st.errors, st.budget_hit)
    return EXIT_PARTIAL if st.errors else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
