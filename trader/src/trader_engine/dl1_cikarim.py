"""DL1 cikarimi (ust lig derin ogrenme kolu; tasarim fikirler/pazartesi-23-11/ust-lig-tasarim.md bolum 2 ve 6).

Saf numpy + stdlib. Motor torch'u ve trader_ml'i ICE AKTARMAZ (bagimlilik yonu): egitim her gun GitHub Actions'ta
(`research/dl1/egit.py`, PyTorch) yapilir; sunucuya yalniz `models/dl1/DL1@1h.json` paketi gelir. Egitim tarafi da kanal
hesabini ve paket ozetini BURADAN alir (egitim ve canli ayni kod; sizinti/uyumsuzluk riski yok).

Dort zaman dilimi (24.11 kullanici karari): 15m, 1h, 4h, 1d; her biri kendi paketi (`models/dl1/DL1@<tf>.json`). Ag ve kanallar ayni; "mum" = o zaman diliminin
mumu (pencere 96 mum, ufuk 48 mum, doluluk orani mum biriminde hesaplanir).

Paket (`dl1/1`): agirliklar, olcekleyici (yalniz egitim diliminden), esik (egitim puanlarinin %98'ligi), kanal listesi, kapsam (cift -> varlik sinifi),
olusturma ve son_kullanma (+45 gun; YALNIZ yas uyarisi), metrikler, sha256 (kendisi haric kanonik JSON ozeti). Yok / bozuk / hash tutmuyor / sema
-> `paket_yukle` (None, neden) doner; kol aday uretmez, diger kollar etkilenmez. 24.11: kalite kapisi (paketteki `kapi.gecti`) ve 45 gunluk son kullanma
paketi ENGELLEMEZ; kapi sonucu yalniz bilgi/rapordur, eski paket islem yapmaya devam eder (kol yalniz uyari sayaci tutar).

Ag (sabit mimari; torch ile birebir ayni dizilim, `Conv1d` cross-correlation, gecerli dolgu):
  girdi (96 mum, 11 kanal: 8 fiyat/hacim + 3 varlik sinifi tek-sicak) -> conv c1(11->32,k5) ReLU -> c2(32->48,k5,adim 2) ReLU -> c3(48->64,k5,adim 2) ReLU
  -> [ortalama | maksimum] zaman havuzu (128) -> d1(128->64) ReLU -> head(64->3) = [long_logit, short_logit, oynaklik]
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

SEMA = "dl1/1"
ZAMAN_DILIMLERI = ("15m", "1h", "4h", "1d")
BAR_NS = {"15m": 900_000_000_000, "1h": 3_600_000_000_000, "4h": 14_400_000_000_000, "1d": 86_400_000_000_000}   # arm_time.ARM_TF_SECONDS ile ayni (testle esitlik)
ARM_ID = "DL1@1h"             # geriye uyum: 1h paketi; diger zaman dilimleri icin arm_id(tf)
PENCERE = 96                  # girdi penceresi (mum)
SINIFLAR = ("kripto", "hisse", "emtia")      # varlik sinifi kanali: tek-sicak, pencere boyunca sabit (olceklenmez)
N_FIYAT = 8
KANALLAR = ("logret", "hl_oran", "govde", "hacim_z", "atr_oran", "fitil_ust", "fitil_alt", "kapanis_konum") + tuple(f"sinif_{x}" for x in SINIFLAR)
N_KANAL = len(KANALLAR)
# Seansli araclar (hisse/emtia): seans kapaliyken mum bos olabilir (hacim 0 ya da h == l) ya da hic gelmez. Bos/eksik mumlar
# DOLDURULMAZ ve yok sayilir: kanal serisi yalniz "dolu" mumlardan kurulur; pencere = son 96 dolu mum. Pencere, takvim zamaninda en az
# MIN_DOLU_ORAN dolulukta olmali: 96 / (ilk ile son dolu mum arasi mum (zaman diliminin mumu) + 1) >= 0,5 (yani 96 dolu mum <= 192 saatlik aralikta). Egitim ve canli ayni kural.
MIN_DOLU_ORAN = 0.5
ATR_UZUN = 14
HACIM_PENCERE = 96
MIN_BAR = PENCERE + HACIM_PENCERE      # canli: bu kadar ardisik kapanmis bar yoksa puan yok (192)
KIRP = 8.0                             # olceklenmis girdi |x| <= 8
UFUK = 48                              # etiket ufku (mum) = canli zaman stopu (signals.TIME_STOP_BARS; testle esitligi sinanir)
STOP_ATR = 1.5
HEDEF_ATR = 3.0
SON_KULLANMA_GUN = 45         # 24.11: yalniz YAS UYARISI esigi (paket bu yastan sonra da islem yapar; sayac + log)
MAX_PAKET_BAYT = 10 * 1024 * 1024
PAKET_DIZINI = Path(__file__).resolve().parents[2] / "models" / "dl1"
PAKET_YOLU = PAKET_DIZINI / "DL1@1h.json"


def arm_id(tf: str) -> str:
    if tf not in BAR_NS:
        raise ValueError(f"bilinmeyen DL1 zaman dilimi: {tf!r}")
    return f"DL1@{tf}"


def paket_yolu(tf: str = "1h") -> Path:
    return PAKET_DIZINI / f"{arm_id(tf)}.json"

# ag sekli: ad -> (agirlik sekli, adim) ; conv w = (cikis, giris, k), dense w = (cikis, giris)
KATMANLAR = (("c1", "conv", N_KANAL, 32, 5, 1), ("c2", "conv", 32, 48, 5, 2), ("c3", "conv", 48, 64, 5, 2),
             ("d1", "dense", 128, 64, 0, 0), ("head", "dense", 64, 3, 0, 0))


def agirlik_sekilleri() -> dict[str, tuple[int, ...]]:
    out: dict[str, tuple[int, ...]] = {}
    for ad, tur, gi, ci, k, _ in KATMANLAR:
        out[ad + ".w"] = (ci, gi, k) if tur == "conv" else (ci, gi)
        out[ad + ".b"] = (ci,)
    return out


def parametre_sayisi() -> int:
    return int(sum(int(np.prod(s)) for s in agirlik_sekilleri().values()))


# ------------------------------------------------------------------------------------------- kanallar
def _pencere_ort(x: np.ndarray, w: int) -> np.ndarray:
    """Her i icin x[i-w+1..i] ortalamasi (ilk w-1 satir NaN; pencerede NaN varsa NaN). Yalniz geriye bakar."""
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        out[w - 1:] = np.lib.stride_tricks.sliding_window_view(x, w).mean(axis=1)
    return out


def _pencere_std(x: np.ndarray, w: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        out[w - 1:] = np.lib.stride_tricks.sliding_window_view(x, w).std(axis=1)
    return out


def atr_serisi(h, l, c) -> np.ndarray:
    """ATR(14) = son 14 gercek araligin ortalamasi (pa_features.atr_at ile ayni tanim). Bar i yalniz <= i'ye bakar."""
    h, l, c = (np.asarray(a, dtype=np.float64) for a in (h, l, c))
    pc = np.r_[np.nan, c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return _pencere_ort(tr, ATR_UZUN)


def kanallar(o, h, l, c, v, sinif: int = 0) -> np.ndarray:
    """(n, 11) kanal matrisi (KANALLAR sirasi); gecersiz satir NaN. YALNIZ kapanmis (dolu) barlar; satir i yalniz <= i'ye bakar. sinif: SINIFLAR indeksi."""
    o, h, l, c, v = (np.asarray(a, dtype=np.float64) for a in (o, h, l, c, v))
    n = len(c)
    out = np.full((n, N_KANAL), np.nan)
    out[:, N_FIYAT:] = 0.0
    out[:, N_FIYAT + int(sinif)] = 1.0
    if n < 2:
        return out
    with np.errstate(divide="ignore", invalid="ignore"):
        pc = np.r_[np.nan, c[:-1]]
        atr = atr_serisi(h, l, c)
        lv = np.log1p(np.maximum(v, 0.0))
        mu, sd = _pencere_ort(lv, HACIM_PENCERE), _pencere_std(lv, HACIM_PENCERE)
        rng = h - l
        out[:, 0] = np.log(c / pc)
        out[:, 1] = rng / c
        out[:, 2] = (c - o) / c
        out[:, 3] = np.where(np.isnan(sd), np.nan, np.where(sd > 1e-12, (lv - mu) / sd, 0.0))
        out[:, 4] = atr / c
        out[:, 5] = (h - np.maximum(o, c)) / c
        out[:, 6] = (np.minimum(o, c) - l) / c
        out[:, 7] = np.where(rng > 0, (c - l) / rng, 0.5)
    bad = ~np.isfinite(out[:, :N_FIYAT]).all(axis=1) | ~(c > 0) | ~(h >= l)
    out[bad, :N_FIYAT] = np.nan
    return out


# ------------------------------------------------------------------------------------------- ileri gecis
def _conv(x: np.ndarray, w: np.ndarray, b: np.ndarray, adim: int) -> np.ndarray:
    """x (B, T, Cin), w (Cout, Cin, K) -> (B, T', Cout); torch Conv1d (dolgu yok) ile ayni."""
    k = w.shape[2]
    win = np.lib.stride_tricks.sliding_window_view(x, k, axis=1)       # (B, T-k+1, Cin, K)
    win = win[:, ::adim]
    return np.tensordot(win, w, axes=([2, 3], [1, 2])) + b


def ileri(agirlik: dict[str, np.ndarray], x: np.ndarray) -> np.ndarray:
    """x (B, 96, 8) OLCEKLENMIS girdi -> (B, 3) logit [long, short, oynaklik]."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 2:
        x = x[None]
    for ad, tur, *_r in KATMANLAR:
        if tur == "conv":
            adim = dict((k[0], k[5]) for k in KATMANLAR)[ad]
            x = np.maximum(_conv(x, agirlik[ad + ".w"], agirlik[ad + ".b"], adim), 0.0)
    z = np.concatenate([x.mean(axis=1), x.max(axis=1)], axis=1)
    z = np.maximum(z @ agirlik["d1.w"].T + agirlik["d1.b"], 0.0)
    return z @ agirlik["head.w"].T + agirlik["head.b"]


def sigmoid(z):
    z = np.asarray(z, dtype=np.float64)
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))


def dolu_maske(h, l, v) -> np.ndarray:
    """Dolu mum: sonlu H/L/hacim, hacim > 0 ve h > l (arm_guard.is_flat_bar'in tersi; eksik/NaN = dolu degil)."""
    h, l, v = (np.asarray(a, dtype=np.float64) for a in (h, l, v))
    with np.errstate(invalid="ignore"):
        return np.isfinite(h) & np.isfinite(l) & np.isfinite(v) & (v > 0) & (h > l)


def pencere_doluluk_ok(ts_ns, pencere: int = PENCERE, bar_ns: int = BAR_NS["1h"]) -> np.ndarray:
    """Dolu mumlarin (siralı, ns) her i'si icin: son `pencere` dolu mumun takvim doluluk orani (mum biriminde, bar_ns) >= MIN_DOLU_ORAN (i < pencere-1: False)."""
    ts_ns = np.asarray(ts_ns, dtype=np.int64)
    ok = np.zeros(len(ts_ns), dtype=bool)
    if len(ts_ns) >= pencere:
        span_h = (ts_ns[pencere - 1:] - ts_ns[:len(ts_ns) - pencere + 1]) / float(bar_ns) + 1.0
        ok[pencere - 1:] = pencere / span_h >= MIN_DOLU_ORAN - 1e-12
    return ok


def olcekle(x: np.ndarray, ort: np.ndarray, std: np.ndarray) -> np.ndarray:
    """Fiyat kanallari (x - ort)/std, |.| <= KIRP; sinif kanallari (ort 0, std 1) oldugu gibi kalir (0/1)."""
    z = (x - ort) / std
    z[..., :N_FIYAT] = np.clip(z[..., :N_FIYAT], -KIRP, KIRP)
    return z


# ------------------------------------------------------------------------------------------- paket
def kanonik(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def paket_ozeti(paket: dict) -> str:
    """sha256 alani HARIC kanonik JSON'un sha256'si (egitim yazarken de, motor okurken de bu)."""
    return hashlib.sha256(kanonik({k: v for k, v in paket.items() if k != "sha256"}).encode("utf-8")).hexdigest()


def agirlik_paketle(agirlik: dict[str, np.ndarray]) -> dict:
    """{ad: {"sekil": [...], "veri": [duz liste]}}; 7 ondalik (float32 hassasiyeti)."""
    out = {}
    for ad, sek in agirlik_sekilleri().items():
        a = np.asarray(agirlik[ad], dtype=np.float64)
        if tuple(a.shape) != sek:
            raise ValueError(f"agirlik sekli {ad}: {a.shape} != {sek}")
        out[ad] = {"sekil": list(sek), "veri": [float(v) for v in np.round(a.ravel(), 7)]}
    return out


def agirlik_ac(d) -> dict[str, np.ndarray]:
    """Paket agirlik bolumunu dogrulayip numpy'a acar; bozuksa ValueError."""
    if not isinstance(d, dict):
        raise ValueError("agirlik bolumu sozluk degil")
    out = {}
    for ad, sek in agirlik_sekilleri().items():
        e = d.get(ad)
        if not isinstance(e, dict) or tuple(e.get("sekil", ())) != sek or not isinstance(e.get("veri"), list):
            raise ValueError(f"agirlik {ad}: sekil/veri gecersiz")
        a = np.asarray(e["veri"], dtype=np.float64)
        if a.size != int(np.prod(sek)) or not np.isfinite(a).all():
            raise ValueError(f"agirlik {ad}: boyut/deger gecersiz")
        out[ad] = a.reshape(sek)
    return out


def _utc(s: str) -> datetime:
    d = datetime.fromisoformat(s)
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


@dataclass(frozen=True)
class Paket:
    agirlik: dict
    ort: np.ndarray
    std: np.ndarray
    siniflar: dict                   # cift -> SINIFLAR indeksi (kapsam)
    esik: float
    olusturma: datetime
    son_kullanma: datetime           # min(son_kullanma, olusturma + 45 gun): uzatilmis alan dolanamaz
    sha256: str
    metrikler: dict
    tf: str = "1h"

    def eski(self, simdi: datetime) -> bool:
        """Yas uyarisi (45 gun): True paketi ENGELLEMEZ, yalniz kol sayac/log tutar (24.11 kullanici karari)."""
        return simdi >= self.son_kullanma


def paket_dogrula(paket, tf: str = "1h") -> Paket:
    """Sozluk -> Paket; hash/sema/yapi bozuksa ValueError (mesaj = neden kodu: sema | hash | bozuk | kanal). Kalite kapisi sonucu (`kapi`) engellemez."""
    if not isinstance(paket, dict) or paket.get("schema") != SEMA or paket.get("arm_id") != arm_id(tf):
        raise ValueError("sema")
    sha = paket.get("sha256")
    if not isinstance(sha, str) or sha != paket_ozeti(paket):
        raise ValueError("hash")
    try:
        if tuple(paket["kanallar"]) != KANALLAR or paket["pencere"] != PENCERE:
            raise ValueError("kanal")
        esik = paket["esik"]
        if isinstance(esik, bool) or not isinstance(esik, (int, float)) or not 0.0 < float(esik) < 1.0:
            raise ValueError("bozuk")
        ort = np.asarray(paket["olcekleyici"]["ort"], dtype=np.float64)
        std = np.asarray(paket["olcekleyici"]["std"], dtype=np.float64)
        if ort.shape != (N_KANAL,) or std.shape != (N_KANAL,) or not np.isfinite(ort).all() or not (np.isfinite(std).all() and (std > 0).all()):
            raise ValueError("bozuk")
        siniflar = paket["kapsam"]["siniflar"]
        if not isinstance(siniflar, dict) or not siniflar or not all(
                isinstance(p, str) and isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(SINIFLAR) for p, i in siniflar.items()):
            raise ValueError("bozuk")
        if not (np.all(ort[N_FIYAT:] == 0.0) and np.all(std[N_FIYAT:] == 1.0)):
            raise ValueError("bozuk")
        olus = _utc(paket["olusturma"])
        son = min(_utc(paket["son_kullanma"]), olus + timedelta(days=SON_KULLANMA_GUN))
        ag = agirlik_ac(paket["agirliklar"])
        met = paket.get("metrikler", {})
        if not isinstance(met, dict):
            raise ValueError("bozuk")
    except ValueError as e:
        if str(e) in ("sema", "hash", "bozuk", "kanal"):
            raise
        raise ValueError("bozuk") from e
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError("bozuk") from e
    return Paket(ag, ort, std, dict(siniflar), float(esik), olus, son, sha, met, tf)


_KILIT = threading.Lock()
_ONBELLEK: dict = {"key": None, "paket": None, "neden": None}


def paket_yukle(yol: Path | str | None = None, simdi: datetime | None = None, tf: str = "1h") -> tuple[Paket | None, str | None]:
    """(Paket, None) ya da (None, neden). Neden: yok | buyuk | bozuk | sema | hash | kanal | erken (simdi < olusturma).
    Dosya okuma/dogrulama mtime+boyut onbellegindedir. Eski paket (45 gun) ve kapi sonucu ENGELLEMEZ (24.11); yas icin Paket.eski(simdi)."""
    yol = Path(yol or paket_yolu(tf))
    try:
        st = yol.stat()
    except OSError:
        return None, "yok"
    if st.st_size > MAX_PAKET_BAYT:
        return None, "buyuk"
    key = (str(yol), st.st_mtime_ns, st.st_size, tf)
    with _KILIT:
        if _ONBELLEK["key"] != key:
            try:
                paket, neden = paket_dogrula(json.loads(yol.read_text(encoding="utf-8")), tf), None
            except ValueError as e:
                paket, neden = None, (str(e) if str(e) in ("sema", "hash", "bozuk", "kanal") else "bozuk")
            except OSError:
                paket, neden = None, "bozuk"
            _ONBELLEK.update(key=key, paket=paket, neden=neden)
        paket, neden = _ONBELLEK["paket"], _ONBELLEK["neden"]
    if paket is None:
        return None, neden
    if simdi is not None and simdi < paket.olusturma:
        return None, "erken"             # saat geri / gelecekten damgali paket: kullanilmaz
    return paket, None


def paket_yasi_gun(yol: Path | str | None, simdi: datetime, tf: str = "1h") -> tuple[str, float | None, float | None]:
    """Saglik icin: (durum, yas_gun, kalan_gun). durum: yok | bozuk | ok | eski (eski = 45 gunden yasli; paket yine islem yapar). Hash tutmayan/bozuk -> bozuk."""
    paket, neden = paket_yukle(yol, tf=tf)
    if paket is None:
        return ("yok" if neden == "yok" else "bozuk"), None, None
    yas = (simdi - paket.olusturma).total_seconds() / 86400.0
    kalan = (paket.son_kullanma - simdi).total_seconds() / 86400.0
    return ("eski" if kalan <= 0 else "ok"), yas, kalan


# ------------------------------------------------------------------------------------------- puanlama (canli)
def kompakt(ts_ns, o, h, l, c, v):
    """Dolu mumlari ayiklar (bosluk doldurulmaz). Doner: (ts, o, h, l, c, v) yalniz dolu satirlar."""
    m = dolu_maske(h, l, v) & np.isfinite(np.asarray(o, dtype=np.float64)) & np.isfinite(np.asarray(c, dtype=np.float64))
    return tuple(np.asarray(a)[m] for a in (ts_ns, o, h, l, c, v))


def atr_son(h, l, c) -> float:
    a = atr_serisi(h[-(ATR_UZUN + 2):], l[-(ATR_UZUN + 2):], c[-(ATR_UZUN + 2):])
    return float(a[-1]) if len(a) and math.isfinite(a[-1]) else float("nan")


def puanla(paket: Paket, cift: str, ts_ns, o, h, l, c, v) -> tuple[float, float, float, float] | None:
    """Karar barinin (p_long, p_short, oynaklik, atr) ya da None. Girdi tf OHLCV (son satir = son KAPANMIS bar, ns zaman damgasi).
    None: cift kapsam disi, son bar dolu degil, <192 dolu bar, pencere doluluk orani < MIN_DOLU_ORAN, sonlu olmayan deger.
    ATR dolu mumlardan hesaplanir (egitim etiketi ile ayni)."""
    sinif = paket.siniflar.get(cift)
    if sinif is None or len(c) < MIN_BAR:
        return None
    ts_ns, o, h, l, c, v = (np.asarray(a, dtype=np.float64 if i else np.int64) for i, a in enumerate((ts_ns, o, h, l, c, v)))
    if not bool(dolu_maske(h[-1:], l[-1:], v[-1:])[0]):
        return None
    ts, o, h, l, c, v = kompakt(ts_ns, o, h, l, c, v)
    if len(c) < MIN_BAR:
        return None
    n = MIN_BAR + 24
    ts, o, h, l, c, v = (a[-n:] for a in (ts, o, h, l, c, v))
    if not pencere_doluluk_ok(ts, bar_ns=BAR_NS[paket.tf])[-1]:
        return None
    pen = kanallar(o, h, l, c, v, sinif)[-PENCERE:]
    atr = atr_son(h, l, c)
    if pen.shape[0] != PENCERE or not np.isfinite(pen).all() or not (math.isfinite(atr) and atr > 0):
        return None
    z = ileri(paket.agirlik, olcekle(pen, paket.ort, paket.std))[0]
    if not np.isfinite(z).all():
        return None
    return float(sigmoid(z[0])), float(sigmoid(z[1])), float(z[2]), atr
