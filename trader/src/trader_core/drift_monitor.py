"""Gunluk sapma izleyicisi (WP-2) -- docs/kagit-degerlendirme-plani.md Bolum 4 ("kdp-v1") uygulamasi.

Saf standart kutuphane. SALT OKUNUR: defter `mode=ro` acilir; izleyici emir vermez, KILL/PAUSE yazmaz, parametre degistirmez,
geri test calistirmaz, kilitli donem verisini okumaz, Telegram'a mesaj ATMAZ (tek gonderici saglik kontrolunun
`drift_alert` sonucudur; docs/saglik-spec.md 16.6). Tek cikti: `<var>/<bot>/drift.json` (sema `drift/1`) ve kendi
durum dosyasi `<var>/<bot>/drift_state.json`.

Pencere sifirlama kapsami (v1): `param_activations` (apply/rollback) ve status.json'dan gozlenen strateji surumu / ML kipi
(active, model_id) degisikligi algilanir. Plan Bolum 2 madde 4 (veto kipi, maliyet ayari, cift listesi, `target_trade_risk`)
v1'de ALGILANMAZ; bu degisiklikler pencereyi kendilignden sifirlamaz (motor yapilandirmasi okunmaz).

Duzeyler YALNIZ: OK, IZLE, UYARI, YETERSIZ (UYARI ustu yoktur). Referans sabitleri plandan AYNEN gomulur; yeniden hesaplanmaz,
bootstrap kosulmaz (plan 4.4: "izleyici bootstrap kosmaz"). Esitlik iyi tarafa duser.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

__all__ = ["PLAN_VERSION", "SCHEMA", "LEVELS", "evaluate", "load_ledger", "read_status", "run_bot", "interp_p1",
           "cusum_replay", "report_lines", "verify_reference", "REF_TRADES_SHA256", "REF_SUMMARY_SHA256", "P1_TABLE"]

PLAN_VERSION = "kdp-v1"
SCHEMA = "drift/1"
OK, IZLE, UYARI, YETERSIZ = "OK", "IZLE", "UYARI", "YETERSIZ"
LEVELS = (OK, IZLE, UYARI, YETERSIZ)
# "en agir": eksik girdi hicbir zaman "iyi" sayilmaz (plan 3.3) -> YETERSIZ, OK'tan agirdir
_SEV = {OK: 0, YETERSIZ: 1, IZLE: 2, UYARI: 3}

# ---------------------------------------------------------------------------- referans (plan Bolum 1, 4) -- DEGISTIRILMEZ
REF_DIR = "research/ml/frozen/backtest_run_ml_cand_v1b_native33"
REF_TRADES_SHA256 = "5fd204a0a34be9a2ced0d55a29f6893b1de361d897016062d6d557c2a7b69061"
REF_SUMMARY_SHA256 = "ea2f58ca9a75f77895015978ec2beb8fa3af41924f39daa541531cba5a73228c"
LAMBDA0 = 2.49                         # aday/gun
FEE_MODEL_BP = 5.00
SLIP_ENTRY_B, SLIP_STOP_B, SLIP_MKT_B = 2.2, 5.2, 2.0
COST_REF_R = 0.127
FUNDING_REF_R = 0.0028
CUSUM_MU0, CUSUM_SIGMA0, CUSUM_K = -0.111, 1.224, 0.5
CUSUM_CLIP_LO, CUSUM_CLIP_HI = -1.5, 3.0
CUSUM_IZLE, CUSUM_UYARI = 3.0, 4.0
CUSUM_COOLDOWN = 30
MIN_N = 20                              # P1 / C1 / M3 / F1 asgari ornek (kural basina asagida)
P1_MAX_N = 300
CANDIDATE_SKIPS = frozenset({"veto_blocked", "veto_missing", "veto_stale", "entry_gate_closed", "order_failed", "ml_filter"})
STOP_EXITS = frozenset({"stop", "trail_stop", "liquidation"})
CHECKPOINTS = (30, 100, 150, 200)

# n, %2,5, %10, ortanca, %90 (plan 4.4 -- baglayici tablo)
P1_TABLE = (
    (20, -14.5, -11.1, -1.1, 16.9), (30, -18.7, -14.1, -0.8, 22.0), (40, -22.4, -16.4, -0.1, 25.9),
    (50, -25.6, -18.2, 0.5, 29.5), (75, -32.1, -22.0, 1.9, 37.6), (100, -37.0, -24.9, 4.0, 43.7),
    (125, -41.4, -27.4, 6.0, 50.5), (150, -45.4, -29.1, 7.3, 56.3), (175, -48.4, -30.9, 9.3, 60.9),
    (200, -51.6, -32.3, 11.2, 66.3), (250, -57.7, -34.4, 15.3, 75.7), (300, -61.0, -36.2, 19.1, 85.4),
)


# ---------------------------------------------------------------------------- yardimcilar
def _f(x):
    """Sonlu float ya da None (bool/None/nan/inf -> None)."""
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def parse_ts(s):
    """ISO zaman -> UTC aware datetime; okunamazsa None."""
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    if not isinstance(s, str):
        return None
    try:
        d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)


def fmt_ts(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _r(x):
    return round(x, 9)


def _gt(x, t):
    return _r(x) > _r(t)


def _lt(x, t):
    return _r(x) < _r(t)


def _ge(x, t):
    return _r(x) >= _r(t)


def _le(x, t):
    return _r(x) <= _r(t)


def _mean(xs):
    return sum(xs) / len(xs)


def _rule(level, value=None, threshold=None, n=0, note=""):
    if level not in LEVELS:
        level = YETERSIZ
    v = _f(value)
    return {"level": level, "value": v, "threshold": threshold, "n": int(n), "note": note}


def _worst(levels):
    return max(levels, key=lambda l: _SEV.get(l, 1)) if levels else YETERSIZ


def _hi(value, izle, uyari):
    return UYARI if _gt(value, uyari) else IZLE if _gt(value, izle) else OK


# ---------------------------------------------------------------------------- defter / durum okuma
def load_ledger(path: str, bot: str) -> dict:
    """Defteri SALT OKUNUR acar (`file:...?mode=ro`); {trades, decisions, activations}. Hata -> istisna (cagiran yakalar)."""
    uri = "file:" + quote(os.path.abspath(path)) + "?mode=ro"
    c = sqlite3.connect(uri, uri=True, timeout=5.0)
    try:
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA query_only=1")
        trades = [dict(r) for r in c.execute("SELECT * FROM v_closed_trades WHERE bot=?", (bot,))]
        decisions = [dict(r) for r in c.execute(
            "SELECT bar_close_ts, final_action, skip_reason, veto_status, param_version_id FROM v_decisions WHERE bot=?", (bot,))]
        acts = [dict(r) for r in c.execute(
            "SELECT activated_at, kind, version_id FROM param_activations WHERE bot=? ORDER BY id", (bot,))]
    finally:
        c.close()
    return {"trades": trades, "decisions": decisions, "activations": acts}


def read_status(path: str, bot: str) -> dict | None:
    """status.json (engine-status/1) -> dict ya da None (yok/bozuk/sema ya da bot uyusmaz)."""
    try:
        with open(path, "rb") as f:
            raw = f.read(2_000_001)
        if len(raw) > 2_000_000:
            return None
        d = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(d, dict) or d.get("schema") != "engine-status/1" or d.get("bot") != bot:
        return None
    return d


def verify_reference(ref_dir: str) -> dict:
    """Istege bagli: referans kosunun sha256 sabitlerini dosyalarla karsilastirir (yeniden hesaplamaz). {dosya: True/False/None}."""
    out = {}
    for name, want in (("trades.csv", REF_TRADES_SHA256), ("summary.json", REF_SUMMARY_SHA256)):
        try:
            h = hashlib.sha256()
            with open(os.path.join(ref_dir, name), "rb") as f:
                for blk in iter(lambda: f.read(1 << 20), b""):
                    h.update(blk)
            out[name] = h.hexdigest() == want
        except OSError:
            out[name] = None
    return out


# ---------------------------------------------------------------------------- islem temizligi
def _clean_trades(rows):
    """-> (gecerli islemler, atlanan satir sayisi). Gecerli: sirali (exit_ts, trade_id).
    Atlanan satir sessizce temizlenmez: sayisi `skipped_rows` olarak yazilir ve ilgili kurallari en iyi IZLE yapar (plan 4.0)."""
    good, skipped = [], 0
    for r in rows:
        try:
            ex, en = parse_ts(r.get("exit_ts")), parse_ts(r.get("entry_ts"))
            pr, rm = _f(r.get("planned_risk")), _f(r.get("r_multiple"))
            qty, ep, xp = _f(r.get("qty")), _f(r.get("entry_price")), _f(r.get("exit_price"))
            fe, fx, fund = _f(r.get("fee_entry")), _f(r.get("fee_exit")), _f(r.get("funding_paid"))
            tid = r.get("trade_id")
            if (ex is None or en is None or pr is None or pr <= 0 or rm is None or qty is None or qty <= 0
                    or ep is None or ep <= 0 or xp is None or xp <= 0 or fe is None or fx is None or fund is None
                    or isinstance(tid, bool) or not isinstance(tid, int)):
                skipped += 1
                continue
            good.append({"trade_id": tid, "entry": en, "exit": ex, "reason": r.get("exit_reason"), "qty": qty,
                         "ep": ep, "xp": xp, "pe": _f(r.get("planned_entry")), "px": _f(r.get("planned_exit")),
                         "risk": pr, "fe": fe, "fx": fx, "fund": fund, "se": _f(r.get("slippage_entry")),
                         "sx": _f(r.get("slippage_exit")), "r": rm})
        except Exception:  # noqa: BLE001 - bozuk satir sessizce temizlenmez, sayilir
            skipped += 1
    good.sort(key=lambda t: (t["exit"], t["trade_id"]))
    return good, skipped


# ---------------------------------------------------------------------------- P1 ve CUSUM
def interp_p1(n: int):
    """n in [20, 300] -> (p2.5, p10, ortanca, p90) komsu iki satir arasi dogrusal; disinda None."""
    if n < P1_TABLE[0][0] or n > P1_TABLE[-1][0]:
        return None
    for a, b in zip(P1_TABLE, P1_TABLE[1:]):
        if a[0] <= n <= b[0]:
            w = (n - a[0]) / (b[0] - a[0])
            return tuple(a[i] + w * (b[i] - a[i]) for i in range(1, 5))
    return tuple(P1_TABLE[-1][1:])


def cusum_replay(rs):
    """Penceredeki r_multiple dizisini (cikis sirasiyla) bastan isler. -> dict(S, n, cooldown, alarms=[1-tabanli indeks])."""
    s, cd, alarms = 0.0, 0, []
    for i, r in enumerate(rs, 1):
        x = min(max(r, CUSUM_CLIP_LO), CUSUM_CLIP_HI)
        z = (x - CUSUM_MU0) / CUSUM_SIGMA0
        s = max(0.0, s - z - CUSUM_K)
        suppressed = cd > 0
        if cd > 0:
            cd -= 1
        if i >= MIN_N and _ge(s, CUSUM_UYARI) and not suppressed:
            alarms.append(i)
            s, cd = 0.0, CUSUM_COOLDOWN
    return {"S": s, "n": len(rs), "cooldown": cd, "alarms": alarms}


# ---------------------------------------------------------------------------- kurallar
def _frequency_rules(decisions, acts, now, mode_note):
    rows = []
    for d in decisions:
        ts = parse_ts(d.get("bar_close_ts"))
        if ts is None or ts > now:
            continue
        a = d.get("final_action") == "entered" or (d.get("final_action") == "skipped"
                                                   and d.get("skip_reason") in CANDIDATE_SKIPS)
        rows.append((ts, a, d.get("final_action") == "entered"))
    rules = {}
    if not rows:
        for k in ("S1", "S2", "S3"):
            rules[k] = _rule(YETERSIZ, None, None, 0, "defterde karar satiri yok")
        return rules
    first = min(t for t, _, _ in rows)
    cands = [t for t, a, _ in rows if a]
    ref = max(cands) if cands else first
    hrs = (now - ref).total_seconds() / 3600.0
    s1 = _hi(hrs, 96.0, 120.0)
    rules["S1"] = _rule(s1, hrs, {"IZLE": "> 96 saat", "UYARI": "> 120 saat"}, len(cands),
                        ("son aday " if cands else "aday yok; ilk karar ") + f"{hrs:.1f} saat once" + mode_note)
    chg = [parse_ts(a.get("activated_at")) for a in acts if a.get("kind") != "initial"]
    for key, days, (ilo, ihi), (ulo, uhi), exp in (("S2", 14, (20, 55), (15, 62), 34.9), ("S3", 30, (51, 99), (44, 108), 74.7)):
        cut = now - timedelta(days=days)
        if first > cut:
            rules[key] = _rule(YETERSIZ, None, None, 0, f"ilk karar {days} gunden yeni")
            continue
        cnt = sum(1 for t, a, _ in rows if a and t >= cut)
        lvl = UYARI if (_le(cnt, ulo) or _ge(cnt, uhi)) else IZLE if (_le(cnt, ilo) or _ge(cnt, ihi)) else OK
        note = f"{days} gunde {cnt} aday (beklenen {exp})"
        if lvl == UYARI and any(c is not None and c >= cut for c in chg):
            lvl, note = IZLE, note + "; ayar degisti, kiyas yaklasik"
        if key == "S2":
            ent = sum(1 for t, _, e in rows if e and t >= cut)
            note += f"; veto gecis orani {ent / cnt:.2f}" if cnt else ""
        rules[key] = _rule(lvl, cnt, {"IZLE": f"<= {ilo} ya da >= {ihi}", "UYARI": f"<= {ulo} ya da >= {uhi}"}, cnt, note + mode_note)
    return rules


def _cost_rules(good, status, mode):
    last = list(reversed(good))          # en yeni once
    rules = {}
    # M1
    l20 = last[:20]
    if len(l20) < 10:
        rules["M1"] = _rule(YETERSIZ, None, None, len(l20), "en az 10 islem gerekir")
    else:
        vals = [t["fe"] / (t["qty"] * t["ep"]) * 1e4 for t in l20] + [t["fx"] / (t["qty"] * t["xp"]) * 1e4 for t in l20]
        m = _mean(vals)
        lvl = UYARI if (_gt(m, 5.50) or _lt(m, 4.50)) else IZLE if (_gt(m, 5.25) or _lt(m, 4.75)) else OK
        rules["M1"] = _rule(lvl, m, {"IZLE": "> 5.25 ya da < 4.75 bp", "UYARI": "> 5.50 ya da < 4.50 bp"}, len(l20),
                            f"komisyon ortalamasi {m:.2f} bp (model {FEE_MODEL_BP:.2f})")
    paper = mode == "paper"
    # M2
    ent = [t["se"] * 1e4 for t in last if t["se"] is not None][:50]
    stp = [t["sx"] * 1e4 for t in last if t["sx"] is not None and t["reason"] in STOP_EXITS][:50]
    mkt = [t["sx"] * 1e4 for t in last if t["sx"] is not None and t["reason"] not in STOP_EXITS][:50]
    for key, xs, b, label in (("M2_giris", ent, SLIP_ENTRY_B, "giris"), ("M2_stop", stp, SLIP_STOP_B, "stop"),
                              ("M2_piyasa", mkt, SLIP_MKT_B, "piyasa cikisi")):
        if len(xs) < 10:
            rules[key] = _rule(YETERSIZ, None, None, len(xs), "en az 10 dolum gerekir")
            continue
        m = _mean(xs)
        izle_t, uyari_t = 1.5 * b + 1.0, 2.0 * b + 2.0
        lvl = _hi(m, izle_t, uyari_t)
        note = f"{label} kaymasi ortalamasi {m:.2f} bp (model {b})"
        thr = {"IZLE": f"> {izle_t:.1f} bp", "UYARI": f"> {uyari_t:.1f} bp"}
        floor = {"M2_giris": 1.5, "M2_stop": 4.5}.get(key)
        if paper and floor is not None:
            thr["UYARI_alt_kagit"] = f"< {floor} bp"
            if _lt(m, floor):
                lvl, note = UYARI, note + "; kagit: benzetim tutarliligi (benzetim modelden az maliyet yaziyor)"
        rules[key] = _rule(lvl, m, thr, len(xs), note)
    # M3
    l50 = last[:50]
    if len(l50) < 20:
        rules["M3"] = _rule(YETERSIZ, None, None, len(l50), "en az 20 islem gerekir")
    else:
        vals = []
        for t in l50:
            pex = t["px"] if t["px"] is not None else t["xp"]
            slip = t["qty"] * (t["pe"] or 0.0) * (t["se"] or 0.0) + t["qty"] * pex * (t["sx"] or 0.0)
            vals.append((t["fe"] + t["fx"] + slip) / t["risk"])
        m = _mean(vals)
        rules["M3"] = _rule(_hi(m, 0.18, 0.21), m, {"IZLE": "> 0.18", "UYARI": "> 0.21"}, len(l50),
                            f"islem basi maliyet/risk {m:.3f} R (referans {COST_REF_R})")
    # F1
    l50 = last[:50]
    if len(l50) < 20:
        rules["F1"] = _rule(YETERSIZ, None, None, len(l50), "en az 20 islem gerekir")
    else:
        m = _mean([t["fund"] / t["risk"] for t in l50])
        lvl = UYARI if _gt(m, 0.030) else IZLE if (_gt(m, 0.020) or _lt(m, -0.020)) else OK
        rules["F1"] = _rule(lvl, m, {"IZLE": "> 0.020 ya da < -0.020", "UYARI": "> 0.030"}, len(l50),
                            f"fonlama/risk {m:.4f} (referans +{FUNDING_REF_R})")
    # F2
    fm = None
    if status is not None:
        cnt = status.get("counters")
        fm = cnt.get("funding_missing") if isinstance(cnt, dict) else None
        fm = fm if isinstance(fm, int) and not isinstance(fm, bool) and fm >= 0 else None
    if fm is None:
        rules["F2"] = _rule(YETERSIZ, None, None, 0, "status.json okunamadi")
    else:
        rules["F2"] = _rule(UYARI if fm > 0 else OK, fm, {"UYARI": "> 0"}, fm, f"eksik fonlama sayaci {fm}")
    return rules


def _window_rules(win, state_prev, now, same_window):
    n = len(win)
    rs = [t["r"] for t in win]
    rules = {}
    # P1
    c = sum(rs)
    if n < MIN_N:
        rules["P1"] = _rule(YETERSIZ, c, None, n, "pencerede en az 20 kapanmis islem gerekir")
    elif n > P1_MAX_N:
        rules["P1"] = _rule(YETERSIZ, c, None, n, "tablo uzatilmali (n > 300)")
    else:
        p25, p10, med, p90 = interp_p1(n)
        lvl = UYARI if _lt(c, p25) else IZLE if _lt(c, p10) else OK
        rules["P1"] = _rule(lvl, c, {"IZLE": f"< {p10:.2f}", "UYARI": f"< {p25:.2f}"}, n,
                            f"kumulatif net R {c:.2f}; olagan aralik {p10:.1f} ... +{p90:.1f}; ortanca {med:.1f}")
        rules["P1"]["p10"], rules["P1"]["p90"] = p10, p90
    # C1
    cu = cusum_replay(rs)
    prev = state_prev.get("cusum") if same_window and isinstance(state_prev.get("cusum"), dict) else None
    last_alarm = cu["alarms"][-1] if cu["alarms"] else None
    new_alarm = False
    if last_alarm is not None:
        if prev is not None and isinstance(prev.get("processed_n"), int):
            new_alarm = last_alarm > prev["processed_n"]
        else:
            # kullanilabilir onceki durum yok (dosya yok/bozuk/pencere degisti): alarm islemi son 36 saatte kapandiysa yeni sayilir
            new_alarm = win[last_alarm - 1]["exit"] >= now - timedelta(hours=36)
    reported_at = None
    sticky = False
    if new_alarm:
        reported_at = fmt_ts(now)
    elif (prev is not None and last_alarm is not None and prev.get("uyari_trade_n") == last_alarm
          and prev.get("processed_n") == n):       # yeni islem geldiyse (sogutma basladi) UYARI tasinmaz
        rep_dt = parse_ts(prev.get("uyari_reported_at"))
        if rep_dt is not None and timedelta(0) <= now - rep_dt < timedelta(hours=20):
            sticky, reported_at = True, prev.get("uyari_reported_at")   # ayni gun yeniden calistirma UYARI'yi dusurmez
    S = cu["S"]
    if n < MIN_N:
        lvl, note = YETERSIZ, "pencerede en az 20 kapanmis islem gerekir"
    elif new_alarm or sticky:
        lvl, note = UYARI, "CUSUM esigi asildi; sayac sifirlandi, sonraki 30 islemde yeni UYARI uretilmez"
    elif cu["cooldown"] > 0:
        lvl, note = IZLE, "UYARI sonrasi sogutma suresi (30 islem); yeni UYARI uretilmez"
    elif _ge(S, CUSUM_IZLE):
        lvl, note = IZLE, "kotulesme birikiyor"
    else:
        lvl, note = OK, "birikim dusuk"
    rules["C1"] = _rule(lvl, S, {"IZLE": ">= 3.0", "UYARI": ">= 4.0"}, n, f"S={S:.3f}; {note}")
    state_cusum = {"S": round(S, 9), "processed_n": n, "last_trade_id": win[-1]["trade_id"] if win else None,
                   "cooldown": cu["cooldown"], "uyari_trade_n": cu["alarms"][-1] if cu["alarms"] else None,
                   "uyari_reported_at": reported_at}
    return rules, state_cusum


def _next_checkpoint(n):
    tgt = next((k for k in CHECKPOINTS if k > n), None)
    if tgt is None:
        tgt = (n // 100 + 1) * 100
    return {"n": tgt, "remaining": tgt - n}


# ---------------------------------------------------------------------------- ana islev
def evaluate(data: dict | None, status: dict | None, state: dict | None, now: datetime, *, bot: str,
             mode: str | None = None) -> tuple[dict, dict]:
    """Saf hesap. data=None -> girdi okunamadi (hepsi YETERSIZ). -> (drift.json govdesi, yeni durum)."""
    state = state if isinstance(state, dict) else {}
    now = now.astimezone(timezone.utc)
    st_mode = status.get("mode") if isinstance(status, dict) and isinstance(status.get("mode"), str) else None
    mode = mode or st_mode or (state.get("mode") if isinstance(state.get("mode"), str) else None) or "unknown"
    out = {"schema": SCHEMA, "generated_at": fmt_ts(now), "bot": bot, "mode": mode, "plan_version": PLAN_VERSION}
    ids = ("S1", "S2", "S3", "M1", "M2_giris", "M2_stop", "M2_piyasa", "M3", "F1", "F2", "P1", "C1")
    if data is None:
        out.update(window={"key": None, "start": None, "n": 0}, skipped_rows=0, next_checkpoint=_next_checkpoint(0),
                   rules={k: _rule(YETERSIZ, None, None, 0, "defter okunamadi ya da yok") for k in ids}, overall=YETERSIZ)
        return out, {"schema": 1, "window": state.get("window")}
    good, skipped = _clean_trades(data["trades"])
    acts = data["activations"]
    # pencere (plan 2): anahtar = bot, kip, strateji@surum, param_version_id. `|ml=inactive` soneki 24.11 (ML filtreleri silindi)
    # sonrasi sabit: eski pencere durum dosyalariyla anahtar uyumu icin korunur (degisirse tum pencereler bir kez sifirlanirdi).
    strat = status.get("strategy") if isinstance(status, dict) and isinstance(status.get("strategy"), dict) else {}
    status_key = f"{strat.get('name')}@{strat.get('version')}|ml=inactive" if status is not None else None
    pw = state.get("window") if isinstance(state.get("window"), dict) else {}
    runtime_start = pw.get("runtime_start")
    if status_key is not None and pw.get("status_key") not in (None, status_key):
        # strateji surumu / ML kipi degisti: yeni pencere; motorun baslama zamani anlamliysa (gecmis degil-gelecek degil, onceki
        # baslangictan sonra) oradan, degilse gozlenen andan
        runtime_start = fmt_ts(now)
        sa = parse_ts(status.get("started_at")) if isinstance(status, dict) else None
        prev_start = parse_ts(pw.get("start"))
        if sa is not None and sa <= now and (prev_start is None or sa > prev_start):
            runtime_start = fmt_ts(sa)
    elif status_key is None:
        status_key, runtime_start = pw.get("status_key"), pw.get("runtime_start")
    act_ts = [parse_ts(a.get("activated_at")) for a in acts if a.get("kind") != "initial"]
    act_ts = [t for t in act_ts if t is not None and t <= now]
    starts = act_ts + ([parse_ts(runtime_start)] if parse_ts(runtime_start) else [])
    wstart = max(starts) if starts else None
    pv = None
    for a in acts:
        ts = parse_ts(a.get("activated_at"))
        if a.get("version_id") is not None and (ts is None or ts <= now):   # gelecek tarihli etkinlestirme sayilmaz
            pv = a["version_id"]
    wkey = f"{bot}|{mode}|{status_key}|pv{pv}"
    win = [t for t in good if wstart is None or t["entry"] >= wstart]
    same = pw.get("start") == (fmt_ts(wstart) if wstart else None)      # yalniz pencere baslangicina bakilir (anahtar metni degil)
    mode_note = "; bot bu surede kapali ya da duraklatilmis olabilir"
    rules = {}
    rules.update(_frequency_rules(data["decisions"], acts, now, mode_note))
    rules.update(_cost_rules(good, status, mode))
    wr, cusum_state = _window_rules(win, state, now, same)
    rules.update(wr)
    if skipped:
        for k in ("M1", "M2_giris", "M2_stop", "M2_piyasa", "M3", "F1", "P1", "C1"):
            if rules[k]["level"] == OK:
                rules[k]["level"] = IZLE
                rules[k]["skip_downgraded"] = True
                rules[k]["note"] += f"; {skipped} bozuk satir atlandi"
    for k in rules:
        if rules[k]["level"] not in LEVELS:
            rules[k]["level"] = YETERSIZ
    n = len(win)
    out.update(window={"key": wkey, "start": fmt_ts(wstart) if wstart else None, "n": n}, rules={k: rules[k] for k in ids},
               overall=_worst([r["level"] for r in rules.values()]), skipped_rows=skipped, next_checkpoint=_next_checkpoint(n))
    new_state = {"schema": 1, "window": {"key": wkey, "start": out["window"]["start"], "status_key": status_key,
                                         "runtime_start": runtime_start}, "cusum": cusum_state, "mode": mode, "updated_at": fmt_ts(now)}
    return out, new_state


# ---------------------------------------------------------------------------- gunluk rapor satirlari (sade Turkce)
def _confidence(n: int) -> str:
    if n < 100:
        return f"Henüz çok az işlem var ({n}): sonuç şans mı beceri mi ayırt edilemez."
    if n < 300:
        return f"Erken gösterge ({n} işlem): yön hakkında fikir verir, kanıt değildir."
    return f"{n} işlem birikti: hâlâ kesin kanıt değil; sıklık ve maliyet uyumu daha güvenilir göstergedir."


def report_lines(body: dict) -> list[str]:
    """drift.json govdesinden "📐" ile baslayan sade Turkce satirlar (kural kimligi/ham kod/Ingilizce alan adi yok)."""
    rules, n = body.get("rules", {}), body.get("window", {}).get("n", 0)
    lines = []
    sk = int(body.get("skipped_rows") or 0)
    # yalniz bozuk satir yuzunden IZLE'ye inen kurallar uyari satiri uretmez; tek "okunamadi" satiri yazilir
    lv = lambda *ks: _worst([(OK if rules[k].get("skip_downgraded") else rules[k]["level"])  # noqa: E731
                             for k in ks if k in rules])
    rem = body.get("next_checkpoint", {}).get("remaining")
    tail = f" · sıradaki değerlendirmeye {rem} işlem kaldı" if isinstance(rem, int) else ""
    freq, cost, fund = lv("S1", "S2", "S3"), lv("M1", "M2_giris", "M2_stop", "M2_piyasa", "M3"), lv("F1", "F2")
    if body.get("overall") == YETERSIZ and all(r["level"] == YETERSIZ for r in rules.values()):
        lines.append("📐 Henüz yeterli veri yok; bot davranışı karşılaştırılamıyor." + tail)
    elif {freq, cost, fund} <= {OK, YETERSIZ}:
        lines.append("📐 Bot beklendiği gibi davranıyor (sıklık, maliyet, fonlama normal)" + tail)
    else:
        if freq in (IZLE, UYARI):
            s2 = rules.get("S2", {})
            c = s2.get("value")
            if rules.get("S1", {}).get("level") in (IZLE, UYARI) and rules["S1"].get("value") is not None:
                lines.append(f"📐 İşlem sıklığı beklenenden düşük: son {int(rules['S1']['value'])} saattir yeni fırsat yok. "
                             "Bot kapalı ya da duraklatılmış olabilir; durdurulmadı, inceleme gerekir.")
            elif c is not None:
                kind = "düşük" if c < 34.9 else "yüksek"
                lines.append(f"📐 İşlem sıklığı beklenenden {kind}: son 14 günde {int(c)} fırsat (beklenen yaklaşık 35). "
                             "Bot durdurulmadı; inceleme gerekir.")
            else:
                lines.append("📐 İşlem sıklığı olağan aralığın kenarında. Bot durdurulmadı; inceleme gerekir.")
        if cost in (IZLE, UYARI):
            lines.append("📐 İşlem maliyeti (komisyon ve kayma) beklenenin dışında. Bot durdurulmadı; inceleme gerekir.")
        if fund in (IZLE, UYARI):
            lines.append("📐 Fonlama maliyeti beklenenin dışında. Bot durdurulmadı; inceleme gerekir.")
        if not lines:
            lines.append("📐 Bot beklendiği gibi davranıyor (sıklık, maliyet, fonlama normal)" + tail)
    p1, c1 = rules.get("P1", {}), rules.get("C1", {})
    if p1.get("level") in (OK, IZLE, UYARI) and p1.get("value") is not None:
        def _tr(x):
            return ("−" if x < 0 else "+") + f"{abs(x):.1f}".replace(".", ",")
        lo = (f" (olağan aralık {_tr(p1['p10'])} … {_tr(p1['p90'])})"
              if isinstance(p1.get("p10"), (int, float)) and isinstance(p1.get("p90"), (int, float)) else "")
        lines.append(f"📐 Kâr/zarar: {n} işlemde {p1['value']:+.1f} R{lo}. {_confidence(n)}")
    else:
        lines.append(f"📐 Kâr/zarar: {n} işlem; henüz değerlendirilemiyor. {_confidence(n)}")
    if c1.get("level") in (IZLE, UYARI) and not c1.get("skip_downgraded"):
        lines.append("📐 Kayıplar art arda birikiyor; bot durdurulmadı, inceleme gerekir.")
    if sk > 0:
        lines.append(f"📐 {sk} kayıt okunamadı; karşılaştırma yaklaşık")
    return lines


# ---------------------------------------------------------------------------- G/C: dosya yazimi ve tek tur
def atomic_write_json(path: str, obj) -> None:
    d = os.path.dirname(os.path.abspath(path))
    tmp = os.path.join(d, f".{os.path.basename(path)}.tmp-{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, 0o644)      # saglik (root) ve rapor okur; icerik gizli degil
    except OSError:
        pass


def _load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("schema") == 1 else {}
    except (OSError, ValueError):
        return {}


def run_bot(var_dir: str, bot: str, now: datetime, *, mode: str | None = None, write: bool = True) -> tuple[dict, bool]:
    """Tek tur: defter (salt okunur) + status.json -> drift.json. -> (govde, defter_bozuk_mu). Defter dosyasi yoksa
    bozuk sayilmaz (bot kapali olabilir): YETERSIZ yazilir."""
    bdir = os.path.join(var_dir, bot)
    ledger = os.path.join(bdir, "ledger.sqlite")
    status = read_status(os.path.join(bdir, "status.json"), bot)
    state_path = os.path.join(bdir, "drift_state.json")
    state = _load_state(state_path)
    broken, data = False, None
    if os.path.exists(ledger):
        try:
            data = load_ledger(ledger, bot)
        except Exception:  # noqa: BLE001 - okunamayan defter: YETERSIZ, calisma bozuk
            broken = True
    body, new_state = evaluate(data, status, state, now, bot=bot, mode=mode)
    body["report_lines"] = report_lines(body)
    if write:
        atomic_write_json(os.path.join(bdir, "drift.json"), body)
        if data is not None:
            atomic_write_json(state_path, new_state)
    return body, broken
