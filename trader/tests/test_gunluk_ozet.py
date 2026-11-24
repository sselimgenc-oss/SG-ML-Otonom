"""ML gunluk ozet yayini testleri (docs/standart/gunluk-ozet-v1-spec.md). Sentetik girdi; ag yok; gercek veri okunmaz."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from trader_core import gunluk_ozet as G

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)         # TSI 15:00 -> gun 2026-11-19 (21:00Z sinirli: 11-18T21:00Z .. 11-19T21:00Z)
GUN_BASI = datetime(2026, 11, 18, 21, 0, tzinfo=UTC)

ANAHTARLAR = {"sema", "proje", "mod", "uretim", "gun", "kasa", "islem", "hesaplar", "ogrenme", "rejim", "drift_uyari",
              "limitler", "saglik", "notlar"}


def tr(exit_ts, pnl, entry_ts=None):
    return NS(exit_ts=exit_ts, realized_pnl=pnl, entry_ts=entry_ts or exit_ts - timedelta(hours=1))


def cand(arm, taken, ts, r):
    return {"arm_id": arm, "taken": taken, "ts": ts, "r": r, "decision_id": 1, "asset_class": "kripto"}


def tum_anahtarlar(doc):
    return (set(doc) == ANAHTARLAR and set(doc["kasa"]) == {"baslangic", "simdi", "gun_pnl", "toplam_pnl", "zirveden_dusus_yuzde"}
            and set(doc["islem"]) == {"gun_acilan", "gun_kapanan", "kazanan", "kaybeden", "acik_pozisyon", "alinmayan_sinyal"}
            and set(doc["ogrenme"]) == {"aktif_ders", "yeni_ders", "emekli_ders", "filtre_aktif"}
            and set(doc["limitler"]) == {"gunluk_kayip_yuzde", "kaldirac_tavan", "durdu_mu"}
            and set(doc["saglik"]) == {"son_nabiz", "hata_sayisi_gun"})


def test_bos_girdi_tum_anahtarlar_null():
    d = G.uret(G.Girdi(), NOW)
    assert tum_anahtarlar(d)
    assert (d["sema"], d["proje"], d["mod"]) == ("ortak.gunluk_ozet.v1", "ML", "kagit")
    assert d["uretim"] == "2026-11-19T12:00:00Z"
    for blok in ("kasa", "islem", "ogrenme", "limitler", "saglik"):
        assert all(v is None for v in d[blok].values()), blok
    assert d["hesaplar"] is None and d["rejim"] is None and d["drift_uyari"] is None and d["notlar"] == []
    json.dumps(d)


def test_gun_siniri_2100z():
    assert G.gun_sinirlari(datetime(2026, 11, 19, 20, 59, 59, tzinfo=UTC))[0] == "2026-11-19"
    g, a, b = G.gun_sinirlari(datetime(2026, 11, 19, 21, 0, 0, tzinfo=UTC))
    assert g == "2026-11-20" and a == datetime(2026, 11, 19, 21, 0, tzinfo=UTC) and b == datetime(2026, 11, 20, 21, 0, tzinfo=UTC)
    assert G.gun_sinirlari(datetime(2026, 11, 19, 0, 0, tzinfo=UTC))[0] == "2026-11-19"
    with pytest.raises(ValueError):
        G.gun_sinirlari(datetime(2026, 11, 19, 12, 0))


def test_gun_siniri_islem_sayimi():
    ic = GUN_BASI                                   # dahil
    dis = GUN_BASI - timedelta(seconds=1)           # onceki gun
    g = G.Girdi(wallet_start=1000.0, acik=[NS(entry_ts=GUN_BASI + timedelta(hours=2))],
                kapanan=[tr(ic, 10.0, entry_ts=dis), tr(dis, -5.0, entry_ts=dis - timedelta(hours=3)),
                         tr(NOW, -2.0, entry_ts=NOW - timedelta(hours=1))])
    d = G.uret(g, NOW)
    assert d["islem"] == {"gun_acilan": 2, "gun_kapanan": 2, "kazanan": 1, "kaybeden": 1, "acik_pozisyon": 1,
                          "alinmayan_sinyal": None}
    assert d["kasa"]["gun_pnl"] == 8.0 and d["kasa"]["toplam_pnl"] == 3.0
    assert d["kasa"]["baslangic"] == 1000.0 and d["kasa"]["simdi"] == 1003.0


def test_dusus_ve_yuvarlama():
    t0 = NOW - timedelta(days=3)
    kap = [tr(t0, 100.0), tr(t0 + timedelta(hours=1), -150.0), tr(t0 + timedelta(hours=2), 20.0),
           tr(t0 + timedelta(hours=3), 0.0049)]
    d = G.uret(G.Girdi(wallet_start=1000.0, kapanan=kap), NOW)
    # ozkaynak 1100 zirve -> 950 cukur: 150/1100
    assert d["kasa"]["zirveden_dusus_yuzde"] == round(150 / 1100 * 100, 2) == 13.64
    assert d["kasa"]["toplam_pnl"] == -29.99 or d["kasa"]["toplam_pnl"] == round(100 - 150 + 20 + 0.0049, 2)
    assert d["kasa"]["simdi"] == round(1000 - 29.9951, 2)
    # baslangic yoksa dusus ve simdi null
    d2 = G.uret(G.Girdi(kapanan=kap), NOW)
    assert d2["kasa"]["zirveden_dusus_yuzde"] is None and d2["kasa"]["simdi"] is None
    assert d2["kasa"]["toplam_pnl"] is not None


def test_hesaplar_sanal_kasa_ve_siralama():
    dun = GUN_BASI - timedelta(hours=5)
    bugun = GUN_BASI + timedelta(hours=1)
    adaylar = [cand("M1@1h", True, dun, 1.0), cand("M1@4h", True, bugun, 2.0),
               cand("PA1@1h", True, dun, 3.0), cand("PA1@1h", False, bugun, 5.0),      # alinmayan sayilmaz
               cand("Q1@1h", True, bugun, -1.0), cand("Q1@1h", True, bugun, None)]       # cozulmemis sayilmaz
    d = G.uret(G.Girdi(adaylar=adaylar, kurulumlar=["M1@1h", "M1@4h", "PA1@1h", "Q1@1h", "X1@1h"]), NOW)
    h = {x["ad"]: x for x in d["hesaplar"]}
    assert h["PA1"] == {"ad": "PA1", "gun_pnl": 0.0, "toplam_pnl": 30.0, "islem": 1}
    assert h["M1"] == {"ad": "M1", "gun_pnl": 20.2, "toplam_pnl": 30.2, "islem": 2}
    assert h["Q1"] == {"ad": "Q1", "gun_pnl": -10.0, "toplam_pnl": -10.0, "islem": 1}
    assert h["X1"] == {"ad": "X1", "gun_pnl": 0.0, "toplam_pnl": 0.0, "islem": 0}
    assert [x["ad"] for x in d["hesaplar"]] == ["M1", "PA1", "X1", "Q1"]      # toplam_pnl azalan
    assert "en iyi kurulum: M1" in d["notlar"]
    for x in d["hesaplar"]:
        assert set(x) == {"ad", "gun_pnl", "toplam_pnl", "islem"}


def test_ogrenme_sayilari():
    def a(kind, actor, ts):
        return NS(kind=kind, actor=actor, activated_at=ts)
    ic = GUN_BASI + timedelta(hours=1)
    acts = [a("apply", "lesson", ic), a("apply", "lesson", GUN_BASI - timedelta(days=2)), a("apply", "user", ic),
            a("rollback", "lesson", ic), a("apply", "lesson", GUN_BASI - timedelta(days=5))]
    d = G.uret(G.Girdi(aktivasyonlar=acts), NOW)
    assert d["ogrenme"] == {"aktif_ders": 2, "yeni_ders": 1, "emekli_ders": 1, "filtre_aktif": None}   # 24.11: ML filtreleri silindi (sema anahtari hep null)


def test_notlar_en_fazla_5_ve_sirsiz():
    g = G.Girdi(notlar=[f"not {i} " + "x" * 200 for i in range(9)], rejim="range", drift_uyari=False,
                gunluk_kayip_yuzde=8.0, kaldirac_tavan=5, durdu_mu=False, son_nabiz="2026-11-19T11:55:00Z", hata_sayisi_gun=0)
    d = G.uret(g, NOW)
    assert len(d["notlar"]) == 5 and all(len(n) <= 80 for n in d["notlar"])
    assert d["limitler"] == {"gunluk_kayip_yuzde": 8.0, "kaldirac_tavan": 5.0, "durdu_mu": False}
    assert d["saglik"] == {"son_nabiz": "2026-11-19T11:55:00Z", "hata_sayisi_gun": 0}
    txt = json.dumps(d).lower()
    assert not re.search(r"token|secret|api_key|password|@\w+\.\w+", txt)


# ------------------------------------------------------------------ CLI / kaynak okuma
def _cfg(tmp_path: Path, *, panel: bool = True) -> Path:
    c = tmp_path / "root" / "config"
    c.mkdir(parents=True)
    (c / "engine.base.json").write_text(json.dumps({"mode": "paper", "wallet_start": 1000.0, "target_trade_risk": 0.01,
                                                    "market_db": "var/market.sqlite"}))
    (c / "engine.learner.json").write_text('{"bot": "learner"}')
    (c / "engine.paper.json").write_text(json.dumps({"risk": {"daily_max_loss": 0.08}, "arms": ["M1@1h", "Q1@1h"]}))
    if panel:
        (c / "panel.json").write_text(json.dumps({"ledger_path": "var/learner/ledger.sqlite", "kill_file": "shared/KILL",
                                                  "status_path": "var/learner/status.json",
                                                  "health_state": "var/health/state.json"}))
    return c


def test_cli_atomik_yazar_ve_eksik_kaynak_null(tmp_path):
    c = _cfg(tmp_path)
    out = tmp_path / "site" / "gunluk_ozet_v1.json"
    rc = G.main(["--config-dir", str(c), "--env", "paper", "--out", str(out)], environ={}, now=NOW)
    assert rc == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert tum_anahtarlar(d)
    assert d["kasa"]["baslangic"] == 1000.0 and d["kasa"]["toplam_pnl"] is None
    assert d["limitler"]["gunluk_kayip_yuzde"] == 8.0 and d["limitler"]["kaldirac_tavan"] == 5.0
    assert d["rejim"] is None and d["drift_uyari"] is None and d["ogrenme"]["filtre_aktif"] is None
    assert sorted(p.name for p in out.parent.iterdir()) == ["gunluk_ozet_v1.json"]      # gecici dosya kalmadi


def test_cli_hata_sifir_olmayan_cikis_dosya_yok(tmp_path, capsys):
    out = tmp_path / "o" / "x.json"
    rc = G.main(["--config-dir", str(tmp_path / "yok"), "--out", str(out)], environ={}, now=NOW)
    assert rc == 1 and not out.exists() and not out.parent.exists()
    assert "HATA" in capsys.readouterr().err


def test_cli_atomik_yazma_hatasinda_mevcut_dosya_korunur(tmp_path, monkeypatch):
    c = _cfg(tmp_path)
    out = tmp_path / "ozet.json"
    out.write_text("{\"eski\": 1}")
    monkeypatch.setattr(G, "uret", lambda g, now: {"x": object()})        # json.dump basarisiz olur
    assert G.main(["--config-dir", str(c), "--out", str(out)], environ={}, now=NOW) == 1
    assert out.read_text() == "{\"eski\": 1}"
    assert [p.name for p in tmp_path.iterdir() if p.name != "root"] == ["ozet.json"]


def test_cli_gercek_defter_okuma(tmp_path):
    import panel_support as PS
    c = _cfg(tmp_path)
    root = c.parent
    (root / "var" / "learner").mkdir(parents=True)
    bar = PS.NOW - timedelta(hours=2)
    PS.mkledger(root / "var" / "learner" / "ledger.sqlite", "learner", [(True, True, bar), (False, True, bar - timedelta(hours=3)), (True, False, bar - timedelta(hours=6))])
    out = tmp_path / "o.json"
    assert G.main(["--config-dir", str(c), "--out", str(out)], environ={}, now=PS.NOW) == 0
    d = json.loads(out.read_text())
    assert tum_anahtarlar(d) and d["gun"] == PS.DAY
    assert d["islem"]["gun_kapanan"] == 2 and d["islem"]["acik_pozisyon"] == 1 and d["islem"]["gun_acilan"] == 3
    assert d["islem"]["kazanan"] == 1 and d["islem"]["kaybeden"] == 1
    assert {h["ad"] for h in d["hesaplar"]} >= {"M1", "Q1", "R1"}


def test_veri_koku_ortam_degiskeni(tmp_path):
    c = _cfg(tmp_path)
    veri = tmp_path / "veri"
    (veri / "var" / "health").mkdir(parents=True)
    (veri / "var" / "health" / "state.json").write_text(json.dumps(
        {"last_run_at": "2026-11-19T11:58:00Z", "last_overall": "OK",
         "fingerprints": {"a|x": {"level": "WARN"}, "b|y": {"level": "CRIT"}, "c|z": {"level": "OK"}}}))
    out = tmp_path / "o.json"
    assert G.main(["--config-dir", str(c), "--out", str(out)], environ={"TRADER_DATA_ROOT": str(veri)}, now=NOW) == 0
    d = json.loads(out.read_text())
    assert d["saglik"] == {"son_nabiz": "2026-11-19T11:58:00Z", "hata_sayisi_gun": 2}


# ------------------------------------------------------------------ yayin baglama
def test_worker_yeni_yol_parolasiz_ve_baslikli_statik():
    t = (DEPLOY / "panel_worker.js").read_text(encoding="utf-8")
    dal = t.index('pathname === "/gunluk_ozet_v1.json"')
    auth = t.index("if (!saltOkuma(istek))")
    assert dal < auth
    kosul = t[t.rfind("if (", 0, dal):dal]
    assert '"GET"' in kosul and '"HEAD"' in kosul
    govde = t[dal:t.index("if (!saltOkuma(istek))", dal)]
    for h in ('"Content-Type", "application/json"', '"Cache-Control", "no-store"', '"Access-Control-Allow-Origin", "*"'):
        assert h in govde


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_worker_davranis(tmp_path):
    js = tmp_path / "t.mjs"
    js.write_text(f"""import w from {str(DEPLOY / 'panel_worker.js')!r};
const env = {{ASSETS: {{fetch: async () => new Response('{{"a":1}}')}}}};
const rq = (p, m) => new Request('https://x' + p, {{method: m || 'GET'}});
for (const m of ['GET', 'HEAD']) {{
  const r = await w.fetch(rq('/gunluk_ozet_v1.json', m), env);
  if (r.status !== 200) throw new Error('acik yol ' + m + ' ' + r.status);
  if (r.headers.get('Content-Type') !== 'application/json' || r.headers.get('Cache-Control') !== 'no-store'
      || r.headers.get('Access-Control-Allow-Origin') !== '*') throw new Error('baslik ' + m);
}}
let r = await w.fetch(rq('/gunluk_ozet_v1.json', 'POST'), env); if (r.status !== 405) throw new Error('POST acik');
for (const p of ['/', '/api/status', '/gunluk_ozet_v1.json/x']) {{     // 20 Kasim: pano kilitsiz, yalniz okuma
  r = await w.fetch(rq(p), env); if (r.status !== 200) throw new Error('pano okunamadi: ' + p);
  if (r.headers.get('Access-Control-Allow-Origin')) throw new Error('pano CORS acmamali: ' + p);
}}
r = await w.fetch(rq('/rejim.json'), env); if (r.status !== 200) throw new Error('rejim.json bozuldu');
""", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type":"module"}')
    r = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_yayin_betigi_uretir_ve_yalniz_uyarir():
    t = (DEPLOY / "panel_yayinla.sh").read_text(encoding="utf-8")
    assert subprocess.run(["bash", "-n", str(DEPLOY / "panel_yayinla.sh")], capture_output=True).returncode == 0
    assert "-m trader_core.gunluk_ozet" in t and '--out "$gecici/site/gunluk_ozet_v1.json"' in t
    i = t.index("-m trader_core.gunluk_ozet")
    blok = t[t.rfind("\nif ", 0, i):t.index("\nfi\n", i)]
    assert blok.lstrip().startswith("if ! ") and "UYARI" in blok and "exit" not in blok
    assert i < t.index("wrangler.jsonc") and i < t.index("deploy --config")


def test_modul_yasak_degil():
    t = (ROOT / "src/trader_core/gunluk_ozet.py").read_text(encoding="utf-8")
    assert not re.search(r"(?m)^\s*(from|import)\s+trader_engine", t)


def test_duygu_notu_yok():
    """Duygu (Fear&Greed) gunluk ozete girmez: Girdi'de alan, uret'te not, okuyucu yok (21 Kasim 2026 silme karari)."""
    import dataclasses
    assert "duygu" not in {f.name for f in dataclasses.fields(G.Girdi)} and not hasattr(G, "_duygu")
    with pytest.raises(TypeError):
        G.Girdi(duygu={"deger": 28, "sinif": "Fear"})
    d = G.uret(G.Girdi(notlar=["a", "b"]), NOW)
    assert d["notlar"] == ["a", "b"] and not any("Duygu" in n for n in d["notlar"])
