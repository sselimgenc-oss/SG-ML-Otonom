"""Kilit ACIK (23.11.2026 kullanici karari): M1 egitimi kilitli donem satirlarini reddetmez/dusurmez."""
from datetime import datetime, timezone

from trader_ml.pa_proposer import train as T

UTC = timezone.utc


def test_in_lock_acikken_hicbir_zaman_kilitli_degil():
    assert T.KILIT_ACIK is True
    assert T.in_lock(datetime(2026, 6, 1, tzinfo=UTC)) is False
    assert T.in_lock(datetime(2026, 4, 30, tzinfo=UTC), datetime(2026, 5, 2, tzinfo=UTC)) is False


def test_assert_no_lock_ve_drop_lock_acikken_satir_birakmaz_dusurmez():
    rows = [{"ts": datetime(2026, 6, 1, tzinfo=UTC)}, {"ts": datetime(2026, 3, 1, tzinfo=UTC)}]
    T.assert_no_lock(rows)                       # hata vermez
    kept, n = T.drop_lock(rows)
    assert len(kept) == 2 and n == 0
