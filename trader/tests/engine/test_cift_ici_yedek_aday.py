"""24.11: kazanan aday sonraki bir kontrolde (adaya ozgu red: uzun_yon) reddedilirse ayni cift icin siradaki aday denenir;
cift basina en cok bir islem; red nedenleri gercek, yalniz onceliginde kaybedenler arm_conflict."""
from __future__ import annotations

import dataclasses
from datetime import timedelta
from types import SimpleNamespace

import test_dd12_wp11_spec as W

H = timedelta(hours=1)
PAIRS = W.PAIRS5[:3]
BTC, ETH, SOL = PAIRS


def _motor(tmp, ayi=False):
    """`ayi=True`: 1d rejimi AYI (uzun_yon) => long adaylar `uzun_yon` ile adaya ozgu reddedilir, short adaylar gecer."""
    over = W._engine_over(PAIRS, arms=["T1@4h", "T1@1h"])
    e = W._E(tmp, PAIRS, W.D_E - H, over)
    if ayi:
        e.eng.gate.uzun_yon = SimpleNamespace(rejim=lambda pair, now: "ayi")
    return e


TF_SAAT = {"1h": 1, "4h": 4, "1d": 24}


def _sinyal(e, D, pair, arm, side="long"):
    tf = arm.split("@")[1]
    stop = 98.0 if side == "long" else 102.0
    e.signal(D, [pair], arm_id=arm, setup="T1", tf=tf, bar_open_ts=D - timedelta(hours=TF_SAAT[tf]), side=side, stop=stop)


def _adaylar(e, D, pair, arms, sides=None, duz_ilk=False):
    """`arms` sirasiyla (buyuk tf once): ilki kazanan, kalanlar extras. `sides`: aday basina yon (varsayilan long)."""
    frames = []
    for i, a in enumerate(arms):
        _sinyal(e, D, pair, a, (sides or ["long"] * len(arms))[i])
        frames.append(e.eng.signals.frames[(pair, D)])
    if duz_ilk:                                                   # ilk aday olu mum (flat_bar: adaya ozgu red, hesap tavanindan ONCE)
        frames[0] = dataclasses.replace(frames[0], trigger_bar=(100.0, 100.0, 5.0))
    e.eng.signals.frames[(pair, D)] = dataclasses.replace(frames[0], extras=tuple(frames[1:]))


def _satirlar(e, pair, D=None):
    return W._ledger_rows(e, "SELECT arm_id, final_action, skip_reason, veto_reason FROM decision_events "
                             f"WHERE pair='{pair}' ORDER BY rowid")


def _kos(tmp, ayi, arms_btc, sides=None):
    e = _motor(tmp, False)
    try:
        D0 = W.D_E
        _sinyal(e, D0, ETH, "T1@4h")                              # ETH once acilir: T1@4h dolar
        e.decide(D0)
        e.step(D0)
        assert e.state.position_for_pair(ETH) is not None
        D1 = D0 + H
        if ayi:
            e.eng.gate.uzun_yon = SimpleNamespace(rejim=lambda pair, now: "ayi")      # ETH girdikten sonra: long adaylar reddedilir
        _adaylar(e, D1, BTC, arms_btc, sides)
        e.decide(D1)
        e.step(D1)
        pos = e.state.position_for_pair(BTC)
        return (None if pos is None else pos.trigger_tf), _satirlar(e, BTC)
    finally:
        e.close()


def test_kazanan_reddedilince_ikinci_aday_girer(tmp_path):
    tf, rows = _kos(tmp_path / "a", True, ["T1@4h", "T1@1h"], ["long", "short"])      # AYI rejimi: long kazanan reddedilir
    assert tf == "1h", rows
    assert rows[0][:3] == ("T1@4h", "skipped", "risk_denied") and "uzun_yon" in rows[0][3], rows
    assert rows[1][:2] == ("T1@1h", "entered"), rows
    assert not [r for r in rows if r[2] == "arm_conflict"], rows           # reddedilen kazanan arm_conflict degil, gercek neden


def test_hepsi_reddedilirse_giris_yok_gercek_nedenler(tmp_path):
    tf, rows = _kos(tmp_path / "b", True, ["T1@4h", "T1@1h"])                          # ikisi de long: ikisi de reddedilir
    assert tf is None, rows
    assert [r[0] for r in rows] == ["T1@4h", "T1@1h"] and all(r[1:3] == ("skipped", "risk_denied") for r in rows), rows
    assert all("uzun_yon" in r[3] for r in rows), rows


def test_kazanan_girerse_digerleri_arm_conflict(tmp_path):
    tf, rows = _kos(tmp_path / "c", False, ["T1@4h", "T1@1h"])
    assert tf == "4h", rows
    assert rows[0][:2] == ("T1@4h", "entered"), rows
    assert rows[1][:3] == ("T1@1h", "skipped", "arm_conflict") and "arm_conflict:T1@4h" in rows[1][3], rows


def test_belirlenimci_ayni_girdi_ayni_sonuc(tmp_path):
    a = _kos(tmp_path / "d1", True, ["T1@4h", "T1@1h"], ["long", "short"])
    b = _kos(tmp_path / "d2", True, ["T1@4h", "T1@1h"], ["long", "short"])
    assert a == b


def test_ayni_adim_bir_islemden_fazla_acilmaz(tmp_path):
    e = _motor(tmp_path)
    try:
        D = W.D_E
        _adaylar(e, D, SOL, ["T1@4h", "T1@1h"])
        e.decide(D)
        e.step(D)
        n = W._ledger_rows(e, "SELECT count(*) FROM decision_events WHERE pair='" + SOL + "' AND final_action='entered'")
        assert n == [(1,)]
    finally:
        e.close()


def _satir_sayisi(e, pair):
    return W._ledger_rows(e, f"SELECT count(*) FROM decision_events WHERE pair='{pair}'")[0][0]


def test_acik_pozisyonlu_cift_iki_sinyal_yeni_satir_yazmaz(tmp_path):
    e = _motor(tmp_path)
    try:
        D0 = W.D_E
        _sinyal(e, D0, ETH, "T1@4h")
        e.decide(D0)
        e.step(D0)
        assert e.state.position_for_pair(ETH) is not None
        onceki = _satir_sayisi(e, ETH)
        D1 = D0 + H
        _adaylar(e, D1, ETH, ["T1@4h", "T1@1h"])                   # ETH acik: position_exists -> ignore
        e.decide(D1)
        e.step(D1)
        assert _satir_sayisi(e, ETH) == onceki                    # arm_conflict dahil yeni satir yok
    finally:
        e.close()


def test_cift_duzeyi_red_durur_kalan_arm_conflict(tmp_path):
    over = W._engine_over(PAIRS, arms=["T1@4h", "T1@1h"])
    over["max_positions"] = 1                                      # hesap tavani: ETH dolduruyor
    e = W._E(tmp_path, PAIRS, W.D_E - H, over)
    try:
        D0 = W.D_E
        _sinyal(e, D0, ETH, "T1@4h")
        e.decide(D0)
        e.step(D0)
        D1 = D0 + H
        _adaylar(e, D1, BTC, ["T1@4h", "T1@1h"])
        e.decide(D1)
        e.step(D1)
        rows = _satirlar(e, BTC)
        assert e.state.position_for_pair(BTC) is None
        assert [r[:3] for r in rows] == [("T1@4h", "skipped", "max_positions"), ("T1@1h", "skipped", "arm_conflict")], rows
        assert "gate:max_positions" == rows[0][3]
        assert e.state.is_decided(BTC, D1)                         # bir kez isaretlendi
    finally:
        e.close()


def test_red_kumeleri_tek_tanim():
    from types import SimpleNamespace as NS
    from trader_engine import gates as G

    def o(code, veto=None, risk=None):
        return NS(code=code, event=NS(veto_reason=veto, risk_reason=risk))
    assert not G.aday_ozgu_red(o("max_positions", "gate:max_positions"))
    for k in ("uzun_yon", "korelasyon_grubu", "flat_bar", "toplam_buyukluk", "tasfiye_mesafesi"):
        assert G.aday_ozgu_red(o(k)), k
    for k in ("cluster_cap", "etiket_rejim", "entry_gate_closed", "rules_missing", "session_closed", "bilinmeyen_kod"):
        assert not G.aday_ozgu_red(o(k)), k
    assert G.aday_ozgu_red(o("risk_denied", risk="boyutlandırma reddedildi: x"))
    assert not G.aday_ozgu_red(o("risk_denied", risk="günlük zarar bütçesi aşılır"))
    assert not G.aday_ozgu_red(o("risk_denied", risk="toplam açık risk sınırı aşılır"))


def test_yapisal_hesap_duzeyi_alani_ve_buyukluk_okunamadi():
    """25.11 denetim #26: yapisal `hesap_duzeyi` alani metne ustun gelir; buyukluk_okunamadi hesap duzeyi (cift icin durulur)."""
    from types import SimpleNamespace as NS
    from trader_engine import gates as G
    assert not G.aday_ozgu_red(NS(code="buyukluk_okunamadi", event=NS(veto_reason=None, risk_reason=None)))
    ev = NS(veto_reason=None, risk_reason="metin degisti")
    assert not G.aday_ozgu_red(NS(code="risk_denied", event=ev, hesap_duzeyi=True))      # metin tutmasa da alan karar verir
    assert G.aday_ozgu_red(NS(code="risk_denied", event=ev, hesap_duzeyi=False))
    # gercek risk.py metinleri hesap duzeyi sayilir
    for m in ("günlük sınır aşıldı: yeni işlem açılamaz", "BTC/USDT için zaten açık pozisyon var", "toplam açık risk sınırı aşılır",
              "günlük zarar bütçesi aşılır", "toplam teminat özsermayeyi aşar"):
        assert G.hesap_duzeyi_risk(m), m
    assert not G.hesap_duzeyi_risk("boyutlandırma reddedildi: x")


def test_cift_duzeyi_red_kazanan_olarak_reddedilen_aday_yazilir(tmp_path):
    """25.11 denetim #27: ilk aday adaya ozgu (flat_bar), ikinci aday hesap tavaniyla reddedilince kalan aday
    `arm_conflict` kaydinda kazanan = reddedilen ikinci aday (ilk aday degil)."""
    over = W._engine_over(PAIRS, arms=["T1@1d", "T1@4h", "T1@1h"])
    over["max_positions"] = 1
    e = W._E(tmp_path, PAIRS, W.D_E - H, over)
    try:
        D0 = W.D_E
        _sinyal(e, D0, ETH, "T1@1d")                               # ETH: T1@1d dolar, hesap tavani da dolar
        e.decide(D0)
        e.step(D0)
        assert e.state.position_for_pair(ETH) is not None
        D1 = D0 + H
        _adaylar(e, D1, BTC, ["T1@1d", "T1@4h", "T1@1h"], duz_ilk=True)
        e.decide(D1)
        e.step(D1)
        rows = _satirlar(e, BTC)
        assert [r[:3] for r in rows] == [("T1@1d", "skipped", "flat_bar"), ("T1@4h", "skipped", "max_positions"),
                                         ("T1@1h", "skipped", "arm_conflict")], rows
        assert rows[0][3] == "gate:flat_bar" and rows[1][3] == "gate:max_positions"
        assert rows[2][3].endswith("arm_conflict:T1@4h"), rows          # kazanan = reddedilen 2. aday
    finally:
        e.close()
