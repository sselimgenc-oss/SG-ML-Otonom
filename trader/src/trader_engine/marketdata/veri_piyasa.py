"""Veri toplama (YALNIZ KAYIT): Binance USDⓈ-M herkese acik piyasa-pozisyon uclari -> `var/veri/piyasa/` (yalniz-ekleme JSONL).
Belirtim: docs/veri-toplama-spec.md. Bu veri HICBIR karar girdisi DEGILDIR (golge/ust lig hatti); motorun baska hicbir modulu bunu
iceri almaz ve bu dizini okumaz (tests/test_veri_toplama.py zorlar).

Uclar (period=1h, limit<=500; en fazla ~30 gun geriye): openInterestHist, globalLongShortAccountRatio, topLongShortPositionRatio,
takerlongshortRatio ve /fapi/v1/fundingRate. HTTP istemcisi ve ban korumasi mevcut `oi_collector` ile AYNIDIR (ortak ban dosyasi,
agirlik tavani, min aralik). Kilitli donem (HOLDOUT) zaman damgalari ne istenir ne yazilir.

Dosya: var/veri/piyasa/<uc>/<SEMBOL>.jsonl ; satir: {"ts": ms, <alanlar>} (alanlar yanit alanlari, sayilar float). `ts` API zaman damgasi AYNEN.
Yalniz son satirdan SONRAKI ts eklenir (tekillestirme + yalniz-ekleme); donemi henuz bitmemis olabilecek (ts > simdi-1sa) saatlik satir atlanir.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from trader_engine.marketdata import oi_collector as C
from trader_engine.types import pair_symbol

log = logging.getLogger("trader.veri_piyasa")

PERIOD = "1h"
PERIOD_MS = 3_600_000
PAGE_LIMIT = 500
FUNDING_LIMIT = 1000

# uc adi -> (yol, {depo alani: yanit alani})
HIST: dict[str, tuple[str, dict[str, str]]] = {
    "oi": ("/futures/data/openInterestHist", {"oi": "sumOpenInterest", "oi_value": "sumOpenInterestValue"}),
    "gls": ("/futures/data/globalLongShortAccountRatio", {"ratio": "longShortRatio", "long": "longAccount", "short": "shortAccount"}),
    "tpp": ("/futures/data/topLongShortPositionRatio", {"ratio": "longShortRatio", "long": "longAccount", "short": "shortAccount"}),
    "taker": ("/futures/data/takerlongshortRatio", {"ratio": "buySellRatio", "buy": "buyVol", "sell": "sellVol"}),
}
FUNDING = "funding"
ENDPOINTS = (*HIST, FUNDING)


def parse_hist(endpoint: str, payload) -> list[dict]:
    cols = HIST[endpoint][1]
    if not isinstance(payload, list):
        raise C.CollectorError(f"{endpoint}: beklenmeyen yanit turu {type(payload).__name__}")
    out = []
    for r in payload:
        try:
            row = {"ts": int(r["timestamp"])}
        except (KeyError, TypeError, ValueError):
            continue
        for k, f in cols.items():
            row[k] = C._num(r.get(f))
        if all(row[k] is None for k in cols):
            continue
        out.append(row)
    return out


def parse_funding(payload) -> list[dict]:
    if not isinstance(payload, list):
        raise C.CollectorError(f"funding: beklenmeyen yanit turu {type(payload).__name__}")
    out = []
    for r in payload:
        try:
            row = {"ts": int(r["fundingTime"]), "rate": C._num(r.get("fundingRate")), "mark": C._num(r.get("markPrice"))}
        except (KeyError, TypeError, ValueError):
            continue
        if row["rate"] is None:
            continue
        out.append(row)
    return out


# ------------------------------------------------------------------ yalniz-ekleme depo
def dosya_yolu(kok: Path, endpoint: str, symbol: str) -> Path:
    return Path(kok) / endpoint / f"{symbol}.jsonl"


def son_ts(yol: Path) -> int | None:
    """Dosyanin son tam satirinin ts'i (yalniz dosya sonundan okunur)."""
    try:
        with open(yol, "rb") as f:
            f.seek(0, os.SEEK_END)
            n = f.tell()
            f.seek(max(0, n - 4096))
            satirlar = f.read().splitlines()
    except FileNotFoundError:
        return None
    for s in reversed(satirlar):
        try:
            return int(json.loads(s)["ts"])
        except (ValueError, KeyError, TypeError):
            continue
    return None


def ekle(yol: Path, rows: Sequence[dict]) -> int:
    """Yalniz son ts'den BUYUK, artan sirali satirlari dosya SONUNA ekler (tek yazim + fsync); varolan icerik degismez."""
    last = son_ts(yol)
    yeni, prev = [], last
    for r in sorted(rows, key=lambda r: r["ts"]):
        if prev is None or r["ts"] > prev:
            yeni.append(r)
            prev = r["ts"]
    if not yeni:
        return 0
    yol.parent.mkdir(parents=True, exist_ok=True)
    veri = "".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n" for r in yeni).encode()
    with open(yol, "ab+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() > 0:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                f.write(b"\n")
        f.write(veri)
        f.flush()
        os.fsync(f.fileno())
    return len(yeni)


# ------------------------------------------------------------------ toplama
def _plan(last: int | None, now_ms: int) -> tuple[int, int]:
    floor = now_ms - C.LOOKBACK_MS + C.LOOKBACK_MARGIN_MS
    start = floor if last is None else max(last + 1, floor)
    return start - start % PERIOD_MS if last is None else start, now_ms


def fetch_hist(client, endpoint: str, symbol: str, lo: int, hi: int, now_ms: int, ceiling: int) -> list[dict]:
    path = HIST[endpoint][0]
    span = PAGE_LIMIT * PERIOD_MS
    out, cur = [], lo
    while cur <= hi:
        if C._weight_hit(client, ceiling):
            raise C.WeightStop()
        top = min(hi, cur + span - 1)
        payload = client.get_json(path, {"symbol": symbol, "period": PERIOD, "limit": PAGE_LIMIT, "startTime": cur, "endTime": top})
        out.extend(r for r in parse_hist(endpoint, payload) if cur <= r["ts"] <= top and r["ts"] <= now_ms - PERIOD_MS
                   and not C.in_holdout(r["ts"]))
        cur = top + 1
    return out


def fetch_funding(client, symbol: str, lo: int, hi: int, ceiling: int) -> list[dict]:
    out, cur = [], lo
    while cur <= hi:
        if C._weight_hit(client, ceiling):
            raise C.WeightStop()
        part = parse_funding(client.get_json("/fapi/v1/fundingRate", {"symbol": symbol, "startTime": cur, "endTime": hi, "limit": FUNDING_LIMIT}))
        out.extend(r for r in part if cur <= r["ts"] <= hi and not C.in_holdout(r["ts"]))
        if len(part) < FUNDING_LIMIT:
            break
        cur = max(r["ts"] for r in part) + 1
    return out


def collect(kok: Path, client, pairs: Sequence[str], now_ms: int, *, endpoints: Sequence[str] = ENDPOINTS,
            max_requests: int = 900, weight_ceiling: int = C.OI_WEIGHT_CEILING) -> C.Stats:
    st = C.Stats()
    for pair in pairs:
        symbol = pair_symbol(pair)
        n_pair = 0
        for ep in endpoints:
            if client.requests_made >= max_requests:
                st.budget_hit = True
                break
            if C._weight_hit(client, weight_ceiling):
                st.budget_hit = st.weight_stop = True
                break
            yol = dosya_yolu(kok, ep, symbol)
            start, end = _plan(son_ts(yol), now_ms)
            try:
                for lo, hi in C.clip_windows(start, end):
                    rows = (fetch_funding(client, symbol, lo, hi, weight_ceiling) if ep == FUNDING
                            else fetch_hist(client, ep, symbol, lo, hi, now_ms, weight_ceiling))
                    n = ekle(yol, rows)
                    st.rows += n
                    n_pair += n
            except C.WeightStop:
                st.budget_hit = st.weight_stop = True
                break
            except (C.BanError, C.GeoBlockError):
                st.requests = client.requests_made
                raise
            except C.CollectorError as e:
                st.errors += 1
                log.error("event=fetch_failed pair=%s endpoint=%s err=%s", pair, ep, e)
        st.per_pair[pair] = n_pair
        if st.budget_hit:
            break
    st.requests = client.requests_made
    return st
