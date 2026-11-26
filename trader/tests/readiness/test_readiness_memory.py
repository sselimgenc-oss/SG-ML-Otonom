"""Hazirlik 8: bellek butcesi. Tum MemoryMax toplamlari 2 GB RAM + 4 GB takas (install.sh) ve baska projenin payi ile karsilastirilir."""
from __future__ import annotations

import re

from readiness_support import DEPLOY, install_text, unit_kv

RAM_MB, SWAP_MB = 2048, 4096
DAEMONS = ["trader-feed.service", "trader-engine@.service", "trader-panel.service", "trader-telegram.service"]
ONESHOTS = ["trader-health.service", "trader-backup.service", "trader-panel-publish.service"]


def _mem(name: str):
    for k, v in unit_kv((DEPLOY / name).read_text(encoding="utf-8")):
        if k == "MemoryMax":
            m = re.fullmatch(r"(\d+)M", v)
            assert m, (name, v)
            return int(m.group(1))
    return None


def test_every_long_running_and_heavy_unit_has_memory_max():
    for n in DAEMONS + ONESHOTS:
        assert _mem(n) is not None, n
    # sinirsiz kalanlar yalniz kisa omurlu, hafif tek seferlik birimler
    assert _mem("trader-counterfactual@.service") is not None
    unlimited = {p.name for p in DEPLOY.glob("trader-*.service") if _mem(p.name) is None}
    assert unlimited == {"trader-health-fail@.service", "trader-telegram-report.service"}, unlimited


def test_memory_budget_sums():
    always = _mem("trader-feed.service") + _mem("trader-engine@.service") + _mem("trader-panel.service") + _mem("trader-telegram.service")
    transient = sum(_mem(n) for n in ONESHOTS)
    cf = _mem("trader-counterfactual@.service")          # gece isi: yalniz ogrenen (DD-12: ikiz kaldirildi)
    worst = always + transient + cf
    assert always == 260 + 750 + 64 + 96 == 1170        # DD-12 §8: feed 260, ogrenen 750
    assert _mem("trader-counterfactual@.service") == 128
    assert worst == 1170 + 64 + 96 + 400 + 128 == 1858   # DD-12 WP-06a: veto birimi kalkti; 25.11: ders birimi (256 MB) kalkti
    # her zaman acik birimlerin SERT tavan toplami RAM'in %60'ini gecmez; boylece baska proje icin >= 800 MB kalir (OS ~150 MB dahil degil)
    assert always <= 0.6 * RAM_MB
    # en kotu ust uste binme bile RAM + takas icinde (OOM yerine takas); RAM'i asar -> swappiness=10 ve takas 4 GB sart
    assert worst < RAM_MB + SWAP_MB
    # 25.11: ders birimi (256 MB) kalkinca en kotu ust uste binme de RAM icine sigar (eskiden takasa girilirdi; denetim raporu OPEN-9)
    assert worst <= RAM_MB
    t = install_text()
    assert 'SWAP_SIZE="4G"' in t and "vm.swappiness=10" in t


def test_tutarlilik_weekly_oneshot_is_bounded_and_fits_slice():
    """Faz 2a: haftalik kagit-geri test tutarlilik birimi (pazartesi 00:30 UTC; kisa omurlu, `backtest --env paper`). Tavan olcume dayanir
    (docs/motor/tutarlilik-raporu-spec.md notu); gece isleri (counterfactual 23:10) ile cakismaz; toplam butceye girer."""
    m = _mem("trader-tutarlilik.service")
    assert m == 300                                                      # olculen tepe ~135 MB (44 cift, 7 gun, store) x ~2,2
    kv = _kv("trader-tutarlilik.service")
    assert kv["Slice"] == "trader.slice" and kv["Nice"] == "10"
    assert m <= int(_kv("trader.slice")["MemoryMax"][:-1]) // 2          # slice tavaninin yarisini asmaz
    worst = 1170 + 64 + 96 + 400 + 128 + m
    assert worst < RAM_MB + SWAP_MB
    tm = (DEPLOY / "trader-tutarlilik.timer").read_text(encoding="utf-8")
    assert "OnCalendar=Mon *-*-* 00:30:00 UTC" in tm and "Persistent=true" in tm


def test_veri_toplama_oneshots_are_bounded_and_fit_slice():
    """Veri toplama (saatlik, yalniz kayit; docs/veri-toplama-spec.md): saf stdlib, 100M tavan; haber yalniz var/veri yazar."""
    for ad, rw in (("haber", "/opt/trader/var/veri"), ("piyasa-veri", "/opt/trader")):
        m = _mem(f"trader-{ad}.service")
        assert m == 100
        kv = _kv(f"trader-{ad}.service")
        assert kv["Slice"] == "trader.slice" and kv["Nice"] == "15"
        assert kv["ReadWritePaths"] == rw + ("" if ad == "haber" else "/var") and kv["ProtectSystem"] == "strict" and kv["NoNewPrivileges"] == "true"
        assert m <= int(_kv("trader.slice")["MemoryMax"][:-1]) // 2
        assert 1170 + 64 + 96 + 400 + 128 + m < RAM_MB + SWAP_MB
        tm = (DEPLOY / f"trader-{ad}.timer").read_text(encoding="utf-8")
        assert "OnCalendar=hourly" in tm and "Persistent=true" in tm and "WantedBy=timers.target" in tm


def test_bakim_weekly_oneshot_is_bounded_and_fits_slice():
    """Haftalik disk bakimi (pazar 04:20 UTC): saf stdlib sqlite; olculen tepe RSS ~47 MB (65 MB defter VACUUM) -> 128M tavan; idle IO."""
    m = _mem("trader-bakim.service")
    assert m == 128
    kv = _kv("trader-bakim.service")
    assert kv["Slice"] == "trader.slice" and kv["Nice"] == "19" and kv["IOSchedulingClass"] == "idle"
    assert kv["ReadWritePaths"] == "/opt/trader/var" and kv["ProtectSystem"] == "strict" and kv["NoNewPrivileges"] == "true"
    assert m <= int(_kv("trader.slice")["MemoryMax"][:-1]) // 2
    assert 1170 + 64 + 96 + 400 + 128 + m < RAM_MB + SWAP_MB
    tm = (DEPLOY / "trader-bakim.timer").read_text(encoding="utf-8")
    assert "OnCalendar=Sun *-*-* 04:20:00 UTC" in tm and "Persistent=true" in tm and "WantedBy=timers.target" in tm


def test_mutabakat_daily_oneshot_is_bounded_and_fits_slice():
    """Islem mutabakati (her gun 04:40 UTC + kurulum sonrasi; saf stdlib, panel veri katmani): kucuk tavan, dusuk oncelik."""
    m = _mem("trader-mutabakat.service")
    assert m == 128
    kv = _kv("trader-mutabakat.service")
    assert kv["Slice"] == "trader.slice" and kv["Nice"] == "15" and kv["IOSchedulingClass"] == "idle"
    assert kv["ReadWritePaths"] == "/opt/trader/var/durum -/opt/trader/var/telegram"
    assert kv["ProtectSystem"] == "strict" and kv["NoNewPrivileges"] == "true" and kv["PrivateNetwork"] == "true"
    assert m <= int(_kv("trader.slice")["MemoryMax"][:-1]) // 2
    assert 1170 + 64 + 96 + 400 + 128 + m < RAM_MB + SWAP_MB
    tm = (DEPLOY / "trader-mutabakat.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 04:40:00 UTC" in tm and "Persistent=true" in tm and "WantedBy=timers.target" in tm
    t = install_text()
    assert "enable_now trader-mutabakat.timer" in t
    i = t.index('if [ -e "${UNIT_DIR}/trader-mutabakat.service" ]')                  # kurulum sonrasi bir kez; kurulumu durdurmaz
    blok = t[i:i + 400]
    assert "systemctl start --no-block trader-mutabakat.service" in blok and "fail " not in blok and "exit " not in blok
    assert i > t.index("enable_now trader-engine@learner.service") and i > t.index("systemctl restart trader-telegram.service")


def test_dd9_budget_with_live_and_testnet_units():
    """DD-9 duzenegi: butce = feed + max(kagit learner, canli) + testnet (+ pano, telegram); canli ile kagit learner AYNI ANDA calismaz.
    Toplam sert tavanlar trader.slice MemoryMax (1300M) ile sinirlanir; RAM+takas icinde kalir."""
    live, paper, testnet = _mem("trader-engine-live.service"), _mem("trader-engine@.service"), _mem("trader-engine-testnet.service")
    assert (live, testnet) == (750, 320)      # 23.11 kullanici karari: canli = kagit (canli MemoryMax 350M -> 750M, kagitla ayni)
    budget = (_mem("trader-feed.service") + max(paper, live) + testnet + _mem("trader-panel.service")
              + _mem("trader-telegram.service"))
    assert budget == 260 + 750 + 320 + 64 + 96 == 1490
    assert budget < RAM_MB + SWAP_MB
    slice_max = int(dict(unit_kv((DEPLOY / "trader.slice").read_text(encoding="utf-8")))["MemoryMax"][:-1])
    assert slice_max < budget            # slice tavani toplam sert tavanlardan kucuk: birlikte asilamaz
    assert _mem("trader-engine-env-retry@.service") == 64


def test_soft_cap_below_hard_cap_and_swap_not_unbounded():
    for n in ("trader-feed.service", "trader-engine@.service"):
        kv = dict(unit_kv((DEPLOY / n).read_text(encoding="utf-8")))
        assert int(kv["MemoryHigh"][:-1]) < int(kv["MemoryMax"][:-1])
        assert kv["CPUQuota"] == "60%"


def test_budget_assumes_twin_removed_and_installed_units_unchanged():
    """DD-12 WP-07: ikiz kaldirildi -> tek motor tavani (yukaridaki 1170 MB); install.sh ikizi etkinlestirmez, devre disi birakir."""
    t = install_text()
    assert "WITH_TWIN" not in t and "enable_now trader-engine@twin.service" not in t
    assert "trader-engine@twin.service" in t and "systemctl disable --now" in t
    # yeni birimler (veto-hmac env) bellek tavanlarini degistirmez; telegram-report hala sinirsiz hafif tek seferlik
    assert _mem("trader-telegram.service") == 96


def test_engine_retry_oneshot_is_bounded():
    assert _mem("trader-engine-retry@.service") == 64   # kisa omurlu, saglik birimiyle ayni tavan (toplam butceye eklenmez: saglikla ayni anda nadiren)


# ---- WP-D: trader.slice + OOM onceligi ----
def _kv(name: str) -> dict[str, str]:
    return dict(unit_kv((DEPLOY / name).read_text(encoding="utf-8")))


def test_trader_slice_exists_with_provisional_caps():
    p = DEPLOY / "trader.slice"
    assert p.exists()
    txt = p.read_text(encoding="utf-8")
    kv = _kv("trader.slice")
    assert kv["MemoryHigh"] == "1100M" and kv["MemoryMax"] == "1300M"
    assert "[Slice]" in txt
    assert "GECICI" in txt and "48" in txt          # sayilar gecici; 48 saatlik olcumle kesinlesir
    assert int(kv["MemoryHigh"][:-1]) < int(kv["MemoryMax"][:-1]) < RAM_MB * 0.7


def test_every_service_in_trader_slice():
    units = sorted(DEPLOY.glob("trader-*.service"))
    assert units
    for p in units:
        if p.name == "trader-oto-guncelle.service":     # kurulum isi: bilincli olarak slice disinda (motoru OOM'a sokmasin), kendi tavani
            assert _mem(p.name) == 800 and "Slice" not in _kv(p.name)
            continue
        assert _kv(p.name).get("Slice") == "trader.slice", p.name


def test_oom_score_adjust_policy():
    assert _kv("trader-panel-publish.service")["OOMScoreAdjust"] == "500"
    # motor ve feed son oldurulur (negatif deger root yonetici tarafindan uygulanir; sandbox engellemez)
    for n in ("trader-engine@.service", "trader-feed.service"):
        assert int(_kv(n)["OOMScoreAdjust"]) < 0, n
    # baska hicbir birim pozitif/negatif ayar almaz
    others = {p.name for p in DEPLOY.glob("trader-*.service") if "OOMScoreAdjust" in _kv(p.name)}
    assert others == {"trader-panel-publish.service", "trader-engine@.service", "trader-feed.service",
                      "trader-engine-live.service"}      # DD-9: canli birim (-300)


def test_install_uninstall_handle_slice_and_publish_stays_gated():
    t = install_text()
    assert "deploy/trader.slice" in t and "/trader.slice" in t
    assert t.index("trader.slice\"") < t.index("systemctl daemon-reload")
    u = (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
    assert "trader.slice" in u
    # yayin zamanlayicisi Cloudflare anahtarlari dolmadan acilmaz (bellek verisi oncesi kapali kalir)
    assert not re.search(r"^enable_now trader-panel-publish\.timer", t, re.M)
    assert "has_value /etc/trader-panel-cf.env CLOUDFLARE_API_TOKEN" in t
    doc = (DEPLOY.parent / "docs" / "sunucu-kurulum.md").read_text(encoding="utf-8")
    assert "Bellek ölçümü" in doc and "systemd-cgtop" in doc and "MemoryCurrent" in doc and "900 MB" in doc


def test_exit_counterfactual_oneshot_is_bounded_and_fits_slice():
    """Cikis karsi-olgusu (25c): gece isi 23:40 UTC; pandas/numpy ice aktarilir (kacinilmaz) -> 256 MB (soft 192 MB). Alinmayan-sinyal isi (23:10, 128 MB)
    ile cakismaz (kisa omurlu, siradan biter); toplam butceye
    bir 'gece isi' payi olarak girer (ONESHOTS listesinde degil: counterfactual gibi gece isleri sirayla calisir)."""
    m = _mem("trader-exit-counterfactual@.service")
    kv = dict(unit_kv((DEPLOY / "trader-exit-counterfactual@.service").read_text(encoding="utf-8")))
    assert m == 256 and kv["MemoryHigh"] == "192M" and int(kv["MemoryHigh"][:-1]) < m
    assert kv["Slice"] == "trader.slice" and kv["Nice"] == "15" and kv["CPUQuota"] == "30%"
    slice_max = int(dict(unit_kv((DEPLOY / "trader.slice").read_text(encoding="utf-8")))["MemoryMax"][:-1])
    assert m <= slice_max // 2                                                  # slice tavaninin yarisini asmaz
    worst = 1170 + 64 + 96 + 400 + 128 + m                                # en kotu ust uste binme bile RAM + takas icinde
    assert worst < RAM_MB + SWAP_MB
