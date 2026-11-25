"""IN1: gosterge setuplari kutuphanesi (24.11 kullanici karari; tasarim: fikirler/gorev/2026-11-24-45474500845/gorev_sonuc.md).

17 formasyon, her biri ayri kurulum (`IN1-RSI` ...) ve 4 zaman diliminde ayri kol (VWAP yalniz 15m ve 1h). Dedektorler long uzayinda
(short = fiyat aynasi; gostergeler aynalanmis seriden hesaplanir) YALNIZ `t` ve oncesini okur. Kural cikislari (`EXIT_RULE`) her
kapanan mumda son kapanmis mumu okur; sagliyorsa piyasa emriyle cikilir. Stopsuz setuplara 2 ATR stop konur (kullanici karari).
Ichimoku bulutu `t`de cizilen deger: t-26 ve oncesinin verisinden. Hacim ortalamasi ve "onceki N mum" pencereleri `t`yi icermez.
Kitap kurallari sabit: ders parametresi okunmaz."""
from __future__ import annotations

import numpy as np

from trader_core import indicators as I

from . import ArmInput
from . import _kutuphane as K
from ._kutuphane import Formasyon, hesapla, ortak

SETUP = "IN1"
TIMEFRAMES = ("15m", "1h", "4h", "1d")
CORE = False
EXIT_MODE = "target"
PRIORITY = 400                       # kutuphane tabanlari: GF1 200, MF1 300, IN1 400 (mevcut kollar hep onde: en buyuk 95)
FEATURES = {"body_ratio": "body_ratio", "wick_ratio": "wick_ratio", "rr": "rr", "f_seviye": "ema_value",
            "f_olcu_atr": "edge_dist_atr", "f_yas": "pullback_ema"}


def _uz(g, ad, fn, *arrs):
    """Gosterge dizisini (ya da demetini) bir kez hesaplar; cok uzun serilerde son IND_PENCERE mumdan (basi NaN)."""
    def hesap():
        n = len(arrs[0])
        s = max(0, n - K.IND_PENCERE)
        r = fn(*[a[s:] for a in arrs])
        if s == 0:
            return r
        pad = lambda x: np.r_[np.full(s, np.nan), x]          # noqa: E731
        return tuple(pad(x) for x in r) if isinstance(r, tuple) else pad(r)
    return g.once(ad, hesap)


def _rsi(g, n=14):
    return _uz(g, ("rsi", n), lambda c: I.rsi(c, n), g.c)


def _sma(g, n):
    return _uz(g, ("sma", n), lambda c: I.sma_np(c, n), g.c)


def _ema(g, n):
    return _uz(g, ("ema", n), lambda c: I.ema_np(c, n), g.c)


def _boll(g):
    return _uz(g, "boll", lambda c: I.bollinger(c, 20, 2.0), g.c)


def _macd(g):
    return _uz(g, "macd", lambda c: I.macd(c, 12, 26, 9), g.c)


def _stok(g):
    return _uz(g, "stok", lambda h, l, c: I.stoch(h, l, c, 14, 3, 3), g.h, g.l, g.c)


def _ichi(g):
    return _uz(g, "ichi", lambda h, l, c: I.ichimoku(h, l, c, 9, 26, 52), g.h, g.l, g.c)


def _vwap(g):
    if g.gun is None or g.v is None:
        return None
    return _uz(g, "vwap", lambda h, l, c, v, gun: I.vwap_gunluk(h, l, c, v, gun), g.h, g.l, g.c, g.v, g.gun)


def _sonuc(stop, etiket, *, hedef=None, seviye=None, olcu=None, yas=0):
    return {"stop": float(stop), "hedef": None if hedef is None else float(hedef),
            "seviye": float(stop if seviye is None else seviye), "olcu": olcu, "yas": int(yas), "etiket": etiket}


def _kes_yukari(a, b, t) -> bool:
    return bool(a[t] > b[t] and a[t - 1] <= b[t - 1])


def _kes_asagi(a, b, t) -> bool:
    return bool(a[t] < b[t] and a[t - 1] >= b[t - 1])


def _stop2atr(g):
    return g.c[g.t] - 2.0 * g.atr[g.t]


# ------------------------------------------------------------------------------------------------ dedektorler
def rsi(g):
    t = g.t
    r, s50, s200 = _rsi(g), _sma(g, 50), _sma(g, 200)
    dip10 = g.dip(10)
    if r[t] < 30 and r[t - 1] >= 30 and s50[t] > s200[t] and dip10 < g.c[t]:
        return _sonuc(dip10, "rsi", olcu=g.c[t] - dip10)
    return None


def makesisim(g):
    t = g.t
    a, b = _sma(g, 50), _sma(g, 200)
    if _kes_yukari(a, b, t):
        return _sonuc(_stop2atr(g), "makesisim", olcu=2.0 * g.atr[t])
    return None


def boll(g):
    t = g.t
    m, alt, _ust = _boll(g)
    if g.l[t] <= alt[t] and g.l[t] < g.c[t]:
        return _sonuc(g.l[t], "boll", hedef=m[t], seviye=m[t], olcu=m[t] - g.c[t])
    return None


def fiyatma(g):
    t = g.t
    s = _sma(g, 50)
    if g.c[t] > s[t] and g.c[t - 1] <= s[t - 1]:
        return _sonuc(_stop2atr(g), "fiyatma", seviye=s[t], olcu=2.0 * g.atr[t])
    return None


def macd(g):
    t = g.t
    m, s, _ = _macd(g)
    if _kes_yukari(m, s, t):
        return _sonuc(_stop2atr(g), "macd", olcu=2.0 * g.atr[t])
    return None


def stok(g):
    t = g.t
    k, d = _stok(g)
    if _kes_yukari(k, d, t) and k[t] < 20 and d[t] < 20 and g.c[t] > _sma(g, 50)[t]:
        return _sonuc(g.dip(10), "stok", olcu=g.c[t] - g.dip(10))
    return None


def rsidonus(g):
    t = g.t
    r = _rsi(g)
    if r[t] > 30 and r[t - 1] <= 30:
        return _sonuc(g.dip(10), "rsidonus", olcu=g.c[t] - g.dip(10))
    return None


def rsi2(g):
    t = g.t
    r = _rsi(g, 2)
    if r[t] < 15 and g.c[t] > _sma(g, 200)[t]:
        return _sonuc(_stop2atr(g), "rsi2", olcu=2.0 * g.atr[t])
    return None


def uyumsuz(g):
    """Boga uyumsuzlugu: D1,D2 pivot dip (5-50 mum arayla), fiyat dusuk dip / RSI yuksek dip; t = D2+2 ve c > h[D2]."""
    t, h, l, c = g.t, g.h, g.l, g.c
    _, LI = g.pivotlar()
    if len(LI) < 2 or int(LI[-1]) != t - 2:
        return None
    d1, d2 = int(LI[-2]), int(LI[-1])
    r = _rsi(g)
    if not (5 <= d2 - d1 <= 50 and l[d2] < l[d1] and r[d2] > r[d1] and c[t] > h[d2]):
        return None
    hedef = h[d1:d2 + 1].max()
    return _sonuc(l[d2], "uyumsuz", hedef=hedef if hedef > c[t] else None, seviye=hedef, olcu=c[t] - l[d2], yas=d2 - d1)


def hizlima(g):
    t = g.t
    if _kes_yukari(_ema(g, 4), _ema(g, 9), t):
        return _sonuc(_stop2atr(g), "hizlima", olcu=2.0 * g.atr[t])
    return None


def bollkir(g):
    t = g.t
    m, _alt, ust = _boll(g)
    mc, ms, _ = _macd(g)
    if g.c[t] > ust[t] and g.c[t - 1] <= ust[t - 1] and mc[t] > ms[t]:
        return _sonuc(m[t], "bollkir", olcu=g.c[t] - m[t])
    return None


def _bulut_ust(g):
    _tk, _kj, sa, sb = _ichi(g)
    return np.maximum(sa, sb)


def tk(g):
    t = g.t
    tn, kj, _sa, _sb = _ichi(g)
    if _kes_yukari(tn, kj, t) and g.c[t] > _bulut_ust(g)[t]:
        return _sonuc(kj[t], "tk", olcu=g.c[t] - kj[t])
    return None


def kumo(g):
    t = g.t
    ust = _bulut_ust(g)
    if g.c[t] > ust[t] and g.c[t - 1] <= ust[t - 1]:
        _tn, kj, sa, sb = _ichi(g)
        stop = kj[t] if kj[t] < g.c[t] else min(sa[t], sb[t])
        return _sonuc(stop, "kumo", olcu=g.c[t] - stop)
    return None


def hacim(g):
    t = g.t
    v = g.v
    if v is None or t < 21:
        return None
    ort = v[t - 20:t].mean()
    if v[t] >= 2.0 * ort and ort > 0 and g.c[t] > g.h[t - 20:t].max() and g.c[t] > g.o[t]:
        return _sonuc(g.l[t], "hacim", olcu=g.c[t] - g.l[t])
    return None


def vwap(g):
    t = g.t
    w = _vwap(g)
    if w is None:
        return None
    if g.c[t] > w[t] and g.c[t - 1] <= w[t - 1]:
        return _sonuc(_stop2atr(g), "vwap", seviye=w[t], olcu=2.0 * g.atr[t])
    return None


def fibo(g):
    t, h, l, c, o = g.t, g.h, g.l, g.c, g.o
    HI, LI = g.pivotlar()
    if len(HI) < 1:
        return None
    b = int(HI[-1])
    onc = LI[LI < b]
    if len(onc) == 0:
        return None
    a = int(onc[-1])
    H = h[b] - l[a]
    if not H >= 3 * g.atr[t]:
        return None
    seviye = h[b] - 0.5 * H
    if not (l[t] <= seviye and c[t] >= h[b] - 0.618 * H and c[t] > o[t]):
        return None
    if (l[b + 1:t] <= seviye).any():                       # B'den beri ilk temas degil
        return None
    return _sonuc(h[b] - 0.786 * H, "fibo", hedef=h[b], seviye=seviye, olcu=H, yas=t - b)


def mageri(g):
    t, l, c, o = g.t, g.l, g.c, g.o
    e20, e50 = _ema(g, 20), _ema(g, 50)
    if not (e20[t] > e50[t] and c[t] > e50[t] and l[t] <= e20[t] and c[t] > e20[t] and c[t] > o[t]):
        return None
    if t >= 5 and (l[t - 5:t] > e20[t - 5:t]).all():
        return _sonuc(l[t], "mageri", seviye=e20[t], olcu=c[t] - l[t])
    return None


# ------------------------------------------------------------------------------------------------ kural cikislari
def _cikis_gorunum(inp: ArmInput):
    ham = ortak(inp)
    return ham.gorunum("short" if inp.side == "short" else "long")


def _kural(fn):
    """`fn(g, t) -> bool` kuralini ArmInput'a (acik pozisyonun yonu `inp.side`) baglar; son kapanmis mum."""
    def cikis(inp: ArmInput):
        g = _cikis_gorunum(inp)
        return bool(fn(g, g.t))
    cikis.fn = fn                           # ML1: kural fonksiyonu disaridan okunabilsin (davranis ayni)
    return cikis


def _c_rsi(g, t):
    return _rsi(g)[t] > 70


def _c_mak(g, t):
    return _sma(g, 50)[t] < _sma(g, 200)[t]


def _c_boll(g, t):
    return g.h[t] >= _boll(g)[0][t - 1]


def _c_fma(g, t):
    return g.c[t] < _sma(g, 50)[t]


def _c_macd(g, t):
    m, s, _ = _macd(g)
    return m[t] < s[t]


def _c_stok(g, t):
    return _stok(g)[0][t] > 80


def _c_rsi2(g, t):
    return _rsi(g, 2)[t] > 85


def _c_hizli(g, t):
    return _ema(g, 4)[t] < _ema(g, 9)[t]


def _c_bkir(g, t):
    return g.c[t] < _boll(g)[0][t]


def _c_tk(g, t):
    tn, kj, _a, _b = _ichi(g)
    return tn[t] < kj[t] or g.c[t] < kj[t]


def _c_kumo(g, t):
    return g.c[t] < _ichi(g)[1][t]


def _c_vwap(g, t):
    w = _vwap(g)
    return w is not None and g.c[t] < w[t]


_TF = TIMEFRAMES
_TF_KISA = ("15m", "1h")
FORMASYONLAR = {
    "UYUMSUZ": Formasyon("UYUMSUZ", "Gosterge: RSI uyumsuzlugu", 1, _TF, 48, uyumsuz),
    "MAKESISIM": Formasyon("MAKESISIM", "Gosterge: SMA50/200 kesisimi", 2, _TF, 48, makesisim, _kural(_c_mak)),
    "KUMO": Formasyon("KUMO", "Gosterge: bulut ustu kirilimi", 3, _TF, 48, kumo, _kural(_c_kumo)),
    "TK": Formasyon("TK", "Gosterge: tenkan/kijun kesisimi", 4, _TF, 48, tk, _kural(_c_tk)),
    "FIBO": Formasyon("FIBO", "Gosterge: fibonacci geri cekilme", 5, _TF, 48, fibo),
    "HACIM": Formasyon("HACIM", "Gosterge: hacimli kirilim", 6, _TF, 48, hacim),
    "RSI": Formasyon("RSI", "Gosterge: RSI 30 donusu", 7, _TF, 48, rsi, _kural(_c_rsi)),
    "RSIDONUS": Formasyon("RSIDONUS", "Gosterge: RSI 30 ustune donus", 8, _TF, 48, rsidonus, _kural(_c_rsi)),
    "RSI2": Formasyon("RSI2", "Gosterge: RSI(2) dip", 9, _TF, 48, rsi2, _kural(_c_rsi2)),
    "STOK": Formasyon("STOK", "Gosterge: stokastik kesisimi", 10, _TF, 48, stok, _kural(_c_stok)),
    "MACD": Formasyon("MACD", "Gosterge: MACD kesisimi", 11, _TF, 48, macd, _kural(_c_macd)),
    "MAGERI": Formasyon("MAGERI", "Gosterge: EMA20 geri cekilmesi", 12, _TF, 48, mageri),
    "BOLLKIR": Formasyon("BOLLKIR", "Gosterge: Bollinger ust bant kirilimi", 13, _TF, 48, bollkir, _kural(_c_bkir)),
    "VWAP": Formasyon("VWAP", "Gosterge: VWAP ustune gecis", 14, _TF_KISA, 48, vwap, _kural(_c_vwap)),
    "FIYATMA": Formasyon("FIYATMA", "Gosterge: fiyat SMA50 ustune gecis", 15, _TF, 48, fiyatma, _kural(_c_fma)),
    "HIZLIMA": Formasyon("HIZLIMA", "Gosterge: EMA4/EMA9 kesisimi", 16, _TF, 48, hizlima, _kural(_c_hizli)),
    "BOLL": Formasyon("BOLL", "Gosterge: Bollinger alt bant donusu", 17, _TF, 48, boll, _kural(_c_boll)),
}


def compute(kod: str, inp: ArmInput):
    return hesapla(SETUP, FORMASYONLAR, kod, inp)
