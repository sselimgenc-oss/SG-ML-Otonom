"""v3 (12 kitap setupu) testleri: her setup icin sentetik ornekte beklenen sinyal (+ olumsuz ornek), ileriye bakis, simulasyon_v3 kurallari, kosu. Hepsi gecmeli."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calistir as CA  # noqa: E402
import gostergeler as G  # noqa: E402
import setuplar_v3 as SV  # noqa: E402
import simulasyon_v3 as S3  # noqa: E402
import v3_kos as K3  # noqa: E402

H = 3600 * 10**9
T0 = 19702 * 86400 * 10**9
MAL0 = (0.0, 0.0, 0.0, 0.0)
KODLAR = list(SV.SETUPLAR)


# ------------------------------------------------------------------------------------------------ yardimcilar
class Seri:
    """Mum dizisi kurucusu. Taban: o=c=100, h = 100.5 - 0.001 i (kesin azalan -> taban pivot tepe uretmez), l = 99.5 + 0.001 i (kesin artan -> pivot dip yok)."""

    def __init__(self, n):
        i = np.arange(n, dtype=float)
        self.o, self.c = np.full(n, 100.0), np.full(n, 100.0)
        self.h, self.l = 100.5 - 0.001 * i, 99.5 + 0.001 * i

    def mum(self, i, o, h, l, c):
        self.o[i], self.h[i], self.l[i], self.c[i] = o, h, l, c
        return self

    def d(self):
        n = len(self.o)
        return {"t": T0 + np.arange(n, dtype="int64") * H, "o": self.o.copy(), "h": self.h.copy(), "l": self.l.copy(), "c": self.c.copy(), "v": np.ones(n)}


def aynala(D, K=200.0):
    return {"t": D["t"], "o": K - D["o"], "h": K - D["l"], "l": K - D["h"], "c": K - D["c"], "v": D["v"]}


def fd(D):
    return {1: SV.ozellik(D, 1), -1: SV.ozellik(D, -1)}


def sinyal(kod, D):
    return SV.gercek_sinyaller(kod, fd(D))


def ts(sig, d=None):
    return [x[0] for x in sig if d is None or x[1] == d]


def al(sig, t, d=1):
    r = [x for x in sig if x[0] == t and x[1] == d]
    assert len(r) == 1, f"t={t} d={d} icin {len(r)} sinyal; var olanlar: {[(x[0], x[1]) for x in sig]}"
    return r[0]


# ------------------------------------------------------------------------------------------------ sabit ornekler (long)
def pin_ornegi(ust=0.05):
    s = Seri(60)
    for i in range(30):                                  # yavas dusus: dipler azalir
        c = 100 - 0.3 * (i + 1)
        s.mum(i, c + 0.3, c + 0.4, c - 0.1, c)
    s.mum(30, 90.4, 90.6 + ust, 88.0, 90.6)               # pin bar: alt golge 2.4 >= 2*gövde(0.2); dip 10 mumun en dusugu
    return s.d()


def ic_taban(n=60):
    s = Seri(n)
    s.l = 99.5 - 0.001 * np.arange(n)                        # h de l de azalir -> taban ic mum uretmez
    return s


def ic_ornegi():
    s = ic_taban()
    s.mum(20, 100, 102, 98, 99)                          # ana mum
    s.mum(21, 99.5, 101, 99, 100)                        # ic mum
    s.mum(22, 100, 101.5, 99.5, 100)                     # 22 ic mum degil (21'in ustune tasar)
    return s.d()


def yutan_ornegi():
    s = Seri(60)
    for i in range(26, 30):
        s.mum(i, 96, 96.2, 95.8, 96)
    s.mum(30, 95.0, 95.1, 93.4, 93.5)                    # dusus mumu, dibi son 5'in en dusugu
    s.mum(31, 93.4, 95.4, 93.3, 95.3)                    # yutan: o <= 93.5, c >= 95.0
    return s.d()


def yildiz_ornegi():
    s = Seri(60)
    s.mum(30, 100, 100.1, 97.9, 98.0)                    # %2 dusus; dibi onceki mumun dibinden dusuk
    s.mum(31, 97.8, 98.0, 97.7, 97.9)                    # govde %0.1, govde tepesi 97.9 <= 98.0
    s.mum(32, 98.0, 99.6, 97.95, 99.5)                   # kapanis 99.5 > (100+98)/2
    return s.d()


def yatay_ornegi(ikinci=104.5, kirilim=105.5):
    s = Seri(90)
    s.mum(30, 100, 105.0, 99.9, 100.3)
    s.mum(40, 100, s.h[40], 98.0, 100)                   # aralik dibi
    s.mum(50, 100, ikinci, 99.9, 100.3)
    s.mum(70, 100, kirilim + 0.1, 99.9, kirilim)
    return s.d()


def ucgen_yukselen():
    s = Seri(90)
    s.mum(30, 100, 105.0, 99.9, 100.3)
    s.mum(33, 100, s.h[33], 98.0, 100)
    s.mum(45, 100, s.h[45], 99.0, 100)
    s.mum(50, 100, 104.8, 99.9, 100.3)
    s.mum(70, 100, 105.6, 99.9, 105.5)
    return s.d()


def ucgen_simetrik():
    s = Seri(90)
    s.mum(30, 100, 105.0, 99.9, 100.3)
    s.mum(33, 100, s.h[33], 98.0, 100)
    s.mum(45, 100, s.h[45], 99.0, 100)
    s.mum(50, 100, 103.0, 99.9, 100.3)
    s.mum(60, 100, 102.6, 99.9, 102.5)
    return s.d()


def ikili_ornegi(ikinci=95.5):
    s = Seri(90)
    s.mum(30, 100, s.h[30], 95.0, 100)
    s.mum(37, 100, 100.8, 99.9, 100)                     # boyun
    s.mum(44, 100, s.h[44], ikinci, 100)
    s.mum(60, 100, 101.1, 99.9, 101.0)
    return s.d()


def obo_ornegi(onceki=True):
    s = Seri(100)
    if onceki:
        s.mum(5, 100, 118.0, 99.9, 100)                  # sol omuzdan onceki hareket
    s.mum(30, 100, s.h[30], 95.0, 100)                   # sol omuz
    s.mum(37, 100, 101.0, 99.9, 100)
    s.mum(45, 100, s.h[45], 90.0, 100)                   # bas
    s.mum(52, 100, 101.2, 99.9, 100)
    s.mum(60, 100, s.h[60], 95.5, 100)                   # sag omuz
    s.mum(75, 100, 102.1, 99.9, 102.0)
    return s.d()


def rsi_ornegi(yukselis=True):
    n = 330
    c = 100 + (0.2 if yukselis else -0.2) * np.arange(n)
    c[260:] = c[259] - 1.5 * np.arange(1, n - 259)
    o = np.r_[c[0], c[:-1]]
    return {"t": T0 + np.arange(n, dtype="int64") * H, "o": o, "h": np.maximum(o, c) + 0.1, "l": np.minimum(o, c) - 0.1, "c": c, "v": np.ones(n)}


def ma_ornegi():
    n = 400
    c = np.r_[np.linspace(200, 100, 250), np.linspace(100, 160, 150)]
    o = np.r_[c[0], c[:-1]]
    return {"t": T0 + np.arange(n, dtype="int64") * H, "o": o, "h": np.maximum(o, c) + 0.2, "l": np.minimum(o, c) - 0.2, "c": c, "v": np.ones(n)}


def boll_ornegi():
    n = 80
    c = 100 + np.sin(np.arange(n) * 0.7)
    o = np.r_[c[0], c[:-1]]
    h, l = np.maximum(o, c) + 0.1, np.minimum(o, c) - 0.1
    o[50], c[50], h[50], l[50] = 100.0, 99.5, 100.1, 96.0
    return {"t": T0 + np.arange(n, dtype="int64") * H, "o": o, "h": h, "l": l, "c": c, "v": np.ones(n)}


def fiyat_ma_ornegi():
    n = 200
    c = np.r_[np.linspace(120, 90, 100), np.linspace(90, 130, 100)]
    o = np.r_[c[0], c[:-1]]
    return {"t": T0 + np.arange(n, dtype="int64") * H, "o": o, "h": np.maximum(o, c) + 0.1, "l": np.minimum(o, c) - 0.1, "c": c, "v": np.ones(n)}


# ================================================================================================ 1. PINBAR
def test_pinbar_sinyal_stop_hedef_ve_olumsuz():
    D = pin_ornegi()
    x = al(sinyal("MUM_PINBAR", D), 30)
    c = 90.6
    assert x[2]["stop"] == pytest.approx(88.0)
    assert x[2]["hedef"] == pytest.approx(c + 2 * (c - 88.0))
    assert SV.kategori("MUM_PINBAR") == "MF1" and SV.SETUPLAR["MUM_PINBAR"][1] == 48
    assert 30 not in ts(sinyal("MUM_PINBAR", pin_ornegi(ust=0.5)))        # ust golge >= %10 -> yok
    s = Seri(60)
    for i in range(30):
        s.mum(i, 100 - 0.3 * i, 100.4 - 0.3 * i, 99.9 - 0.3 * i, 99.7 - 0.3 * i)
    s.mum(25, 92.5, 92.6, 85.0, 92.5)                      # daha dusuk dip onceden var -> pin bar dibi 10 mumun en dusugu degil
    s.mum(30, 90.4, 90.65, 88.0, 90.6)
    assert 30 not in ts(sinyal("MUM_PINBAR", s.d()))


def test_pinbar_short_ayna():
    D = aynala(pin_ornegi())
    x = al(sinyal("MUM_PINBAR", D), 30, -1)
    assert x[2]["stop"] == pytest.approx(200 - 88.0)
    assert x[2]["hedef"] == pytest.approx(200 - 90.6 - 2 * (90.6 - 88.0))


# ================================================================================================ 2. IC CUBUK
def test_ic_cubuk_emirler_ve_dolum():
    D = ic_ornegi()
    sig = sinyal("MUM_IC_CUBUK", D)
    u = al(sig, 21, 1)
    assert u[2]["emir"] == pytest.approx(102.0) and u[2]["stop"] == pytest.approx(98.0) and u[2]["hedef"] == pytest.approx(110.0) and u[2]["pencere"] == 2
    k = al(sig, 21, -1)
    assert k[2]["emir"] == pytest.approx(98.0) and k[2]["stop"] == pytest.approx(102.0) and k[2]["hedef"] == pytest.approx(90.0)
    assert 22 not in ts(sig)
    # dolum: t+1 ve t+2 gecerli; sonrasi yok; bosluk acilistan
    S = D
    S["h"][22], S["l"][22] = 101.0, 99.0
    S["h"][23], S["l"][23] = 102.5, 99.5
    assert S3.emir_dolum(S, 21, 1, 102.0, 2, H) == (23, 102.0)
    S["h"][23] = 101.5
    assert S3.emir_dolum(S, 21, 1, 102.0, 2, H) is None
    S["o"][22], S["h"][22] = 103.0, 103.5
    assert S3.emir_dolum(S, 21, 1, 102.0, 2, H) == (22, 103.0)
    S["o"][22], S["l"][22] = 97.0, 96.5
    assert S3.emir_dolum(S, 21, -1, 98.0, 2, H) == (22, 97.0)
    # ic mum degil (tasan) -> emir yok
    s = ic_taban()
    s.mum(20, 100, 102, 98, 99)
    s.mum(21, 99.5, 102.5, 99, 100)
    assert 21 not in ts(sinyal("MUM_IC_CUBUK", s.d()))


def test_ic_cubuk_oco_ilk_dolan_ve_ayni_mumda_stop():
    D = ic_ornegi()
    D["o"][22], D["h"][22], D["l"][22], D["c"][22] = 100.0, 102.4, 99.0, 102.2      # yukari emir dolar; asagi (98) dolmaz
    for i in range(23, 40):
        D["h"][i], D["l"][i], D["c"][i], D["o"][i] = 109.9, 108.0, 109.0, 109.0
    D["h"][24] = 110.5                                                             # hedef 110
    sig = sinyal("MUM_IC_CUBUK", D)
    sig = [x for x in sig if x[0] == 21]
    sayac = {"acik_atlanan": 0, "sim_yok": 0}
    rows = K3.islem_dongusu_v3(D, sig, 48, MAL0, H, None, 0, 0.0, sayac)
    assert len(rows) == 1 and rows[0][6] == 1 and rows[0][1] == 1                   # long, hedef
    assert rows[0][0] == pytest.approx(2.0)                                         # R: giris 102, stop 98, hedef 110 -> (110-102)/4
    # ayni mumda iki emir de tetiklenir -> stop (-1R)
    E = ic_ornegi()
    E["o"][22], E["h"][22], E["l"][22], E["c"][22] = 100.0, 102.5, 97.5, 100.0
    sig = [x for x in sinyal("MUM_IC_CUBUK", E) if x[0] == 21]
    rows = K3.islem_dongusu_v3(E, sig, 48, MAL0, H, None, 0, 0.0, {"acik_atlanan": 0, "sim_yok": 0})
    assert len(rows) == 1 and rows[0][1] == 0 and rows[0][0] == pytest.approx(-1.0)


# ================================================================================================ 3. YUTAN
def test_yutan_sinyal_ve_olumsuz():
    D = yutan_ornegi()
    x = al(sinyal("MUM_YUTAN", D), 31)
    assert x[2]["stop"] == pytest.approx(93.3) and x[2]["hedef"] == pytest.approx(95.3 + 2 * (95.3 - 93.3))
    E = yutan_ornegi()
    E["o"][31] = 93.7                                       # o > onceki kapanis -> tam yutmuyor (kitap: acilis <= onceki kapanis)
    assert 31 not in ts(sinyal("MUM_YUTAN", E))
    F = yutan_ornegi()
    F["l"][28] = 93.0                                       # onceki mumun dibi son 5'in en dusugu degil
    assert 31 not in ts(sinyal("MUM_YUTAN", F))
    assert 31 in ts(sinyal("MUM_YUTAN", aynala(yutan_ornegi())), -1)


# ================================================================================================ 4. YILDIZ
def test_yildiz_sinyal_yuzde_stop_hedef_ve_zaman():
    D = yildiz_ornegi()
    x = al(sinyal("MUM_YILDIZ", D), 32)
    assert x[2]["stop"] == pytest.approx(99.5 * 0.97) and x[2]["hedef"] == pytest.approx(99.5 * 1.09)
    assert SV.SETUPLAR["MUM_YILDIZ"][1] == 20
    for ad, deger in (("c1", (30, "c", 98.6)), ("govde", (31, "c", 98.5)), ("kapanis", (32, "c", 98.9))):
        E = yildiz_ornegi()
        E[deger[1]][deger[0]] = deger[2]
        assert 32 not in ts(sinyal("MUM_YILDIZ", E)), ad
    assert 32 in ts(sinyal("MUM_YILDIZ", aynala(yildiz_ornegi(), 200.0)), -1)


# ================================================================================================ 5. YATAY
def test_yatay_kirilim_seviye_stop_hedef():
    D = yatay_ornegi()
    x = al(sinyal("FOR_YATAY_KIRILIM", D), 70)
    assert x[2]["stop"] == pytest.approx(99.9)              # min(seviye, kirilim mumu dibi)
    assert x[2]["hedef"] == pytest.approx(105.0 + (105.0 - 98.0))
    assert 70 not in ts(sinyal("FOR_YATAY_KIRILIM", yatay_ornegi(ikinci=110.0)))      # tepeler %3'ten uzak
    E = yatay_ornegi()
    E["c"][60] = 105.2                                      # daha once kapanisla kirilmis
    assert 70 not in ts(sinyal("FOR_YATAY_KIRILIM", E))
    assert 70 not in ts(sinyal("FOR_YATAY_KIRILIM", yatay_ornegi(kirilim=104.9)))    # seviyenin ustunde kapanis yok
    assert 70 in ts(sinyal("FOR_YATAY_KIRILIM", aynala(yatay_ornegi())), -1)


def test_yatay_pivot_onay_gecikmesi():
    """Pivot 2 mum sonra kullanilir: ikinci tepe i=50 ise kirilim en erken 52 kapanisinda olabilir."""
    D = yatay_ornegi()
    D["o"][51], D["c"][51], D["h"][51] = 100, 105.4, 105.45   # i=50'den hemen sonra kapanis seviyenin ustunde, ama pivot henuz bilinmiyor/kesin degil
    D["c"][70], D["h"][70] = 100, 100.5
    assert 51 not in ts(sinyal("FOR_YATAY_KIRILIM", D))


# ================================================================================================ 6. UCGEN
def test_ucgen_yukselen_stop_hedef():
    x = al(sinyal("FOR_UCGEN", ucgen_yukselen()), 70)
    assert x[5] == "yukselen"
    assert x[2]["stop"] == pytest.approx(99.0)              # kirilimdan onceki son onayli pivot dip
    assert x[2]["hedef"] == pytest.approx(105.0 + (105.0 - 98.0))     # en genis yer = ilk tepe - ilk dip
    D = ucgen_yukselen()
    D["l"][45] = 97.5                                        # dipler yukselmiyor (98 -> 97.5)
    assert 70 not in ts(sinyal("FOR_UCGEN", D))
    assert al(sinyal("FOR_UCGEN", aynala(ucgen_yukselen())), 70, -1)[5] == "alcalan"


def test_ucgen_simetrik_cizgi_kirilimi():
    D = ucgen_simetrik()
    x = al(sinyal("FOR_UCGEN", D), 60)
    assert x[5] == "simetrik"
    U60 = 105.0 - 0.1 * 30
    assert x[2]["stop"] == pytest.approx(99.0)
    assert x[2]["hedef"] == pytest.approx(U60 + (105.0 - 98.0))
    E = ucgen_simetrik()
    E["c"][60] = 101.5                                       # ust cizginin (102) icinde -> yok
    assert 60 not in ts(sinyal("FOR_UCGEN", E))
    F = ucgen_simetrik()
    F["h"][50] = 106.0                                       # tepeler yukseliyor -> simetrik degil
    assert 60 not in ts(sinyal("FOR_UCGEN", F))


# ================================================================================================ 7. IKILI DIP
def test_ikili_dip_boyun_stop_hedef():
    x = al(sinyal("FOR_IKILI_DIP", ikili_ornegi()), 60)
    assert x[2]["stop"] == pytest.approx(95.0)
    assert x[2]["hedef"] == pytest.approx(100.8 + (100.8 - 95.0))
    assert 60 not in ts(sinyal("FOR_IKILI_DIP", ikili_ornegi(ikinci=92.0)))          # dipler %3'ten uzak
    assert al(sinyal("FOR_IKILI_DIP", aynala(ikili_ornegi())), 60, -1)[5] == "ikili_tepe"
    k = Seri(90)
    k.mum(30, 100, k.h[30], 95.0, 100)
    k.mum(33, 100, 100.8, 99.9, 100)
    k.mum(41, 100, k.h[41], 95.5, 100)                       # 41-30 = 11 ... mesafe 5-25 icinde -> gecerli
    k.mum(60, 100, 101.1, 99.9, 101.0)
    assert 60 in ts(sinyal("FOR_IKILI_DIP", k.d()))
    u = Seri(120)
    u.mum(30, 100, u.h[30], 95.0, 100)
    u.mum(40, 100, 100.8, 99.9, 100)
    u.mum(58, 100, u.h[58], 95.5, 100)                       # 28 mum arayla (> 25) -> yok
    u.mum(80, 100, 101.1, 99.9, 101.0)
    assert 80 not in ts(sinyal("FOR_IKILI_DIP", u.d()))


# ================================================================================================ 8. OBO
def test_tobo_ve_obo_stop_hedef_ve_trend_sarti():
    D = obo_ornegi()
    x = al(sinyal("FOR_OBO", D), 75)
    egim = (101.2 - 101.0) / 15
    boyun75 = 101.0 + egim * (75 - 37)
    D_ = (101.0 + egim * (45 - 37)) - 90.0
    assert x[5] == "tobo" and x[2]["stop"] == pytest.approx(90.0)
    assert x[2]["hedef"] == pytest.approx(boyun75 + D_)
    assert 75 not in ts(sinyal("FOR_OBO", obo_ornegi(onceki=False)))                # onceki hareket < 2 * bas-boyun
    assert al(sinyal("FOR_OBO", aynala(obo_ornegi())), 75, -1)[5] == "obo"
    E = obo_ornegi()
    E["l"][60] = 92.0                                         # omuzlar arasi fark > %3
    assert 75 not in ts(sinyal("FOR_OBO", E))
    F = obo_ornegi()
    F["l"][45] = 96.0                                         # bas en dusuk degil
    assert 75 not in ts(sinyal("FOR_OBO", F))


# ================================================================================================ 9. RSI
def test_rsi_30_ilk_mum_sma_filtresi_stop_ve_cikis():
    D = rsi_ornegi(True)
    F = SV.ozellik(D, 1)
    rsi = G.rsi(D["c"], 14)
    ilk = int(np.flatnonzero((rsi < 30) & (np.r_[np.nan, rsi[:-1]] >= 30))[0])
    sig = sinyal("IND_RSI_3070", D)
    x = al(sig, ilk)
    assert x[2]["stop"] == pytest.approx(D["l"][ilk - 9:ilk + 1].min())
    assert x[2]["hedef"] is None and x[2]["cx"].dtype == bool
    assert [t for t in ts(sig, 1) if t < 330][0] == ilk
    assert (x[2]["cx"] == (rsi > 70)).all()
    assert ts(sinyal("IND_RSI_3070", rsi_ornegi(False)), 1) == []       # SMA50 < SMA200 -> long yok
    assert ts(sig, -1) == []                                           # RSI hic 70'in ustune cikmadi


def test_rsi_short_ayna_ve_filtre():
    D = aynala(rsi_ornegi(True), 1000.0)
    sig = sinyal("IND_RSI_3070", D)
    assert ts(sig, 1) == []
    assert len(ts(sig, -1)) >= 1


# ================================================================================================ 10. MA KESISIM
def test_ma_kesisim_ve_ters_kesisim_cikisi():
    D = ma_ornegi()
    c = D["c"]
    a = np.convolve(c, np.ones(50) / 50, "valid")
    b = np.convolve(c, np.ones(200) / 200, "valid")
    A, B = np.r_[np.full(49, np.nan), a], np.r_[np.full(199, np.nan), b]
    with np.errstate(invalid="ignore"):
        beklenen = np.flatnonzero((A > B) & (np.r_[np.nan, A[:-1]] <= np.r_[np.nan, B[:-1]]))
    sig = sinyal("IND_MA_KESISIM", D)
    assert ts(sig, 1) == beklenen.tolist() and len(beklenen) == 1
    x = al(sig, int(beklenen[0]))
    assert x[2]["stop"] is None and x[2]["hedef"] is None
    assert x[2]["rbirim"] == pytest.approx(2 * G.atr(D["h"], D["l"], c, 14)[beklenen[0]])
    assert SV.SETUPLAR["IND_MA_KESISIM"][1] == 48
    # ters kesisim = cikis: asagi kesisim olan bar isaretli
    E = ma_ornegi()
    E["c"][335:] = np.linspace(E["c"][334], 60, 65)
    E["o"][335:] = np.r_[E["c"][334], E["c"][335:-1]]
    E["h"], E["l"] = np.maximum(E["o"], E["c"]) + 0.2, np.minimum(E["o"], E["c"]) - 0.2
    x = al(sinyal("IND_MA_KESISIM", E), int(beklenen[0]))
    assert x[2]["cx"].any() and np.flatnonzero(x[2]["cx"])[0] > beklenen[0]
    assert len(ts(sinyal("IND_MA_KESISIM", aynala(D, 400.0)), -1)) == 1


# ================================================================================================ 11. BOLLINGER
def test_boll_dokunus_stop_ve_dinamik_orta_bant():
    D = boll_ornegi()
    c = D["c"]
    s20 = np.mean(c[31:51], axis=0)
    sd = np.std(c[31:51])
    assert D["l"][50] <= s20 - 2 * sd
    sig = sinyal("IND_BOLL_DONUS", D)
    x = al(sig, 50)
    assert x[2]["stop"] == pytest.approx(96.0) and x[2]["hedef"] is None
    assert x[2]["hd"][51] == pytest.approx(s20)               # bar 51 icin emir seviyesi = 50'nin kapanisindaki orta bant
    assert x[2]["hd"][52] == pytest.approx(np.mean(c[32:52]))  # her mumda guncel
    E = boll_ornegi()
    E["l"][50] = 99.0
    assert 50 not in ts(sinyal("IND_BOLL_DONUS", E), 1)
    short = al(sinyal("IND_BOLL_DONUS", aynala(boll_ornegi(), 200.0)), 50, -1)
    assert short[2]["stop"] == pytest.approx(200 - 96.0)


# ================================================================================================ 12. FIYAT-MA
def test_fiyat_ma_kesisim_ve_cikis():
    D = fiyat_ma_ornegi()
    c = D["c"]
    s = np.r_[np.full(49, np.nan), np.convolve(c, np.ones(50) / 50, "valid")]
    with np.errstate(invalid="ignore"):
        beklenen = np.flatnonzero((c > s) & (np.r_[np.nan, c[:-1]] <= np.r_[np.nan, s[:-1]]))
    sig = sinyal("IND_FIYAT_MA", D)
    assert ts(sig, 1) == beklenen.tolist() and len(beklenen) >= 1
    x = al(sig, int(beklenen[0]))
    assert x[2]["stop"] is None and x[2]["hedef"] is None
    with np.errstate(invalid="ignore"):
        assert (x[2]["cx"] == (c < s)).all()
    assert len(ts(sinyal("IND_FIYAT_MA", aynala(D, 400.0)), -1)) == len(beklenen)


# ================================================================================================ kimlik / kategori
def test_12_setup_kimlik_ve_kategori():
    assert len(KODLAR) == 12
    kat = {k: SV.kategori(k) for k in KODLAR}
    assert sorted(set(kat.values())) == ["GF1", "IN1", "MF1"]
    assert [k for k in KODLAR if kat[k] == "MF1"] == ["MUM_PINBAR", "MUM_IC_CUBUK", "MUM_YUTAN", "MUM_YILDIZ"]
    assert [k for k in KODLAR if kat[k] == "GF1"] == ["FOR_YATAY_KIRILIM", "FOR_UCGEN", "FOR_IKILI_DIP", "FOR_OBO"]
    assert [k for k in KODLAR if kat[k] == "IN1"] == ["IND_RSI_3070", "IND_MA_KESISIM", "IND_BOLL_DONUS", "IND_FIYAT_MA"]


def test_pivot_sol10_sag2_kesin():
    l = np.r_[np.full(10, 5.0), 3.0, 4.0, 4.5, np.full(5, 6.0)]
    assert np.flatnonzero(SV.pivot_dip_kesin(l)).tolist() == [10]
    l2 = l.copy()
    l2[0] = 3.0                                               # sol 10 mumdan biri esit -> pivot degil (kesin esitsizlik)
    assert np.flatnonzero(SV.pivot_dip_kesin(l2)).tolist() == []
    l3 = l.copy()
    l3[12] = 3.0                                              # sag 2'den biri esit -> pivot degil
    assert np.flatnonzero(SV.pivot_dip_kesin(l3)).tolist() == []
    l4 = np.r_[np.full(9, 5.0), 3.0, 4.0, 4.5, np.full(5, 6.0)]        # solda yalniz 9 mum -> yok
    assert np.flatnonzero(SV.pivot_dip_kesin(l4)).tolist() == []


# ================================================================================================ ileriye bakis
ORNEKLER = {
    "MUM_PINBAR": (pin_ornegi, 30), "MUM_IC_CUBUK": (ic_ornegi, 21), "MUM_YUTAN": (yutan_ornegi, 31), "MUM_YILDIZ": (yildiz_ornegi, 32),
    "FOR_YATAY_KIRILIM": (yatay_ornegi, 70), "FOR_UCGEN": (ucgen_yukselen, 70), "FOR_IKILI_DIP": (ikili_ornegi, 60), "FOR_OBO": (obo_ornegi, 75),
    "IND_RSI_3070": (rsi_ornegi, None), "IND_MA_KESISIM": (ma_ornegi, None), "IND_BOLL_DONUS": (boll_ornegi, 50), "IND_FIYAT_MA": (fiyat_ma_ornegi, None),
}


def _gelecegi_boz(D, bas, tohum=11):
    rg = np.random.default_rng(tohum)
    E = {k: v.copy() for k, v in D.items()}
    n = len(E["t"]) - bas
    kat = 1 + rg.normal(0.1, 0.15, n)
    for k in ("o", "h", "l", "c"):
        E[k][bas:] = E[k][bas:] * kat
    E["h"][bas:] = np.maximum.reduce([E["h"][bas:], E["o"][bas:], E["c"][bas:]]) * 1.02
    E["l"][bas:] = np.minimum.reduce([E["l"][bas:], E["o"][bas:], E["c"][bas:]]) * 0.97
    return E


def _esit_sinyal(a, b):
    if (a[0], a[1], a[3], a[4], a[5]) != (b[0], b[1], b[3], b[4], b[5]) and not (np.isnan(a[3]) and np.isnan(b[3]) and (a[0], a[1]) == (b[0], b[1])):
        return False
    for k in ("stop", "hedef", "emir", "rbirim"):
        if a[2].get(k) != b[2].get(k):
            return False
    t = a[0]
    for k in ("hd", "cx"):
        if (k in a[2]) != (k in b[2]):
            return False
        if k in a[2] and not np.array_equal(a[2][k][:t + 1], b[2][k][:t + 1], equal_nan=True):
            return False
    return True


@pytest.mark.parametrize("kod", KODLAR)
def test_ileriye_bakis_sentetik_ornek(kod):
    fn, tb = ORNEKLER[kod]
    D = fn()
    n = len(D["t"])
    s1 = sinyal(kod, D)
    assert len(s1) > 0
    t_ref = tb if tb is not None else s1[0][0]
    assert t_ref in ts(s1)
    for tohum in (1, 2):
        E = _gelecegi_boz(D, t_ref + 1, tohum)
        s2 = sinyal(kod, E)
        a = [x for x in s1 if x[0] <= t_ref]
        b = [x for x in s2 if x[0] <= t_ref]
        assert len(a) == len(b) and len(a) > 0, kod
        assert all(_esit_sinyal(x, y) for x, y in zip(a, b)), kod


def _rastgele_seri(n, tohum):
    rg = np.random.default_rng(tohum)
    c = 100 * np.exp(np.cumsum(rg.normal(0, 0.008, n)))
    o = np.r_[c[0], c[:-1]]
    return {"t": T0 + np.arange(n, dtype="int64") * H, "o": o, "h": np.maximum(o, c) * (1 + rg.uniform(0, 0.006, n)),
            "l": np.minimum(o, c) * (1 - rg.uniform(0, 0.006, n)), "c": c, "v": rg.uniform(1, 3, n)}


def test_ileriye_bakis_rastgele_seri_tum_setuplar():
    n, t0 = 3000, 2200
    D = _rastgele_seri(n, 5)
    E = _gelecegi_boz(D, t0 + 1, 3)
    toplam = {}
    for kod in KODLAR:
        a = [x for x in sinyal(kod, D) if x[0] <= t0]
        b = [x for x in sinyal(kod, E) if x[0] <= t0]
        assert len(a) == len(b), kod
        assert all(_esit_sinyal(x, y) for x, y in zip(a, b)), kod
        toplam[kod] = len(a)
    assert sum(toplam.values()) > 100 and toplam["IND_BOLL_DONUS"] > 0 and toplam["MUM_IC_CUBUK"] > 0


def test_ozellikler_nedensel():
    D = _rastgele_seri(1500, 9)
    E = _gelecegi_boz(D, 1001, 4)
    for yon in (1, -1):
        A, B = SV.ozellik(D, yon), SV.ozellik(E, yon)
        for k, v in A.items():
            if isinstance(v, np.ndarray) and v.shape == (1500,):
                son = 1000 - 2 if k in ("piv_d", "piv_t") else 1001           # ham pivot i'de isaretli, i+2'de bilinir
                assert np.array_equal(v[:son], B[k][:son], equal_nan=True), k


# ================================================================================================ simulasyon_v3
def _S(o, h, l, c):
    n = len(o)
    return {"t": T0 + np.arange(n, dtype="int64") * H, "o": np.array(o, float), "h": np.array(h, float), "l": np.array(l, float), "c": np.array(c, float), "v": np.ones(n)}


def test_sim_ayni_mumda_stop_ve_hedef_stop():
    S = _S([100, 100, 100], [100, 111, 100], [100, 89, 100], [100, 100, 100])
    r = S3.simule_v3(S, 1, 100.0, 1, {"stop": 90.0, "hedef": 110.0}, 5, MAL0, H)
    assert r[1] == 0 and r[0] == pytest.approx(-1.0)


def test_sim_bosluk_dolumu_ve_hedef():
    S = _S([100, 100, 85, 100], [100, 101, 86, 101], [100, 99, 84, 99], [100, 100, 85, 100])
    r = S3.simule_v3(S, 1, 100.0, 1, {"stop": 90.0, "hedef": 120.0}, 5, MAL0, H)
    assert r[1] == 0 and r[0] == pytest.approx(-1.5)           # stop 90, acilis 85'ten dolum
    S = _S([100, 100, 125, 100], [100, 101, 126, 101], [100, 99, 124, 99], [100, 100, 125, 100])
    r = S3.simule_v3(S, 1, 100.0, 1, {"stop": 90.0, "hedef": 120.0}, 5, MAL0, H)
    assert r[1] == 1 and r[0] == pytest.approx(2.5)


def test_sim_sinyal_cikisi_ertesi_acilista_ve_ters_yone_gecis():
    cx = np.zeros(8, bool)
    cx[3] = True
    S = _S([100, 100, 101, 102, 104, 105, 105, 105], [101] * 8, [99] * 8, [100, 101, 102, 103, 104, 105, 105, 105])
    r = S3.simule_v3(S, 1, 100.0, 1, {"stop": None, "hedef": None, "rbirim": 4.0, "cx": cx}, 6, MAL0, H)
    assert r[1] == 3 and r[4] == 4 and r[0] == pytest.approx((104 - 100) / 4.0)       # bar 3 kapanisinda sinyal -> bar 4 acilisi
    assert r[6] == 3                                                                  # ayni acilista yeni karar (3. mum kapanisi) serbest
    # stop yoksa zaman stopu: kapanista
    r2 = S3.simule_v3(S, 1, 100.0, 1, {"stop": None, "hedef": None, "rbirim": 4.0}, 4, MAL0, H)
    assert r2[1] == 2 and r2[4] == 4 and r2[0] == pytest.approx((S["c"][4] - 100) / 4.0)


def test_sim_dinamik_hedef_her_mumda_guncel_ve_bosluk():
    hd = np.array([np.nan, 103.0, 101.5, 100.2, 100.2, 100.2])
    S = _S([100, 100, 99, 99, 99, 99], [100, 100.9, 101.4, 99.5, 99.5, 99.5], [100, 98.5, 98.5, 98.5, 98.5, 98.5], [100, 99, 99, 99, 99, 99])
    r = S3.simule_v3(S, 1, 100.0, 1, {"stop": 95.0, "hd": hd}, 5, MAL0, H)
    assert r[1] == 0 or r[1] == 2
    S2 = _S([100, 100, 99, 99, 99, 99], [100, 100.9, 101.6, 99.5, 99.5, 99.5], [100, 98.5, 98.5, 98.5, 98.5, 98.5], [100, 99, 99, 99, 99, 99])
    r = S3.simule_v3(S2, 1, 100.0, 1, {"stop": 95.0, "hd": hd}, 5, MAL0, H)
    assert r[1] == 1 and r[0] == pytest.approx((101.5 - 100.0) / 5.0) and r[4] == 2          # bar 2'nin emri 101.5, h=101.6 -> dolum
    hd2 = hd.copy()
    hd2[2] = 99.5                                            # seviye acilisin altinda: bosluk -> acilistan (99) degil, acilis 99 < 99.5 hedef dolmaz
    r = S3.simule_v3(S2, 1, 100.0, 1, {"stop": 95.0, "hd": hd2}, 5, MAL0, H)
    assert r[1] == 1                                         # h=101.6 >= 99.5 ve acilis 99 < 99.5 -> seviyeden dolum
    assert r[0] == pytest.approx((99.5 - 100.0) / 5.0)


def test_sim_masraf_fonlama_ve_veri_sonu():
    S = _S([100, 100, 100, 100, 100], [100, 100.5, 100.5, 100.5, 100.5], [100, 99.5, 99.5, 99.5, 99.5], [100, 100, 100, 100, 100])
    mal = (0.0004, 0.0003, 0.0002, 0.0005)
    r = S3.simule_v3(S, 1, 100.0, 1, {"stop": 95.0, "hedef": 110.0}, 3, mal, H)
    giris, cik = 100 * 1.0003, 100 * (1 - 0.0002)
    assert r[1] == 2 and r[0] == pytest.approx(((cik - giris) - 0.0004 * (giris + cik)) / (giris - 95.0))
    assert S3.simule_v3(S, 3, 100.0, 1, {"stop": 95.0, "hedef": 110.0}, 3, mal, H) is None          # veri bitti: zaman stopuna ulasilamadi
    fon = {"t": S["t"][[1, 2]] + 0, "r": np.array([0.001, 0.001])}
    import simulasyon as SM
    fh = SM.fonlama_hazirla(fon)
    r0 = S3.simule_v3(S, 1, 100.0, 1, {"stop": 95.0, "hedef": 110.0}, 3, MAL0, H, fh)
    assert r0[5] == pytest.approx(-0.001 * 100.0 / 5.0)                                              # giris acilisindaki odeme sayilmaz, 2. odeme long'dan kesilir
    # kisa yon: fonlama pozitifken kazanir
    rs = S3.simule_v3(S, 1, 100.0, -1, {"stop": 105.0, "hedef": 90.0}, 3, MAL0, H, fh)
    assert rs[5] == pytest.approx(0.001 * 100.0 / 5.0)


def test_sim_min_risk_stop_yoksa_uygulanmaz_ve_mum_boslugu():
    S = _S([100] * 6, [100.5] * 6, [99.5] * 6, [100] * 6)
    assert S3.simule_v3(S, 1, 100.0, 1, {"stop": 99.8, "hedef": 101.0}, 3, MAL0, H, None, 0.006) is None
    assert S3.simule_v3(S, 1, 100.0, 1, {"stop": None, "hedef": None, "rbirim": 0.2}, 3, MAL0, H, None, 0.0) is not None
    S["t"][3:] += H
    assert S3.simule_v3(S, 1, 100.0, 1, {"stop": 90.0, "hedef": 120.0}, 4, MAL0, H) is None


def test_islem_dongusu_acik_pozisyon_varken_giris_yok_ve_ters_yone_gecis():
    n = 12
    c = np.array([100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100.0])
    S = _S(c, c + 0.5, c - 0.5, c)
    cx = np.zeros(n, bool)
    cx[4] = True
    sp = {"stop": None, "hedef": None, "rbirim": 2.0, "cx": cx}
    sp2 = {"stop": None, "hedef": None, "rbirim": 2.0}
    sig = [(2, 1, sp, np.nan, np.inf, "a"), (3, 1, sp, np.nan, np.inf, "b"), (4, -1, sp2, np.nan, np.inf, "c")]
    sayac = {"acik_atlanan": 0, "sim_yok": 0}
    rows = K3.islem_dongusu_v3(S, sig, 6, MAL0, H, None, 0, 0.0, sayac)
    assert [r[9] for r in rows] == ["a", "c"] and sayac["acik_atlanan"] == 1          # b acik pozisyon yuzunden atlandi; c, a'nin cikis acilisinda (bar 5) girer
    assert rows[0][5] == int(S["t"][5]) and rows[1][4] == int(S["t"][5])


# ================================================================================================ kosu / rastgele / cli
def test_rastgele_ozet_agirlikli_ve_yetersiz():
    R = np.array([0.5] * 60 + [-0.5] * 40)
    rr = [(100, 200, 200 * 0.1, 200 * 0.25), (300, 200, -200 * 0.2, 200 * 0.3)]
    g = K3.rastgele_ozet(R, rr)
    assert g["rastgele_ort_net_R"] == pytest.approx((100 * 0.1 + 300 * -0.2) / 400)
    assert g["z_durum"] == "ok" and g["z"] is not None
    assert K3.rastgele_ozet(R[:10], rr)["z_durum"] == "yetersiz"
    assert K3.rastgele_ozet(np.zeros(0), rr)["gercek_islem"] == 0


def test_rastgele_grup_eslesme_ayni_yil_ve_isinma():
    D = _rastgele_seri(2500, 2)
    atr = G.atr(D["h"], D["l"], D["c"], 14)
    rows = [(1.0, 1, 5, 0, int(D["t"][800]), int(D["t"][805]), 1, 2.0, 3.0, "x")] * 3
    rg = np.random.default_rng(1)
    n_g, k, s1, s2 = K3.rastgele_grup(D, atr, rows, 1, rg, 48, MAL0, H, None, 0, 0.0)
    assert n_g == 3 and 0 < k <= K3.RASTGELE_N and s2 >= 0
    assert K3.rastgele_grup(D, atr, rows, -1, rg, 48, MAL0, H, None, 0, 0.0)[:2] == (0, 0)       # yon eslesmesi
    rows_stopsuz = [(1.0, 3, 5, 0, int(D["t"][800]), int(D["t"][805]), 1, float("nan"), float("inf"), "x")]
    assert K3.rastgele_grup(D, atr, rows_stopsuz, 1, np.random.default_rng(2), 48, MAL0, H, None, 0, 0.0)[1] > 0


def test_isle_cift_ve_hesapla_uctan_uca_sentetik():
    D = _rastgele_seri(2500, 6)
    import pandas as pd
    df = pd.DataFrame({"date": pd.to_datetime(D["t"], utc=True), "open": D["o"], "high": D["h"], "low": D["l"], "close": D["c"], "volume": D["v"]})
    K3.G.clear()
    K3.G.update(mal={"XX/USDT": (0.0004, 0.0003, 0.0002, 0.0005)}, mum={"1h": {"XX/USDT": df}}, fon={}, bas_ns=0, tfler=["1h"], setuplar=KODLAR)
    pi, sonuc, rastgele, sayaclar, kapsam = K3.isle_cift((0, "XX/USDT"))
    assert set(sonuc) == {(k, "1h") for k in KODLAR} and kapsam["1h"]["mum"] == 2500
    j = K3.hesapla(sonuc, rastgele, sayaclar, ["XX/USDT"], ["1h"], KODLAR)
    m = j["ana"]["IND_BOLL_DONUS"]["1h"]["hepsi"]
    assert m["islem"] > 20 and set(m["cikis_turleri"]) == {"stop", "hedef", "zaman", "sinyal"} and m["yillik_toplam_R"] and m["cift_sayisi"] == 1
    assert sum(j["ana"][k]["1h"]["hepsi"]["islem"] for k in KODLAR) > 100
    toplam = sum(m["cikis_turleri"].values())
    assert toplam == m["islem"]
    assert j["rastgele"]["IND_BOLL_DONUS"]["1h"]["hepsi"]["rastgele_islem"] > 0
    md = K3.ozet_md({"ana": j["ana"], "rastgele": j["rastgele"], "meta": {"donem": "t", "ciftler": ["XX/USDT"], "veri_olan_ciftler": ["XX/USDT"], "tfler": ["1h"],
                                                                             "fonlama_cift": 0, "kesim": "x", "sure_sn": 1.0, "kapsam": {"XX/USDT": kapsam},
                                                                             "tam_gecmis_esigi": {"1h": "2021-01-15"}}})
    assert "IND_BOLL_DONUS" in md and "FOR_OBO" in md


def test_cli_v3_kilitli_bayraksiz_hata_ve_bilinmeyen_setup(tmp_path):
    assert CA.main(["--setuplar", "v3", "--donem", "kilitli", "--cikti", str(tmp_path / "x")]) == 2
    assert CA.main(["--setuplar", "v3", "--donem", "gelistirme", "--setup", "YOK_BOYLE", "--ciftler", "BTC/USDT", "--cikti", str(tmp_path / "y")]) == 2
