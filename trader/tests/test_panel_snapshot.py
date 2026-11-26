"""Anlik goruntu (docs/panel-spec.md §13): kendi kendine yeten, damgali, sirsiz, agsiz."""
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys

import pytest

from panel_support import NOW, ROOT, Env
from trader_panel import snapshot as SN
from trader_panel.data import PanelData, load_config


@pytest.fixture(scope="module")
def html(tmp_path_factory):
    e = Env(tmp_path_factory.mktemp("snap"))
    out = SN.render(PanelData(load_config(e.cfg_path), clock=lambda: NOW))
    e.close()
    return out


def test_self_contained_no_external_urls(html):
    assert "<style>" in html and "window.__SNAPSHOT__=" in html
    assert "/static/" not in html and "<link" not in html.lower()
    assert not re.search(r"<script[^>]+src=", html, re.I)
    assert not re.search(r"https?://|//cdn|@import|url\(\s*[\"']?(?!data:)", html, re.I)


def test_stamp_present_and_tsi(html):
    assert "Oluşturulma: 2026-11-16 21:00:00 TSİ" in html
    m = re.search(r'window\.__SNAPSHOT__=(\{.*?\});</script>', html, re.S)
    snap = json.loads(m.group(1))
    assert snap["generated_at"] == "2026-11-16T18:00:00.000Z"
    # yalniz panel.js'in okudugu uclar gomulur (9b-01): /api/pano ve /api/kapanan (donem basina)
    for b in ("learner",):
        assert f"/api/pano?bot={b}" in snap["data"]
        for d in ("bugun", "7g", "30g", "tumu"):
            assert f"/api/kapanan?bot={b}&period={d}" in snap["data"]
    for k in snap["data"]:
        assert k.startswith(("/api/pano?", "/api/kapanan?")), k


def test_panel_js_yalniz_gomulen_uclari_okur():
    js = (Path(__file__).resolve().parents[1] / "src" / "trader_panel" / "static" / "panel.js").read_text(encoding="utf-8")
    assert set(re.findall(r"/api/([a-z0-9_]+)", js)) == {"kapanan", "pano"}


def test_client_side_stale_banner_logic(html):
    assert 'id="snap-bant"' in html
    assert "SNAP_STALE_S = 600" in html and "Date.now() - Date.parse(SNAP.generated_at)" in html
    assert "BAYAT GÖRÜNÜM" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_stale_banner_executes(html, tmp_path):
    js = re.search(r"<script>\n(/\* panel\.js.*?)\n</script>", html, re.S)
    assert js
    for age_s, expect in ((120, False), (900, True)):
        code = f"""
const els = {{}}; const mk = () => ({{style: {{}}, textContent: '', classList: {{toggle(){{}}, add(){{}}, remove(){{}}}}, addEventListener(){{}},
  setAttribute(){{}}, getAttribute(){{return null}}, appendChild(){{}}, children: [], firstChild: null}});
global.document = {{getElementById: (i) => els[i] || (els[i] = mk()), createElement: mk, createTextNode: () => mk(),
  querySelectorAll: () => [], documentElement: mk(), addEventListener(){{}}, hidden: true}};
global.window = {{__SNAPSHOT__: {{generated_at: new Date(Date.now() - {age_s}*1000).toISOString(), data: {{}}}}}};
global.localStorage = {{getItem(){{return null}}, setItem(){{}}}};
global.location = {{reload(){{}}}};
global.setInterval = () => 0;
try {{ {js.group(1)} }} catch (e) {{ console.log('ERR ' + e.message); }}
console.log(els['snap-bant'].style.display === '' ? 'shown' : 'hidden');
"""
        f = tmp_path / "t.js"
        f.write_text(code, encoding="utf-8")
        r = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=20)
        assert ("shown" if expect else "hidden") in r.stdout.splitlines()[-1], (r.stdout, r.stderr)


def test_no_secrets_in_output(html, monkeypatch):
    sentinels = {"ANTHROPIC_API_KEY_LESSON": "sk-ant-SENTINEL123456", "TELEGRAM_BOT_TOKEN": "123456789:SENTINELtokenSENTINELtokenSENTINEL",
                 "CLOUDFLARE_API_TOKEN": "cfSENTINELtoken99", "TRADER_VETO_HMAC_KEY": "hmacSENTINELkey77", "PANEL_SIFRE": "pwSENTINEL"}
    for k, v in sentinels.items():
        monkeypatch.setenv(k, v)
    # ayni cikti yeniden uretilir: ortam degerleri sizmamali
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        e = Env(Path(d))
        out = SN.render(PanelData(load_config(e.cfg_path), clock=lambda: NOW))
        e.close()
    for v in sentinels.values():
        assert v not in out and v not in html
    for pat in (r"sk-ant-[A-Za-z0-9_-]{8,}", r"\b\d{8,10}:[A-Za-z0-9_-]{30,}", r"ghp_|github_pat_", "PRIVATE KEY",
                r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[\"']?[A-Za-z0-9]{12,}"):
        assert not re.search(pat, out), pat


def test_cli_snapshot_writes_file(tmp_path):
    e = Env(tmp_path / "d")
    out = tmp_path / "o" / "index.html"
    out.parent.mkdir()
    r = subprocess.run([sys.executable, "-m", "trader_panel", "--config", str(e.cfg_path), "snapshot", "--out", str(out)],
                       capture_output=True, text=True, cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"})
    e.close()
    assert r.returncode == 0, r.stderr
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert [p.name for p in out.parent.iterdir()] == ["index.html"]
