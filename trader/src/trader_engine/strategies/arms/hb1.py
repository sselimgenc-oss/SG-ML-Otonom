"""HB1: haber kolu (ust lig; tasarim fikirler/pazartesi-23-11/ust-lig-tasarim.md bolum 1 ve 6). Aday, `haber_sinyal.json` dosyasindan uretilir.

Kol YALNIZ `var/learner/sinyal/haber_sinyal.json` dosyasini salt okur (ham haberi okumaz; dosyayi `scripts/haber_sinyal_run.py` uretir).
Dosya yok / bozuk / sema disi / bayat -> aday yok (yalniz girisler durur; diger kollar ve acik pozisyon cikislari etkilenmez; M1 ile ayni ilke).
Giris (long; short aynasi), hepsi birlikte:
  1) dosya taze: uretim + GECERLILIK_SAAT (3 sa) > karar zamani D; ve mum kapanisi (= D) > uretim + SIZINTI_MARJ_S (60 sn): sinyal yalniz
     uretimden SONRA kapanan mumda alinir (yayin saati degil alim saati; sizinti yok);
  2) enstrumanin sonumlu birlesik puani |puan| >= ESIK_PUAN (puan dosyada hazir: [-3, 3], 6 saat pencere, 2 saat yari omur);
  3) teyit_kaynak (YALNIZ sinyal yonundeki, yon != 0 olaylarin farkli kaynaklari) >= MIN_KAYNAK (2) YA DA yonlu max_siddet == 3;
     olay ham degerleri dosyada varsa puan/teyit karar zamanina gore YENIDEN sonumlenir; yoksa sinyal yasi > MAX_SINYAL_YASI_DK (90 dk)
     ise aday yok (normal akis ~52 dk);
  4) son kapanmis 1s mum sinyal yonunde kapanmis (long: close > open; short: close < open).
Stop = giris -/+ 1,5 ATR, hedef = giris +/- 3 ATR (M1 ile ayni), zaman stopu 24 mum (ortak kural). Zaman dilimi yalniz 1s.
Kapsam: dosyadaki enstrumanlar (43: kripto + hisse + emtia); seans kurallari mevcut altyapidan gelir."""
from __future__ import annotations

import json
import logging
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Sinyal dosyasi sozlesmesi (trader_core.haber_sinyal ile ayni; motor o modulu ICE AKTARMAZ: bagimlilik yonu).
# Esitlik tests/engine/test_hb1_kol.py icinde sinanir.
HS_SEMA = "haber_sinyal/2"
HS_GECERLILIK_SAAT = 3.0
HS_PUAN_SINIR = 3.0
HS_PENCERE_SAAT = 6.0
HS_YARI_OMUR_SAAT = 2.0
HS_H_MS = 3_600_000
HS_CIKTI_DOSYASI = "haber_sinyal.json"
from trader_core import pa_features as PF

from . import ArmInput
from . import _pa as P
from .m1 import empty_output

log = logging.getLogger("trader.hb1")

SETUP = "HB1"
TIMEFRAMES = ("1h",)
CORE = False
EXIT_MODE = "target"
TIME_STOP = 24                           # 25.11 kullanici karari: HB1 zaman stopu 24 mum (tasarim; motor varsayilani 48 degil)
PRIORITY = 92                           # M1 (90) ile ayni mumda cakisirsa M1 kazanir; DL1 icin 95 ayrilmis
FEATURES = {"hb1_body": "body_ratio", "hb1_wick": "wick_ratio", "hb1_rr": "rr"}
# olay_kimligi ML ozellik tasiyicisina (edge_dist_atr) YAZILMAZ: suzgec ozelligini bozardi. `reasons` etiketi `hb1_olay=<kimlik>` olarak
# tasinir (tum canli ayni yonlu olay kimlikleri "+" ile, kucukten buyuge); gates._features bunu features["hb1_olay"] alanina virgullu METIN olarak yazar (ML sayisal ozellik cikarimi metni atlar).
# "Ayni haberle yeniden giris yok" kontrolu gates.py `_hb1_olay_karari` (kol defteri okuyamaz).
OLAY_ETIKET = "hb1_olay="

# ---- adlandirilmis sabitler (giris kurali)
ESIK_PUAN = 0.6          # |sonumlu puan| alt siniri. Tek olay puani = yon * siddet/3 * guven * sonum <= 1; 0,6 ~ "taze, siddet 3, guven >= 0,6"
                         # ya da birkac orta olayin toplami. Dosyanin kirpma siniri PUAN_SINIR = 3.
MIN_KAYNAK = 2           # en az bu kadar farkli haber kaynagi (sinyal yonunde) ...
SIDDET_YETERLI = 3       # ... YA DA enstrumanin en yuksek olay siddeti bu (0-3)
SIZINTI_MARJ_S = 60      # mum kapanisi > sinyal uretimi + bu kadar sn (sizinti korumasi)
MAX_SINYAL_YASI_DK = 90  # olay ham degerleri dosyada yoksa: karar - uretim bundan buyukse aday yok (normal akis ~52 dk)
GECERLILIK_SAAT = HS_GECERLILIK_SAAT   # dosya alani gecerlilik_sonu_ms bundan uzun olsa bile uretim + 3 sa'te tavanlanir

RR = PF.TARGET_ATR / PF.STOP_ATR
_REPO_ROOT = Path(__file__).resolve().parents[4]
SINYAL_YOLU = Path(os.environ.get("TRADER_HABER_SINYAL") or (_REPO_ROOT / "var" / "learner" / "sinyal" / HS_CIKTI_DOSYASI))

# gozlem sayaclari (surec boyunca; log + test): neden -> adet
COUNTERS: Counter = Counter()
_ONBELLEK: dict = {"key": None, "belge": None, "neden": None}


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def belge_dogrula(d) -> dict | None:
    """Ust duzey sema kontrolu; gecerliyse belge, degilse None. Enstruman satirlari tek tek `satir_gecerli` ile sinanir."""
    if not isinstance(d, dict) or d.get("schema") != HS_SEMA:
        return None
    if not _int(d.get("uretim_ms")) or not _int(d.get("gecerlilik_sonu_ms")) or not isinstance(d.get("enstrumanlar"), dict):
        return None
    return d


def olay_gecerli(e) -> bool:
    return (isinstance(e, dict) and _int(e.get("alim_ms")) and e.get("yon") in (-1, 0, 1) and _int(e.get("yon"))
            and _int(e.get("siddet")) and 0 <= e["siddet"] <= 3 and _num(e.get("guven")) and 0.0 <= e["guven"] <= 1.0
            and _num(e.get("ufuk_saat")) and e["ufuk_saat"] > 0 and isinstance(e.get("kaynaklar"), list)
            and all(isinstance(k, str) for k in e["kaynaklar"]) and _int(e.get("kimlik")) and e["kimlik"] >= 0)


def satir_gecerli(s) -> bool:
    return (isinstance(s, dict) and _num(s.get("puan")) and abs(s["puan"]) <= HS_PUAN_SINIR + 1e-9
            and _int(s.get("kaynak_sayisi")) and s["kaynak_sayisi"] >= 0 and _int(s.get("teyit_kaynak")) and s["teyit_kaynak"] >= 0
            and _int(s.get("max_siddet")) and 0 <= s["max_siddet"] <= 3
            and _int(s.get("olay_kimligi")) and 0 <= s["olay_kimligi"] < 2 ** 53
            and ("olaylar" not in s or (isinstance(s["olaylar"], list) and all(olay_gecerli(e) for e in s["olaylar"]))))


def yayinci(kaynak: str) -> str:
    """Besleme adi -> yayinci (24.11; trader_core.haber_sinyal.yayinci ile ayni kural): ayni yayincinin beslemeleri tek teyit."""
    return str(kaynak).split("_", 1)[0]


def yeniden_sonumle(s: dict, D_ms: int) -> dict:
    """Satirda ham olaylar varsa puan/teyit/max_siddet/olay_kimligi'ni karar zamanina (D) gore yeniden hesaplar (uretici `birlestir` ile
    ayni formul: pencere 6 sa, yari omur 2 sa, olay ufku). Olaylar yoksa satir aynen doner."""
    if "olaylar" not in s:
        return s
    puan, canli = 0.0, []
    for e in s["olaylar"]:
        yas = (D_ms - e["alim_ms"]) / HS_H_MS
        if yas < 0 or yas > HS_PENCERE_SAAT or yas > e["ufuk_saat"]:
            continue
        puan += e["yon"] * (e["siddet"] / 3.0) * e["guven"] * 0.5 ** (yas / HS_YARI_OMUR_SAAT)
        if e["yon"] != 0:
            canli.append(e)
    puan = max(-HS_PUAN_SINIR, min(HS_PUAN_SINIR, puan))
    yon = 1 if puan > 0 else -1 if puan < 0 else 0
    ayni = [e for e in canli if e["yon"] == yon] if yon else []
    en_yeni = max(ayni, key=lambda e: (e["alim_ms"], e["kimlik"]), default=None)
    return {**s, "puan": puan, "teyit_kaynak": len({yayinci(k) for e in ayni for k in e["kaynaklar"]}),
            "max_siddet": max((e["siddet"] for e in ayni), default=0), "olay_kimligi": en_yeni["kimlik"] if en_yeni else 0,
            "olay_kimlikleri": sorted({e["kimlik"] for e in ayni})}


def sinyal_oku(yol: Path | None = None) -> tuple[dict | None, str | None]:
    """(belge, None) ya da (None, neden). Neden: yok | bozuk | sema. mtime+boyut onbellegi (her cift/saat icin dosyayi yeniden okumaz)."""
    yol = Path(yol or SINYAL_YOLU)
    try:
        st = yol.stat()
    except OSError:
        return None, "yok"
    key = (str(yol), st.st_mtime_ns, st.st_size)
    if _ONBELLEK["key"] == key:
        return _ONBELLEK["belge"], _ONBELLEK["neden"]
    try:
        raw = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        belge, neden = None, "bozuk"
    else:
        belge = belge_dogrula(raw)
        neden = None if belge is not None else "sema"
    _ONBELLEK.update(key=key, belge=belge, neden=neden)
    return belge, neden


def _red(neden: str, ayrinti: str = ""):
    COUNTERS[neden] += 1
    if COUNTERS[neden] == 1 or neden in ("yok", "bozuk", "sema", "bayat"):
        log.debug("HB1 aday yok: %s %s", neden, ayrinti)
    return None


def yon_sec(inp_pair: str, belge: dict, D: datetime, o: float, c: float) -> tuple[str, dict] | None:
    """Saf karar: (yon, satir) ya da None. Tum giris sartlari (taze, sizinti, esik, kaynak/siddet, mum yonu) burada."""
    D_ms = int(D.astimezone(timezone.utc).timestamp() * 1000)
    uretim = belge["uretim_ms"]
    son = min(belge["gecerlilik_sonu_ms"], uretim + int(GECERLILIK_SAAT * HS_H_MS))
    if son <= D_ms:
        return _red("bayat")
    if D_ms <= uretim + SIZINTI_MARJ_S * 1000:
        return _red("sizinti")
    s = belge["enstrumanlar"].get(inp_pair)
    if s is None:
        return _red("sinyal_yok")
    if not satir_gecerli(s):
        return _red("satir_bozuk")
    if "olaylar" in s:
        s = yeniden_sonumle(s, D_ms)
    elif D_ms - uretim > MAX_SINYAL_YASI_DK * 60_000:
        return _red("eski_sinyal")
    if abs(s["puan"]) < ESIK_PUAN:
        return _red("esik_alti")
    if not (s["teyit_kaynak"] >= MIN_KAYNAK or s["max_siddet"] >= SIDDET_YETERLI):
        return _red("tek_kaynak")
    yon = "long" if s["puan"] > 0 else "short"
    if not ((c > o) if yon == "long" else (c < o)):
        return _red("mum_ters")
    return yon, s


def compute(inp: ArmInput):
    belge, neden = sinyal_oku()
    if belge is None:                       # dosya yok/bozuk/sema disi: aday yok; kurulum tablosu hic hesaplanmaz (D-T22)
        COUNTERS[neden or "yok"] += 1
        return empty_output(inp.trig.index)
    trig = inp.trig
    if len(trig) < PF.WINDOW:
        return empty_output(trig.index)
    o, c = float(trig["open"].iloc[-1]), float(trig["close"].iloc[-1])
    if not (math.isfinite(o) and math.isfinite(c)):
        return empty_output(trig.index)
    karar = yon_sec(inp.pair, belge, inp.D, o, c)
    if karar is None:
        return empty_output(trig.index)
    side, s = karar
    core = inp.core()
    if core is None:                        # ortak tablo yok: aday yok
        return empty_output(trig.index)
    p = P.prepare(inp, core)
    tab = P.Table(p.core)
    i = len(p.c) - 1
    if not bool(p.ok[i]):
        return tab.frame()
    atr = PF.atr_at(p.h, p.l, p.c, i)
    sg = P.SIGN[side]
    entry = float(p.c[i])
    stop = entry - sg * PF.STOP_ATR * atr
    target = entry + sg * PF.TARGET_ATR * atr
    rng = p.h[i] - p.l[i]
    body = float(abs(p.c[i] - p.o[i]) / rng)
    wick = float((p.h[i] - max(p.o[i], p.c[i])) / rng) if side == "long" else float((min(p.o[i], p.c[i]) - p.l[i]) / rng)
    COUNTERS["aday"] += 1
    ids = s.get("olay_kimlikleri")                      # tum canli ayni yonlu olaylar (olaylar yoksa yalniz en yeni kimlik)
    ids = sorted({int(x) for x in ids}) if ids else ([int(s["olay_kimligi"])] if int(s["olay_kimligi"]) > 0 else [])
    tab.put(i, setup=SETUP, side=side, skip=None,
            labels=["hb1", f"puan={s['puan']:+.2f}", f"k={s['teyit_kaynak']}", f"s={s['max_siddet']}", f"{OLAY_ETIKET}{'+'.join(map(str, ids)) if ids else 0}"], entry=entry,
            stop=stop, target=target, rr=RR, sda=PF.STOP_ATR, ema=np.nan, body=body, wick=wick, edge=np.nan, pb=0)
    return tab.frame()
