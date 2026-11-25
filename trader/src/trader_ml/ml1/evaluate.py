"""ML1 degerlendirme: olay basina tek pozisyon secimi, ozetler, kirilimlar, kalibrasyon ve rapor (markdown + json).

Tek pozisyon: ayni event_id icinde yalniz bir aday alinir (ML: en yuksek puan; taban: ilk aday = en erken decision_ts, esitlikte arm_id).
Sonuc R'si `r_net` (maliyet dusulmus). "Edge yok" gecerli bir sonuctur: `verdict` = "no_edge" / "insufficient" / "edge_candidate"."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .model import _clean

FIXED_THRESHOLDS = (0.50, 0.55, 0.60)


# ----------------------------------------------------------------------------------------------------------- secim / ozet
def select_one_per_event(df: pd.DataFrame, score: str | None = None) -> pd.DataFrame:
    """Olay basina tek satir. score=None: ilk aday (en erken decision_ts, esitlikte arm_id); aksi halde `score` sutununda en yuksek
    (esitlikte en erken). event_id yoksa her satir kendi olayidir."""
    if len(df) == 0:
        return df.copy()
    if "event_id" not in df.columns:
        return df.copy()
    d = df.copy()
    d["_arm"] = d["arm_id"].astype(str) if "arm_id" in d.columns else ""
    if score is None:
        d = d.sort_values(["event_id", "decision_ts", "_arm"], kind="stable")
    else:
        d["_neg"] = -d[score].to_numpy(float)
        d = d.sort_values(["event_id", "_neg", "decision_ts", "_arm"], kind="stable")
    d = d.drop_duplicates("event_id", keep="first")
    return d.drop(columns=[c for c in ("_arm", "_neg") if c in d.columns]).sort_values("decision_ts", kind="stable")


def summarize(df: pd.DataFrame) -> dict:
    n = len(df)
    if n == 0:
        return {"trades": 0, "win_pct": None, "mean_R": None, "total_R": 0.0}
    r = df["r_net"].to_numpy(float)
    return {"trades": int(n), "win_pct": float(100.0 * (r > 0).mean()), "mean_R": float(r.mean()), "total_R": float(r.sum())}


def breakdown(df: pd.DataFrame, by: str) -> list[dict]:
    if len(df) == 0:
        return []
    key = df["decision_ts"].dt.year if by == "year" else df[by]
    out = []
    for k, sub in df.groupby(key, sort=True, observed=True):
        out.append({by: str(k), **summarize(sub)})
    return out


def deciles(df: pd.DataFrame, p_col: str = "p", n_bins: int = 10) -> list[dict]:
    """Puan ondaliklari: tahmin edilen ortalama olasilik vs gerceklesen kazanma orani (tum adaylar, olay secimi YOK)."""
    if len(df) < n_bins:
        return []
    bins = pd.qcut(df[p_col].rank(method="first"), n_bins, labels=False)
    out = []
    for b, sub in df.groupby(bins, sort=True):
        out.append({"decile": int(b) + 1, "n": len(sub), "pred": float(sub[p_col].mean()),
                    "win_rate": float((sub["r_net"] > 0).mean()), "mean_R": float(sub["r_net"].mean())})
    return out


def _section(df: pd.DataFrame, threshold: float | None) -> dict:
    """Bir veri parcasi (OOS ya da holdout): taban + ML sonuclari, kirilimlar, kalibrasyon."""
    if len(df) == 0:
        return {"n_candidates": 0}
    first = select_one_per_event(df, None)
    best = select_one_per_event(df, "p")
    ml = best[best["p"] >= threshold] if threshold is not None else best.iloc[0:0]
    sec = {
        "n_candidates": len(df), "n_events": len(first),
        "baseline_all_candidates": summarize(df), "baseline_first_per_event": summarize(first),
        "ml": summarize(ml), "ml_threshold": threshold,
        "fixed_thresholds": {f"{t:.2f}": summarize(best[best["p"] >= t]) for t in FIXED_THRESHOLDS},
        "by_year": {"ml": breakdown(ml, "year"), "baseline": breakdown(first, "year")},
        "by_tf": {"ml": breakdown(ml, "tf"), "baseline": breakdown(first, "tf")},
        "by_group": {"ml": breakdown(ml, "group"), "baseline": breakdown(first, "group")},
        "calibration_deciles": deciles(df),
    }
    return sec


# ----------------------------------------------------------------------------------------------------------- rapor
def verdict(oos: dict, hold: dict, threshold: float | None) -> dict:
    reasons: list[str] = []
    if threshold is None or not oos.get("n_candidates"):
        return {"verdict": "insufficient", "reasons": ["esik secilemedi (min islem sayisi saglanmadi) ya da OOS verisi yok"]}
    o, b = oos["ml"], oos["baseline_first_per_event"]
    if o["trades"] == 0 or o["mean_R"] is None or o["mean_R"] <= 0:
        reasons.append("OOS ML ortalama net R <= 0")
    if b["mean_R"] is not None and o["mean_R"] is not None and o["mean_R"] <= b["mean_R"]:
        reasons.append("OOS ML ortalama net R, tabandan (olay basina ilk aday) iyi degil")
    h = hold.get("ml") if hold else None
    if not h or h["trades"] == 0:
        reasons.append("holdout'ta ML islemi yok")
    elif h["mean_R"] <= 0:
        reasons.append("holdout ML ortalama net R <= 0")
    if reasons:
        return {"verdict": "no_edge", "reasons": reasons}
    return {"verdict": "edge_candidate", "reasons": ["OOS ve holdout ML ortalama net R > 0 ve tabandan iyi (kucuk orneklem uyarisina bak)"]}


def build_report(res: dict) -> dict:
    """train.run sonucundan json-uyumlu rapor sozlugu."""
    oos, hold = res["oos"], res["holdout"]
    th = res.get("threshold")
    s_oos, s_hold = _section(oos, th), _section(hold, th)
    rep = {
        "schema": "ml1-report/1", "config": res["config"], "data": res["data"], "ridge": res.get("ridge"), "threshold": th,
        "threshold_note": res.get("threshold_note"), "folds": res.get("folds", []), "oos": s_oos, "holdout": s_hold,
        "verdict": verdict(s_oos, s_hold, th),
    }
    return _clean(rep)


def _f(x, nd=3) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def _row(name: str, s: dict) -> str:
    return f"| {name} | {s['trades']} | {_f(s['win_pct'], 1)} | {_f(s['mean_R'])} | {_f(s['total_R'], 1)} |"


def _table(rows: list[str]) -> list[str]:
    return ["| set | trades | win% | mean net R | total net R |", "|---|---|---|---|---|"] + rows + [""]


def _bd(sec: dict, key: str, title: str) -> list[str]:
    out = [f"#### {title}", "", "| key | ML trades | ML mean R | ML total R | baseline trades | baseline mean R |", "|---|---|---|---|---|---|"]
    bm = {r[next(k for k in r if k not in ("trades", "win_pct", "mean_R", "total_R"))]: r for r in sec[key]["baseline"]}
    mm = {r[next(k for k in r if k not in ("trades", "win_pct", "mean_R", "total_R"))]: r for r in sec[key]["ml"]}
    for k in sorted(set(bm) | set(mm)):
        m, b = mm.get(k), bm.get(k)
        out.append(f"| {k} | {m['trades'] if m else 0} | {_f(m['mean_R']) if m else '-'} | {_f(m['total_R'], 1) if m else '-'} | "
                   f"{b['trades'] if b else 0} | {_f(b['mean_R']) if b else '-'} |")
    return out + [""]


def render_markdown(rep: dict) -> str:
    L = ["# ML1 egitim / degerlendirme raporu", ""]
    v = rep["verdict"]
    L += [f"**Karar: {v['verdict']}**", ""] + [f"- {r}" for r in v["reasons"]] + [""]
    d = rep["data"]
    L += ["## Veri", "", f"- tablo satiri: {d.get('n_rows')}; etiketli (status ok, censored degil): {d.get('n_labeled')}",
          f"- censored pay: {_f(d.get('censored_share'), 4)} (etiket disi; ayri raporlanir)",
          f"- dev: {d.get('dev_start')} .. {d.get('holdout_start')}; holdout: {d.get('holdout_start')} .. {d.get('data_end')}",
          f"- embargo (maks. elde tutma): {d.get('embargo_days')} gun; ridge: {rep.get('ridge')}; esik: {rep.get('threshold')}",
          f"- {rep.get('threshold_note') or ''}", ""]
    for name, key in (("Walk-forward OOS", "oos"), ("Holdout (tek sefer)", "holdout")):
        s = rep[key]
        L += [f"## {name}", ""]
        if not s.get("n_candidates"):
            L += ["veri yok", ""]
            continue
        rows = [_row("baseline: tum adaylar", s["baseline_all_candidates"]),
                _row("baseline: olay basina ilk aday", s["baseline_first_per_event"]),
                _row(f"ML1 (esik {rep.get('threshold')})", s["ml"])]
        rows += [_row(f"ML1 sabit esik {t}", x) for t, x in s["fixed_thresholds"].items()]
        L += [f"adaylar: {s['n_candidates']}, olaylar: {s['n_events']}", ""] + _table(rows)
        L += _bd(s, "by_year", "Yila gore") + _bd(s, "by_tf", "tf'e gore") + _bd(s, "by_group", "Fikir grubuna gore")
        L += ["#### Kalibrasyon (puan ondaligi)", "", "| decile | n | tahmin | gerceklesen kazanma | mean R |", "|---|---|---|---|---|"]
        L += [f"| {x['decile']} | {x['n']} | {_f(x['pred'])} | {_f(x['win_rate'])} | {_f(x['mean_R'])} |" for x in s["calibration_deciles"]] + [""]
    L += ["## Katlar", "", "| test baslangic | test bitis | egitim | test |", "|---|---|---|---|"]
    L += [f"| {f['test_start']} | {f['test_end']} | {f['n_train']} | {f['n_test']} |" for f in rep.get("folds", [])] + [""]
    return "\n".join(L)


def write_report(rep: dict, out_dir: str | Path) -> tuple[Path, Path]:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    jp, mp = d / "ml1_report.json", d / "ml1_report.md"
    jp.write_text(json.dumps(rep, indent=1, sort_keys=True), encoding="utf-8")
    mp.write_text(render_markdown(rep), encoding="utf-8")
    return jp, mp
