#!/usr/bin/env python3
"""Kagit-geri test tutarlilik raporu (haftalik; docs/motor/tutarlilik-raporu-spec.md, Faz 2a). YALNIZ BILGI VERIR: islemi engellemez,
kurulum kapatmaz, kapi degildir; motor etkilenmez.

Son 7 tam UTC gunu (`[pazartesi 00:00Z - 7g, pazartesi 00:00Z)`) icin kagit defteri ile `backtest --env paper` (kagitla AYNI strateji,
arms/kume/maliyet katmani ve cok kurullu sinyal kaynagi; `--source store` + ayni market.sqlite) ciktisini kurulum (setup) basina
karsilastirir. Donemin kilitli doneme (2026-05-01 -> 2026-11-01) dusen kismi kesilir; kilit burada da ayrica denetlenir.
Parametre/surum degisimi olan donemde (param_activations) onceki alt donem disarida birakilir ve rapora yazilir.
Ciktilar: `<veri>/var/rapor/tutarlilik/<YYYY-AA-GG>.md` ve `<veri>/var/durum/tutarlilik_v1.json` (atomik).
Geri test calismazsa (desteklenmeyen/veri yok) sessizce baska strateji KULLANILMAZ: `not` alani "TIKANDI: ..." yazar, cikis 0.
Test: `main(argv, now_fn=, env=, runner=)`; `runner(spec) -> BacktestResult`.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

log = logging.getLogger("trader.tutarlilik.run")
SCHEMA = "ml.tutarlilik.v1"
EQ_FIELDS = ("entry_price", "qty", "exit_ts", "exit_price", "exit_reason", "fee_entry", "fee_exit", "funding_paid", "realized_pnl")
COST_FIELDS = ("fee_entry", "fee_exit", "funding_paid", "realized_pnl")
CAUSES = ("paper_gap", "no_paper_record", "data_conflict", "maliyet", "gecikme", "veri", "aciklanamayan")
MIN_TRADES = 5
MATCH_MIN = 0.90
R_ABS_MIN, R_REL = 1.0, 0.20
ENTRY_SLIP_MAX_BPS = 10.0
EXIT_OK = 0


def data_root(env) -> Path:
    v = (env.get("TRADER_DATA_ROOT") or "").strip()
    return Path(v) if v and os.path.isabs(v) else _HERE.parent


# --------------------------------------------------------------------------------------------- donem
def week_window(now: datetime) -> tuple[datetime, datetime]:
    """Son 7 tam UTC gunu: [pazartesi 00:00Z - 7g, pazartesi 00:00Z). `now` pazartesi 00:30Z ise o pazartesi."""
    day = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    monday = day - timedelta(days=day.weekday())
    return monday - timedelta(days=7), monday


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(x):
    """Defter zaman damgasi -> UTC pandas.Timestamp (None/NaT -> None)."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    try:
        t = pd.Timestamp(x)
    except (ValueError, TypeError):
        return None
    if pd.isna(t):
        return None
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


# --------------------------------------------------------------------------------------------- defter okuma
def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def read_trades(path) -> pd.DataFrame:
    c = _ro(path)
    try:
        return pd.read_sql("SELECT * FROM v_trades", c)
    finally:
        c.close()


def read_decisions(path) -> pd.DataFrame:
    c = _ro(path)
    try:
        return pd.read_sql("SELECT pair, side, bar_close_ts, final_action, skip_reason, veto_reason FROM v_decisions", c)
    finally:
        c.close()


def read_activations(path) -> list[dict]:
    c = _ro(path)
    try:
        rows = c.execute("SELECT a.id, a.version_id, a.kind, a.activated_at, v.params FROM param_activations a "
                         "JOIN param_versions v ON v.id = a.version_id ORDER BY a.id").fetchall()
    finally:
        c.close()
    out = []
    for i, vid, kind, at, params in rows:
        try:
            p = json.loads(params)
        except (TypeError, ValueError):
            p = {}
        out.append({"id": i, "version_id": vid, "kind": kind, "at": _ts(at), "params": p})
    return out


def apply_activation_cut(start: datetime, end: datetime, acts: list[dict]) -> tuple[datetime, dict, str | None]:
    """Pencere icinde (start, end) etkinlesen parametre surumu varsa onceki alt donem disarida: yeni baslangic = son etkinlesme.
    Dondurur: (baslangic, geri test parametreleri, rapor notu)."""
    note = None
    cut = None
    for a in acts:
        if a["at"] is not None and pd.Timestamp(start) < a["at"] < pd.Timestamp(end):
            cut = a["at"]
    if cut is not None:
        start = cut.to_pydatetime()
        note = f"param_activation_changed: {_iso(start)} oncesi disarida birakildi"
    cur = None
    for a in acts:
        if a["at"] is not None and a["at"] <= pd.Timestamp(end):
            cur = a
    params = {}
    if cur is not None:
        from trader_core import ledger as L
        params = {k: v for k, v in cur["params"].items() if k in L.PARAM_KEYS and k != "trigger_tf"}
    return start, params, note


# --------------------------------------------------------------------------------------------- karsilastirma
def _gap_near(gaps_fn, pair, t0, t1) -> str | None:
    """Pair icin [t0, t1] yakininda eksik mum/cakisma: 'conflict' | 'missing' | None."""
    if gaps_fn is None or t0 is None:
        return None
    try:
        found = gaps_fn(pair, t0 - pd.Timedelta(hours=1), (t1 or t0) + pd.Timedelta(minutes=15))
    except Exception:  # noqa: BLE001
        return None
    if not found:
        return None
    return "conflict" if any(r == "conflict" for r in found) else "missing"


def _norm_trades(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Anahtar (pair, side, entry_ts) -> satir. Pencerede girilmis islemler; pencere sonundan sonra kapananlar ACIK sayilir."""
    out = {}
    for r in df.to_dict("records"):
        et = _ts(r.get("entry_ts"))
        if et is None or not (start <= et < end):
            continue
        xt = _ts(r.get("exit_ts"))
        if xt is not None and xt >= end:
            for k in ("exit_ts", "exit_price", "exit_reason", "fee_exit", "funding_paid", "realized_pnl", "gross_pnl", "r_multiple"):
                if k in r:
                    r[k] = None
            xt = None
        r["_et"], r["_xt"] = et, xt
        out[(r["pair"], r["side"], et)] = r
    return out


def _eq(a, b, rel=1e-9) -> bool:
    na = a is None or (isinstance(a, float) and np.isnan(a))
    nb = b is None or (isinstance(b, float) and np.isnan(b))
    if na or nb:
        return na and nb
    if isinstance(a, (int, float, np.integer, np.floating)) and isinstance(b, (int, float, np.integer, np.floating)):
        return abs(float(a) - float(b)) <= rel * max(1.0, abs(float(a)))
    ta, tb = _ts(a), _ts(b)
    if ta is not None and tb is not None and isinstance(a, str) and isinstance(b, str) and a[:2] == "20" and b[:2] == "20":
        return ta == tb
    return a == b


def _slip_bps(side: str, paper: float, bt: float, leg: str) -> float | None:
    """Kagit aleyhine pozitif, bps. Giris: long'ta kagit daha pahali; cikis: long'ta kagit daha ucuz."""
    if paper is None or bt is None or not bt or np.isnan(paper) or np.isnan(bt):
        return None
    sign = 1.0 if side == "long" else -1.0
    if leg == "exit":
        sign = -sign
    return sign * (float(paper) - float(bt)) / float(bt) * 1e4


def compare(paper_df: pd.DataFrame, bt_df: pd.DataFrame, start: datetime, end: datetime, *, decisions: pd.DataFrame | None = None,
            gaps_fn=None, any_decision_ts: set | None = None) -> dict:
    """Kurulum (setup) basina olculer + fark nedenleri. Saf islev (dosya okumaz): testlerde sentetik cerceve verilir."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    P, B = _norm_trades(paper_df, s, e), _norm_trades(bt_df, s, e)
    both = sorted(set(P) & set(B))
    only_p = sorted(set(P) - set(B))
    only_b = sorted(set(B) - set(P))
    dec_idx: dict = {}
    if decisions is not None and len(decisions):
        for r in decisions.to_dict("records"):
            dec_idx.setdefault((r["pair"], r["side"], _ts(r["bar_close_ts"])), []).append(r)
    dec_ts = any_decision_ts if any_decision_ts is not None else {_ts(x) for x in (decisions["bar_close_ts"] if decisions is not None and len(decisions) else [])}
    causes: dict = {}                     # anahtar -> sinif (her fark olayi bir kez)
    consumed: set = set()

    def data_cause(pair, t0, t1):
        g = _gap_near(gaps_fn, pair, t0, t1)
        return "data_conflict" if g == "conflict" else ("veri" if g == "missing" else None)

    # gecikme (giris): ayni cift/yon, kagit-yalniz giris geri test-yalniz girisinden SONRA
    for kb in only_b:
        for kp in only_p:
            if kp in consumed or kp[0] != kb[0] or kp[1] != kb[1]:
                continue
            if kp[2] > kb[2] and (kp[2] - kb[2]) <= pd.Timedelta(hours=24):
                causes[kb] = "gecikme"                       # tek olay: bir kez sayilir (kagit-yalniz esi `consumed`)
                consumed.update({kb, kp})
                break
    for kb in only_b:
        if kb in consumed:
            continue
        d = dec_idx.get(kb, [])
        if any(x["skip_reason"] in ("entry_gate_closed", "other") for x in d):
            causes[kb] = "paper_gap"
        elif not d and kb[2] not in dec_ts:
            causes[kb] = "no_paper_record"
        else:
            causes[kb] = data_cause(kb[0], kb[2], B[kb]["_xt"]) or "aciklanamayan"
    for kp in only_p:
        if kp in consumed:
            continue
        causes[kp] = data_cause(kp[0], kp[2], P[kp]["_xt"]) or "aciklanamayan"
    entry_slip, exit_slip = {}, {}
    for k in both:
        p, b = P[k], B[k]
        bad = [f for f in EQ_FIELDS if not _eq(p.get(f), b.get(f))]
        se = _slip_bps(k[1], p.get("entry_price"), b.get("entry_price"), "entry")
        sx = _slip_bps(k[1], p.get("exit_price"), b.get("exit_price"), "exit") if (p["_xt"] is not None and b["_xt"] is not None) else None
        entry_slip[k], exit_slip[k] = se, sx
        if not bad:
            continue
        if p["_xt"] is not None and b["_xt"] is not None and p["_xt"] > b["_xt"]:
            causes[k] = "gecikme"
        elif set(bad) <= set(COST_FIELDS):
            causes[k] = "maliyet"
        else:
            causes[k] = data_cause(k[0], k[2], p["_xt"] or b["_xt"]) or "aciklanamayan"

    setups = sorted({str(r.get("setup")) for r in list(P.values()) + list(B.values())})
    out = []
    for su in setups:
        ps = {k: v for k, v in P.items() if str(v.get("setup")) == su}
        bs = {k: v for k, v in B.items() if str(v.get("setup")) == su}
        # eslesme kumesi: kagit setup'i esas (esleseni kagitin setup'ina yazariz)
        ks_both = [k for k in both if str(P[k].get("setup")) == su]
        ks_p = [k for k in only_p if str(P[k].get("setup")) == su]
        ks_b = [k for k in only_b if str(B[k].get("setup")) == su]
        # kagit-yalniz ile geri test-yalniz giris gecikmesi farkli setup'a dusebilir: sayilar kendi setup'ina aittir
        n_e, n_p, n_b = len(ks_both), len(ks_p), len(ks_b)
        # kagit tarafi setup'a gore, geri test tarafi (esleseni) kagit setup'una gore
        bt_keys = set(ks_b) | set(ks_both)
        pr = [ps[k] for k in ps]
        br = [B[k] for k in bt_keys]

        def agg(rows):
            closed = [r for r in rows if r["_xt"] is not None]
            wins = sum(1 for r in closed if (r.get("realized_pnl") or 0) > 0)
            rs = [float(r["r_multiple"]) for r in closed if r.get("r_multiple") is not None and not pd.isna(r["r_multiple"])]
            pn = [float(r["realized_pnl"]) for r in closed if r.get("realized_pnl") is not None and not pd.isna(r["realized_pnl"])]
            return dict(n=len(rows), closed=len(closed), win=(wins / len(closed) if closed else None),
                        R=sum(rs), absR=sum(abs(x) for x in rs), pnl=sum(pn))
        ap, ab = agg(pr), agg(br)
        den = n_e + n_p + n_b
        es = [entry_slip[k] for k in ks_both if entry_slip.get(k) is not None]
        xs = [exit_slip[k] for k in ks_both if exit_slip.get(k) is not None]
        ncause = {c: 0 for c in CAUSES}
        for k, c in causes.items():
            if k in ks_both or k in ks_p or k in ks_b:
                ncause[c] += 1
        out.append(dict(
            ad=su, kagit_islem=ap["n"], bt_islem=ab["n"], eslesen=n_e,
            eslesme_orani=(round(n_e / den, 4) if den else None), yalniz_kagit=n_p, yalniz_bt=n_b,
            giris_kayma_bps_ort=(round(float(np.mean(es)), 3) if es else None),
            giris_kayma_bps_en_kotu=(round(float(max(es)), 3) if es else None),
            cikis_kayma_bps_ort=(round(float(np.mean(xs)), 3) if xs else None),
            cikis_kayma_bps_en_kotu=(round(float(max(xs)), 3) if xs else None),
            kagit_R=round(ap["R"], 4), bt_R=round(ab["R"], 4), kagit_pnl=round(ap["pnl"], 4), bt_pnl=round(ab["pnl"], 4),
            kagit_kazanma=(round(ap["win"], 4) if ap["win"] is not None else None),
            bt_kazanma=(round(ab["win"], 4) if ab["win"] is not None else None),
            kagit_mutlak_R=round(ap["absR"], 4), nedenler=ncause))
    return {"kurulumlar": out}


def warn_reasons(setups: list[dict]) -> list[str]:
    """Esik (oneri): kurulumun en az 5 islemi varsa ve (aciklanamayan>0 | eslesme<%90 | |dR|>max(1R, kagit |R| %20) | ort. giris kaymasi>10bps)."""
    why = []
    for s in setups:
        if max(s["kagit_islem"], s["bt_islem"]) < MIN_TRADES:
            continue
        n = s["nedenler"]
        if n.get("aciklanamayan", 0) > 0:
            why.append(f"{s['ad']}: aciklanamayan={n['aciklanamayan']}")
        if s["eslesme_orani"] is not None and s["eslesme_orani"] < MATCH_MIN:
            why.append(f"{s['ad']}: eslesme %{s['eslesme_orani'] * 100:.0f} < %{MATCH_MIN * 100:.0f}")
        lim = max(R_ABS_MIN, R_REL * s.get("kagit_mutlak_R", 0.0))
        if abs(s["bt_R"] - s["kagit_R"]) > lim:
            why.append(f"{s['ad']}: |R farki|={abs(s['bt_R'] - s['kagit_R']):.2f} > {lim:.2f}")
        if s["giris_kayma_bps_ort"] is not None and s["giris_kayma_bps_ort"] > ENTRY_SLIP_MAX_BPS:
            why.append(f"{s['ad']}: ort. giris kaymasi {s['giris_kayma_bps_ort']:.1f} bps > {ENTRY_SLIP_MAX_BPS:.0f}")
    return why


# --------------------------------------------------------------------------------------------- cikti
def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def make_summary(now: datetime, start: datetime, end: datetime, setups: list[dict], why: list[str], note: str | None) -> dict:
    keep = ("ad", "kagit_islem", "bt_islem", "eslesme_orani", "eslesen", "yalniz_kagit", "yalniz_bt", "giris_kayma_bps_ort",
            "cikis_kayma_bps_ort", "kagit_R", "bt_R", "kagit_pnl", "bt_pnl", "kagit_kazanma", "bt_kazanma", "nedenler")
    return {"sema": SCHEMA, "uretim": _iso(now), "donem": {"bas": _iso(start), "bit": _iso(end)},
            "kurulumlar": [{k: s[k] for k in keep} for s in setups], "uyari": bool(why), "uyari_nedenleri": why, "not": note}


def _f(x, nd=2, plus=False):
    if x is None:
        return "-"
    return (f"{x:+.{nd}f}" if plus else f"{x:.{nd}f}").replace(".", ",")


def render_md(summary: dict, setups: list[dict]) -> str:
    L = [f"# Kagit - geri test tutarlilik raporu ({summary['donem']['bas'][:10]} -> {summary['donem']['bit'][:10]})", "",
         "Yalniz bilgi: islemi engellemez, kurulum kapatmaz, kapi degildir. Yontem: `backtest --env paper` (ayni strateji/arms/"
         "kume/maliyet, ayni `market.sqlite`) ile kagit defteri, anahtar `(pair, side, entry_ts)`.", "",
         f"- Uretim: {summary['uretim']}", f"- Donem: {summary['donem']['bas']} .. {summary['donem']['bit']}"]
    if summary["not"]:
        L.append(f"- Not: {summary['not']}")
    L.append(f"- Uyari: {'EVET (tutarlilik_sapma)' if summary['uyari'] else 'yok'}")
    for w in summary["uyari_nedenleri"]:
        L.append(f"  - {w}")
    L += ["", "## Kurulum basina", "",
          "| Kurulum | Islem (kagit/GT) | Eslesme | Yalniz kagit | Yalniz GT | Giris kayma ort/en kotu (bps) | Cikis kayma ort/en kotu (bps) |",
          "|---|---|---|---|---|---|---|"]
    for s in setups:
        orn = "-" if s["eslesme_orani"] is None else f"%{s['eslesme_orani'] * 100:.0f}"
        L.append(f"| {s['ad']} | {s['kagit_islem']}/{s['bt_islem']} | {orn} | {s['yalniz_kagit']} | {s['yalniz_bt']} | "
                 f"{_f(s['giris_kayma_bps_ort'], 1)} / {_f(s['giris_kayma_bps_en_kotu'], 1)} | "
                 f"{_f(s['cikis_kayma_bps_ort'], 1)} / {_f(s['cikis_kayma_bps_en_kotu'], 1)} |")
    L += ["", "| Kurulum | Kazanma (kagit/GT) | Toplam R (kagit/GT/fark) | Toplam PnL (kagit/GT/fark) |", "|---|---|---|---|"]
    for s in setups:
        kw = "-" if s["kagit_kazanma"] is None else f"%{s['kagit_kazanma'] * 100:.0f}"
        bw = "-" if s["bt_kazanma"] is None else f"%{s['bt_kazanma'] * 100:.0f}"
        L.append(f"| {s['ad']} | {kw} / {bw} | {_f(s['kagit_R'])} / {_f(s['bt_R'])} / {_f(s['kagit_R'] - s['bt_R'], 2, True)} | "
                 f"{_f(s['kagit_pnl'])} / {_f(s['bt_pnl'])} / {_f(s['kagit_pnl'] - s['bt_pnl'], 2, True)} |")
    L += ["", "## Fark nedenleri", "", "| Kurulum | " + " | ".join(CAUSES) + " |", "|---|" + "---|" * len(CAUSES)]
    for s in setups:
        L.append(f"| {s['ad']} | " + " | ".join(str(s["nedenler"][c]) for c in CAUSES) + " |")
    L += ["", "Sinif aciklamasi: `paper_gap` (kagitta kapi kapali/stale kaydi), `no_paper_record` (kagitta o bar icin karar yok: motor "
          "kapaliydi), `data_conflict` (feed cakismasi), `maliyet` (komisyon/funding), `gecikme` (kagit giris/cikis geri testten sonraki "
          "barda), `veri` (eksik mum), `aciklanamayan`.",
          "", "Bilinen sinirlar: pencere basinda acik kagit pozisyonlari geri testte yoktur (bos baslar); ML/M1 paketi ve ders durumu "
          "kosu anindaki dosyalardir.", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------------------------- calistirma
def _default_runner(spec):
    from trader_engine import backtest as BT
    return BT.run_spec(spec)


def _empty(now, start, end, note) -> tuple[dict, list]:
    return make_summary(now, start, end, [], [], note), []


def run(now: datetime, *, paper_ledger: Path, market_db: Path, config_dir: Path, work_root: Path, runner=None,
        window: tuple[datetime, datetime] | None = None) -> tuple[dict, list]:
    from trader_engine import backtest as BT
    from trader_engine.holdout import HOLDOUT, KILIT_ACIK, BacktestArgError, check_holdout
    start, end = window if window is not None else week_window(now)   # window: elle yeniden kosu / test (kilit ve kesim yine uygulanir)
    notes: list[str] = []
    if not KILIT_ACIK and start < HOLDOUT[1] and end > HOLDOUT[0]:
        if end <= HOLDOUT[1]:
            return _empty(now, start, end, "donem tamamen kilitli donemde: okunmadi")
        start = HOLDOUT[1]
        notes.append(f"donemin {HOLDOUT[1]:%Y-%m-%d} oncesi kilitli doneme dustugu icin kesildi")
    check_holdout(start, end)                                  # ek (motor tarafi zaten var)
    if not Path(paper_ledger).exists():
        return _empty(now, start, end, "kagit defteri yok")
    try:
        acts = read_activations(paper_ledger)
        paper_all = read_trades(paper_ledger)
        decisions = read_decisions(paper_ledger)
    except Exception as e:  # noqa: BLE001
        return _empty(now, start, end, f"TIKANDI: kagit defteri okunamadi: {type(e).__name__}: {e}")
    start, params, cut_note = apply_activation_cut(start, end, acts)
    if cut_note:
        notes.append(cut_note)
    if end <= start:
        return _empty(now, start, end, "; ".join(notes + ["karsilastirilacak alt donem kalmadi"]))
    # kagit ozsermayesi pencere basinda (siralama: baslangic + kapanmis islemlerin gerceklesen K/Z'si)
    wallet = None
    try:
        from trader_engine.config import load_cli_config
        cfg = load_cli_config(config_dir, "learner", "paper")
        pnl0 = 0.0
        for r in paper_all.to_dict("records"):
            xt = _ts(r.get("exit_ts"))
            if xt is not None and xt < pd.Timestamp(start) and r.get("realized_pnl") is not None and not pd.isna(r["realized_pnl"]):
                pnl0 += float(r["realized_pnl"])
        wallet = float(cfg.wallet_start) + pnl0
    except Exception as e:  # noqa: BLE001
        return _empty(now, start, end, f"TIKANDI: kagit yapilandirmasi okunamadi: {type(e).__name__}: {e}")
    open_at_start = [1 for r in paper_all.to_dict("records")
                     if _ts(r.get("entry_ts")) is not None and _ts(r.get("entry_ts")) < pd.Timestamp(start)
                     and (_ts(r.get("exit_ts")) is None or _ts(r.get("exit_ts")) >= pd.Timestamp(start))]
    if open_at_start:
        notes.append(f"pencere basinda {len(open_at_start)} acik kagit pozisyonu var; geri test bos baslar (sapma beklenir)")
    work_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="tut_", dir=str(work_root)))
    try:
        spec = BT.BacktestSpec(id=f"tutarlilik_{start:%Y%m%d}", start=start, end=end, env="paper", source="store",
                               market_db=str(market_db), config_dir=str(config_dir), out_root=str(work), params=params,
                               wallet_start=wallet, record_filtered=True)
        try:
            res = (runner or _default_runner)(spec)
        except BacktestArgError as e:
            return _empty(now, start, end, "; ".join(notes + [f"TIKANDI: geri test reddetti ({e.code}): {e}"]))
        except Exception as e:  # noqa: BLE001
            return _empty(now, start, end, "; ".join(notes + [f"TIKANDI: geri test calismadi: {type(e).__name__}: {e}"]))
        bt = read_trades(Path(res.out_dir) / "ledger.sqlite")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    gaps_fn = _store_gaps(market_db)
    cmp_ = compare(paper_all, bt, start, end, decisions=decisions, gaps_fn=gaps_fn)
    setups = cmp_["kurulumlar"]
    why = warn_reasons(setups)
    return make_summary(now, start, end, setups, why, "; ".join(notes) or None), setups


def _store_gaps(market_db):
    def fn(pair, t0, t1):
        from trader_engine.marketdata.store import MarketStore
        st = MarketStore(market_db, read_only=True)
        try:
            a, b = int(t0.timestamp() * 1000), int(t1.timestamp() * 1000)
            rows = []
            for tf in ("1m", "15m", "1h"):
                rows += st.gaps_in(pair, tf, a, b)
            return [r for _, r in rows]
        finally:
            st.close()
    return fn


def main(argv=None, *, now_fn=None, env=None, runner=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", required=True)
    ap.add_argument("--now", help="sabit zaman (UTC, ISO; testler icin)")
    ap.add_argument("--data-root")
    ap.add_argument("--config-dir")
    ap.add_argument("--paper-ledger")
    ap.add_argument("--market-db")
    ap.add_argument("--start", help="elle yeniden kosu: pencere basi (UTC, ISO); --end ile birlikte")
    ap.add_argument("--end", help="elle yeniden kosu: pencere sonu (UTC, ISO)")
    ap.add_argument("--dry-run", action="store_true", help="hesapla, dosya yazma (ozet stdout)")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    env = os.environ if env is None else env
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    if a.now:
        now = datetime.fromisoformat(a.now.replace("Z", "+00:00")).astimezone(timezone.utc)
    root = Path(a.data_root) if a.data_root else data_root(env)
    cfgd = Path(a.config_dir) if a.config_dir else _HERE.parent / "config"
    ledger = Path(a.paper_ledger) if a.paper_ledger else root / "var" / "learner" / "ledger.sqlite"
    mdb = Path(a.market_db) if a.market_db else root / "var" / "market.sqlite"
    rapor = root / "var" / "rapor" / "tutarlilik"
    window = None
    if a.start or a.end:
        if not (a.start and a.end):
            print("--start ve --end birlikte verilmeli", file=sys.stderr)
            return 1
        try:
            window = tuple(datetime.fromisoformat(x.replace("Z", "+00:00")).astimezone(timezone.utc) if "T" in x or "+" in x or x.endswith("Z")
                           else datetime.strptime(x, "%Y-%m-%d").replace(tzinfo=timezone.utc) for x in (a.start, a.end))
        except ValueError:
            print("--start/--end cozulemedi", file=sys.stderr)
            return 1
        if window[1] <= window[0]:
            print("--end > --start olmali", file=sys.stderr)
            return 1
    try:
        summary, setups = run(now, paper_ledger=ledger, market_db=mdb, config_dir=cfgd, work_root=rapor / ".work", runner=runner,
                              window=window)
    except Exception as e:  # noqa: BLE001  (rapor bilgi amaclidir; beklenmeyen hata da dosyaya yazilir, cikis 0)
        log.exception("tutarlilik beklenmeyen hata")
        s, _e = window if window is not None else week_window(now)
        summary, setups = _empty(now, s, _e, f"TIKANDI: beklenmeyen hata: {type(e).__name__}: {e}")
    if a.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return EXIT_OK
    day = summary["donem"]["bit"][:10]
    write_atomic(rapor / f"{day}.md", render_md(summary, setups))
    write_atomic(root / "var" / "durum" / "tutarlilik_v1.json", json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=False) + "\n")
    print(json.dumps({"status": "ok", "donem": summary["donem"], "uyari": summary["uyari"], "not": summary["not"]}, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
