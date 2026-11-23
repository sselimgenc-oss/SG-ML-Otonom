"""Alinmayan sinyal x sonuc raporu (`ml.alinmayan_sonuc.v1`): `var/durum/alinmayan_sonuc_v1.json`. YALNIZ BILGI: karar/emir yoluna girmez.

Satir bicimi CT `rejim_sonuc` ile AYNI: {etiket, n, kazanan, isabet_yuzde, toplam_pnl, ortalama_pnl}.
BIRIM = R (USD DEGIL): alinmayan aday icin kagit boyut/dolum yoktur; "alinsaydi" sonucu `counterfactual.sqlite` `hyp_r_net` (R, maliyet dusulmus).
`toplam_pnl`/`ortalama_pnl` alanlari bu raporda R'dir; karsilastirma satiri da R'dir (kapanan islemin `r_multiple`'i). Belirtim: docs/alinmayan-sonuc-spec.md.
Yontem `plan` (planlanan stop/hedef, 48 mum; version>=2). Sonucu olmayan aday (bekleyen, veri bosluğu, gecersiz plan) "cozulmedi" sayilir, uydurulmaz.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import counterfactual as CF

PENCERE_GUN = 7
SUTUNLAR = ("etiket", "n", "kazanan", "isabet_yuzde", "toplam_pnl", "ortalama_pnl")      # CT uyumu

SEMA = "ml.alinmayan_sonuc.v1"
DOSYA = "alinmayan_sonuc_v1.json"
BIRIM = "R"
YONTEM = "plan"
ALINAN = "alınan işlemler"
# Defterin skipped karar nedenleri (ledger._SKIP; sozluk disi deger gelirse ada gore sona eklenir)
NEDEN_SIRA = ("max_positions", "cluster_cap", "flat_bar", "arm_conflict", "arm_disabled", "session_closed", "ml_filter", "etiket_rejim", "etiket_duygu", "etiket_kalabalik", "ml_no_model",
              "risk_denied", "entry_gate_closed", "veto_blocked", "veto_missing", "veto_stale", "stop_width", "rr_below_min",
              "order_failed", "llm_invalid", "other")


def _say(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _satirlar(kv: dict[str, list[float]], sira: tuple[str, ...]) -> list[dict]:
    out = []
    for etiket in sira:
        p = kv.get(etiket)
        if not p:
            continue
        toplam, kaz = sum(p), sum(1 for x in p if x > 0)
        out.append({"etiket": etiket, "n": len(p), "kazanan": kaz, "isabet_yuzde": round(100.0 * kaz / len(p), 1),
                    "toplam_pnl": round(toplam, 2), "ortalama_pnl": round(toplam / len(p), 2)})
    return out


def yaz_atomik(yol: Path, metin: str) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(yol.parent), prefix=".as-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(metin)
        os.replace(tmp, yol)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _utc(dt: Any) -> datetime | None:
    if not isinstance(dt, datetime):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _sira(nedenler: Iterable[str]) -> tuple[str, ...]:
    s = set(nedenler)
    return tuple(n for n in NEDEN_SIRA if n in s) + tuple(sorted(s - set(NEDEN_SIRA)))


def _tablo(cf: list[Mapping], atlanan: list[Mapping], alinan: list[Mapping]) -> tuple[dict, dict]:
    """cf = sonuclu satirlar [{decision_id, skip_reason, r}]; atlanan = defterdeki skipped kararlar [{id, skip_reason}];
    alinan = [{r}]. Doner: ({"neden": satirlar + alinan satiri}, {neden: cozulmedi sayisi})."""
    kv: dict[str, list[float]] = {}
    cozulen: set = set()
    for r in cf:
        v = _say(r.get("r"))
        if v is None:
            continue
        kv.setdefault(str(r.get("skip_reason") or "bilinmiyor"), []).append(v)
        cozulen.add(r.get("decision_id"))
    coz: dict[str, int] = {}
    for d in atlanan:
        if d.get("id") not in cozulen:
            k = str(d.get("skip_reason") or "bilinmiyor")
            coz[k] = coz.get(k, 0) + 1
    satir = _satirlar(kv, _sira(kv))
    av = [x for x in (_say(a.get("r")) for a in alinan) if x is not None]
    satir += _satirlar({ALINAN: av}, (ALINAN,))
    return {"neden": satir}, {k: coz[k] for k in _sira(coz)}


def topla(cf: list[Mapping], atlanan: list[Mapping], alinan: list[Mapping], simdi: datetime, gun: int = PENCERE_GUN) -> dict:
    """Saf. cf: [{decision_id, skip_reason, ts(karar zamani), r}]; atlanan: [{id, skip_reason, ts}]; alinan: [{ts(kapanis), r}].
    Son `gun` gun (`tablolar`) ve tum zamanlar. Kilitli donemde (CF.HOLDOUT_*) karar cozulmedi sayilmaz (motor onlari hic okumaz)."""
    alt = simdi - timedelta(days=gun)

    def pen(rows, tum):
        out = []
        for r in rows:
            t = _utc(r.get("ts"))
            if t is not None and (tum or alt <= t <= simdi):
                out.append(r)
        return out

    def kilit(d):
        t = _utc(d.get("ts"))
        return (not CF.KILIT_ACIK) and t is not None and CF.HOLDOUT_START <= t < CF.HOLDOUT_END

    atl = [d for d in atlanan if not kilit(d)]
    res = {}
    for ad, tum in (("tablolar", False), ("tum_zamanlar", True)):
        tb, coz = _tablo(pen(cf, tum), pen(atl, tum), pen(alinan, tum))
        res[ad], res[ad + "_cozulmedi"] = tb, coz
    return res


def olustur(cf: list[Mapping], atlanan: list[Mapping], alinan: list[Mapping], simdi: datetime) -> dict:
    t = topla(cf, atlanan, alinan, simdi)
    n7 = sum(r["n"] for r in t["tablolar"]["neden"] if r["etiket"] != ALINAN)
    nt = sum(r["n"] for r in t["tum_zamanlar"]["neden"] if r["etiket"] != ALINAN)
    c7, ct = sum(t["tablolar_cozulmedi"].values()), sum(t["tum_zamanlar_cozulmedi"].values())
    notlar = ["Yalnız bilgi: karar/limit/eşik/kol ayarı değiştirmez.",
              "BİRİM R (USD değil): alınmayan aday için boyut/dolum yok; 'alınsaydı' sonucu net R (maliyet düşülmüş, plan yöntemi: planlanan stop/hedef, 48 mum). "
              "Toplam/Ort. PnL sütunları bu raporda R'dir; 'alınan işlemler' satırı da R (kapanan işlemin r_multiple'ı).",
              f"Çözülen alınmayan aday: son {PENCERE_GUN} gün {n7}, tüm zamanlar {nt}; çözülmedi (bekleyen/veri boşluğu/geçersiz plan): {c7} / {ct}.",
              "Üst sınır: sonraki kapıları ve dolumu yok sayar, giriş = planlanan fiyat; işlem yapılabilir kâr değildir."]
    return {"sema": SEMA, "uretim": simdi.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "birim": BIRIM,
            "pencere_gun": PENCERE_GUN, "tablolar": t["tablolar"], "tum_zamanlar": t["tum_zamanlar"],
            "cozulmedi": {"tablolar": t["tablolar_cozulmedi"], "tum_zamanlar": t["tum_zamanlar_cozulmedi"]}, "not": " ".join(notlar)}


def _cf_satirlari(cf_yol: Path, bot: str) -> list[dict]:
    """Hesaplanmis (hyp_r_net dolu) plan satirlari; depo yok/okunamazsa []."""
    if not Path(cf_yol).exists():
        return []
    try:
        with CF.CounterfactualStore(cf_yol, read_only=True) as st:
            rows = st._db.execute("SELECT decision_id, skip_reason, decision_ts, hyp_r_net FROM cf_outcomes WHERE bot=? AND method=? "
                                  "AND version>=2 AND hyp_r_net IS NOT NULL", (bot, YONTEM)).fetchall()
    except (CF.CounterfactualError, sqlite3.Error):
        return []
    out = []
    for r in rows:
        try:
            ts = datetime.fromisoformat(str(r["decision_ts"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        out.append({"decision_id": r["decision_id"], "skip_reason": r["skip_reason"], "ts": ts, "r": r["hyp_r_net"]})
    return out


def girdi_oku(ledger: Any, cf_yol: Path, bot: str) -> tuple[list[dict], list[dict], list[dict]]:
    """(cf, atlanan, alinan). Defter None/okunamazsa atlanan/alinan bos (yalniz cf kirilimi)."""
    cf = _cf_satirlari(Path(cf_yol), bot)
    atlanan: list[dict] = []
    alinan: list[dict] = []
    if ledger is not None:
        try:
            atlanan = [{"id": d.id, "skip_reason": d.skip_reason, "ts": d.bar_close_ts}
                       for d in ledger.list_decisions(final_action="skipped")]
            alinan = [{"ts": t.exit_ts, "r": t.r_multiple} for t in ledger.list_closed_trades(limit=ledger.LIST_CLOSED_MAX)]
        except Exception:  # noqa: BLE001
            atlanan, alinan = [], []
    return cf, atlanan, alinan


def yaz(ledger: Any, cf_yol: Path, bot: str, simdi: datetime, yol: Path) -> dict:
    cf, atl, aln = girdi_oku(ledger, cf_yol, bot)
    veri = olustur(cf, atl, aln, simdi)
    yaz_atomik(yol, json.dumps(veri, ensure_ascii=False, indent=1) + "\n")
    return veri


def yaz_defterden(ledger_yol: Path, cf_yol: Path, bot: str, simdi: datetime, yol: Path) -> dict | None:
    """Defteri salt okunur acip yazar (gece isi). Her hata yutulur: None doner (rapor bilgi amacli; isi bozmaz)."""
    try:
        from . import ledger as L
        led = None
        try:
            if Path(ledger_yol).exists():
                led = L.open_ledger(str(ledger_yol), bot, create=False, read_only=True, migrate=False)
        except Exception:  # noqa: BLE001 - defter okunamadi: yalniz cf kirilimi
            led = None
        try:
            return yaz(led, Path(cf_yol), bot, simdi, Path(yol))
        finally:
            if led is not None:
                led.close()
    except Exception:  # noqa: BLE001
        return None
