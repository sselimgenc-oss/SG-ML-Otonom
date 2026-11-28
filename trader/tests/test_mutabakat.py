"""Islem mutabakati (src/trader_core/mutabakat.py + scripts/mutabakat_run.py): eslesen islemler, eksik panel satiri, K/Z farki, yanlis yon,
Telegram oncesi siniflamasi, kasa denklemi (komisyon + fonlama), acik pozisyon sayisi, Telegram gonderim kaydi, panel TEKNIK satiri."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from panel_support import NOW, ROOT, Env
from trader_core import mutabakat as M
from trader_core import panel_data as P
from trader_core import telegram as T
from trader_core import tg_sade as TS

UTC = timezone.utc
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


R = _load("mutabakat_run")


def tr(i, side="long", pair="ETH/USDT", closed=True, net=10.0, fee_e=0.5, fee_x=0.5, fund=0.2, day=14):
    a = datetime(2026, 11, day, 6 + i, 0, tzinfo=UTC)
    return SimpleNamespace(trade_id=i, pair=pair, side=side, entry_ts=a, entry_price=2000.0 + i,
                           exit_ts=a + timedelta(hours=1) if closed else None, exit_price=2050.0 if closed else None,
                           fee_entry=fee_e, fee_exit=fee_x if closed else None, funding_paid=fund if closed else None,
                           gross_pnl=net + fee_e + fee_x + fund if closed else None, realized_pnl=net if closed else None,
                           setup="R1", decision_id=i)


def motor(*trades):
    k = [t for t in trades if t.exit_ts is not None]
    a = [t for t in trades if t.exit_ts is None]
    return M.motor_satirlari(k, a, lambda t: "Yatay piyasa kenarı · 1 saat")


def panel_rows(rows, over=None):
    """Motor satirlarindan panelin kapanan/acik satirlarini taklit eder (panel_pano.closed_row bicimi)."""
    out = []
    for r in rows:
        d = {"id": r["islem_no"], "coin": r["coin"], "yon": r["yon"], "kol": r["kol"], "giris": r["giris"], "cikis": r["cikis"],
             "kz": r["net"], "komisyon": r["komisyon"], "fonlama": r["fonlama"],
             "acilis": M.PP.tsi_kisa(r["_a"]), "kapanis": M.PP.tsi_kisa(r["_k"]) if r["_k"] else None}
        d.update((over or {}).get(r["islem_no"], {}))
        out.append(d)
    return out


def split(rows, prow):
    kap = [p for p, r in zip(prow, rows) if r["durum"] == "kapalı"]
    ac = [p for p, r in zip(prow, rows) if r["durum"] == "açık"]
    return kap, ac


# ---------------------------------------------------------------------------------------------------- motor + panel
def test_motor_net_includes_fees_and_funding_and_shows_both():
    r = motor(tr(1, net=7.5, fee_e=0.4, fee_x=0.6, fund=0.25))[0]
    assert r["net"] == 7.5 and r["komisyon"] == pytest.approx(1.0) and r["fonlama"] == 0.25
    assert r["brut"] == pytest.approx(7.5 + 1.0 + 0.25) and r["acilis"] == "2026-11-14 10:00"      # 07:00Z = 10:00 TSI
    assert (r["coin"], r["yon"], r["durum"]) == ("ETH", "long", "kapalı")


def test_matching_trades_zero_mismatch():
    rows = motor(tr(1), tr(2, "short", "BTC/USDT"), tr(3, closed=False))
    kap, ac = split(rows, panel_rows(rows))
    assert M.panel_karsilastir(rows, kap, ac, 200) == []
    assert all(r["panel"] == "aynı" and not r["uyusmazlik"] for r in rows)


def test_missing_panel_row_is_mismatch_but_list_limit_is_not():
    rows = motor(tr(1), tr(2), tr(3))
    kap, ac = split(rows, panel_rows(rows))
    kap = [p for p in kap if p["id"] != 2]
    M.panel_karsilastir(rows, kap, ac, 200)
    assert rows[1]["panel"] == "YOK" and rows[1]["uyusmazlik"] == ["panelde yok"] and not rows[0]["uyusmazlik"]
    rows = motor(tr(1), tr(2), tr(3))                         # panel yalniz son 2 kapanani gosterir (liste siniri)
    kap = [p for p in split(rows, panel_rows(rows))[0] if p["id"] != 1]
    M.panel_karsilastir(rows, kap, [], 2)
    assert rows[0]["panel"].startswith("liste sınırı dışı") and not rows[0]["uyusmazlik"]


def test_pnl_mismatch_over_one_cent_and_within_tolerance():
    rows = motor(tr(1), tr(2))
    kap, ac = split(rows, panel_rows(rows, {1: {"kz": 10.02}, 2: {"kz": 10.005}}))
    M.panel_karsilastir(rows, kap, ac, 200)
    assert rows[0]["panel"].startswith("FARK") and rows[0]["uyusmazlik"] == ["K/Z farkı 0,02 $"]
    assert rows[1]["panel"] == "aynı"


def test_wrong_side_and_time_mismatch():
    rows = motor(tr(1), tr(2))
    kap, ac = split(rows, panel_rows(rows, {1: {"yon": "short"}, 2: {"kapanis": "01.01 00:00"}}))
    M.panel_karsilastir(rows, kap, ac, 200)
    assert rows[0]["uyusmazlik"] == ["yön farkı"] and "yön panel=short motor=long" in rows[0]["panel"]
    assert rows[1]["uyusmazlik"] == ["kapanış saati farkı"]


def test_panel_extra_row_reported():
    rows = motor(tr(1))
    kap, ac = split(rows, panel_rows(rows))
    assert M.panel_karsilastir(rows, kap + [{"id": 99}], ac, 200) == ["panelde fazla işlem #99"]


# ---------------------------------------------------------------------------------------------------- telegram
def _tg(rows, kayit=None, isaretli=lambda i, t: False, imlec=None, now=datetime(2026, 11, 20, tzinfo=UTC), tgb=None):
    return M.telegram_karsilastir(rows, now=now, kayit=kayit or {}, isaretli=isaretli, imlec=imlec, tg_baslangic=tgb)


def _log(rows, tur_yon=None, kz=None):
    out = {}
    for r in rows:
        for tur, t in (("acildi", r["_a"]), ("kapandi", r["_k"])):
            if t is not None:
                out[(r["islem_no"], tur)] = {"yon": (tur_yon or {}).get(r["islem_no"], r["yon"]), "_ts": t + timedelta(minutes=1),
                                             "kz": (kz or {}).get(r["islem_no"], r["net"])}
    return out


def test_telegram_pre_message_system_trades_are_not_mismatches():
    rows = motor(tr(1, day=10), tr(2, day=18))
    kayit = {k: v for k, v in _log(rows).items() if k[0] == 2}        # kayit ilk 18 Kasim'da basladi
    _tg(rows, kayit)
    assert rows[0]["telegram_acildi"] == rows[0]["telegram_kapandi"] == M.TG_ONCESI and not rows[0]["uyusmazlik"]
    assert rows[1]["telegram_acildi"] == "gönderildi (kayıt)" and not rows[1]["uyusmazlik"]
    # kayit hic yok + imlec hic yok: Telegram hic calismamis -> hepsi 'oncesi'
    rows = motor(tr(1), tr(2))
    _tg(rows)
    assert {r["telegram_kapandi"] for r in rows} == {M.TG_ONCESI}


def test_telegram_missing_wrong_side_wrong_pnl_and_extra():
    rows = motor(tr(1), tr(2), tr(3), tr(4))
    kayit = _log(rows, tur_yon={2: "short"}, kz={3: 99.0})
    del kayit[(4, "kapandi")]
    kayit[(77, "acildi")] = {"yon": "long", "_ts": datetime(2026, 11, 15, tzinfo=UTC), "kz": None}
    fazla = _tg(rows, kayit, imlec={"acilan": [1, 2, 3, 4], "kapanan": [1, 2, 3, 4]})
    assert rows[1]["telegram_acildi"] == M.TG_YON and rows[2]["telegram_kapandi"] == M.TG_KZ
    assert rows[3]["telegram_kapandi"] == M.TG_EKSIK          # kayit tutuluyor ama bu mesajin kaydi yok
    assert fazla == ["Telegram'da fazla işlem #77 (defterde yok)"]
    d = M.ozet(rows, [], fazla, now=datetime(2026, 11, 20, tzinfo=UTC))
    assert (d["telegram"]["eksik"], d["telegram"]["yanlis_yon"], d["telegram"]["yanlis_kz"], d["telegram"]["fazla"]) == (1, 2, 1, 1)
    assert d["uyusmazlik_sayisi"] == 4


def test_telegram_cursor_only_and_outbox_marker_sources():
    rows = motor(tr(1, day=18), tr(2, day=18), tr(3, day=18))
    imlec = {"acilan": [1, 2, 3], "kapanan": [1, 3]}
    _tg(rows, imlec=imlec, isaretli=lambda i, t: (i, t) == (2, "kapandi"))
    assert rows[0]["telegram_kapandi"] == "gönderildi (imleç)"
    assert rows[1]["telegram_kapandi"] == "gönderildi (outbox işareti)"
    rows = motor(tr(5, day=18), tr(9, day=18))
    _tg(rows, imlec={"acilan": [5, 7], "kapanan": [5]})                # 9 imlecte yok, imlec kimligi daha kucuk -> eksik
    assert rows[1]["telegram_kapandi"] == M.TG_EKSIK
    rows = motor(tr(3, day=18), tr(9, day=18))
    _tg(rows, imlec={"acilan": [5, 7], "kapanan": [5]})                # 3 imlec araligindan eski -> mesaj sistemi oncesi
    assert rows[0]["telegram_kapandi"] == M.TG_ONCESI


def test_recent_event_waits_instead_of_missing():
    rows = motor(tr(1, day=20))
    _tg(rows, imlec={"acilan": [], "kapanan": []}, now=rows[0]["_k"] + timedelta(minutes=3))
    assert rows[0]["telegram_kapandi"] == M.TG_BEKLEMEDE and "telegram kapandi: eksik" not in rows[0]["uyusmazlik"]


# ---------------------------------------------------------------------------------------------------- kontroller
def _acik(**k):
    return {"trade_id": 7, "side": "long", "entry_price": 100.0, "qty": 2.0, "fee_paid_entry": 0.4, "funding_paid": 0.0,
            "partial_realized_usd": 0.0, "partial_fee_usd": 0.0, **k}


def test_kasa_equation_with_fees_and_funding():
    rows = motor(tr(1, net=10.0, fee_e=0.5, fee_x=0.5, fund=0.2), tr(2, net=-4.0, fee_e=0.3, fee_x=0.3, fund=-0.1))
    net = M.toplamlar(rows)["tumu"]["net"]
    assert net == pytest.approx(6.0)
    kw = dict(baslangic=1000.0, net_sql=6.0, net_motor=net)
    assert M.kontrol_kasa(**kw, status={"wallet": 1006.0, "open_positions": []})["sonuc"] == "geçti"
    # acik pozisyon: giris komisyonu kasadan dusmus
    assert M.kontrol_kasa(**kw, status={"wallet": 1005.6, "open_positions": [_acik()]})["sonuc"] == "geçti"
    # kismi cikis (brut +3,00, komisyon 0,10) ve acik pozisyonda odenen fonlama (0,25) kasaya hemen islenir
    st = {"wallet": 1006.0 - 0.4 - 0.25 + 3.0 - 0.10,
          "open_positions": [_acik(funding_paid=0.25, partial_realized_usd=3.0, partial_fee_usd=0.10)]}
    k = M.kontrol_kasa(**kw, status=st)
    assert k["sonuc"] == "geçti" and k["ayrinti"] == "Kasa 1.008,25 $ tutuyor"
    # gercek uyusmazlik: sade Turkce metin, formul/Σ/4 hane yok
    k = M.kontrol_kasa(**kw, status={"wallet": 1005.1, "open_positions": [_acik()]})
    assert k["sonuc"] == "kaldı" and k["ayrinti"] == "Kasa 1.005,60 $ olmalı, kayıtta 1.005,10 $ · fark 0,50 $"
    assert "Σ" not in k["ayrinti"] and "=" not in k["ayrinti"]
    # eski motor (yeni alanlar yok): kaldi degil atlandi
    eski = {"wallet": 1005.6, "open_positions": [{"trade_id": 7, "side": "long", "entry_price": 100.0, "qty": 2.0}]}
    k = M.kontrol_kasa(**kw, status=eski)
    assert k["sonuc"] == "atlandı" and "eski sürüm" in k["ayrinti"]
    assert M.kontrol_kasa(**kw, status=None)["sonuc"] == "atlandı"
    assert M.kontrol_kasa(**kw, status={"equity": 1006.0, "open_positions": []})["sonuc"] == "atlandı"      # wallet yok
    # SQL toplami motor toplamindan sapiyorsa kaldi
    assert M.kontrol_kasa(baslangic=1000.0, net_sql=6.5, net_motor=net, status={"wallet": 1006.5, "open_positions": []})["sonuc"] == "kaldı"


def test_kasa_bilgi_satiri_ve_turkce_sayi():
    b = M.bilgi_acik_kz({"equity": 1010.0, "wallet": 1000.0, "unrealized_pnl_usd": 9.65})
    assert "fark 0,35 $" in b and "uyuşmazlık sayılmaz" in b and M.bilgi_acik_kz({"equity": 1.0}) is None
    assert M.usd(1021.4) == "1.021,40" and M.isr(-3.5) == "-3,50" and M.isr(23.6387) == "+23,64"


def test_open_position_count_mismatch():
    assert M.kontrol_acik(2, 2, 2, 2)["sonuc"] == "geçti"
    k = M.kontrol_acik(2, 2, 3, 2)
    assert k["sonuc"] == "kaldı" and "şerit 3" in k["ayrinti"]
    assert M.kontrol_acik(1, 1, 1, 2)["sonuc"] == "kaldı"


def test_long_short_totals_and_limit_and_open_pnl_source():
    rows = motor(tr(1, net=5.0), tr(2, "short", net=-2.0), tr(3, "short", net=1.0))
    tp = M.toplamlar(rows)
    assert (tp["long"]["n"], tp["short"]["n"], tp["short"]["net"]) == (1, 2, -1.0)
    kap = split(rows, panel_rows(rows))[0]
    assert all(k["sonuc"] == "geçti" for k in M.kontrol_long_short(tp, kap, 3, 4.0))
    kap[1] = {**kap[1], "yon": "long"}
    assert any(k["sonuc"] == "kaldı" for k in M.kontrol_long_short(tp, kap, 3, 4.0))
    assert M.kontrol_limit(0.08, 0.08)["sonuc"] == "geçti" and M.kontrol_limit(0.05, 0.08)["sonuc"] == "kaldı"
    pos = {"trade_id": 7, "side": "long", "entry_price": 100.0, "qty": 2.0, "mark": 101.0, "unrealized_pnl_usd": 2.0}
    ok = M.kontrol_acik_kz({"open_positions": [pos]}, [{"id": 7, "simdi": 101.0, "kz": 2.0}])
    assert ok["sonuc"] == "geçti" and "panelle aynı" in ok["ayrinti"]
    assert M.kontrol_acik_kz({"open_positions": [pos]}, [{"id": 7, "simdi": 101.0, "kz": 2.5}])["sonuc"] == "kaldı"


# ---------------------------------------------------------------------------------------------------- uctan uca (gercek defter + panel)
@pytest.fixture()
def env(tmp_path):
    e = Env(tmp_path)
    shutil.copy(ROOT / "config/engine.paper.json", tmp_path / "config/engine.paper.json")
    yield e
    e.close()


def _trades(env):
    led = P.open_ledger_ro(str(env.root / "var/learner/ledger.sqlite"), "learner")
    try:
        return led.list_closed_trades(None, None, 100), led.list_open_trades()
    finally:
        led.close()


def _setup(env, *, extra_open=False, equity_delta=0.0, wallet_delta=0.0, imlec=True, log=True):
    kap, ac = _trades(env)
    net = sum(t.realized_pnl for t in kap)
    fee_open = sum(t.fee_entry for t in ac)
    pos = [{"trade_id": t.trade_id, "pair": t.pair, "side": t.side, "qty": t.qty, "entry_price": t.entry_price, "stop": 1960.0,
            "mark": 2010.0, "fee_paid_entry": t.fee_entry, "funding_paid": 0.0, "partial_realized_usd": 0.0,
            "partial_fee_usd": 0.0, "notional_usd": t.qty * 2010.0, "unrealized_pnl_usd": (2010.0 - t.entry_price) * t.qty} for t in ac]
    unreal = sum(p["unrealized_pnl_usd"] for p in pos)
    if extra_open:
        pos.append({**pos[0], "trade_id": 99})
    env.write_status("learner", 5, wallet=1000.0 + net - fee_open + wallet_delta, equity=1000.0 + net - fee_open + unreal + equity_delta,
                     open_positions=pos, open_trade_ids=[p["trade_id"] for p in pos], unrealized_pnl_unused=0,
                     unrealized_pnl_usd=unreal)
    tg = env.root / "var/telegram"
    tg.mkdir(parents=True, exist_ok=True)
    if log:
        with open(tg / "islem_gonderildi.jsonl", "w", encoding="utf-8") as f:
            for t in kap + ac:
                f.write(json.dumps({"ts": (t.entry_ts + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), "trade_id": t.trade_id,
                                    "tur": "acildi", "yon": TS.yon(t.side), "coin": TS.coin(t.pair), "kz": None}) + "\n")
                if t.exit_ts:
                    f.write(json.dumps({"ts": (t.exit_ts + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), "trade_id": t.trade_id,
                                        "tur": "kapandi", "yon": TS.yon(t.side), "coin": TS.coin(t.pair), "kz": t.realized_pnl}) + "\n")
    return kap, ac


def _run(env):
    e = {"TELEGRAM_VAR_DIR": str(env.root / "var/telegram")}
    assert R.main(["--once", "--root", str(env.root)], now_fn=lambda: NOW, env=e) == 0
    return json.loads((env.root / "var/durum/mutabakat_v1.json").read_text(encoding="utf-8"))


def test_end_to_end_all_match(env):
    kap, ac = _setup(env)
    d = _run(env)
    assert d["islem_sayisi"] == len(kap) + len(ac) == 6 and d["acik"] == 1
    assert d["uyusmazlik_sayisi"] == 0, d["uyusmazliklar"]
    assert {k["sonuc"] for k in d["kontroller"]} == {"geçti"}, d["kontroller"]
    assert {r["panel"] for r in d["satirlar"]} == {"aynı"}
    assert {r["telegram_acildi"] for r in d["satirlar"]} == {"gönderildi (kayıt)"}
    assert all(set(r) >= {"islem_no", "kol", "coin", "yon", "acilis", "kapanis", "giris", "cikis", "net", "komisyon", "fonlama"} for r in d["satirlar"])
    assert d["satirlar"][0]["kol"] == "Yatay piyasa kenarı · 1 saat" and "_a" not in d["satirlar"][0]
    md = (env.root / "var/durum/mutabakat.md").read_text(encoding="utf-8")
    assert "İşlem no" in md and "Net K/Z $" in md and "Uyuşmazlık: 0" in md
    assert _outbox_items(env) == []      # her sey yolunda: kurulum kosusunda da HICBIR Telegram mesaji yok


def test_end_to_end_open_count_and_kasa_mismatch_and_daily_telegram(env):
    _setup(env, extra_open=True, wallet_delta=0.5)
    d = _run(env)
    ad = {k["ad"]: k for k in d["kontroller"]}
    assert ad["Açık pozisyon sayısı (motor = panel = şerit = durum)"]["sonuc"] == "kaldı"
    assert ad["Kasa = başlangıç + Σ net K/Z"]["sonuc"] == "kaldı"
    assert d["uyusmazlik_sayisi"] >= 2
    # kurulum kosusu: gercek sorun var -> TEK mesaj (WARN), sade, islem numarasi yok; ayni kosuda gunluk uyari ayrica gitmez
    tum = _outbox_items(env)
    assert [i["severity"] for i in tum] == ["WARN"]
    t = tum[0]["text"]
    assert t.startswith("[ML] ⚠️ ") and "Kasa kayıtla tutmuyor: " in t and "olmalı, kayıtta" in t and " $" in t
    assert "#" not in t and "Σ" not in t and "_" not in t and TS.kontrol(t) == [] and len(t.splitlines()) <= 4
    md = (env.root / "var/durum/mutabakat.md").read_text(encoding="utf-8")
    assert "olmalı, kayıtta" in md and "+0." not in md and "Anlık kâr/zarar" not in md
    # sonraki kosu ayni gun, ayni sorun: yeni mesaj yok
    e = {"TELEGRAM_VAR_DIR": str(env.root / "var/telegram")}
    assert R.main(["--once", "--root", str(env.root)], now_fn=lambda: NOW, env=e) == 0
    assert len(_outbox_items(env)) == 1
    assert R.main(["--once", "--root", str(env.root)], now_fn=lambda: NOW + timedelta(days=1), env=e) == 0   # ertesi gun de ayni icerik: yok
    assert len(_outbox_items(env)) == 1


def test_end_to_end_no_telegram_records_means_before_message_system(env):
    _setup(env, log=False)
    d = _run(env)
    assert {r["telegram_acildi"] for r in d["satirlar"]} == {M.TG_ONCESI}
    assert d["telegram"]["eksik"] == 0 and d["uyusmazlik_sayisi"] == 0
    assert "Telegram geçmişine erişim yok; motorun gönderdi kaydı (imleç) kullanıldı" in d["telegram"]["kaynak"]


def test_ledger_opened_read_only_and_unchanged(env):
    _setup(env)
    p = env.root / "var/learner/ledger.sqlite"
    before = p.read_bytes()
    _run(env)
    assert p.read_bytes() == before
    src = (ROOT / "scripts/mutabakat_run.py").read_text(encoding="utf-8")
    assert "open_ledger_ro" in src and "mode=ro" in src and "migrate=True" not in src


# ---------------------------------------------------------------------------------------------------- Telegram gonderim kaydi
def test_sent_log_append_only_never_blocks(tmp_path):
    t = tr(5, "short", "SOL/USDT")
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    T.gonderildi_yaz(tmp_path / "v", now, "kapandi", t, -3.14159265)
    T.gonderildi_yaz(tmp_path / "v", now, "acildi", t)
    ls = [json.loads(x) for x in (tmp_path / "v/islem_gonderildi.jsonl").read_text(encoding="utf-8").splitlines()]
    assert ls[0] == {"ts": "2026-11-20T12:00:00Z", "trade_id": 5, "tur": "kapandi", "yon": "short", "coin": "SOL", "kz": -3.141593}
    assert ls[1]["tur"] == "acildi" and ls[1]["kz"] is None
    blocker = tmp_path / "dosya"
    blocker.write_text("x")
    T.gonderildi_yaz(blocker / "alt", now, "acildi", t)          # yazilamaz: istisna disari cikmaz
    T.gonderildi_yaz(tmp_path, now, "acildi", object())          # bozuk girdi de yutulur


def test_islem_tick_writes_sent_log_only_for_delivered(tmp_path):
    src = (ROOT / "src/trader_core/telegram.py").read_text(encoding="utf-8")
    a = src.index("def islem_tick")
    body = src[a:src.index("def zarar_tick")]
    assert body.count("gonderildi_yaz(") == 2 and "if gitti:" in body
    assert R.gonderim_kaydi(tmp_path / "yok.jsonl") == {}
    p = tmp_path / "l.jsonl"
    p.write_text('bozuk\n{"ts":"2026-11-20T12:00:00Z","trade_id":3,"tur":"acildi","yon":"long"}\n', encoding="utf-8")
    assert list(R.gonderim_kaydi(p)) == [(3, "acildi")]


# ---------------------------------------------------------------------------------------------------- panel TEKNIK satiri
def test_panel_teknik_has_islem_kontrolu_when_json_exists(env):
    from trader_panel.data import PanelData, load_config
    d = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    assert "mutabakat" not in d.pano("learner")["teknik"]                    # json yok: gizli
    _setup(env)
    _run(env)
    t = PanelData(load_config(env.cfg_path), clock=lambda: NOW).pano("learner")["teknik"]
    assert {k: v for k, v in t["mutabakat"].items() if k != "yas_s"} == {"son": "16.11 21:00", "islem": 6, "uyusmazlik": 0}
    assert t["mutabakat"]["yas_s"] >= 0
    js = (ROOT / "src/trader_panel/static/panel.js").read_text(encoding="utf-8")
    assert "t.mutabakat" in js and "İşlem kontrolü" in js and "Son kontrol: " in js


def test_mutabakat_view_rejects_bad_files(tmp_path):
    from trader_core import panel_pano as PP
    p = tmp_path / "m.json"
    assert PP.mutabakat_view(str(p)) is None
    p.write_text("{bozuk")
    assert PP.mutabakat_view(str(p)) is None
    p.write_text(json.dumps({"sema": "baska"}))
    assert PP.mutabakat_view(str(p)) is None
    p.write_text(json.dumps({"sema": M.SEMA, "uretim": "2026-11-20T01:40:00Z", "islem_sayisi": 12, "uyusmazlik_sayisi": 2}))
    assert PP.mutabakat_view(str(p), datetime(2026, 11, 20, 2, 0, tzinfo=timezone.utc)) == {
        "son": "20.11 04:40", "islem": 12, "uyusmazlik": 2, "yas_s": 1200.0}


# ---------------------------------------------------------------- kurulum sonrasi tek seferlik sessiz ozet
def _outbox_items(env):
    out = []
    for p in sorted((env.root / "var" / "telegram" / "outbox").glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return out


def test_kurulum_mesaji_yalniz_sorun_varsa_ve_icerik_degisince(env, monkeypatch):
    _setup(env, wallet_delta=0.5)                                                      # gercek sorun: kasa tutmuyor
    e = {"TELEGRAM_VAR_DIR": str(env.root / "var" / "telegram")}

    def mesajlar():
        return [i for i in _outbox_items(env) if "Kasa kayıtla tutmuyor" in i.get("text", "")]

    monkeypatch.setattr(R, "kod_surumu", lambda *a, **k: "/rel/aaa")
    assert R.main(["--once", "--root", str(env.root)], now_fn=lambda: NOW, env=e) == 0
    assert len(mesajlar()) == 1 and mesajlar()[0]["severity"] == "WARN"
    assert R.main(["--once", "--root", str(env.root)], now_fn=lambda: NOW + timedelta(seconds=20), env=e) == 0
    assert len(mesajlar()) == 1                                                       # ayni surum: yok
    monkeypatch.setattr(R, "kod_surumu", lambda *a, **k: "/rel/bbb")
    assert R.main(["--once", "--root", str(env.root)], now_fn=lambda: NOW + timedelta(seconds=40), env=e) == 0
    assert len(mesajlar()) == 1                                                       # yeni kurulum ama AYNI icerik: tekrar yok
    _setup(env, wallet_delta=0.9)                                                     # ayni tur sorun ama tutarlar degisti -> yeni icerik
    monkeypatch.setattr(R, "kod_surumu", lambda *a, **k: "/rel/ccc")
    assert R.main(["--once", "--root", str(env.root)], now_fn=lambda: NOW + timedelta(seconds=60), env=e) == 0
    assert len(mesajlar()) == 2


def test_kurulum_saglamken_mesaj_yok(env, monkeypatch):
    _setup(env)
    e = {"TELEGRAM_VAR_DIR": str(env.root / "var" / "telegram")}
    monkeypatch.setattr(R, "kod_surumu", lambda *a, **k: "/rel/aaa")
    assert R.main(["--once", "--root", str(env.root)], now_fn=lambda: NOW, env=e) == 0
    assert _outbox_items(env) == []


def test_islem_kontrolu_ozet_text_examples_max_three():
    doc = {"islem_sayisi": 7, "acik": 2, "kapanan": 5, "uyusmazlik_sayisi": 4,
           "uyusmazliklar": ["#1 SOL long: panelde yok", "#2 BTC short: K/Z farkı", "#3 ETH long: yön", "#4 X long: y"],
           "satirlar": [{"yon": "long"}] * 4 + [{"yon": "short"}] * 3,
           "kontroller": [{"ad": "Kasa = başlangıç + Σ net K/Z", "sonuc": "geçti", "ayrinti": ""}]}
    t = TS.islem_kontrolu_ozet(doc)
    assert "7 işlem (açık 2 / kapanan 5 · long 4 / short 3) · uyuşmazlık 4 · kasa tutuyor" in t and "✅" not in t and "#" not in t
    assert t.count("\n- ") == 3 and "#4" not in t
    doc["kontroller"][0]["sonuc"] = "kaldı"
    assert "kasa tutmuyor" in TS.islem_kontrolu_ozet(doc) and "❌" not in TS.islem_kontrolu_ozet(doc)


def test_kurulum_ozeti_surum_release_dosyasindan_commit(env, tmp_path):
    """Surum kimligi /etc/trader-release COMMIT'idir; sorun varsa ilk kurulumda bir mesaj, ayni icerikle yeni commit'te yok."""
    _setup(env, wallet_delta=0.5)
    rel = tmp_path / "trader-release"
    e = {"TELEGRAM_VAR_DIR": str(env.root / "var" / "telegram"), "MUTABAKAT_RELEASE_FILE": str(rel)}

    def ozetler():
        return [i for i in _outbox_items(env) if "Kasa kayıtla tutmuyor" in i.get("text", "")]

    def kos(dk):
        assert R.main(["--once", "--root", str(env.root)], now_fn=lambda: NOW + timedelta(minutes=dk), env=e) == 0

    rel.write_text("COMMIT=" + "a" * 40 + "\n", encoding="utf-8")
    kos(0)
    assert len(ozetler()) == 1
    kos(5)
    assert len(ozetler()) == 1
    rel.write_text("COMMIT=" + "b" * 40 + "\n", encoding="utf-8")
    kos(10)
    assert len(ozetler()) == 1                                                       # yeni commit, ayni sonuc: tekrar yok
    kos(15)
    assert len(ozetler()) == 1


def test_kod_surumu_release_yoksa_yola_duser(tmp_path):
    a = R.kod_surumu({"MUTABAKAT_RELEASE_FILE": str(tmp_path / "yok")})
    assert a == str(Path(R.__file__).resolve().parent.parent)
    (tmp_path / "r").write_text("COMMIT=\n", encoding="utf-8")
    assert R.kod_surumu({"MUTABAKAT_RELEASE_FILE": str(tmp_path / "r")}) == a


def test_acik_kz_race_retry_passes_when_second_read_matches(env, monkeypatch):
    _setup(env)
    real, calls = M.kontrol_acik_kz, []

    def fake(status, rows):
        calls.append(1)
        if len(calls) == 1:   # motor pano ile durum arasinda yeni durum yazdi
            return M.kontrol("Açık K/Z fiyat kaynağı (panel = motor mark)", False, "Açık işlem kâr/zararı panelde farklı: #1 fark 0,03 $")
        return real(status, rows)
    monkeypatch.setattr(R.M, "kontrol_acik_kz", fake)
    d = _run(env)
    assert len(calls) == 2
    kz = [k for k in d["kontroller"] if k["ad"].startswith("Açık K/Z fiyat")]
    assert kz and kz[0]["sonuc"] == "geçti"


def test_acik_kz_real_mismatch_still_reported_after_retry(env, monkeypatch):
    _setup(env)
    calls = []

    def fake(status, rows):
        calls.append(1)
        return M.kontrol("Açık K/Z fiyat kaynağı (panel = motor mark)", False, "Açık işlem kâr/zararı panelde farklı: #1 fark 0,30 $")
    monkeypatch.setattr(R.M, "kontrol_acik_kz", fake)
    d = _run(env)
    assert len(calls) == 2
    kz = [k for k in d["kontroller"] if k["ad"].startswith("Açık K/Z fiyat")]
    assert kz[0]["sonuc"] == "kaldı"
