"""19.11 kullanici karari: kagitta ML filtresi AKTIF. Esik alti puan bir girisi `ml_filter` ile atlatir; boyut/kaldirac/limit degismez.
Paket yok/bozuk/suresi gecmis/<10 islem/istisna => serbest. Egitim holdout satiri almaz. Canli/testnet yolu degismez."""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from ortak_ogrenme import filtre as PF
from ortak_ogrenme.kayit import Aday
from trader_core import ledger as L
from trader_engine import ogrenme_filtre as OF
from trader_engine.config import load_cli_config
from trader_engine.gates import EntryGate, NoVeto
from trader_engine.killswitch import Killswitch
from trader_engine.clock import SimClock
from trader_engine.state import StateStore
from trader_engine.strategy_runner import SignalFrame
from trader_engine.types import SymbolRules

from test_engine_05_impl_smoke import T0, _params, _row  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CFG = load_cli_config(ROOT / "config", "learner", "paper")
NOW = datetime(2026, 12, 1, 0, 0, 5, tzinfo=timezone.utc)


class Sahte:
    def __init__(self, karar=None, hata=False):
        self._k, self._h, self.cagri = karar, hata, 0

    def karar(self, arm, oz, simdi):
        self.cagri += 1
        if self._h:
            raise RuntimeError("filtre patladi")
        return self._k


def _kur(tmp_path, flt, cfg=CFG, day_start=1000.0):
    tmp_path.mkdir(parents=True, exist_ok=True)
    clock = SimClock(T0 + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:price_action_v1@1b.0")
    state = StateStore(":memory:", bot="learner")
    with state.tx():
        state.kv_set("day_start:2026-12-01", day_start)
    state.open_positions = lambda: []   # type: ignore[method-assign]
    broker = SimpleNamespace(account=lambda: SimpleNamespace(equity=1000.0, wallet=1000.0))
    rules = lambda p: SymbolRules(p, p.replace("/", ""), 0.01, 0.001, 0.001, 1e9, 5.0)  # noqa: E731
    g = EntryGate(cfg, led, state, Killswitch(str(tmp_path / "KILL"), clock), NoVeto(), clock, broker, rules)
    g.ml_filtre = flt
    return SimpleNamespace(g=g, led=led, state=state)


def _go(e):
    fr = SignalFrame(pair="BTC/USDT", status="ok", detail=None, last=_row(), table=None, trigger_bar=(110.0, 99.0, 5.0))
    return e.g.decide(fr, T0, e.g.pre(T0, "1h", True, "1h"), 1)


def _kapat(*es):
    for e in es:
        e.state.close()
        e.led.close()


def test_esik_alti_giris_atlanir_ml_filter_yazilir(tmp_path):
    e = _kur(tmp_path / "a", Sahte(OF.Karar(False, 0.12, "esik_alti")))
    try:
        o = _go(e)
        assert o.action == "skip" and o.code == "ml_filter"
        assert o.event.skip_reason == "ml_filter" and o.event.final_action == "skipped" and o.event.ml_score == 0.12
        assert o.event.size_qty is None and o.event.leverage is None            # boyut/kaldirac yazilmaz: giris yok
        did = e.led.record_decision(o.event)                                    # defter bu nedeni kabul eder (alinmayan sinyal kaydi)
        assert e.led.get_decision(did).skip_reason == "ml_filter"
    finally:
        _kapat(e)


def test_esik_ustu_ayni_giris_boyut_kaldirac_limit_birebir(tmp_path):
    a, b = _kur(tmp_path / "a", None), _kur(tmp_path / "b", Sahte(OF.Karar(True, 0.9, "ok")))
    try:
        oa, ob = _go(a), _go(b)
        assert oa.action == ob.action == "enter"
        assert dataclasses.asdict(oa.event) == dataclasses.asdict(ob.event)
        assert (oa.size, oa.leverage) == (ob.size, ob.leverage)
    finally:
        _kapat(a, b)


@pytest.mark.parametrize("flt", [Sahte(hata=True), None, OF.FiltreDeposu("/yok/boyle/dizin")])
def test_hata_ya_da_filtre_yok_giris_serbest(tmp_path, flt):
    a, b = _kur(tmp_path / "a", None), _kur(tmp_path / "b", flt)
    try:
        oa, ob = _go(a), _go(b)
        assert ob.action == "enter" and dataclasses.asdict(oa.event) == dataclasses.asdict(ob.event)
        assert ob.code != "ml_no_model"
    finally:
        _kapat(a, b)


def test_gunluk_limit_filtreden_bagimsiz(tmp_path):
    """Gunluk kayip siniri: filtre gecse bile risk kapisi ayni karari verir (risk_denied)."""
    a = _kur(tmp_path / "a", None, day_start=1100.0)
    b = _kur(tmp_path / "b", Sahte(OF.Karar(True, 0.9, "ok")), day_start=1100.0)
    try:
        oa, ob = _go(a), _go(b)
        assert oa.code == ob.code == "risk_denied"
        assert dataclasses.asdict(oa.event) == dataclasses.asdict(ob.event)
    finally:
        _kapat(a, b)


def test_canli_testnet_yolunda_filtre_calismaz(tmp_path):
    s = Sahte(OF.Karar(False, 0.0, "esik_alti"))
    cfg = dataclasses.replace(CFG, mode="testnet")
    e = _kur(tmp_path / "a", s, cfg=cfg)
    try:
        o = _go(e)
        assert s.cagri == 0 and o.code != "ml_filter"
    finally:
        _kapat(e)


def test_config_kagit_active_canli_testnet_eskisi_gibi():
    assert CFG.ml_mode == "active" and CFG.mode == "paper"
    for env in ("testnet", "live"):
        try:
            c = load_cli_config(ROOT / "config", "learner", env)
        except Exception:  # noqa: BLE001 - canli yapilandirma bu ortamda eksik anahtar isteyebilir; ml_mode degismedi
            continue
        # 23.11 kullanici karari: canli = kagit (canlida ML filtresi AKTIF; testnet degismedi)
        assert c.ml_mode == ("active" if env == "live" else "off")


# ------------------------------------------------------------------ FiltreDeposu (gercek paket)
def _adaylar(arm, n, *, t0=datetime(2026, 11, 2, tzinfo=timezone.utc), saat=1):
    out = []
    for i in range(n):
        x = -5.0 if i % 3 == 2 else 5.0       # 2/3 kazanan, x etiketi tam ayirir: yayin oncesi sinama (>=3 kabul) gecer
        out.append(Aday(id=f"{arm}{i}", proje="ML", kurulum=arm, enstruman="BTC/USDT", varlik_sinifi="kripto", yon="long",
                        ts=t0 + timedelta(hours=saat * i), alindi=True, r=1.0 if x > 0 else -1.0, ozellikler={"x": x}))
    return out


def test_paket_egitim_esik_alti_atlar_ustu_gecirir(tmp_path):
    OF.egit_hepsi(_adaylar("T1@1h", 20), tmp_path, NOW)
    d = OF.FiltreDeposu(tmp_path)
    assert d.karar("T1@1h", {"x": -5.0}, NOW).izin is False
    k = d.karar("T1@1h", {"x": 5.0}, NOW)
    assert k.izin is True and k.neden == "ok" and 0.0 <= k.puan <= 1.0
    assert d.aktif_kurulumlar(NOW) == ["aile:T1"]


def test_10dan_az_islem_filtre_yok(tmp_path):
    r = OF.egit_hepsi(_adaylar("T1@1h", 9), tmp_path, NOW)
    assert r["aileler"]["T1"]["durum"] == "az_islem"
    assert OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW).izin is True
    # n_egitim<10 paketi (elle uretilmis) de kullanilmaz
    p = PF.egit("aile:T1", _adaylar("aile:T1", 6), olusturma=NOW)
    PF.kaydet(p, tmp_path)
    k = OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW)
    assert k.izin is True and k.neden == "filtre_yok"


def test_bozuk_ve_suresi_gecmis_paket_serbest(tmp_path):
    OF.egit_hepsi(_adaylar("T1@1h", 20), tmp_path, NOW)
    assert OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW + timedelta(days=30)).izin is True   # suresi gecmis
    yol = tmp_path / "aile_T1.json"
    yol.write_text(yol.read_text().replace('"esik": ', '"esik": 0.99, "x_": '), encoding="utf-8")         # hash bozuldu
    k = OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW)
    assert k.izin is True and k.neden == "filtre_yok"
    yol.write_text("{bozuk", encoding="utf-8")
    assert OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW).izin is True


def test_puan_istisnasi_serbest(tmp_path, monkeypatch):
    OF.egit_hepsi(_adaylar("T1@1h", 20), tmp_path, NOW)
    d = OF.FiltreDeposu(tmp_path)
    monkeypatch.setattr(d._mod[0], "puan", lambda *a, **k: 1 / 0)
    k = d.karar("T1@1h", {"x": -5.0}, NOW)
    assert k.izin is True and k.neden == "hata"


def test_env_kapali_filtre_yok(tmp_path, monkeypatch):
    OF.egit_hepsi(_adaylar("T1@1h", 20), tmp_path, NOW)
    monkeypatch.setenv(OF.ENV_KAPALI, "1")
    assert OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW).izin is True


def test_egitim_acik_kilitte_holdout_satiri_da_alir(tmp_path):
    """23.11.2026 kullanici karari: kilit ACIK -> kilitli donem satirlari egitime girer, kilit_dusen 0."""
    assert OF.KILIT_ACIK is True
    ic = _adaylar("T1@1h", 5, t0=datetime(2026, 6, 1, tzinfo=timezone.utc))
    dis = _adaylar("T1@1h", 20, t0=datetime(2026, 11, 3, tzinfo=timezone.utc))
    OF.egit_hepsi(ic + [dataclasses.replace(a, id="k" + a.id) for a in dis], tmp_path, NOW)
    meta = json.loads((tmp_path / "aile_T1.json").read_text())["meta"]
    assert meta["n_egitim"] == 25 and meta["kilit_dusen"] == 0
    assert not OF._kilit_kesisir(datetime(2026, 10, 31, 23, tzinfo=timezone.utc), datetime(2026, 11, 2, tzinfo=timezone.utc))


def test_egitim_holdout_satiri_almaz(tmp_path, monkeypatch):
    monkeypatch.setattr(OF, "KILIT_ACIK", False)          # kilit mekanizmasi kapali bayrakla sinanir
    ic = _adaylar("T1@1h", 5, t0=datetime(2026, 6, 1, tzinfo=timezone.utc))            # holdout icinde
    dis = _adaylar("T1@1h", 20, t0=datetime(2026, 11, 3, tzinfo=timezone.utc))
    OF.egit_hepsi(ic + [dataclasses.replace(a, id="k" + a.id) for a in dis], tmp_path, NOW)
    meta = json.loads((tmp_path / "aile_T1.json").read_text())["meta"]
    assert meta["n_egitim"] == 20 and meta["kilit_dusen"] == 5
    assert OF._kilit_kesisir(datetime(2026, 10, 31, 23, tzinfo=timezone.utc), datetime(2026, 11, 2, tzinfo=timezone.utc))
    assert not OF._kilit_kesisir(datetime(2026, 11, 1, tzinfo=timezone.utc), datetime(2026, 11, 2, tzinfo=timezone.utc))


def test_yeniden_egitim_kurali_10_yeni_islem(tmp_path):
    OF.egit_hepsi(_adaylar("T1@1h", 20), tmp_path, NOW)
    h0 = json.loads((tmp_path / "aile_T1.json").read_text())["meta"]["model_hash"]
    r = OF.egit_hepsi(_adaylar("T1@1h", 24), tmp_path, NOW + timedelta(days=1))
    assert r["aileler"]["T1"]["durum"] == "guncel"
    r = OF.egit_hepsi(_adaylar("T1@1h", 31), tmp_path, NOW + timedelta(days=2))
    assert r["aileler"]["T1"]["durum"] == "ok"
    assert json.loads((tmp_path / "aile_T1.json").read_text())["meta"]["n_egitim"] == 31
    assert (tmp_path / "aile_T1.prev.json").exists() and h0


# ------------------------------------------------------------------ AILE modeli (kurulum ailesi, tum zaman dilimleri havuzda)
def _aile_adaylar(kollar: dict[str, int]):
    out = []
    for arm, n in kollar.items():
        out += _adaylar(arm, n, t0=datetime(2026, 11, 2, tzinfo=timezone.utc) + timedelta(minutes=len(out)))
    out.sort(key=lambda a: a.ts)
    # etiket deseni havuz sirasina gore (her aile diliminde iki sinif + yayin oncesi sinama gecer)
    return [dataclasses.replace(a, r=-1.0 if i % 3 == 2 else 1.0, ozellikler={"x": -5.0 if i % 3 == 2 else 5.0}) for i, a in enumerate(out)]


def test_aile_of_ve_tf_ozellikleri():
    assert OF.aile_of("M1@15m") == "M1" and OF.aile_of("T1@1d") == "T1"
    assert OF.aile_of("?@1h") is None and OF.aile_of("M1@3h") is None and OF.aile_of(None) is None and OF.aile_of("M1") is None
    f = OF.tf_ozellikleri("4h")
    assert f["tf_log2_dk"] == pytest.approx(7.9068905956) and f["tf_4h"] == 1.0 and f["tf_1h"] == 0.0


def test_aile_toplam_10_olunca_aktif_her_kola_uygulanir(tmp_path):
    # hicbir kolun tek basina 10 islemi yok: 8+6+4+4 = 22 >= 10
    r = OF.egit_hepsi(_aile_adaylar({"M1@15m": 8, "M1@1h": 6, "M1@4h": 4, "M1@1d": 4}), tmp_path, NOW)
    assert r["aileler"]["M1"]["durum"] == "ok" and r["aileler"]["M1"]["n"] == 22
    assert r["aileler"]["M1"]["kollar"] == {"M1@15m": 8, "M1@1h": 6, "M1@4h": 4, "M1@1d": 4}
    meta = json.loads((tmp_path / "aile_M1.json").read_text())["meta"]
    assert meta["kurulum"] == "aile:M1" and meta["n_egitim"] == 22 and "tf_log2_dk" in meta["ozellikler"]
    d = OF.FiltreDeposu(tmp_path)
    assert d.aktif_aileler(NOW) == ["M1"] and d.aktif_kol_sayisi(NOW) == 4
    for arm in ("M1@15m", "M1@1h", "M1@4h", "M1@1d"):
        assert d.karar(arm, {"x": -5.0}, NOW).izin is False, arm          # filtre gercekten engeller
        assert d.karar(arm, {"x": 5.0}, NOW).izin is True, arm
    assert d.karar("T1@1h", {"x": -5.0}, NOW).izin is True               # baska aile: filtre yok


def test_aile_toplam_10dan_az_filtre_yok(tmp_path):
    r = OF.egit_hepsi(_aile_adaylar({"M1@15m": 4, "M1@1h": 3, "M1@4h": 2}), tmp_path, NOW)
    assert r["aileler"]["M1"]["durum"] == "az_islem"
    assert OF.FiltreDeposu(tmp_path).karar("M1@15m", {"x": -5.0}, NOW).neden == "filtre_yok"


def test_t1_ve_r1_ayri_aileler(tmp_path):
    r = OF.egit_hepsi(_aile_adaylar({"T1@1h": 6, "R1@1h": 6}), tmp_path, NOW)
    assert r["aileler"]["T1"]["durum"] == r["aileler"]["R1"]["durum"] == "az_islem"   # havuzlanmaz


def test_eski_kol_paketi_yok_sayilir_ve_tasinir(tmp_path):
    eski = PF.egit("M1@1h", _adaylar("M1@1h", 12), olusturma=NOW)
    PF.kaydet(eski, tmp_path)
    (tmp_path / OF.DURUM_DOSYASI).write_text(json.dumps({"M1@1h": {"zaman": NOW.isoformat(), "n": 12, "model": True}}))
    d = OF.FiltreDeposu(tmp_path)
    assert d.karar("M1@1h", {"x": -5.0}, NOW).neden == "filtre_yok" and d.aktif_kurulumlar(NOW) == []
    r = OF.egit_hepsi([], tmp_path, NOW)
    assert r["eski_tasinan"] == 1 and (tmp_path / OF.ESKI_ALT / "M1@1h.json").exists() and not (tmp_path / "M1@1h.json").exists()
    assert json.loads((tmp_path / OF.DURUM_DOSYASI).read_text()) == {}


def test_aile_yeniden_egitim_havuz_sayisiyla(tmp_path):
    OF.egit_hepsi(_aile_adaylar({"M1@15m": 6, "M1@1h": 6}), tmp_path, NOW)
    r = OF.egit_hepsi(_aile_adaylar({"M1@15m": 8, "M1@1h": 8}), tmp_path, NOW + timedelta(days=1))
    assert r["aileler"]["M1"]["durum"] == "guncel"
    r = OF.egit_hepsi(_aile_adaylar({"M1@15m": 12, "M1@1h": 11}), tmp_path, NOW + timedelta(days=2))
    assert r["aileler"]["M1"]["durum"] == "ok" and r["aileler"]["M1"]["n"] == 23


def test_gece_birimi_paper_models_csv_aile_satiri(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import ml_retrain_run as R
    lp = tmp_path / "ledger.sqlite"
    L.open_ledger(lp, "learner", create=True, migrate=True).close()
    monkeypatch.setattr(OF, "adaylar_defterden", lambda led, *a, **k: _aile_adaylar({"M1@15m": 8, "M1@1h": 6, "M1@4h": 4, "M1@1d": 4, "T1@1h": 3}))
    rc = R.main(["--once", "--ledger", str(lp), "--models-dir", str(tmp_path / "m"), "--no-m1",
                 "--paper-models-csv", str(tmp_path / "pm.csv")], now_fn=lambda: NOW, env={})
    assert rc == 0
    satirlar = {s.split(",")[0]: s for s in (tmp_path / "pm.csv").read_text().splitlines()}
    m1 = satirlar["ortak_filtre_aile_M1_2026-12-01"]
    assert "durum=ok" in m1 and "n=22" in m1 and "M1@15m=8" in m1 and "aile=M1" in m1
    assert "durum=az_islem" in satirlar["ortak_filtre_aile_T1_2026-12-01"]
    assert (tmp_path / "models" / "ortak_filtre" / "aile_M1.json").exists()


def test_kaldirilan_kol_icin_aile_paketi_uretilmez(tmp_path):
    adaylar = _adaylar("C1@1h", 20) + _adaylar("T1@1h", 20)
    r = OF.egit_hepsi(adaylar, tmp_path, NOW, kollar=["T1@1h", "T1@4h"])
    assert list(r["aileler"]) == ["T1"]
    assert sorted(p.name for p in tmp_path.glob("aile_*.json") if not p.name.endswith(".sinama.json")) == ["aile_T1.json"]
    assert "C1" not in json.dumps(r)
    r2 = OF.egit_hepsi(adaylar, tmp_path / "b", NOW)                     # kollar verilmezse eski davranis
    assert sorted(r2["aileler"]) == ["C1", "T1"]


def test_ml_retrain_config_kollari_okunur(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ml_retrain_run_t", ROOT / "scripts" / "ml_retrain_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"arms": ["T1@1h", "M1@4h"]}))
    assert mod._config_arms(p) == ["T1@1h", "M1@4h"]
    assert mod._config_arms(tmp_path / "yok.json") is None


def test_ml_retrain_kaldirilan_kol_paketi_yazilmaz(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ml_retrain_run_t2", ROOT / "scripts" / "ml_retrain_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    seen = {}
    monkeypatch.setattr(mod.L, "open_ledger", lambda *a, **k: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(mod.T, "collect_rows", lambda *a, **k: [{"arm_id": "C1@1h"}, {"arm_id": "T1@1h"}])
    monkeypatch.setattr(mod.T, "train_all", lambda rows, **k: (seen.setdefault("rows", rows) and {}, {"lock_dropped": 0}))
    cfgp = tmp_path / "c.json"
    cfgp.write_text(json.dumps({"arms": ["T1@1h"]}))
    mod.main(["--once", "--ledger", str(tmp_path / "x.sqlite"), "--models-dir", str(tmp_path / "sf"), "--no-m1",
              "--paper-models-csv", str(tmp_path / "p.csv"), "--paper-config", str(cfgp)], now_fn=lambda: NOW)
    assert seen["rows"] == [{"arm_id": "T1@1h"}]
