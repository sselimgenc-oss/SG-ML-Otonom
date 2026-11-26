"""Rapor uretimi: butun bolumleri toplar (`build_report`) ve markdown / JSON / CSV / tek satir ozet metinlerini dondurur.
Dosya yazimi ve saat CLI'dadir; burada hicbir yere yazilmaz, `now` disaridan verilir."""
from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import exits as EX
from . import gates as GA
from . import guard
from . import inputs as I
from . import regimes as RG
from . import sizing as SZ
from .stats import merge, DASH, finalize_tables, tr_sayi, tr_isaretli

SECTION_ORDER = ("exits", "gates", "regimes", "sizing")
SECTION_TITLES = {"exits": "1 Çıkış karnesi", "gates": "2 Kapı ve veto karnesi", "regimes": "3 Piyasa koşulu",
                  "dokum": "4 Alt grup ve yıl satırları", "sizing": "5 Küçük hesap"}
CSV_COLS = ["trade_id", "pair", "side", "setup", "regime", "exit_reason", "net_r", "gross_r", "mfe_r", "mae_r", "geri_verme_r",
            "verim", "post_fav_r_24", "post_adv_r_24", "post_close_r_24", "ilk_dokunus_24", "erken_cikis_24",
            "post_fav_r_72", "post_adv_r_72", "post_close_r_72", "ilk_dokunus_72", "erken_cikis_72", "durum_24", "durum_72", "ozet"]
W_LOCK = "Kilitli dönem 2026-05-01..2026-11-01 okunmadı; atlanan satır: {n}."
W_WISH = "Bu rapor ayar değiştirmez; geçmişe bakarak 'keşke' okuması içerir."
W_CF = ("Alınmayan sinyallerin sonucu (karşı-olgu) üst sınırdır: emir gerçekleşmesi, sonraki kapılar ve gerçek çıkış kuralı "
        "hesaba katılmaz (varsayım).")
W_FUT = "Çıkış sonrası yol ve 'trend ödedi' etiketi geleceği kullanır; yalnız değerlendirmedir."


@dataclass
class Options:
    mode: str                       # 'bot' | 'run'
    bot: str | None = None
    ledger: str | None = None
    cf: str | None = None
    market: str | None = None
    budget: str | None = None
    run_dir: str | None = None
    history: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    now: datetime = None
    sections: tuple = SECTION_ORDER
    wallets: tuple = (250.0, 300.0, 1000.0)
    risk: float | None = None
    risk_usd: float | None = None
    compare_backtest: str | None = None
    synthetic_rules: bool = False
    synthetic_steps: dict = field(default_factory=dict)
    config: str | None = None


def _cfg(path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        return {}


def _load_run(run_dir: Path, since, until):
    """Backtest kosusu: (meta, decisions, dskip, trades, tskip, conn)."""
    try:
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise I.ReportError("meta_missing", f"meta.json okunamadi: {run_dir}") from e
    return meta


def build_report(o: Options) -> dict:
    cfg = _cfg(o.config)
    del I.FALLBACK_LOG[:]
    now_iso = guard.iso(o.now)
    since = guard.iso(o.since) if o.since else None
    until = guard.iso(o.until) if o.until else now_iso
    secs = [s for s in SECTION_ORDER if s in o.sections]
    warnings: list[str] = []
    counters = {"holdout_skipped": 0, "holdout_skipped_trades": 0, "holdout_skipped_decisions": 0, "holdout_skipped_cf": 0,
                "pending": 0, "data_gap": 0}
    backtest = o.mode == "run"
    meta: dict = {"now": now_iso, "sections": secs}
    run_dir = Path(o.run_dir) if backtest else None
    if backtest:
        bmeta = _load_run(run_dir, since, until)
        rid = bmeta.get("id") or run_dir.name
        target = f"bt_{rid}"
        per = bmeta.get("period")
        merge(meta, {"mod": f"backtest:{rid}", "kural_kaynagi_kosu": bmeta.get("rules_source")})
        try:
            if not isinstance(per, (list, tuple)) or len(per) != 2:
                raise ValueError("period")
            ps, pe = I.utc_dt(per[0]), I.utc_dt(per[1])
        except (TypeError, ValueError, IndexError, KeyError, AttributeError) as e:
            raise I.ReportError("meta_period", "meta.json period [baslangic, bitis] olmali") from e
        try:
            guard.check_run(ps, pe)
        except guard.BacktestArgError:
            return {"status": "holdout_locked", "target": target, "meta": meta, "files": {
                "rapor.json": json.dumps({"status": "holdout_locked"}, sort_keys=True) + "\n",
                "rapor.md": "Kilitli dönem kesişimi: koşu okunmadı (holdout_locked).\n",
                "cikis_islemler.csv": "", "ozet.txt": ""}, "counters": counters, "n_trades": 0, "n_decisions": 0, "k_rapor": 0}
        meta["donem"] = f"{per[0]}..{per[1]}"
        ledger_path = run_dir / "ledger.sqlite"
    else:
        target = o.bot
        ledger_path = Path(o.ledger)
        meta["mod"] = f"{cfg.get('mode') or 'bilinmiyor'}:{o.bot}"
    conn = I.open_ro(ledger_path, "ledger_missing")
    reader = None
    try:
        meta["defter_surumu"] = I.check_ledger_schema(conn)
        decisions, dskip = I.load_decisions(conn, since, until)
        shadow = I.load_shadow(conn, since, until)          # WP-3 8-2: sema 4; yoksa None
        has_xr = False
        if backtest:
            by_id = {d["id"]: d for d in decisions}
            trades, tskip = I.load_trades_csv(run_dir / "trades.csv", since, until, by_id)
        else:
            has_xr = I.has_column(conn, "v_closed_trades", "exit_regime") or I.has_column(conn, "trade_exits", "exit_regime")
            trades, tskip = I.load_trades_ledger(conn, since, until, has_xr)
    finally:
        conn.close()
    counters["holdout_skipped_trades"], counters["holdout_skipped_decisions"] = tskip, dskip

    cf, cf_warn, cfskip = None, None, 0
    if not backtest:
        cf, cfskip, cf_warn = I.load_cf(o.cf, o.bot, now_iso, since, until, {d["id"] for d in decisions})
        if cf_warn:
            warnings.append(cf_warn)
    cf_shadow = None
    if not backtest and shadow:
        cf_shadow = I.load_cf_shadow(o.cf, o.bot, now_iso, since, until, {s["id"] for s in shadow})
    counters["holdout_skipped_cf"] = cfskip
    counters["holdout_skipped"] = tskip + dskip   # islem + atlanan karar (karsi-olgu satiri atlanan kararla ayni olay)

    sqlite_rules = None
    try:
        if backtest:
            if o.history:
                reader = I.FeatherBars(o.history)
            else:
                warnings.append("history_missing")
        else:
            if o.market and Path(o.market).is_file():
                reader = I.SqliteBars(o.market)
                sqlite_rules = reader.rules()
            else:
                warnings.append("market_missing")
        meta["mum_kaynagi"] = (reader.source if reader else "yok") + " (son fiyat)"
        status = "empty" if (not trades and not decisions) else "ok"

        now_ms = I.dt_ms(o.now)
        tables: list = []
        out: dict = {}
        csv_rows: list = []
        ozet: dict = {}
        if "exits" in secs:
            ex = EX.build(trades, decisions, cf, reader, now_ms)
            out["exits"] = ex
            csv_rows = ex["csv_rows"]
            merge(ozet, ex["ozet"])
            for k in ("pending", "data_gap"):
                counters[k] += ex["counters"][k]
            counters["holdout_skipped_windows"] = ex["counters"]["holdout_skipped_windows"]
        period_days = None
        lo = since or min([d["bar_close_ts"] for d in decisions] + [t["entry_ts"] for t in trades], default=None)
        if lo:
            period_days = (I.utc_dt(until) - I.utc_dt(lo)).total_seconds() / 86400
        base_cfg = _cfg(Path(o.config).parent / "engine.base.json") if o.config else {}
        tau = o.risk if o.risk is not None else float(base_cfg.get("target_trade_risk", cfg.get("target_trade_risk", 0.005)))
        cfg_tau = float(base_cfg.get("target_trade_risk", cfg.get("target_trade_risk", 0.005)))
        risk_usd = o.risk_usd if o.risk_usd is not None else cfg_tau * float(base_cfg.get("wallet_start", cfg.get("wallet_start", 1000.0)))
        if "gates" in secs:
            cost = None if backtest else I.veto_cost_usd(o.budget, since, until) if o.budget else None
            ga = GA.build(trades, decisions, cf, mode_backtest=backtest, period_days=period_days, veto_cost=cost,
                          risk_usd=risk_usd, cf_warning=cf_warn, shadow=shadow, cf_shadow=cf_shadow)
            if o.compare_backtest:
                cdir = Path(o.compare_backtest)
                cmp_ok = False
                try:
                    cm_meta = json.loads((cdir / "meta.json").read_text(encoding="utf-8"))
                    cper = cm_meta["period"]
                    if not isinstance(cper, (list, tuple)) or len(cper) != 2:
                        raise ValueError("period")
                    guard.check_run(I.utc_dt(cper[0]), I.utc_dt(cper[1]))
                    cmp_ok = True
                except guard.BacktestArgError:
                    warnings.append("compare_holdout_locked")
                except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                    warnings.append("compare_meta_period")
            if o.compare_backtest and cmp_ok:
                bconn = I.open_ro(cdir / "ledger.sqlite", "ledger_missing")
                try:
                    I.check_ledger_schema(bconn)
                    bdec, _ = I.load_decisions(bconn, None, None)
                finally:
                    bconn.close()
                btr, _ = I.load_trades_csv(cdir / "trades.csv", None, None, {d["id"]: d for d in bdec})
                bcounts: dict = {}
                for d in bdec:
                    k = GA.gate_key(d)
                    if k:
                        bcounts[k] = bcounts.get(k, 0) + 1
                ga["compare"] = GA.compare(trades, ga["gate_counts"], btr, bcounts, period_days)
            out["gates"] = ga
        if "regimes" in secs:
            out["regimes"] = RG.build(trades, decisions, cf, has_xr)
        if "sizing" in secs:
            pairs = sorted({d["pair"] for d in decisions} | {t["pair"] for t in trades})
            rules = I.load_rules(pairs, sqlite_rules, o.history, o.synthetic_rules, o.synthetic_steps)
            taus = [tau]
            if backtest and 0.014 not in taus:
                taus.append(0.014)
            out["sizing"] = SZ.build(decisions, trades, rules, list(o.wallets), taus, backtest)
            srcs = out["sizing"]["data"]["kural_kaynagi"]
            meta["kural_kaynagi"] = ", ".join(srcs) if srcs else "yok"
    finally:
        if reader is not None:
            reader.close()

    warnings.extend(f"immutable_fallback:{x}" for x in I.FALLBACK_LOG)

    # ---- alt grup tablolari: K_rapor ve z_K
    sub = []
    for name in secs:
        for b in out[name]["blocks"]:
            if hasattr(b, "finalize"):
                sub.append(b)
    fin, k_rapor, zk = finalize_tables(sub)
    fmap = {t["id"]: t for t in fin}
    sections_blocks: dict[str, list] = {}
    for name in secs:
        final = [({"kind": "table", **fmap[b.tid]} if hasattr(b, "finalize") else b) for b in out[name]["blocks"]]
        out[name]["blocks"] = final
        if name == "regimes":
            sections_blocks["regimes"] = [b for b in final if not str(b.get("id", "")).startswith("dokum_")]
            sections_blocks["dokum"] = [b for b in final if str(b.get("id", "")).startswith("dokum_")]
        else:
            sections_blocks[name] = final
    n_engel = out["gates"]["n_engel_toplam"] if "gates" in out else None
    sumtxt = summary_line(trades, ozet, out, n_engel)
    report = {"schema": 1, "status": status, "meta": meta, "counters": counters, "k_rapor": k_rapor, "z_k": zk,
              "warnings": warnings}
    for name in SECTION_ORDER:
        if name in out:
            o_ = out[name]
            report[name] = {"tables": [b for b in o_["blocks"] if b.get("kind") == "table"]}
            for k in ("data", "veto", "gate_counts", "compare", "ozet"):
                if k in o_:
                    report[name][k] = o_[k]
            if name == "regimes":
                report[name]["years"] = o_["years"]
    files = {"rapor.md": render_md(target, meta, counters, secs, sections_blocks, out, k_rapor, zk, warnings),
             "rapor.json": to_json(report), "cikis_islemler.csv": to_csv(csv_rows), "ozet.txt": sumtxt + "\n"}
    return {"status": status, "target": target, "meta": meta, "files": files, "counters": counters, "n_trades": len(trades),
            "n_decisions": len(decisions), "k_rapor": k_rapor, "summary": sumtxt}


# --------------------------------------------------------------------------- bicim
def _clean(x):
    if isinstance(x, float):
        return None if (math.isnan(x) or math.isinf(x)) else round(x, 6)
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    return x


def to_json(obj) -> str:
    return json.dumps(_clean(obj), sort_keys=True, ensure_ascii=False, allow_nan=False, indent=1) + "\n"


def to_csv(rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLS)
    for r in rows:
        w.writerow(["" if r.get(c) is None else (repr(round(r[c], 6)) if isinstance(r.get(c), float) else r.get(c)) for c in CSV_COLS])
    return buf.getvalue()


def _cell(v) -> str:
    if v is None:
        return DASH
    if isinstance(v, bool):
        return "evet" if v else "hayır"
    if isinstance(v, float):
        return DASH if (math.isnan(v) or math.isinf(v)) else tr_sayi(v, 4)
    if isinstance(v, (list, tuple)):
        return "[" + "; ".join(_cell(x) for x in v) + "]" if all(x is not None for x in v) else DASH
    return str(v).replace("|", "\\|")


def _table_md(b: dict) -> list[str]:
    L = [f"### {b['title']}", ""]
    if b.get("k_rapor") is not None:
        zk = b.get("z_k")
        L += [f"K_tablo: {b['k_table']} · K_rapor: {b['k_rapor']} · z_K: {_cell(zk)}", ""]
    cols = b["columns"]
    L.append("| " + " | ".join(cols) + " |")
    L.append("|" + "|".join("---" for _ in cols) + "|")
    for r in b["rows"]:
        L.append("| " + " | ".join(_cell(r.get(c)) for c in cols) + " |")
    L.append("")
    for n in b.get("notes", []):
        L.append(f"*{n}*")
        L.append("")
    return L


def render_md(target, meta, counters, secs, blocks, out, k_rapor, zk, warnings) -> str:
    L = [f"# Rapor: {target}", ""] + ([] if guard.KILIT_ACIK else [W_LOCK.format(n=counters["holdout_skipped"]), ""]) + [W_WISH, ""]
    if "gates" in secs:
        L += [W_CF, ""]
    if "exits" in secs or "regimes" in secs:
        L += [W_FUT, ""]
    src = (f"Kaynak: kip {meta.get('mod')}; dönem {meta.get('donem') or DASH}; now {meta['now']}; defter sürümü "
           f"{meta.get('defter_surumu')}; kural kaynağı {meta.get('kural_kaynagi', DASH)}; mum kaynağı {meta.get('mum_kaynagi')}.")
    L += [src, "", f"K_rapor: {k_rapor} · z_K: {_cell(zk)}", ""]
    if warnings:
        L += ["Uyarı: " + ", ".join(warnings), ""]
    L += [f"Sayaçlar: bekleyen {counters['pending']}, veri boşluğu {counters['data_gap']}"
          + ("." if guard.KILIT_ACIK else f", atlanan satır {counters['holdout_skipped']}."), ""]
    for key in ("exits", "gates", "regimes", "dokum", "sizing"):
        if key not in blocks:
            continue
        L += [f"## {SECTION_TITLES[key]}", ""]
        for b in blocks[key]:
            if b.get("kind") == "text":
                L += [b["text"], ""]
            else:
                L += _table_md(b)
        if key == "exits":
            for s in out["exits"]["data"].get("okuma_cumleleri", []):
                L += [f"- {s}", ""]
        if key == "gates" and out["gates"].get("compare"):
            c = out["gates"]["compare"]
            L += ["### 2.5 Backtest karşılaştırması", "",
                  f"Yalnız backtest'te görülen çıkış nedenleri: {', '.join(c['yalniz_backtest_cikis_nedenleri']) or DASH}", ""]
            if c["durum"] == "erken":
                L += ["Kapı karşılaştırması: erken (kâğıt dönemi 28 günden kısa).", ""]
            else:
                L += [f"Yalnız backtest'te devreye giren kapılar: {', '.join(c['yalniz_backtest_kapilari']) or DASH}", ""]
        if key == "dokum":
            L += ["### 4.6 Yıl satırları", ""]
            for k, y in out["regimes"]["years"].items():
                L += [f"**{k}** · pozitif_yil_orani: {_cell(y['pozitif_yil_orani'])}", ""]
                L += _table_md({"title": f"Yıl: {k}", "columns": ["yil", "n", "G", "ort", "aralik", "toplam", "etiket", "not"], "rows": y["rows"]})[2:]
                if y.get("not"):
                    L += [f"*{y['not']}*", ""]
    return "\n".join(L).rstrip() + "\n"


def summary_line(trades, ozet, out, n_engel) -> str:
    """§10.3: duz Turkce, <= 300 karakter."""
    if not trades:
        s = "Haftalık karne: bu dönemde kapanan işlem yok."
        if n_engel is not None:
            s += f" Filtreler {n_engel} sinyali engelledi."
        return s
    p = [f"Haftalık karne: {len(trades)} işlem kapandı, ortalama {tr_isaretli(ozet['ort_net_r'], 2)}R."] if ozet else \
        [f"Haftalık karne: {len(trades)} işlem kapandı."]
    if ozet and ozet.get("n_ulasan_05"):
        p.append(f"Kâra geçip zararla kapanan: {ozet['n_geri_05']}/{ozet['n_ulasan_05']}.")
    if ozet and ozet.get("n_ok_72"):
        p.append(f"Çıkıştan sonra 1R daha giden: {ozet['erken_72']}/{ozet['n_ok_72']}.")
    tail = "Ayrıntı raporda; bu rapor ayar değiştirmez."
    red = out.get("sizing", {}).get("ozet_red") if out.get("sizing") else None
    redtxt = f"Küçük hesapta reddedilen: %{tr_sayi(red * 100, 1)}." if red is not None else ""
    bad: list[str] = []
    if n_engel is not None and "gates" in out:
        for b in out["gates"]["blocks"]:
            if b.get("id") == "kapi_karnesi":
                bad = [GA.tr_name(r["hucre"]) for r in b["rows"]
                       if str(r.get("bayrak", "")).startswith("kazanani_engelliyor")]
    def assemble(nbad):
        q = list(p)
        if n_engel is not None:
            f = f"Filtreler {n_engel} sinyali engelledi"
            if bad:
                f += "; engellenenler kazanırdı görünen: " + ", ".join(bad[:nbad]) + " (varsayım)"
            q.append(f + ".")
        if redtxt:
            q.append(redtxt)
        q.append(tail)
        return " ".join(q)
    s = assemble(len(bad))
    n = len(bad)
    while len(s) > 300 and n > 1:
        n -= 1
        s = assemble(n)
    return s
