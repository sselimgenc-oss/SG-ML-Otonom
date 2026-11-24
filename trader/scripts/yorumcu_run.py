#!/usr/bin/env python3
"""YZ yorumcu (ust lig §3; gunluk 05:40 UTC): dunun islemlerini/kararlarini/olcum raporunu sade Turkce yorumlar.

YETKISI YOK: yalniz `var/durum/yorumcu/YYYY-MM-DD.md` yazar (+ Telegram outbox'a kisa ozet). Motor bu dizini okumaz; ders sistemine bagli degil.
Girdi (hepsi SALT OKUNUR): kagit defteri (kapanmis islemler, kararlar), `var/durum/tur1_olcum_v1.json`, `alinmayan_sonuc_v1.json`,
haftalik ozetin sabit bolumu, bekleyen ders onerileri. Tum sayilar kodla hesaplanir (`trader_reports.yorumcu`); model yalniz yorumlar.
Model: claude-sonnet-5-5, MEVCUT `lesson.AnthropicBatchClient` (Batch API) + `budget` servisi `yorumcu` (anahtar: ANTHROPIC_API_KEY_YORUMCU).
Butce bitti / anahtar yok / API hatasi / defter yok: "bugün rapor yok: <neden>" dosyasi yazilir, cikis 0. Kilitli donem okunmaz.
Test: `main(argv, client=, budget=, now_fn=, env=, sleep=)`; `client.submit(bundle, custom_id)` / `client.poll(batch_id)`.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import budget as _budget  # noqa: E402
from trader_core import lesson as LS  # noqa: E402
from trader_core import panel_data as P  # noqa: E402
from trader_engine import arm_guard as AG  # noqa: E402
from trader_engine.fileio import atomic_write_text  # noqa: E402
from trader_panel.data import load_config  # noqa: E402
from trader_reports import tur1_olcum as T  # noqa: E402
from trader_reports import yorumcu as Y  # noqa: E402

log = logging.getLogger("trader.yorumcu")
BOT = "learner"
POLL_ARALIK_S = 30.0
POLL_AZAMI_S = 3000.0          # servis TimeoutStartSec=3300; batch bu surede bitmezse rapor yok
CUSTOM_ID = "yorumcu-gunluk"


def data_root(env) -> Path:
    v = (env.get("TRADER_DATA_ROOT") or "").strip()
    return Path(v) if v and os.path.isabs(v) else _HERE.parent


def cikti_dizini(root: Path) -> Path:
    return root / "var" / "durum" / "yorumcu"


def yaz(dizin: Path, tarih: str, metin: str) -> Path:
    """Tek yazma noktasi: yalniz `dizin` icine, `YYYY-MM-DD.md` adiyla (baska yol uretilemez)."""
    datetime.strptime(tarih, "%Y-%m-%d")
    dizin.mkdir(parents=True, exist_ok=True)
    hedef = (dizin / f"{tarih}.md").resolve()
    if hedef.parent != dizin.resolve():
        raise ValueError("yorumcu yalniz kendi dizinine yazar")
    atomic_write_text(hedef, metin)
    return hedef


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def haftalik_sabit(ledger_path: Path) -> list[str]:
    """Son haftalik ozetin '## Sabit bölüm' satirlari (yoksa bos)."""
    try:
        dosyalar = sorted((ledger_path.with_name("weekly_summaries")).glob("*.md"))
        if not dosyalar:
            return []
        govde = dosyalar[-1].read_text(encoding="utf-8")
        a = govde.index("## Sabit bölüm") + len("## Sabit bölüm")
        b = govde.find("\n## ", a)
        return [ln.strip() for ln in govde[a:b if b >= 0 else None].splitlines() if ln.strip()]
    except (OSError, ValueError):
        return []


def dersler(cfg, now: datetime) -> list[str]:
    """Bekleyen/acik ders onerileri (kisa metin); ders deposu yoksa bos. Ders sistemine YAZMAZ."""
    try:
        store = getattr(cfg, "lesson_store", None) or "user_data/lesson.sqlite"
        v = P.lesson_view(str(store), now, "")
        return [json.dumps(r, ensure_ascii=False, sort_keys=True)[:300] for r in (v.get("open_requests") or [])[:5]]
    except Exception:  # noqa: BLE001
        return []


def defteri_oku(root: Path):
    cfg = load_config(root / "config" / "panel.json")
    led_path = Path(cfg.ledger_path)
    if not led_path.exists():
        return cfg, led_path, None, None
    try:
        raw = json.loads(Path(cfg.engine_config).read_text(encoding="utf-8"))
        cl = {k: SimpleNamespace(pairs=tuple(v.get("pairs", ()))) for k, v in (raw.get("clusters") or {}).items()}
    except (OSError, ValueError):
        cl = {}
    asset_of = lambda pair: AG.asset_class(pair, cl)  # noqa: E731
    led = P.open_ledger_ro(str(led_path), BOT)
    try:
        kapali = led.list_closed_trades(None, None, P.CLOSED_MAX)
        dec_all = led.list_decisions()
    finally:
        led.close()
    dec = {d.id: d for d in dec_all}
    trades = [T.trade_dict(t, dec.get(t.decision_id), asset_of) for t in kapali if t.exit_ts is not None]
    return cfg, led_path, trades, [T.decision_dict(d, asset_of) for d in dec_all]


def varsayilan_istemci(env, b):
    key = env.get(b.api_key_env(Y.SERVICE))
    if not key:
        return None
    import anthropic  # noqa: PLC0415  (mevcut SDK; yeni bagimlilik yok)
    return LS.AnthropicBatchClient(client=anthropic.Anthropic(api_key=key, max_retries=0, timeout=60.0))


def telegram_gonder(root: Path, env, tarih: str, metin: str, now: datetime) -> bool:
    try:
        from trader_core.telegram import Outbox  # noqa: PLC0415
        tg = Path((env.get("TELEGRAM_VAR_DIR") or "").strip() or root / "var" / "telegram")
        ok = True
        for i, parca in enumerate(Y.telegram_parcalari(metin, tarih)):   # dosya adi zamandan: parcalar sirali gider
            ob = Outbox(tg, lambda i=i: now + timedelta(microseconds=i))
            ok = ob.enqueue({"text": parca, "severity": "INFO",
                             "dedup_key": f"yorumcu:{tarih}" + (f":{i}" if i else ""), "expires_at": None,
                             "reply_markup": None, "created_at": now.timestamp() + i * 1e-3}) and ok
        return ok
    except Exception as e:  # noqa: BLE001
        log.warning("telegram ozeti yazilamadi: %s", type(e).__name__)
        return False


def _batch_calistir(client, params: dict, sleep, sure_azami: float):
    """(metin, usage) | (None, neden). Batch gonder, bitene kadar yokla."""
    try:
        bid = client.submit(SimpleNamespace(params=params), CUSTOM_ID)
    except Exception as e:  # noqa: BLE001
        return None, f"API hatası ({LS.scrub(type(e).__name__)})"
    gecen = 0.0
    while True:
        try:
            pr = client.poll(bid)
        except Exception as e:  # noqa: BLE001
            return None, f"API hatası ({LS.scrub(type(e).__name__)})"
        if pr.status == "ended":
            for r in pr.results:
                if r.custom_id == CUSTOM_ID and r.result_type == "succeeded" and (r.text or "").strip():
                    return (r.text, r.usage), None
            return None, "model cevap vermedi (batch sonucu başarısız/boş)"
        if gecen >= sure_azami:
            try:
                client.cancel(bid)
            except Exception:  # noqa: BLE001
                pass
            return None, "batch zamanında bitmedi"
        sleep(POLL_ARALIK_S)
        gecen += POLL_ARALIK_S


def kos(root: Path, now: datetime, env, *, client=None, budget=None, sleep=time.sleep, force=False,
        sure_azami: float = POLL_AZAMI_S) -> dict:
    b = budget or _budget
    tarih = now.astimezone(timezone.utc).date().isoformat()
    dizin = cikti_dizini(root)
    if (dizin / f"{tarih}.md").exists() and not force:
        return {"status": "exists", "date": tarih}

    def yok(neden: str) -> dict:
        yol = yaz(dizin, tarih, Y.rapor_yok(tarih, neden))
        return {"status": "no_report", "reason": neden, "file": str(yol)}

    if client is None:
        try:
            client = varsayilan_istemci(env, b)
        except Exception as e:  # noqa: BLE001
            log.warning("LLM istemcisi kurulamadi: %s", LS.scrub(e))
            client = None
    if client is None:
        return yok("API anahtarı yok")
    try:
        cfg, led_path, trades, decisions = defteri_oku(root)
    except Exception as e:  # noqa: BLE001
        return yok(f"defter okunamadı ({type(e).__name__})")
    if trades is None:
        return yok("defter yok")
    durum = root / "var" / "durum"
    tablolar = Y.tablolari_kur(trades, decisions, now, olcum=_json(durum / "tur1_olcum_v1.json"),
                               alinmayan=_json(durum / "alinmayan_sonuc_v1.json"),
                               haftalik_sabit=haftalik_sabit(led_path), dersler=dersler(cfg, now))
    params = Y.parametreler(tablolar)
    est = b.estimate_cost(Y.MODEL, max(1, (len(Y.SYSTEM) + len(params["messages"][0]["content"])) // 3), Y.MAX_OUT, batch=True)
    grant = b.authorize(Y.SERVICE, est)
    if not hasattr(grant, "grant_id"):                    # Denial: butce yok => API'ye HIC gidilmez
        return yok(f"bütçe yok ({getattr(grant, 'reason', 'denied')})")
    sonuc, neden = _batch_calistir(client, params, sleep, sure_azami)
    if sonuc is None:
        try:
            b.release(grant)
        except Exception as e:  # noqa: BLE001
            log.error("butce serbest birakilamadi: %s", LS.scrub(e))
        return yok(neden)
    metin, usage = sonuc
    try:
        b.record(Y.SERVICE, grant, LS.budget_usage(usage), Y.MODEL, True)
    except Exception as e:  # noqa: BLE001
        log.error("butce kaydi yazilamadi: %s", LS.scrub(e))
    rapor, denetim = Y.raporu_denetle(metin, tablolar)
    yol = yaz(dizin, tarih, rapor)
    telegram_gonder(root, env, tarih, rapor, now)
    return {"status": "ok", "file": str(yol), "sayi_hatasi": denetim["sayi_hatasi"], "uyarilar": denetim["uyarilar"]}


def main(argv=None, *, client=None, budget=None, now_fn=None, env=None, sleep=time.sleep) -> int:
    ap = argparse.ArgumentParser(prog="yorumcu_run.py")
    ap.add_argument("--once", action="store_true", required=True)
    ap.add_argument("--force", action="store_true", help="bugunku rapor varsa yeniden yaz")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    env = os.environ if env is None else env
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    try:
        out = kos(data_root(env), now, env, client=client, budget=budget, sleep=sleep, force=a.force)
    except Exception as e:  # noqa: BLE001  (yorumcu hicbir seyi bozmaz: sessiz cik)
        print(json.dumps({"status": "error", "error": LS.scrub(type(e).__name__)}), file=sys.stderr)
        return 0
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
