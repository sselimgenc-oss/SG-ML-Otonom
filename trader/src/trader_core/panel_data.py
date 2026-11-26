"""Panel (pano) icin yapisal, salt okunur veri yardimcilari (docs/panel-spec.md §3, §10, §11).

Telegram bolum ureticilerinin (`section_ledger/budget`) yapisal karsiliklari: ayni formuller, ayni hata
kodlari, ama metin yerine dict doner. `telegram.py` ice aktarilmaz (o modul `trader_engine`i ceker; panel yalniz
dosya/DB sozlesmelerine bagli). Esdegerlik `tests/test_panel_equivalence.py` ile sinanir.

Panel yeni hesap yapmaz: sayilar defter/butce/saglik ciktisindan aynen gelir; yalniz toplama, siralama,
ilk-N kesme, zaman farki (bayatlik) ve cizim icin kumulatif seri yapilir. Hicbir kaynaga yazilmaz.
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import budget as B
from . import ledger as L
from . import health as H
from .health import DEFAULT_CFG as HEALTH_CFG
from .arm_time import arm_id_of

UTC = timezone.utc
TR = timezone(timedelta(hours=3))        # Europe/Istanbul: sabit UTC+3 (DST yok), telegram.TR ile ayni
STALE_S = 120                            # telegram.STALE_S ile ayni (esitlik testle sinanir; telegram ice aktarilamaz)
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CLOSED_MAX = L.Ledger.LIST_CLOSED_MAX

# status.json'dan panele gecen alanlar (05 §8.2); baska alan gecmez
STATUS_FIELDS = ("mode", "dry_run", "kill", "kill_state", "entries_open", "entries_blocked_reason", "loop_at",
                 "started_at", "equity", "day_start_equity", "wallet", "counters", "param_version_id", "strategy",
                 "trigger_tf", "open_positions", "unrealized_pnl_usd", "mark_ts", "dayaniklilik")


class SectionError(Exception):
    """Kaynak okunamadi; `code` "veri yok: <kod>" olarak gosterilir (telegram.SectionError ile ayni kodlar)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def fmt_z(dt: datetime | None) -> str | None:
    return None if dt is None else dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def parse_z(s: Any) -> datetime | None:
    if not isinstance(s, str):
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def day_bounds_utc(day: str) -> tuple[datetime, datetime]:
    """Istanbul gunu [00:00, +1 gun) -> UTC (telegram._istanbul_day_bounds_utc ile ayni sinirlar)."""
    d0 = datetime.fromisoformat(day).replace(tzinfo=TR)
    return d0.astimezone(UTC), (d0 + timedelta(days=1)).astimezone(UTC)


def fmt_tsi(iso: str | None) -> str:
    d = parse_z(iso)
    return "—" if d is None else d.astimezone(TR).strftime("%Y-%m-%d %H:%M:%S") + " TSİ"


def today_tr(now: datetime) -> str:
    return now.astimezone(TR).strftime("%Y-%m-%d")


def daily_loss_rate(mode: Any = "paper") -> float:
    """Gunluk zarar orani: Telegram ile ayni tek kaynak (`tg_sade.limit_orani`: kagitta ayar dosyasi, canlida kilitli)."""
    from . import tg_sade as _TS  # noqa: PLC0415
    return _TS.limit_orani(None, mode)


def daily_loss_limit(day_start_equity: Any) -> float | None:
    """Gunluk zarar siniri = risk kilidi `daily_max_loss` x gun basi equity (sabit sayi yok)."""
    try:
        v = float(day_start_equity)
    except (TypeError, ValueError):
        return None
    return daily_loss_rate() * v if v > 0 else None


# ---------------------------------------------------------------------------------------------
# status.json (yalniz dosya): bayat / yok / bozuk => deger gosterilmez
# ---------------------------------------------------------------------------------------------
def read_status(path: str, now: datetime, stale_s: int = STALE_S) -> dict:
    """-> {"state": live|stale|missing|bad, "code", "loop_at", "age_s", "data"}; `data` YALNIZ canliyken dolu.
    Son bilinen degerler hicbir zaman canli gibi dondurulmez."""
    out: dict[str, Any] = {"state": "missing", "code": "status_yok", "loop_at": None, "age_s": None, "data": None}
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return out
    except OSError:
        return {**out, "state": "bad", "code": "status_okunamadi"}
    try:
        st = json.loads(raw)
        if not isinstance(st, dict):
            raise ValueError
    except ValueError:
        return {**out, "state": "bad", "code": "status_bozuk"}
    la = parse_z(st.get("loop_at"))
    if la is None:
        return {**out, "state": "bad", "code": "status_bozuk"}
    age = (now - la).total_seconds()
    out.update(loop_at=fmt_z(la), age_s=round(age, 1))
    if age > stale_s:
        return {**out, "state": "stale", "code": "status_bayat"}
    gate = st.get("gate") if isinstance(st.get("gate"), Mapping) else {}
    data = {k: st.get(k) for k in STATUS_FIELDS}
    data["gate_code"] = gate.get("code")
    return {**out, "state": "live", "code": None, "data": data}


# ---------------------------------------------------------------------------------------------
# defter
# ---------------------------------------------------------------------------------------------
def open_ledger_ro(path: str, bot: str) -> L.Ledger:
    if not path or not Path(path).exists():
        raise SectionError("defter_yok")
    try:
        return L.open_ledger(path, bot, create=False, read_only=True, migrate=False)
    except Exception as e:  # noqa: BLE001
        if "readonly" in str(e).lower() and not Path(path + "-wal").exists():
            # WAL kipi + -wal/-shm yok (bot durmus) + dizin salt okunur: mode=ro acilamaz (spec §10 notu)
            raise SectionError("wal_yok_salt_okunur") from None
        raise SectionError(getattr(e, "code", None) or type(e).__name__) from None


def sum_pnl_r(trades: list) -> tuple[float, float]:
    return (sum(t.realized_pnl or 0.0 for t in trades), sum(t.r_multiple or 0.0 for t in trades))


def ledger_day(path: str, bot: str, day: str) -> tuple[list, list]:
    """(o gunun kapanan islemleri, tum acik islemler); telegram._ledger_day ile ayni kume."""
    led = open_ledger_ro(path, bot)
    try:
        a, b = day_bounds_utc(day)
        return led.list_closed_trades(a, b, CLOSED_MAX), led.list_open_trades()
    except SectionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise SectionError(type(e).__name__) from None
    finally:
        led.close()


def day_summary(closed: list, opened: list, day_start_equity: Any = None) -> dict:
    pnl, r = sum_pnl_r(closed)
    return {"closed": len(closed), "pnl": pnl, "r": r,
            "win": sum(1 for t in closed if (t.realized_pnl or 0) > 0),
            "loss": sum(1 for t in closed if (t.realized_pnl or 0) <= 0),
            "open": len(opened), "daily_loss": max(0.0, -pnl), "daily_limit": daily_loss_limit(day_start_equity)}


def trade_dict(t: L.TradeRecord) -> dict:
    return {"trade_id": t.trade_id, "pair": t.pair, "side": t.side, "setup": t.setup, "leverage": t.leverage,
            "entry_ts": fmt_z(t.entry_ts), "exit_ts": fmt_z(t.exit_ts), "entry_price": t.entry_price,
            "exit_price": t.exit_price, "qty": t.qty, "planned_stop": t.planned_stop,
            "planned_risk": t.planned_risk, "fee_entry": t.fee_entry, "fee_exit": t.fee_exit,
            "realized_pnl": t.realized_pnl, "r_multiple": t.r_multiple, "exit_reason": t.exit_reason}


def decisions_summary(led: L.Ledger, day: str) -> dict:
    a, b = day_bounds_utc(day)
    rows = led.list_decisions(since_ts=a, until_ts=b, limit=CLOSED_MAX)
    reasons: dict[str, int] = {}
    for d in rows:
        if d.final_action == "skipped":
            k = d.skip_reason or "bilinmiyor"
            reasons[k] = reasons.get(k, 0) + 1
    return {"total": len(rows), "entered": sum(1 for d in rows if d.final_action == "entered"),
            "skipped": sum(1 for d in rows if d.final_action == "skipped"),
            "skip_reasons": dict(sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0])))}


def recent_closed(path: str, bot: str, limit: int = 200) -> list[dict]:
    led = open_ledger_ro(path, bot)
    try:
        return [trade_dict(t) for t in led.list_closed_trades(None, None, limit)]
    except Exception as e:  # noqa: BLE001
        raise SectionError(type(e).__name__) from None
    finally:
        led.close()


def ledger_view(path: str, bot: str, day: str, status_dse: Any, limit: int = 200, by_day: bool = False) -> dict:
    led = open_ledger_ro(path, bot)
    try:
        a, b = day_bounds_utc(day)
        day_closed = led.list_closed_trades(a, b, CLOSED_MAX)
        opened = led.list_open_trades()
        shown = day_closed[:limit] if by_day else led.list_closed_trades(None, None, limit)
        return {"day": day, "summary": day_summary(day_closed, opened, status_dse),
                "closed": [trade_dict(t) for t in shown], "open": [trade_dict(t) for t in opened],
                "decisions": decisions_summary(led, day)}
    except SectionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise SectionError(type(e).__name__) from None
    finally:
        led.close()


def equity_curve(path: str, bot: str, start_equity: Any, limit: int = 5000, max_points: int = 400,
                 calendar_days: int = 42) -> dict:
    """Kapanan islemlerden (cikis zamanina gore) kumulatif seri. Baslangic yoksa seri 0'dan kumulatif K/Z olur
    (`base`="pnl"); yuzde dususler yalniz baslangic biliniyorsa verilir."""
    led = open_ledger_ro(path, bot)
    try:
        trades = led.list_closed_trades(None, None, limit)
    except Exception as e:  # noqa: BLE001
        raise SectionError(type(e).__name__) from None
    finally:
        led.close()
    truncated = len(trades) >= limit
    trades = [t for t in reversed(trades) if t.exit_ts is not None]
    try:
        start = float(start_equity) if start_equity is not None and float(start_equity) > 0 else None
    except (TypeError, ValueError):
        start = None
    base = start if start is not None else 0.0
    cum, peak = 0.0, base
    pts: list[list] = []
    daily: dict[str, list] = {}
    max_dd_abs = max_dd_pct = 0.0
    for t in trades:
        pnl = t.realized_pnl or 0.0
        cum += pnl
        eq = base + cum
        peak = max(peak, eq)
        dd_abs = eq - peak
        dd_pct = (eq / peak - 1.0) if (start is not None and peak > 0) else None
        max_dd_abs = min(max_dd_abs, dd_abs)
        if dd_pct is not None:
            max_dd_pct = min(max_dd_pct, dd_pct)
        pts.append([fmt_z(t.exit_ts), eq, dd_abs, dd_pct])
        d = daily.setdefault(t.exit_ts.astimezone(TR).strftime("%Y-%m-%d"), [0.0, 0.0, 0])
        d[0] += pnl
        d[1] += t.r_multiple or 0.0
        d[2] += 1
    if len(pts) > max_points:                       # yalniz cizim inceltmesi: son nokta korunur
        step = len(pts) / max_points
        pts = [pts[int(i * step)] for i in range(max_points - 1)] + [pts[-1]]
    cal = [{"day": k, "pnl": v[0], "r": v[1], "n": v[2]} for k, v in sorted(daily.items())]
    return {"base": "equity" if start is not None else "pnl", "start": start,
            "peak": peak if start is not None else None, "max_dd_pct": max_dd_pct if start is not None else None,
            "max_dd_abs": max_dd_abs, "total_closed": len(trades), "truncated": truncated,
            "points": pts, "daily": cal[-calendar_days:] if calendar_days else cal}


def risk_usage(path: str, bot: str, equity: Any, day_start_equity: Any, day: str, mode: Any = "paper",
               max_positions: Any = None) -> dict:
    """Acik risk / limitler: kipin ayar dosyasindaki oranlar x equity (motorla ayni); kullanilan = defterdeki planned_risk.
    Gunluk zarar = gun basi kasa - simdiki kasa (gerceklesmemis dahil; motor/Telegram ile ayni).
    `max_positions` (motor ayarindan; sabit sayi yok) sayiysa 5. satir: acik pozisyon sayisi / tavan (birim 'adet')."""
    closed, opened = ledger_day(path, bot, day)
    try:
        eq, dse = float(equity), float(day_start_equity)
    except (TypeError, ValueError):
        raise SectionError("equity_yok") from None
    used_open = sum(t.planned_risk or 0.0 for t in opened)
    long_r = sum(t.planned_risk or 0.0 for t in opened if t.side == "long")
    short_r = sum(t.planned_risk or 0.0 for t in opened if t.side == "short")
    from . import tg_sade as _TS  # noqa: PLC0415
    c = _TS.risk_ayari(None, mode)
    rows = [("Toplam açık risk", used_open, c.max_open_risk * eq, "$"),
            ("Long açık risk", long_r, c.max_same_dir_risk * eq, "$"),
            ("Short açık risk", short_r, c.max_same_dir_risk * eq, "$"),
            ("Günlük zarar", max(0.0, dse - eq), daily_loss_rate(mode) * dse, "$")]
    if isinstance(max_positions, int) and not isinstance(max_positions, bool) and max_positions > 0:
        rows.append(("Açık pozisyon sayısı", len(opened), max_positions, "adet"))
    return {"rows": [{"label": n, "used": u, "limit": lim, "pct": (u / lim * 100.0) if lim > 0 else None, "birim": b}
                     for n, u, lim, b in rows]}


# ---------------------------------------------------------------------------------------------
# butce / saglik / sistem
# ---------------------------------------------------------------------------------------------
def budget_view(budget_config: str) -> dict:
    """telegram.section_budget ile ayni cozum: yapilandirma -> db yolu (goreli ise config/'un ust dizinine gore)."""
    try:
        bc = B.load_config(budget_config)
        db = Path(bc.db_path)
        if not db.is_absolute():
            db = Path(budget_config).resolve().parent.parent / db
        bc = dataclasses.replace(bc, db_path=str(db))
    except Exception:  # noqa: BLE001
        raise SectionError("yapilandirma_gecersiz") from None
    if not db.exists():
        raise SectionError("depo_yok")
    st = B.BudgetGuard(bc, read_only=True).status()
    if not st.config_ok:
        raise SectionError("yapilandirma_gecersiz")
    if not st.store_ok:
        raise SectionError("depo_okunamadi")
    return {"day": st.day, "month": st.month, "month_used_usd": st.month_used_usd,
            "monthly_cap_usd": st.monthly_cap_usd, "month_state": st.month_state,
            "provider_blocked_until": st.provider_blocked_until, "prices_verified": st.prices_verified,
            "services": {k: {"used_usd": v.used_usd, "cap_usd": v.cap_usd, "pct": v.pct, "state": v.state,
                             "calls_today": v.calls_today} for k, v in st.services.items()}}


def health_view(state_path: str, now: datetime, stale_s: float) -> dict:
    """Yalniz health `state.json` (saglik-spec §5.3); health.evaluate calistirilmaz."""
    if not state_path:
        raise SectionError("saglik_yapilandirma_yok")
    try:
        raw = Path(state_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SectionError("state_yok") from None
    except OSError:
        raise SectionError("state_okunamadi") from None
    try:
        st = json.loads(raw)
        if not isinstance(st, dict):
            raise ValueError
    except ValueError:
        raise SectionError("state_bozuk") from None
    lr = parse_z(st.get("last_run_at"))
    age = None if lr is None else round((now - lr).total_seconds(), 1)
    fps = st.get("fingerprints") if isinstance(st.get("fingerprints"), Mapping) else {}
    alerts = []
    for k, v in fps.items():
        v = v if isinstance(v, Mapping) else {}
        name, _, code = str(k).partition("|")
        alerts.append({"name": name, "code": code, "first_seen": v.get("first_seen"),
                       "consecutive": v.get("consecutive"), "alerted": bool(v.get("alerted")),
                       "level": v.get("level")})
    rc = st.get("restart_counts") if isinstance(st.get("restart_counts"), Mapping) else {}
    return {"overall": st.get("last_overall"), "last_run_at": fmt_z(lr), "age_s": age,
            "check_stale": age is None or age > stale_s, "alerts": alerts[:50],
            "restart_counts": {str(k): v for k, v in rc.items() if isinstance(v, (int, float))}}


def _meminfo() -> dict[str, int]:
    out: dict[str, int] = {}
    with open("/proc/meminfo", encoding="ascii") as f:
        for line in f:
            k, _, v = line.partition(":")
            if k in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                out[k] = int(v.split()[0]) * 1024
    return out


def system_view(disk_path: str) -> dict:
    """/proc/meminfo + statvfs; bellek/takas/disk renk esikleri health modulunden."""
    c = HEALTH_CFG
    try:
        m = _meminfo()
        avail, tot = m["MemAvailable"], m["MemTotal"]
        sw_tot, sw_used = m["SwapTotal"], m["SwapTotal"] - m["SwapFree"]
    except (OSError, KeyError, ValueError):
        raise SectionError("meminfo_okunamadi") from None
    try:
        sv = os.statvfs(disk_path)
        free, dtot = sv.f_bavail * sv.f_frsize, sv.f_blocks * sv.f_frsize
    except OSError:
        free = dtot = None
    ratio = (sw_used / sw_tot) if sw_tot else 0.0
    lvl = lambda warn, crit: "kotu" if crit else ("uyari" if warn else "iyi")  # noqa: E731
    return {"mem_available": avail, "mem_total": tot,
            "mem_level": lvl(avail < H.PANEL_MEM_WARN_BYTES, avail < H.PANEL_MEM_CRIT_BYTES),
            "swap_total": sw_tot, "swap_used": sw_used,
            "swap_level": lvl(ratio >= H.PANEL_SWAP_WARN_RATIO, ratio >= H.PANEL_SWAP_CRIT_RATIO),
            "disk_free": free, "disk_total": dtot,
            "disk_level": None if free is None else lvl(free < c.disk_warn_bytes, free < c.disk_crit_bytes)}


# ---- DD-12 WP-17: öğrenme görünümü (kurulum karnesi, ML, seans/varlık kırılımı, haftalık özet, harcama) ----
LEARNER_BOT = "learner"
PAPER_CONFIG = Path(__file__).resolve().parents[2] / "config" / "engine.paper.json"   # kâğıt yapılandırması (kümeler, kurulumlar)
WEEKLY_DIR = "weekly_summaries"
WEEKLY_RE = re.compile(r"^\d{4}-W\d{2}\.md$")
WEEKLY_MAX_CHARS = 3000
_ARM_CLASS_TR = {"kripto": "kripto", "hisse": "hisse senedi", "emtia": "metal / enerji"}
_COMMODITY_CLUSTERS = ("metal", "enerji_sanayi")


def paper_maps(path=None) -> tuple[list[str], Any]:
    """(kurulum listesi, varlık sınıfı fonksiyonu) config/engine.paper.json'dan. Okunamazsa: boş liste, hepsi kripto."""
    from .arm_time import CLASS_COMMODITY, CLASS_CRYPTO, CLASS_EQUITY
    try:
        raw = json.loads(Path(path or PAPER_CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        raw = {}
    clusters = {k: list((v or {}).get("pairs") or []) for k, v in (raw.get("clusters") or {}).items() if isinstance(v, dict)}
    arms_raw = raw.get("arms") or []
    if isinstance(arms_raw, dict):
        arms = [f"{k}@{tf}" for k, tfs in arms_raw.items() for tf in tfs]
    else:
        arms = [str(a) for a in arms_raw] if isinstance(arms_raw, list) else []

    def asset_of(pair: str) -> str:
        names = [n for n, ps in clusters.items() if pair in ps]
        if "hisse" in names:
            return CLASS_EQUITY
        if any(n in _COMMODITY_CLUSTERS for n in names):
            return CLASS_COMMODITY
        return CLASS_CRYPTO
    return arms, asset_of


def clusters_of_pair(pair: str, path=None) -> list[str]:
    try:
        raw = json.loads(Path(path or PAPER_CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    return [k for k, v in (raw.get("clusters") or {}).items() if isinstance(v, dict) and pair in (v.get("pairs") or [])]


def _latest_weekly(ledger_path: str) -> dict | None:
    d = Path(ledger_path).parent / WEEKLY_DIR
    try:
        names = sorted(p.name for p in d.iterdir() if WEEKLY_RE.match(p.name))
    except OSError:
        return None
    if not names:
        return None
    try:
        text = (d / names[-1]).read_text(encoding="utf-8")
    except OSError:
        return None
    return {"week": names[-1][:-3], "text": text[:WEEKLY_MAX_CHARS]}


def _ledger_learning(ledger_path: str, now: datetime, paper_config=None) -> dict:
    """Defterden öğrenme özeti (salt okunur). Okunamazsa SectionError; çağıran bölümü tek satırla bildirir."""
    from . import counterfactual as CF
    arms, asset_of = paper_maps(paper_config)
    base = Path(ledger_path).parent
    led = open_ledger_ro(ledger_path, LEARNER_BOT)
    try:
        decisions = led.list_decisions()
        trades = led.list_closed_trades(limit=10000)
        open_trades = led.list_open_trades()
    except SectionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise SectionError(getattr(e, "code", None) or type(e).__name__) from None
    finally:
        led.close()
    cf_path = base / "counterfactual.sqlite"
    try:
        cf_rows = CF.arm_rows(cf_path, LEARNER_BOT) if cf_path.exists() else []
    except CF.CounterfactualError as e:
        raise SectionError(e.code) from None
    closed: set[str] = set()                    # ders kaydi (arms_off.json) artik okunmaz: kol durumu hep "open"
    cands = CF.arm_candidates(decisions=decisions, trades=trades, cf_rows=cf_rows, asset_class_of=asset_of)
    by_id = {d.id: d for d in decisions}
    for c in cands:
        d = by_id.get(c["decision_id"])
        c["session"] = (d.session_tag if d is not None else None) or "open"
        c["skip_reason"] = d.skip_reason if d is not None else None
    sc = CF.arm_scorecard(cands, arms=arms, closed=closed)
    scorecard = [{"arm": a, "candidates": b["candidates"], "taken": b["taken"], "resolved": b["resolved"],
                  "mean_r_taken": b["mean_r_taken"], "mean_r_taken_cf": b["mean_r_taken_cf"], "state": b["state"],
                  "by_class": b["by_class"], "kasa": b["kasa"]} for a, b in sc.items()]
    sessions: dict[str, dict] = {}
    for s_ in ("open", "closed", "weekend"):
        cs_s = [c for c in cands if c["session"] == s_]
        sessions[s_] = {k: CF._arm_block([c for c in cs_s if c["asset_class"] == k]) for k in _ARM_CLASS_TR
                        if any(c["asset_class"] == k for c in cs_s)}
    asset_cls = {k: CF._arm_block([c for c in cands if c["asset_class"] == k]) for k in _ARM_CLASS_TR
                 if any(c["asset_class"] == k for c in cands)}
    arm_of = {d.id: (getattr(d, "arm_id", None) or arm_id_of(d.setup, d.trigger_tf)) for d in decisions}
    open_arm: dict[str, int] = {}
    open_cluster: dict[str, int] = {}
    for t in open_trades:
        a = arm_of.get(t.decision_id, "?")
        open_arm[a] = open_arm.get(a, 0) + 1
        for k in clusters_of_pair(t.pair, paper_config):
            open_cluster[k] = open_cluster.get(k, 0) + 1
    return {"scorecard": scorecard, "sessions": sessions, "asset_class": asset_cls,
            "open": {"total": len(open_trades), "by_arm": dict(sorted(open_arm.items())),
                     "by_cluster": dict(sorted(open_cluster.items()))},
            "trades_closed": len(trades), "decisions": len(decisions)}


def learning_view(ledger_path: str, budget_config: str, now: datetime, *, paper_config=None) -> dict:
    """Öğrenme sekmesi ve günlük rapor için tek kaynak (salt okunur). Her bölüm bağımsız: defter okunamazsa
    `ledger_error` kodu döner, harcama ve haftalık özet yine gelir (sayılar yok, çökme yok)."""
    out: dict[str, Any] = {"ledger_error": None}
    empty = {"scorecard": [],
             "sessions": {}, "asset_class": {}, "open": {"total": 0, "by_arm": {}, "by_cluster": {}},
             "trades_closed": 0, "decisions": 0}
    try:
        out.update(_ledger_learning(ledger_path, now, paper_config))
    except SectionError as e:
        out.update(empty)
        out["ledger_error"] = e.code
    try:
        out["budget"] = budget_view(budget_config) if budget_config else {"code": "yapilandirma_yok"}
    except SectionError as e:
        out["budget"] = {"code": e.code}
    out["weekly_summary"] = _latest_weekly(ledger_path) if ledger_path else None
    return out


# ---- tutarlilik (kagit-geri test) ve PBO / holdout muhru: salt okunur, eksik/bozuk dosya paneli bozmaz ----
TUTARLILIK_MAX_AGE_DAYS = 8              # docs/motor/tutarlilik-raporu-spec.md: 8 gunden eski rapor = "rapor yok"
_TUT_FIELDS = ("kagit_islem", "bt_islem", "eslesme_orani", "yalniz_kagit", "yalniz_bt", "giris_kayma_bps_ort",
               "cikis_kayma_bps_ort", "kagit_R", "bt_R", "kagit_pnl", "bt_pnl")


def _fnum(x: Any) -> float | int | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return x if math.isfinite(x) else None


def _read_json_obj(path: str) -> tuple[dict | None, str | None]:
    if not path:
        return None, "yapilandirma_yok"
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "dosya_yok"
    except OSError:
        return None, "okunamadi"
    try:
        d = json.loads(raw)
    except ValueError:
        return None, "bozuk"
    return (d, None) if isinstance(d, dict) else (None, "bozuk")


def tutarlilik_view(path: str, now: datetime) -> dict:
    """`var/durum/tutarlilik_v1.json` ozeti. Yok/bozuk/bayat -> {"var": False, "neden": kod}; asla SectionError atmaz."""
    d, err = _read_json_obj(path)
    if d is None:
        return {"var": False, "neden": err}
    if d.get("sema") != "ml.tutarlilik.v1":
        return {"var": False, "neden": "sema_yanlis"}
    made = parse_z(d.get("uretim"))
    if made is None:
        return {"var": False, "neden": "uretim_yok"}
    age_s = (now - made).total_seconds()
    if age_s > TUTARLILIK_MAX_AGE_DAYS * 86400:
        return {"var": False, "neden": "bayat", "uretim": fmt_z(made), "yas_gun": round(age_s / 86400, 1)}
    reasons = [str(x)[:200] for x in d.get("uyari_nedenleri") or [] if isinstance(x, (str, int, float))][:50] \
        if isinstance(d.get("uyari_nedenleri"), list) else []
    rows = []
    for k in (d.get("kurulumlar") if isinstance(d.get("kurulumlar"), list) else [])[:100]:
        if not isinstance(k, Mapping):
            continue
        ad = str(k.get("ad", "?"))[:40]
        r = {"ad": ad, **{f: _fnum(k.get(f)) for f in _TUT_FIELDS}}
        r["uyari"] = [x for x in reasons if ad in x]
        rows.append(r)
    donem = d.get("donem") if isinstance(d.get("donem"), Mapping) else {}
    note = d.get("not")
    return {"var": True, "uretim": fmt_z(made), "yas_gun": round(age_s / 86400, 1),
            "donem": {"bas": str(donem.get("bas"))[:32] if donem.get("bas") else None,
                      "bit": str(donem.get("bit"))[:32] if donem.get("bit") else None},
            "kurulumlar": rows, "uyari": bool(d.get("uyari")), "uyari_nedenleri": reasons,
            "not": note[:500] if isinstance(note, str) else None}


def pbo_view(pbo_path: str, muhur_path: str) -> dict:
    """`research/holdout/pbo_ozet.json` aile tablosu + `muhur.json` muhur durumu (hash en cok ilk 12 karakter)."""
    out: dict = {"pbo": {"var": False}, "muhur": {"var": False}}
    d, err = _read_json_obj(pbo_path)
    if d is None:
        out["pbo"]["neden"] = err
    else:
        fams = []
        for a in (d.get("aileler") if isinstance(d.get("aileler"), list) else [])[:50]:
            if not isinstance(a, Mapping):
                continue
            fams.append({"aile": str(a.get("aile", "?"))[:60], "tur": str(a.get("tur", ""))[:16],
                         "pbo": _fnum(a.get("pbo")), "dsr": _fnum(a.get("dsr")),
                         "n_yapilandirma": _fnum(a.get("n_yapilandirma")), "T": _fnum(a.get("T")),
                         "durum": str(a.get("durum", ""))[:24], "yorum": str(a.get("yorum") or "")[:128]})
        par = d.get("parametreler") if isinstance(d.get("parametreler"), Mapping) else {}
        out["pbo"] = {"var": True, "aileler": fams,
                      "holdout_oncesi_sinir": str(par.get("holdout_oncesi_sinir"))[:16] if par.get("holdout_oncesi_sinir") else None}
    m, err = _read_json_obj(muhur_path)
    if m is None:
        out["muhur"]["neden"] = err
    else:
        ho = m.get("holdout") if isinstance(m.get("holdout"), Mapping) else {}
        h = m.get("birlesik_sha256")
        out["muhur"] = {"var": True, "muhur_tarihi": str(m.get("muhur_tarihi"))[:32] if m.get("muhur_tarihi") else None,
                        "dosya_sayisi": _fnum(m.get("dosya_sayisi")),
                        "acildi": bool(m.get("acildi")) if "acildi" in m else None,
                        "baslangic": str(ho.get("baslangic"))[:16] if ho.get("baslangic") else None,
                        "bitis": str(ho.get("bitis"))[:16] if ho.get("bitis") else None,
                        "hash12": h[:12] if isinstance(h, str) else None}
    return out


# ---- cikis kaniti (cikis karsi-olgusu gece isi): salt okunur, eksik/bozuk kaynak paneli bozmaz ----
EXITCF_DAYS = 4 * 30                       # kanit penceresi (exit_counterfactual.deltas varsayilani)
_EXITCF_SOURCES = ("paper", "testnet")   # hukum yalniz kendi bot defterinden (exit_counterfactual.SOURCES_VERDICT)


def _ro_connect(path: str):
    import sqlite3
    from urllib.parse import quote
    return sqlite3.connect("file:" + quote(os.path.abspath(path)) + "?mode=ro", uri=True, timeout=2.0)


def exitcf_view(path: str, now: datetime) -> dict:
    """`var/<bot>/exit_counterfactual.sqlite` ozeti (ecf_outcomes = exitcf-v1, ecf_modes = exitcf-v2), kurulum (setup) basina.
    Yok/bozuk/bos -> {"var": False, "neden": kod}; asla istisna atmaz. Delta = alternatif net R - mevcut cikis (ayni yol, ayni maliyet)."""
    import sqlite3
    if not path:
        return {"var": False, "neden": "yapilandirma_yok"}
    if not os.path.exists(path):
        return {"var": False, "neden": "dosya_yok"}
    lo = (now - timedelta(days=EXITCF_DAYS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    hi = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    qs = ",".join("?" * len(_EXITCF_SOURCES))
    try:
        db = _ro_connect(path)
    except Exception:  # noqa: BLE001
        return {"var": False, "neden": "okunamadi"}
    groups: dict[str, dict] = {}
    last = {"v1": None, "v2": None}
    try:
        try:
            ver = db.execute("SELECT MAX(version) FROM ecf_outcomes WHERE bot='learner'").fetchone()[0]
            if ver is not None:
                rows = db.execute(
                    "SELECT source, run_id, trade_id, setup, role, value, net_r, computed_at FROM ecf_outcomes WHERE bot='learner' "
                    f"AND version=? AND source IN ({qs}) AND entry_ts>=? AND entry_ts<? AND window_end_ts<=? AND net_r IS NOT NULL",
                    [ver, *_EXITCF_SOURCES, lo, hi, hi]).fetchall()
                last["v1"] = db.execute("SELECT MAX(computed_at) FROM ecf_outcomes WHERE bot='learner'").fetchone()[0]
                by: dict[tuple, list] = {}
                for r in rows:
                    by.setdefault((r[0], r[1], r[2]), []).append(r)
                for rs in by.values():
                    bases = [r for r in rs if r[4] == "base" and _fnum(r[6]) is not None]
                    if not bases:
                        continue
                    b = max(bases, key=lambda r: (str(r[7]), r[5]))
                    g = groups.setdefault(str(b[3] or "?")[:16], {})
                    g["islem_v1"] = g.get("islem_v1", 0) + 1
                    for role in ("up", "down"):
                        c = [r for r in rs if r[4] == role and _fnum(r[6]) is not None
                             and (r[5] > b[5] if role == "up" else r[5] < b[5])]
                        if c:
                            a = min(c, key=lambda r: abs(r[5] - b[5]))
                            k = g.setdefault(role, [0, 0.0])
                            k[0] += 1
                            k[1] += float(a[6]) - float(b[6])
        except sqlite3.OperationalError:
            pass                                                   # tablo yok: v1 kaniti yok
        try:
            from . import exit_counterfactual as _ecf
            ver = _ecf.modes_version_from_config()                 # 24.11: aktif target_mode'a gore surum (okunamazsa MAX)
            if ver is None:
                ver = db.execute("SELECT MAX(version) FROM ecf_modes WHERE bot='learner'").fetchone()[0]
            if ver is not None:
                rows = db.execute(
                    "SELECT source, run_id, trade_id, setup, variant, net_r FROM ecf_modes WHERE bot='learner' "
                    f"AND version=? AND source IN ({qs}) AND entry_ts>=? AND entry_ts<? AND window_end_ts<=? AND net_r IS NOT NULL",
                    [ver, *_EXITCF_SOURCES, lo, hi, hi]).fetchall()
                last["v2"] = db.execute("SELECT MAX(computed_at) FROM ecf_modes WHERE bot='learner'").fetchone()[0]
                by = {}
                for r in rows:
                    by.setdefault((r[0], r[1], r[2]), {})[r[4]] = r
                for vs in by.values():
                    off = vs.get("off")
                    if off is None or _fnum(off[5]) is None:
                        continue
                    g = groups.setdefault(str(off[3] or "?")[:16], {})
                    g["islem_v2"] = g.get("islem_v2", 0) + 1
                    for mode in ("breakeven", "partial"):
                        on = vs.get(mode)
                        if on is not None and _fnum(on[5]) is not None:
                            k = g.setdefault(mode, [0, 0.0])
                            k[0] += 1
                            k[1] += float(on[5]) - float(off[5])
        except sqlite3.OperationalError:
            pass
    except sqlite3.Error:
        return {"var": False, "neden": "bozuk"}
    finally:
        db.close()
    if not groups:
        return {"var": False, "neden": "kayit_yok"}
    def part(g: dict, key: str) -> dict:
        n, s = g.get(key, [0, None])
        return {"n": n, "delta_r": round(s, 4) if s is not None and math.isfinite(s) else None}

    kurulumlar = []
    for ad in sorted(groups):
        g = groups[ad]
        r = {"kurulum": ad, "islem": max(g.get("islem_v1", 0), g.get("islem_v2", 0)),
             "trail_yukari": part(g, "up"), "trail_asagi": part(g, "down"),
             "basabas": part(g, "breakeven"), "kismi": part(g, "partial")}
        kurulumlar.append(r)
    return {"var": True, "pencere_gun": EXITCF_DAYS, "kurulumlar": kurulumlar,
            "son_kosu_v1": last["v1"], "son_kosu_v2": last["v2"]}


def alinmayan_sonuc_view(path: str) -> dict:
    """`var/durum/alinmayan_sonuc_v1.json` (`ml.alinmayan_sonuc.v1`, alinmayan_sonuc.py yazar): yalniz bicim, yeni hesap yok.
    Yok/bozuk/sema yanlis/kayit yok -> {"var": False, "neden": kod}; asla istisna atmaz. Birim R."""
    try:
        d, err = _read_json_obj(path)
        if d is None:
            return {"var": False, "neden": err}
        if d.get("sema") != "ml.alinmayan_sonuc.v1" or not isinstance(d.get("tablolar"), dict) or not isinstance(d.get("tum_zamanlar"), dict):
            return {"var": False, "neden": "sema_yanlis"}
        if not any(d[k].get("neden") for k in ("tablolar", "tum_zamanlar")):
            return {"var": False, "neden": "kayit_yok"}
        coz = d.get("cozulmedi")
        return {"var": True, "uretim": d.get("uretim"), "birim": d.get("birim") or "R", "pencere_gun": d.get("pencere_gun"),
                "tablolar": d["tablolar"], "tum_zamanlar": d["tum_zamanlar"], "cozulmedi": coz if isinstance(coz, dict) else {},
                "not": d.get("not") if isinstance(d.get("not"), str) else ""}
    except Exception:  # noqa: BLE001
        return {"var": False, "neden": "okunamadi"}
