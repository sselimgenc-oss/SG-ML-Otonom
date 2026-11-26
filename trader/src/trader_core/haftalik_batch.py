"""Haftalik YZ raporlari icin Message Batches API yardimcisi (24 Kasim 2026 kullanici karari: promosyon kredisi yalniz Batch'i kapsar).

Kullananlar: `scripts/weekly_summary_run.py`, `scripts/tur1_haftalik_yorum_run.py`. `ortak.AnthropicBatchClient`
(submit/poll/cancel) kullanilir; yeni SDK ya da istemci yok. Akis: GONDER (butce `authorize` (batch fiyatli tahmin) -> `client.submit` ->
durum dosyasi: batch kimligi + butce rezervi) ve sonraki kosularda TOPLA (`client.poll`; bitince `record(..., batch=True)`, basarisizsa
`release`). Durum dosyasi diskte tutulur: ayni hafta icin ikinci gonderim yapilmaz.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from trader_core import budget as _budget
from trader_core import ortak as ORT

log = logging.getLogger("trader.haftalik_batch")
POLL_ARALIK_S = 30.0
BAYAT_S = 36 * 3600            # Batch en gec 24 saatte biter; bunun otesi icin vazgec (iptal + rezervi serbest birak)
SUBMITTED, DONE, FAILED = "submitted", "done", "failed"


@dataclass(frozen=True)
class Sonuc:
    durum: str                  # pending | ok | failed
    metin: str | None = None
    neden: str | None = None
    usage: Any = None


def utc_iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- durum dosyasi
def durum_oku(p: Path) -> dict | None:
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def durum_yaz(p: Path, d: dict) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def _grant_dict(grant: Any) -> dict:
    if dataclasses.is_dataclass(grant) and not isinstance(grant, type):
        return dataclasses.asdict(grant)
    return {"grant_id": getattr(grant, "grant_id", None)}


def _grant_nesne(d: dict, service: str):
    try:
        return _budget.Grant(**d)
    except TypeError:
        return SimpleNamespace(**d, service=service)


# ---------------------------------------------------------------- istemci / telegram
def varsayilan_istemci(env, b, service: str, timeout_s: float = 60.0):
    """Anahtar yoksa None. Anahtar yalniz ortamdan okunur, hicbir yere yazilmaz."""
    key = env.get(b.api_key_env(service))
    if not key:
        return None
    import anthropic  # noqa: PLC0415  (mevcut SDK; yeni bagimlilik yok)
    return ORT.AnthropicBatchClient(client=anthropic.Anthropic(api_key=key, max_retries=0, timeout=timeout_s))


def telegram_yaz(tg_dir: Path, text: str, dedup_key: str, now: datetime) -> bool:
    try:
        from trader_core.telegram import Outbox  # noqa: PLC0415
        return bool(Outbox(Path(tg_dir), lambda: now).enqueue({"text": text, "severity": "INFO", "dedup_key": dedup_key,
                                                               "expires_at": None, "reply_markup": None,
                                                               "created_at": now.timestamp()}))
    except Exception as e:  # noqa: BLE001
        log.warning("telegram yazilamadi: %s", type(e).__name__)
        return False


# ---------------------------------------------------------------- gonder
def gonder(client, b, service: str, model: str, params: dict, est_in_tokens: int, max_out: int, custom_id: str,
           hafta: str, now: datetime) -> tuple[dict | None, str]:
    """(durum | None, neden). Butce: authorize -> submit; submit hatasinda release. Reddedilirse API'ye gidilmez."""
    try:
        est = b.estimate_cost(model, max(1, est_in_tokens), max_out, batch=True)
    except Exception as e:  # noqa: BLE001  (model fiyat tablosunda yok vb.)
        log.warning("maliyet tahmini yapilamadi: %s", ORT.scrub(e))
        return None, "no_price"
    grant = b.authorize(service, est)
    if not hasattr(grant, "grant_id"):
        return None, "budget_denied"
    try:
        bid = client.submit(SimpleNamespace(params=params), custom_id)
    except Exception as e:  # noqa: BLE001
        try:
            b.release(grant)
        except Exception as e2:  # noqa: BLE001
            log.error("butce serbest birakilamadi: %s", ORT.scrub(e2))
        log.warning("batch gonderilemedi: %s", ORT.scrub(type(e).__name__))
        return None, "llm_error"
    return {"hafta": hafta, "batch_id": str(bid), "custom_id": custom_id, "model": model, "service": service,
            "grant": _grant_dict(grant), "submitted_at": utc_iso(now), "durum": SUBMITTED}, "submitted"


# ---------------------------------------------------------------- topla
_NEDEN = {"expired": "batch süresi doldu", "errored": "batch hatası", "canceled": "batch iptal edildi",
          "succeeded": "model boş cevap verdi"}


def _yokla(client, st: dict) -> Sonuc:
    cid = st["custom_id"]
    try:
        pr = client.poll(st["batch_id"])
    except Exception as e:  # noqa: BLE001
        if getattr(e, "status", None) == 404 or getattr(e, "status_code", None) == 404:
            return Sonuc("failed", neden="batch bulunamadı")
        log.warning("batch yoklanamadi (sonraki kosuda tekrar): %s", ORT.scrub(type(e).__name__))
        return Sonuc("pending")
    if pr.status != "ended":
        return Sonuc("pending")
    sonuclar = [r for r in pr.results if r.custom_id == cid]
    for r in sonuclar:
        if r.result_type == "succeeded" and (r.text or "").strip():
            return Sonuc("ok", metin=r.text.strip(), usage=r.usage)
    tur = sonuclar[0].result_type if sonuclar else "yok"
    return Sonuc("failed", neden=_NEDEN.get(tur, "batch sonucu alınamadı"))


def topla(client, st: dict, now: datetime, b, *, bekle_s: float = 0.0, sleep=time.sleep) -> Sonuc:
    """Bekleyen bir batch'i yokla (en cok `bekle_s` sn bekler). Bitince butceyi kapatir: basarida `record(batch=True)`,
    basarisizlikta `release`. Bitmediyse `pending` (butce rezervi acik kalir; sonraki kosu tekrar dener)."""
    service, model = st["service"], st["model"]
    gecen = 0.0
    while True:
        sn = _yokla(client, st)
        if sn.durum == "pending":
            try:
                bayat = (now - _parse(st["submitted_at"])).total_seconds() + gecen > BAYAT_S
            except (KeyError, ValueError):
                bayat = False
            if bayat:
                try:
                    client.cancel(st["batch_id"])
                except Exception:  # noqa: BLE001
                    pass
                sn = Sonuc("failed", neden="batch zamanında bitmedi")
            elif gecen < bekle_s:
                sleep(POLL_ARALIK_S)
                gecen += POLL_ARALIK_S
                continue
            else:
                return sn
        grant = _grant_nesne(st.get("grant") or {}, service)
        if sn.durum == "ok":
            try:
                b.record(service, grant, ORT.budget_usage(sn.usage), model, True)
            except Exception as e:  # noqa: BLE001
                log.error("butce kaydi yazilamadi: %s", ORT.scrub(e))
            return sn
        try:
            b.release(grant)
        except Exception as e:  # noqa: BLE001
            log.error("butce serbest birakilamadi: %s", ORT.scrub(e))
        return sn
