#!/usr/bin/env python3
"""Ham haber + Fear & Greed toplayici (YALNIZ KAYIT; docs/veri-toplama-spec.md). Saatlik, tek seferlik.

Yazar: `<var>/veri/haber/haber.jsonl` ve `fng.jsonl` (yalniz-ekleme, tekillestirilmis). Karar yoluna GIRMEZ.
Kaynak hatasi yutulur. Cikis: 0; 2 = yerel yazma hatasi.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_core import veri_haber as V  # noqa: E402


def kos(dizin: Path, simdi_ms: int, gj=None, gm=None) -> int:
    try:
        V.topla(dizin, simdi_ms, gj, gm)
    except OSError:
        return 2
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--var-dir", type=Path, default=ROOT / "var")
    a = ap.parse_args(argv)
    return kos(a.var_dir / "veri" / "haber", int(datetime.now(timezone.utc).timestamp() * 1000))


if __name__ == "__main__":
    sys.exit(main())
