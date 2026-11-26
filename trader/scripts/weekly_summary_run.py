#!/usr/bin/env python3
"""Haftalik ozet (DD-12 WP-09, spec eki 18 Kas 2026): haftanin kapanan islemlerini sade Turkce ozetler (sahibin okumasi icin).

Haftalik dosya SABIT BOLUM (LLM'siz: tutarlilik, cikis kaniti, PBO, alinmayan sinyal) + istege bagli "Yorum"
paragrafindan olusur; sabit bolum anahtar olsun olmasin her hafta yazilir (Telegram haftalik ozeti ve panel okur).
Tek LLM kullanimi yorumdur ve 24 Kas 2026'dan beri MESSAGE BATCHES API ile yapilir (`trader_core.haftalik_batch`, `ortak.AnthropicBatchClient`):
1. GONDER (pazar 18:10 UTC): sabit bolum dosyasi hemen yazilir; yorum icin batch gonderilir, batch kimligi + butce rezervi
   `<defter dizini>/weekly_summaries/YYYY-Www.batch.json` dosyasina yazilir (ayni hafta ikinci gonderim yok); kisa sure (`--wait-s`) beklenir.
2. TOPLA (`--collect`, `trader-weekly-collect.timer`, 3 saatte bir; her normal kosu da once bekleyenleri toplar): batch bitince
   "## Yorum" dosyaya eklenir + Telegram mesaji; butce `record(batch=True)`. Batch basarisiz/suresi dolmus/36 saatte bitmemisse rezerv
   serbest birakilir, Telegram'a "yorum atlandi" notu gider (sabit bolum yine vardir).
Butce payi `haftalik_ozet` (aylik tavan 20 $; pay bitince DURUR, motor etkilenmez): `budget.authorize` (batch fiyatli tahmin) -> gonderim -> `budget.record(..., True)`.
API anahtari (budget.api_key_env("haftalik_ozet")) yoksa yorum atlanir (sabit bolum yine yazilir).
Cikti: `<defter dizini>/weekly_summaries/YYYY-Www.md` (hafta basina bir kez). Test: `main(argv, client=, budget=, now_fn=, env=, sleep=)`;
`client.submit(bundle, custom_id)` / `client.poll(batch_id)` / `client.cancel(batch_id)`.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import budget as _budget  # noqa: E402
from trader_core import haftalik_batch as HB  # noqa: E402
from trader_core import ledger as L  # noqa: E402
from trader_core import ortak as ORT  # noqa: E402

log = logging.getLogger("trader.weekly.run")
SERVICE = "haftalik_ozet"
MODEL = "claude-haiku-5-5"
MAX_OUT = 700
MAX_ISLEM = 60
SYSTEM = ("Sen bir kagit-islem botunun haftalik ozetini yazan yardimcisin. Yalnizca verilen sayilara ve islem satirlarina dayan; "
          "uydurma. Sade Turkce, kisa paragraflar, teknik terimleri acikla. Para tavsiyesi verme; gercek paraya "
          "gecis hakkinda yorum yapma. Sonda en fazla uc maddelik 'dikkat edilecekler' ver.")


def _resolve(p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else _HERE.parent / q)


def week_key(day: datetime) -> str:
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def _data_root(env) -> Path:
    v = (env.get("TRADER_DATA_ROOT") or "").strip()
    return Path(v) if v and os.path.isabs(v) else _HERE.parent


def _tr_pct(x: float) -> str:
    return f"%{round(x * 100):d}"


def tutarlilik_satiri(env, now: datetime, durum_path=None) -> str:
    """Faz 2a: var/durum/tutarlilik_v1.json'dan tek satir. Dosya yok/bozuk ya da 8 gunden eski -> `Tutarlılık: rapor yok`."""
    p = Path(durum_path) if durum_path else _data_root(env) / "var" / "durum" / "tutarlilik_v1.json"
    yok = "Tutarlılık: rapor yok"
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        uret = datetime.strptime(doc["uretim"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (OSError, ValueError, KeyError, TypeError):
        return yok
    if not isinstance(doc, dict) or (now - uret) > timedelta(days=8):
        return yok
    ks = doc.get("kurulumlar") or []
    nt = doc.get("not")
    if not ks:
        return f"Tutarlılık: {nt}" if nt else yok
    e = sum(int(k.get("eslesen") or 0) for k in ks)
    yk = sum(int(k.get("yalniz_kagit") or 0) for k in ks)
    yb = sum(int(k.get("yalniz_bt") or 0) for k in ks)
    dr = sum(float(k.get("kagit_R") or 0.0) - float(k.get("bt_R") or 0.0) for k in ks)
    oran = _tr_pct(e / (e + yk + yb)) if (e + yk + yb) else "yok"
    uy = "uyarı: tutarlilik_sapma" if doc.get("uyari") else "uyarı yok"
    return f"Tutarlılık: eşleşme {oran}, ΣR farkı {dr:+.1f}R; {uy}".replace(".", ",")


def build_input(ledger, since: str, until: str) -> tuple[dict, str]:
    """Haftanin kapanan islemleri (defterden; kod hesaplar, model yalniz yorumlar). Not tablosu kullanilmaz."""
    tr = [t for t in ledger.list_closed_trades(limit=ledger.LIST_CLOSED_MAX)
          if getattr(t, "exit_ts", None) is not None and since <= t.exit_ts.date().isoformat() <= until]
    nedenler = Counter(str(t.exit_reason) for t in tr)
    rs = [t.r_multiple for t in tr if t.r_multiple is not None]
    stats = {"hafta_baslangic": since, "hafta_bitis": until, "islem_sayisi": len(tr),
             "toplam_R": round(sum(rs), 3), "ortalama_R": round(sum(rs) / len(rs), 3) if rs else None,
             "cikis_nedenleri": dict(sorted(nedenler.items()))}
    lines = [f"- {t.setup} {t.pair} {t.side}: cikis {t.exit_reason}, R={'?' if t.r_multiple is None else round(t.r_multiple, 2)}"
             for t in tr[-MAX_ISLEM:]]
    return stats, "Sayilar:\n" + json.dumps(stats, ensure_ascii=False, sort_keys=True) + "\n\nIslemler:\n" + "\n".join(lines)


SABIT_BASLIK = "## Sabit bölüm"
YORUM_BASLIK = "## Yorum"


def _fmt_r(x) -> str:
    """R bicimi (+4,50R): alinmayan sonuc tablosunun toplam_pnl alani R'dir, dolar degil."""
    return f"{float(x):+.2f}R".replace(".", ",")


def cikis_kaniti_satiri(env, lp: str, now: datetime) -> str:
    """Cikis karsi-olgusu (`panel_data.exitcf_view` ile ayni kaynak): kurulum basina en buyuk olumlu fark.
    Kaynak yok/bos -> 'Çıkış kanıtı: henüz veri yok'."""
    yok = "Çıkış kanıtı: henüz veri yok"
    try:
        from trader_core import panel_data as P  # noqa: PLC0415
        v = P.exitcf_view(str(Path(lp).with_name("exit_counterfactual.sqlite")), now)
        if not v.get("var"):
            return yok
        best = None
        for k in v.get("kurulumlar") or []:
            for ad, alan in (("trail yukarı", "trail_yukari"), ("trail aşağı", "trail_asagi"), ("başabaş", "basabas"), ("kısmi", "kismi")):
                d = (k.get(alan) or {}).get("delta_r")
                if d is not None and d > 0 and (best is None or d > best[0]):
                    best = (d, k["kurulum"], ad, (k.get(alan) or {}).get("n", 0))
        if best is None:
            return "Çıkış kanıtı: olumlu fark yok"
        return f"Çıkış kanıtı: en büyük olumlu fark {best[1]} {best[2]} {best[0]:+.2f}R (n={best[3]})".replace(".", ",")
    except Exception:  # noqa: BLE001
        return yok


def pbo_satiri(env) -> str | None:
    """`research/holdout/pbo_ozet.json` (yalniz gelistirme makinesinde): yoksa/bozuksa None (satir atlanir, sessiz)."""
    try:
        d = json.loads((_data_root(env) / "research" / "holdout" / "pbo_ozet.json").read_text(encoding="utf-8"))
        parts = [f"{a['aile']} %{round(a['pbo'] * 100):d}" for a in d.get("aileler", [])[:4]
                 if isinstance(a, dict) and isinstance(a.get("pbo"), (int, float)) and a.get("aile")]
        return ("PBO: " + ", ".join(parts)) if parts else None
    except Exception:  # noqa: BLE001
        return None


def alinmayan_satiri(env, durum_path=None) -> str:
    """`var/durum/alinmayan_sonuc_v1.json` (`ml.alinmayan_sonuc.v1`; son 7 gun `tablolar.neden`): en iyi/en kotu neden. Yok -> henuz veri yok."""
    yok = "Alınmayan sinyal: henüz veri yok"
    try:
        p = Path(durum_path) if durum_path else _data_root(env) / "var" / "durum" / "alinmayan_sonuc_v1.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(d, dict) or d.get("sema") != "ml.alinmayan_sonuc.v1":
            return yok
        rows = [r for r in (d["tablolar"].get("neden") or []) if int(r["n"]) >= 1]
        if not rows:
            return yok
        iyi, kotu = max(rows, key=lambda r: r["toplam_pnl"]), min(rows, key=lambda r: r["toplam_pnl"])
        f = lambda r: f"{r['etiket']} {_fmt_r(r['toplam_pnl'])} (n={r['n']})"  # noqa: E731
        return f"Alınmayan sinyal (7g): {sum(int(r['n']) for r in rows)} sinyal; en iyi {f(iyi)}, en kötü {f(kotu)}"
    except Exception:  # noqa: BLE001
        return yok


def arm_conflict_satiri(env, durum_path=None) -> str | None:
    """Kurulum x zaman dilimi basina `arm_conflict` kayiplari ve "alinsaydi" net R (son 7 gun). Veri yoksa None (satir yazilmaz)."""
    try:
        p = Path(durum_path) if durum_path else _data_root(env) / "var" / "durum" / "alinmayan_sonuc_v1.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(d, dict) or d.get("sema") != "ml.alinmayan_sonuc.v1":
            return None
        rows = [r for r in ((d.get("arm_conflict") or {}).get("tablolar") or []) if int(r["kayip"]) >= 1]
        if not rows:
            return None
        rows.sort(key=lambda r: -int(r["kayip"]))
        f = lambda r: f"{r['etiket']} {r['kayip']} kayıp, alınsaydı {float(r['toplam_pnl']):+.2f}R (n={r['n']})"  # noqa: E731
        return "Kol çatışması kayıpları (7g): " + "; ".join(f(r) for r in rows[:5])
    except Exception:  # noqa: BLE001
        return None


def sabit_bolum(env, lp: str, now: datetime) -> list[str]:
    """Haftalik sabit satirlar (LLM'siz). Her satir kendi icinde hata yutar; ozeti asla engellemez."""
    def guard(fn, yok):
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return yok
    out = [guard(lambda: tutarlilik_satiri(env, now), "Tutarlılık: rapor yok"),
           guard(lambda: cikis_kaniti_satiri(env, lp, now), "Çıkış kanıtı: henüz veri yok")]
    pbo = guard(lambda: pbo_satiri(env), None)
    if pbo:
        out.append(pbo)
    out.append(guard(lambda: alinmayan_satiri(env), "Alınmayan sinyal: henüz veri yok"))
    ac = guard(lambda: arm_conflict_satiri(env), None)
    if ac:
        out.append(ac)
    return out


def _istem(led_path: str, day: datetime) -> tuple[dict | None, int, str]:
    """(batch parametreleri | None, tahmini girdi tokeni, durum): yorum girdisi defterden kurulur."""
    try:
        led = L.open_ledger(led_path, "learner", create=False, read_only=True, migrate=False)
    except Exception as e:  # noqa: BLE001
        log.warning("defter acilamadi: %s", ORT.scrub(e))
        return None, 0, "no_ledger"
    try:
        stats, user = build_input(led, (day - timedelta(days=6)).date().isoformat(), day.date().isoformat())
    except Exception as e:  # noqa: BLE001
        log.warning("yorum girdisi kurulamadi: %s", ORT.scrub(e))
        return None, 0, "no_ledger"
    finally:
        close = getattr(led, "close", None)
        if close:
            close()
    if stats["islem_sayisi"] == 0:
        return None, 0, "no_notes"
    params = {"model": MODEL, "max_tokens": MAX_OUT, "system": SYSTEM,
              "messages": [{"role": "user", "content": user}]}
    return params, max(1, (len(SYSTEM) + len(user)) // 3), "ok"


def _tg_dir(env) -> Path:
    return Path((env.get("TELEGRAM_VAR_DIR") or "").strip() or _data_root(env) / "var" / "telegram")


def _state_path(out_dir: Path, hafta: str) -> Path:
    return out_dir / f"{hafta}.batch.json"


def _is_bekliyor(st: dict | None) -> bool:
    """Isleme gerekir mi: batch sonucu bekleniyor ya da sonuc mesaji Telegram'a henuz gitmedi."""
    return bool(st) and (st.get("durum") == HB.SUBMITTED or (bool(st.get("mesaj")) and not st.get("telegram")))


def _yorumu_ekle(out: Path, hafta: str, metin: str, env, lp: str, now: datetime) -> None:
    """Sabit bolumlu dosyaya '## Yorum' ekler (dosya yoksa sabit bolum yeniden uretilir)."""
    try:
        body = out.read_text(encoding="utf-8")
    except OSError:
        body = f"# Haftalik ozet {hafta}\n\n{SABIT_BASLIK}\n" + "\n".join(sabit_bolum(env, lp, now)) + "\n"
    if f"\n{YORUM_BASLIK}\n" not in body:
        body += f"\n{YORUM_BASLIK}\n{metin}\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")


def _bekleyenleri_isle(out_dir: Path, client, b, env, lp: str, now: datetime, *, bekle_s: float = 0.0,
                       sleep=time.sleep, sadece: str | None = None) -> list[dict]:
    """Dizindeki bekleyen batch durumlarini isler (sonuc: dosyaya yorum + Telegram; basarisizlik: not). [{hafta, durum}]."""
    rapor: list[dict] = []
    for sp in sorted(out_dir.glob("*.batch.json")):
        st = HB.durum_oku(sp)
        if not st or "hafta" not in st or (sadece and st["hafta"] != sadece) or not _is_bekliyor(st):
            continue
        hafta = st["hafta"]
        if st.get("durum") == HB.SUBMITTED:
            if client is None:                                  # anahtar yok: toplanamaz (rezerv acik kalir, sonraki kosu)
                rapor.append({"hafta": hafta, "durum": "pending"})
                continue
            sn = HB.topla(client, st, now, b, bekle_s=bekle_s, sleep=sleep)
            if sn.durum == "pending":
                rapor.append({"hafta": hafta, "durum": "pending"})
                continue
            if sn.durum == "ok":
                st.update(durum=HB.DONE, mesaj=f"Haftalık özet yorumu ({hafta}):\n{sn.metin}", telegram=False)
                try:
                    _yorumu_ekle(out_dir / f"{hafta}.md", hafta, sn.metin, env, lp, now)
                except OSError as e:
                    log.error("yorum dosyaya eklenemedi: %s", ORT.scrub(e))
            else:
                st.update(durum=HB.FAILED, neden=sn.neden, telegram=False,
                          mesaj=f"Haftalık özet yorumu ({hafta}) atlandı: {sn.neden}. Sabit bölüm yazıldı.")
            HB.durum_yaz(sp, st)
        ek = "" if st["durum"] == HB.DONE else "-atlandi"
        if HB.telegram_yaz(_tg_dir(env), st["mesaj"], f"haftalik-ozet{ek}:{hafta}", now):
            st["telegram"] = True
            HB.durum_yaz(sp, st)
        rapor.append({"hafta": hafta, "durum": st["durum"]})
    return rapor


def main(argv=None, *, client=None, budget=None, now_fn=None, env=None, sleep=time.sleep) -> int:
    ap = argparse.ArgumentParser(prog="weekly_summary_run.py")
    ap.add_argument("--once", action="store_true", required=True)
    ap.add_argument("--collect", action="store_true", help="yalniz bekleyen batch'leri topla (yeni gonderim/dosya yok)")
    ap.add_argument("--wait-s", type=float, default=120.0, help="gonderimden sonra batch icin en cok bu kadar sn bekle")
    ap.add_argument("--day", help="YYYY-MM-DD: bu gunun haftasi (varsayilan: bugun UTC); son 7 gun ozetlenir")
    ap.add_argument("--ledger")
    ap.add_argument("--out-dir")
    ap.add_argument("--force", action="store_true", help="bu hafta icin ozet varsa yeniden yaz (bekleyen batch varsa yalniz toplar)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    env = os.environ if env is None else env
    b = budget or _budget
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    day = datetime.strptime(args.day, "%Y-%m-%d").replace(tzinfo=timezone.utc) if args.day else now
    lp = _resolve(args.ledger or env.get("LEDGER_PATH") or "var/learner/ledger.sqlite")
    out_dir = Path(_resolve(args.out_dir) if args.out_dir else str(Path(lp).with_name("weekly_summaries")))
    hafta = week_key(day)
    out = out_dir / f"{hafta}.md"
    states = [HB.durum_oku(p) for p in sorted(out_dir.glob("*.batch.json"))] if out_dir.is_dir() else []
    if client is None and (args.collect or any(_is_bekliyor(s) for s in states) or args.force or not out.exists()):
        try:
            client = HB.varsayilan_istemci(env, b, SERVICE)
        except Exception as e:  # noqa: BLE001
            log.warning("LLM istemcisi kurulamadi: %s", ORT.scrub(e))
            client = None
    # once bekleyenleri topla (onceki haftalarin batch'i dahil); bu haftanin batch'i bekliyorsa yeni gonderim YOK
    rapor = _bekleyenleri_isle(out_dir, client, b, env, lp, now, sleep=sleep) if out_dir.is_dir() else []
    if args.collect:
        print(json.dumps({"status": "collect", "batches": rapor}, ensure_ascii=False))
        return 0
    mevcut = HB.durum_oku(_state_path(out_dir, hafta))
    if mevcut and mevcut.get("durum") == HB.SUBMITTED:
        print(json.dumps({"status": "pending", "week": hafta}))
        return 0
    if out.exists() and not args.force:
        print(json.dumps({"status": "exists", "week": hafta}))
        return 0
    satirlar = sabit_bolum(env, lp, now)               # LLM'den bagimsiz: anahtarsiz da yazilir
    yorum_durum, st = "no_api_key", None
    if client is not None:
        params, est_in, yorum_durum = _istem(lp, day)
        if params is not None:
            st, yorum_durum = HB.gonder(client, b, SERVICE, MODEL, params, est_in, MAX_OUT, f"haftalik-ozet-{hafta}", hafta, now)
            if st is not None:
                try:                                              # dosyadan ONCE: cokme olsa da ayni hafta ikinci gonderim olmaz
                    HB.durum_yaz(_state_path(out_dir, hafta), st)
                except OSError as e:
                    print(f"batch durumu yazilamadi: {ORT.scrub(e)}", file=sys.stderr)
                    return 3
    body = f"# Haftalik ozet {hafta}\n\n{SABIT_BASLIK}\n" + "\n".join(satirlar) + "\n"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
    except OSError as e:
        print(f"ozet yazilamadi: {ORT.scrub(e)}", file=sys.stderr)
        return 3
    if st is not None and args.wait_s > 0:                    # kisa sinirli bekleme; bitmediyse sonraki toplama kosusu alir
        _bekleyenleri_isle(out_dir, client, b, env, lp, now, bekle_s=args.wait_s, sleep=sleep, sadece=hafta)
    print(json.dumps({"status": "ok", "week": hafta, "file": str(out), "comment": yorum_durum}))
    return 2 if yorum_durum in ("llm_error", "empty") else 0


if __name__ == "__main__":
    sys.exit(main())
