"""Ortak test duzenegi. Paper acilis kapisi (Engine._startup_gate; kural + taze 1m veri 10/10) gercek davranista
zorunludur; sahte/eski veri kullanan mevcut paper testleri (modul/oturum kapsamli fixture'lar dahil) icin varsayilan
olarak etkisiz kilinir. Kapiyi gercekten sinayan modul `REAL_STARTUP_GATE = True` tanimlar."""
import pytest

_REAL = {"on": False}


@pytest.fixture(scope="session", autouse=True)
def _neutral_startup_gate_session():
    try:
        from trader_engine.engine import Engine
    except Exception:  # noqa: BLE001 - motor import edilemiyorsa kapi yok
        yield
        return
    orig = Engine._startup_gate

    def gate(self):
        if _REAL["on"]:
            return orig(self)
        return None

    Engine._startup_gate = gate
    try:
        yield
    finally:
        Engine._startup_gate = orig


@pytest.fixture(autouse=True)
def _real_gate_for_marked_modules(request):
    _REAL["on"] = bool(getattr(request.module, "REAL_STARTUP_GATE", False))
    yield
    _REAL["on"] = False


@pytest.fixture
def kilitli_donem(monkeypatch):
    """23.11.2026 kullanici karariyla kilit ACIK (trader_engine.holdout.KILIT_ACIK). Bu fixture kilidi KAPATIR (eski kilit davranisi):
    kilit mekanizmasinin hala dogru calistigini sinayan testler kullanir. Acik davranis varsayilandir; fixture'siz testler onu sinar."""
    from datetime import datetime, timedelta, timezone

    from trader_core import alinmayan_sonuc  # noqa: F401  (yuklensin)
    from trader_engine import holdout as H
    from trader_reports import guard
    monkeypatch.setattr(H, "KILIT_ACIK", False)
    monkeypatch.setattr(guard, "KILIT_ACIK", False)
    h0, h1 = H.HOLDOUT
    iso = guard.iso
    monkeypatch.setattr(guard, "H0", h0)
    monkeypatch.setattr(guard, "H1", h1)
    monkeypatch.setattr(guard, "H0_MS", int(h0.timestamp() * 1000))
    monkeypatch.setattr(guard, "H1_MS", int(h1.timestamp() * 1000))
    monkeypatch.setattr(guard, "H1_ISO", iso(h1))
    monkeypatch.setattr(guard, "H0_PAD_ISO", iso(h0 - timedelta(hours=guard.PAD_HOURS)))
    monkeypatch.setattr(guard, "PARAMS", {"h1": iso(h1), "h0p": iso(h0 - timedelta(hours=guard.PAD_HOURS))})
    yield
