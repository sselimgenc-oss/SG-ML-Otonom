"""Risk kademe denetimi cekirdegi (docs/motor/12-risk-kademe.md, RK-1): sabitler, ozet zincirli gunluk, katlama (`fold`),
tetikler (`evaluate`), etkin risk (`step_config`), sayaclar (`counters`) ve aktarim eslestirme (`match_transfers`).

Saf Python (stdlib + trader_core.risk); `trader_engine` ice aktarilmaz. Risk sabitleri YALNIZ burada (kod sabiti);
yapilandirma dosyalarina yazilmaz. Kademe durumu gunlugun saf katlamasidir; hicbir durum baska yerde tutulmaz.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from .risk import RiskConfig, tightened

SCHEMA = "risk-ladder/1"
STEPS = {-1: 0.0035, 0: 0.005, 1: 0.0075, 2: 0.010, 3: 0.012, 4: 0.014}   # basamak -> hedef islem riski
STEP_NAMES = {-1: "K-1", 0: "K0", 1: "K1", 2: "K2", 3: "K3", 4: "K4"}
START_STEP = 0
MAX_STEP_APPROVABLE = 0          # RK-1: step_up yalniz K-1 -> K0. RK-1b bu sabiti yukseltir
# 23.11 kullanici karari: canli = kagit. Canli gunlugun `initial` satiri `start_step` tasiyabilir (en cok LIVE_START_STEP = K2 = %1);
# gunluk kendi kendini tanimlar. Onaylanabilir tavan = max(MAX_STEP_APPROVABLE, gunlugun baslangic basamagi): dusus sonrasi geri cikis
# en cok baslangic basamagina kadardir. Tum asagi inis korumalari (tepeden -%10/-%15, -%20 durma, taban, capital_latch) degismez.
LIVE_START_STEP = 2
# 24.11 kullanici karari: risk dusurme kapali; etkin risk her kipte yapilandirmadaki deger (%1). Ayar degil, yalniz kod sabiti.
STEP_RISK_ENABLED = False
KM1_MIN_CAPITAL = 1000.0         # dep_net bunun altindaysa en alt basamak K0
DOWN_1_RATIO = 0.90              # equity <= 0.90 * peak  (tepeden -%10)
DOWN_2_RATIO = 0.85              # equity <= 0.85 * peak  (tepeden -%15)
STOP_RATIO = 0.80                # equity <= 0.80 * base  (-%20 durma)
FLOOR_RATIO = 0.60               # equity <= 0.60 * dep_net (son taban)
CAPITAL_LATCH_RATIO = 0.85      # equity <= 0.85 * dep_net -> yeni giris mandali (capital_latch; tum kiplerde, yalniz kullanici acar)
NEAR_RATIO = 0.85                # equity <= 0.85 * base -> "esige yaklasiyor" uyarisi
CONFIRM_N = 2
EVAL_EVERY_S = 60.0
XFER_POLL_S = 120.0
XFER_STALE_S = 900.0
XFER_TOL = 1.0
XFER_WINDOW_S = 7 * 86400
XFER_MUST_S = 5 * 86400
XFER_PAIR_S = 48 * 3600
INIT_TOL_ABS = 2.0
INIT_TOL_REL = 0.02
RESUME_MIN_WAIT_S = 86400        # yalniz Telegram yolu
STATUS_FRESH_S = 120.0
STEP_UP_MIN_TRADES = 60
STEP_UP_MIN_DAYS = 42
STEP_UP_SINCE_DOWN_DAYS = 56
NOTE_MAX = 200
ZERO_HASH = "0" * 64
LIST_CLOSED_MAX = 10000

UTC = timezone.utc
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
_EPS = 1e-9


class LadderLogError(Exception):
    """Gunluk yok/bozuk/gecersiz satir. Kismi katlama yoktur."""


@dataclass(frozen=True)
class LadderState:
    status: Literal["ok", "review", "floor"]
    step: int
    step_since: datetime
    dep_net: float
    base: float
    peak: float
    started_at: datetime
    last_down_at: datetime | None
    stopped_at: datetime | None
    fired: frozenset
    seq: int
    head_hash: str
    max_step: int = 0                # step_up tavani (gunlugun baslangic basamagina gore; fold doldurur)


@dataclass(frozen=True)
class Action:
    kind: Literal["step_down", "review_stop", "floor_stop"]
    step: int | None = None          # yalniz step_down
    trigger: str | None = None       # yalniz step_down


@dataclass(frozen=True)
class Transfer:
    ts: datetime
    amount: float                    # isaretli: vadeli cuzdana giris +
    tran_id: str
    asset: str


@dataclass(frozen=True)
class MatchResult:
    ok: bool
    unmatched_exchange: tuple
    unmatched_log: tuple             # seq'ler


# ======================================================================================================
# Yardimcilar
# ======================================================================================================
def fmt_at(t: datetime) -> str:
    if t.tzinfo is None:
        raise LadderLogError("zaman dilimsiz saat")
    return t.astimezone(UTC).strftime(_TS_FMT)


def parse_at(s: Any) -> datetime:
    if not isinstance(s, str) or len(s) != 20:
        raise LadderLogError(f"at gecersiz: {s!r}")
    try:
        return datetime.strptime(s, _TS_FMT).replace(tzinfo=UTC)
    except ValueError as e:
        raise LadderLogError(f"at gecersiz: {s!r}") from e


def lowest(dep_net: float) -> int:
    """En alt basamak: K-1 yalniz dep_net >= KM1_MIN_CAPITAL iken; aksi K0."""
    return -1 if dep_net >= KM1_MIN_CAPITAL else 0


def _fin(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


finite_number = _fin


def _th(ratio: float, ref: float) -> float:
    return round(ratio * ref, 8)


def row_hash(row: Mapping) -> str:
    body = {k: v for k, v in row.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


_COMMON = ("seq", "at", "kind", "by", "note", "prev", "hash")
_EXTRA = {
    "initial": ("amount",), "deposit": ("amount",), "withdraw": ("amount", "equity", "capital_part"),
    "adjust": ("amount",), "peak": ("value",), "step_down": ("step", "trigger", "equity", "peak"),
    "review_stop": ("equity", "base"), "floor_stop": ("equity", "dep_net"),
    "review_resume": ("equity", "rebase", "decision"), "floor_restart": ("equity", "decision"),
    "step_up": ("step", "decision"),
}
KINDS = tuple(_EXTRA)
TRIGGERS = ("dd_peak_10", "dd_peak_15")


def _bad(msg: str) -> LadderLogError:
    return LadderLogError(msg)


def _need_pos(row: Mapping, key: str) -> float:
    v = row[key]
    if not _fin(v) or v <= 0:
        raise _bad(f"{row.get('kind')}.{key} sonlu ve > 0 olmali: {v!r}")
    return float(v)


def _need_str(row: Mapping, key: str, *, nonempty: bool) -> str:
    v = row[key]
    if not isinstance(v, str) or (nonempty and not v.strip()):
        raise _bad(f"{row.get('kind')}.{key} {'bos olmayan ' if nonempty else ''}metin olmali")
    return v


def _need_step(row: Mapping) -> int:
    v = row["step"]
    if isinstance(v, bool) or not isinstance(v, int) or v not in STEPS:
        raise _bad(f"{row.get('kind')}.step gecersiz: {v!r}")
    return v


# ======================================================================================================
# Katlama
# ======================================================================================================
def fold(rows: Sequence[Mapping]) -> LadderState | None:
    """Gunluk satirlarini dogrular ve katlar. Satir yok -> None. Herhangi bir ihlal -> LadderLogError (kismi durum yok)."""
    st: dict[str, Any] | None = None
    prev_hash = ZERO_HASH
    prev_at: datetime | None = None
    for i, row in enumerate(rows, 1):
        if not isinstance(row, Mapping):
            raise _bad(f"satir {i}: nesne degil")
        kind = row.get("kind")
        if not isinstance(kind, str) or kind not in _EXTRA:
            raise _bad(f"satir {i}: bilinmeyen kind {kind!r}")
        want = set(_COMMON) | set(_EXTRA[kind])
        if kind == "initial" and "start_step" in row:
            want.add("start_step")                                # istege bagli (yalniz canli: LIVE_START_STEP)
        if set(row) != want:
            raise _bad(f"satir {i}: alanlar uyusmuyor (fazla/eksik): {sorted(set(row) ^ want)}")
        seq = row["seq"]
        if isinstance(seq, bool) or not isinstance(seq, int) or seq != i:
            raise _bad(f"satir {i}: seq kirik: {seq!r}")
        at = parse_at(row["at"])
        if prev_at is not None and at < prev_at:
            raise _bad(f"satir {i}: at geri gitti")
        by = row["by"]
        if not isinstance(by, str) or not by:
            raise _bad(f"satir {i}: by gecersiz")
        note = row["note"]
        if not isinstance(note, str) or len(note) > NOTE_MAX:
            raise _bad(f"satir {i}: note gecersiz")
        if row["prev"] != prev_hash:
            raise _bad(f"satir {i}: prev kirik")
        if row["hash"] != row_hash(row):
            raise _bad(f"satir {i}: hash kirik")
        if i == 1 and kind != "initial":
            raise _bad("ilk satir initial olmali")
        if i > 1 and kind == "initial":
            raise _bad("initial yalniz seq 1")
        st = _apply(st, row, kind, at, i)
        prev_hash, prev_at = row["hash"], at
    if st is None:
        return None
    return LadderState(
        status=st["status"], step=st["step"], step_since=st["step_since"], dep_net=st["dep_net"], base=st["base"],
        peak=st["peak"], started_at=st["started_at"], last_down_at=st["last_down_at"], stopped_at=st["stopped_at"],
        fired=frozenset(st["fired"]), seq=len(rows), head_hash=prev_hash,
        max_step=max(MAX_STEP_APPROVABLE, st["start_step"]))


def _apply(st: dict | None, row: Mapping, kind: str, at: datetime, i: int) -> dict:
    if kind == "initial":
        a = _need_pos(row, "amount")
        start = START_STEP
        if "start_step" in row:
            start = row["start_step"]
            if isinstance(start, bool) or not isinstance(start, int) or not (START_STEP <= start <= LIVE_START_STEP):
                raise _bad(f"satir {i}: start_step gecersiz: {start!r}")
        return {"status": "ok", "step": start, "start_step": start, "step_since": at, "dep_net": a, "base": a, "peak": a,
                "started_at": at, "last_down_at": None, "stopped_at": None, "fired": set()}
    assert st is not None
    s = dict(st)
    s["fired"] = set(st["fired"])
    if kind == "deposit":
        a = _need_pos(row, "amount")
        s["dep_net"] += a
        s["base"] += a
        s["peak"] += a
    elif kind == "withdraw":
        a = _need_pos(row, "amount")
        _need_pos(row, "equity")
        c = row["capital_part"]
        if not _fin(c) or c < 0 or c > a:
            raise _bad(f"satir {i}: capital_part gecersiz: {c!r}")
        s["dep_net"] -= c
        s["base"] -= c
        s["peak"] = max(s["base"], s["peak"] - a)
        if not (s["dep_net"] > 0 and s["base"] > 0):
            raise _bad(f"satir {i}: cekme sermayeyi sifirliyor")
    elif kind == "adjust":
        a = row["amount"]
        if not _fin(a) or a == 0:
            raise _bad(f"satir {i}: adjust.amount sonlu ve sifirdan farkli olmali")
        _need_str(row, "note", nonempty=True)
        s["dep_net"] += a
        s["base"] += a
        s["peak"] = max(s["base"], s["peak"] + a)
        if not (s["dep_net"] > 0 and s["base"] > 0):
            raise _bad(f"satir {i}: adjust sonucu > 0 olmali")
    elif kind == "peak":
        v = _need_pos(row, "value")
        s["peak"] = max(s["peak"], v)
        s["fired"] = set()
    elif kind == "step_down":
        step = _need_step(row)
        if row["trigger"] not in TRIGGERS:
            raise _bad(f"satir {i}: trigger gecersiz")
        _need_pos(row, "equity")
        _need_pos(row, "peak")
        if not (-1 <= step < s["step"]):
            raise _bad(f"satir {i}: step_down yalniz asagi")
        s["step"] = step
        s["step_since"] = at
        s["last_down_at"] = at
        s["fired"].add(row["trigger"])
    elif kind == "review_stop":
        _need_pos(row, "equity")
        _need_pos(row, "base")
        if s["status"] != "ok":
            raise _bad(f"satir {i}: review_stop yalniz ok durumundan")
        s["status"] = "review"
        s["stopped_at"] = at
        s["last_down_at"] = at
    elif kind == "floor_stop":
        _need_pos(row, "equity")
        _need_pos(row, "dep_net")
        if s["status"] not in ("ok", "review"):
            raise _bad(f"satir {i}: floor_stop floor durumundan gecersiz")
        s["status"] = "floor"
        s["stopped_at"] = at
        s["last_down_at"] = at
    elif kind == "review_resume":
        eq = _need_pos(row, "equity")
        if not isinstance(row["rebase"], bool):
            raise _bad(f"satir {i}: rebase bool olmali")
        _need_str(row, "decision", nonempty=False)
        if s["status"] != "review":
            raise _bad(f"satir {i}: review_resume yalniz review durumundan")
        s["status"] = "ok"
        if row["rebase"]:
            s["base"] = min(s["base"], eq)
            s["peak"] = max(s["base"], eq)
            s["fired"] = set()
            if s["step"] > 0:
                s["step"] = 0
                s["step_since"] = at
    elif kind == "floor_restart":
        eq = _need_pos(row, "equity")
        _need_str(row, "decision", nonempty=True)
        if s["status"] != "floor":
            raise _bad(f"satir {i}: floor_restart yalniz floor durumundan")
        s["status"] = "ok"
        s["dep_net"] = s["base"] = s["peak"] = eq
        s["step"] = min(s["step"], 0)
        s["step_since"] = at
        s["fired"] = set()
    elif kind == "step_up":
        step = _need_step(row)
        _need_str(row, "decision", nonempty=True)
        if s["status"] != "ok":
            raise _bad(f"satir {i}: step_up yalniz ok durumunda")
        if step != s["step"] + 1 or step > max(MAX_STEP_APPROVABLE, s["start_step"]):
            raise _bad(f"satir {i}: step_up gecersiz basamak {step}")
        s["step"] = step
        s["step_since"] = at
    return s


# ======================================================================================================
# Gunluk (dosya ya da bellek)
# ======================================================================================================
class LadderLog:
    """Yalniz eklenen, ozet zincirli gunluk. path=None: yalniz bellek (kagit gozlemi)."""

    def __init__(self, path: str | None) -> None:
        self.path = None if path is None else str(path)
        self._mem: list[dict] = []

    # -- okuma ---------------------------------------------------------------
    def _read_file(self) -> list[dict]:
        assert self.path is not None
        try:
            raw = open(self.path, "rb").read()
        except FileNotFoundError:
            return []
        except OSError as e:
            raise _bad(f"gunluk okunamadi: {type(e).__name__}") from e
        if not raw:
            return []
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise _bad("gunluk UTF-8 degil") from e
        if not text.endswith("\n"):
            raise _bad("gunluk satiri yarim (satir sonu yok)")
        out = []
        for n, line in enumerate(text[:-1].split("\n"), 1):
            try:
                d = json.loads(line)
            except ValueError as e:
                raise _bad(f"satir {n}: JSON degil") from e
            if not isinstance(d, dict):
                raise _bad(f"satir {n}: nesne degil")
            out.append(d)
        return out

    def _read_shared(self) -> list[dict]:
        """Yazarin yarim satirini gormemek icin paylasimli kilit (kilit dosyasi acilamazsa kilitsiz okunur)."""
        assert self.path is not None
        if not os.path.exists(self.path):
            return []
        try:
            lk = open(f"{self.path}.lock", "a+")
        except OSError:
            return self._read_file()
        try:
            fcntl.flock(lk.fileno(), fcntl.LOCK_SH)
            return self._read_file()
        finally:
            lk.close()

    def rows(self) -> list[dict]:
        if self.path is None:
            rows = [dict(r) for r in self._mem]
        else:
            rows = self._read_shared()
        fold(rows)                                       # tum zincir dogrulanir; bozuksa LadderLogError
        return rows

    def state(self) -> LadderState | None:
        return fold(self.rows())

    # -- yazma ---------------------------------------------------------------
    def append(self, kind: str, by: str, now: datetime, *, note: str = "", **fields: Any) -> dict:
        """Kilit altinda oku+dogrula+ekle. Eklenince katlama gecersizse LadderLogError ve HICBIR SEY yazilmaz."""
        if self.path is None:
            return self._append_to(self._mem, kind, by, now, note, fields)
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(f"{self.path}.lock", "a+") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            try:
                rows = self._read_file()
                row = self._build(rows, kind, by, now, note, fields)
                line = json.dumps(row, ensure_ascii=False) + "\n"
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line)
                    f.flush()
                    os.fsync(f.fileno())
                return row
            finally:
                fcntl.flock(lk.fileno(), fcntl.LOCK_UN)

    def _append_to(self, rows: list, kind, by, now, note, fields) -> dict:
        row = self._build(rows, kind, by, now, note, fields)
        rows.append(row)
        return dict(row)

    @staticmethod
    def _build(rows: list[dict], kind: str, by: str, now: datetime, note: str, fields: Mapping) -> dict:
        fold(rows)                                       # mevcut gunluk gecerli olmali
        if not isinstance(now, datetime):
            raise _bad("now datetime olmali")
        row: dict[str, Any] = {"seq": len(rows) + 1, "at": fmt_at(now), "kind": kind, "by": by, "note": note}
        row.update(fields)
        row["prev"] = rows[-1]["hash"] if rows else ZERO_HASH
        try:
            row["hash"] = row_hash(row)
            json.dumps(row)
        except (TypeError, ValueError) as e:
            raise _bad(f"satir serilestirilemedi: {e}") from e
        fold(rows + [row])                               # ekleyince gecersizse yazilmaz
        return row


# ======================================================================================================
# Tetikler
# ======================================================================================================
def evaluate(st: LadderState, equity: float) -> tuple[Action, ...]:
    """Saf: 0 ya da 1 eylem (12 §6.1). Gecersiz equity -> ValueError."""
    if not _fin(equity) or equity <= 0:
        raise ValueError(f"equity sonlu ve > 0 olmali: {equity!r}")
    if st.status == "floor":
        return ()
    if equity <= _th(FLOOR_RATIO, st.dep_net):
        return (Action("floor_stop"),)
    if st.status == "review":
        return ()
    if equity <= _th(STOP_RATIO, st.base):
        return (Action("review_stop"),)
    if not STEP_RISK_ENABLED:
        return ()                                        # 24.11: dd_peak_15 / dd_peak_10 inisleri uretilmez
    low = lowest(st.dep_net)
    if equity <= _th(DOWN_2_RATIO, st.peak) and "dd_peak_15" not in st.fired:
        target = max(low, 0 if st.step > 0 else -1)
        if target < st.step:
            return (Action("step_down", target, "dd_peak_15"),)
        return ()                                        # zaten en altta: dd_peak_10'a gecilmez
    if equity <= _th(DOWN_1_RATIO, st.peak) and "dd_peak_10" not in st.fired:
        target = max(low, st.step - 1)
        if target < st.step:
            return (Action("step_down", target, "dd_peak_10"),)
    return ()


def step_config(base_cfg: RiskConfig, step: int) -> RiskConfig:
    """Etkin risk: min(cfg.target_trade_risk, STEPS[step]); yalniz `tightened` ile (kilit gevsemez)."""
    if isinstance(step, bool) or not isinstance(step, int) or step not in STEPS:
        raise ValueError(f"bilinmeyen basamak: {step!r}")
    if not STEP_RISK_ENABLED:
        return base_cfg                                  # 24.11: eski gunluk basamagi riski dusuremez
    v = min(base_cfg.target_trade_risk, STEPS[step])
    if v == base_cfg.target_trade_risk:
        return base_cfg
    return tightened(base_cfg, target_trade_risk=v)


# ======================================================================================================
# Sayaclar
# ======================================================================================================
def counted_trades(trades: Sequence, st: LadderState) -> list:
    """Sayilan islemler, cikis zamanina gore eskiden yeniye: kapanmis, entry_ts >= started_at, exit_reason != manual."""
    sel = [t for t in trades
           if getattr(t, "exit_ts", None) is not None and t.entry_ts >= st.started_at and t.exit_reason != "manual"]
    sel.sort(key=lambda t: (t.exit_ts, t.trade_id))
    return sel


def counters(trades: Sequence, st: LadderState, now: datetime) -> dict:
    sel = counted_trades(trades, st)
    step_sel = [t for t in sel if t.entry_ts >= st.step_since]
    rs = [t.r_multiple for t in step_sel if _fin(t.r_multiple)]
    consec = 0
    for t in reversed(sel):
        r = t.r_multiple
        if _fin(r) and r < 0:
            consec += 1
        else:
            break
    last30 = [t.r_multiple for t in sel[-30:] if _fin(t.r_multiple)]
    days = int(max(0.0, (now - st.step_since).total_seconds()) // 86400)
    return {"total_trades": len(sel), "step_trades": len(step_sel), "step_days": days,
            "step_mean_r": (sum(rs) / len(rs)) if rs else None, "consec_losses": consec,
            "last30_sum_r": float(sum(last30))}


# ======================================================================================================
# Aktarim eslestirme (12 §7)
# ======================================================================================================
def match_transfers(rows: Sequence[Mapping], transfers: Sequence[Transfer], now: datetime) -> MatchResult:
    started = parse_at(rows[0]["at"]) if rows else now
    ex_from = max(started, now - timedelta(seconds=XFER_WINDOW_S))
    log_from = now - timedelta(seconds=XFER_WINDOW_S + XFER_PAIR_S)
    must_from = now - timedelta(seconds=XFER_MUST_S)      # v1.1: yalniz gunluk tarafi 5 gun; borsa tarafi tam 7 gun
    pool = []                                            # (seq, at, signed)
    for r in rows:
        if r["kind"] in ("deposit", "withdraw"):
            at = parse_at(r["at"])
            if at >= log_from:
                pool.append((r["seq"], at, r["amount"] if r["kind"] == "deposit" else -r["amount"]))
    pool.sort(key=lambda x: (x[1], x[0]))
    used: set[int] = set()
    xs = sorted((t for t in transfers if t.ts >= ex_from), key=lambda t: (t.ts, str(t.tran_id)))
    un_ex: list[Transfer] = []
    for t in xs:
        hit = None
        if t.asset == "USDT":
            for seq, at, amt in pool:
                if seq in used:
                    continue
                if (amt > 0) != (t.amount > 0):
                    continue
                if abs(amt - t.amount) > XFER_TOL + _EPS:
                    continue
                if abs((at - t.ts).total_seconds()) > XFER_PAIR_S:
                    continue
                hit = seq
                break
        if hit is None:
            un_ex.append(t)
        else:
            used.add(hit)
    un_log = [(seq, at) for seq, at, _ in pool if seq not in used]
    bad = bool(un_ex) or any(at >= must_from for _, at in un_log)     # un_ex zaten 7 gunluk havuzdan (ex_from)
    return MatchResult(ok=not bad, unmatched_exchange=tuple(un_ex), unmatched_log=tuple(s for s, _ in un_log))


def init_wallet_mismatch(rows: Sequence[Mapping], wallet: float) -> bool:
    """Ilk kurulum denetimi (12 §7): gunlukte yalniz `initial` varken cuzdan ile dep_net uyusmuyor mu."""
    if len(rows) != 1 or rows[0].get("kind") != "initial" or not _fin(wallet):
        return False
    dep = float(rows[0]["amount"])
    return abs(wallet - dep) > max(INIT_TOL_ABS, INIT_TOL_REL * dep)


def step_up_problems(st: LadderState, cnt: Mapping, now: datetime) -> list[str]:
    """`ladder step-up` kosullari (12 §5): tutmayanlarin listesi (bos = hepsi tutuyor)."""
    out: list[str] = []
    if st.status != "ok":
        out.append(f"durum ok degil ({st.status})")
    if st.step + 1 > st.max_step:
        out.append(f"{STEP_NAMES.get(st.step, st.step)} -> {STEP_NAMES.get(st.step + 1, st.step + 1)} RK-1'de onaylanamaz "
                   f"(tavan {STEP_NAMES[st.max_step]})")
    if cnt["step_trades"] < STEP_UP_MIN_TRADES:
        out.append(f"basamak islemi {cnt['step_trades']} < {STEP_UP_MIN_TRADES}")
    if cnt["step_days"] < STEP_UP_MIN_DAYS:
        out.append(f"basamak gunu {cnt['step_days']} < {STEP_UP_MIN_DAYS}")
    m = cnt["step_mean_r"]
    if m is None or m < 0:
        out.append(f"basamak ortalama R {m} < 0")
    if st.last_down_at is not None and (now - st.last_down_at).total_seconds() < STEP_UP_SINCE_DOWN_DAYS * 86400:
        days = int(max(0.0, (now - st.last_down_at).total_seconds()) // 86400)
        out.append(f"son dusus {days} gun once < {STEP_UP_SINCE_DOWN_DAYS}")
    return out
