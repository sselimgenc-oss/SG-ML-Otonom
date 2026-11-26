"""Telegram outbox sahiplik modeli: root'un yazdigi dosya/dizin dizinin sahibine cevrilir; yabanci dosya servisi dusurmez."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trader_core import telegram as tg  # noqa: E402

T0 = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
ITEM = {"text": "x", "severity": "WARN", "dedup_key": "k1", "expires_at": None, "reply_markup": None, "created_at": 0}


def _mock_sahip(monkeypatch, ref=(1001, 2002), dosya=(0, 0)):
    """outbox dizini (ref) trader:trader-tg; olusturulan her sey root (dosya) gibi gorunur. chown cagrilari kaydedilir."""
    calls, modes = [], []
    gercek_stat, gercek_lstat = os.stat, os.lstat

    def fake_stat(p, *a, **k):
        r = gercek_stat(p, *a, **k)
        if Path(p).name != "outbox":
            return r

        class _S:
            st_uid, st_gid = ref

            def __getattr__(self, ad):
                return getattr(r, ad)
        return _S()

    def fake_lstat(p, *a, **k):
        r = gercek_lstat(p, *a, **k)

        class _S:                           # uid/gid sahte, gerisi gercek
            st_uid, st_gid = dosya

            def __getattr__(self, ad):
                return getattr(r, ad)
        return _S()

    monkeypatch.setattr(os, "stat", fake_stat)
    monkeypatch.setattr(os, "lstat", fake_lstat)
    monkeypatch.setattr(os, "chown", lambda p, u, g: calls.append((Path(p).name, u, g)))
    real_chmod = os.chmod
    monkeypatch.setattr(os, "chmod", lambda p, m: (modes.append((Path(p).name, m)), real_chmod(p, m))[1])
    return calls, modes


def test_root_sent_dizini_ve_isaret_dizin_sahibine_cevrilir(tmp_path, monkeypatch):
    ob = tg.Outbox(tmp_path, lambda: T0)
    ob.dir.mkdir(parents=True)
    calls, modes = _mock_sahip(monkeypatch)
    ob.mark_sent("k1")
    assert ("sent", 1001, 2002) in calls
    assert any(c[0] == tg._key_hash("k1") and c[1:] == (1001, 2002) for c in calls)
    assert ("sent", 0o2770) in modes


def test_root_kuyruk_dosyasi_dizin_sahibine_cevrilir(tmp_path, monkeypatch):
    ob = tg.Outbox(tmp_path, lambda: T0)
    ob.dir.mkdir(parents=True)
    calls, _ = _mock_sahip(monkeypatch)
    assert ob.enqueue(dict(ITEM)) is True
    assert any(n.endswith(f"{tg._key_hash('k1')}.json") and (u, g) == (1001, 2002) for n, u, g in calls)


def test_sahip_zaten_dogruysa_chown_yok(tmp_path, monkeypatch):
    ob = tg.Outbox(tmp_path, lambda: T0)
    ob.dir.mkdir(parents=True)
    calls, _ = _mock_sahip(monkeypatch, dosya=(1001, 2002))
    ob.mark_sent("k1")
    assert calls == []


def test_chown_yetkisiz_olsa_da_yazma_basarili(tmp_path, monkeypatch):
    ob = tg.Outbox(tmp_path, lambda: T0)
    ob.dir.mkdir(parents=True)
    _mock_sahip(monkeypatch)

    def red(*a, **k):
        raise PermissionError(1, "izin yok")
    monkeypatch.setattr(os, "chown", red)
    assert ob.enqueue(dict(ITEM)) is True
    assert len(ob.list()) == 1


def test_yabanci_dosya_silinemezse_drain_dusmez(tmp_path, monkeypatch):
    ob = tg.Outbox(tmp_path, lambda: T0)
    assert ob.enqueue(dict(ITEM)) is True
    ob.mark_sent("k1")                      # sent_recently -> drain dosyayi silmeye calisir

    def red(self, missing_ok=False):
        raise PermissionError(13, "izin yok")
    monkeypatch.setattr(Path, "unlink", red)
    client = SimpleNamespace(send_message=lambda *a, **k: (_ for _ in ()).throw(AssertionError("gonderilmemeli")))
    assert ob.drain(client, 1, lambda s: None) == 0


def test_mutabakat_isaret_okunamazsa_yok_sayar(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    import mutabakat_run as MR
    (tmp_path / "outbox" / "sent").mkdir(parents=True)
    orig = Path.exists

    def red(self, *a, **k):
        if self.parent.name == "sent":
            raise PermissionError(13, "izin yok")
        return orig(self, *a, **k)
    monkeypatch.setattr(Path, "exists", red)
    var = MR.isaret_fonksiyonu(tmp_path, [])
    assert var(1, "kapandi") is False


def test_install_sh_sent_dizinini_ve_sahipligi_her_kurulumda_onarir():
    s = (ROOT / "deploy" / "install.sh").read_text(encoding="utf-8")
    assert 'install -d -m 2770 -o "$TRADER_USER" -g "$TG_GROUP" "$TRADER_DIR/var/telegram/outbox/sent"' in s
    assert 'find "$TRADER_DIR/var/telegram/outbox" -mindepth 1 -xdev -exec chown -h "$TRADER_USER:$TG_GROUP" {} +' in s


def test_kalici_hata_ogeyi_rejected_e_tasir_ve_siradakine_gecer(tmp_path):
    ob = tg.Outbox(tmp_path, lambda: T0)
    kotu = dict(ITEM, dedup_key="kotu", text="bozuk")
    iyi = dict(ITEM, dedup_key="iyi", text="iyi")
    assert ob.enqueue(kotu) and ob.enqueue(iyi)
    gonderilen = []

    def send(chat, text, **k):
        if text == "bozuk":
            raise tg.TelegramError("permanent", 400, desc="bad request")
        gonderilen.append(text)
    assert ob.drain(SimpleNamespace(send_message=send), 1, lambda s: None) == 1
    assert gonderilen == ["iyi"]
    assert ob.list() == []                                      # kuyruk basi tikanmadi
    assert len(list((ob.dir / "rejected").glob("*.json"))) == 1  # kotu oge saklandi
    assert ob.drain(SimpleNamespace(send_message=send), 1, lambda s: None) == 0
