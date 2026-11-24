"""status.json (05 §8.2): atomik yazim, kalp atisi. Yazma hatasi dongu bozmaz."""
from __future__ import annotations

import json
import logging
import math
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trader_core import giris_izi as GI

from .clock import Clock
from .config import EngineConfig
from .fileio import atomic_write_json, fmt_ts, heartbeat_read, heartbeat_write, FileIoError

log = logging.getLogger("engine.status")
SCHEMA = "engine-status/1"


# ------------------------------------------------------------------ toplu sok (bilgi raporu; ayri modul degil: modul envanteri kilitli)
# Toplu sok (joint shock) raporu: canli oncesi guvenlik hesabi. YALNIZ BILGI: karar/emir/boyut yoluna GIRMEZ.
#
# Girdi: acik pozisyonlar (status.json `open_positions`: pair, side, qty, entry_price, mark, stop, asset_class) + kasa (equity)
# + maliyet varsayimlari (taker komisyon, stop kaymasi bps) + gunluk zarar siniri (oran). Kagit ve canli ayni kodu kullanir.
#
# Hesaplar (hepsi $ ve kasa yuzdesi):
# - ortak sok X% (X = 2, 5, 10, 20): TUM pozisyonlar ayni anda KENDI aleyhine X% hareket eder: zarar = X/100 x notional(mark).
# - iliskili sok: kripto -X%, hisse ve emtia -X/2 (her pozisyonun aleyhine yonde).
# - stop dolumu: her stop dolarsa kayip = mevcut fiyattan stop dolum fiyatina (stop, kayma kadar aleyhe) + cikis komisyonu.
#   Taban: yapilandirmadaki slip_stop_bps; stres: 2 x slip_stop_bps. Stop kardaysa (iz suren stop) kayip negatif olabilir (kazanc kilidi).
# Izole teminatta pozisyon zarari teminati asamaz; kaldirac 3-5 ve sok <= %20 iken notional x X < teminat oldugundan tavan uygulanmaz
# (tavan: zarar <= notional/kaldirac; kaldirac bilinmiyorsa uygulanmaz).
SEMA = "ml.toplu_sok.v1"
SOKLAR = (2, 5, 10, 20)
KRIPTO = "kripto"
UYARI_SOK = 10                      # gunluk limitle karsilastirilan ortak sok (%)
DOSYA = "toplu_sok_{mod}_v1.json"   # var/durum/ altinda
KAYMA_STRES = 2.0


def _f(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def _sgn(side: Any) -> float:
    return 1.0 if str(side).lower() == "long" else -1.0


def _norm(pozisyonlar: Sequence[Mapping]) -> list[dict]:
    """Gecerli pozisyonlar: qty > 0, fiyat (mark yoksa giris) > 0, yon long/short. Gecersiz atlanir ve sayilir (cagiran `atlanan`)."""
    out = []
    for p in pozisyonlar or ():
        qty, ep = _f(p.get("qty")), _f(p.get("entry_price"))
        mark = _f(p.get("mark")) or ep
        side = str(p.get("side", "")).lower()
        if not qty or qty <= 0 or not mark or mark <= 0 or side not in ("long", "short"):
            continue
        out.append({"pair": str(p.get("pair")), "side": side, "qty": qty, "fiyat": mark, "stop": _f(p.get("stop")),
                    "sinif": str(p.get("asset_class") or KRIPTO), "kaldirac": _f(p.get("leverage"))})
    return out


def _ozet(zarar: float, equity: float) -> dict:
    return {"usd": round(zarar, 2), "kasa_yuzde": round(zarar / equity * 100.0, 4) if equity > 0 else None}


def _zarar_sok(pos: Sequence[dict], x_kripto: float, x_diger: float) -> float:
    """Yon-bagimsiz: her pozisyon KENDI aleyhine hareket eder; zarar = oran x notional (izole teminat tavani varsa uygulanir)."""
    toplam = 0.0
    for p in pos:
        oran = (x_kripto if p["sinif"] == KRIPTO else x_diger) / 100.0
        z = oran * p["qty"] * p["fiyat"]
        if p["kaldirac"]:
            z = min(z, p["qty"] * p["fiyat"] / p["kaldirac"])
        toplam += z
    return toplam


def _zarar_stop(pos: Sequence[dict], taker_fee: float, kayma_bps: Mapping[str, float], carpan: float) -> tuple[float, int]:
    """Her stop dolarsa: sgn x (mark - dolum) x qty + cikis komisyonu; dolum = stop, aleyhe `carpan x slip_stop_bps`."""
    toplam, stopsuz = 0.0, 0
    for p in pos:
        if p["stop"] is None or p["stop"] <= 0:
            stopsuz += 1
            continue
        sg = _sgn(p["side"])
        dolum = p["stop"] * (1.0 - sg * carpan * float(kayma_bps.get(p["pair"], kayma_bps.get("*", 5.0))) / 10000.0)
        toplam += sg * (p["fiyat"] - dolum) * p["qty"] + taker_fee * p["qty"] * dolum
    return toplam, stopsuz

def hesapla(pozisyonlar: Sequence[Mapping], equity: Any, *, gunluk_limit: Any = None, taker_fee: float = 0.0005,
            kayma_bps: Mapping[str, float] | None = None) -> dict[str, Any]:
    """-> {"sema", "equity", "pozisyon_sayisi", "notional", "ortak": {"2": {usd, kasa_yuzde}, ...}, "iliskili": {...},
    "stop_dolumu": {"taban": .., "stres_2x": .., "stopsuz": n}, "gunluk_limit": {...}, "uyari": bool, ...}. Hic alan atlanmaz."""
    eq = _f(equity)
    pos = _norm(pozisyonlar)
    kb = dict(kayma_bps or {})
    n_gelen = len(pozisyonlar or ())
    notional = sum(p["qty"] * p["fiyat"] for p in pos)
    out: dict[str, Any] = {"sema": SEMA, "pozisyon_sayisi": len(pos), "atlanan": n_gelen - len(pos),
                           "equity": None if eq is None else round(eq, 2), "notional": round(notional, 2),
                           "notional_kasa_kat": round(notional / eq, 4) if eq and eq > 0 else None,
                           "formul": {"ortak": "zarar = X/100 x notional (tum pozisyonlar kendi aleyhine)",
                                      "iliskili": "kripto -X, hisse+emtia -X/2 (kendi aleyhine)",
                                      "stop_dolumu": "sgn x (mark - stop x (1 -/+ k x slip_stop_bps/1e4)) x qty + taker x qty x dolum; k = 1 (taban), 2 (stres)"},
                           "varsayim": {"taker_fee": taker_fee, "slip_stop_bps": kb, "stres_carpan": KAYMA_STRES, "soklar": list(SOKLAR)}}
    if eq is None or eq <= 0:
        return {**out, "ortak": None, "iliskili": None, "stop_dolumu": None, "gunluk_limit": None, "uyari": None, "neden": "equity_yok"}
    out["ortak"] = {str(x): _ozet(_zarar_sok(pos, x, x), eq) for x in SOKLAR}
    out["iliskili"] = {str(x): _ozet(_zarar_sok(pos, x, x / 2.0), eq) for x in SOKLAR}
    t, sz = _zarar_stop(pos, taker_fee, kb, 1.0)
    s, _ = _zarar_stop(pos, taker_fee, kb, KAYMA_STRES)
    out["stop_dolumu"] = {"taban": _ozet(t, eq), "stres_2x": _ozet(s, eq), "stopsuz": sz}
    lim = _f(gunluk_limit)
    sok10 = out["ortak"][str(UYARI_SOK)]["kasa_yuzde"]
    if lim is None or lim <= 0:
        out["gunluk_limit"], out["uyari"] = None, None
    else:
        out["gunluk_limit"] = {"oran": lim, "kasa_yuzde": round(lim * 100.0, 4), "usd": round(lim * eq, 2)}
        out["uyari"] = bool(sok10 > lim * 100.0)       # %10 ortak sok gunluk zarar sinirini asar
    return out


def kayma_haritasi(pairs: Sequence[str], taban_bps: float, overrides: Mapping[str, Mapping[str, Mapping[str, float]]] | None) -> dict[str, float]:
    """cift -> slip_stop_bps: cift icin seans bazli degerlerin EN BUYUGU (muhafazakar), yoksa taban; "*" = taban."""
    out = {"*": float(taban_bps)}
    for p in pairs:
        ov = (overrides or {}).get(p)
        if ov:
            vals = [float(v["slip_stop_bps"]) for v in ov.values() if isinstance(v, Mapping) and "slip_stop_bps" in v]
            if vals:
                out[p] = max(max(vals), float(taban_bps))
    return out


def durum_yolu(status_yolu: str | os.PathLike, mod: str) -> Path:
    """var/<bot>/status.json -> var/durum/toplu_sok_<mod>_v1.json"""
    return Path(status_yolu).resolve().parent.parent / "durum" / DOSYA.format(mod=mod)


def oku(yol: str | os.PathLike) -> dict | None:
    """Yazilmis rapor; yok/bozuk/yanlis sema -> None."""
    try:
        d = json.loads(Path(yol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("sema") == SEMA else None


def saglik_ozeti(doc: Mapping | None) -> dict | None:
    """Saglik denetimi girdisi: {"sok10": kasa %, "limit": kasa %, "usd": ..}; hesap yoksa None."""
    try:
        if not doc or doc.get("uyari") is None:
            return None
        return {"sok10": float(doc["ortak"][str(UYARI_SOK)]["kasa_yuzde"]), "limit": float(doc["gunluk_limit"]["kasa_yuzde"]),
                "sok10_usd": float(doc["ortak"][str(UYARI_SOK)]["usd"])}
    except (KeyError, TypeError, ValueError):
        return None



def _z(t: datetime | None) -> str | None:
    return None if t is None else fmt_ts(t)


def _ms_to_z(ms) -> str | None:
    if isinstance(ms, bool) or not isinstance(ms, (int, float)) or ms <= 0:
        return None
    try:
        return fmt_ts(datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc))
    except (OverflowError, OSError, ValueError):
        return None


def _unrealized(p, m) -> dict:
    """Acik pozisyon K/Z (eklemeli). m = (son kapanmis 1m last_c, bar kapanis ts) ya da None. Fiyat/giris bilinmiyorsa None."""
    out = {"mark": None, "notional_usd": None, "unrealized_pnl_usd": None, "unrealized_pct": None, "mark_ts": None}
    try:
        if not m:
            return out
        mark, ts = float(m[0]), m[1]
        qty, ep = float(p.qty), float(p.entry_price)
        if not (math.isfinite(mark) and mark > 0 and math.isfinite(qty) and math.isfinite(ep) and ep > 0):
            return out
        sgn = 1.0 if p.side == "long" else -1.0
        out.update(mark=mark, notional_usd=qty * mark, unrealized_pnl_usd=sgn * (mark - ep) * qty,
                   unrealized_pct=sgn * (mark - ep) / ep * 100.0, mark_ts=_z(ts))
    except (TypeError, ValueError):
        pass
    return out


def _sinif(engine, pair: str) -> str | None:
    """kripto | hisse | emtia (saglik denetimi: seans disi fiyat gelmemesi normal). Bilinmezse None."""
    try:
        from trader_engine.arm_guard import asset_class  # noqa: PLC0415
        return asset_class(pair, engine.cfg.clusters)
    except Exception:  # noqa: BLE001
        return None


def _exchange_block(engine, f: dict, mode: str) -> dict | None:
    """11 §9.4: canli kiplerde (testnet/live) `exchange` blogu; kagit kipinde yok. naked = [{trade_id, pair, seconds}]
    (saglik denetcisi bos degilse CRIT), reachable = borsa okunabiliyor mu, last_ban = broker'in son yasagi
    ({"http", "retry_after_s"}) ya da None. Eksik alan None; blok asla yazimi bozmaz."""
    ex = f.get("exchange")
    if not isinstance(ex, dict):
        return None
    naked = []
    for r in ex.get("naked") or []:
        try:
            naked.append({"trade_id": int(r["trade_id"]), "pair": str(r["pair"]), "seconds": float(r["seconds"])})
        except (KeyError, TypeError, ValueError):
            continue
    lb = getattr(getattr(engine, "broker", None), "last_ban", None)
    last_ban = None
    if isinstance(lb, (tuple, list)) and len(lb) == 2:
        last_ban = {"http": lb[0], "retry_after_s": lb[1]}
    reach = ex.get("reachable")

    def _cnt(k):
        v = ex.get(k)
        return v if isinstance(v, int) and not isinstance(v, bool) else None
    am = {"drift": _cnt("account_mode_drift"), "unverified": _cnt("account_mode_unverified"),
          "unverified_ban": _cnt("account_mode_unverified_ban")}      # DD-9 §8.1
    return {"env": mode, "reachable": reach if isinstance(reach, bool) else None,
            "last_sync": ex.get("last_sync_ts"), "clock_offset_ms": ex.get("clock_offset_ms"),
            "used_weight": ex.get("used_weight"), "ban_until": _ms_to_z(ex.get("ban_until_ms")),
            "ban_until_ms": ex.get("ban_until_ms") if isinstance(ex.get("ban_until_ms"), int) and not isinstance(ex.get("ban_until_ms"), bool) else None,
            "last_ban": last_ban, "naked": naked, "account_mode": am}


class StatusWriter:
    def __init__(self, path: str, clock: Clock, cfg: EngineConfig) -> None:
        self.path = str(path)
        self.clock = clock
        self.cfg = cfg
        self.started_at = clock.now()
        self._last_write: datetime | None = None
        self._hb_prev: str | None = None
        self._hb_read = False
        self._sok_yazildi: datetime | None = None

    def _ayar_sha(self) -> str | None:
        """6c: etkin yapilandirmanin tam sha256'si (bir kez); hata durumu bozmaz."""
        if not hasattr(self, "_ayar"):
            try:
                self._ayar = GI.ayar_sha256(self.cfg)
            except Exception as e:  # noqa: BLE001
                log.warning("ayar_surumu hesaplanamadi: %s", e)
                self._ayar = None
        return self._ayar

    def _toplu_sok(self, engine, pos: list, equity) -> dict | None:
        """23.11 toplu sok raporu (yalniz bilgi; kagit = canli): status.json `toplu_sok` + var/durum/toplu_sok_<mod>_v1.json.
        Hata durumu bozmaz (None). JSON dakikada en cok bir kez yazilir."""
        try:
            lev = float(self.cfg.leverage)
            girdi = [{**r, "leverage": lev} for r in pos]
            kb = kayma_haritasi([r["pair"] for r in pos], self.cfg.cost.slip_stop_bps, self.cfg.cost_overrides)
            doc = hesapla(girdi, equity, gunluk_limit=self.cfg.risk_config.daily_max_loss,
                              taker_fee=self.cfg.cost.taker_fee, kayma_bps=kb)
            doc = {**doc, "ts": _z(self.clock.now()), "mod": self.cfg.mode, "bot": self.cfg.bot}
            now = self.clock.now()
            if self._sok_yazildi is None or (now - self._sok_yazildi).total_seconds() >= 60:
                atomic_write_json(str(durum_yolu(self.path, self.cfg.mode)), doc)
                self._sok_yazildi = now
            return {"uyari": doc["uyari"], "ortak": doc["ortak"], "iliskili": doc["iliskili"], "stop_dolumu": doc["stop_dolumu"],
                    "gunluk_limit": doc["gunluk_limit"], "ts": doc["ts"]}
        except Exception as e:  # noqa: BLE001 - bilgi raporu dongu/durum yazimini bozmaz
            log.warning("toplu sok hesaplanamadi: %s: %s", type(e).__name__, e)
            return None

    def build(self, engine) -> dict:
        now = self.clock.now()
        f = engine.status_fields()
        marks = f.get("last_marks") or {}
        extra = f.get("open_extra") or {}
        pos = [{"trade_id": p.trade_id, "pair": p.pair, "side": p.side, "qty": p.qty, "entry_price": p.entry_price,
                "stop": p.current_stop, "asset_class": _sinif(engine, p.pair), **_unrealized(p, marks.get(p.pair)), **(extra.get(p.trade_id) or {})}
               for p in f["open_positions"] if p.status in ("open", "closing")]
        known = [r["unrealized_pnl_usd"] for r in pos if r["unrealized_pnl_usd"] is not None]
        mark_tss = [m[1] for m in (marks.get(r["pair"]) for r in pos) if m]
        unreal_total = sum(known) if known else (0.0 if not pos else None)
        mark_ts = _z(max(mark_tss)) if mark_tss else None
        ids = [p.trade_id for p in f["open_positions"] if p.status in ("open", "closing")]
        blocked = f["entries_blocked_reason"]
        gate_code = f["gate_code"]
        sok = self._toplu_sok(engine, pos, f["equity"]) if f["equity"] is not None else None
        return {
            "schema": SCHEMA, "bot": self.cfg.bot, "mode": self.cfg.mode, "pid": os.getpid(),
            "started_at": _z(self.started_at), "loop_at": _z(now), "last_minute_ts": _z(f["last_minute_ts"]),
            "last_decision_bar_close": _z(f["last_decision_close"]), "last_candle_open": _z(f["last_candle_open"]),
            "trigger_tf": f["tf"], "param_version_id": f["param_version_id"], "ayar_surumu": self._ayar_sha(),
            "strategy": {"name": f["strategy_name"], "version": f["strategy_version"]},
            "entries_open": bool(f["entries_open"]), "gate": {"ok": gate_code == "ok", "code": gate_code},
            "kill": bool(f["kill"]), "kill_state": f["kill_state"], "entries_blocked_reason": blocked,
            "entries_blocked_reasons": list(f.get("entries_blocked_reasons") or ([blocked] if blocked else [])),   # DD-2: eklemeli
            "dry_run": self.cfg.mode != "live", "wallet": f["wallet"], "equity": f["equity"], "account_stale": bool(f.get("account_stale", False)),
            **({"equity_last": f["equity_last"], "account_at": _z(f["account_at"])} if f.get("equity_last") is not None else {}),
            "day_start_equity": f["day_start_equity"],
            "open_positions": pos, "unrealized_pnl_usd": unreal_total, "mark_ts": mark_ts, "open_trade_ids": ids, "counters": f["counters"],
            **({"records": f["records"]} if f.get("records") is not None else {}),   # WP-3 9.3: yalniz kayit sayaclari
            **({"cluster_counts": f["cluster_counts"]} if f.get("cluster_counts") is not None else {}),   # DD-12 WP-05 (yalniz kagit)
            **({"etiket_kurallari": f["etiket_kurallari"]} if f.get("etiket_kurallari") is not None else {}),   # 20 Kasim: etiket kurallari
            **({"pause": f["pause"]} if f.get("pause") is not None else {}),
            **({"risk_ladder": f["risk_ladder"]} if f.get("risk_ladder") is not None else {}),   # 12 §10
            **({"toplu_sok": sok} if sok is not None else {}),   # 23.11: bilgi raporu (ortak/iliskili sok, stop dolumu)
            **({"exchange": xb} if (xb := _exchange_block(engine, f, self.cfg.mode)) is not None else {}),
        }

    def write(self, engine, *, force: bool = False, stopped: bool = False) -> bool:
        now = self.clock.now()
        if (not force and self._last_write is not None
                and (now - self._last_write).total_seconds() < self.cfg.loop_sleep_s):
            return False
        try:
            atomic_write_json(self.path, self.build(engine))
            self._last_write = now
        except Exception as e:  # noqa: BLE001 - yazma hatasi dongu bozmaz
            log.warning("status.json yazilamadi: %s", e)
            return False
        try:
            d = Path(self.path).parent
            if not self._hb_read:
                self._hb_read = True
                try:
                    prev = heartbeat_read(d)
                    self._hb_prev = prev["ts"] if prev else None
                except FileIoError as e:
                    log.warning("kalp atisi okunamadi: %s", e)
            heartbeat_write(d, now, self.started_at, self._hb_prev, stopped=stopped)
        except Exception as e:  # noqa: BLE001
            log.warning("kalp atisi yazilamadi: %s", e)
        return True
