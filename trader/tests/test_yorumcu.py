"""YZ yorumcu (ust lig §3): tablo kurucu, sayi kontrolu, n<30 dili, butce reddi, sahte batch istemcisiyle bastan sona, koruma testleri."""
from __future__ import annotations

import importlib.util
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import budget as B
from trader_core import ortak as LS
from trader_reports import yorumcu as Y

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 24, 5, 40, tzinfo=UTC)


def _betik():
    s = importlib.util.spec_from_file_location("yorumcu_run", ROOT / "scripts" / "yorumcu_run.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def trade(i, arm, r, exit_ts="2026-11-23T10:00:00.000Z", entry_ts="2026-11-23T06:00:00.000Z"):
    return {"trade_id": i, "pair": "BTC/USDT", "side": "long", "arm": arm, "tf": "1h", "regime": "trend", "asset": "kripto",
            "entry_ts": entry_ts, "exit_ts": exit_ts, "planned_risk": 10.0, "net_r": r, "gross_pnl": 1.0, "pnl": 0.5}


def ledger():
    """40 islem M1@1h (n>=30), 5 islem S2@1h (n<30), 1 kilitli donem islemi (elenmeli)."""
    tr = [trade(i, "M1@1h", 0.5 if i % 2 else -0.25) for i in range(40)]
    tr += [trade(100 + i, "S2@1h", -1.0) for i in range(5)]
    tr.append(trade(999, "M1@1h", 7.77, entry_ts="2026-06-01T00:00:00.000Z", exit_ts="2026-06-01T05:00:00.000Z"))
    dec = [{"id": i, "pair": "BTC/USDT", "side": "long", "arm": "M1@1h", "regime": "trend", "asset": "kripto",
            "bar_close_ts": "2026-11-23T06:00:00.000Z", "final_action": "open" if i < 3 else "skip",
            "skip_reason": None if i < 3 else "ml_filtre", "ml_score": 0.5} for i in range(10)]
    return tr, dec


def tablolar():
    tr, dec = ledger()
    return Y.tablolari_kur(tr, dec, NOW, haftalik_sabit=["Tutarlılık: eşleşme %98"])


# ------------------------------------------------------------------ tablo kurucu
@pytest.mark.usefixtures("kilitli_donem")
def test_tablo_kurucu_sayilar_kodla_ve_kilitli_donem_elenir():
    t = tablolar()
    assert t["tarih"] == "2026-11-24" and t["kilitli_donem_atilan_islem"] == 1 and t["toplam_kapanmis_islem"] == 45
    k = {r["kol"]: r for r in t["kollar"]}
    assert k["M1@1h"]["n"] == 40 and k["M1@1h"]["toplam_R"] == 5.0 and k["M1@1h"]["etiket"] == ""
    assert k["S2@1h"]["n"] == 5 and k["S2@1h"]["toplam_R"] == -5.0 and k["S2@1h"]["etiket"] == "yetersiz örnek"
    assert t["dun"]["gun"] == "2026-11-23" and t["dun"]["kapanan_n"] == 45
    assert t["kararlar"]["eylem"] == {"open": 3, "skip": 7} and t["kararlar"]["en_sik_red_nedenleri"] == [{"neden": "ml_filtre", "n": 7}]
    assert "7.77" not in Y.tablo_metni(t)                     # kilitli donem islemi hicbir tabloya sizmaz
    p = Y.parametreler(t)
    assert p["model"] == "claude-sonnet-5-5" and "Kapanmış" not in p["system"] and "M1@1h" in p["messages"][0]["content"]


# ------------------------------------------------------------------ sayi kontrolu
def test_sayi_kontrolu_gecer_ve_kalir():
    t = tablolar()
    girdi = Y.tablo_metni(t)
    iyi = "## Bulgular\n- M1@1h: n=40, toplam 5,0 R.\n## Öneriler\nÖneri 1: bak. Nasıl ölçülür: 7 gün sonra tekrar."
    assert Y.sayi_kontrolu(iyi, girdi) == []
    kotu = "- M1@1h toplam 5,0 R ve ortalama 0,1234 R."
    assert Y.sayi_kontrolu(kotu, girdi) == ["0.1234"]
    metin, d = Y.raporu_denetle("## Bulgular\n- M1@1h n=40 toplam 12,75 R", t)
    assert metin.startswith("# Yorumcu raporu 2026-11-24") and "SAYI HATASI" in metin.split("## Bulgular")[0] and d["sayi_hatasi"] == ["12.75"]
    temiz, d2 = Y.raporu_denetle("## Bulgular\n- M1@1h n=40 toplam 5,0 R", t)
    assert "SAYI HATASI" not in temiz and d2["sayi_hatasi"] == []


def test_n30_alti_satira_yetersiz_ornek_eklenir():
    t = tablolar()
    metin, _ = Y.raporu_denetle("## Bulgular\n- S2@1h kaybediyor, n=5.\n- M1@1h n=40 toplam 5,0 R.\n- S2@1h yine kötü, n=5, yetersiz örnek.", t)
    satirlar = {ln for ln in metin.splitlines()}
    assert "- S2@1h kaybediyor, n=5. (yetersiz örnek, n=5)" in satirlar
    assert "- M1@1h n=40 toplam 5,0 R." in satirlar                 # n>=30: dokunulmaz
    assert "- S2@1h yine kötü, n=5, yetersiz örnek." in satirlar    # zaten var: tekrar eklenmez


def test_en_cok_3_oneri_ve_nasil_olculur():
    t = tablolar()
    m = ("## Öneriler\nÖneri 1: a. Nasıl ölçülür: x.\nÖneri 2: b.\nÖneri 3: c. Nasıl ölçülür: y.\nÖneri 4: d. Nasıl ölçülür: z.\n")
    metin, d = Y.raporu_denetle(m, t)
    assert "Öneri 4" not in metin and metin.count("Öneri ") == 3
    assert any("fazla öneri" in u for u in d["uyarilar"]) and any("Nasıl ölçülür" in u for u in d["uyarilar"])
    assert "Nasıl ölçülür: belirtilmedi" in metin


# ------------------------------------------------------------------ betik: sahte batch istemcisi
class FakeClient:
    def __init__(self, text, usage=None, fail=None):
        self.text, self.fail, self.submitted, self.polls = text, fail, [], 0
        self.usage = usage or {"input_tokens": 3000, "output_tokens": 400}

    def submit(self, bundle, custom_id):
        if self.fail:
            raise LS.LlmConnectionError("ag")
        self.submitted.append((bundle.params, custom_id))
        return "batch_1"

    def poll(self, batch_id):
        self.polls += 1
        if self.polls < 2:
            return LS.BatchPoll("in_progress")
        return LS.BatchPoll("ended", (LS.BatchResult(self.submitted[0][1], "succeeded", self.text, "end_turn", self.usage),))

    def cancel(self, batch_id):
        pass


class Hata(FakeClient):
    def poll(self, batch_id):
        return LS.BatchPoll("ended", (LS.BatchResult("yorumcu-gunluk", "errored"),))


def gercek_butce(tmp_path):
    d = json.loads((ROOT / "config" / "budget.json").read_text())
    d["db_path"] = str(tmp_path / "b.sqlite")
    (tmp_path / "budget.json").write_text(json.dumps(d))
    g = B.BudgetGuard(B.load_config(tmp_path / "budget.json"))
    return g, SimpleNamespace(authorize=g.authorize, record=g.record, release=g.release, estimate_cost=g.estimate_cost,
                              api_key_env=lambda s: B.load_config(tmp_path / "budget.json").api_key_env[s])


@pytest.fixture
def betik(tmp_path, monkeypatch):
    m = _betik()
    tr, dec = ledger()
    cfg = SimpleNamespace()
    monkeypatch.setattr(m, "defteri_oku", lambda root: (cfg, tmp_path / "ledger.sqlite", tr, dec))
    monkeypatch.setattr(m, "data_root", lambda env: tmp_path)
    return m


MODEL_CEVABI = ("## Bulgular\n- M1@1h: n=40, toplam 5,0 R.\n- S2@1h: n=5, toplam -5,0 R; yetersiz örnek.\n"
                "## Öneriler\nÖneri 1: S2@1h izlensin. Nasıl ölçülür: kapanan işlem sayısı 30'a ulaşınca ort. R bakılır.\n")


def test_bastan_sona_sahte_istemci_rapor_telegram_ve_butce(betik, tmp_path):
    g, b = gercek_butce(tmp_path)
    c = FakeClient(MODEL_CEVABI)
    rc = betik.main(["--once"], client=c, budget=b, now_fn=lambda: NOW, env={}, sleep=lambda s: None)
    assert rc == 0 and len(c.submitted) == 1 and c.submitted[0][0]["model"] == "claude-sonnet-5-5"
    md = (tmp_path / "var" / "durum" / "yorumcu" / "2026-11-24.md").read_text(encoding="utf-8")
    assert "SAYI HATASI" not in md and "Öneri 1" in md and "Nasıl ölçülür" in md and "yetersiz örnek" in md
    # yalniz kendi dizinine yazildi
    yazilan = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file() and p.suffix == ".md"}
    assert yazilan == {"var/durum/yorumcu/2026-11-24.md"}
    ob = list((tmp_path / "var" / "telegram" / "outbox").glob("*.json"))
    tx = json.loads(ob[0].read_text())["text"]
    assert len(ob) == 1 and tx.startswith("Yorumcu raporu 2026-11-24")
    # tam rapor, sade metin: markdown isareti ve acilmayan dosya yolu yok
    assert "Nasıl ölçülür" in tx and "**" not in tx and "##" not in tx and ".md" not in tx and "📌 Bulgular" in tx
    assert g.status().services["yorumcu"].used_usd > 0
    # ayni gun ikinci kosu: tekrar yok
    c2 = FakeClient(MODEL_CEVABI)
    betik.main(["--once"], client=c2, budget=b, now_fn=lambda: NOW, env={}, sleep=lambda s: None)
    assert c2.submitted == []


def test_model_uydurma_sayi_yazarsa_rapor_sayi_hatasi_ile_baslar(betik, tmp_path):
    _, b = gercek_butce(tmp_path)
    betik.main(["--once"], client=FakeClient("## Bulgular\n- M1@1h n=40 toplam 99,5 R."), budget=b, now_fn=lambda: NOW, env={}, sleep=lambda s: None)
    md = (tmp_path / "var" / "durum" / "yorumcu" / "2026-11-24.md").read_text(encoding="utf-8")
    assert "SAYI HATASI" in md.split("## Bulgular")[0]


def test_butce_reddi_api_cagrisi_yok(betik, tmp_path):
    g, b = gercek_butce(tmp_path)
    g.authorize("yorumcu", 0.15)                               # gunluk payi (0.15 $) doldur
    c = FakeClient(MODEL_CEVABI)
    rc = betik.main(["--once"], client=c, budget=b, now_fn=lambda: NOW, env={}, sleep=lambda s: None)
    assert rc == 0 and c.submitted == [] and c.polls == 0
    md = (tmp_path / "var" / "durum" / "yorumcu" / "2026-11-24.md").read_text(encoding="utf-8")
    assert "bugün rapor yok: bütçe" in md


def test_api_hatasi_ve_anahtar_yok_rapor_yok_cikis_0(betik, tmp_path):
    g, b = gercek_butce(tmp_path)
    rc = betik.main(["--once"], client=FakeClient("x", fail=True), budget=b, now_fn=lambda: NOW, env={}, sleep=lambda s: None)
    assert rc == 0
    md = (tmp_path / "var" / "durum" / "yorumcu" / "2026-11-24.md").read_text(encoding="utf-8")
    assert md.startswith("# Yorumcu raporu 2026-11-24") and "bugün rapor yok: API hatası" in md
    assert g.status().services["yorumcu"].used_usd == 0            # rezerv serbest birakildi
    betik.main(["--once", "--force"], client=Hata("x"), budget=b, now_fn=lambda: NOW, env={}, sleep=lambda s: None)
    assert "bugün rapor yok: model cevap vermedi" in (tmp_path / "var" / "durum" / "yorumcu" / "2026-11-24.md").read_text(encoding="utf-8")
    # anahtar yok (istemci verilmedi, ortamda anahtar yok)
    betik.main(["--once", "--force"], budget=b, now_fn=lambda: NOW, env={}, sleep=lambda s: None)
    assert "bugün rapor yok: API anahtarı yok" in (tmp_path / "var" / "durum" / "yorumcu" / "2026-11-24.md").read_text(encoding="utf-8")


def test_yazma_yalniz_kendi_dizinine(tmp_path):
    m = _betik()
    d = tmp_path / "yorumcu"
    assert m.yaz(d, "2026-11-24", "x").parent == d.resolve()
    for kotu in ("../x", "2026-11-24/../../a", "x"):
        with pytest.raises(ValueError):
            m.yaz(d, kotu, "x")


# ------------------------------------------------------------------ koruma: yetkisiz, motor okumaz, derse bagli degil, kilitli donem
def test_motor_yorumcu_dizinini_okumaz_ve_derse_bagli_degil():
    src = ROOT / "src"
    yasak = re.compile(r"yorumcu", re.I)
    bulunan = [p.relative_to(src).as_posix() for p in (src / "trader_engine").rglob("*.py") if yasak.search(p.read_text(encoding="utf-8"))]
    assert bulunan == [], f"motor modulu yorumcu cikti dizinine/modulune bakiyor: {bulunan}"
    for kok in ("trader_core", "trader_ml", "trader_panel"):
        for p in (src / kok).rglob("*.py"):
            t = p.read_text(encoding="utf-8")
            # budget.py/telegram.py yalniz servis adini tasir (ad haritasi); yorumcu modulunu ice alan/dosya yolunu okuyan yok
            assert not re.search(r"trader_reports\.yorumcu|trader_reports import yorumcu|durum/yorumcu|var/durum.{0,20}yorumcu", t), p.name
    mod = (src / "trader_reports" / "yorumcu.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+.*(trader_engine)", mod, re.M)
    assert "open(" not in mod and "write_text" not in mod and "sqlite3" not in mod       # saf hesap: dosya acmaz


@pytest.mark.usefixtures("kilitli_donem")
def test_kilitli_donem_okunmaz():
    mod = (ROOT / "src" / "trader_reports" / "yorumcu.py").read_text(encoding="utf-8")
    assert "holdout_filtrele" in mod and "2026-05-01" not in mod and "HOLDOUT" not in mod.replace("(HOLDOUT)", "")
    betik = (ROOT / "scripts" / "yorumcu_run.py").read_text(encoding="utf-8")
    assert "2026-05-01" not in betik and "sqlite3.connect" not in betik
    t = Y.tablolari_kur([trade(1, "M1@1h", 3.21, entry_ts="2026-07-01T00:00:00.000Z", exit_ts="2026-07-01T04:00:00.000Z")], [
        {"id": 1, "pair": "BTC/USDT", "side": "long", "arm": "M1@1h", "regime": "x", "asset": "k", "bar_close_ts": "2026-07-01T00:00:00.000Z",
         "final_action": "open", "skip_reason": None, "ml_score": None}], NOW)
    assert t["toplam_kapanmis_islem"] == 0 and t["kilitli_donem_atilan_islem"] == 1 and t["kararlar"]["n_karar"] == 0 and t["kollar"] == []


# ------------------------------------------------------------------ dagitim kablolari
def test_dagitim_kablolari():
    dep = ROOT / "deploy"
    svc = (dep / "trader-yorumcu.service").read_text(encoding="utf-8")
    assert "yorumcu_run.py --once" in svc and "ProtectSystem=strict" in svc and "ReadWritePaths=/opt/trader/var/durum/yorumcu " in svc
    assert "/opt/trader/var/durum " not in svc and not re.search(r"ReadWritePaths=.*/opt/trader/var/learner", svc)
    assert "OnCalendar=*-*-* 05:40:00 UTC" in (dep / "trader-yorumcu.timer").read_text(encoding="utf-8")
    inst = (dep / "install.sh").read_text(encoding="utf-8")
    assert "enable_now trader-yorumcu.timer" in inst and "var/durum/yorumcu" in inst
    assert "yorumcu_son.md" in (dep / "durum_yayinla.sh").read_text(encoding="utf-8")
    assert re.search(r"^ANTHROPIC_API_KEY_YORUMCU=$", (dep / "trader-lesson.env.example").read_text(encoding="utf-8"), re.M)
    cfg = json.loads((ROOT / "config" / "budget.json").read_text())
    assert cfg["api_key_env"]["yorumcu"] == "ANTHROPIC_API_KEY_YORUMCU" and "yorumcu" in cfg["daily_cap_usd"]


def test_telegram_uzun_rapor_sirali_parcalara_bolunur_hic_satir_kaybolmaz():
    from trader_reports import yorumcu as Y
    satirlar = [f"- madde {i}: " + "x" * 90 for i in range(120)]
    metin = "# Yorumcu raporu 2026-11-24\n\n**SAYI HATASI**: deneme.\n\n## Bulgular\n" + "\n".join(satirlar)
    ps = Y.telegram_parcalari(metin, "2026-11-24")
    n = len(ps)
    assert n > 1 and all(len(p) <= Y.TG_PARCA + 40 for p in ps)
    assert [p.split("\n", 1)[0] for p in ps] == [f"Yorumcu raporu 2026-11-24 ({i}/{n})" for i in range(1, n + 1)]
    birlesik = "\n".join(p.split("\n\n", 1)[1] for p in ps)
    assert all(f"• madde {i}: " in birlesik for i in range(120))
    assert "⚠️ Dikkat:" in ps[0] and "**" not in birlesik and "#" not in birlesik


def test_telegram_parcalari_outbox_sirasiyla_yazilir(betik, tmp_path):
    from trader_core.telegram import Outbox
    from trader_reports import yorumcu as Y
    metin = "## Bulgular\n" + "\n".join(f"- satir {i} " + "y" * 200 for i in range(60))
    assert betik.telegram_gonder(tmp_path, {}, "2026-11-24", metin, NOW)
    ob = Outbox(tmp_path / "var" / "telegram", lambda: NOW)
    yazilan = [json.loads(p.read_text())["text"] for p in sorted(ob.list())]
    assert yazilan == Y.telegram_parcalari(metin, "2026-11-24") and len(yazilan) > 1


def test_dun_tablosu_istanbul_gunune_gore():
    """25.11 denetim #24: "dun" Istanbul gunu (UTC+3); UTC gunu degil."""
    tr = [trade(1, "M1@1h", 1.0, exit_ts="2026-11-22T20:59:59.000Z"),    # 22'si 23:59 TR -> dun degil
          trade(2, "M1@1h", 2.0, exit_ts="2026-11-22T21:00:00.000Z"),    # 23'u 00:00 TR -> dun
          trade(3, "M1@1h", 4.0, exit_ts="2026-11-23T20:59:59.000Z"),    # 23'u 23:59 TR -> dun
          trade(4, "M1@1h", 8.0, exit_ts="2026-11-23T21:00:00.000Z")]    # 24'u 00:00 TR -> bugun
    d = Y.dun_tablosu(tr, NOW)
    assert d["gun"] == "2026-11-23" and d["kapanan_n"] == 2 and d["toplam_R"] == 6.0
