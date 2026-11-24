#!/usr/bin/env python3
"""DL1 yedek tetik denetimi (stdlib; workflow `kontrol` isi). Yedek cron (02:00 UTC) calistiginda, ayni UTC gununde basarili bir DL1 kosusu
varsa egitim atlanir (GitHub schedule guvenilir degil: ana 01:00 kosusu tetiklenmezse yedek egitir, tetiklendiyse tekrar egitmez).

  gh run list --workflow dl1-egitim.yml --status success --json databaseId,createdAt,conclusion | python gunluk_kontrol.py --bugun 2026-11-25 --kendi-id 123

stdin: gh JSON listesi. stdout: `atla=1` (bugun, kendisi disinda basarili kosu var) ya da `atla=0` (GITHUB_OUTPUT'a eklenir)."""
from __future__ import annotations

import argparse
import json
import sys


def bugun_basarili_var(kosular: list, bugun: str, kendi_id: int | None = None) -> bool:
    """`createdAt` (ISO, UTC 'Z') bugun (YYYY-MM-DD) ile basliyan, `kendi_id` disindaki, basarili (conclusion yoksa ya da 'success') bir kosu var mi."""
    for k in kosular or []:
        if not isinstance(k, dict):
            continue
        if kendi_id is not None and str(k.get("databaseId")) == str(kendi_id):
            continue
        if k.get("conclusion") not in (None, "", "success"):
            continue
        if str(k.get("createdAt", "")).startswith(bugun):
            return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--bugun", required=True, help="YYYY-MM-DD (UTC)")
    ap.add_argument("--kendi-id", type=int, default=None)
    args = ap.parse_args(argv)
    try:
        kosular = json.load(sys.stdin)
    except ValueError:
        kosular = []                       # okunamazsa temkinli: egit (atla=0)
    print(f"atla={'1' if bugun_basarili_var(kosular, args.bugun, args.kendi_id) else '0'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
