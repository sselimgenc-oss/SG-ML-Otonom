"""Bellek/yuk saglamlik: gercek surec (python -m trader_panel), 200 islemli defter, 8 esli istemci, RSS tavani."""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from panel_support import Env, ROOT, free_port, mkledger

UTC = timezone.utc
RSS_MAX_KB = 60 * 1024
PATHS = ["/api/status", "/api/ledger?bot=learner", "/api/curve?bot=learner", "/api/risk?bot=learner",
         "/api/budget", "/api/health", "/api/system", "/"]


@pytest.mark.skipif(not os.path.exists("/proc/self/status"), reason="/proc yok")
def test_rss_under_load_and_main_entrypoint(tmp_path):
    e = Env(tmp_path, learner=False)
    specs = [(i % 3 != 0, True, datetime(2026, 10, 1, tzinfo=UTC) + timedelta(hours=i)) for i in range(200)]
    mkledger(tmp_path / "var/learner/ledger.sqlite", "learner", specs)
    now = datetime.now(UTC)
    e.write_status("learner", 1)
    st = json.loads((tmp_path / "var/learner/status.json").read_text())
    st["loop_at"] = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    (tmp_path / "var/learner/status.json").write_text(json.dumps(st))
    port = free_port()
    cfg = json.loads(e.cfg_path.read_text())
    cfg["port"] = port
    e.cfg_path.write_text(json.dumps(cfg))
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src")}          # sir/ortam yok
    p = subprocess.Popen([sys.executable, "-m", "trader_panel", "--config", str(e.cfg_path)], env=env, cwd=str(tmp_path),
                         stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("panel baslamadi")
        codes: list = []
        stop = time.monotonic() + 4.0

        def client(k):
            i = k
            while time.monotonic() < stop:
                try:
                    r = urllib.request.urlopen(base + PATHS[i % len(PATHS)], timeout=5)
                    codes.append(r.status)
                    r.read()
                except urllib.error.HTTPError as ex:
                    codes.append(ex.code)
                i += 1
        ts = [threading.Thread(target=client, args=(k,)) for k in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert len(codes) > 50 and set(codes) <= {200, 503}
        j = json.loads(urllib.request.urlopen(base + "/api/curve?bot=learner", timeout=5).read())
        assert j["ok"] and j["total_closed"] == 200
        hwm = [int(ln.split()[1]) for ln in open(f"/proc/{p.pid}/status") if ln.startswith("VmHWM")][0]
        print(f"RSS tepe {hwm / 1024:.1f} MB")
        assert hwm <= RSS_MAX_KB, f"RSS tepe {hwm / 1024:.1f} MB"
    finally:
        p.terminate()
        p.wait(10)
        e.close()
