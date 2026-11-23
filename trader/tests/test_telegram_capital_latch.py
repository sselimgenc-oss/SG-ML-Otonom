"""/devam + 4 haneli kodla `capital_latch` tutusu kaldirilir (ayni denetim, by = telegram:<kullanici>)."""
from __future__ import annotations

from test_telegram_pause_impl_smoke import msg, rig, say, status  # noqa: F401
from trader_core import telegram as T
from trader_core import tg_sade


def test_devam_lifts_capital_latch_with_code(rig):  # noqa: F811
    d = rig
    status(d)
    for p in d.r.pauses.values():
        p.add("capital_latch", "engine:rk1", "dep_net=1000.00 equity=849.00")
    assert "0427" in say(d, "/devam", 1)
    assert all(p.active() for p in d.r.pauses.values())          # kod gelmeden kalkmaz
    say(d, "0427", 2)
    for p in d.r.pauses.values():
        assert not p.active()
        assert p.last_op("capital_latch") == "remove"
    rows = [l for l in open(d.r.pauses["learner"].audit_path, encoding="utf-8")]
    assert '"by": "telegram:111"' in rows[-1] and '"reason": "capital_latch"' in rows[-1]


def test_devam_keeps_capital_floor_refusal(rig):  # noqa: F811
    d = rig
    status(d)
    for p in d.r.pauses.values():
        p.add("capital_floor", "engine:rk1")
    assert "kaldırılamaz" in say(d, "/devam", 1)


def test_reason_texts():
    assert T.NEDEN_TR["capital_latch"] == "Ana para kilidi (kasa ana paranın %15 altına indi)"
    assert "capital_latch" in tg_sade._SAGLIK_EK
    from trader_core.panel_pano import NEDEN_KISA
    assert "capital_latch" in NEDEN_KISA
