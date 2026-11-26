"""Salt okunur kanit: dosya sha256/mtime degismez, mode=ro yazma reddi, WAL kipinde (yazar acik / kapali / salt okunur
dizin) salt okunur baglama. Sonuc docs/panel-spec.md §10 notunda."""
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

import pytest

from panel_support import DAY, PARAMS, ROOT, Env, Running, STD_LEARNER, mkledger
from trader_core import panel_data as P

ENDPOINTS = ["/api/status", "/api/ledger?bot=learner", f"/api/ledger?bot=learner&day={DAY}",
             "/api/curve?bot=learner", "/api/risk?bot=learner", "/api/budget",
             "/api/pano?bot=learner", "/api/kapanan?bot=learner&period=7g", "/api/health", "/api/system", "/healthz", "/", "/static/panel.js"]


def snap(root: Path, skip=(".sqlite-shm",)) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.endswith(skip):
            st = p.stat()
            out[str(p.relative_to(root))] = (hashlib.sha256(p.read_bytes()).hexdigest(), st.st_mtime_ns)
    return out


def test_endpoints_do_not_modify_data_files(tmp_path):
    e = Env(tmp_path, keep_open=True)                  # yazar baglantilari acik: ledger -wal dosyalari var
    before = snap(tmp_path)
    assert any(k.endswith("ledger.sqlite-wal") for k in before)
    r = Running(e, cache_s=0)
    for _ in range(3):
        for p in ENDPOINTS:
            assert r.req(p)[0] == 200, p
    r.stop()
    after = snap(tmp_path)
    changed = {k for k in before if before[k] != after.get(k)}
    assert not changed, changed                          # ana DB, -wal, butce, status, config: ayni sha ve mtime
    for p in set(after) - set(before):                                        # yeni dosya yalniz kapali DB'nin SQLite -wal yardimcisi olabilir
        assert p.endswith("-wal"), p
    e.close()


def test_mode_ro_connection_rejects_writes(tmp_path):
    mkledger(tmp_path / "l.sqlite", "learner", STD_LEARNER)
    c = sqlite3.connect("file:" + quote(str(tmp_path / "l.sqlite")) + "?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        c.execute("DELETE FROM sqlite_master")
    with pytest.raises(sqlite3.OperationalError):
        c.execute("CREATE TABLE x(a)")
    c.close()
    led = P.open_ledger_ro(str(tmp_path / "l.sqlite"), "learner")
    with pytest.raises(Exception):
        led.init_params(PARAMS, reason="x")                 # yazma API'si salt okunur defterde reddedilir
    led.close()


# ---------------- WAL kipi ----------------
def test_wal_writer_open_then_closed_same_user(tmp_path):
    w = mkledger(tmp_path / "l.sqlite", "learner", STD_LEARNER, keep_open=True)
    assert (tmp_path / "l.sqlite-wal").exists()
    led = P.open_ledger_ro(str(tmp_path / "l.sqlite"), "learner")        # yazar acikken
    assert len(led.list_closed_trades()) == 5
    led.close()
    w.close()                                                             # temiz kapanis: -wal/-shm silinir
    assert not (tmp_path / "l.sqlite-wal").exists() and not (tmp_path / "l.sqlite-shm").exists()
    sha = hashlib.sha256((tmp_path / "l.sqlite").read_bytes()).hexdigest()   # yazarin son (checkpoint) hali
    led = P.open_ledger_ro(str(tmp_path / "l.sqlite"), "learner")        # yazilabilir dizinde acilir (yan etki: -wal/-shm olusur)
    assert len(led.list_closed_trades()) == 5
    led.close()
    assert hashlib.sha256((tmp_path / "l.sqlite").read_bytes()).hexdigest() == sha   # ana dosya ayni


def _unpriv(script: str, *args):
    if os.getuid() == 0:
        if not shutil.which("setpriv"):
            pytest.skip("root ve setpriv yok")
        pre = ["setpriv", "--reuid=65534", "--regid=65534", "--clear-groups"]
    else:
        pre = []
    cmd = pre + [sys.executable, "-I", "-c", script, *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


PROBE = ("import sys; sys.path.insert(0, sys.argv[1])\n"
         "from trader_core import panel_data as P\n"
         "try:\n"
         "    l = P.open_ledger_ro(sys.argv[2], 'learner'); n = len(l.list_closed_trades()); l.close(); print('OK', n)\n"
         "except P.SectionError as e:\n"
         "    print('ERR', e.code)\n")


@pytest.fixture
def ro_dir():
    d = Path(tempfile.mkdtemp(prefix="panel-wal-"))
    os.chmod(d, 0o755)
    yield d
    os.chmod(d, 0o755)
    shutil.rmtree(d, ignore_errors=True)


def _probe_ok():
    r = _unpriv("print('hi')")
    if r.returncode != 0 or "hi" not in r.stdout:
        pytest.skip("ayrici olmayan kullanici calistirilamiyor")


def _open_as_other(ro_dir):
    r = _unpriv(PROBE, str(ROOT / "src"), str(ro_dir / "l.sqlite"))
    return r.stdout.strip() + r.stderr.strip()[-200:]


def test_wal_readonly_dir_writer_running_opens(ro_dir):
    """Bot calisiyor (-wal/-shm var) + dizin salt okunur + farkli (yazma yetkisiz) kullanici: ACILIR."""
    _probe_ok()
    w = mkledger(ro_dir / "l.sqlite", "learner", STD_LEARNER, keep_open=True)
    for f in ro_dir.iterdir():
        os.chmod(f, 0o644)
    os.chmod(ro_dir, 0o555)
    names = sorted(f.name for f in ro_dir.iterdir())
    assert names == ["l.sqlite", "l.sqlite-shm", "l.sqlite-wal"]
    assert _open_as_other(ro_dir).startswith("OK 5")
    assert sorted(f.name for f in ro_dir.iterdir()) == names                 # hicbir dosya olusmadi/silinmedi
    os.chmod(ro_dir, 0o755)
    w.close()


def test_wal_readonly_dir_writer_stopped_fails_closed(ro_dir):
    """Bot durmus (-wal/-shm yok) + dizin salt okunur: mode=ro ACILAMAZ -> panel 'wal_yok_salt_okunur' (veri yok), cokmez."""
    _probe_ok()
    mkledger(ro_dir / "l.sqlite", "learner", STD_LEARNER)
    os.chmod(ro_dir / "l.sqlite", 0o644)
    assert sorted(f.name for f in ro_dir.iterdir()) == ["l.sqlite"]
    os.chmod(ro_dir, 0o555)
    assert _open_as_other(ro_dir).startswith("ERR wal_yok_salt_okunur")
    assert sorted(f.name for f in ro_dir.iterdir()) == ["l.sqlite"]
