#!/usr/bin/env python3
"""Strateji verisi (beyin firtinasi icin): kurulumdan sonra ve 6 saatte bir (zamanlayici) `strateji-veri-ml.md` dosyasini yeniler; dosyayi
tek SESSIZ Telegram BELGESI olarak yalniz BIR KEZ gonderir ("[ML] Strateji verisi (beyin fırtınası için)"). SALT OKUNUR: defter `read_only` + migrate yok; motoru etkilemez.

Tekrar gondermez: basarili gonderimden sonra `<veri>/var/durum/strateji_veri_gonderildi.json` {"surum": 1, ...} yazilir; kayit
SURUM >= bu betigin SURUM'u ise hicbir sey gonderilmez. Ikinci bir dosya icin SURUM sabiti artirilir. Gonderim basarisizsa kayit
yazilmaz (sonraki kurulum yeniden dener). Kilitli donem (2026-05-01 -> 2026-11-01) verisi okunmaz (SQL since + ayiklama).
Telegram: servisle ayni `/etc/trader-telegram.env` (unit EnvironmentFile) ve `TelegramClient.send_document` (disable_notification).
Cikis: 0 (gonderildi / zaten gonderilmis / anahtar yok); 1: gonderilemedi; 2: defter okunamadi.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import kol_yasam as KY  # noqa: E402
from trader_core import panel_data as P  # noqa: E402
from trader_core import strateji_veri as SV  # noqa: E402
from trader_core import telegram as T  # noqa: E402
from trader_core import tg_sade as TS  # noqa: E402
from trader_engine.fileio import atomic_write_text  # noqa: E402
from trader_panel.data import load_config  # noqa: E402

BOT = "learner"
SURUM = 1                                   # ikinci bir dosya gonderilecekse artirilir (isaret dosyasi surumu >= SURUM ise gonderilmez)
ISARET = "strateji_veri_gonderildi.json"
CIKTI = "strateji-veri-ml.md"
BASLIK = TS.ETIKET + SV.BASLIK              # "[ML] Strateji verisi (beyin fırtınası için)"


def data_root(env) -> Path:
    v = (env.get("TRADER_DATA_ROOT") or "").strip()
    return Path(v) if v and os.path.isabs(v) else _HERE.parent


def gonderildi_mi(durum: Path) -> bool:
    try:
        d = json.loads((durum / ISARET).read_text(encoding="utf-8"))
        return isinstance(d, dict) and int(d.get("surum", 0)) >= SURUM
    except (OSError, ValueError, TypeError):
        return False


def yapilandirilmis_kollar(config_dir: Path) -> list[str]:
    d = SV.json_oku(config_dir / "engine.paper.json") or {}
    arms = d.get("arms")
    return [str(a) for a in arms] if isinstance(arms, list) else []


def rapor_uret(root: Path, now: datetime) -> str | None:
    """Defteri SALT OKUNUR acar, markdown dondurur; defter yoksa None. Kilitli donem satirlari SQL'de bile istenmez."""
    cfg = load_config(root / "config" / "panel.json")
    led_path = Path(cfg.ledger_path)
    if not led_path.exists():
        return None
    led = P.open_ledger_ro(str(led_path), BOT)            # read_only=True, migrate=False
    try:
        kararlar = led.list_decisions(since_ts=SV.KILIT[1])
        kapali = led.list_closed_trades(since=SV.KILIT[1], limit=P.CLOSED_MAX)
        acik = led.list_open_trades()
    finally:
        led.close()
    by_id = {d.id: d for d in kararlar}
    islemler = SV.islem_satirlari(kapali, acik, by_id)
    kr = SV.karar_satirlari(kararlar)
    atlanan = (len(kapali) + len(acik) - len(islemler)) + (len(kararlar) - len(kr))
    arms_off = KY.read_arms_state(led_path.parent / "arms_off.json")           # yok/bozuk -> {} (hepsi acik)
    tut, tut_t = SV.tutarlilik_oku(root / "var" / "durum" / "tutarlilik_v1.json")
    doc = SV.hesapla(kollar=yapilandirilmis_kollar(root / "config"), islemler=islemler, kararlar=kr, simdi=now, tutarlilik=tut,
                     tut_veri=tut_t, arms_off=arms_off,
                     atlanan=atlanan)
    return SV.markdown(doc)


def kos(root: Path, now: datetime, env, http_post=None, dry_run: bool = False) -> int:
    durum = root / "var" / "durum"
    zaten = (not dry_run) and gonderildi_mi(durum)      # zamanlayici: dosya HER kosuda yenilenir (canli-durum dalina gider); Telegram yalniz bir kez
    try:
        md = rapor_uret(root, now)
    except Exception as e:  # noqa: BLE001
        print(f"strateji-veri: defter okunamadi ({type(e).__name__})", file=sys.stderr)
        return 2
    if md is None:
        print("strateji-veri: defter yok; atlandi", file=sys.stderr)
        return 0
    if dry_run:
        print(md)
        return 0
    atomic_write_text(durum / CIKTI, md)
    if zaten:
        print("strateji-veri: dosya yenilendi; Telegram'a zaten gonderilmis, tekrar gonderilmedi")
        return 0
    cfg = T.TelegramConfig.from_env(env)
    if cfg is None:
        print("strateji-veri: Telegram anahtari yok; gonderilmedi (dosya yazildi)", file=sys.stderr)
        return 0
    try:
        sonuc = T.TelegramClient(cfg.token, http_post).send_document(cfg.chat_id, CIKTI, md.encode("utf-8"), BASLIK,
                                                                      disable_notification=True)
    except T.TelegramError as e:
        print(f"strateji-veri: gonderilemedi: {T.mask(e, cfg.token)}", file=sys.stderr)
        return 1
    atomic_write_text(durum / ISARET, json.dumps(
        {"surum": SURUM, "gonderildi": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "mesaj_no": sonuc.get("message_id"),
         "sha256": hashlib.sha256(md.encode("utf-8")).hexdigest()}, ensure_ascii=False) + "\n")
    print("strateji-veri: gonderildi")
    return 0


def main(argv=None, now_fn=None, env=None, http_post=None) -> int:
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description="Strateji verisi: tek seferlik sessiz Telegram belgesi (salt okunur)")
    ap.add_argument("--once", action="store_true", help="bir kez calis (kurulum sonrasi birim)")
    ap.add_argument("--root", type=Path, default=None, help="veri kok dizini (varsayilan: TRADER_DATA_ROOT ya da kod koku)")
    ap.add_argument("--dry-run", action="store_true", help="yalniz markdown'i yazdir; gonderme, isaret yazma")
    a = ap.parse_args(argv)
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    return kos(a.root or data_root(env), now, env, http_post, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
