"""08 §4.6: Faz A kapsam kilidi (modül envanteri)."""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PHASE = "B"
ENGINE = "src/trader_engine"
ALLOWED_MODULES_A = {
    "__init__.py", "__main__.py", "errors.py", "types.py", "numeric.py", "clock.py", "bars.py", "config.py", "fileio.py", "holdout.py",
    "state.py", "order_manager.py", "position_manager.py", "funding.py", "strategy_runner.py", "gates.py", "engine.py", "vol_tahmin.py",
    "reconcile.py", "killswitch.py", "status.py", "backtest.py", "precomputed.py", "metrics.py", "cli.py",
    "marketdata/__init__.py", "marketdata/rest_public.py", "marketdata/store.py", "marketdata/feed.py", "marketdata/sources.py",
    "strategies/__init__.py", "strategies/base.py", "strategies/registry.py", "strategies/price_action_v1.py", "strategies/price_action_v1_4h.py",
    "brokers/__init__.py", "brokers/base.py", "brokers/paper.py", "exchange/__init__.py", "exchange/rules.py"}
# Faz B (11 §2): dört yeni modül izinli (binance_rest B1, pause B6, binance_futures B3, reconcile_live B5).
ALLOWED_MODULES_B = ALLOWED_MODULES_A | {"exchange/binance_rest.py", "pause.py", "brokers/binance_futures.py",
                                         "reconcile_live.py", "stamp.py",     # DD-8: mod/hesap damgasi
                                         "marketdata/oi_collector.py",   # ML-G7: yalniz acik uclar, OI/oran toplayici
                                         "marketdata/veri_piyasa.py",   # 23.11 veri toplama: saatlik piyasa konumlanmasi (yalniz kayit)
                                         "ladder.py",                    # 12 (RK-1): risk kademe calisma zamani sarmalayicisi
                                         "shadow.py", "mtm.py",          # WP-3: golge karar satirlari ve oz varlik isareti (yalniz kayit)
                                         "ml1_gate.py",                  # 25.11 ML1 kagit giris kapisi (paper; cevrimdisi ML1 ozellik/puan islevlerini yeniden kullanir)
                                         "ml1_ogren.py",                 # ML1 aninda ogrenme (yalniz kagit): cozme + uydurma + guvenlik, motor adim sonunda cagirir
                                         "ml1_sanal.py",                 # ML1 golge (sanal) ogrenme: alinmayan adayin kagit kurallariyla simulasyonu (yalniz ogrenici dosyasina yazar)
                                         "olcumler.py",                  # P1-0: olcum kayit defteri (200/300 islem sorulari; yalniz olcer, tek cikti var/learner/olcum/ozet.json)
                                         "stop_tabani.py",               # 27.11 sahip karari: stop tabani (giris kararinda; saf hesap)
                                         "seans_disi.py",                # 23.11 fikir 9 a: seans disi (hafta sonu/tatil/haber) giris kapisi, saf stdlib
                                         "arm_guard.py",                 # DD-12 WP-04: saf kume/seans/tatil yardimcilari
                                         "tur_koruyucu.py", "sembol_izleme.py",   # 1L3A dayaniklilik portu: tur koruyucusu, sembol izleyici
                                         "strategies/lab.py", "strategies/arms/__init__.py",   # DD-12 WP-11: bilesik strateji ve kurulum paketi
                                         "strategies/arms/t1.py", "strategies/arms/r1.py",
                                         "strategies/arms/tf1.py", "strategies/arms/b1.py",   # DD-12 WP-12a: yeni kurulumlar
                                         "strategies/arms/_pa.py",                            # WP-12a: ortak yardimci (kurulum degil)
                                         "strategies/arms/f1.py", "strategies/arms/s1.py",   # DD-12 WP-12b: yeni kurulumlar
                                         "strategies/arms/h2.py",
                                         "strategies/arms/_kutuphane.py", "strategies/arms/mf1.py", "strategies/arms/gf1.py", "strategies/arms/in1.py", "strategies/arms/pa2.py",   # 24.11 kullanici karari: formasyon kutuphanesi
                                         "strategies/arms/_varyant.py", "strategies/arms/t1v.py", "strategies/arms/r1v.py",   # 24.11 kullanici karari: PA varyantlari ayri kimlik
                                         "strategies/arms/tf1v.py", "strategies/arms/b1v.py", "strategies/arms/f1v.py",
                                         "strategies/arms/s1v.py", "strategies/arms/h2v.py"}
PHASE_B_FILES = ["brokers/binance_futures.py", "exchange/binance_rest.py", "marketdata/ws.py", "reconcile_live.py"]
FORBIDDEN_TEXT_B = ["listen" + "Key", "web" + "sockets"]   # Faz B: algo metni serbest, kullanıcı veri akışı ertelendi (11 §2)
FORBIDDEN_TEXT = ["listen" + "Key", "userData" + "Stream", "algo" + "Order", "web" + "sockets"]


def scan_inventory(root: Path, phase: str = PHASE) -> list[str]:
    v = []
    base = Path(root) / ENGINE
    if not base.exists():
        return v
    for d, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                rel = str((Path(d) / f).relative_to(base))
                if rel not in (ALLOWED_MODULES_A if phase == "A" else ALLOWED_MODULES_B):
                    v.append(f"unlisted module {rel}")
                t = (Path(d) / f).read_text(encoding="utf-8")
                words = FORBIDDEN_TEXT if phase == "A" else FORBIDDEN_TEXT_B
                v += [f"{rel}: forbidden text {w}" for w in words if w in t]
    if phase == "A":
        v += [f"phase B file {p}" for p in PHASE_B_FILES if (base / p).exists()]
    return v


def test_real_tree_inventory():
    assert scan_inventory(REPO) == []


def test_phase_constant():
    assert PHASE == "B"


def test_scanner_boundaries(tmp_path):
    b = tmp_path / ENGINE
    (b / "brokers").mkdir(parents=True)
    (b / "types.py").write_text("x = 1\n")
    assert scan_inventory(tmp_path) == []
    (b / "extra.py").write_text("")
    assert scan_inventory(tmp_path) == ["unlisted module extra.py"]
    (b / "extra.py").unlink()
    (b / "brokers" / "binance_futures.py").write_text("")
    r = scan_inventory(tmp_path, phase="A")
    assert any("binance_futures" in x for x in r)
    (b / "brokers" / "binance_futures.py").unlink()
    (b / "types.py").write_text("x = 'listen" + "Key'\n")
    assert scan_inventory(tmp_path)
    assert scan_inventory(tmp_path, phase="B")                       # Faz B'de de listenKey/websockets yasak (11 §2)
    (b / "types.py").write_text("x = '" + "algo" + "Order'\n")
    assert scan_inventory(tmp_path, phase="B") == [] and scan_inventory(tmp_path, phase="A")
