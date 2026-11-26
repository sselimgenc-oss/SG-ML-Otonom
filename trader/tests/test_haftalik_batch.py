"""Haftalik YZ raporlari Message Batches API ile (24 Kas 2026): gonder / bekle / topla / basarisizlik / cift gonderim yok / Telegram / butce.

Sahte istemci (ag yok, gercek API cagrilmaz); gercek `BudgetGuard` (tmp sqlite) ile batch fiyati ve rezerv kapanisi dogrulanir.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import budget as B
from trader_core import haftalik_batch as HB
from trader_core import ortak as LS

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import weekly_summary_run as W  # noqa: E402

TUR1 = importlib.util.module_from_spec(importlib.util.spec_from_file_location("tur1_haftalik_yorum_run", ROOT / "scripts" / "tur1_haftalik_yorum_run.py"))
TUR1.__spec__.loader.exec_module(TUR1)
TUR1.HAFTALIK_YORUM_TELEGRAM = True        # 26.11: varsayilan KAPALI; gonderim/toplama yollari burada acik sinanir (kapali yol: test_tur1_karar)

NOW = datetime(2026, 11, 29, 6, 0, tzinfo=UTC)          # pazar, 2026-W48
USAGE = {"input_tokens": 3000, "output_tokens": 400}


class Sahte:
    """submit -> batch_N; poll: `mod` in_progress | ended | expired | errored; hic API cagrisi yok."""

    def __init__(self, mod="in_progress", metin="- bir\n- iki\n- uc"):
        self.mod, self.metin, self.gonderilen, self.iptal, self.polls = mod, metin, [], [], 0

    def submit(self, bundle, custom_id):
        self.gonderilen.append((bundle.params, custom_id))
        return f"batch_{len(self.gonderilen)}"

    def poll(self, batch_id):
        self.polls += 1
        if self.mod == "in_progress":
            return LS.BatchPoll("in_progress")
        cid = self.gonderilen[-1][1]
        if self.mod == "ended":
            return LS.BatchPoll("ended", (LS.BatchResult(cid, "succeeded", self.metin, "end_turn", USAGE),))
        return LS.BatchPoll("ended", (LS.BatchResult(cid, self.mod),))

    def cancel(self, batch_id):
        self.iptal.append(batch_id)


def gercek_butce(tmp_path):
    d = json.loads((ROOT / "config" / "budget.json").read_text())
    d["db_path"] = str(tmp_path / "b.sqlite")
    (tmp_path / "budget.json").write_text(json.dumps(d))
    cfg = B.load_config(tmp_path / "budget.json")
    g = B.BudgetGuard(cfg)
    return g, SimpleNamespace(authorize=g.authorize, record=g.record, release=g.release, estimate_cost=g.estimate_cost,
                              api_key_env=lambda s: cfg.api_key_env[s])


def outbox(root):
    return sorted((root / "var" / "telegram" / "outbox").glob("*.json")) if (root / "var" / "telegram" / "outbox").is_dir() else []


def mesajlar(root):
    return [json.loads(p.read_text(encoding="utf-8")) for p in outbox(root)]


def kullanilan(g, servis="haftalik_ozet"):
    return g.status().services[servis].used_usd


# ------------------------------------------------------------------ yapilandirma
def test_butce_batch_fiyati_yarim_ve_rezerv_suresi_batch_icin_yeterli(tmp_path):
    _, b = gercek_butce(tmp_path)
    tam = b.estimate_cost("claude-fable-5-2", 1000, 1000)
    assert b.estimate_cost("claude-fable-5-2", 1000, 1000, batch=True) == pytest.approx(tam * 0.5)
    ttl = json.loads((ROOT / "config" / "budget.json").read_text())["reservation_ttl_s"]["haftalik_ozet"]
    assert ttl >= 86400 + 3600             # batch 24 saate kadar surebilir; rezerv bu surede 'expired' olmamali


# ------------------------------------------------------------------ haftalik ozet (weekly_summary_run)
LP_REL = Path("var") / "learner" / "ledger.sqlite"


class SahteDefter:
    LIST_CLOSED_MAX = 10

    def list_closed_trades(self, limit=0):
        return [SimpleNamespace(exit_ts=datetime(2026, 11, 29, 1, 0, tzinfo=UTC), exit_reason="stop", r_multiple=-1.0,
                                setup="T1", pair="BTC/USDT", side="long")]

    def close(self):
        pass


@pytest.fixture
def ozet(tmp_path, monkeypatch):
    monkeypatch.setattr(W.L, "open_ledger", lambda *a, **k: SahteDefter())
    (tmp_path / LP_REL).parent.mkdir(parents=True)

    def calistir(*extra, client=None, budget=None, now=NOW):
        return W.main(["--once", "--ledger", str(tmp_path / LP_REL), *extra],
                      client=client, budget=budget, now_fn=lambda: now, env={"TRADER_DATA_ROOT": str(tmp_path)}, sleep=lambda s: None)
    md = tmp_path / "var" / "learner" / "weekly_summaries" / "2026-W48.md"
    return calistir, md, md.with_name("2026-W48.batch.json")


def test_ozet_gonderir_sabit_bolum_hemen_yorum_bekler_cift_gonderim_yok(ozet, tmp_path, capsys):
    calistir, md, durum = ozet
    g, b = gercek_butce(tmp_path)
    c = Sahte("in_progress")
    assert calistir("--wait-s", "60", client=c, budget=b) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["comment"] == "submitted" and len(c.gonderilen) == 1 and c.gonderilen[0][0]["model"] == "claude-haiku-5-5"
    assert "## Sabit bölüm" in md.read_text(encoding="utf-8") and "## Yorum" not in md.read_text(encoding="utf-8")
    st = json.loads(durum.read_text(encoding="utf-8"))
    assert st["durum"] == "submitted" and st["batch_id"] == "batch_1" and st["grant"]["grant_id"]
    assert c.polls == 3 and mesajlar(tmp_path) == []                    # 60 sn / 30 sn aralik: 3 yoklama; Telegram yok (bekliyor)
    assert kullanilan(g) > 0                                            # rezerv acik (batch fiyatli tahmin)
    # ayni hafta ikinci kosu (normal, --force'lu bile): yeni batch YOK
    for ek in ((), ("--force",)):
        assert calistir(*ek, client=c, budget=b) == 0 and json.loads(capsys.readouterr().out.splitlines()[-1])["status"] == "pending"
    assert len(c.gonderilen) == 1


def test_ozet_sonraki_kosuda_toplar_yorum_dosyaya_ve_telegrama_butce_batch_fiyatiyla(ozet, tmp_path):
    calistir, md, durum = ozet
    g, b = gercek_butce(tmp_path)
    c = Sahte("in_progress")
    calistir("--wait-s", "0", client=c, budget=b)
    c.mod, c.metin = "ended", "Hafta sakindi."
    assert calistir("--collect", client=c, budget=b, now=NOW + timedelta(hours=3)) == 0
    t = md.read_text(encoding="utf-8")
    assert t.index("## Sabit bölüm") < t.index("## Yorum") and "Hafta sakindi." in t
    st = json.loads(durum.read_text(encoding="utf-8"))
    assert st["durum"] == "done" and st["telegram"] is True
    ms = mesajlar(tmp_path)
    assert len(ms) == 1 and "Hafta sakindi." in ms[0]["text"] and ms[0]["dedup_key"] == "haftalik-ozet:2026-W48"
    # gercek maliyet: haiku batch = (3000*0.10 + 400*0.50)/1e6 * 0.5
    assert kullanilan(g) == pytest.approx((3000 * 0.10 + 400 * 0.50) / 1e6 * 0.5, abs=1e-6)
    c.mod = "in_progress"
    calistir("--collect", client=c, budget=b)                           # toplanmis: tekrar mesaj/gonderim yok
    assert len(mesajlar(tmp_path)) == 1 and len(c.gonderilen) == 1


def test_ozet_ayni_kosuda_biterse_hemen_toplanir(ozet, tmp_path):
    calistir, md, _ = ozet
    _, b = gercek_butce(tmp_path)
    assert calistir(client=Sahte("ended", "Anlik."), budget=b) == 0
    assert "Anlik." in md.read_text(encoding="utf-8") and len(mesajlar(tmp_path)) == 1


@pytest.mark.parametrize("mod", ["expired", "errored", "canceled"])
def test_ozet_batch_basarisiz_kisa_not_gider_rezerv_serbest(ozet, tmp_path, mod):
    calistir, md, durum = ozet
    g, b = gercek_butce(tmp_path)
    c = Sahte("in_progress")
    calistir("--wait-s", "0", client=c, budget=b)
    c.mod = mod
    assert calistir("--collect", client=c, budget=b) == 0
    assert json.loads(durum.read_text(encoding="utf-8"))["durum"] == "failed"
    ms = mesajlar(tmp_path)
    assert len(ms) == 1 and "atlandı" in ms[0]["text"] and "2026-W48" in ms[0]["text"] and len(ms[0]["text"]) < 200
    assert "## Yorum" not in md.read_text(encoding="utf-8") and kullanilan(g) == 0
    calistir("--collect", client=c, budget=b)
    assert len(mesajlar(tmp_path)) == 1                                 # not bir kez


def test_ozet_36_saati_asan_batch_iptal_edilir_ve_not_gider(ozet, tmp_path):
    calistir, _, durum = ozet
    g, b = gercek_butce(tmp_path)
    c = Sahte("in_progress")
    calistir("--wait-s", "0", client=c, budget=b)
    assert calistir("--collect", client=c, budget=b, now=NOW + timedelta(hours=37)) == 0
    assert c.iptal == ["batch_1"] and json.loads(durum.read_text(encoding="utf-8"))["durum"] == "failed"
    assert "atlandı" in mesajlar(tmp_path)[0]["text"] and kullanilan(g) == 0


def test_ozet_gonderim_hatasi_rezerv_birakilir_sabit_bolum_yazilir(ozet, tmp_path):
    calistir, md, durum = ozet

    class Bozuk(Sahte):
        def submit(self, bundle, custom_id):
            raise LS.LlmConnectionError("ag")
    g, b = gercek_butce(tmp_path)
    assert calistir(client=Bozuk(), budget=b) == 2
    assert md.exists() and not durum.exists() and kullanilan(g) == 0


def test_ozet_telegram_yazilamazsa_sonraki_toplama_kosusu_yeniden_dener(ozet, tmp_path, monkeypatch):
    calistir, _, durum = ozet
    _, b = gercek_butce(tmp_path)
    c = Sahte("in_progress")
    calistir("--wait-s", "0", client=c, budget=b)
    c.mod = "ended"
    monkeypatch.setattr(HB, "telegram_yaz", lambda *a, **k: False)
    calistir("--collect", client=c, budget=b)
    assert json.loads(durum.read_text(encoding="utf-8"))["telegram"] is False
    monkeypatch.undo()
    calistir("--collect", client=c, budget=b)
    assert len(mesajlar(tmp_path)) == 1 and json.loads(durum.read_text(encoding="utf-8"))["telegram"] is True


def test_ozet_butce_reddi_ve_anahtar_yok_api_yok(ozet, tmp_path):
    calistir, md, durum = ozet
    g, b = gercek_butce(tmp_path)
    g.authorize("haftalik_ozet", 0.25)                                  # gunluk payi doldur
    c = Sahte()
    assert calistir(client=c, budget=b) == 0 and c.gonderilen == [] and md.exists() and not durum.exists()
    md.unlink()
    assert calistir(budget=b) == 0 and "## Sabit bölüm" in md.read_text(encoding="utf-8")   # anahtar yok (env bos)


# ------------------------------------------------------------------ tur 1 haftalik yorum
def tur1_hazirla(root):
    d = root / "var" / "durum"
    d.mkdir(parents=True)
    (d / "tur1_olcum.md").write_text("# Tur 1\n- n=55\n", encoding="utf-8")
    (d / "tur1_karar_son.json").write_text(json.dumps({"gecmis": [{"gun": "2026-11-28", "satir": "Canlıya hazır: HAYIR"}]}))
    return d, {"TRADER_DATA_ROOT": str(root)}


def tur1(root, env, *args, client=None, budget=None, now=NOW):
    return TUR1.main(["--once", *args], client=client, budget=budget, now_fn=lambda: now, env=env, sleep=lambda s: None)


def test_tur1_gonderir_bekler_sonra_toplar_telegram_ve_butce(tmp_path):
    d, env = tur1_hazirla(tmp_path)
    g, b = gercek_butce(tmp_path)
    c = Sahte("in_progress")
    assert tur1(tmp_path, env, "--wait-s", "0", client=c, budget=b) == 0
    assert len(c.gonderilen) == 1 and c.gonderilen[0][0]["model"] == "claude-fable-5-2" and "temperature" not in c.gonderilen[0][0]
    assert mesajlar(tmp_path) == [] and not (d / "tur1_haftalik_yorum.json").exists()
    assert json.loads((d / "tur1_haftalik_batch.json").read_text())["durum"] == "submitted" and kullanilan(g) > 0
    # ayni hafta tekrar: yeni batch yok (normal ve --force)
    tur1(tmp_path, env, client=c, budget=b)
    tur1(tmp_path, env, "--force", client=c, budget=b)
    assert len(c.gonderilen) == 1
    c.mod = "ended"
    assert tur1(tmp_path, env, "--collect", client=c, budget=b, now=NOW + timedelta(hours=3)) == 0
    ms = mesajlar(tmp_path)
    assert len(ms) == 1 and ms[0]["text"].endswith("- bir\n- iki\n- uc") and ms[0]["dedup_key"] == "tur1-haftalik:2026-W48"
    assert json.loads((d / "tur1_haftalik_yorum.json").read_text())["hafta"] == "2026-W48"
    assert kullanilan(g) == pytest.approx((3000 * 8.0 + 400 * 40.0) / 1e6 * 0.5, abs=1e-6)
    tur1(tmp_path, env, client=c, budget=b)                              # toplanmis hafta: tekrar yok
    assert len(mesajlar(tmp_path)) == 1 and len(c.gonderilen) == 1


@pytest.mark.parametrize("mod", ["expired", "errored"])
def test_tur1_batch_basarisiz_atlandi_notu_ve_rezerv_serbest(tmp_path, mod):
    d, env = tur1_hazirla(tmp_path)
    g, b = gercek_butce(tmp_path)
    c = Sahte("in_progress")
    tur1(tmp_path, env, "--wait-s", "0", client=c, budget=b)
    c.mod = mod
    assert tur1(tmp_path, env, "--collect", client=c, budget=b) == 0
    ms = mesajlar(tmp_path)
    assert len(ms) == 1 and "atlandı" in ms[0]["text"] and ms[0]["dedup_key"] == "tur1-haftalik-atlandi:2026-W48"
    assert kullanilan(g) == 0
    tur1(tmp_path, env, client=c, budget=b)                              # ayni hafta bir daha denenmez
    assert len(c.gonderilen) == 1 and len(mesajlar(tmp_path)) == 1


def test_tur1_collect_bekleyen_yoksa_hicbir_sey_yapmaz(tmp_path):
    _, env = tur1_hazirla(tmp_path)
    c = Sahte()
    assert tur1(tmp_path, env, "--collect", client=c, budget=gercek_butce(tmp_path)[1]) == 0
    assert c.gonderilen == [] and c.polls == 0


def test_tur1_onceki_haftanin_bekleyen_batchi_yeni_hafta_kosusunda_toplanir(tmp_path):
    d, env = tur1_hazirla(tmp_path)
    _, b = gercek_butce(tmp_path)
    c = Sahte("in_progress")
    tur1(tmp_path, env, "--wait-s", "0", client=c, budget=b)
    c.mod = "ended"
    tur1(tmp_path, env, "--wait-s", "0", client=c, budget=b, now=NOW + timedelta(days=7))
    ms = mesajlar(tmp_path)
    assert {m["dedup_key"] for m in ms} == {"tur1-haftalik:2026-W48", "tur1-haftalik:2026-W49"} and len(c.gonderilen) == 2


# ------------------------------------------------------------------ depo / birim
def test_deploy_collect_zamanlayicisi_ve_unit_yollari():
    dep = ROOT / "deploy"
    svc = (dep / "trader-weekly-collect.service").read_text(encoding="utf-8")
    assert "weekly_summary_run.py --once --collect" in svc and "tur1_haftalik_yorum_run.py --once --collect" in svc
    assert "/opt/trader/var/telegram" in svc and "TELEGRAM_VAR_DIR" in svc
    assert "OnCalendar" in (dep / "trader-weekly-collect.timer").read_text(encoding="utf-8")
    assert "trader-weekly-collect.timer" in (dep / "install.sh").read_text(encoding="utf-8")
    assert "var/telegram" in (dep / "trader-weekly-summary.service").read_text(encoding="utf-8")


def test_haftalik_ozet_servisi_normal_mesajlar_api_kullanmaz():
    for ad in ("weekly_summary_run.py", "tur1_haftalik_yorum_run.py"):
        kaynak = (ROOT / "scripts" / ad).read_text(encoding="utf-8")
        assert "messages.create" not in kaynak
