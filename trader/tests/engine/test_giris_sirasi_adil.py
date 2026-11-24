"""Giris adaylari sirasi: buyuk tf once, esitlikte D'den turetilen donen ofset; deterministik; tavan dolarken ayni cift hep onde degil."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from trader_engine.engine import Engine

import test_dd12_wp11_spec as W

UTC = timezone.utc
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]


def _frames(tfs):
    """tfs: cift -> tf adi ya da None (adayi yok)."""
    out = {}
    for p in PAIRS:
        tf = tfs.get(p)
        out[p] = SimpleNamespace(last=None if tf is None else SimpleNamespace(tf=tf))
    return out


def _sira(D, tfs=None):
    stub = SimpleNamespace(cfg=SimpleNamespace(pairs=tuple(PAIRS)))
    return Engine._entry_order(stub, D, _frames(tfs or {p: "1h" for p in PAIRS}))


def test_ayni_zaman_damgasi_ayni_sira():
    D = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
    assert _sira(D) == _sira(D) == _sira(datetime(2026, 11, 11, 15, 0, tzinfo=UTC))


def test_ofset_her_15dk_adimda_doner():
    D = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
    ilkler = [_sira(D + timedelta(minutes=15 * k))[0] for k in range(len(PAIRS))]
    assert sorted(ilkler) == sorted(PAIRS)                     # bes ardisik adimda her cift bir kez one gecer
    for k in range(len(PAIRS)):
        s = _sira(D + timedelta(minutes=15 * k))
        assert sorted(s) == sorted(PAIRS)
        i = PAIRS.index(s[0])
        assert s == PAIRS[i:] + PAIRS[:i]                      # yapilandirma sirasinin donmus hali (goreli sira korunur)


def test_buyuk_zaman_dilimi_once():
    D = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
    tfs = {"BTC/USDT": "15m", "ETH/USDT": "1h", "SOL/USDT": "1d", "BNB/USDT": "4h", "XRP/USDT": None}
    for k in range(8):
        s = _sira(D + timedelta(minutes=15 * k), tfs)
        assert s == ["SOL/USDT", "BNB/USDT", "ETH/USDT", "BTC/USDT", "XRP/USDT"], s


def test_esit_tfte_ofset_buyuk_tfyi_bozmaz():
    D = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
    tfs = {"BTC/USDT": "1h", "ETH/USDT": "4h", "SOL/USDT": "1h", "BNB/USDT": "4h", "XRP/USDT": "1h"}
    gorulen = set()
    for k in range(10):
        s = _sira(D + timedelta(minutes=15 * k), tfs)
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
        kume[k] = _acilanlar(tmp_path / f"s{k}", D0 + timedelta(minutes=15 * k))
        assert len(kume[k]) == 2, kume
    assert len(set(kume.values())) > 1, kume                    # hep ayni iki cift (config sirasi) degil
    assert _acilanlar(tmp_path / "tekrar", D0) == kume[0]       # ayni D -> ayni sonuc
