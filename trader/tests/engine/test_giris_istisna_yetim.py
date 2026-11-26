"""P5-01: kagitta `submit_entry` istisnasi yetim `opening` pozisyon birakmaz; sayac artar, sonraki mumda yeniden giris mumkundur."""
from __future__ import annotations

from datetime import timedelta

from test_engine_05_spec import BTC, Env, H, T0


def test_kagit_submit_entry_istisnasi_yetim_opening_birakmaz(tmp_path, monkeypatch):
    env = Env(tmp_path)
    env.start()
    try:
        def boom(*a, **k):
            raise ValueError("beklenmeyen emir hatasi")
        with monkeypatch.context() as m:
            m.setattr(env.orders, "submit_entry", boom)
            env.signal(T0, (BTC,))
            env.decide(T0)                                              # istisnasiz tamamlanir
            env.step(T0)
        pos = env.pos(BTC)
        assert pos is None or pos.status == "closed"                    # (1) opening kalmaz
        assert not any(p.status == "opening" for p in env.state.open_positions())
        assert env.engine.counters()["entry_submit_hata"] == 1          # (2)
        # (3) yama kalkinca ayni cift sonraki mumda yeniden girebilir (position_exists kilidi yok)
        D1 = T0 + H
        env.signal(D1, (BTC,))
        env.decide(D1)
        env.step(D1)
        assert env.pos(BTC) is not None and env.pos(BTC).status in ("open", "opening")
        assert env.engine.counters()["entry_submit_hata"] == 1
    finally:
        env.close()
