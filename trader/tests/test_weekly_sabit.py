"""Haftalik ozet: sabit bolum (LLM'siz) her hafta yazilir; yorum yalniz anahtar + butce varsa. Sentetik veri (tmp_path)."""
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import weekly_summary_run as W  # noqa: E402
from trader_core import ortak as LS  # noqa: E402
from trader_core import telegram as T  # noqa: E402

NOW = datetime(2026, 11, 22, 18, 10, tzinfo=timezone.utc)
DAY = "2026-11-22"


def _islem():
    from types import SimpleNamespace
    return SimpleNamespace(exit_ts=datetime(2026, 11, 22, 1, 0, tzinfo=timezone.utc), exit_reason="stop", r_multiple=-1.0,
                           setup="T1", pair="BTC/USDT", side="long")


def _write(p: Path, doc):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc), encoding="utf-8")


def _run(tmp_path, **kw):
    lp = tmp_path / "var" / "learner" / "ledger.sqlite"
    lp.parent.mkdir(parents=True, exist_ok=True)
    return W.main(["--once", "--day", DAY, "--ledger", str(lp), *kw.pop("extra", [])],
                  now_fn=lambda: NOW, env={"TRADER_DATA_ROOT": str(tmp_path)}, **kw), lp.parent / "weekly_summaries" / "2026-W47.md"


def test_keyless_writes_fixed_section_and_no_llm(tmp_path, capsys):
    rc, f = _run(tmp_path)
    assert rc == 0 and json.loads(capsys.readouterr().out)["comment"] == "no_api_key"
    t = f.read_text(encoding="utf-8")
    for s in ("Tutarlılık: rapor yok", "Çıkış kanıtı: henüz veri yok", "Alınmayan sinyal: henüz veri yok"):
        assert s in t
    assert "PBO" not in t and "## Yorum" not in t                 # PBO dosyasi yok: sessiz atla
    # Telegram yolu: sabit satirlar gunluk rapordaki haftalik ozet satirina girer, [ML] etiketi + fit_text sinirina uyar
    m = T._haftalik_ozet_metni({"week": "2026-W47", "text": t})
    assert "Tutarlılık: rapor yok" in m and "Alınmayan sinyal: henüz veri yok" in m and "## " not in m
    assert T.fit_text(T.etiketle(m, "INFO")).startswith("[ML] ") and len(T.fit_text(m)) <= T.MAX_TEXT


def test_keyed_adds_comment_after_fixed_and_once_per_week(tmp_path, capsys):
    calls = []

    class Bud:
        def estimate_cost(self, *a, **k): return 0.01
        def authorize(self, svc, est): return type("G", (), {"grant_id": 1})()
        def record(self, *a): pass
        def release(self, g): pass

    class FakeLed:
        LIST_CLOSED_MAX = 10
        def list_closed_trades(self, limit=0): return [_islem()]
        def close(self): pass

    orig = W.L.open_ledger
    W.L.open_ledger = lambda *a, **k: FakeLed()
    try:
        class Llm:
            def submit(self, bundle, custom_id):
                calls.append(bundle.params)
                self.cid = custom_id
                return "b1"

            def poll(self, batch_id):
                return LS.BatchPoll("ended", (LS.BatchResult(self.cid, "succeeded", "Hafta sakindi.", "end_turn",
                                                             {"input_tokens": 1, "output_tokens": 1}),))

            def cancel(self, batch_id): pass
        llm = Llm()
        rc, f = _run(tmp_path, client=llm, budget=Bud())
        assert rc == 0 and len(calls) == 1
        t = f.read_text(encoding="utf-8")
        assert t.index("## Sabit bölüm") < t.index("## Yorum") and "Hafta sakindi." in t
        capsys.readouterr()
        rc, _ = _run(tmp_path, client=llm, budget=Bud())              # ayni hafta: dokunma
        assert json.loads(capsys.readouterr().out)["status"] == "exists" and len(calls) == 1
    finally:
        W.L.open_ledger = orig


def test_budget_denied_still_writes_fixed(tmp_path, capsys):
    class Bud:
        def estimate_cost(self, *a, **k): return 0.01
        def authorize(self, svc, est): return type("D", (), {"reason": "cap"})()
    orig = W.L.open_ledger

    class FakeLed:
        LIST_CLOSED_MAX = 10
        def list_closed_trades(self, limit=0): return [_islem()]
        def close(self): pass
    W.L.open_ledger = lambda *a, **k: FakeLed()
    try:
        rc, f = _run(tmp_path, client=object(), budget=Bud())
    finally:
        W.L.open_ledger = orig
    assert rc == 0 and "## Sabit bölüm" in f.read_text(encoding="utf-8") and "## Yorum" not in f.read_text(encoding="utf-8")


def test_alinmayan_satiri(tmp_path):
    p = tmp_path / "var" / "durum" / "alinmayan_sonuc_v1.json"
    assert W.alinmayan_satiri({"TRADER_DATA_ROOT": str(tmp_path)}) == "Alınmayan sinyal: henüz veri yok"
    r = lambda e, n, pnl: {"etiket": e, "n": n, "kazanan": 1, "isabet_yuzde": 50.0, "toplam_pnl": pnl, "ortalama_pnl": pnl / n}  # noqa: E731
    _write(p, {"sema": "ml.alinmayan_sonuc.v1", "tablolar": {"neden": [r("risk_limiti", 3, 4.5), r("dusuk_skor", 2, -1.0)]},
               "tum_zamanlar": {"neden": []}})
    s = W.alinmayan_satiri({"TRADER_DATA_ROOT": str(tmp_path)})
    assert s == "Alınmayan sinyal (7g): 5 sinyal; en iyi risk_limiti +4,50R (n=3), en kötü dusuk_skor -1,00R (n=2)"
    assert "$" not in s                                                    # 24.11 denetim: R dolar diye yazilmaz
    p.write_text("{", encoding="utf-8")
    assert W.alinmayan_satiri({"TRADER_DATA_ROOT": str(tmp_path)}).endswith("henüz veri yok")


def test_pbo_satiri_only_when_file(tmp_path):
    env = {"TRADER_DATA_ROOT": str(tmp_path)}
    assert W.pbo_satiri(env) is None
    _write(tmp_path / "research" / "holdout" / "pbo_ozet.json", {"aileler": [{"aile": "ML 19c", "pbo": 0.3225}]})
    assert W.pbo_satiri(env) == "PBO: ML 19c %32"


def test_cikis_kaniti_cases(tmp_path):
    lp = str(tmp_path / "ledger.sqlite")
    assert W.cikis_kaniti_satiri({}, lp, NOW) == "Çıkış kanıtı: henüz veri yok"
    db = sqlite3.connect(tmp_path / "exit_counterfactual.sqlite")
    db.execute("CREATE TABLE ecf_outcomes (bot, version, source, run_id, trade_id, setup, role, value, net_r, computed_at, entry_ts, window_end_ts)")
    ts = (NOW - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    rows = [("learner", 1, "paper", "r", "t1", "M1", "base", 2.0, 0.5, ts, ts, ts),
            ("learner", 1, "paper", "r", "t1", "M1", "up", 3.0, 1.2, ts, ts, ts)]
    db.executemany("INSERT INTO ecf_outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.commit(); db.close()
    s = W.cikis_kaniti_satiri({}, lp, NOW)
    assert s == "Çıkış kanıtı: en büyük olumlu fark M1 trail yukarı +0,70R (n=1)"
