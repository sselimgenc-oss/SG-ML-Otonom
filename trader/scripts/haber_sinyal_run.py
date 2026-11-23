#!/usr/bin/env python3
"""Haber sinyali uretici (ust lig §1; saatlik, :08). Yeni basliklari Haiku 5.5 ile puanlar -> `var/learner/sinyal/haber_sinyal.json`.

Girdi: `var/veri/haber/haber.jsonl` (SALT OKUNUR; yalniz bu betik okur, motor okumaz: KARAR-8). Butce: servis `haber_kolu`,
anahtar ANTHROPIC_API_KEY_HABER. Butce reddi / anahtar yok / API hatasi: dosya yenilenmez (3 saatte bayatlar), cikis 0.
Test: `main(argv, client=, budget=, now_fn=, env=)`; `client.create(params) -> (metin, usage)`.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_core import haber_sinyal as HS  # noqa: E402

log = logging.getLogger("trader.haber_sinyal")


def main(argv=None, *, client=None, budget=None, now_fn=None, env=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--var-dir", type=Path, default=ROOT / "var")
    ap.add_argument("--config-dir", type=Path, default=ROOT / "config")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    env = os.environ if env is None else env
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    try:
        out = HS.kos(a.var_dir, a.config_dir, int(now.timestamp() * 1000), env, client=client, budget=budget)
    except Exception as e:  # noqa: BLE001  (sinyal hicbir seyi bozmaz: dosya bayatlar, cikis 0)
        log.error("haber sinyali hatasi: %s", type(e).__name__)
        return 0
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
