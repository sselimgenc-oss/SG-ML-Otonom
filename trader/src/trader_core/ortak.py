"""Ortak yardimcilar: anahtar maskeleme (`scrub`), zaman bicimi (`fmt_ts`) ve Anthropic Batch API istemcisi.

Ders sistemi kaldirildi (25.11); yorumcu, haftalik ozet ve Telegram'in kullandigi kucuk ortak parcalar burada kalir.
Standart kutuphane; `anthropic` SDK bu modulde ice aktarilmaz (istemci disaridan verilir). Anahtar degeri hicbir yere
yazilmaz/yazdirilmaz/saklanmaz. Gercek API hicbir testte cagrilmaz.
"""
from __future__ import annotations

import contextlib
import dataclasses
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from trader_core import budget as _budget_mod

UTC = timezone.utc
_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]*")


class LlmHttpError(Exception):
    """Saglayicidan HTTP yanitli hata."""

    def __init__(self, status_code: int | None, error_type: str | None = None, error_code: str | None = None,
                 message: str = "", retry_after_s: float | None = None):
        super().__init__(message or f"http {status_code}")
        self.status_code, self.error_type, self.error_code = status_code, error_type, error_code
        self.message, self.retry_after_s = message, retry_after_s


class LlmConnectionError(Exception):
    """Yanitsiz hata (zaman asimi / baglanti)."""


def scrub(text: Any) -> str:
    """API anahtari benzeri dizgileri (sk-ant-...) tamamen atar (metinde `sk-ant-` kalmaz)."""
    return _KEY_RE.sub("[redacted]", str(text))


def fmt_ts(dt: datetime) -> str:
    d = dt.astimezone(UTC)
    return d.strftime("%Y-%m-%dT%H:%M:%S") + ".%03dZ" % (d.microsecond // 1000)


def _num_ok(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


@dataclass(frozen=True)
class BatchResult:
    custom_id: str
    result_type: str                      # succeeded | errored | expired | canceled
    text: str | None = None
    stop_reason: str | None = None
    usage: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class BatchPoll:
    status: str                           # in_progress | ended | canceling
    results: tuple = ()



def _g(obj, name, default=None):
    v = obj.get(name) if isinstance(obj, Mapping) else getattr(obj, name, None)
    return default if v is None else v


def _usage_dict(usage) -> dict:
    if isinstance(usage, Mapping):
        return {str(k): v for k, v in usage.items() if _num_ok(v) or v is None or isinstance(v, (str, Mapping))}
    if dataclasses.is_dataclass(usage):
        return {f.name: getattr(usage, f.name) for f in dataclasses.fields(usage)}
    return {k: getattr(usage, k) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens")
            if hasattr(usage, k)}


def budget_usage(usage) -> "_budget_mod.Usage":
    """Yanittaki `usage`'tan birebir (5m/1h kirilimi yoksa toplam 1sa yazilir; butce-spec 6)."""
    if usage is None:
        return _budget_mod.Usage()
    cc = _g(usage, "cache_creation", None)
    w5 = w1 = 0
    if cc is not None:
        w5 = int(_g(cc, "ephemeral_5m_input_tokens", 0))
        w1 = int(_g(cc, "ephemeral_1h_input_tokens", 0))
    else:
        w1 = int(_g(usage, "cache_creation_input_tokens", 0))
    return _budget_mod.Usage(input_tokens=int(_g(usage, "input_tokens", 0)),
                             output_tokens=int(_g(usage, "output_tokens", 0)),
                             cache_write_5m_tokens=w5, cache_write_1h_tokens=w1,
                             cache_read_tokens=int(_g(usage, "cache_read_input_tokens", 0)))



class AnthropicBatchClient:
    """Batch API istemcisi (submit/poll/cancel). SDK istemcisi `client=` ile disaridan verilir (`max_retries=0`);
    anahtar bu sinifta okunmaz, hicbir yere yazilmaz."""

    def __init__(self, *, client):
        self._client = client

    @staticmethod
    def _map(e: Exception) -> Exception:
        sc = getattr(e, "status_code", None)
        if isinstance(sc, int):
            body = getattr(e, "body", None)
            err = body.get("error", {}) if isinstance(body, Mapping) else {}
            hdr = getattr(getattr(e, "response", None), "headers", None)
            ra = None
            try:
                ra = float(hdr.get("retry-after")) if hdr is not None and hdr.get("retry-after") else None
            except (TypeError, ValueError):
                ra = None
            return LlmHttpError(sc, err.get("type") if isinstance(err, Mapping) else None,
                                err.get("code") if isinstance(err, Mapping) else None, scrub(e)[:300], ra)
        return LlmConnectionError(scrub(e)[:300])

    def submit(self, bundle, custom_id: str) -> str:
        try:
            b = self._client.messages.batches.create(
                requests=[{"custom_id": custom_id, "params": dict(bundle.params)}])
        except Exception as e:  # noqa: BLE001
            raise self._map(e) from None
        return str(b.id)

    def poll(self, batch_id: str) -> BatchPoll:
        try:
            b = self._client.messages.batches.retrieve(batch_id)
            status = _g(b, "processing_status", "in_progress")
            if status != "ended":
                return BatchPoll("in_progress" if status == "in_progress" else str(status))
            out = []
            for ent in self._client.messages.batches.results(batch_id):
                res = _g(ent, "result")
                rtype = _g(res, "type", "errored")
                text = stop = usage = None
                if rtype == "succeeded":
                    msg = _g(res, "message")
                    text = "".join(_g(c, "text", "") for c in (_g(msg, "content", []) or [])
                                   if _g(c, "type") == "text")
                    stop = _g(msg, "stop_reason")
                    u = _g(msg, "usage")
                    usage = u.model_dump() if hasattr(u, "model_dump") else (dict(u) if u is not None else None)
                out.append(BatchResult(_g(ent, "custom_id"), rtype, text, stop, usage))
            return BatchPoll("ended", tuple(out))
        except Exception as e:  # noqa: BLE001
            raise self._map(e) from None

    def cancel(self, batch_id: str) -> None:
        with contextlib.suppress(Exception):
            self._client.messages.batches.cancel(batch_id)
