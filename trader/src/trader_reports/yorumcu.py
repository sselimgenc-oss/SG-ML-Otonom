"""YZ yorumcu (ust lig tasarimi §3): gunluk sade Turkce rapor. YETKISI YOK: yalniz `var/durum/yorumcu/` altina yazar.

Tum sayilar kodla hesaplanir ve kompakt tablolara konur; model yalniz yorumlar. Model cevabindan sonra kodla uc kontrol:
  1. sayi kontrolu: rapordaki her sayi girdi tablolarinda gecmeli; gecmezse rapor "SAYI HATASI" ile baslar;
  2. n < 30 satirlari "yetersiz örnek" tasir (kolu anan satirda yoksa kod ekler);
  3. en cok 3 oneri; her onerinin "Nasıl ölçülür" kismi olmali.
Motor bu modulu ve cikti dizinini OKUMAZ (kaynak tarama testi). Ders sistemine bagli degildir. Kilitli donem (HOLDOUT) okunmaz:
islemler/kararlar `tur1_olcum.holdout_filtrele` ile elenir. Bu modul ag/sqlite/dosya acmaz; girdiyi cagiran verir.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from . import tur1_olcum as T

MODEL = "claude-sonnet-5-5"
SERVICE = "yorumcu"
MAX_OUT = 2500
YETERSIZ = T.YETERSIZ
YETERSIZ_N = T.YETERSIZ_N          # 30
MAX_ONERI = 3
SON_GUN = 7
ISARET_SAYI_HATASI = "SAYI HATASI"
CIKTI_DIZIN = "var/durum/yorumcu"

SYSTEM = (
    "Sen bir kagit-islem botunun gunluk yorumcususun. Okuyucu teknik olmayan sahibi. Sade Turkce yaz, kisa cumleler, "
    "teknik terimi bir cumleyle ac. YALNIZCA verilen tablolardaki sayilari kullan; hicbir sayiyi yuvarlama, hesaplama, "
    "toplama ya da turetme: sayiyi tabloda yazdigi gibi aynen kopyala. Tabloda olmayan sayi yazma. "
    "Her bulguda ornek sayisini (n) yaz; n < 30 ise ayni cumlede 'yetersiz örnek' de ve kesin sonuc cikarma. "
    "Para tavsiyesi verme; gercek paraya gecis hakkinda yorum yapma; hicbir ayari degistiremezsin, yalniz oner. "
    "Bicim: '## Bulgular' basligi altinda en cok 5 madde; '## Öneriler' basligi altinda EN COK 3 madde, her biri "
    "'Öneri 1:' , 'Öneri 2:' ... diye baslar ve icinde 'Nasıl ölçülür:' ile onerinin nasil sinanacagini yazar. "
    "Veri yetersizse bunu acikca soyle; oneri vermek zorunda degilsin.")


# ----------------------------------------------------------------------------- tablolar (tum sayilar kodla)
def _f(x, nd=3) -> str:
    return "yok" if x is None else f"{x:.{nd}f}"


def kol_tablosu(trades: list[dict], now: datetime) -> list[dict]:
    """Kol (arm) basina: tum zaman n/toplam/ort/kazanma orani + son 7 gun n/toplam. Sayilar R cinsinden, masraf sonrasi."""
    esik = (now - timedelta(days=SON_GUN)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    by: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by[t["arm"]].append(t)
    rows = []
    for arm in sorted(by):
        xs = by[arm]
        r = [t["net_r"] for t in xs]
        son = [t["net_r"] for t in xs if t["exit_ts"] >= esik]
        n = len(r)
        rows.append({"kol": arm, "n": n, "toplam_R": round(T.toplam(r), 2), "ort_R": round(T.toplam(r) / n, 3),
                     "kazanma_orani_yuzde": round(100.0 * sum(1 for v in r if v > 0) / n, 1),
                     "son7g_n": len(son), "son7g_toplam_R": round(T.toplam(son), 2),
                     "etiket": YETERSIZ if n < YETERSIZ_N else ""})
    return rows


def dun_tablosu(trades: list[dict], now: datetime) -> dict:
    gun = (now - timedelta(days=1)).date().isoformat()
    xs = [t["net_r"] for t in trades if t["exit_ts"][:10] == gun]
    return {"gun": gun, "kapanan_n": len(xs), "toplam_R": round(T.toplam(xs), 2),
            "etiket": YETERSIZ if len(xs) < YETERSIZ_N else ""}


def karar_tablosu(decisions: list[dict]) -> dict:
    ac = Counter(d.get("final_action") or "yok" for d in decisions)
    neden = Counter(d.get("skip_reason") for d in decisions if d.get("skip_reason"))
    return {"n_karar": len(decisions), "eylem": dict(sorted(ac.items())),
            "en_sik_red_nedenleri": [{"neden": k, "n": v} for k, v in neden.most_common(5)]}


def olcum_ozeti(olcum: dict | None) -> dict | None:
    """tur1_olcum_v1.json'dan kompakt kesit: canli sartlari maddeleri, rastgele giris yuzdeligi, ilk 5 kayip kumesi."""
    if not isinstance(olcum, dict):
        return None
    b = olcum.get("bolumler") or {}
    out: dict = {"uretim": olcum.get("uretim"), "n_islem": olcum.get("n_islem")}
    ra = ((b.get("rakip_kiyasi") or {}).get("rastgele_giris")) or {}
    if ra.get("durum") == "ok":
        out["rastgele_giris"] = {"n": ra.get("n"), "yuzdelik": round(float(ra["yuzdelik"]), 1), "p": round(float(ra["p"]), 3)}
    out["canli_sartlari"] = [{"ad": m.get("ad"), "sonuc": m.get("sonuc"), "deger": m.get("deger")}
                             for m in ((b.get("canli_sartlari") or {}).get("maddeler") or [])]
    kk = (b.get("kayip_kumeleri") or {}).get("sayiya_gore") or []
    out["kayip_kumeleri"] = [{"kol": r.get("kol"), "rejim": r.get("rejim"), "yon": r.get("yon"), "saat": r.get("saat"),
                              "kayip_sayisi": r.get("kayip_sayisi"), "toplam_kayip_R": r.get("toplam_kayip_r")} for r in kk[:5]]
    return out


def alinmayan_ozeti(doc: dict | None) -> list[dict] | None:
    try:
        if not isinstance(doc, dict) or doc.get("sema") != "ml.alinmayan_sonuc.v1":
            return None
        return [{"neden": r["etiket"], "n": int(r["n"]), "toplam_pnl_usd": round(float(r["toplam_pnl"]), 2)}
                for r in (doc["tablolar"].get("neden") or []) if int(r["n"]) >= 1][:8]
    except (KeyError, TypeError, ValueError):
        return None


def tablolari_kur(trades_raw: list[dict], decisions_raw: list[dict], now: datetime, *, olcum: dict | None = None,
                  alinmayan: dict | None = None, haftalik_sabit: list[str] | None = None,
                  dersler: list[str] | None = None) -> dict:
    """Girdi tablolari. Kilitli donem burada elenir (tek gecit: `tur1_olcum.holdout_filtrele`)."""
    trades, decisions, kilit = T.holdout_filtrele(trades_raw, decisions_raw)
    return {"tarih": now.astimezone(timezone.utc).date().isoformat(), "yetersiz_ornek_esigi_n": YETERSIZ_N,
            "son_gun_penceresi": SON_GUN, "kilitli_donem_atilan_islem": kilit,
            "toplam_kapanmis_islem": len(trades), "kollar": kol_tablosu(trades, now), "dun": dun_tablosu(trades, now),
            "kararlar": karar_tablosu(decisions), "olcum": olcum_ozeti(olcum), "alinmayan_sinyal": alinmayan_ozeti(alinmayan),
            "haftalik_sabit_bolum": list(haftalik_sabit or []), "aktif_dersler": list(dersler or [])}


def tablo_metni(tablolar: dict) -> str:
    return json.dumps(tablolar, ensure_ascii=False, sort_keys=True, indent=1)


def kullanici_istemi(tablolar: dict) -> str:
    return ("Asagidaki tablolari yorumla. Tablolardaki 'etiket' alani 'yetersiz örnek' ise o satir n < 30 demektir.\n\n"
            + tablo_metni(tablolar))


def parametreler(tablolar: dict) -> dict:
    return {"model": MODEL, "max_tokens": MAX_OUT, "system": SYSTEM,
            "messages": [{"role": "user", "content": kullanici_istemi(tablolar)}]}


# ----------------------------------------------------------------------------- cevap denetimi
_SAYI = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")
_SERBEST_TAM = {"1", "2", "3", "4", "5"}      # madde numaralari / "Öneri 2" (tablo disi yalniz bunlar serbest)


def sayilar(metin: str) -> set[float]:
    """Metindeki sayilar sayisal deger olarak ('12,50' == 12.5; isaret ayri durur, mutlak deger alinir)."""
    return {float(m.group(0).replace(",", ".")) for m in _SAYI.finditer(metin)}


def sayi_kontrolu(rapor: str, girdi_metni: str) -> list[str]:
    """Rapordaki girdide bulunmayan sayilar (bos liste = temiz). Tarih parcalari girdideki `tarih` alanindan gelir."""
    izinli = sayilar(girdi_metni)
    kotu = []
    for tok in sorted(sayilar(rapor)):
        if tok in izinli or (tok.is_integer() and str(int(tok)) in _SERBEST_TAM):
            continue
        kotu.append(f"{tok:g}")
    return kotu


def yetersiz_satirlari_tamamla(rapor: str, tablolar: dict) -> str:
    """n < 30 olan bir kolu/satiri anan her satirda 'yetersiz örnek' yoksa kod ekler (model unutsa da kural korunur)."""
    zayif = {k["kol"]: k["n"] for k in tablolar.get("kollar", []) if k["n"] < YETERSIZ_N}
    out = []
    for ln in rapor.splitlines():
        if ln.strip() and not ln.lstrip().startswith("#") and YETERSIZ not in ln:
            for kol, n in zayif.items():
                if re.search(rf"(?<![\w@]){re.escape(kol)}(?![\w])", ln):
                    ln = f"{ln} ({YETERSIZ}, n={n})"
                    break
        out.append(ln)
    return "\n".join(out)


_ONERI = re.compile(r"^\s*(?:[-*]\s*)?\**Öneri\s*\d", re.M)


def onerileri_sinirla(rapor: str) -> tuple[str, list[str]]:
    """En cok 3 oneri (fazlasi kesilir); 'Nasıl ölçülür' eksik onerilere not duser. Uyarilari doner."""
    uy = []
    ms = list(_ONERI.finditer(rapor))
    if len(ms) > MAX_ONERI:
        rapor = rapor[:ms[MAX_ONERI].start()].rstrip() + "\n"
        uy.append(f"model {MAX_ONERI}'ten fazla öneri verdi; ilk {MAX_ONERI} öneri tutuldu")
        ms = ms[:MAX_ONERI]
    parcalar = [rapor[m.start():(ms[i + 1].start() if i + 1 < len(ms) else len(rapor))] for i, m in enumerate(ms)]
    for p in parcalar:
        if not re.search(r"nas[ıi]l [öo]l[çc][üu]l[üu]r", p, re.I):
            uy.append("bir önerinde 'Nasıl ölçülür' yok")
            rapor = rapor.replace(p, p.rstrip() + "\n  Nasıl ölçülür: belirtilmedi (model atladı).\n", 1)
    return rapor, uy


def raporu_denetle(model_metni: str, tablolar: dict) -> tuple[str, dict]:
    """Model cevabi -> son rapor metni (+ denetim ozeti). Sayi kontrolu MODELIN metni uzerinde yapilir (kodun ekledikleri girdidendir)."""
    girdi = tablo_metni(tablolar)
    kotu = sayi_kontrolu(model_metni, girdi)
    govde, uy = onerileri_sinirla(yetersiz_satirlari_tamamla(model_metni.strip(), tablolar))
    ust = []
    if kotu:
        ust.append(f"**{ISARET_SAYI_HATASI}**: yapay zekâ verilerde olmayan sayı yazdı ({', '.join(kotu)}). Bu sayılara güvenme; diğerleri verilerden.")
    ust += [f"UYARI: {u}." for u in uy]
    metin = f"# Yorumcu raporu {tablolar['tarih']}\n\n" + ("\n".join(ust) + "\n\n" if ust else "")
    metin += ("Yalnız yorum: bu rapor hiçbir ayarı değiştirmez, işlem açıp kapatmaz. "
              f"Kapanmış işlem n = {tablolar['toplam_kapanmis_islem']}.\n\n") + govde.rstrip() + "\n"
    return metin, {"sayi_hatasi": kotu, "uyarilar": uy}


def rapor_yok(tarih: str, neden: str) -> str:
    return f"# Yorumcu raporu {tarih}\n\nbugün rapor yok: {neden}\n"


TG_PARCA = 3300                      # Telegram mesaj siniri (MAX_TEXT=3500) altinda, etiket payi birakir


def _sade(ln: str) -> str:
    """Markdown isaretlerini atar: "## Baslik" -> "📌 Baslik", '**x**' -> 'x', '- ' -> '• '."""
    t = ln.strip()
    if t.startswith("#"):
        return "📌 " + t.lstrip("#").strip()   # .upper() Turkce i harfini bozar (Öneriler -> ÖNERILER)
    t = t.replace("**", "").replace("__", "")
    if t.startswith(("- ", "* ")):
        t = "• " + t[2:]
    return t.replace(f"{ISARET_SAYI_HATASI}:", "⚠️ Dikkat:")


def telegram_parcalari(metin: str, tarih: str, sinir: int = TG_PARCA) -> list[str]:
    """Raporun TAMAMI, sade metin olarak (markdown isareti yok, dosya yolu yok); uzunsa satir sinirindan parcalara bolunur."""
    satirlar = [_sade(ln) for ln in metin.splitlines() if not ln.startswith("# ")]
    govde = re.sub(r"\n{3,}", "\n\n", "\n".join(satirlar)).strip()
    parcalar, cur = [], ""
    for ln in govde.split("\n"):
        while len(ln) > sinir:                      # tek satir bile sigmiyorsa kelime sinirindan bol
            k = ln[:sinir].rsplit(" ", 1)[0] or ln[:sinir]
            if cur:
                parcalar.append(cur); cur = ""
            parcalar.append(k); ln = ln[len(k):].lstrip()
        if cur and len(cur) + 1 + len(ln) > sinir:
            parcalar.append(cur); cur = ln
        else:
            cur = f"{cur}\n{ln}" if cur else ln
    if cur:
        parcalar.append(cur)
    n = len(parcalar)
    bas = f"Yorumcu raporu {tarih}"
    return [f"{bas}{f' ({i}/{n})' if n > 1 else ''}\n\n{p}" for i, p in enumerate(parcalar or ["(boş rapor)"], 1)]


def telegram_ozeti(metin: str, tarih: str) -> str:
    """Geriye uyum: ilk parca."""
    return telegram_parcalari(metin, tarih)[0]
