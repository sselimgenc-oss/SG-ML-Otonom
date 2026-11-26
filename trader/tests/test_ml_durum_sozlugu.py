"""Ortak durum sozlugu + sahipsiz karar duzeltmesi + OZET'te ders karti YOK (24.11: makine ogrenmesi karti, 25.11: ders karti silindi)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from trader_core import panel_pano as PP
from trader_engine.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_ledger_spec as T  # noqa: E402
from test_ledger_spec import clock, dbpath, led, lp  # noqa: E402,F401  (fikstürler)


def test_vocabulary_strings_and_colours():
    assert PP.ogrenme_durumu(True, True) == ("Açık, işlemleri etkiliyor", "yesil")
    assert PP.ogrenme_durumu(True, False, 6, 10) == ("Açık, veri birikiyor (6/10)", "sari")
    assert PP.ogrenme_durumu(False, False, 6, 10) == ("Kapalı", "gri")


def test_ozet_has_no_ders_card_and_no_ml_card():
    js = (ROOT / "src/trader_panel/static/panel.js").read_text(encoding="utf-8")
    ozet = js.split("function tabOzet")[1].split("function isikKart")[0]
    assert "'Ders öğrenmesi'" not in js and "'Makine öğrenmesi'" not in js
    assert "p.ders" not in js and "p.ml" not in js
    assert "Henüz ders yok" not in js and "Son 7 günde değiştirdiği işlem" not in js
    assert "ogrenmeOzetKart" in ozet                     # kalan ogrenme karti: kol x zaman dilimi ozeti


def _eng(led, in_flight=()):
    st = SimpleNamespace(decision_ids_in_flight=lambda: set(in_flight))
    return SimpleNamespace(ledger=led, state=st)


def test_orphan_entered_decision_is_superseded_on_start(lp, clock):
    d1 = lp.record_decision(T.dec())
    clock.advance(hours=2)
    assert lp.find_orphan_decisions(older_than_s=3600) == [d1]
    assert Engine._reconcile_orphan_decisions(_eng(lp)) == 1
    assert lp.find_orphan_decisions(older_than_s=3600) == []
    cur = [d for d in lp.list_decisions() if d.supersedes_id == d1]
    assert cur and cur[0].final_action == "skipped" and cur[0].skip_reason == "order_failed"


def test_orphan_with_live_position_is_left_alone(lp, clock):
    d1 = lp.record_decision(T.dec())
    clock.advance(hours=2)
    assert Engine._reconcile_orphan_decisions(_eng(lp, {d1})) == 0
    assert lp.find_orphan_decisions(older_than_s=3600) == [d1]

