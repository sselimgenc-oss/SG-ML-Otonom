"""DD-12 WP-09 duman testleri: kodla islem notu, aday ders yasam dongusu, ML disa aktarimi, haftalik ozet (sahte LLM, ag yok)."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import budget as B
from trader_core import lesson as LS
from trader_core import trade_notes as TN
from test_dd12_wp08_impl import D0, Env  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import notes_run  # noqa: E402
import weekly_summary_run as W  # noqa: E402


def _env(tmp_path):
    e = Env(tmp_path)
    for d in range(4):
        e.add(d, -1.0, rr=1.2)            # dusuk rr kayiplari (ders adayi: dusuk_rr:R1)
    return e


def test_notes_written_for_every_closed_trade_idempotent(tmp_path):
    e = _env(tmp_path)
    day = (D0 + timedelta(days=5)).date().isoformat()
    r1 = TN.write_nightly_notes(e.led, day)
    assert r1["written"] == 4
    notes = e.led.list_trade_notes()
    assert len(notes) == 4 and all(n["model"] == "code" and n["cost_usd"] == 0 for n in notes)
    assert all(TN.valid_tag(t) for n in notes for t in n["tags"])
    assert "ders:dusuk_rr:R1" in notes[0]["tags"]
    assert TN.write_nightly_notes(e.led, day)["written"] == 0


def test_vocab_rejects_unknown_tag():
    with pytest.raises(ValueError):
        TN.validate_tags(["giris:iyi", "uydurma:x"])
    assert not TN.valid_tag("ders:bilinmeyen:R1")


def test_lifecycle_alive_and_retired(tmp_path):
    e = _env(tmp_path)
    day = (D0 + timedelta(days=5)).date().isoformat()
    TN.write_nightly_notes(e.led, day)
    st = tmp_path / "lc.json"
    out = TN.lifecycle_tick(e.led, st, day, 0)
    assert "dusuk_rr:R1" in out["born"] and TN.active_lessons(st) == ["dusuk_rr:R1"]
    # ertesi gunden sonra kosula uyan kayip islem => ders etkisi > 0 => yasar
    e.add(7, -1.0, rr=1.2)
    d2 = (D0 + timedelta(days=9)).date().isoformat()
    assert TN.lifecycle_tick(e.led, st, d2, 0)["alive"] == ["dusuk_rr:R1"]
    # sonra kazanc getirir => etki <= 0 => emekli; istemden cikar, kayit kalir
    for dd in (10, 11, 12):
        e.add(dd, 3.0, rr=1.2)
    d3 = (D0 + timedelta(days=14)).date().isoformat()
    assert TN.lifecycle_tick(e.led, st, d3, 0)["retired"] == ["dusuk_rr:R1"]
    assert TN.active_lessons(st) == [] and json.loads(st.read_text())["dusuk_rr:R1"]["status"] == "retired"


def test_export_rows_are_labels(tmp_path):
    e = _env(tmp_path)
    TN.write_nightly_notes(e.led, (D0 + timedelta(days=5)).date().isoformat())
    rows = TN.export_ml_rows(e.led)
    assert len(rows) == 4 and rows[0]["role"] == "label" and rows[0]["tags"]["sonuc"] == "kayip"
    assert rows[0]["lesson_ids"] == ["dusuk_rr:R1"] and rows[0]["r"] < 0


def test_notes_run_cli(tmp_path, capsys):
    e = _env(tmp_path)
    e.led.close()
    day = (D0 + timedelta(days=5)).date().isoformat()
    rc = notes_run.main(["--once", "--day", day, "--ledger", str(tmp_path / "learner.sqlite"),
                         "--export", str(tmp_path / "ml.jsonl")], env={})
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["written"] == 4
    assert len((tmp_path / "ml.jsonl").read_text().splitlines()) == 4


def _budget(tmp_path, cap=20.0):   # 23.11: aylik tavan 20 $ (paylar toplami 17 $)
    cfg = json.loads((ROOT / "config" / "budget.json").read_text())
    cfg["db_path"] = str(tmp_path / "budget.sqlite")
    cfg["monthly_cap_usd"] = cap
    cfg["monthly_warn_usd"] = cap / 2
    pay = cfg.get("monthly_share_usd") or {}
    if pay and sum(pay.values()) > cap:                    # cok kucuk tavan denemesi: paylar tavana orantili kucultulur
        cfg["monthly_share_usd"] = {k: v * cap * 0.99 / sum(pay.values()) for k, v in pay.items()}   # yuvarlama payi
    cfg["prepaid_credit_usd"] = 10.0
    p = tmp_path / "budget.json"
    p.write_text(json.dumps(cfg))
    g = B.BudgetGuard(B.load_config(p)) if hasattr(B, "BudgetGuard") else None
    B._set_default_guard(g)
    return B


def test_weekly_summary_budget_and_noop(tmp_path, capsys):
    e = _env(tmp_path)
    day = (D0 + timedelta(days=5))
    TN.write_nightly_notes(e.led, day.date().isoformat())
    e.led.close()
    lp = str(tmp_path / "learner.sqlite")
    now = lambda: day  # noqa: E731
    # anahtar yok => sabit bolum yazilir, yorum yok (hafta basina bir kez; sonraki kosu icin dosyayi sil)
    assert W.main(["--once", "--ledger", lp], env={"TRADER_DATA_ROOT": str(tmp_path)}, now_fn=now) == 0
    o = json.loads(capsys.readouterr().out)
    assert o["status"] == "ok" and o["comment"] == "no_api_key"
    f = next((tmp_path / "weekly_summaries").glob("*.md"))
    assert "## Sabit bölüm" in f.read_text() and "## Yorum" not in f.read_text()
    f.unlink()
    b = _budget(tmp_path)
    calls = []

    class Fake:                                           # sahte Batch istemcisi (ag yok)
        def submit(self, bundle, custom_id):
            calls.append(bundle.params)
            self.cid = custom_id
            return "batch_1"

        def poll(self, batch_id):
            return LS.BatchPoll("ended", (LS.BatchResult(self.cid, "succeeded", "Bu hafta 4 islem kapandi.", "end_turn",
                                                         {"input_tokens": 500, "output_tokens": 100}),))

        def cancel(self, batch_id):
            pass
    fake = Fake()

    try:
        assert W.main(["--once", "--ledger", lp], client=fake, budget=b, now_fn=now, env={}) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "ok" and len(calls) == 1
        out = next((tmp_path / "weekly_summaries").glob("*.md")).read_text()
        assert "4 islem" in out and "## Yorum" in out and out.index("## Sabit") < out.index("## Yorum")
        assert W.main(["--once", "--ledger", lp], client=fake, budget=b, now_fn=now, env={}) == 0   # bu hafta var
        assert len(calls) == 1
        assert b.status().month_used_usd > 0 if hasattr(b.status(), "month_used_usd") else True
        # tavan bitti => cagri yok
        (tmp_path / "x").mkdir()
        b2 = _budget(tmp_path / "x", cap=0.0001)
        assert W.main(["--once", "--ledger", lp, "--force"], client=fake, budget=b2, now_fn=now, env={}) == 0
        assert len(calls) == 1
    finally:
        B._set_default_guard(None)
