#!/usr/bin/env python3
"""Tur 1 / Asama A olcum raporu (gunluk; YALNIZ BILGI: botu degistirmez, islem engellemez, karar yoluna girmez).

Kagit defterini (kapanan islemler + karar satirlari) ve var/market.sqlite mumlarini SALT OKUNUR acar; alti bolum hesaplar
(rakip kiyasi, gecikme/masraf dayanikliligi, sans/kuyruk, canliya gecis sartlari, yon denetimi, kayip kumeleri; cekirdek:
`trader_reports.tur1_olcum`). Kilitli donem (HOLDOUT) okunmaz. Cikti: `<veri>/var/durum/tur1_olcum_v1.json` + `tur1_olcum.md`
(atomik); `deploy/durum_yayinla.sh` ikisini canli-durum dalinin ml/ klasorune yayimlar. Cikis: 0 (defter yoksa da); 2: defter okunamadi.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import panel_data as P  # noqa: E402
from trader_engine import arm_guard as AG  # noqa: E402
from trader_engine.fileio import atomic_write_text  # noqa: E402
from trader_panel.data import load_config  # noqa: E402
from trader_reports import inputs as I  # noqa: E402
from trader_reports import tur1_olcum as T  # noqa: E402

BOT = "learner"
DOSYA_JSON, DOSYA_MD = "tur1_olcum_v1.json", "tur1_olcum.md"


def data_root(env) -> Path:
    v = (env.get("TRADER_DATA_ROOT") or "").strip()
    return Path(v) if v and os.path.isabs(v) else _HERE.parent


def sinif_fonksiyonu(paper_cfg: Path):
    try:
        raw = json.loads(paper_cfg.read_text(encoding="utf-8"))
        cl = {k: SimpleNamespace(pairs=tuple(v.get("pairs", ()))) for k, v in (raw.get("clusters") or {}).items()}
    except (OSError, ValueError):
        cl = {}
    return lambda pair: AG.asset_class(pair, cl)


def masraf_ayari(root: Path, panel_engine_cfg: Path) -> dict | None:
    """Rastgele rakibin masrafı için kâğıt motor ayarı: `config/engine.paper.json` (yoksa panelin engine_config'i); okunamazsa None (eski masraf)."""
    for p in (root / "config" / "engine.paper.json", panel_engine_cfg):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def kos(root: Path, now: datetime, *, market: Path | None = None, runs: int = T.KARISTIRMA_SAYISI, b: int = T.RASTGELE_B) -> tuple[int, dict | None]:
    cfg = load_config(root / "config" / "panel.json")
    led_path = Path(cfg.ledger_path)
    if not led_path.exists():
        print("tur1_olcum: defter yok; atlandi", file=sys.stderr)
        return 0, None
    asset_of = sinif_fonksiyonu(Path(cfg.engine_config))
    try:
        led = P.open_ledger_ro(str(led_path), BOT)
    except Exception as e:  # noqa: BLE001
        print(f"tur1_olcum: defter okunamadi: {type(e).__name__}", file=sys.stderr)
        return 2, None
    try:
        kapali = led.list_closed_trades(None, None, P.CLOSED_MAX)
        dec_all = led.list_decisions()
    finally:
        led.close()
    dec = {d.id: d for d in dec_all}
    trades = [T.trade_dict(t, dec.get(t.decision_id), asset_of) for t in kapali if t.exit_ts is not None]
    decisions = [T.decision_dict(d, asset_of) for d in dec_all]
    try:
        ws = json.loads(Path(cfg.engine_config).read_text(encoding="utf-8")).get("wallet_start")
        ws = float(ws) if isinstance(ws, (int, float)) and not isinstance(ws, bool) and ws > 0 else 1000.0
    except (OSError, ValueError, AttributeError):
        ws = 1000.0
    mp = market or (root / "var" / "market.sqlite")
    mumlar = None
    try:
        if mp.exists():
            mumlar = T.MumDeposu(mp)
        d = T.rapor(trades, decisions, mumlar, kasa0=ws, now=now, models_dir=led_path.parent / "models", b=b, runs=runs,
                    maliyet_cfg=masraf_ayari(root, Path(cfg.engine_config)))
    finally:
        if mumlar is not None:
            mumlar.close()
    d["kasa_baslangic_kaynagi"] = "engine config wallet_start" if ws != 1000.0 else "varsayim 1000 (wallet_start okunamadi)"
    d["market_verisi"] = bool(mumlar)
    out = root / "var" / "durum"
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out / DOSYA_JSON, json.dumps(d, ensure_ascii=False, sort_keys=True, indent=1))
    atomic_write_text(out / DOSYA_MD, T.render_md(d))
    print(json.dumps({"status": "ok", "n": d["n_islem"], "file": str(out / DOSYA_JSON)}))
    return 0, d


def main(argv=None, *, now_fn=None, env=None) -> int:
    ap = argparse.ArgumentParser(prog="tur1_olcum_run.py")
    ap.add_argument("--once", action="store_true", required=True)
    ap.add_argument("--market", default=None)
    ap.add_argument("--runs", type=int, default=T.KARISTIRMA_SAYISI)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    env = os.environ if env is None else env
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    rc, _ = kos(data_root(env), now, market=Path(a.market) if a.market else None, runs=max(5000, a.runs))
    return rc


if __name__ == "__main__":
    sys.exit(main())
