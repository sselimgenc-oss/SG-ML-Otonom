#!/usr/bin/env python3
"""Haftalik ozet (DD-12 WP-09, spec eki 18 Kas 2026): haftanin islem notlarini sade Turkce ozetler (sahibin okumasi icin).

Haftalik dosya SABIT BOLUM (LLM'siz: tutarlilik, cikis kaniti, PBO, alinmayan sinyal) + istege bagli "Yorum"
paragrafindan olusur; sabit bolum anahtar olsun olmasin her hafta yazilir (Telegram gunluk raporu `telegram.rapor_ogrenme` onu okur).
Tek LLM kullanimi yorumdur. Butce payi `haftalik_ozet` (aylik tavan 20 $; pay bitince DURUR, motor/not/ders etkilenmez):
`budget.authorize` -> cagri -> `budget.record` (hata/sapmada `release`). API anahtari (budget.api_key_env("haftalik_ozet"))
yoksa yorum atlanir (sabit bolum yine yazilir). Mevcut yardimcilar: `lesson.AnthropicBatchClient` (hata esleme), `lesson.budget_usage`; yeni SDK yok.
Cikti: `<defter dizini>/weekly_summaries/YYYY-Www.md` (hafta basina bir kez). Test: `main(argv, llm=, budget=, now_fn=, env=)`;
`llm(params) -> (metin, usage)`.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import budget as _budget  # noqa: E402
from trader_core import ledger as L  # noqa: E402
from trader_core import lesson as LS  # noqa: E402

log = logging.getLogger("trader.weekly.run")
SERVICE = "haftalik_ozet"
MODEL = "claude-haiku-5-5"
MAX_OUT = 700
MAX_NOTES = 60
SYSTEM = ("Sen bir kagit-islem botunun haftalik ozetini yazan yardimcisin. Yalnizca verilen sayilara ve notlara dayan; "
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
    notes = [n for n in ledger.list_trade_notes() if since <= n["note_date"] <= until]
    tags = Counter(t for n in notes for t in n["tags"])
    rt = {t.trade_id: t.r_multiple for t in ledger.list_closed_trades(limit=ledger.LIST_CLOSED_MAX)}
    rs = [rt[n["trade_id"]] for n in notes if rt.get(n["trade_id"]) is not None]
    stats = {"hafta_baslangic": since, "hafta_bitis": until, "not_sayisi": len(notes),
             "toplam_R": round(sum(rs), 3), "ortalama_R": round(sum(rs) / len(rs), 3) if rs else None,
             "etiket_sayilari": dict(sorted(tags.items()))}
    lines = [f"- {n['text']}" for n in notes[-MAX_NOTES:]]
    return stats, "Sayilar:\n" + json.dumps(stats, ensure_ascii=False, sort_keys=True) + "\n\nNotlar:\n" + "\n".join(lines)


def _default_llm(env, b):
    key = env.get(b.api_key_env(SERVICE))
    if not key:
        return None
    import anthropic  # noqa: PLC0415  (mevcut SDK; yeni bagimlilik yok)
    helper = LS.AnthropicBatchClient(client=anthropic.Anthropic(api_key=key, max_retries=0, timeout=60.0))

    def call(params):
        try:
            msg = helper._client.messages.create(**params)
        except Exception as e:  # noqa: BLE001
            raise helper._map(e) from None
        text = "".join(LS._g(c, "text", "") for c in (msg.content or []) if LS._g(c, "type") == "text")
        return text, msg.usage
    return call


SABIT_BASLIK = "## Sabit bölüm"
YORUM_BASLIK = "## Yorum"


def _fmt_pnl(x) -> str:
    return f"{float(x):+.2f} $".replace(".", ",")


def cikis_kaniti_satiri(env, lp: str, now: datetime, lesson_store=None) -> str:
    """Cikis karsi-olgusu (`panel_data.exitcf_view`/`exitcf_bekleyen` ile ayni kaynak): kurulum basina en buyuk olumlu fark + bekleyen
    ders onerisi sayisi. Kaynak yok/bos -> 'Çıkış kanıtı: henüz veri yok'."""
    yok = "Çıkış kanıtı: henüz veri yok"
    try:
        from trader_core import panel_data as P  # noqa: PLC0415
        bek: list[str] = []
        try:
            bek = P.exitcf_bekleyen(P.lesson_view(str(lesson_store or ""), now, lp))
        except Exception:  # noqa: BLE001  (ders deposu yok: oneri sayisi 0)
            pass
        v = P.exitcf_view(str(Path(lp).with_name("exit_counterfactual.sqlite")), now, bek)
        if not v.get("var"):
            return yok
        best = None
        for k in v.get("kurulumlar") or []:
            for ad, alan in (("trail yukarı", "trail_yukari"), ("trail aşağı", "trail_asagi"), ("başabaş", "basabas"), ("kısmi", "kismi")):
                d = (k.get(alan) or {}).get("delta_r")
                if d is not None and d > 0 and (best is None or d > best[0]):
                    best = (d, k["kurulum"], ad, (k.get(alan) or {}).get("n", 0))
        pend = f"bekleyen ders önerisi {len(v.get('bekleyen') or [])}"
        if best is None:
            return f"Çıkış kanıtı: olumlu fark yok; {pend}"
        return f"Çıkış kanıtı: en büyük olumlu fark {best[1]} {best[2]} {best[0]:+.2f}R (n={best[3]}); {pend}".replace(".", ",")
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
        f = lambda r: f"{r['etiket']} {_fmt_pnl(r['toplam_pnl'])} (n={r['n']})"  # noqa: E731
        return f"Alınmayan sinyal (7g): {sum(int(r['n']) for r in rows)} sinyal; en iyi {f(iyi)}, en kötü {f(kotu)}"
    except Exception:  # noqa: BLE001
        return yok


def sabit_bolum(env, lp: str, now: datetime, lesson_store=None) -> list[str]:
    """Haftalik sabit satirlar (LLM'siz). Her satir kendi icinde hata yutar; ozeti asla engellemez."""
    def guard(fn, yok):
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return yok
    out = [guard(lambda: tutarlilik_satiri(env, now), "Tutarlılık: rapor yok"),
           guard(lambda: cikis_kaniti_satiri(env, lp, now, lesson_store), "Çıkış kanıtı: henüz veri yok")]
    pbo = guard(lambda: pbo_satiri(env), None)
    if pbo:
        out.append(pbo)
    out.append(guard(lambda: alinmayan_satiri(env), "Alınmayan sinyal: henüz veri yok"))
    return out


def _comment(llm, b, led_path: str, day: datetime) -> tuple[str | None, str]:
    """(yorum metni | None, durum). Butce mantigi eskisi gibi: authorize -> cagri -> record (hata/sapmada release)."""
    try:
        led = L.open_ledger(led_path, "learner", create=False, read_only=True, migrate=False)
    except Exception as e:  # noqa: BLE001
        log.warning("defter acilamadi: %s", LS.scrub(e))
        return None, "no_ledger"
    try:
        stats, user = build_input(led, (day - timedelta(days=6)).date().isoformat(), day.date().isoformat())
    except Exception as e:  # noqa: BLE001
        log.warning("yorum girdisi kurulamadi: %s", LS.scrub(e))
        return None, "no_ledger"
    finally:
        close = getattr(led, "close", None)
        if close:
            close()
    if stats["not_sayisi"] == 0:
        return None, "no_notes"
    params = {"model": MODEL, "max_tokens": MAX_OUT, "system": SYSTEM,
              "messages": [{"role": "user", "content": user}]}
    est = b.estimate_cost(MODEL, max(1, (len(SYSTEM) + len(user)) // 3), MAX_OUT)
    grant = b.authorize(SERVICE, est)
    if not hasattr(grant, "grant_id"):                     # Denial: pay/tavan bitti => yorum yok
        return None, "budget_denied"
    try:
        text, usage = llm(params)
    except Exception as e:  # noqa: BLE001
        b.release(grant)
        log.warning("LLM hatasi: %s", LS.scrub(type(e).__name__))
        return None, "llm_error"
    try:
        b.record(SERVICE, grant, LS.budget_usage(usage), MODEL, False)
    except Exception as e:  # noqa: BLE001
        log.error("butce kaydi yazilamadi: %s", LS.scrub(e))
    text = (text or "").strip()
    return (text, "ok") if text else (None, "empty")


def main(argv=None, *, llm=None, budget=None, now_fn=None, env=None) -> int:
    ap = argparse.ArgumentParser(prog="weekly_summary_run.py")
    ap.add_argument("--once", action="store_true", required=True)
    ap.add_argument("--day", help="YYYY-MM-DD: bu gunun haftasi (varsayilan: bugun UTC); son 7 gun ozetlenir")
    ap.add_argument("--ledger")
    ap.add_argument("--out-dir")
    ap.add_argument("--lesson-store", help="ders deposu (cikis kaniti bekleyen oneri sayisi); varsayilan user_data/lesson.sqlite")
    ap.add_argument("--force", action="store_true", help="bu hafta icin ozet varsa yeniden yaz")
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
    out = out_dir / f"{week_key(day)}.md"
    if out.exists() and not args.force:
        print(json.dumps({"status": "exists", "week": week_key(day)}))
        return 0
    if llm is None:
        try:
            llm = _default_llm(env, b)
        except Exception as e:  # noqa: BLE001
            log.warning("LLM istemcisi kurulamadi: %s", LS.scrub(e))
            llm = None
    store = args.lesson_store or env.get("LESSON_STORE") or "user_data/lesson.sqlite"
    satirlar = sabit_bolum(env, lp, now, _resolve(store))     # LLM'den bagimsiz: anahtarsiz da yazilir
    yorum, yorum_durum = (None, "no_api_key") if llm is None else _comment(llm, b, lp, day)
    body = f"# Haftalik ozet {week_key(day)}\n\n{SABIT_BASLIK}\n" + "\n".join(satirlar) + "\n"
    if yorum:
        body += f"\n{YORUM_BASLIK}\n{yorum}\n"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
    except OSError as e:
        print(f"ozet yazilamadi: {LS.scrub(e)}", file=sys.stderr)
        return 3
    print(json.dumps({"status": "ok", "week": week_key(day), "file": str(out), "comment": yorum_durum}))
    return 2 if yorum_durum in ("llm_error", "empty") else 0


if __name__ == "__main__":
    sys.exit(main())
