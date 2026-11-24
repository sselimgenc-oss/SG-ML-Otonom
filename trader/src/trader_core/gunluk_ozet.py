"""ML gunluk ozet yayini (`ortak.gunluk_ozet.v1`; belirtim: docs/standart/gunluk-ozet-v1-spec.md).

Yalniz KAGIT botun ozetini raporlar; motor/kapi/risk davranisi degismez. Kaynaklar salt okunur acilir; mevcut okuyucular
yeniden kullanilir (panel_data, counterfactual, ledger, rejim_yayini, drift/health dosyalari).

- `uret(girdi, now)`: SAF (ag yok, dosya yok); bilinmeyen alan `None`, hicbir alan atlanmaz.
- `girdi_oku(config_dir, env, environ, now)`: gercek kaynaklari okur; her kaynak bagimsiz, okunamayan -> None.
- CLI: `python -m trader_core.gunluk_ozet --config-dir config --env paper --out <yol>` (atomik; hata -> cikis 1, dosya yok).

Katman: trader_core; trader_engine ice aktarilmaz. Sir/anahtar okunmaz ve yazilmaz.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SEMA = "ortak.gunluk_ozet.v1"
PROJE = "ML"
MOD = "kagit"
BOT = "learner"
TR = timezone(timedelta(hours=3))          # Europe/Istanbul: sabit UTC+3 (DST yok), panel_data.TR ile ayni
UTC = timezone.utc
SANAL_BASLANGIC = 1000.0                   # counterfactual.arm_virtual_bankroll varsayilani
DRIFT_MAX_YAS_S = 36 * 3600
NOT_MAX = 5
REJIM_CIFTI = "BTC/USDT"


@dataclass
class Girdi:
    """`uret` girdisi. None = kaynak okunamadi/yok (alan null olur)."""
    wallet_start: float | None = None
    kapanan: Sequence[Any] | None = None        # TradeRecord benzeri: exit_ts, realized_pnl, setup
    acik: Sequence[Any] | None = None           # acik islemler: entry_ts
    adaylar: Sequence[Mapping] | None = None    # counterfactual.arm_candidates ciktisi (arm_id, taken, ts, r)
    kurulumlar: Sequence[str] = ()              # yapilandirilmis kurulum kimlikleri (arm_id)
    alinmayan_sinyal: int | None = None         # gunluk sayi (zaten gun icin hesaplanmis)
    aktivasyonlar: Sequence[Any] | None = None  # ActivationEvent benzeri: kind, actor, activated_at
    rejim: str | None = None
    drift_uyari: bool | None = None
    gunluk_kayip_yuzde: float | None = None
    kaldirac_tavan: float | None = None
    durdu_mu: bool | None = None
    son_nabiz: str | None = None
    hata_sayisi_gun: int | None = None
    notlar: list[str] = field(default_factory=list)


# ----------------------------------------------------------------- saf yardimcilar
def _r2(x: Any) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, 2) if math.isfinite(v) else None


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def gun_sinirlari(now: datetime) -> tuple[str, datetime, datetime]:
    """(Istanbul yerel tarihi, gun basi UTC, gun sonu UTC). Sinir 21:00Z."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now UTC farkindalikli olmali")
    gun = now.astimezone(TR).strftime("%Y-%m-%d")
    a = datetime.fromisoformat(gun).replace(tzinfo=TR)
    return gun, a.astimezone(UTC), (a + timedelta(days=1)).astimezone(UTC)


def _icinde(ts: Any, a: datetime, b: datetime) -> bool:
    return isinstance(ts, datetime) and a <= ts.astimezone(UTC) < b


def _pnl(t: Any) -> float:
    v = getattr(t, "realized_pnl", None)
    return float(v) if v is not None else 0.0


def dusus_yuzde(start: float, kapanan: Sequence[Any]) -> float:
    """Kapanmis islemlerin (cikis zamanina gore) kumulatif ozkaynak egrisinde zirveden cukura en buyuk dusus (%, pozitif)."""
    eq = peak = float(start)
    worst = 0.0
    for t in sorted((x for x in kapanan if getattr(x, "exit_ts", None) is not None), key=lambda x: x.exit_ts):
        eq += _pnl(t)
        peak = max(peak, eq)
        if peak > 0:
            worst = max(worst, (peak - eq) / peak * 100.0)
    return worst


def _hesaplar(adaylar: Sequence[Mapping], kurulumlar: Sequence[str], gun_basi: datetime) -> list[dict]:
    """Kurulum (setup) basina SANAL kasa: counterfactual.arm_virtual_bankroll `taken` serisi (start=1000, risk=%1).
    Kurulum = arm_id'nin '@' oncesi. gun_pnl = toplam - gun basindaki kasa; islem = sonucu olan alinan aday sayisi."""
    from trader_core import counterfactual as CF

    def setup_of(arm: str) -> str:
        return str(arm).split("@", 1)[0]

    cs = [{**c, "arm_id": setup_of(c["arm_id"])} for c in adaylar]
    setups = list(dict.fromkeys([*(setup_of(a) for a in kurulumlar), *(c["arm_id"] for c in cs)]))
    tum = CF.arm_virtual_bankroll(cs, arms=setups)
    once = CF.arm_virtual_bankroll([c for c in cs if c["ts"] < gun_basi], arms=setups)
    out = []
    for ad, v in tum.items():
        eq, eq0 = v["taken"]["equity"], once[ad]["taken"]["equity"]
        out.append({"ad": ad, "gun_pnl": _r2(eq - eq0), "toplam_pnl": _r2(eq - SANAL_BASLANGIC),
                    "islem": v["taken"]["n"]})
    out.sort(key=lambda h: (-(h["toplam_pnl"] or 0.0), h["ad"]))
    return out


def uret(g: Girdi, now: datetime) -> dict[str, Any]:
    """Ozet belgesi (saf). Her sema alani yazilir; bilinmeyen None."""
    gun, a, b = gun_sinirlari(now)
    notlar = list(g.notlar)

    toplam = gun_pnl = simdi = dd = None
    kazanan = kaybeden = gun_kapanan = None
    if g.kapanan is not None:
        toplam = math.fsum(_pnl(t) for t in g.kapanan)
        bugun = [t for t in g.kapanan if _icinde(getattr(t, "exit_ts", None), a, b)]
        gun_pnl = math.fsum(_pnl(t) for t in bugun)
        gun_kapanan = len(bugun)
        kazanan = sum(1 for t in bugun if _pnl(t) > 0)
        kaybeden = gun_kapanan - kazanan
        if g.wallet_start is not None:
            simdi = g.wallet_start + toplam
            dd = dusus_yuzde(g.wallet_start, g.kapanan)
    gun_acilan = None
    if g.kapanan is not None and g.acik is not None:
        gun_acilan = sum(1 for t in [*g.kapanan, *g.acik] if _icinde(getattr(t, "entry_ts", None), a, b))

    hesaplar = None
    if g.adaylar is not None:
        hesaplar = _hesaplar(g.adaylar, g.kurulumlar, a)
        iyi = [h for h in hesaplar if h["islem"] > 0 and (h["toplam_pnl"] or 0) > 0]
        if iyi:
            notlar.append(f"en iyi kurulum: {iyi[0]['ad']}")

    aktif = yeni = emekli = None
    if g.aktivasyonlar is not None:
        les = [x for x in g.aktivasyonlar if getattr(x, "actor", None) == "lesson"]
        ap = [x for x in les if x.kind == "apply"]
        rb = [x for x in les if x.kind == "rollback"]
        aktif = max(0, len(ap) - len(rb))
        yeni = sum(1 for x in ap if _icinde(x.activated_at, a, b))
        emekli = sum(1 for x in rb if _icinde(x.activated_at, a, b))

    doc = {
        "sema": SEMA,
        "proje": PROJE,
        "mod": MOD,
        "uretim": _iso_z(now),
        "gun": gun,
        "kasa": {
            "baslangic": _r2(g.wallet_start),
            "simdi": _r2(simdi),
            "gun_pnl": _r2(gun_pnl),
            "toplam_pnl": _r2(toplam),
            "zirveden_dusus_yuzde": _r2(dd),
        },
        "islem": {
            "gun_acilan": gun_acilan,
            "gun_kapanan": gun_kapanan,
            "kazanan": kazanan,
            "kaybeden": kaybeden,
            "acik_pozisyon": None if g.acik is None else len(g.acik),
            "alinmayan_sinyal": g.alinmayan_sinyal,
        },
        "hesaplar": hesaplar,
        "ogrenme": {"aktif_ders": aktif, "yeni_ders": yeni, "emekli_ders": emekli,
                     "filtre_aktif": None},   # v1 sema anahtari korunur: ML filtreleri 24.11'de silindi (kaynak yok => hep null)
        "rejim": g.rejim,
        "drift_uyari": g.drift_uyari,
        "limitler": {"gunluk_kayip_yuzde": _r2(g.gunluk_kayip_yuzde), "kaldirac_tavan": _r2(g.kaldirac_tavan),
                     "durdu_mu": g.durdu_mu},
        "saglik": {"son_nabiz": g.son_nabiz, "hata_sayisi_gun": g.hata_sayisi_gun},
        "notlar": [str(n)[:80] for n in notlar[:NOT_MAX]],
    }
    return doc


# ----------------------------------------------------------------- kaynak okuma (salt okunur)
def _json(p: Path) -> dict:
    d = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(d, dict):
        raise ValueError("JSON nesnesi bekleniyor")
    return d


def _kok(config_dir: Path, environ: Mapping[str, str]) -> Path:
    """TRADER_DATA_ROOT mutlaksa veri koku (scripts/health_run.data_root ile ayni kural); degilse config kokunun ustu."""
    v = (environ.get("TRADER_DATA_ROOT") or "").strip()
    if v and os.path.isabs(v):
        return Path(v)
    return config_dir.parent if config_dir.name == "config" else config_dir


def _yol(kok: Path, v: Any, varsayilan: str) -> Path:
    p = Path(v if isinstance(v, str) and v else varsayilan)
    return p if p.is_absolute() else kok / p


def _motor_yapilandirma(config_dir: Path, env: str) -> dict:
    from trader_core.config_loader import deep_merge
    cfg: dict = {}
    if not (config_dir / "engine.base.json").exists():
        raise FileNotFoundError(f"engine.base.json yok: {config_dir}")
    for ad in ("engine.base.json", f"engine.{BOT}.json", f"engine.{env}.json"):
        p = config_dir / ad
        if p.exists():
            cfg = deep_merge(cfg, _json(p))
    return cfg


def _limitler(cfg: Mapping) -> tuple[float | None, float | None]:
    """Paper risk yapilandirmasi (trader_engine.config.build_paper_risk_config ile ayni kural; ice aktarmadan)."""
    from trader_core import risk as R
    try:
        blok = cfg.get("risk")
        if isinstance(blok, Mapping) and blok:
            kw = {k: float(v) for k, v in blok.items() if k in R.PAPER_KEYS}
            if cfg.get("target_trade_risk") is not None:
                kw["target_trade_risk"] = float(cfg["target_trade_risk"])
            rc = R.paper_config(**kw)
        else:
            rc = R.LOCKED_CFG
        return rc.daily_max_loss * 100.0, float(rc.max_leverage)
    except (ValueError, TypeError):
        return None, None


def _rejim(cfg: Mapping, config_dir: Path, kok: Path, now: datetime) -> str | None:
    from trader_core import rejim_yayini as RY
    try:
        db = _yol(kok, cfg.get("market_db"), "var/market.sqlite")
        store = RY.MarketReader(db)
        try:
            doc = RY.uret(store, [REJIM_CIFTI], {}, now)
        finally:
            store.close()
        v = doc["varliklar"][REJIM_CIFTI]["4h"]
        return v["rejim"] if v.get("bar_ts") else None
    except Exception:  # noqa: BLE001
        return None


def _drift(yol: Path, now: datetime) -> bool | None:
    try:
        d = _json(yol)
        if d.get("schema") != "drift/1":
            return None
        gen = datetime.fromisoformat(str(d["generated_at"]).replace("Z", "+00:00"))
        if gen.tzinfo is None or (now - gen).total_seconds() > DRIFT_MAX_YAS_S:
            return None
        rules = d.get("rules") if isinstance(d.get("rules"), Mapping) else {}
        seviyeler = [d.get("overall")] + [r.get("level") for r in rules.values() if isinstance(r, Mapping)]
        return "UYARI" in seviyeler
    except Exception:  # noqa: BLE001
        return None


def _saglik(yol: Path, now: datetime) -> tuple[str | None, int | None]:
    try:
        st = _json(yol)
    except Exception:  # noqa: BLE001
        return None, None
    lr = st.get("last_run_at")
    nabiz = None
    if isinstance(lr, str):
        try:
            d = datetime.fromisoformat(lr.replace("Z", "+00:00"))
            nabiz = _iso_z(d if d.tzinfo else d.replace(tzinfo=UTC))
        except ValueError:
            nabiz = None
    fps = st.get("fingerprints")
    sayi = None
    if isinstance(fps, Mapping):
        sayi = sum(1 for v in fps.values() if isinstance(v, Mapping) and v.get("level") in ("WARN", "CRIT"))
    return nabiz, sayi


def _durdu(durum_yol: Path, kill_yol: Path | None, now: datetime) -> bool | None:
    from trader_core import panel_data as P
    try:
        if kill_yol is not None and kill_yol.exists():
            return True
    except OSError:
        pass
    s = P.read_status(str(durum_yol), now, P.STALE_S)
    if s["state"] != "live":
        return None
    d = s["data"] or {}
    return bool(d.get("kill") or d.get("entries_open") is False or d.get("entries_blocked_reason"))


def _cf_gunluk(cf_yol: Path, a: datetime, b: datetime) -> int | None:
    from trader_core import counterfactual as CF
    if not cf_yol.exists():
        return None
    try:
        with CF.CounterfactualStore(cf_yol, read_only=True) as st:
            r = st._db.execute("SELECT COUNT(DISTINCT decision_id) FROM cf_outcomes WHERE bot=? AND decision_ts>=? AND decision_ts<?",
                               (BOT, CF._fmt(a), CF._fmt(b))).fetchone()
        return int(r[0])
    except Exception:  # noqa: BLE001
        return None


def girdi_oku(config_dir: str | os.PathLike, env: str, environ: Mapping[str, str], now: datetime) -> Girdi:
    from trader_core import counterfactual as CF
    from trader_core import panel_data as P
    cdir = Path(config_dir)
    kok = _kok(cdir, environ)
    cfg = _motor_yapilandirma(cdir, env)          # okunamazsa istisna: CLI hata verir (yapilandirma zorunlu)
    try:
        panel = _json(cdir / "panel.json")
    except (OSError, ValueError):
        panel = {}
    ledger_yol = _yol(kok, panel.get("ledger_path"), "var/learner/ledger.sqlite")
    ldir = ledger_yol.parent
    _, a, b = gun_sinirlari(now)
    g = Girdi(notlar=[])
    ws = cfg.get("wallet_start")
    g.wallet_start = float(ws) if isinstance(ws, (int, float)) and not isinstance(ws, bool) else None
    g.gunluk_kayip_yuzde, g.kaldirac_tavan = _limitler(cfg)
    arms = cfg.get("arms") or []
    g.kurulumlar = [str(x) for x in (arms if isinstance(arms, list) else [])]

    try:
        led = P.open_ledger_ro(str(ledger_yol), BOT)
        try:
            g.kapanan = led.list_closed_trades(limit=P.CLOSED_MAX)
            g.acik = led.list_open_trades()
            g.aktivasyonlar = led.list_activations()
            decisions = led.list_decisions()
        finally:
            led.close()
        cf_yol = ldir / "counterfactual.sqlite"
        try:
            rows = CF.arm_rows(cf_yol, BOT) if cf_yol.exists() else []
        except CF.CounterfactualError:
            rows = []
        g.adaylar = CF.arm_candidates(decisions=decisions, trades=g.kapanan, cf_rows=rows,
                                      asset_class_of=lambda _p: "kripto")
    except Exception:  # noqa: BLE001 - defter okunamadi: ilgili alanlar null
        g.notlar.append("defter okunamadi")
    g.alinmayan_sinyal = _cf_gunluk(ldir / "counterfactual.sqlite", a, b)
    g.rejim = _rejim(cfg, cdir, kok, now)
    if g.rejim is None:
        g.notlar.append("rejim verisi yok")
    g.drift_uyari = _drift(ldir / "drift.json", now)
    sag = _yol(kok, panel.get("health_state"), "/var/lib/trader-health/state.json")
    g.son_nabiz, g.hata_sayisi_gun = _saglik(sag, now)
    if g.son_nabiz is None:
        g.notlar.append("saglik durumu okunamadi")
    kill = panel.get("kill_file")
    g.durdu_mu = _durdu(_yol(kok, panel.get("status_path"), "var/learner/status.json"),
                        _yol(kok, kill, "shared/KILL") if kill else None, now)
    return g


# ----------------------------------------------------------------- atomik yazma
def atomik_yaz(path: str | os.PathLike, doc: Mapping[str, Any]) -> None:
    from trader_core.rejim_yayini import atomik_yaz as _yaz
    _yaz(path, doc)


# ----------------------------------------------------------------- CLI
def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None,
         now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m trader_core.gunluk_ozet",
                                 description="ML gunluk ozetini (ortak.gunluk_ozet.v1) salt-okunur JSON olarak yayinlar.")
    ap.add_argument("--config-dir", default="config")
    ap.add_argument("--env", default="paper")
    ap.add_argument("--out", required=True, help="cikti JSON yolu (atomik yazilir)")
    args = ap.parse_args(argv)
    try:
        t = now or datetime.now(UTC)
        g = girdi_oku(args.config_dir, args.env, os.environ if environ is None else environ, t)
        doc = uret(g, t)
        atomik_yaz(args.out, doc)
    except Exception as e:  # noqa: BLE001 - her hata sifir olmayan cikis, dosya yazilmaz
        print(f"HATA: gunluk ozet uretilemedi: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(f"gunluk ozet yazildi: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
