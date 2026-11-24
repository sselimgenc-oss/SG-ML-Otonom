"""24.11 denetim: risk kademesi CLI'si kagitta (kullanici karari: risk kademesi kaldirildi, kagit = canli zorlamasi).
Kagitta `ladder`/`capital` yazan komutlar satir yazar, `capital init` reddedilir; backtest'te yazan komutlar reddedilir."""
from __future__ import annotations

import test_risk_ladder_spec as S
from trader_core import risk_ladder as rl


def _cli(tmp_path, mode):
    """Taban ayar dosyasinin kipini ayarla (write_cfg tabani varsayilan kagit)."""
    import json
    c = S.Cli(tmp_path, mode="paper")
    p = c.cfgd / "engine.base.json"
    raw = json.loads(p.read_text())
    raw["mode"] = mode
    p.write_text(json.dumps(raw))
    return c


def _paper(tmp_path):
    return _cli(tmp_path, "paper")


def test_kagitta_ladder_devam_komutu_satir_yazar(tmp_path):
    c = _paper(tmp_path)
    c.log_path.parent.mkdir(parents=True, exist_ok=True)
    lg = rl.LadderLog(str(c.log_path))
    lg.append("initial", "engine:paper", S.RN - 5 * S.D, amount=1000.0)
    lg.append("review_stop", "engine:rk1", S.RN - 3 * S.D, equity=790.0, base=1000.0)
    n = len(c.rows())
    assert c.run("ladder", "resume", "--equity", "790") == 0
    rows = c.rows()
    assert len(rows) == n + 1 and rows[-1]["kind"] == "review_resume" and rows[-1]["by"] == "cli:sg"
    assert c.run("capital", "deposit", "--amount", "5") == 0 and c.rows()[-1]["kind"] == "deposit"


def test_kagitta_capital_init_reddedilir(tmp_path, capsys):
    c = _paper(tmp_path)
    assert c.run("capital", "init", "--amount", "1000") == 2
    assert "kagitta `capital init` yok" in capsys.readouterr().err
    assert c.rows() == []


def test_backtestte_yazan_komutlar_reddedilir(tmp_path, capsys):
    c = _cli(tmp_path, "backtest")
    for argv in (("capital", "init", "--amount", "1000"), ("capital", "deposit", "--amount", "5"),
                 ("capital", "adjust", "--amount", "5", "--note", "x"), ("ladder", "resume", "--equity", "9"),
                 ("ladder", "step-up", "--decision", "x")):
        assert c.run(*argv) == 2, argv
    assert "backtest kipinde sermaye kaydi yok" in capsys.readouterr().err
    assert not c.log_path.exists()
    assert c.run("capital", "list", by=None) == 0
