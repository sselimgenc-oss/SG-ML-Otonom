"""Gorunum.onb t'ler arasi paylasimi (hiz icin) ile t basina taze onbellek AYNI aday kumesini vermeli (paylasilan anahtar t'ye
bagliysa sizinti olurdu)."""
from __future__ import annotations

from trader_ml.ml1 import groups as G
from trader_ml.ml1 import scan as SC
from trader_ml.ml1.table import stable_equal

from ml1_destek import PAIR, TF, STARTUP, sentetik


def test_paylasilan_onb_ile_paylasilmayan_ayni_satirlari_verir():
    b = sentetik(n=340, seed=11)
    arms = [a for a in G.rule_arm_ids() if a.endswith("@" + TF) and a.split("-")[0] in ("IN1", "GF1", "PA2")]
    assert len(arms) >= 25
    kw = dict(arm_ids=arms, startup=STARTUP, min_contig=5)
    paylasimli = SC.scan_pair_tf(PAIR, TF, b, b, share_onb=True, **kw)
    taze = SC.scan_pair_tf(PAIR, TF, b, b, share_onb=False, **kw)
    assert len(paylasimli) > 20
    assert len(paylasimli) == len(taze)
    assert stable_equal(paylasimli, taze, rtol=0.0)
    assert paylasimli.attrs["n_err"] == 0 and taze.attrs["n_err"] == 0
