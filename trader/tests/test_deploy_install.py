"""Sunucu kurulum paketi icin statik denetimler (ag yok, systemd yok)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"
SCRIPTS = [DEPLOY / "install.sh", DEPLOY / "uninstall.sh", DEPLOY / "oto_guncelle.sh",
           DEPLOY / "trader-geri-al", DEPLOY / "trader-oto-ac", DEPLOY / "trader-oto-simdi"]
UNITS = sorted(p for p in DEPLOY.iterdir() if p.suffix in (".service", ".timer"))


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_bash_syntax(path):
    assert subprocess.run(["bash", "-n", str(path)], capture_output=True).returncode == 0


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck yok")
@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_shellcheck(path):
    r = subprocess.run(["shellcheck", "-S", "warning", str(path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_no_secrets(path):
    t = path.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{8,}", t)
    assert not re.search(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}", t)  # telegram token
    assert "PRIVATE KEY" not in t
    assert "ghp_" not in t and "github_pat_" not in t
    assert not re.search(r"^\s*(set -x|.*\bxtrace\b)", t, re.M)


def test_strict_mode_and_root_check():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in t
    assert "id -u" in t


def test_no_firewall_or_public_bind():
    t = "\n".join(p.read_text(encoding="utf-8") for p in SCRIPTS)
    assert not re.search(r"\bufw\b|iptables|nft |0\.0\.0\.0", t)


def test_engine_unit():
    t = (DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")
    assert re.search(r"^MemoryMax=\d+M", t, re.M)
    assert re.search(r"^Nice=\d+", t, re.M)
    assert "Restart=on-failure" in t
    assert "-m trader_engine run --bot %i --env paper" in t and "init-ledger --bot %i --env paper" in t   # DD-12
    assert re.search(r"^MemoryHigh=600M$", t, re.M) and re.search(r"^MemoryMax=750M$", t, re.M)         # DD-12 §8
    assert (ROOT / "src/trader_engine/__main__.py").exists()
    assert (ROOT / "config/engine.learner.json").exists() and (ROOT / "config/engine.paper.json").exists()
    assert not (ROOT / "config/engine.twin.json").exists()                                              # DD-12: ikiz kaldirildi
    assert (ROOT / "config/engine.base.json").exists()


def test_feed_unit_and_engine_ordering():
    f = (DEPLOY / "trader-feed.service").read_text(encoding="utf-8")
    assert "-m trader_engine feed --config-dir config" in f
    assert "User=trader" in f and "Restart=always" in f
    assert re.search(r"^OnFailure=trader-health-fail@%n\.service", f, re.M)
    assert re.search(r"^MemoryMax=260M$", f, re.M) and re.search(r"^MemoryHigh=200M$", f, re.M) and re.search(r"^Nice=\d+", f, re.M)
    assert re.search(r"^ReadWritePaths=.*/opt/trader/var", f, re.M)
    e = (DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")
    for key in ("ProtectSystem=strict", "NoNewPrivileges=true", "PrivateTmp=true", "ProtectHome=read-only"):
        assert key in f and key in e, key
    assert re.search(r"^After=.*trader-feed\.service", e, re.M) and re.search(r"^Wants=.*trader-feed\.service", e, re.M)


def test_install_enables_feed_before_engine_and_uninstall_covers_it():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert t.index("enable_now trader-feed.service") < t.index("enable_now trader-engine@learner.service")
    u = (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
    assert "trader-feed.service" in u and "trader-*.service" in u


def _exec_lines():
    for u in UNITS:
        if u.suffix != ".service":
            continue
        for ln in u.read_text(encoding="utf-8").splitlines():
            m = re.match(r"(ExecStart|ExecStartPre)=-?(.*)", ln)
            if m:
                yield u.name, m.group(2)


def test_every_unit_exec_target_resolves():
    """`python3 -m X <altkomut>` modulu/alt komutu ve betik yollari gercekten var (feed alt komutu dahil)."""
    import importlib.util
    if True:
        from trader_engine import cli
        subcmds = set(cli.build_parser()._subparsers._group_actions[0].choices)
        seen_mod = 0
        for name, cmd in _exec_lines():
            toks = cmd.split()
            if "-m" in toks:
                i = toks.index("-m")
                mod = toks[i + 1]
                assert importlib.util.find_spec(mod) is not None, f"{name}: modul yok: {mod}"
                seen_mod += 1
                if mod == "trader_engine":
                    assert toks[i + 2] in subcmds, f"{name}: trader_engine alt komutu yok: {toks[i + 2]}"
                    if toks[i + 2] in ("feed", "rules-snapshot"):
                        from trader_engine.marketdata import feed as F
                        assert callable(getattr(F, "main" if toks[i + 2] == "feed" else "rules_snapshot_main"))
            for t in toks:
                m = re.match(r"/opt/trader/((?:scripts|config|src|docs)/[\w./-]+)", t)
                if m:
                    assert (ROOT / m.group(1)).exists(), f"{name}: {m.group(1)}"
        assert seen_mod >= 4


def test_units_reference_existing_paths():
    for u in UNITS:
        for m in re.finditer(r"/opt/trader/((?:scripts|config|src|docs)/[\w./-]+)", u.read_text(encoding="utf-8")):
            assert (ROOT / m.group(1)).exists(), f"{u.name}: {m.group(1)}"


def test_every_unit_handled_by_install():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    # glob ile hepsi kurulur
    assert 'deploy/trader-*.service' in t and 'deploy/trader-*.timer' in t
    assert all(u.name.startswith("trader-") for u in UNITS)
    # etkinlestirme politikasi: her zamanlayici ve servis ya acikca etkinlestirilir ya da bilincli olarak etkinlestirilmez
    enabled = set(re.findall(r"enable_now (trader-[\w@.-]+)", t))
    deliberately_not = {"trader-health-fail@.service", "trader-health.service", "trader-backup.service",
                        "trader-telegram-report.service", "trader-engine@.service",
                        "trader-panel-publish.service", "trader-engine-retry@.service", "trader-counterfactual@.service", "trader-exit-counterfactual@.service",
                        "trader-oi.service", "trader-haber.service", "trader-piyasa-veri.service", "trader-drift@.service", "trader-weekly-summary.service", "trader-universe.service",
                        "trader-tutarlilik.service",  # Faz 2a: haftalik tutarlilik raporu (zamanlayici etkinlestirilir; servis tetiklenir)
                        "trader-tur1-olcum.service",  # tur 1 olcum raporu: gunluk zamanlayici etkinlestirilir; servis tetiklenir
                        "trader-weekly-collect.service",  # haftalik YZ batch sonuclarini toplama: zamanlayici etkinlestirilir; servis tetiklenir
                        "trader-tur1-haftalik.service",  # tur 1 haftalik YZ yorumu: haftalik zamanlayici etkinlestirilir; servis tetiklenir
                        "trader-yorumcu.service",  # ust lig YZ yorumcu: gunluk zamanlayici etkinlestirilir; servis tetiklenir
                        "trader-mutabakat.service",  # islem mutabakati: gunluk zamanlayici etkinlestirilir; servis ayrica kurulum sonrasi tetiklenir
                        "trader-strateji-veri.service",  # strateji verisi: kurulum sonrasi tek seferlik sessiz Telegram belgesi (zamanlayici 6 saatte bir dosyayi yeniler; install.sh servisi ayrica kurulum sonrasi tetikler)
                        "trader-durum-yayin.service",  # canli durum yayini: saatlik zamanlayici etkinlestirilir; servis tetiklenir
                        "trader-bakim.service",  # haftalik disk bakimi (zamanlayici etkinlestirilir; servis tetiklenir)
                        "trader-engine-live.service", "trader-engine-env-retry@.service",
                        "trader-oto-guncelle.service", "trader-kurulum-gozcu.service"}  # tetikleyici/sablon birimler (DD-9: canli birim yalniz --live ile, enable_now ile degil; oto-guncelle servisi zamanlayicidan tetiklenir)
    for u in UNITS:
        if u.name == "trader-engine@.service":
            assert "trader-engine@learner.service" in enabled and "trader-engine@twin.service" not in enabled
        elif u.name in deliberately_not:
            continue
        elif u.name == "trader-engine-retry@.timer":
            assert "trader-engine-retry@learner.timer" in enabled and "trader-engine-retry@twin.timer" not in enabled
        elif u.name == "trader-engine-env-retry@.timer":      # DD-9: testnet ornegi etkin; live ornegi yalniz --live (systemctl enable --now)
            assert "enable_now trader-engine-env-retry@testnet.timer" in t and "enable --now trader-engine-env-retry@live.timer" in t
        elif u.name == "trader-drift@.timer":
            assert "trader-drift@learner.timer" in enabled and "trader-drift@twin.timer" not in enabled
        elif u.name == "trader-counterfactual@.timer":
            assert "trader-counterfactual@learner.timer" in enabled and "trader-counterfactual@twin.timer" not in enabled
        elif u.name == "trader-exit-counterfactual@.timer":
            assert "trader-exit-counterfactual@learner.timer" in enabled and "trader-exit-counterfactual@twin.timer" not in enabled
        else:
            assert u.name in enabled, u.name


def test_env_examples_installed():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    for p in DEPLOY.glob("*.env.example"):
        assert p.name in t, p.name
    assert "[ -e \"$dst\" ]" in t  # var olan ezilmez


def test_placeholder_gated_timers():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        assert re.search(rf"has_value \S+ {key}", t), key
    # DD-12 WP-06a: veto zamanlayicisi artik anahtara bagli degil (kagitta veto yok): has_value ile etkinlestirilmez
    assert "ANTHROPIC_API_KEY_VETO" not in t and "enable_now trader-veto" not in t
    # 25.11: ders servisi kaldirildi: ANTHROPIC_API_KEY_LESSON artik hicbir yerde istenmez / etkinlestirme kosulu degil
    assert "ANTHROPIC_API_KEY_LESSON" not in t and "enable_now trader-lesson" not in t and "enable_now trader-notes" not in t


def test_ders_ve_not_birimleri_emekli_dongusunde_idempotent():
    """25.11 sahip karari: trader-lesson.* ve trader-notes.* birim dosyalari depoda yok; install.sh mevcut emekli birim dongusunde
    (varlik kontrollu disable --now + dosya silme) eski kopyalari temizler."""
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    for u in ("trader-lesson.timer", "trader-lesson.service", "trader-notes.timer", "trader-notes.service"):
        assert not (DEPLOY / u).exists(), u
    m = re.search(r"for u in (trader-veto\.timer.*?); do\n(.*?)\n  rm -f \"\$\{UNIT_DIR\}/\$u\"\ndone", t, re.S)
    assert m, "emekli birim dongusu bulunamadi"
    for u in ("trader-lesson.timer", "trader-lesson.service", "trader-notes.timer", "trader-notes.service"):
        assert u in m.group(1), u
    assert 'systemctl disable --now "$u" >/dev/null 2>&1 || true' in m.group(2)
    assert not re.search(r"^ANTHROPIC_API_KEY_LESSON=", (DEPLOY / "trader-lesson.env.example").read_text(encoding="utf-8"), re.M)


def test_veto_units_removed_and_disabled_on_install():
    """24.11 kullanici karari: AI veto artiklari silindi; dagitimda birim/env ornegi yok; install.sh eski kurulumdaki birimleri ve
    /etc dosyalarini varlik kontrolu ile (idempotent) temizler; HMAC anahtari artik uretilmez."""
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert not (DEPLOY / "trader-veto.service").exists() and not (DEPLOY / "trader-veto.timer").exists()
    assert not (DEPLOY / "trader-veto.env.example").exists() and not (DEPLOY / "trader-veto-hmac.env.example").exists()
    assert "for u in trader-veto.timer trader-veto.service" in t and "disable --now" in t
    assert "for f in /etc/trader-veto.env /etc/trader-veto-hmac.env; do" in t and 'if [ -e "$f" ] || [ -L "$f" ]' in t
    assert "openssl rand" not in t and "TRADER_VETO_HMAC_KEY" not in t and 'copy_env "$REL_DIR/deploy/trader-veto' not in t
    assert "shared/veto" not in t.split("# ---- 6. dizinler", 1)[1].split("# ---- 7.", 1)[0]


def test_twin_removed_options_gone_and_archived():
    """DD-12 WP-07: ikiz birimleri durdurulur/devre disi, --with-twin/--no-twin kalkti, var/twin arsive tasinir (silinmez)."""
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "WITH_TWIN" not in t and "--no-twin" not in t and "--with-twin" not in t
    assert 'HEALTH_BOTS_VAL="learner"' in t and "learner,twin" not in t
    assert re.search(r"systemctl disable --now \"\$u\"", t) and "trader-engine@twin.service" in t
    assert "var/arsiv/twin-" in t and 'mv "$TRADER_DIR/var/twin"' in t
    assert re.search(r"^HEALTH_BOTS=learner$", (DEPLOY / "trader-health.env.example").read_text(encoding="utf-8"), re.M)


def test_install_sets_pause_bots_for_telegram():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "PAUSE_BOTS=${HEALTH_BOTS_VAL}" in t
    env = (DEPLOY / "trader-telegram.env.example").read_text(encoding="utf-8")
    for k in ("PAUSE_FILE=", "ENGINE_VAR_DIR=", "PAUSE_BOTS="):
        assert re.search(rf"^{k}", env, re.M)
    assert "WorkingDirectory=/opt/trader" in (DEPLOY / "trader-telegram.service").read_text(encoding="utf-8")


def test_uninstall_only_trader_units():
    t = (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
    rms = re.findall(r"rm -[a-z]*f?\s+(.+)", t)
    assert "--purge" in t
    assert 'trader-*.service' in t and 'trader-*.timer' in t
    for line in t.splitlines():
        if re.search(r"systemctl (disable|stop)", line):
            assert '"$u"' in line  # yalniz trader-* ile suzulmus liste
    assert 'case "$u" in trader-*)' in t
    # silinen yollar yalniz bize ait
    for r in rms:
        for tok in r.split():
            tok = tok.strip('"')
            if tok.startswith("-"):
                continue
            assert any(k in tok for k in ("trader", "$f", "REPO_DIR")), tok
    assert "/swapfile" not in re.sub(r"echo .*", "", t)


def test_python_version_guard_and_runtime_deps():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "(3, 11)" in t
    assert "freqtrade" not in re.sub(r"#.*", "", t) and "pytest" not in re.sub(r"#.*", "", t)
    for dep in ("requests", "pandas", "numpy", "pyarrow", "anthropic"):
        assert dep in t


def test_install_does_not_install_frameworks():
    t = (Path(__file__).resolve().parents[1] / "deploy" / "install.sh").read_text()
    code = re.sub(r"#.*", "", t)
    for banned in ("ccxt", "freqtrade", "python-binance"):
        assert banned not in code


def test_panel_unit():
    t = (DEPLOY / "trader-panel.service").read_text(encoding="utf-8")
    assert re.search(r"^MemoryMax=64M$", t, re.M) and re.search(r"^Nice=10$", t, re.M)
    assert "EnvironmentFile" not in re.sub(r"#.*", "", t)          # anahtar/token gorulmez
    assert "-m trader_panel --config /opt/trader/config/panel.json" in t
    assert re.search(r"^ReadOnlyPaths=.*/opt/trader/var", t, re.M)
    assert re.search(r"^IPAddressAllow=localhost$", t, re.M) and re.search(r"^IPAddressDeny=any$", t, re.M)
    assert (ROOT / "src/trader_panel/__main__.py").exists() and (ROOT / "config/panel.json").exists()


def test_panel_installed_enabled_and_removed():
    i = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert re.search(r"^enable_now trader-panel\.service", i, re.M)       # etkin + baslatilir
    u = (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
    assert "trader-*.service" in u and 'case "$u" in trader-*)' in u      # glob trader-panel.service'i de kaldirir


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze yok")
def test_panel_unit_systemd_verify():
    r = subprocess.run(["systemd-analyze", "verify", "--man=no", str(DEPLOY / "trader-panel.service")],
                       capture_output=True, text=True)
    bad = [ln for ln in (r.stdout + r.stderr).splitlines()
           if "trader-panel" in ln and not re.search(r"Failed to (create|connect)|not found|Executable|User|Group", ln)]
    assert not bad, bad


# ---- panel yayini (Cloudflare Worker, spec §13) ----
def test_publish_script_static():
    p = DEPLOY / "panel_yayinla.sh"
    assert subprocess.run(["bash", "-n", str(p)], capture_output=True).returncode == 0
    t = p.read_text(encoding="utf-8")
    code = re.sub(r"^\s*#.*$", "", t, flags=re.M)
    assert "set -euo pipefail" in t
    assert "set -x" not in t and "xtrace" not in t
    for line in code.splitlines():
        if re.search(r"\b(echo|printf|cat)\b", line):
            assert "CLOUDFLARE_API_TOKEN" not in line and "CLOUDFLARE_ACCOUNT_ID" not in line, line
    assert "trader-pano" in t and "TRADER_PANEL_WORKER" in t
    assert "snapshot --out" in t and "wrangler" in t and " deploy " in t
    assert "exit 1" in t and "/etc/trader-panel-cf.env" in t
    assert "PANO_KILITSIZ" not in t


def test_publish_units_and_env_example():
    s = (DEPLOY / "trader-panel-publish.service").read_text(encoding="utf-8")
    assert "Type=oneshot" in s and re.search(r"^MemoryMax=\d+M", s, re.M) and re.search(r"^Nice=\d+", s, re.M)
    assert "EnvironmentFile=/etc/trader-panel-cf.env" in s
    tm = (DEPLOY / "trader-panel-publish.timer").read_text(encoding="utf-8")
    assert "OnUnitActiveSec=5min" in tm and "Persistent=true" in tm
    ex = (DEPLOY / "trader-panel-cf.env.example").read_text(encoding="utf-8")
    for line in ex.splitlines():
        if line and not line.startswith("#"):
            k, _, v = line.partition("=")
            assert v == "", line   # yalniz yer tutucu


def test_publish_timer_gated_and_wrangler_pinned():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert re.search(r"has_value /etc/trader-panel-cf\.env CLOUDFLARE_API_TOKEN", t)
    assert re.search(r"has_value /etc/trader-panel-cf\.env CLOUDFLARE_ACCOUNT_ID", t)
    assert "enable_now trader-panel-publish.timer" in t
    assert "PANEL_SIFRE" not in t and "Protect this Worker behind Access" not in t   # 20 Kasim: pano kilitsiz (parola/Access yok)
    assert re.search(r'^WRANGLER_VERSION="\d+\.\d+\.\d+"', t, re.M)
    code = re.sub(r"#.*", "", t)
    assert "npm install -g" not in code and "npm i -g" not in code
    assert not re.search(r"curl[^\n|]*\|\s*(ba)?sh", code)
    assert "command -v node" in t
    assert "trader-panel-cf.env.example" in t


def test_worker_js_static():
    t = (DEPLOY / "panel_worker.js").read_text(encoding="utf-8")
    # 20 Kasim kullanici karari: pano kilitsiz (parola yok, Cloudflare Access JWT dogrulamasi kaldirildi); yalniz okuma (GET/HEAD)
    assert "PANEL_SIFRE" not in t and "WWW-Authenticate" not in t
    assert "Cf-Access-Jwt-Assertion" not in t and "crypto.subtle.verify" not in t
    assert "if (!saltOkuma(istek)) return red();" in t
    assert re.search(r'"Cache-Control", "no-store"', t)
    for h in ("X-Content-Type-Options", "Referrer-Policy", "Content-Security-Policy"):
        assert h in t
    # yalniz orkestra kapisi cerceveleyebilir (X-Frame-Options yerine CSP frame-ancestors)
    assert "frame-ancestors 'self' https://orkestra-kapi.sselimgenc-c18.workers.dev" in t
    assert "frame-ancestors 'none'" not in t and 'h.set("X-Frame-Options"' not in t
    assert "pano_worker.js" in t       # kaynak notu
    n = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "pano_worker.js" in n


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_worker_js_acik_yalniz_okuma(tmp_path):
    """Pano kilitsiz: GET/HEAD icerigi doner, yazma yontemleri 405; dis istek (sertifika vb.) yapilmaz."""
    js = tmp_path / "t.mjs"
    js.write_text(f"""import w from {str(DEPLOY / 'panel_worker.js')!r};
globalThis.fetch = async () => {{ throw new Error('dis istek yapilmamali'); }};
const env0 = {{ASSETS: {{fetch: async () => new Response('ok')}}}};
const rq = (m) => new Request('https://x/', {{method: m || 'GET'}});
for (const m of ['GET', 'HEAD']) {{ const r = await w.fetch(rq(m), env0); if (r.status !== 200) throw new Error(m + ' ' + r.status); }}
for (const m of ['POST', 'PUT', 'DELETE']) {{ const r = await w.fetch(rq(m), env0); if (r.status !== 405) throw new Error(m + ' acik'); }}
""", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type":"module"}')
    r = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_engine_retry_units_and_install():
    s = (DEPLOY / "trader-engine-retry@.service").read_text(encoding="utf-8")
    tm = (DEPLOY / "trader-engine-retry@.timer").read_text(encoding="utf-8")
    e = (DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")
    assert "RestartPreventExitStatus=7" in e                      # kapi hatasi hala 'failed' olur
    assert "Type=oneshot" in s and "User=root" in s and "engine_retry.py --bot %i" in s
    assert "OnUnitActiveSec=5min" in tm and "WantedBy=timers.target" in tm
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "enable_now trader-engine-retry@learner.timer" in t
    assert "enable_now trader-engine-retry@twin" not in t
    u = (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
    assert "trader-*.timer" in u                                   # sablon zamanlayici da kaldirilir


def test_trader_slice_installed_and_removed():
    i = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    u = (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
    assert (DEPLOY / "trader.slice").exists()
    assert 'render "$REL_DIR/deploy/trader.slice" "${UNIT_DIR}/trader.slice"' in i      # DD-9: sablonlar root sahipli surum dizininden
    assert i.index("trader.slice\"") < i.index("systemctl daemon-reload")
    assert 'rm -f "$UNIT_DIR/trader.slice"' in u
    assert "Slice=trader.slice" in i          # trader-fetch (systemd-run) de ayni slice'ta


def test_counterfactual_units_and_install():
    """Alinmayan sinyal gece isi (25a): sablon birim, 23:10 UTC (02:10 TSI), defter/market salt okunur, yalniz var/<bot> yazilabilir."""
    s = (DEPLOY / "trader-counterfactual@.service").read_text(encoding="utf-8")
    tm = (DEPLOY / "trader-counterfactual@.timer").read_text(encoding="utf-8")
    assert "Type=oneshot" in s and "Slice=trader.slice" in s and "User=trader" in s
    assert "counterfactual_run.py --bot %i --once" in s and "OnFailure=trader-health-fail@%n.service" in s
    assert re.search(r"^MemoryMax=128M$", s, re.M) and re.search(r"^Nice=\d+", s, re.M) and "NoNewPrivileges=true" in s
    assert "ProtectSystem=strict" in s and "ProtectHome=read-only" in s and "PrivateTmp=true" in s
    assert "EnvironmentFile" not in re.sub(r"#.*", "", s)                      # anahtar/token yok: ag ve API kullanmaz
    rw = re.search(r"^ReadWritePaths=(.*)$", s, re.M).group(1).split()
    assert rw == ["-/opt/trader/var/%i", "-/opt/trader/var/durum"]             # kendi bot dizini + alinmayan_sonuc_v1.json (var/durum)
    ro = re.search(r"^ReadOnlyPaths=(.*)$", s, re.M).group(1).split()
    assert "-/opt/trader/var/%i/ledger.sqlite" in ro and "-/opt/trader/var/market.sqlite" in ro
    assert "OnCalendar=*-*-* 23:10:00 UTC" in tm and "Persistent=true" in tm
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "enable_now trader-counterfactual@learner.timer" in t
    assert "enable_now trader-counterfactual@twin" not in t
    assert (ROOT / "scripts/counterfactual_run.py").exists() and (ROOT / "docs/alinmayan-sinyal-spec.md").exists()


def test_exit_counterfactual_units_and_install():
    """Cikis karsi-olgusu gece isi (25c; docs/cikis-karsi-olgu-spec.md 8): 23:40 UTC, alinmayan-sinyal 23:10'dan sonra, ders servisinden once;
    MemoryMax=256M (pandas ~70 MB), defter/market salt okunur, backtest yolu yok, ag/anahtar yok."""
    s = (DEPLOY / "trader-exit-counterfactual@.service").read_text(encoding="utf-8")
    tm = (DEPLOY / "trader-exit-counterfactual@.timer").read_text(encoding="utf-8")
    code = re.sub(r"#.*", "", s)
    assert "Type=oneshot" in s and "Slice=trader.slice" in s and "User=trader" in s
    assert "exit_counterfactual_run.py --bot %i --once --registry-id exitcf-v1" in s and "OnFailure=trader-health-fail@%n.service" in s
    for k, v in (("MemoryMax", "256M"), ("MemoryHigh", "192M"), ("CPUQuota", "30%"), ("Nice", "15"), ("IOSchedulingClass", "idle"),
                 ("TimeoutStartSec", "900"), ("ProtectSystem", "strict")):
        assert re.search(rf"^{k}={re.escape(v)}$", s, re.M), k
    assert "NoNewPrivileges=true" in s and "ProtectHome=read-only" in s and "PrivateTmp=true" in s and "PrivateNetwork=true" in s
    assert "EnvironmentFile" not in code and "backtests" not in code and "history" not in code      # anahtar yok; backtest yolu yok
    assert re.search(r"^ReadWritePaths=(.*)$", s, re.M).group(1).split() == ["-/opt/trader/var/%i"]
    ro = re.search(r"^ReadOnlyPaths=(.*)$", s, re.M).group(1).split()
    assert ro == ["-/opt/trader/var/%i/ledger.sqlite", "-/opt/trader/var/market.sqlite"]
    assert "OnCalendar=*-*-* 23:40:00 UTC" in tm and "Persistent=true" in tm and "RandomizedDelaySec=600" in tm
    cf = (DEPLOY / "trader-counterfactual@.timer").read_text(encoding="utf-8")
    assert "23:10:00 UTC" in cf and "RandomizedDelaySec=900" in cf and "23:10" < "23:40"            # 23:10 isi (+15 dk) 23:40'tan once biter
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "enable_now trader-exit-counterfactual@learner.timer" in t and "enable_now trader-exit-counterfactual@twin" not in t
    assert (ROOT / "scripts/exit_counterfactual_run.py").exists() and (ROOT / "docs/cikis-karsi-olgu-spec.md").exists()
    assert "trader-exit-counterfactual@twin.timer" in t                                            # ikiz birimi (varsa) kapatilir


def test_ct_kadro_and_c1_units_removed_and_cleaned_on_install():
    """CT/ML ayriligi + 24.11 kullanici karari: CT/C1 birimleri depoda yok; install.sh sunucuda durdurur/devre disi birakir/siler
    (varlik kontrollu, idempotent); C1 goc/temizlik betikleri ve cagrilari silindi (defter dosyalarina dokunulmaz)."""
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert not (DEPLOY / "trader-ct-kadro.service").exists() and not (DEPLOY / "trader-ct-kadro.timer").exists()
    assert not (DEPLOY / "trader-c1-goc.service").exists()
    assert "enable_now trader-ct-kadro" not in t and "enable_now trader-c1-goc" not in t
    assert 'systemctl disable --now "$u"' in t and "trader-ct-kadro.timer trader-ct-kadro.service trader-c1-goc.service" in t
    assert 'rm -f "${UNIT_DIR}/$u"' in t
    for gone in ("c1_goc_dene", "c1_acik_sayisi", "c1_temizle", "c1_goc.done", "scripts/c1_goc.py"):
        assert gone not in t, gone
    assert not (ROOT / "scripts" / "c1_goc.py").exists() and not (ROOT / "scripts" / "c1_temizle.py").exists()
    assert not (ROOT / "src" / "trader_core" / "kol_kaldirma.py").exists()
    assert "var/ct" not in t.replace("var/ct/kadro", "")                       # var/ct artik olusturulmaz
    assert not (ROOT / "scripts" / "ct_kadro_cek.py").exists() and not (ROOT / "src" / "trader_core" / "ct_kadro.py").exists()
    assert not (ROOT / "src" / "trader_engine" / "strategies" / "arms" / "c1.py").exists()


def test_durum_yayinla_no_longer_whitelists_c1_goc_raporu():
    t = (DEPLOY / "durum_yayinla.sh").read_text(encoding="utf-8")
    assert "c1_goc_raporu.json" not in t


def test_uzun_omurlu_daemonlar_reboot_sonrasi_acilir():
    """23.11: trader-telegram.service [Install] bolumu olmadan 'static' idi; sunucu yeniden baslayinca kapali kaldi."""
    for n in ("trader-telegram.service", "trader-feed.service", "trader-panel.service", "trader-engine@.service"):
        t = (DEPLOY / n).read_text(encoding="utf-8")
        assert "[Install]" in t and "WantedBy=multi-user.target" in t, n
