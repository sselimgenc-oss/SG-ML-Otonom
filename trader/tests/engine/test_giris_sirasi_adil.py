"""Giris adaylari sirasi: buyuk tf once, esitlikte (D // tf_saniye) % n donen ofset; deterministik; tavan dolarken ayni cift hep onde degil."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from trader_engine.engine import Engine

import test_dd12_wp11_spec as W

UTC = timezone.utc
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]


def _frames(tfs, pairs=PAIRS):
    """tfs: cift -> tf adi ya da None (adayi yok)."""
    out = {}
    for p in pairs:
        tf = tfs.get(p)
        out[p] = SimpleNamespace(last=None if tf is None else SimpleNamespace(tf=tf, signal=not str(tf).startswith('!')))
    return out


def _sira(D, tfs=None):
    stub = SimpleNamespace(cfg=SimpleNamespace(pairs=tuple(PAIRS)))
    return Engine._entry_order(stub, D, _frames(tfs or {p: "1h" for p in PAIRS}))


def test_ayni_zaman_damgasi_ayni_sira():
    D = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
    assert _sira(D) == _sira(D) == _sira(datetime(2026, 11, 11, 15, 0, tzinfo=UTC))


def test_ofset_her_tf_adiminda_doner():
    D = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
    ilkler = [_sira(D + timedelta(hours=k))[0] for k in range(len(PAIRS))]
    assert sorted(ilkler) == sorted(PAIRS)                     # bes ardisik adimda her cift bir kez one gecer
    for k in range(len(PAIRS)):
        s = _sira(D + timedelta(hours=k))
        assert sorted(s) == sorted(PAIRS)
        i = PAIRS.index(s[0])
        assert s == PAIRS[i:] + PAIRS[:i]                      # yapilandirma sirasinin donmus hali (goreli sira korunur)


def test_buyuk_zaman_dilimi_once():
    D = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
    tfs = {"BTC/USDT": "15m", "ETH/USDT": "1h", "SOL/USDT": "1d", "BNB/USDT": "4h", "XRP/USDT": None}
    for k in range(8):
        s = _sira(D + timedelta(hours=k), tfs)
        assert s == ["SOL/USDT", "BNB/USDT", "ETH/USDT", "BTC/USDT", "XRP/USDT"], s


def test_esit_tfte_ofset_buyuk_tfyi_bozmaz():
    D = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
    tfs = {"BTC/USDT": "1h", "ETH/USDT": "4h", "SOL/USDT": "1h", "BNB/USDT": "4h", "XRP/USDT": "1h"}
    gorulen = set()
    for k in range(10):
        s = _sira(D + timedelta(hours=k), tfs)
        assert set(s[:2]) == {"ETH/USDT", "BNB/USDT"} and set(s[2:]) == {"BTC/USDT", "SOL/USDT", "XRP/USDT"}
        gorulen.add(s[0])
    assert gorulen == {"ETH/USDT", "BNB/USDT"}                  # esit tf icinde baslangic doner


def _acilanlar(tmp, D):
    pairs = W.PAIRS5[:4]
    over = W._engine_over(pairs, arms=["T1@1h"], arm_max_positions={"default": 6})
    over["max_positions"] = 2                                   # hesap tavani: yalniz 2 giris
    e = W._E(tmp, pairs, D - timedelta(hours=1), over)
    try:
        for p, yon in zip(pairs, ("long", "short", "long", "short")):
            kw = {} if yon == "long" else {"side": "short", "planned_stop": 102.0, "regime": "trend_down"}
            W._signal_arm(e, D, p, "T1@1h", **kw)
        e.decide(D)
        e.step(D)
        return frozenset(p for p in pairs if e.state.position_for_pair(p) is not None)
    finally:
        e.close()


def test_tavan_dolarken_farkli_adimlar_farkli_cift_alir(tmp_path):
    D0 = W.D_E
    kume = {}
    for k in range(4):
        kume[k] = _acilanlar(tmp_path / f"s{k}", D0 + timedelta(hours=k))
        assert len(kume[k]) == 2, kume
    assert len(set(kume.values())) > 1, kume                    # hep ayni iki cift (config sirasi) degil
    assert _acilanlar(tmp_path / "tekrar", D0) == kume[0]       # ayni D -> ayni sonuc


def _sira_n(D, pairs, tfs):
    stub = SimpleNamespace(cfg=SimpleNamespace(pairs=tuple(pairs)))
    return Engine._entry_order(stub, D, _frames(tfs, pairs))


def test_n48_ortak_bolenli_ofset_durmaz():
    """48 cift: 4h adaylari yalniz 4h sinirlarinda gorunur; (D//900)%48 her 16 adimda ayni degeri verir (donus durur).
    tf'ten turetilen ofset ise her 4h sinirinda ilerler."""
    pairs = [f"P{i:02d}/USDT" for i in range(48)]
    D0 = datetime(2026, 11, 11, 16, 0, tzinfo=UTC)               # 4h siniri
    tfs = {p: "4h" for p in pairs}
    ilk = [_sira_n(D0 + timedelta(hours=4 * k), pairs, tfs)[0] for k in range(48)]
    assert len(set(ilk)) == 48                                     # 48 4h-adiminda her cift bir kez one gecer
    tfs1 = {p: "1d" for p in pairs}
    g = [_sira_n(D0 + timedelta(days=k), pairs, tfs1)[0] for k in range(48)]
    assert len(set(g)) == 48


def test_karisik_tf_gercek_cerceveler_ve_ortak_bolenli_n():
    """n=12 (4 ve 16 ile ortak bolenli), karisik tf: gruplar buyukten kucuge; her grup kendi tf adiminda doner; sinyalsiz -1 (en sonda)."""
    pairs = [f"P{i:02d}/USDT" for i in range(12)]
    tfs = {p: ("4h" if i % 3 == 0 else "1h" if i % 3 == 1 else None) for i, p in enumerate(pairs)}
    D0 = datetime(2026, 11, 11, 16, 0, tzinfo=UTC)
    ilk4 = set()
    for k in range(12):
        s = _sira_n(D0 + timedelta(hours=4 * k), pairs, tfs)
        assert s == _sira_n(D0 + timedelta(hours=4 * k), pairs, tfs)          # deterministik
        g4 = [p for p in s if tfs[p] == "4h"]
        g1 = [p for p in s if tfs[p] == "1h"]
        gn = [p for p in s if tfs[p] is None]
        assert s == g4 + g1 + gn
        ilk4.add(g4[0])
    assert ilk4 == {p for p in pairs if tfs[p] == "4h"}                       # 4h grubunda baslangic doner


def test_sinyalsiz_cift_en_sonda_minus_bir():
    """Satiri olan ama sinyali olmayan cift, kucuk tf'li sinyal verenin de arkasina duser."""
    D = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
    tfs = {"BTC/USDT": "!1d", "ETH/USDT": "15m", "SOL/USDT": None, "BNB/USDT": "!4h", "XRP/USDT": "1h"}
    for k in range(6):
        s = _sira(D + timedelta(hours=k), tfs)
        assert s[:2] == ["XRP/USDT", "ETH/USDT"] and set(s[2:]) == {"BTC/USDT", "SOL/USDT", "BNB/USDT"}, s
