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
    out = say(d, "/devam", 1)
    assert "0427" in out and "Ana para kilidi" in out         # kod isteminde kaldirilacak tutuslar listelenir
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


def test_capital_latch_has_own_telegram_alert():
    """V-05: ana para kilidi devreye girince ayri Telegram uyarisi gider (eskiden sessizdi); duzelince 'Düzeldi'; tekrar siniri mevcut alarm anahtari."""
    from datetime import datetime, timezone

    from trader_core import health as H
    now = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)
    a = H.Alert(H.Status.WARN, "capital_latch", "ana para kilidi", "b", "capital_latch|learner", now)
    tur, text, key = tg_sade.saglik_mesaji(a)
    assert tur == "alarm" and key == "capital_latch|learner" and "/devam" in text
    assert "Ana para kilidi devrede" in text and "Yeni işlem açılmıyor" in text and text.startswith("[ML] ⚠")
    assert tg_sade.kontrol(text) == []
    tur, text, _ = tg_sade.saglik_mesaji(H.Alert(H.Status.OK, "capital_latch", "t", "b", "capital_latch|learner|duzeldi|x", now))
    assert tur == "duzeldi" and "ana para kilidi kaldırıldı" in text
    # panel cumlesi degismez (TEKNIK sekmesi): eski _SAGLIK_EK cumlesi
    assert tg_sade.saglik_cumlesi("capital_latch:learner", "capital_latch") == (
        "Ana para kilidi: kasa ana paranın %15 altına indi", "Yeni girişler kapalı; açmak için /devam yaz.")
