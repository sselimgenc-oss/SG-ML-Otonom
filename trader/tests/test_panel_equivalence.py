"""Panel sayilari = telegram.section_* sayilari (ayni fiksturde). telegram yalniz burada (test) ice aktarilir."""
import json

import pytest

from panel_support import DAY, NOW, Env, ROOT
from trader_core import panel_data as P
from trader_core import telegram as T
from trader_core import tg_sade as TS


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    e = Env(tmp_path_factory.mktemp("eq"))
    yield e
    e.close()


@pytest.fixture(scope="module")
def tcfg(env):
    r = env.root
    return T.TelegramConfig("1:tok", 5, str(r / "tg"), "", str(r / "var/learner/status.json"),
                            ledger_path=str(r / "var/learner/ledger.sqlite"),
                            budget_config=str(r / "config/budget.json"), lesson_store=str(r / "user_data/lesson.sqlite"))


def test_shared_constants_equal_telegram():
    assert P.STALE_S == T.STALE_S
    assert P.TR == T.TR
    for d in ("2026-11-16", "2026-03-29", "2027-01-01"):
        a, b = P.day_bounds_utc(d)
        assert (P.fmt_z(a), P.fmt_z(b)) == T._istanbul_day_bounds_utc(d)


def test_ledger_numbers_equal_section_ledger(env, tcfg):
    text = T.section_ledger(tcfg, DAY)
    closed, opened = P.ledger_day(tcfg.ledger_path, "learner", DAY)
    dse = json.loads((env.root / "var/learner/status.json").read_text())["day_start_equity"]
    s = P.day_summary(closed, opened, dse)
    assert (f"kapanan={s['closed']} PnL={s['pnl']:+.2f}$ R={s['r']:+.2f} kazanan/kaybeden={s['win']}/{s['loss']} "
            f"açık={s['open']}") in text
    assert f"günlük zarar={s['daily_loss']:.2f}$ / bütçe %{P.daily_loss_rate() * 100:g}={s['daily_limit']:.2f}$" in text
    assert "ikiz" not in text                                  # DD-12: ikiz satiri yok
    # telegram'in eski yolu (_trades) ile ayni kume ve toplam
    from trader_core import ledger as L
    led = L.open_ledger(tcfg.ledger_path, "learner", create=False, read_only=True, migrate=False)
    a, b = T._istanbul_day_bounds_utc(DAY)
    old = led._trades("exit_ts>=? AND exit_ts<?", [a, b], closed=True)
    led.close()
    assert T._sum(old) == pytest.approx(P.sum_pnl_r(closed))
    assert sorted(t.trade_id for t in old) == sorted(t.trade_id for t in closed)
    assert abs(TS.limit_orani(tcfg.config_dir, None) * dse - s["daily_limit"]) < 1e-9   # telegram ve panel ayni tek kaynak


def test_budget_equals_section_budget(tcfg):
    text = T.section_budget(tcfg)
    b = P.budget_view(tcfg.budget_config)
    names = {"haftalik_ozet": "haftalık özet", "lesson": "ders", "haber_kolu": "haber kolu", "yorumcu": "yorumcu"}
    parts = [f"{names.get(k, k)} {v['used_usd']:.2f}$/{v['cap_usd']:.2f}$ ({v['state']})" for k, v in b["services"].items()]
    want = f"ay {b['month_used_usd']:.2f}$/{b['monthly_cap_usd']:.2f}$ ({b['month_state']}); bugün: " + ", ".join(parts)
    if not b["prices_verified"]:
        want += "; fiyatlar doğrulanmadı"
    assert text == want


def test_lesson_equals_section_lesson(tcfg):
    text = T.section_lesson(tcfg, NOW)
    j = P.lesson_view(tcfg.lesson_store, NOW)
    assert f"bekleyen öneri: {j['open_count']}" in text
    q = j["open_requests"][0]
    assert f"{q['request_id']}: {q['param']} {q['from']}→{q['to']} ({q['scope']})" in text
    sh = j["shadow"]
    assert f"gölge dönem: gün {sh['day']}/{sh['total']} (bitiş {sh['end']})" in text
    lr = j["last_run"]
    assert f"son çalışma: {lr['day']} {lr['status']}/{lr['code']}" in text


def test_section_error_codes_equal(tmp_path):
    cfg = T.TelegramConfig("1:tok", 5, str(tmp_path), "", "", ledger_path=str(tmp_path / "l.sqlite"),
                           lesson_store=str(tmp_path / "x.sqlite"), budget_config=str(tmp_path / "config" / "budget.json"))
    for fn_t, fn_p in ((lambda: T.section_ledger(cfg, DAY), lambda: P.ledger_day(cfg.ledger_path, "learner", DAY)),
                       (lambda: T.section_lesson(cfg, NOW), lambda: P.lesson_view(cfg.lesson_store, NOW)),
                       (lambda: T.section_budget(cfg), lambda: P.budget_view(cfg.budget_config))):
        with pytest.raises(T.SectionError) as te:
            fn_t()
        with pytest.raises(P.SectionError) as pe:
            fn_p()
        assert te.value.code == pe.value.code
