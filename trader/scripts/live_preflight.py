#!/usr/bin/env python3
"""Canli birim on denetimi (DD-9 §6.5). `install.sh --live` root kopyadan, root venv ile calistirir; ag yok.

Her denetim icin stdout'a tek satir `OK <kod>` ya da `FAIL <kod>` yazar; HICBIR DEGER (anahtar, gizli anahtar, LIVE_CONFIRM)
yazilmaz. Biri FAIL ise donus 1, hepsi OK ise 0. Yalniz standart kutuphane + trader_core.live_paths.
"""
from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import live_paths as LP  # noqa: E402

TRADER_USER, TG_GROUP = "trader", "trader-tg"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def _parse_env(path: Path) -> dict[str, str] | None:
    """AD=deger satirlari (yorum/bos satir atlanir). Okunamazsa None."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    out: dict[str, str] = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, _, v = ln.partition("=")
        out[k.strip()] = v.strip()
    return out


def _check_env_perms(etc: Path, skip_owner: bool) -> bool:
    files = sorted(etc.glob("trader-*.env"))
    if not files:
        return False
    for p in files:
        try:
            st = os.lstat(p)
        except OSError:
            return False
        if not stat.S_ISREG(st.st_mode):               # sembolik baglanti/dizin = ret
            return False
        if stat.S_IMODE(st.st_mode) != 0o600:
            return False
        if not skip_owner and st.st_uid != 0:
            return False
    return True


def _trader_groups(id_groups) -> tuple[str, ...]:
    if id_groups is not None:
        return tuple(id_groups)
    import grp
    import pwd
    try:
        pw = pwd.getpwnam(TRADER_USER)
    except KeyError:
        return ()
    names = []
    try:
        names.append(grp.getgrgid(pw.pw_gid).gr_name)
    except KeyError:
        pass
    names += [g.gr_name for g in grp.getgrall() if TRADER_USER in g.gr_mem]
    return tuple(names)


def main(argv=None, *, etc_dir="/etc", config_dir=None, id_groups=None) -> int:
    ap = argparse.ArgumentParser(prog="live_preflight.py")
    ap.add_argument("--etc-dir", default=None)
    ap.add_argument("--config-dir", default=None)
    ap.add_argument("--skip-owner", action="store_true", help="yalniz test: dosya sahibi denetimini kapatir")
    a = ap.parse_args(argv)
    etc = Path(a.etc_dir or etc_dir)
    cdir = a.config_dir or config_dir or str(_HERE.parent / "config")
    results: list[tuple[str, bool]] = []

    def rec(code: str, ok: bool) -> None:
        results.append((code, bool(ok)))

    rec("env_perms", _check_env_perms(etc, a.skip_owner))

    live = _parse_env(etc / "trader-live.env")
    tag = None
    try:
        tag = LP.expected_from_config(cdir)
    except LP.LivePathError:
        pass
    key = (live or {}).get("BINANCE_API_KEY", "")
    sec = (live or {}).get("BINANCE_API_SECRET", "")
    conf = (live or {}).get("LIVE_CONFIRM", "")
    rec("live_env_complete", live is not None and bool(conf) and all(len(v) >= 32 and not re.search(r"\s", v) for v in (key, sec)))
    rec("live_confirm_matches", tag is not None and bool(conf) and conf == tag["account_tag"])
    tn = _parse_env(etc / "trader-testnet.env")
    tkey = (tn or {}).get("BINANCE_API_KEY", "")
    rec("keys_not_testnet", not (tkey and key and tkey == key))

    def paths_ok(env: dict[str, str] | None, need_live_bots: bool) -> bool:
        if env is None:
            return False
        if need_live_bots and env.get("LIVE_BOTS", "") != "learner":
            return False
        return LP.check_against_config(env, cdir) == ()

    rec("telegram_paths", paths_ok(_parse_env(etc / "trader-telegram.env"), True))
    rec("health_paths", paths_ok(_parse_env(etc / "trader-health.env"), True))
    les = _parse_env(etc / "trader-lesson.env")      # dosya adi tarihsel: yorumcu/haftalik ozet/veri servislerinin ortak env dosyasi (ders servisi kaldirildi)
    if les is not None and tag is not None:
        les = {**les, "LIVE_BOTS": "learner", "LIVE_VAR_DIR": tag["var_dir"], "LIVE_PAUSE_FILE": tag["pause_file"]}
        rec("ortak_env_paths", paths_ok(les, False))
    else:
        rec("ortak_env_paths", False)
    rec("trader_not_in_tg", TG_GROUP not in _trader_groups(id_groups))
    rel = None
    try:
        rel = _parse_env(etc / "trader-release")
    except Exception:  # noqa: BLE001
        rel = None
    rec("release_pinned", bool(rel) and bool(_HEX40.match(rel.get("COMMIT", ""))))

    for code, ok in results:
        print(f"{'OK' if ok else 'FAIL'} {code}")
    return 0 if all(ok for _c, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
