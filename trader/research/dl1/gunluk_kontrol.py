#!/usr/bin/env python3
"""DL1 yedek tetik denetimi (stdlib; workflow `kontrol` isi). Yedek cron (02:00 UTC) calistiginda, zaman dilimi BASINA karar verir: yalniz bugun (UTC)
yenilenmemis paketler egitilir. Bir zaman dilimi hata verip is kirmizi bitse bile yedek kosu dort paketi birden degil, yalniz eksik olani yeniden egitir.
Paket "bugun yenilendi" = `models/dl1/DL1@<tf>.json` icindeki `olusturma` damgasinin UTC takvim gunu bugundur (dosya dalda; checkout bunu getirir).
Dosya yok/okunamaz/bozuk -> yenilenmedi sayilir (egitilir).

  python gunluk_kontrol.py --bugun 2026-11-25 --dizin trader/models/dl1 [--yedek]

stdout (GITHUB_OUTPUT'a eklenir): `egit_15m=0|1`, `egit_1h=..`, `egit_4h=..`, `egit_1d=..` ve `atla=1` (dortu de bugun yenilenmis: hic egitim yok) ya da `atla=0`.
`--yedek` verilmezse (ana cron, elle tetikleme) paketlere bakilmaz: dortu de egitilir."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ZAMAN_DILIMLERI = ("15m", "1h", "4h", "1d")


def bugun_yenilendi(yol: Path, bugun: str) -> bool:
    """Paket dosyasinin `olusturma` damgasi UTC'de `bugun` (YYYY-MM-DD) gunundeyse True; okunamayan/bozuk/eksik dosya False."""
    try:
        d = json.loads(Path(yol).read_text(encoding="utf-8"))
        t = datetime.fromisoformat(str(d["olusturma"]))
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc).date().isoformat() == bugun


def karar(dizin: Path, bugun: str, yedek: bool) -> dict[str, bool]:
    """tf -> egitilsin mi. Yedek degilse hepsi True."""
    return {tf: (not yedek) or not bugun_yenilendi(Path(dizin) / f"DL1@{tf}.json", bugun) for tf in ZAMAN_DILIMLERI}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--bugun", required=True, help="YYYY-MM-DD (UTC)")
    ap.add_argument("--dizin", type=Path, default=Path("trader/models/dl1"))
    ap.add_argument("--yedek", action="store_true", help="yedek cron: yalniz bugun yenilenmemis zaman dilimlerini egit")
    args = ap.parse_args(argv)
    k = karar(args.dizin, args.bugun, args.yedek)
    for tf, egit in k.items():
        print(f"egit_{tf}={'1' if egit else '0'}")
    print(f"atla={'0' if any(k.values()) else '1'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
