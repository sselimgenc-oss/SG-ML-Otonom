"""Yeni pano: sade Turkce veri katmani, risk durumu, TSI gunu, bos kart gizleme, kol adi, yasak metin taramasi."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from panel_support import NOW, ROOT, Env, status_doc
from trader_core import panel_data as P
from trader_core import panel_pano as PP
from trader_core import tg_sade as TS
from trader_panel.data import PanelData, load_config

STATIC = ROOT / "src/trader_panel/static"
UTC = timezone.utc


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    e = Env(tmp_path_factory.mktemp("pano"))
    yield e
    e.close()


@pytest.fixture(scope="module")
def pano(env):
    return PanelData(load_config(env.cfg_path), clock=lambda: NOW).pano("learner")


def walk_strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from walk_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk_strings(v)


def test_limit_equals_single_source_not_hardcoded_5pct(pano):
    r = pano["serit"]["risk"]
    assert r["limit_orani"] == P.daily_loss_rate("paper")
    assert r["limit"] == pytest.approx(P.daily_loss_rate("paper") * 1000.0)       # day_start_equity fikstur = 1000
    assert r["limit"] != pytest.approx(0.05 * 1000.0) or P.daily_loss_rate("paper") == 0.05
    src = (ROOT / "src/trader_core/panel_pano.py").read_text(encoding="utf-8")
    assert "0.05" not in src and "* 0.05" not in src


def test_risk_status_levels():
    live = {"mode": "paper", "day_start_equity": 1000.0, "equity": 1000.0, "entries_open": True}
    lim = P.daily_loss_rate("paper") * 1000.0
    g = PP.risk_durumu(live, "live", False, 0.0)
    assert g["renk"] == "yesil" and g["metin"] == "Güvenli" and "günlük limite kalan" in g["alt"]
    y = PP.risk_durumu(live, "live", False, -0.7 * lim)
    assert y["renk"] == "sari" and y["metin"] == "Limite yakın"
    assert PP.risk_durumu(live, "live", False, -0.69 * lim)["renk"] == "yesil"
    k = PP.risk_durumu({**live, "entries_open": False, "entries_blocked_reason": "stale_data"}, "live", False, 0.0)
    assert k["renk"] == "kirmizi" and k["metin"] == "Durdu: piyasa verisi eski"
    d = PP.risk_durumu(live, "live", False, -lim)
    assert d["renk"] == "kirmizi" and "limiti doldu" in d["metin"]
    st = PP.risk_durumu(None, "stale", False, 5.0, 7200.0)             # durum eski: gri, limit/kalan yok (eski sayi canli gibi gosterilmez)
    assert st["renk"] == "gri" and st["metin"] == "Bilinmiyor (durum bilgisi eski)" and st["limit"] is None and st["kalan"] is None
    assert "limite kalan —" in st["alt"] and "2 sa önce" in st["alt"] and not re.search(r"\d+,\d\d \$", st["alt"])
    assert PP.risk_durumu(None, "missing", False, 0.0)["renk"] == "gri"
    for eksik in ({"equity": None}, {"day_start_equity": None}):         # kasa ya da gun basi yok: gri Bilinmiyor
        m = PP.risk_durumu({**live, **eksik}, "live", False, 0.0)
        assert m["renk"] == "gri" and m["metin"].startswith("Bilinmiyor") and m["kalan"] is None and m["alt"].endswith("—")
    assert PP.risk_durumu(live, "live", True, 0.0)["metin"] == "Durdu: acil durdurma"
    unk = PP.risk_durumu({**live, "entries_open": False, "entries_blocked_reason": "yeni_bilinmeyen_kod"}, "live", False, 0.0)
    assert "_" not in unk["metin"] and "bilinmeyen" not in unk["metin"]


def test_no_raw_codes_files_sha_utc_in_data_layer(pano, env):
    d = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    texts = list(walk_strings(pano)) + list(walk_strings(d.kapanan("learner", "tumu")))
    bad = re.compile(r"\.(py|json|sqlite)\b|sha256|UTC|\bT\d\d:\d\d|\d{4}-\d{2}-\d{2}|gate_code|entries_blocked|[a-z]+_[a-z]+")
    for t in texts:
        if t in ("learner", "bot_durum") or re.fullmatch(r"\d{4}-\d{2}-\d{2}T[\d:.]+Z", t):
            continue
        assert not bad.search(t), t


def test_kol_adi_used_like_telegram(env):
    d = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    rows = d.kapanan("learner", "tumu")["rows"]
    assert rows and all(r["kol"] == TS.kol_adi("R1@1h") == "Yatay piyasa kenarı · 1 saat" for r in rows)
    assert all(r["coin"] in ("ETH", "BTC") and r["yon"] == "long" for r in rows)
    assert d.pano("learner")["acik"]["rows"][0]["kol"] == "Yatay piyasa kenarı · 1 saat"


def test_closed_row_has_size_leverage_margin(env):
    d = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    rows = d.kapanan("learner", "tumu")["rows"]
    assert rows
    for r in rows:
        assert r["buyukluk"] is not None and r["buyukluk"] > 0
        assert "kaldirac" in r and "marj" in r
        if r["kaldirac"]:
            assert r["marj"] == pytest.approx(r["buyukluk"] / r["kaldirac"])
        else:
            assert r["marj"] is None
        assert isinstance(r["kapanis_ts"], float)


def test_tsi_day_boundary(env):
    d = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    # 2026-11-15 21:30 UTC = 16.11 00:30 TSI => 16.11 gunune dahil, 15.11'e degil; 20:59 UTC = 15.11 23:59 TSI
    a, b = PP.period_bounds("bugun", datetime(2026, 11, 16, 18, 0, tzinfo=UTC))
    assert a == datetime(2026, 11, 15, 21, 0, tzinfo=UTC) and b == datetime(2026, 11, 16, 21, 0, tzinfo=UTC)
    a2, _ = PP.period_bounds("bugun", datetime(2026, 11, 16, 20, 59, tzinfo=UTC))
    assert a2 == datetime(2026, 11, 15, 21, 0, tzinfo=UTC)
    a3, _ = PP.period_bounds("bugun", datetime(2026, 11, 16, 21, 0, tzinfo=UTC))      # 17.11 00:00 TSI: yeni gun
    assert a3 == datetime(2026, 11, 16, 21, 0, tzinfo=UTC)
    assert PP.tsi_kisa(datetime(2026, 11, 15, 21, 30, tzinfo=UTC)) == "16.11 00:30"
    assert d.kapanan("learner", "bugun")["n"] == 2          # 16.11 (TSI) kapanislari: fikstur 2 adet
    assert d.kapanan("learner", "tumu")["n"] == 5


def test_empty_cards_hidden_and_unmeasured_text(pano):
    assert "ders" not in pano                                  # 25.11: ders sistemi kaldirildi; ders karti yok
    assert "ml" not in pano                                    # 24.11: makine ogrenmesi karti (ML filtresi) silindi
    z = pano["kz"]
    assert z["oran"]["kazanma_yuzde"] == 60.0                    # 5 islem >= asgari
    o = PP.olculemedi(8, 30)
    assert o == {"olculemedi": "Henüz ölçülemedi (8 işlem, en az 30 gerek)"}


def test_unmeasured_win_rate_when_few_trades(tmp_path):
    from panel_support import mkledger, STD_LEARNER
    p = tmp_path / "l.sqlite"
    mkledger(p, "learner", STD_LEARNER[:2])
    ctx = PP.Ctx(str(p))
    kz = PP.kz_view(ctx, 1000.0, NOW, None)
    assert kz["oran"] == {"olculemedi": "Henüz ölçülemedi (2 işlem, en az 5 gerek)"}
    assert kz["egri"] is None


def test_invalid_period_rejected(env):
    d = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    assert d.kapanan("learner", "yil")["ok"] is False


# ---------------- panel.js / html yasak metin taramasi
def _js_code():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)                  # yorumlar goruntulenmez
    return re.sub(r"(?m)(?<![:'\"])//.*$", "", js)


def test_panel_js_free_of_forbidden_text():
    js = _js_code() + (STATIC / "index.html").read_text(encoding="utf-8")
    for bad in ("gate_code", "entries_blocked_reason", "sha256", "commit", "UTC", "/onayla", "kill dosyası", "journalctl",
                "param_version_id", ".sqlite", "panel.py"):
        assert bad not in js, bad
    assert not re.search(r"\b5\s*%|0\.05\b", js)
    assert "Salt okunur panel" not in js
    assert not re.search(r"['\"][\w/-]+\.(json|py|sqlite)['\"]", js)


def test_panel_js_new_structure():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    for t in ("ÖZET", "AÇIK", "KAPANAN", "K/Z", "ML1", "TEKNİK", "Risk durumu", "Zirveden düşüş", "Toplam K/Z", "Kasa = başlangıç + kapanan K/Z + açık K/Z − açık işlemlerin giriş komisyonu", "'açık K/Z ' + usdS(s.acik_kz)", "Bugün K/Z", "Açık işlem",
              "window.self !== window.top", "data-theme", "YENILE_S = 300", "son güncelleme"):
        assert t in js, t
    assert "TAB_MS" not in js and "setInterval" in js and "location.reload" in js
    css = (STATIC / "panel.css").read_text(encoding="utf-8")
    assert "repeat(3,minmax(0,1fr))" in css and "repeat(6,minmax(0,1fr))" in css and ".gomulu .ust{display:none}" in css


# ---------------- Turkce bicim, ek yardimcisi, ML durumlari
def _node_js(code: str) -> str:
    import shutil
    import subprocess
    if shutil.which("node") is None:
        pytest.skip("node yok")
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_turkish_suffix_helper_and_number_format():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    fn = js.split("/* ek:basla")[1].split("*/", 1)[1].split("/* ek:bitir */")[0]
    trn = re.search(r"  function trn\(x, d\) \{.*?\n  \}\n", js, re.S).group(0)
    want = {1: "i", 2: "si", 3: "ü", 4: "ü", 5: "i", 6: "sı", 7: "si", 8: "i", 9: "u", 10: "u", 20: "si", 30: "u", 40: "ı", 50: "si",
            60: "ı", 70: "i", 80: "i", 90: "ı", 100: "ü", 1000: "i"}
    out = _node_js(trn + fn + f"for (const n of {list(want)}) console.log(n + ek(n)); console.log(trn(1428.4)); console.log(trn(-7.2)); console.log(trn(0.5, 1));")
    lines = out.split("\n")
    for line, (n, e) in zip(lines, want.items()):
        assert line == f"{n}'{e}", line
    assert lines[len(want):len(want) + 3] == ["1.428,40", "7,20", "0,5"]


def test_server_number_format_turkish():
    assert PP.tr_sayi(1428.4) == "1.428,40" and PP.tr_sayi(-7.2) == "7,20" and PP.tr_sayi(1000000) == "1.000.000,00"


def test_strip_has_start_not_kasa_pct_and_title_turkish(pano):
    assert pano["serit"]["baslangic"] == 1000.0 and "kasa_yuzde" not in pano["serit"]
    assert "<h1>İşlem Botu</h1>" in (STATIC / "index.html").read_text(encoding="utf-8")


def test_partial_state_is_not_healthy_and_says_why():
    k = ["bir özellik işlemleri etkilemiyor"]
    y = PP.ne_yapmali("live", {"renk": "yesil"}, 3, k)
    assert y.startswith("Bir şey yapmanız gerekmiyor; bir özellik işlemleri")


def _h(overall, *fps):
    return {"overall": overall, "check_stale": False,
            "alerts": [{"name": n, "code": c, "level": lv} for n, c, lv in fps]}


def _tv(health):
    return PP.teknik_view(health=health, risk_rows=None, budget=None, tut=None, pbo=None, ctx=None)


def test_saglik_uyarisi_adiyla_gorunur_ve_isik_ne_yapmali():
    t = _tv(_h("WARN", ("candle_age:learner", "candle_stale", "WARN"), ("backup_age", "backup_stale", "WARN")))["saglik"]
    assert t["renk"] == "sari" and t["uyarilar"] == ["Piyasa verisi güncel değil", "Yedek alınmıyor ya da çok eski"]
    assert "kod" not in " ".join(t["uyarilar"]) and "_" not in " ".join(t["uyarilar"])
    isik = PP._problem(t, "live", {"renk": "yesil"}, None)
    assert isik["renk"] == "sari" and "Piyasa verisi güncel değil" in isik["metin"]
    y = PP.ne_yapmali("live", {"renk": "yesil"}, 2, [], t)
    assert y.startswith("Bir şey yapmanız gerekmiyor; sağlık uyarısı inceleniyor: Piyasa verisi güncel değil")


def test_saglik_kritik_kirmizi_senden_eylemi_ve_warmup_eki():
    t = _tv(_h("CRIT", ("disk_free", "disk_low", "CRIT"), ("bot_loop_age:learner", "stale_loop_warmup", "WARN")))["saglik"]
    assert t["renk"] == "kirmizi" and "Disk neredeyse dolu" in t["uyarilar"][0] and "Bot döngüsü durmuş görünüyor" in t["uyarilar"]
    assert PP._problem(t, "live", {"renk": "yesil"}, None)["renk"] == "kirmizi"
    y = PP.ne_yapmali("live", {"renk": "yesil"}, 0, [], t)
    assert y.startswith("Sağlık uyarısı: Disk neredeyse dolu") and "yer açılması" in y
    assert "uyarı" in PP.ne_yapmali("live", {"renk": "kirmizi"}, 0, [], t)                  # risk durumunda da anılır


def test_saglik_bilinmeyen_kod_ve_adsiz_warn_kod_sizmaz():
    t = _tv(_h("WARN", ("yeni_kontrol_x", "yeni_kod_y", "WARN")))["saglik"]
    assert t["uyarilar"] == ["Bir sistem kontrolü uyarı veriyor (kod gösterilmez)"]
    assert _tv(_h("WARN"))["saglik"]["renk"] == "sari"                                     # kayit yok ama genel durum WARN: yine sari
    assert _tv(_h("OK"))["saglik"]["renk"] == "yesil" and _tv(_h("OK", ("backup_age", "ok", "OK")))["saglik"]["uyarilar"] == []
    assert PP.ne_yapmali("live", {"renk": "yesil"}, 0, [], _tv(_h("OK"))["saglik"]).startswith("Bir şey yapmanız gerekmiyor; bot")


def test_testnet_capital_missing_does_not_redden_paper():
    h = _h("CRIT", ("risk_ladder:learner@testnet", "capital_missing", "CRIT"), ("backup_age", "ok", "OK"))
    sg = _tv(h)["saglik"]
    assert sg["renk"] == "yesil" and sg["durum"] == "Sistem sağlıklı" and sg["uyarilar"] == [] and sg["senden"] == []
    assert sg["diger_botlar"] == ["Testnet botu: sermaye kaydı girilmemiş (gerçek paraya geçişte yapılacak)"]
    assert "inceleniyor" not in (PP.saglik_yapmali(sg) or "")
    assert PP._problem(sg, "live", {"renk": "yesil"}, None)["renk"] == "yesil"
    # kagit botun kendi sorunu yine gorunur
    sg2 = _tv(_h("CRIT", ("risk_ladder:learner@testnet", "capital_missing", "CRIT"), ("candle_age:learner", "candle_stale", "CRIT")))["saglik"]
    assert sg2["renk"] == "kirmizi" and sg2["uyarilar"] and sg2["diger_botlar"]


def test_telegram_silent_for_testnet_ladder_alert():
    from types import SimpleNamespace
    a = SimpleNamespace(code="capital_missing", fingerprint="risk_ladder:learner@testnet|capital_missing", level="CRIT", title="")
    assert TS.saglik_mesaji(a)[0] == "sustur"


def test_stale_status_strip_grey_no_live_numbers(env, tmp_path):
    import shutil
    d = PanelData(load_config(env.cfg_path), clock=lambda: NOW + timedelta(hours=2)).pano("learner")      # durum dosyasi 2 saat eski
    r = d["serit"]["risk"]
    assert d["bot_durum"] == "stale" and r["renk"] == "gri" and r["limit"] is None and r["kalan"] is None
    assert d["serit"]["kasa"] is None and d["serit"]["durum_yasi_s"] >= 7000
    assert "limite kalan —" in r["alt"]


# ---------------- 28.11 duzeltme: sayi bicimi, serit, kartlar, telefon duzeni
def _js_fn(name: str) -> str:
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    m = re.search(rf"  function {name}\(.*?\n  \}}\n|  function {name}\([^\n]*\}}\n", js, re.S)
    assert m, name
    return m.group(0)


def test_js_sifira_yuvarlanan_sayida_isaret_yok():
    """V-11: gosterilen basamaga yuvarlaninca sifir olan deger isaretsiz; digerleri degismez; rakam ile birim bolunmez (G-03)."""
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    fns = "".join(_js_fn(n) for n in ("trn", "num", "sifir", "f2", "sgn", "usd", "usdS", "pc"))
    out = _node_js(fns + """
console.log([sgn(-0.004), sgn(0.004), sgn(0), sgn(-0.006), sgn(1.5), sgn(-1.5), pc(-0.0001), pc(0.0001), pc(1.234), pc(-1.234),
  f2(-0.001), f2(-2), usdS(-0.004), usdS(12.5), usd(-0.001)].join('|'));""").strip()
    assert out == "0,00|0,00|0,00|−0,01|+1,50|−1,50|%0,00|%0,00|+%1,23|−%1,23|0,00|−2,00|0,00 $|+12,50 $|0,00 $"
    assert "\\u00a0R" in js and "' $'" not in js                      # R de bolunmez; $ onunde yalniz NBSP


def test_serit_etiketleri_ve_zirveden_dusus_aciklamasi():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    top = js.split("function renderTop")[1].split("/* ---------- sekmeler")[0]
    assert "sk('Bugün K/Z'" in top and "Bugün kapanan" not in js and "sk('Açık işlem'" in top and "Açık poz." not in js    # G-04, M-01
    assert "s.toplam_kaynak === 'kasa' ? pc(s.dusus_yuzde) + ' · açık işlemler dahil'" in top and "sk('Zirveden düşüş'" in top    # V-08
    assert "kasa-not" in js and 'id="kasa-not"' in (STATIC / "index.html").read_text(encoding="utf-8") and "KASA_IPUCU" in js      # G-07: ? dokununca gorunur satir
    assert "q.title = KASA_IPUCU" in js and "aria-label" in js


def test_ozet_ve_kz_kartlari_tek_acik_kz_rakami():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    ozet = js.split("function tabOzet")[1].split("function isikKart")[0]
    assert "satir('Adet'" not in ozet and "satir('Toplam K/Z'" not in ozet and "Açık en iyi" in ozet and "Açık en kötü" in ozet            # V-01, M-01
    kz = js.split("function tabKz")[1].split("/* ML1 */")[0]
    assert "Açık işlemlerden (şu anki değer)'" in kz and "t.acik_brut" in kz and "Açık işlemlerin giriş komisyonu" in kz and "t.acik_komisyon" in kz
    assert "Kazanma oranı · tüm işlemler" in kz and "Diğer (fonlama vb.)" in kz and "'uyar'" not in kz                                    # A-13
    assert "Fonlama (+ = alınan)" in kz and "· 30 gün'" not in kz.split("kart('Masraflar')")[1] and "link('Fikir grubuna göre ayrıntı'" not in kz   # M-04, K-04
    assert PP.FARK_GOSTER == 1.0


def test_kapanan_tablosu_dort_sutun_kisa_neden_ayrintida_tam():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    kap = js.split("function yukleKapanan")[1].split("/* K/Z */")[0]
    assert "tablo(['Sembol', 'Kapanış', 'K/Z', 'Neden']" in kap and "'Büyüklük', 'Neden'" not in kap and "r.neden_kisa" in kap      # G-02, K-03
    assert "['Büyüklük', usd(r.buyukluk)]" in kap and "['Neden', r.neden]" in kap and "r.neden_aciklama" in kap                     # ayrintida kalir


def test_closed_row_neden_kisa(env):
    d = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    rows = d.kapanan("learner", "tumu")["rows"]
    assert rows and all("neden_kisa" in r and r["neden_kisa"] == r["neden"].partition(" (")[0] for r in rows)
    other = TS.ilk_buyuk(TS.kapanis_neden("other"))
    assert other == "Bot kapattı (kural/koruma)" and other.partition(" (")[0] == "Bot kapattı"                                          # kisa metin parantez onceki kisim


def test_ml1_tablolari_basliklar_kisa_ve_acik_sutunu_yok():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    assert "tablo(['Zaman dilimi', 'Adet', 'Kazanma', 'Net R', 'K/Z']" in js and "tablo(['Fikir grubu', 'Adet', 'Kazanma', 'Net R', 'K/Z']" in js
    assert "'Kazanan'" not in js and "'İşlem', 'Kazanan'" not in js and "'Açık']" not in js                                           # G-01
    css = (STATIC / "panel.css").read_text(encoding="utf-8")
    th = re.search(r"(?m)^th\{[^}]*\}", css).group(0)
    assert "white-space:nowrap" in th and "overflow-wrap:anywhere" not in re.search(r"th\.sirali\{[^}]*\}", css).group(0)


def test_telefon_css_yazi_boyu_dokunma_hedefi_ve_olu_kod():
    css = (STATIC / "panel.css").read_text(encoding="utf-8")
    mobil = css.split("@media (max-width:420px){", 1)[1].split("}\n@media print", 1)[0]
    assert re.search(r"\.tabs button\{font-size:(1[1-9][.\d]*)px", mobil) and float(re.search(r"\.tabs button\{font-size:([\d.]+)px", mobil).group(1)) >= 11.5
    assert float(re.search(r"\.ks \.e\{font-size:([\d.]+)px", mobil).group(1)) >= 11
    assert float(re.search(r"\.ks \.e \.ipucu\{[^}]*font-size:([\d.]+)px", css).group(1)) >= 11
    assert ".tabs button,#yenile,#tema,.donem button{min-height:40px}" in css                                                          # G-06
    assert "td.sg .n,td.sg .u{white-space:nowrap" in css                                                                              # G-03
    for olu in (".d4", ".baz{", ".og .kolad"):                                                                                         # K-05
        assert olu not in css, olu


def test_teknik_sekmesi_yalniz_kalan_kartlar_ve_olu_js_yok():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    tek = js.split("function tabTeknik")[1].split("function ciz")[0]
    for kalan in ("'Sağlık'", "'Risk limitleri'", "'İşlem kontrolü'"):
        assert kalan in tek, kalan
    for kalkan in ("Yapay zekâ yorum harcaması", "'Kayıtlar'", "Backtest / doğrulama", "'Dayanıklılık'"):                              # K-01: UI cizmez
        assert kalkan not in js, kalkan
    for olu in ("function etiketTsi", "function kzHatasi", "function boldMetin"):                                                     # K-05
        assert olu not in js, olu
    assert "t.mutabakat.yas_s" in tek and "ago(t.mutabakat.yas_s)" in tek


def test_teknik_payload_kaldirilan_kartlarin_verisini_hala_tasir(env):
    t = PanelData(load_config(env.cfg_path), clock=lambda: NOW).pano("learner")["teknik"]
    assert "kayitlar" in t and "butce" in t                              # veri uretilir (baska testler okur); UI cizmez (yukaridaki test)


def test_sayfa_yasi_bir_kez_ve_ml1_aciklama_yer_tutucusuz():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    snap = js.split("function snapBanner")[1].split("function get(")[0]
    assert "u.style.display = 'none'" in snap and "u.style.display = ''" in snap and "son güncelleme" in js                           # M-03
    acik = js.split("function ml1Aciklama")[1].split("function ml1Eleme")[0]
    assert "henüz okunamadı" not in acik and "Kurallar aday bulur; ML1 her adaya puan verir, puanı " in acik                           # K-02
    assert "' ve üstü olanlar'" in acik and "'yeterince yüksek olanlar'" in acik and "m.tf_satiri" not in acik and "m.durum_satiri" in acik   # M-02
    assert "Bu dönemde puanlanan aday yok." in js
