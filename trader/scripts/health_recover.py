#!/usr/bin/env python3
"""Yeniden baslatma kurtarma kontrol listesi (docs/saglik-spec.md Bolum 7). SALT OKUNUR.

Hicbir sey baslatmaz, duzeltmez, yazmaz (spool bosaltma dahil); kapiyi acmaz. Her adim:
PASS | WARN | FAIL | UNKNOWN ve yapilacak elle islem. Cikis: 0 hepsi PASS/WARN, 2 FAIL/UNKNOWN var.
Kullanim: health_recover.py --check
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE))

import health_run as R  # noqa: E402
from trader_core import health as H  # noqa: E402


def step(code, status, text, action=""):
    return {"step": code, "status": status, "detail": text, "action": action}


def run_checks(env, snap, state, *, run=subprocess.run, expected_dry_run=True) -> list[dict]:
    out = []
    for k, c in snap.containers.items():
        if c.state is None:
            out.append(step("R1", "UNKNOWN", f"{k} durumu okunamadi", "motor status.json okunamadi/yok: motor surecini (systemd/journal) elle kontrol et"))
        elif c.state != "running" or c.oom_killed:
            out.append(step("R1", "FAIL", f"{k} durum={c.state} oom={c.oom_killed}",
                            "status.json bayat: motor surecini ve journal'i incele (journalctl -u <motor birimi> -n 200)"))
        else:
            out.append(step("R1", "PASS", f"{k} motoru calisiyor (status taze), yeniden baslatma sayaci={c.restart_count}"))
    for bot in R.BOTS:
        db = R.ledger_path(env["ENGINE_VAR_DIR"], bot)
        st = os.path.join(env["ENGINE_VAR_DIR"], bot, "state.sqlite")
        for label, p in ((f"ledger_{bot}", db), (f"state_{bot}", st)):
            try:
                c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
                try:
                    r = c.execute("PRAGMA quick_check").fetchone()[0]
                finally:
                    c.close()
                out.append(step("R2", "PASS" if r == "ok" else "FAIL", f"{label} quick_check={r}",
                                "" if r == "ok" else "botu durdur, spec 6.9 ile son iyi yedegi geri yukle"))
            except Exception as e:  # noqa: BLE001
                out.append(step("R2", "UNKNOWN", f"{label} okunamadi ({type(e).__name__})"))
        lp = snap.ledger.get(bot)
        if lp is None:
            out.append(step("R3", "UNKNOWN", f"{bot} defter olculemedi"))
            continue
        out.append(step("R3", {True: "PASS", False: "FAIL", None: "UNKNOWN"}[lp.schema_ok], f"{bot} sema_ok={lp.schema_ok}",
                        "kod/sema uyumsuzlugu: imaj ve src surumunu kontrol et; goc yalniz bot durmusken, elle"))
        out.append(step("R4", "UNKNOWN" if lp.spool_lines is None else ("FAIL" if lp.spool_lines > 0 else "PASS"),
                        f"{bot} spool_lines={lp.spool_lines}",
                        "bot acilista drain_spool() cagirir; dolu kaliyorsa kapi/degraded'a bak; elle bosaltma yalniz botlar durmusken"))
        ap = snap.api.get(bot)
        if ap is None or lp.unledgered_ids is None:
            out.append(step("R5", "UNKNOWN", f"{bot} acik islem/defter farki olculemedi"))
        elif lp.unledgered_ids:
            out.append(step("R5", "FAIL", f"{bot} defterde girisi olmayan acik islem: {list(lp.unledgered_ids)}",
                            "elle karar: geriye donuk (isaretli) giris ekle ya da pozisyonu kapat; otomatik duzeltme yok"))
        else:
            out.append(step("R5", "PASS", f"{bot} acik islemlerin hepsi defterde"))
        if ap is None or ap.unprotected_ids is None:
            out.append(step("R7", "UNKNOWN", f"{bot} acik pozisyon stop'lari status.json'dan okunamadi",
                            "status.json yok/bozuk: motoru ve pozisyonlari elle kontrol et"))
        elif ap.unprotected_ids:
            out.append(step("R7", "FAIL", f"{bot} stop'u olmayan acik pozisyon: {list(ap.unprotected_ids)}",
                            "motor mutabakati stop'u yeniden kurana dek izle; gerekirse pozisyonu elle kapat (insan karari)"))
        else:
            out.append(step("R7", "PASS", f"{bot} tum acik pozisyonlarin stop'u var (paper: status.open_positions[].stop)"))
        if ap is None or ap.dry_run is None:
            out.append(step("R8", "UNKNOWN", f"{bot} dry_run okunamadi (status.json)"))
        elif ap.dry_run != expected_dry_run:
            out.append(step("R8", "FAIL", f"{bot} dry_run={ap.dry_run} beklenmeyen", "ACIL: yapilandirmayi kontrol et"))
        else:
            out.append(step("R8", "PASS", f"{bot} dry_run={ap.dry_run}"))
        c = snap.containers.get(f"trader-{bot}")
        if c is None or c.started_at is None or lp.last_write_at is None:
            out.append(step("R9", "UNKNOWN", f"{bot} kapi yoklamasi olculemedi"))
        elif lp.last_write_at >= c.started_at:
            out.append(step("R9", "PASS", f"{bot} baslangictan sonra defter yazimi var"))
        else:
            out.append(step("R9", "WARN", f"{bot} baslangictan sonra defter yazimi yok", "2 mum sonra yeniden bak"))
    try:
        p = run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"], capture_output=True, text=True,
                timeout=5, check=True)
        v = p.stdout.strip()
        out.append(step("R10", "PASS" if v == "yes" else "WARN", f"NTPSynchronized={v}",
                        "" if v == "yes" else "saat esitlemesini kontrol et"))
    except Exception:  # noqa: BLE001
        out.append(step("R10", "UNKNOWN", "timedatectl okunamadi"))
    fps = (state or {}).get("fingerprints", {})
    out.append(step("R11", "PASS", "onceki bozuk kontroller: " + (", ".join(sorted(fps)) or "yok")))
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv != ["--check"]:
        print("kullanim: health_recover.py --check (salt okunur)", file=sys.stderr)
        return 1
    try:
        from datetime import datetime, timezone
        env = R.load_env()
        now = datetime.now(timezone.utc)
        state, _ = R.load_state(os.path.join(env.get("STATE_DIR", "/var/lib/trader-health"), "state.json"))
        import time
        snap = R.collect(env, state, now, deadline=time.monotonic() + R.TOTAL_BUDGET_S)
        rows = run_checks(env, snap, state)
        for r in rows:
            print(f"{r['step']:4} {r['status']:8} {r['detail']}" + (f"\n         -> {r['action']}" if r["action"] else ""))
        report = H.evaluate(snap)
        print(f"genel saglik: {report.overall.value}")
        return 2 if any(r["status"] in ("FAIL", "UNKNOWN") for r in rows) else 0
    except Exception as e:  # noqa: BLE001
        print(f"health_recover: hata: {type(e).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
