"""Hiz testleri icin makine olcegi: ayni surecte sabit bir saf-Python referans isi olculur; esikler bu makinenin
referans makineye (gelistirme kutusu, ~0.09 s) gore ne kadar yavas oldugu oraninda buyutulur. Boylece hiz testleri
yavas/yuklu CI kosucusunda sahte hata vermez, ama kodun KENDI yavaslamasini (ayni makinede oran) yine yakalar.
Olcek [1, 4] araliginda kirpilir: 4 kattan yavas makinede test yine kalir (esik gevsetilmez, yalniz makineye uyarlanir)."""
from __future__ import annotations

import time

REFERANS_S = 0.09


def _ref_is() -> float:
    t = time.process_time()
    s = 0
    for i in range(2_000_000):
        s += i * i % 7
    return time.process_time() - t


def olcek() -> float:
    en_iyi = min(_ref_is() for _ in range(3))
    return max(1.0, min(en_iyi / REFERANS_S, 4.0))
