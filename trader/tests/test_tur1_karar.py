"""Tur 1 gunluk karar satiri (degisim tespiti, outbox, hata dayanikliligi) ve haftalik YZ yorumu (sahte istemci/butce)."""
from __future__ import annotations

import importlib.util
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trader_core import lesson as LS
from trader_reports import tur1_karar as K

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 29, 5, 10, tzinfo=timezone.utc)      # pazar


def _betik(ad):
    s = importlib.util.spec_from_file_location(ad, ROOT / "scripts" / f"{ad}.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def madde(ad, gecti, deger):
    return {"ad": ad, "gecti": gecti, "deger": deger, "sonuc": "PASS" if gecti else "FAIL"}


def rapor(n=55, rastgele=False, dusus=False, net=True, masraf=True, rejim=True, pct=40.0, p95=31.2):
    return {"canli_sartlari": {"maddeler": [
        madde("En az 300 kapanmış işlem", n >= 300, f"n = {n}"),
        madde("Masraf sonrası net > 0 ve güven alt sınırı > 0", net, "net = +3.20 R; ort = +0.058 R; alt sınır = +0.010"),
        madde("En az 2 rejimde pozitif (rejim başına >= 20 işlem ...)", rejim, "2 rejim pozitif ['a', 'b']; rejim n: a=30"),
        madde("Rastgele giriş yüzdeliği >= 95", rastgele, f"yüzdelik = {pct}"),
        madde("Masraf x1.5 altında net > 0", masraf, "net = +1.00 R"),
        madde("Monte Carlo %95 maks düşüş <= %25 (...)", not dusus, f"p95 = %{p95} (n={n})"),
        {"ad": "Çoklu deneme: DSR ve PBO (BİLGİ)", "gecti": True, "bilgi": True, "sonuc": "BİLGİ", "deger": "x"},
    ]}}


def test_karar_hayir_eksikleri_ve_gecenleri_listeler():
    k = K.karar(rapor(n=55, rastgele=False, dusus=True))
    assert k["hazir"] is False and k["eksik"] == ["dusus", "islem", "rastgele"]
    s = k["satir"]
    assert s.startswith("Canlıya hazır: HAYIR — eksik: işlem 55/300, rastgele girişten iyi değil (yüzdelik 40,0), en kötü düşüş sınırı aşıldı (%31,2)")
    assert "tamam: masraf sonrası net kâr pozitif" in s and "BİLGİ" not in s and "\n" not in s


def test_karar_evet_ve_veri_yok():
    k = K.karar(rapor(n=400, rastgele=True))
    assert k["hazir"] is True and k["eksik"] == [] and k["satir"].startswith("Canlıya hazır: EVET")
    assert K.karar({}) is None and K.karar({"canli_sartlari": {}}) is None


def test_degisim_tespiti():
    a = K.karar(rapor(n=55, rastgele=False))
    onceki = {"hazir": a["hazir"], "eksik": a["eksik"]}
    assert K.degisti(None, a) is True                                           # ilk calisma
    assert K.degisti(onceki, K.karar(rapor(n=80, pct=41.5))) is False           # yalniz sayi degisti
    assert K.degisti(onceki, K.karar(rapor(n=80, rastgele=True))) is True       # eksik kumesi degisti
    assert K.degisti(onceki, K.karar(rapor(n=80, rastgele=False, dusus=True))) is True
    assert K.degisti(onceki, K.karar(rapor(n=400, rastgele=True))) is True      # HAZIR oldu


def _outbox(tmp_path):
    return sorted((tmp_path / "var" / "telegram" / "outbox").glob("*.json"))


def test_karar_bildir_ilk_calisma_gonderir_ayni_karar_gondermez(tmp_path):
    m = _betik("tur1_olcum_run")
    env = {}
    assert m.karar_bildir(tmp_path, env, rapor(), NOW) is True
    dosyalar = _outbox(tmp_path)
    assert len(dosyalar) == 1
    it = json.loads(dosyalar[0].read_text(encoding="utf-8"))
    assert set(it) == {"text", "severity", "dedup_key", "expires_at", "reply_markup", "created_at"}
    assert it["severity"] == "INFO" and it["text"].startswith("Canlıya hazır: HAYIR") and it["dedup_key"].startswith("tur1-karar:2026-11-29:")
    # ertesi gun, sayi degisti: gonderilmez
    from datetime import timedelta
    assert m.karar_bildir(tmp_path, env, rapor(n=70, pct=44.0), NOW + timedelta(days=1)) is False
    assert len(_outbox(tmp_path)) == 1
    # eksik kumesi degisti: gider
    assert m.karar_bildir(tmp_path, env, rapor(n=90, rastgele=True), NOW + timedelta(days=2)) is True
    assert len(_outbox(tmp_path)) == 2
    st = json.loads((tmp_path / "var" / "durum" / "tur1_karar_son.json").read_text(encoding="utf-8"))
    assert [g["gun"] for g in st["gecmis"]] == ["2026-11-29", "2026-11-30", "2026-12-01"]
    assert st["son_gonderilen"]["eksik"] == ["islem"]


def test_karar_bildir_telegram_hatasi_cokmez_ve_ertesi_gun_tekrar_dener(tmp_path, monkeypatch):
    m = _betik("tur1_olcum_run")
    import trader_core.telegram as TG

    def bozuk(self, item):
        raise OSError("disk dolu")
    monkeypatch.setattr(TG.Outbox, "enqueue", bozuk)
    assert m.karar_bildir(tmp_path, {}, rapor(), NOW) is False
    st = json.loads((tmp_path / "var" / "durum" / "tur1_karar_son.json").read_text(encoding="utf-8"))
    assert "son_gonderilen" not in st                       # gonderilemedi: durum ilerlemez
    monkeypatch.undo()
    assert m.karar_bildir(tmp_path, {}, rapor(), NOW) is True
    # bozuk rapor ya da yazilamayan durum dizini de cokmez
    assert m.karar_bildir(tmp_path, {}, {"x": 1}, NOW) is False
    (tmp_path / "blok").write_text("x")
    assert m.karar_bildir(tmp_path / "blok", {}, rapor(), NOW) is False


# ----------------------------------------------------------------- haftalik YZ yorumu
class Butce:
    def __init__(self, izin=True):
        self.izin, self.olay = izin, []

    def api_key_env(self, s):
        return "ANTHROPIC_API_KEY_HAFTALIK_OZET"

    def estimate_cost(self, model, i, o, *a, **k):
        self.olay.append(("est", model))
        return 0.2

    def authorize(self, svc, est):
        self.olay.append(("auth", svc))
        if not self.izin:
            from trader_core.budget import Denial
            return Denial.__new__(Denial)
        return type("G", (), {"grant_id": 1})()

    def record(self, svc, grant, usage, model, batch):
        self.olay.append(("record", svc, model))

    def release(self, grant):
        self.olay.append(("release",))


def hazirla(tmp_path):
    d = tmp_path / "var" / "durum"
    d.mkdir(parents=True)
    (d / "tur1_olcum.md").write_text("# Tur 1\n- n=55\n", encoding="utf-8")
    (d / "tur1_karar_son.json").write_text(json.dumps({"gecmis": [{"gun": "2026-11-28", "satir": "Canlıya hazır: HAYIR — eksik: işlem 50/300"}]}))
    return {"TRADER_DATA_ROOT": str(tmp_path)}


class SahteBatch:
    """Sahte Batch istemcisi: submit -> poll (hemen biter) ; ag yok."""

    def __init__(self, metin="- bir\n- iki\n- uc", hata=False):
        self.metin, self.hata, self.gonderilen = metin, hata, []

    def submit(self, bundle, custom_id):
        if self.hata:
            raise RuntimeError("api")
        self.gonderilen.append(bundle.params)
        self.cid = custom_id
        return "batch_1"

    def poll(self, batch_id):
        return LS.BatchPoll("ended", (LS.BatchResult(self.cid, "succeeded", self.metin, "end_turn",
                                                     {"input_tokens": 10, "output_tokens": 5}),))

    def cancel(self, batch_id):
        pass


def test_haftalik_ok_yolu_mesaj_yazar_ve_ayni_hafta_tekrar_etmez(tmp_path):
    m = _betik("tur1_haftalik_yorum_run")
    env, b, c = hazirla(tmp_path), Butce(), SahteBatch()
    assert m.main(["--once"], client=c, budget=b, now_fn=lambda: NOW, env=env) == 0
    assert len(c.gonderilen) == 1 and "temperature" not in c.gonderilen[0] and c.gonderilen[0]["model"] == "claude-fable-5-2"
    assert "Canlıya hazır: HAYIR" in c.gonderilen[0]["messages"][0]["content"] and "n=55" in c.gonderilen[0]["messages"][0]["content"]
    assert [e[0] for e in b.olay] == ["est", "auth", "record"] and b.olay[-1] == ("record", "haftalik_ozet", "claude-fable-5-2")
    it = json.loads(_outbox(tmp_path)[0].read_text(encoding="utf-8"))
    assert it["text"].endswith("- bir\n- iki\n- uc") and it["dedup_key"] == "tur1-haftalik:2026-W48"
    assert m.main(["--once"], client=c, budget=b, now_fn=lambda: NOW, env=env) == 0 and len(c.gonderilen) == 1


def test_haftalik_butce_reddi_cagri_ve_mesaj_yok(tmp_path):
    m = _betik("tur1_haftalik_yorum_run")
    env, c = hazirla(tmp_path), SahteBatch()
    assert m.main(["--once"], client=c, budget=Butce(izin=False), now_fn=lambda: NOW, env=env) == 0
    assert c.gonderilen == [] and _outbox(tmp_path) == []


def test_haftalik_gonderim_hatasi_butceyi_birakir_mesaj_yok(tmp_path):
    m = _betik("tur1_haftalik_yorum_run")
    env, b = hazirla(tmp_path), Butce()
    assert m.main(["--once"], client=SahteBatch(hata=True), budget=b, now_fn=lambda: NOW, env=env) == 0
    assert ("release",) in b.olay and not any(e[0] == "record" for e in b.olay) and _outbox(tmp_path) == []


def test_haftalik_anahtar_yok_ve_rapor_yok_sessiz(tmp_path):
    m = _betik("tur1_haftalik_yorum_run")
    assert m.main(["--once"], budget=Butce(), now_fn=lambda: NOW, env={"TRADER_DATA_ROOT": str(tmp_path)}) == 0     # rapor yok
    env = hazirla(tmp_path)
    assert m.main(["--once"], budget=Butce(), now_fn=lambda: NOW, env=env) == 0 and _outbox(tmp_path) == []        # anahtar yok


def test_haftalik_gercek_butce_fable_fiyatini_bilir_ve_tavanin_altinda(tmp_path):
    from trader_core import budget as B
    m = _betik("tur1_haftalik_yorum_run")
    cfg = B.load_config(str(ROOT / "config" / "budget.json"))
    assert "claude-fable-5-2" in cfg.prices_usd_per_mtok
    g = B.BudgetGuard(B.load_config(str(ROOT / "config" / "budget.json")).__class__(**{**cfg.__dict__, "db_path": str(tmp_path / "b.sqlite")}))
    est = g.estimate_cost(m.MODEL, (len(m.SYSTEM) + m.MAX_MD_KARAKTER + 2000) // 2, m.MAX_OUT)
    assert est <= cfg.daily_cap_usd["haftalik_ozet"]


def test_haftalik_parametreleri_gercek_sdk_imzasina_uyar():
    import anthropic
    m = _betik("tur1_haftalik_yorum_run")
    p = m.istem_parametreleri("x")
    assert "temperature" not in p
    inspect.signature(anthropic.resources.Messages.create).bind(None, **p)
