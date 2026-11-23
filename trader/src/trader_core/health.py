"""Saglik izleme: saf degerlendirme, uyari planlama, dis nabiz gonderici. Bkz. docs/saglik-spec.md (v1).

Girdi kaynagi: kendi motorumuzun `status.json` dosyasi (`ApiProbe` adi tarihsel; alanlari
`scripts/health_run.py::probe_status` doldurur). Bkz. spec "Motor uyarlamasi".

Yalnizca standart kutuphane. Modul dosya/ag/saat/surec OKUMAZ; olcumleri `scripts/health_run.py`
toplar ve `HealthSnapshot` olarak verir. Her belirsizlikte fail-closed: olculemeyen girdi
`UNKNOWN` olur ve nabzi keser. Modul islem acmaz, bot baslatmaz, defter satiri yazmaz.
(`HttpsHeartbeat` yalnizca `ok()/fail()` cagrilinca ag kullanir.)
"""
from __future__ import annotations

import logging
import math
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, fields, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Mapping, Protocol
from urllib.parse import urlsplit

__all__ = [
    "Status", "CheckResult", "HealthReport", "HealthSnapshot", "ApiProbe", "LedgerProbe",
    "ContainerProbe", "HealthConfig", "DEFAULT_CFG", "evaluate", "combine", "Alert", "Notifier",
    "LogNotifier", "NullNotifier", "plan_alerts", "revert_failed_alerts", "empty_state",
    "PauseProbe", "quiet_http_loggers", "IMMEDIATE_CODES", "HeartbeatSender", "HttpsHeartbeat", "parse_env_text",
    "parse_maintenance", "heartbeat_message", "should_send_ok", "REQUIRED_CHECKS", "MarketProbe",
    "MlProbe", "DriftProbe", "BanProbe", "HaberSinyalProbe", "Dl1PaketProbe",
]

log = logging.getLogger("trader.health")

def quiet_http_loggers() -> None:
    """urllib3/requests gunlukleri en az INFO (DEBUG istek satirlarini ve sorgu dizgilerini yazar; imza/anahtar sizmasin)."""
    for n in ("urllib3", "requests"):
        lg = logging.getLogger(n)
        if lg.getEffectiveLevel() < logging.INFO:
            lg.setLevel(logging.INFO)


GIB = 1024 ** 3
MIB = 1024 ** 2


class Status(str, Enum):
    OK = "OK"
    WARN = "WARN"
    CRIT = "CRIT"
    UNKNOWN = "UNKNOWN"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    code: str
    detail: str
    value: float | None = None
    threshold: float | None = None


# Zorunlu kontroller (Z): taban adlari. Bot bazlilar "<ad>:<bot>" olur.
REQUIRED_CHECKS = ("api_reachable", "bot_loop_age", "candle_age", "ledger_write_age", "ledger_gate",
                   "disk_free", "memory", "container_restarts")
_PER_BOT = ("api_reachable", "bot_loop_age", "candle_age", "ledger_write_age", "ledger_gate",
            "container_restarts")


@dataclass(frozen=True)
class HealthReport:
    generated_at: datetime
    results: tuple[CheckResult, ...]
    overall: Status
    healthy: bool

    def failing(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results
                     if r.status in (Status.WARN, Status.CRIT, Status.UNKNOWN))


# ---------------------------------------------------------------------------------------------
# Anlik goruntu
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ApiProbe:
    ping_ok: bool | None = None
    last_process_at: datetime | None = None
    last_candle_open: datetime | None = None
    open_trade_ids: tuple[int, ...] | None = None
    dry_run: bool | None = None
    # Motor status.json alanlari (docs/saglik-spec.md "Motor uyarlamasi"); None = bilgi yok/saglanmadi.
    gate_code: str | None = None          # status.gate.code ("ok", "kill", "degraded", ...)
    kill: bool | None = None              # status.kill
    ledger_errors: int | None = None      # status.counters.ledger_errors (surec basindan beri)
    unprotected_ids: tuple[int, ...] | None = None   # stop'u olmayan acik pozisyonlar (yalniz kurtarma R7)
    # WP-B8: canli/testnet `status.exchange` blogu (11 §9.4). mode: status.mode; has_exchange: blok var mi.
    mode: str | None = None
    has_exchange: bool = False
    exchange_reachable: bool | None = None
    exchange_last_sync: datetime | None = None
    naked: tuple[tuple[int, str, float], ...] | None = None   # (trade_id, cift, stopsuz sure sn); None = okunamadi
    # 12 §11: status.json `risk_ladder` blogu (+ opsiyonel "pause_holds": [{reason, at}] = status.pause.holds); None = blok yok.
    ladder: Mapping | None = None
    # DD-9 §8.1/§8.2: hesap modu sayaclari (status.exchange.account_mode; None = okunamadi) ve "borsa kipi beklenir"
    # (LIVE_BOTS/golge yoklamasi: durum dosyasi okunamasa da canli denetimler uretilir).
    acct_drift: int | None = None
    acct_unverified: int | None = None
    expect_exchange: bool = False
    # Acik pozisyonlarin (cift, varlik sinifi kripto|hisse|emtia); None = okunamadi / sinif bilinmiyor (denetim uretilmez).
    open_pairs: tuple[tuple[str, str], ...] | None = None


@dataclass(frozen=True)
class BanProbe:
    """DD-7 §6: bir ban dosyasi (`ban.<host>.json`). until None = bozuk/okunamayan dosya (corrupt=True). Suresi dolmus kayit da
    gelir; karar cekirdekte (`until > snap.now`)."""
    host: str
    until: datetime | None
    http: int | None
    source: str | None
    corrupt: bool = False


@dataclass(frozen=True)
class PauseProbe:
    """PAUSE dosyasi + denetim gunlugu (11 §9.2). holds: simdiki tutus nedenleri (None = okunamadi);
    last_ops: neden -> gunlukteki SON islem ("add" | "remove"); audit_ok: gunluk okunabildi mi (yok = bos, okunabilir)."""
    holds: tuple[str, ...] | None = None
    last_ops: Mapping[str, str] = field(default_factory=dict)
    audit_ok: bool = True


@dataclass(frozen=True)
class LedgerProbe:
    last_write_at: datetime | None = None
    spool_lines: int | None = None
    unledgered_ids: tuple[int, ...] | None = None
    orphan_ids: tuple[int, ...] | None = None
    schema_ok: bool | None = None
    has_active_params: bool | None = None
    spool_corrupt_lines: int | None = None    # DD-8 (E4): `<defter>.spool.corrupt.jsonl` satir sayisi (None = okunamadi)


@dataclass(frozen=True)
class ContainerProbe:
    state: str | None = None
    restart_count: int | None = None
    started_at: datetime | None = None
    oom_killed: bool | None = None


@dataclass(frozen=True)
class MarketProbe:
    """Piyasa verisi olcumleri (docs/saglik-spec.md Bolum 15). `*_state`: "ok" | "missing" | "unreadable"."""
    feed_status_state: str = "missing"
    feed_status_at: datetime | None = None            # feed-status.json `ts`
    db_state: str = "missing"                         # market.sqlite
    pairs: tuple[str, ...] = ()                       # yapilandirilmis cift listesi (bos = bilinmiyor)
    newest_bar_at: Mapping[str, datetime | None] = field(default_factory=dict)   # cift -> en yeni 1m (last) mum acilisi
    rules_count: int | None = None
    rules_fetched_at: datetime | None = None          # feed_meta.rules_fetched_at
    rules_missing: Mapping[str, int | None] = field(default_factory=dict)        # bot -> status counters.rules_missing
    pair_classes: Mapping[str, str] = field(default_factory=dict)                # cift -> varlik sinifi (bilinmeyen = kripto, 7/24)


@dataclass(frozen=True)
class MlProbe:
    """ML model paketi olcumleri (docs/saglik-spec.md Bolum 16.2). Olculemeyen alan None.
    `present`: status.json `ml` blogu var mi (None = status okunamadi). `file_*`: diskteki paketin meta alanlari
    (runner `scripts/health_run.py` hesaplar; bu modul paketi acmaz). `file_stale`: runner'in `ml_seen` karsilastirmasindan
    cikan "yeni dosya, eski veri" bayragi (16.4)."""
    present: bool | None = None
    mode: str | None = None
    state: str | None = None
    model_id: str | None = None
    expires_at: datetime | None = None
    error: str | None = None
    score_errors: int | None = None
    file_state: str = "not_configured"      # "ok" | "missing" | "unreadable" | "not_configured"
    file_model_id: str | None = None
    file_created_at: datetime | None = None
    file_expires_at: datetime | None = None
    file_data_hash: str | None = None
    file_train_end: datetime | None = None
    file_gate_passed: bool | None = None
    file_user_approved: bool | None = None
    file_stale: bool = False


@dataclass(frozen=True)
class DriftProbe:
    """Sapma izleyicisi cikti dosyasi olcumu (Bolum 16.6; WP-2). Saglik istatistik hesaplamaz."""
    file_state: str = "missing"             # "ok" | "missing" | "unreadable"
    generated_at: datetime | None = None
    overall: str | None = None
    rules_at_uyari: tuple[str, ...] = ()


@dataclass(frozen=True)
class HaberSinyalProbe:
    """Haber sinyali dosyasi (var/learner/sinyal/haber_sinyal.json) olcumu (ust lig HB1 girdisi). Saglik yalniz yasa bakar."""
    file_state: str = "missing"             # "ok" | "missing" | "unreadable"
    produced_at: datetime | None = None     # dosyadaki `uretim`
    valid_until: datetime | None = None     # uretim + gecerlilik (uretim + 3 sa tavanli)
    job_installed: bool = False             # sinyal isi kurulu: unit dosyasi var YA DA durum dosyasi (haber_sinyal_durum.json) var
    job_status: str | None = None           # durum dosyasindaki son tur sonucu: ok | anahtar_yok | api_hata | butce | hata
    job_since: datetime | None = None       # isin ilk zamani: durum dosyasi calisma.ilk_ms, yoksa unit dosyasi mtime


@dataclass(frozen=True)
class Dl1PaketProbe:
    """DL1 paketi (models/dl1/DL1@1h.json) olcumu (ust lig DL1 kolu girdisi). Saglik yalniz yasa/son kullanmaya bakar."""
    file_state: str = "missing"             # "ok" | "missing" | "unreadable" (bozuk / hash tutmuyor / kapi gecmemis / sema disi)
    created_at: datetime | None = None
    expires_at: datetime | None = None      # min(son_kullanma, olusturma + 45 gun)


@dataclass(frozen=True)
class HealthSnapshot:
    now: datetime
    timeframe_s: int | None = None
    api: Mapping[str, ApiProbe] = field(default_factory=dict)
    ledger: Mapping[str, LedgerProbe] = field(default_factory=dict)
    disk_free_bytes: int | None = None
    disk_total_bytes: int | None = None
    mem_available_bytes: int | None = None
    swap_total_bytes: int | None = None
    swap_used_bytes: int | None = None
    containers: Mapping[str, ContainerProbe] = field(default_factory=dict)
    prev_restart_counts: Mapping[str, int] = field(default_factory=dict)
    veto_file_mtime: datetime | None = None
    budget_state: str | None = None
    last_backup_at: datetime | None = None
    # Ek (spec 5.3 / 6.7): runner durum dosyasindan doldurur; yoksa varsayilan.
    consecutive_restart_runs: Mapping[str, int] = field(default_factory=dict)
    installed_at: datetime | None = None
    # Piyasa verisi alarmlari; None = bu denetimler kapali (MARKET_DB yapilandirilmamis).
    market: MarketProbe | None = None
    prev_rules_missing: Mapping[str, int] = field(default_factory=dict)
    # WP-B8: bot -> PauseProbe; onceki turda gorulen tutuslar (kayip tutus: kaybolan + gunlukte "remove" yok).
    pause: Mapping[str, PauseProbe] = field(default_factory=dict)
    prev_pause_holds: Mapping[str, tuple] = field(default_factory=dict)
    # Bolum 16: bot -> MlProbe; None = ML denetimi kapali. prev_ml_score_errors: onceki turun sayaci (runner state.json).
    ml: Mapping[str, MlProbe] | None = None
    prev_ml_score_errors: Mapping[str, int] = field(default_factory=dict)
    # Bolum 16.6 (WP-2 yer tutucusu): bot -> DriftProbe; None = yok.
    drift: Mapping[str, DriftProbe] | None = None
    # DD-7 §6: ban dosyasi yoklamasi; None = yoklanmadi (exchange_ban denetimi uretilmez), () = dosya yok.
    bans: tuple[BanProbe, ...] | None = None
    # DD-9 §8.1: bot -> onceki kosudaki (acct_drift, acct_unverified); None = onceki yok.
    prev_account_mode: Mapping[str, tuple[int, int]] | None = None
    # DD-9 §8.3: canli yol tutarliligi; None = LIVE_BOTS bos (denetim uretilmez), () = tutarli, aksi uyusmazlik kodlari.
    live_path_issues: tuple[str, ...] | None = None
    # Ust lig: haber sinyali dosyasi; None = yoklanmadi (haber_sinyal_age denetimi uretilmez).
    haber_sinyal: HaberSinyalProbe | None = None
    # Ust lig: DL1 paketi; None = yoklanmadi (dl1_paket_age denetimi uretilmez).
    dl1_paket: Dl1PaketProbe | None = None

    def __post_init__(self):
        if not isinstance(self.now, datetime) or self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("now tz-aware datetime olmali")


# ---------------------------------------------------------------------------------------------
# Yapilandirma
# ---------------------------------------------------------------------------------------------
def _pos(name, v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise ValueError(f"{name} sonlu ve pozitif sayi olmali")


@dataclass(frozen=True)
class HealthConfig:
    loop_warn_s: int = 120
    loop_crit_s: int = 300
    candle_warn_mult: float = 2.0
    candle_crit_mult: float = 3.0
    candle_margin_s: int = 120
    ledger_warn_mult: float = 1.0
    ledger_crit_mult: float = 2.0
    ledger_margin_s: int = 300
    disk_warn_bytes: int = 3 * GIB
    disk_crit_bytes: int = 1 * GIB
    mem_warn_bytes: int = 250 * MIB
    mem_crit_bytes: int = 120 * MIB
    swap_warn_ratio: float = 0.50
    swap_crit_ratio: float = 0.80
    restart_warn_delta: int = 1
    restart_crit_delta: int = 3
    restart_crit_runs: int = 3
    backup_warn_s: int = 26 * 3600
    backup_crit_s: int = 50 * 3600
    warmup_s: int = 600
    clock_skew_tolerance_s: int = 5
    require_bots: tuple[str, ...] = ("learner",)
    veto_max_age_s: int | None = None
    veto_strict: bool = False   # True: veto belgesi yok -> CRIT; yas > veto_max_age_s -> CRIT (WARN bandi yok)
    budget_check_enabled: bool = False
    # Uyari bastirma (Bolum 5)
    confirm_runs: int = 2
    crit_repeat_min: int = 180
    warn_repeat_min: int = 720
    multiple_threshold: int = 4
    # Piyasa verisi (Bolum 15)
    feed_status_crit_s: int = 180
    market_bar_crit_s: int = 300
    open_price_stale_s: int = 600      # acik pozisyonun cifti icin yeni 1m mum gelmeyeli (seans acikken) uyari esigi
    rules_warn_s: int = 24 * 3600
    # Canli/testnet (WP-B8): stopsuz pozisyon `naked_alarm_s`'i asarsa CRIT (11 §6.5: bos olmayan liste hemen CRIT => 0);
    # borsa okunamiyorsa `exchange_unreachable_s` sonra CRIT (11 §10 F1), once WARN.
    naked_alarm_s: float = 0.0
    exchange_unreachable_s: int = 60
    # ML model paketi (Bolum 16): sure uyari esikleri (gun; 7/3/1 ayri kodlar), mutlak veri yasi (gun; None = kapali)
    ml_warn_days: tuple = (7, 3, 1)
    ml_data_max_age_days: float | None = None
    # Sapma izleyicisi kancasi (16.6): WP-2 teslimine kadar kapali
    drift_max_age_s: int = 129600
    drift_check_enabled: bool = False

    def __post_init__(self):
        for n in ("loop_warn_s", "loop_crit_s", "candle_warn_mult", "candle_crit_mult", "candle_margin_s",
                  "ledger_warn_mult", "ledger_crit_mult", "ledger_margin_s", "disk_warn_bytes",
                  "disk_crit_bytes", "mem_warn_bytes", "mem_crit_bytes", "swap_warn_ratio",
                  "swap_crit_ratio", "restart_warn_delta", "restart_crit_delta", "restart_crit_runs",
                  "backup_warn_s", "backup_crit_s", "warmup_s", "confirm_runs", "crit_repeat_min",
                  "warn_repeat_min", "multiple_threshold", "feed_status_crit_s", "market_bar_crit_s", "open_price_stale_s", "rules_warn_s",
                  "exchange_unreachable_s", "drift_max_age_s"):
            _pos(n, getattr(self, n))
        w = self.ml_warn_days
        if not isinstance(w, tuple) or len(w) != 3:
            raise ValueError("ml_warn_days 3 elemanli demet olmali")
        for x in w:
            _pos("ml_warn_days", x)
        if not w[0] > w[1] > w[2]:
            raise ValueError("ml_warn_days azalan olmali")
        if self.ml_data_max_age_days is not None:
            _pos("ml_data_max_age_days", self.ml_data_max_age_days)
        if not isinstance(self.drift_check_enabled, bool):
            raise ValueError("drift_check_enabled bool olmali")
        v = self.naked_alarm_s
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise ValueError("naked_alarm_s sonlu ve >= 0 olmali")
        if self.clock_skew_tolerance_s is None or isinstance(self.clock_skew_tolerance_s, bool) \
                or not isinstance(self.clock_skew_tolerance_s, (int, float)) \
                or not math.isfinite(self.clock_skew_tolerance_s) or self.clock_skew_tolerance_s < 0:
            raise ValueError("clock_skew_tolerance_s >= 0 olmali")
        if not self.loop_warn_s < self.loop_crit_s:
            raise ValueError("loop_warn_s < loop_crit_s olmali")
        if not self.candle_warn_mult < self.candle_crit_mult:
            raise ValueError("candle_warn_mult < candle_crit_mult olmali")
        if not self.ledger_warn_mult < self.ledger_crit_mult:
            raise ValueError("ledger_warn_mult < ledger_crit_mult olmali")
        if not self.disk_crit_bytes < self.disk_warn_bytes:
            raise ValueError("disk_crit_bytes < disk_warn_bytes olmali")
        if not self.mem_crit_bytes < self.mem_warn_bytes:
            raise ValueError("mem_crit_bytes < mem_warn_bytes olmali")
        if not self.swap_warn_ratio < self.swap_crit_ratio:
            raise ValueError("swap_warn_ratio < swap_crit_ratio olmali")
        if not self.restart_warn_delta < self.restart_crit_delta:
            raise ValueError("restart_warn_delta < restart_crit_delta olmali")
        if not self.backup_warn_s < self.backup_crit_s:
            raise ValueError("backup_warn_s < backup_crit_s olmali")
        if self.veto_max_age_s is not None:
            _pos("veto_max_age_s", self.veto_max_age_s)
        if not isinstance(self.budget_check_enabled, bool):
            raise ValueError("budget_check_enabled bool olmali")
        if not isinstance(self.require_bots, tuple) or not self.require_bots \
                or not all(isinstance(b, str) and b for b in self.require_bots):
            raise ValueError("require_bots bos olmayan metin demeti olmali")


DEFAULT_CFG = HealthConfig()


# ---------------------------------------------------------------------------------------------
# Kontroller
# ---------------------------------------------------------------------------------------------
class _Skew(Exception):
    pass


def _res(name, status, code, detail, value=None, threshold=None) -> CheckResult:
    return CheckResult(name, status, code, detail,
                       None if value is None else float(value),
                       None if threshold is None else float(threshold))


def _unknown(name, code, detail) -> CheckResult:
    return CheckResult(name, Status.UNKNOWN, code, detail, None, None)


def _age_s(now: datetime, ts: datetime, cfg: HealthConfig) -> float:
    if not isinstance(ts, datetime) or ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("zaman damgasi tz-aware datetime degil")
    age = (now - ts).total_seconds()
    if age < -cfg.clock_skew_tolerance_s:
        raise _Skew()
    return max(age, 0.0)


def _graded(name, age, warn, crit, ok_code, bad_code, label) -> CheckResult:
    if age > crit:
        return _res(name, Status.CRIT, bad_code, f"{label} {age:.0f} sn, kritik esik {crit:.0f} sn", age, crit)
    if age > warn:
        return _res(name, Status.WARN, bad_code, f"{label} {age:.0f} sn, uyari esigi {warn:.0f} sn", age, warn)
    return _res(name, Status.OK, ok_code, f"{label} {age:.0f} sn", age, warn)


def _container_key(snap: HealthSnapshot, bot: str) -> str:
    for k in (f"trader-{bot}", bot):
        if k in snap.containers:
            return k
    return f"trader-{bot}"


def _in_warmup(snap: HealthSnapshot, bot: str, cfg: HealthConfig) -> bool:
    c = snap.containers.get(_container_key(snap, bot))
    if c is None or not isinstance(c.started_at, datetime) or c.started_at.tzinfo is None:
        return False
    since = (snap.now - c.started_at).total_seconds()
    return 0 <= since <= cfg.warmup_s


def _warm(r: CheckResult, warm: bool) -> CheckResult:
    if warm and r.status is Status.CRIT:
        return replace(r, status=Status.WARN, code=r.code + "_warmup",
                       detail=r.detail + " (isinma suresi icinde)")
    return r


def _c_api(snap, bot, cfg):
    name = f"api_reachable:{bot}"
    p = snap.api[bot].ping_ok
    if p is None:
        return _unknown(name, "api_unknown", f"{bot} API durumu olculemedi")
    if p is True:
        return _res(name, Status.OK, "ok", f"{bot} API yanit veriyor")
    return _res(name, Status.CRIT, "api_unreachable", f"{bot} API yanit vermiyor")


def _c_loop(snap, bot, cfg):
    name = f"bot_loop_age:{bot}"
    t = snap.api[bot].last_process_at
    if t is None:
        return _unknown(name, "loop_unknown", f"{bot} dongu zamani olculemedi")
    try:
        age = _age_s(snap.now, t, cfg)
    except _Skew:
        return _unknown(name, "clock_skew", f"{bot} dongu zamani gelecekte; saat uyumsuz")
    r = _graded(name, age, cfg.loop_warn_s, cfg.loop_crit_s, "ok", "stale_loop", f"{bot} son dongu yasi")
    return _warm(r, _in_warmup(snap, bot, cfg))


def _c_candle(snap, bot, cfg):
    name = f"candle_age:{bot}"
    t = snap.api[bot].last_candle_open
    T = snap.timeframe_s
    if t is None or T is None or isinstance(T, bool) or not isinstance(T, int) or T <= 0:
        return _unknown(name, "candle_unknown", f"{bot} mum zamani/zaman dilimi olculemedi")
    try:
        age = _age_s(snap.now, t, cfg)
    except _Skew:
        return _unknown(name, "clock_skew", f"{bot} mum zamani gelecekte; saat uyumsuz")
    warn = cfg.candle_warn_mult * T + cfg.candle_margin_s
    crit = cfg.candle_crit_mult * T + cfg.candle_margin_s
    r = _graded(name, age, warn, crit, "ok", "stale_candle", f"{bot} son mum yasi")
    return _warm(r, _in_warmup(snap, bot, cfg))


def _c_ledger_age(snap, bot, cfg):
    name = f"ledger_write_age:{bot}"
    t = snap.ledger[bot].last_write_at
    T = snap.timeframe_s
    if t is None or T is None or isinstance(T, bool) or not isinstance(T, int) or T <= 0:
        return _unknown(name, "ledger_age_unknown", f"{bot} defter yazma zamani olculemedi")
    try:
        age = _age_s(snap.now, t, cfg)
    except _Skew:
        return _unknown(name, "clock_skew", f"{bot} defter zamani gelecekte; saat uyumsuz")
    warn = cfg.ledger_warn_mult * T + cfg.ledger_margin_s
    crit = cfg.ledger_crit_mult * T + cfg.ledger_margin_s
    r = _graded(name, age, warn, crit, "ok", "ledger_write_stale", f"{bot} defter son yazma yasi")
    return _warm(r, _in_warmup(snap, bot, cfg))


def _c_spool_corrupt(snap, bot, cfg):
    """DD-8 (E4): ayri denetim (ledger_gate'in erken donusleri maskeleyemez; isinma yumusatmaz). Dosya bosalana/adi degisene
    kadar CRIT; motor dosyayi silmez/kisaltmaz."""
    name = f"spool_corrupt:{bot}"
    n = snap.ledger[bot].spool_corrupt_lines
    if n is None:
        return _unknown(name, "spool_corrupt_unreadable", f"{bot} bozuk spool dosyasi okunamadi")
    if n > 0:
        return _res(name, Status.CRIT, "spool_corrupt", f"{bot} deftere yazilamayan {n} bozuk kayit var", n, 0)
    return _res(name, Status.OK, "ok", f"{bot} bozuk spool kaydi yok", 0, 0)


def _c_gate(snap, bot, cfg):
    name = f"ledger_gate:{bot}"
    p = snap.ledger[bot]
    if p.spool_lines is not None and p.spool_lines > 0:
        return _res(name, Status.CRIT, "spool_pending", f"{bot} spool'da {p.spool_lines} satir var; kapi kapali olurdu",
                    p.spool_lines, 0)
    if p.unledgered_ids:
        ids = ",".join(str(i) for i in list(p.unledgered_ids)[:5])
        return _res(name, Status.CRIT, "unledgered_trades",
                    f"{bot} defterde girisi olmayan acik islem var: {ids}", len(p.unledgered_ids), 0)
    if p.has_active_params is False:
        return _res(name, Status.CRIT, "no_active_params", f"{bot} etkin parametre yok")
    if p.schema_ok is False:
        return _res(name, Status.CRIT, "schema", f"{bot} defter semasi beklenenden farkli")
    a = snap.api.get(bot)
    gc = None if a is None else a.gate_code
    if gc is not None and gc not in ("ok", "kill"):
        return _res(name, Status.CRIT, "engine_gate_closed", f"{bot} motor giris kapisi kapali: {gc}")
    if p.spool_lines is None or p.unledgered_ids is None or p.has_active_params is None or p.schema_ok is None:
        return _unknown(name, "gate_unknown", f"{bot} defter kapisi durumu olculemedi")
    if gc == "kill" or (a is not None and a.kill is True):
        return _res(name, Status.WARN, "engine_kill", f"{bot} kill dosyasi etkin; girisler kapali (operator karari)")
    if a is not None and a.ledger_errors:
        return _res(name, Status.WARN, "ledger_errors", f"{bot} motor surec basindan beri {a.ledger_errors} defter hatasi saydi",
                    a.ledger_errors, 0)
    if p.orphan_ids:
        ids = ",".join(str(i) for i in list(p.orphan_ids)[:5])
        return _res(name, Status.WARN, "orphan_decisions",
                    f"{bot} yeniden baslatma sirasinda yarim kalan {len(p.orphan_ids)} giris karari var (islemleri etkilemez; "
                    f"motor acilista duzeltir): {ids}", len(p.orphan_ids), 0)
    return _res(name, Status.OK, "ok", f"{bot} defter kapisi acik olurdu")


def _c_disk(snap, cfg):
    v = snap.disk_free_bytes
    if v is None:
        return _unknown("disk_free", "disk_unknown", "bos disk alani olculemedi")
    if v < cfg.disk_crit_bytes:
        return _res("disk_free", Status.CRIT, "disk_low", f"bos alan {v / GIB:.2f} GiB, kritik", v, cfg.disk_crit_bytes)
    if v < cfg.disk_warn_bytes:
        return _res("disk_free", Status.WARN, "disk_low", f"bos alan {v / GIB:.2f} GiB, dusuk", v, cfg.disk_warn_bytes)
    return _res("disk_free", Status.OK, "ok", f"bos alan {v / GIB:.2f} GiB", v, cfg.disk_warn_bytes)


def _c_mem(snap, cfg):
    v = snap.mem_available_bytes
    if v is None:
        return _unknown("memory", "memory_unknown", "kullanilabilir bellek olculemedi")
    if v < cfg.mem_crit_bytes:
        return _res("memory", Status.CRIT, "memory_low", f"kullanilabilir bellek {v / MIB:.0f} MiB, kritik", v,
                    cfg.mem_crit_bytes)
    if v < cfg.mem_warn_bytes:
        return _res("memory", Status.WARN, "memory_low", f"kullanilabilir bellek {v / MIB:.0f} MiB, dusuk", v,
                    cfg.mem_warn_bytes)
    return _res("memory", Status.OK, "ok", f"kullanilabilir bellek {v / MIB:.0f} MiB", v, cfg.mem_warn_bytes)


def _c_swap(snap, cfg):
    tot, used = snap.swap_total_bytes, snap.swap_used_bytes
    if tot is None or used is None:
        return _unknown("swap", "swap_unknown", "swap durumu olculemedi")
    if tot == 0:
        return _res("swap", Status.SKIPPED, "no_swap", "swap tanimli degil")
    if tot < 0 or used < 0:
        return _unknown("swap", "swap_unknown", "swap degerleri gecersiz")
    ratio = used / tot
    if ratio > cfg.swap_crit_ratio:
        return _res("swap", Status.CRIT, "swap_high", f"swap kullanimi {ratio:.2f}, kritik", ratio, cfg.swap_crit_ratio)
    if ratio > cfg.swap_warn_ratio:
        return _res("swap", Status.WARN, "swap_high", f"swap kullanimi {ratio:.2f}, yuksek", ratio, cfg.swap_warn_ratio)
    return _res("swap", Status.OK, "ok", f"swap kullanimi {ratio:.2f}", ratio, cfg.swap_warn_ratio)


def _c_container(snap, key, cfg):
    name = f"container_restarts:{key}"
    c = snap.containers.get(key)
    if c is None or c.state is None or c.restart_count is None:
        return _unknown(name, "container_unknown", f"{key} konteyner durumu olculemedi")
    prev = snap.prev_restart_counts.get(key)
    delta = 0 if prev is None else max(c.restart_count - prev, 0)
    runs = int(snap.consecutive_restart_runs.get(key, 0)) + (1 if delta >= 1 else 0)
    if c.oom_killed is True:
        return _res(name, Status.CRIT, "oom_killed", f"{key} bellek yetmezliginden oldurulmus", delta,
                    cfg.restart_crit_delta)
    if c.state != "running":
        return _res(name, Status.CRIT, "container_not_running", f"{key} durumu '{c.state}'", delta,
                    cfg.restart_crit_delta)
    if delta >= cfg.restart_crit_delta:
        return _res(name, Status.CRIT, "restart_loop", f"{key} son turdan beri {delta} yeniden baslatma", delta,
                    cfg.restart_crit_delta)
    if delta >= 1 and runs >= cfg.restart_crit_runs:
        return _res(name, Status.CRIT, "restart_loop", f"{key} {runs} tur ust uste yeniden basladi", delta,
                    cfg.restart_crit_runs)
    if delta >= cfg.restart_warn_delta:
        return _res(name, Status.WARN, "container_restarted", f"{key} son turdan beri {delta} yeniden baslatma",
                    delta, cfg.restart_warn_delta)
    return _res(name, Status.OK, "ok", f"{key} calisiyor, yeniden baslatma yok", delta, cfg.restart_warn_delta)


def _c_backup(snap, cfg):
    t = snap.last_backup_at
    if t is None:
        inst = snap.installed_at
        if inst is not None:
            try:
                if _age_s(snap.now, inst, cfg) <= cfg.backup_warn_s:
                    return _res("backup_age", Status.SKIPPED, "no_backup_yet", "ilk yedek henuz alinmadi (kurulum gunu)")
            except (_Skew, ValueError):
                pass
        return _unknown("backup_age", "no_backup", "dogrulanmis yedek zamani bilinmiyor")
    try:
        age = _age_s(snap.now, t, cfg)
    except _Skew:
        return _unknown("backup_age", "clock_skew", "yedek zamani gelecekte; saat uyumsuz")
    return _graded("backup_age", age, cfg.backup_warn_s, cfg.backup_crit_s, "ok", "backup_stale", "son yedek yasi")


def _c_veto(snap, cfg):
    mx = cfg.veto_max_age_s
    if mx is None:
        return _res("veto_file_age", Status.SKIPPED, "placeholder", "veto dosyasi denetimi kapali")
    t = snap.veto_file_mtime
    if t is None:
        if cfg.veto_strict:
            return _res("veto_file_age", Status.CRIT, "veto_missing", "veto belgesi yok/bayat: girisler kapali")
        return _unknown("veto_file_age", "veto_unknown", "veto dosyasi yok ya da okunamadi")
    try:
        age = _age_s(snap.now, t, cfg)
    except _Skew:
        return _unknown("veto_file_age", "clock_skew", "veto dosya zamani gelecekte; saat uyumsuz")
    if cfg.veto_strict:
        if age > mx:
            return _res("veto_file_age", Status.CRIT, "veto_stale",
                        f"veto belgesi yok/bayat: girisler kapali (yas {age:.0f} sn, esik {mx:.0f} sn)", age, mx)
        return _res("veto_file_age", Status.OK, "ok", f"veto dosyasi yasi {age:.0f} sn", age, mx)
    return _graded("veto_file_age", age, mx, 3 * mx, "ok", "veto_stale", "veto dosyasi yasi")


def _c_budget(snap, cfg):
    if not cfg.budget_check_enabled:
        return _res("budget_status", Status.SKIPPED, "placeholder", "butce denetimi kapali")
    s = snap.budget_state
    if s == "ok":
        return _res("budget_status", Status.OK, "ok", "butce durumu iyi")
    if s == "warn":
        return _res("budget_status", Status.WARN, "budget_warn", "butce uyari duzeyinde")
    if s == "exhausted":
        return _res("budget_status", Status.CRIT, "budget_exhausted", "butce tukendi")
    return _unknown("budget_status", "budget_unknown", "butce durumu olculemedi ya da taninmiyor")


def _c_feed_status(snap, cfg):
    m = snap.market
    name = "feed_status_age"
    if m.feed_status_state == "missing":
        return _res(name, Status.CRIT, "feed_status_missing", "feed-status.json yok; feed calismiyor olabilir")
    if m.feed_status_state != "ok" or m.feed_status_at is None:
        return _unknown(name, "feed_status_unknown", "feed-status.json okunamadi/bozuk")
    try:
        age = _age_s(snap.now, m.feed_status_at, cfg)
    except _Skew:
        return _unknown(name, "clock_skew", "feed durum zamani gelecekte; saat uyumsuz")
    if age > cfg.feed_status_crit_s:
        return _res(name, Status.CRIT, "feed_status_stale",
                    f"feed durum dosyasi {age:.0f} sn eski, kritik esik {cfg.feed_status_crit_s} sn", age,
                    cfg.feed_status_crit_s)
    return _res(name, Status.OK, "ok", f"feed durum dosyasi {age:.0f} sn", age, cfg.feed_status_crit_s)


def _db_problem(name, m):
    if m.db_state == "missing":
        return _res(name, Status.CRIT, "market_db_missing", "market.sqlite yok; feed hic veri yazmamis")
    if m.db_state != "ok":
        return _unknown(name, "market_db_unreadable", "market.sqlite okunamadi")
    return None


def _c_market_bars(snap, cfg):
    m = snap.market
    name = "market_bar_age"
    bad = _db_problem(name, m)
    if bad:
        return bad
    if not m.pairs:
        return _unknown(name, "pairs_unknown", "yapilandirilmis cift listesi bilinmiyor")
    from trader_core.arm_time import session_tag   # noqa: PLC0415
    stale, worst = [], 0.0
    once = snap.now - timedelta(seconds=cfg.market_bar_crit_s)
    for p in m.pairs:
        cls = m.pair_classes.get(p) or m.pair_classes.get(_canon(p))
        if cls:
            try:   # _c_open_price ile ayni kural: seans kapali (ya da esik oncesi kapali) cift icin mum beklenmez
                if session_tag(cls, snap.now) != "open" or session_tag(cls, once) != "open":
                    continue
            except ValueError:
                continue
        t = m.newest_bar_at.get(p)
        if t is None:
            stale.append(f"{p}: mum yok")
            worst = max(worst, float("inf"))
            continue
        age = _age_s(snap.now, t, cfg)
        worst = max(worst, age)
        if age > cfg.market_bar_crit_s:
            stale.append(f"{p}: {age:.0f} sn")
    if stale:
        v = None if worst == float("inf") else worst
        return _res(name, Status.CRIT, "market_bars_stale",
                    "1m mum bayat (esik %d sn): %s" % (cfg.market_bar_crit_s, "; ".join(stale[:5])), v,
                    cfg.market_bar_crit_s)
    return _res(name, Status.OK, "ok", f"tum ciftlerde 1m mum taze (en eski {worst:.0f} sn)", worst,
                cfg.market_bar_crit_s)


def _canon(p: str) -> str:
    return str(p).strip().upper().split(":", 1)[0]


def _c_open_price(snap, bot, cfg):
    """Acik pozisyonun cifti icin fiyat (1m mum) gelmiyor mu? Paper'da stop yalniz gelen mumda islenir (brokers/paper.py advance);
    mum yoksa stop beklemede kalir. Seans kapaliyken (hisse/emtia hafta sonu ve seans disi) mum gelmemesi NORMALDIR: uyari yok.
    Esik oncesi de seans aciksa (yeni acilis) sayilir; boylece acilisin ilk dakikalarinda sahte uyari cikmaz."""
    from trader_core.arm_time import session_tag   # noqa: PLC0415
    name = f"acik_pozisyon_fiyat_bayat:{bot}"
    a = snap.api[bot]
    m = snap.market
    if not a.open_pairs:
        return _res(name, Status.OK, "ok", "acik pozisyon yok")
    newest = {_canon(k): v for k, v in m.newest_bar_at.items()}
    esik = cfg.open_price_stale_s
    once = snap.now - timedelta(seconds=esik)
    bayat, kapali = [], 0
    for pair, cls in a.open_pairs:
        try:
            if session_tag(cls, snap.now) != "open" or session_tag(cls, once) != "open":
                kapali += 1
                continue
        except ValueError:
            continue
        t = newest.get(_canon(pair))
        try:
            age = float("inf") if t is None else _age_s(snap.now, t, cfg)
        except _Skew:
            continue
        if age > esik:
            bayat.append(pair)
    if not bayat:
        return _res(name, Status.OK, "ok", "acik pozisyonlarin fiyati geliyor" + (f" ({kapali} cift seans disi)" if kapali else ""))
    coins = ", ".join(dict.fromkeys(p.split("/")[0].upper() for p in bayat))
    return _res(name, Status.WARN, "open_price_stale",
                f"{coins} için fiyat gelmiyor; açık pozisyonun stopu fiyat gelince işler", None, esik)


def _c_rules_count(snap, cfg):
    m = snap.market
    name = "rules_coverage"
    bad = _db_problem(name, m)
    if bad:
        return bad
    if not m.pairs or m.rules_count is None:
        return _unknown(name, "rules_unknown", "kural satir sayisi ya da cift listesi bilinmiyor")
    if m.rules_count < len(m.pairs):
        return _res(name, Status.CRIT, "rules_incomplete",
                    f"kural satiri {m.rules_count} < yapilandirilmis cift {len(m.pairs)}", m.rules_count, len(m.pairs))
    return _res(name, Status.OK, "ok", f"kural satiri {m.rules_count}/{len(m.pairs)}", m.rules_count, len(m.pairs))


def _c_rules_age(snap, cfg):
    m = snap.market
    name = "rules_age"
    bad = _db_problem(name, m)
    if bad:
        return bad
    if m.rules_fetched_at is None:
        return _unknown(name, "rules_age_unknown", "rules_fetched_at yok (kural hic cekilmemis)")
    try:
        age = _age_s(snap.now, m.rules_fetched_at, cfg)
    except _Skew:
        return _unknown(name, "clock_skew", "rules_fetched_at gelecekte; saat uyumsuz")
    if age > cfg.rules_warn_s:
        return _res(name, Status.WARN, "rules_stale", f"kurallar {age / 3600:.1f} sa once cekildi, esik "
                    f"{cfg.rules_warn_s / 3600:.0f} sa", age, cfg.rules_warn_s)
    return _res(name, Status.OK, "ok", f"kurallar {age / 3600:.1f} sa once cekildi", age, cfg.rules_warn_s)


def _c_rules_missing(snap, bot, cfg):
    name = f"rules_missing:{bot}"
    cur = snap.market.rules_missing.get(bot)
    if cur is None:
        return _unknown(name, "rules_missing_unknown", f"{bot} rules_missing sayaci okunamadi")
    prev = snap.prev_rules_missing.get(bot)
    if prev is not None and cur > prev:
        return _res(name, Status.CRIT, "rules_missing_increase",
                    f"{bot} rules_missing {prev} -> {cur} (artti)", cur - prev, 0)
    return _res(name, Status.OK, "ok", f"{bot} rules_missing {cur} (artis yok)", cur, 0)


_ML_RANK = {Status.CRIT: 3, Status.UNKNOWN: 2, Status.WARN: 1, Status.OK: 0}
ML_FILE_FUTURE_TOL_S = 300


def _c_ml(snap, bot, cfg):
    """ml_package:<bot> (Bolum 16.3). Satirlar sirayla; en agir durum sonuc, esitlikte tablo sirasi."""
    name = f"ml_package:{bot}"
    p = snap.ml[bot]
    now = snap.now
    if p.present is None:
        return _unknown(name, "ml_status_unreadable", "status.json okunamadi; ML durumu bilinmiyor")
    if p.present is False or p.mode == "off":
        return _res(name, Status.SKIPPED, "ml_off", "ML filtresi kapali")
    found: list[tuple[Status, str, str]] = []
    mode, state = p.mode, p.state
    value = None
    valid = mode in ("shadow", "active") and state in ("ok", "expired", "no_model")
    if mode == "active" and state == "expired":
        found.append((Status.CRIT, "ml_expired", "model suresi doldu; yeni girisler kapali"))
    elif mode == "active" and state == "no_model":
        found.append((Status.CRIT, "ml_no_model", f"model yuklenemedi; yeni girisler kapali (hata: {p.error or 'bilinmiyor'})"))
    elif mode == "shadow" and state in ("expired", "no_model"):
        found.append((Status.WARN, "ml_shadow_down", f"golge model calismiyor ({state})"))
    elif valid and state == "ok":
        if not isinstance(p.expires_at, datetime) or p.expires_at.tzinfo is None:
            found.append((Status.UNKNOWN, "ml_status_invalid", "model suresi (expires_at) yok ya da gecersiz"))
        else:
            kalan = (p.expires_at - now).total_seconds() / 86400.0
            value = kalan
            d7, d3, d1 = cfg.ml_warn_days
            tag = "kip=shadow; " if mode == "shadow" else ""
            for lim, code in ((d1, "ml_expiring_1d"), (d3, "ml_expiring_3d"), (d7, "ml_expiring_7d")):
                if kalan <= lim:
                    found.append((Status.WARN, code, f"{tag}model suresi {kalan:.2f} gun sonra doluyor"))
                    break
    if not valid:
        found.append((Status.UNKNOWN, "ml_status_invalid", "ml blogunda bilinmeyen kip/durum"))
    note = ""
    if p.file_state == "not_configured":
        note = "paket yolu bilinmiyor"
    else:
        fok = p.file_state == "ok"
        bozuk = (p.file_state in ("missing", "unreadable")
                 or (fok and (p.file_model_id is None or not isinstance(p.file_created_at, datetime)
                              or not isinstance(p.file_expires_at, datetime)))
                 or (fok and isinstance(p.file_created_at, datetime) and p.file_created_at.tzinfo is not None
                     and (p.file_created_at - now).total_seconds() > ML_FILE_FUTURE_TOL_S))
        if fok and not bozuk and p.file_model_id != p.model_id:
            gecerli = (now < p.file_expires_at and p.file_gate_passed is True
                       and (mode != "active" or p.file_user_approved is True))
            if gecerli:
                found.append((Status.WARN, "ml_restart_needed", "diskte yeni paket var; motor eskisini kullaniyor"))
        if fok and not bozuk:
            stale = bool(p.file_stale)
            lim = cfg.ml_data_max_age_days
            if lim is not None and isinstance(p.file_train_end, datetime) \
                    and (p.file_created_at - p.file_train_end).total_seconds() / 86400.0 > lim:
                stale = True
            if stale:
                found.append((Status.WARN, "ml_stale_data", "yeni paket eski veriyle uretilmis gorunuyor"))
        if bozuk:
            found.append((Status.WARN, "ml_file_invalid", f"model dosyasi gecersiz ({p.file_state})"))
    sc, prev = p.score_errors, snap.prev_ml_score_errors.get(bot)
    if sc is None:
        note = (note + "; " if note else "") + "puanlama hata sayaç okunamadı"
    elif isinstance(prev, int) and not isinstance(prev, bool) and sc > prev:
        found.append((Status.WARN, "ml_score_errors", f"puanlama hatalari {prev} -> {sc}"))
    if not found:
        return _res(name, Status.OK, "ok", "ML modeli normal" + (f" ({note})" if note else ""), value)
    worst = max(found, key=lambda f: _ML_RANK[f[0]])
    detail = "; ".join(f"{c}: {d}" for _s, c, d in found) + (f" ({note})" if note else "")
    return _res(name, worst[0], worst[1], detail, value)


HABER_SINYAL_ILK_SAAT_S = 2 * 3600     # isin ilk zamanindan sonra bu sure dosya yoksa bile yalniz bilgi (INFO)


def _c_haber_sinyal(snap, cfg):
    """haber_sinyal_age: HB1 kolunun girdisi. Taze -> OK; bayat (gecerlilik doldu) / bozuk -> WARN (yalniz HB1 girisleri durur);
    uretici durumu anahtar_yok -> WARN (sessiz olu kol); dosya yok: isi kurulu degil ya da isin ilk zamanindan (durum dosyasi / unit mtime)
    sonraki ilk 2 saatteyse INFO (Status.OK, kod `haber_sinyal_info`), aksi WARN."""
    name = "haber_sinyal_age"
    p = snap.haber_sinyal
    if p.job_installed and p.job_status == "anahtar_yok":
        return _res(name, Status.WARN, "haber_anahtar_yok", "haber anahtari yok, haber kolu sinyal goremiyor; HB1 girisleri durdu")
    if p.file_state == "unreadable":
        return _res(name, Status.WARN, "haber_sinyal_bozuk", "haber sinyali dosyasi okunamadi/sema disi; HB1 girisleri durdu")
    if p.file_state != "ok" or not isinstance(p.produced_at, datetime) or p.produced_at.tzinfo is None:
        ilk = (isinstance(p.job_since, datetime) and p.job_since.tzinfo is not None
               and (snap.now - p.job_since).total_seconds() < HABER_SINYAL_ILK_SAAT_S)
        if not p.job_installed or ilk:
            return _res(name, Status.OK, "haber_sinyal_info", "INFO: haber sinyali dosyasi yok (sinyal isi kurulu degil ya da ilk saatler)")
        return _res(name, Status.WARN, "haber_sinyal_yok", "haber sinyali dosyasi yok; HB1 girisleri durdu")
    try:
        age = _age_s(snap.now, p.produced_at, cfg)
    except _Skew:
        return _unknown(name, "clock_skew", "haber sinyali zamani gelecekte; saat uyumsuz")
    lim = p.valid_until
    gecerlilik = (lim - p.produced_at).total_seconds() if isinstance(lim, datetime) and lim.tzinfo is not None else 3 * 3600
    if age > gecerlilik:
        ek = f" (uretici son durum: {p.job_status})" if p.job_status not in (None, "ok") else ""
        return _res(name, Status.WARN, "haber_sinyal_bayat",
                    f"haber sinyali yasi {age:.0f} sn, gecerlilik {gecerlilik:.0f} sn{ek}; HB1 girisleri durdu", age, gecerlilik)
    return _res(name, Status.OK, "ok", f"haber sinyali yasi {age:.0f} sn", age, gecerlilik)


DL1_YAKLASIYOR_GUN = 7       # son kullanmaya bundan az kaldiysa WARN (gunluk egitim bu surede yenilemeliydi)


def _c_dl1_paket(snap, cfg):
    """dl1_paket_age: DL1 kolunun girdisi. Yok -> INFO (Status.OK, kod `dl1_paket_info`: "DL1 paketi henuz yok"); bozuk / eski (son kullanma gecti) /
    son kullanmaya < 7 gun -> WARN (yalniz DL1 girisleri durur ya da duracak); aksi OK (yas satiri)."""
    name = "dl1_paket_age"
    p = snap.dl1_paket
    if p.file_state == "unreadable":
        return _res(name, Status.WARN, "dl1_paket_bozuk", "DL1 paketi okunamadi/hash tutmuyor/kapi gecmemis; DL1 girisleri durdu")
    if p.file_state != "ok" or not isinstance(p.created_at, datetime) or p.created_at.tzinfo is None \
            or not isinstance(p.expires_at, datetime) or p.expires_at.tzinfo is None:
        return _res(name, Status.OK, "dl1_paket_info", "INFO: DL1 paketi henuz yok")
    yas = (snap.now - p.created_at).total_seconds()
    kalan = (p.expires_at - snap.now).total_seconds()
    if kalan <= 0:
        return _res(name, Status.WARN, "dl1_paket_eski", f"DL1 paketi yasi {yas / 86400:.1f} gun, son kullanma gecti; DL1 girisleri durdu", yas, kalan)
    if kalan < DL1_YAKLASIYOR_GUN * 86400:
        return _res(name, Status.WARN, "dl1_paket_yaklasiyor",
                    f"DL1 paketi yasi {yas / 86400:.1f} gun, son kullanmaya {kalan / 86400:.1f} gun kaldi; yenilenmezse DL1 girisleri duracak", yas, kalan)
    return _res(name, Status.OK, "ok", f"DL1 paketi yasi {yas / 86400:.1f} gun, son kullanmaya {kalan / 86400:.1f} gun", yas, kalan)


def _c_drift(snap, bot, cfg):
    """drift_monitor:<bot> (Bolum 16.6). Bilincli istisna: hicbir kosulda CRIT/UNKNOWN uretmez."""
    name = f"drift_monitor:{bot}"
    try:
        if not cfg.drift_check_enabled or snap.drift is None:
            return _res(name, Status.SKIPPED, "placeholder", "sapma izleyicisi kapali")
        d = snap.drift.get(bot)
        if d is None or d.file_state == "missing":
            return _res(name, Status.WARN, "drift_missing", "drift.json yok")
        if d.file_state != "ok" or not isinstance(d.generated_at, datetime) or d.generated_at.tzinfo is None:
            return _res(name, Status.WARN, "drift_unreadable", "drift.json okunamadi/bozuk")
        age = (snap.now - d.generated_at).total_seconds()
        if age < -cfg.clock_skew_tolerance_s:
            return _res(name, Status.WARN, "drift_unreadable", "drift.json zamani gelecekte")
        if age > cfg.drift_max_age_s:
            return _res(name, Status.WARN, "drift_stale",
                        f"drift.json {age:.0f} sn eski, esik {cfg.drift_max_age_s} sn", age, cfg.drift_max_age_s)
        if d.overall == "UYARI":
            kurallar = ", ".join(str(x) for x in d.rules_at_uyari) or "-"
            return _res(name, Status.WARN, "drift_alert", f"sapma izleyicisi UYARI; kurallar: {kurallar}")
        if d.overall in ("OK", "IZLE", "YETERSIZ"):
            return _res(name, Status.OK, "ok", f"sapma izleyicisi {d.overall}")
        return _res(name, Status.WARN, "drift_unreadable", "drift.json genel durumu taninmiyor")
    except Exception:  # noqa: BLE001 - UNKNOWN uretilmez (16.6)
        return _res(name, Status.WARN, "drift_unreadable", "drift.json degerlendirilemedi")


def _live_mode(a: ApiProbe) -> bool:
    return a.has_exchange or a.mode in ("testnet", "live") or a.expect_exchange


def _acct_increase(cur: int, prev) -> int:
    """DD-9 §8.1: onceki yok -> 0; surec yeniden baslamis (simdiki < onceki) -> simdiki; aksi fark."""
    if not isinstance(prev, int) or isinstance(prev, bool):
        return 0
    if cur < prev:
        return cur
    return cur - prev


def _c_account_mode(snap, bot, cfg):
    """account_mode:<bot> (DD-9 §8.1): drift artisi CRIT, dogrulanamama artisi (yasak kaynaklilar haric) WARN, bilinmeyen UNKNOWN."""
    name = f"account_mode:{bot}"
    a = snap.api[bot]
    if a.acct_drift is None or a.acct_unverified is None:
        return _unknown(name, "account_mode_unknown", f"{bot} hesap modu sayaclari (exchange.account_mode) okunamadi")
    prev = (snap.prev_account_mode or {}).get(bot)
    pd = pu = None
    if isinstance(prev, (tuple, list)) and len(prev) == 2:
        pd, pu = prev
    d_inc = _acct_increase(a.acct_drift, pd)
    u_inc = _acct_increase(a.acct_unverified, pu)
    if d_inc >= 1:
        return _res(name, Status.CRIT, "account_mode_drift",
                    f"{bot} hesap ayari (kaldirac/marjin tipi) botun ayarindan farkli: +{d_inc}", d_inc, 0)
    if u_inc >= 1:
        return _res(name, Status.WARN, "account_mode_unverified",
                    f"{bot} hesap ayari dogrulanamadi, giris atlandi: +{u_inc}", u_inc, 0)
    return _res(name, Status.OK, "ok", f"{bot} hesap ayari tutarli")


def _c_live_paths(snap, cfg):
    """live_paths (DD-9 §8.3): canli bot yollari yapilandirmayla tutarli mi."""
    issues = snap.live_path_issues
    if issues is None:
        return None
    if not issues:
        return _res("live_paths", Status.OK, "ok", "canli bot yollari tutarli")
    return _res("live_paths", Status.CRIT, "live_paths_mismatch", "canli bot yollari tutarsiz: " + ", ".join(issues[:8]),
                len(issues), 0)


def _c_naked(snap, bot, cfg):
    """Acik canli/testnet pozisyon stopsuz (11 §6.5): status.exchange.naked bos degilse (sure > esik) hemen CRIT.
    status.open_positions'ta stop'u olmayan pozisyon da (canli kipte) ayni alarmdir."""
    name = f"naked_position:{bot}"
    a = snap.api[bot]
    rows = a.naked
    if rows is None:
        return _unknown(name, "naked_unknown", f"{bot} stopsuz pozisyon bilgisi (exchange.naked) okunamadi")
    bad = [r for r in rows if r[2] > cfg.naked_alarm_s]
    if bad:
        txt = ", ".join(f"{r[1]}#{r[0]} {r[2]:.0f} sn" for r in bad[:5])
        return _res(name, Status.CRIT, "naked_position", f"{bot} stopsuz acik pozisyon: {txt}",
                    max(r[2] for r in bad), cfg.naked_alarm_s)
    if a.unprotected_ids:
        ids = ",".join(str(i) for i in a.unprotected_ids[:5])
        return _res(name, Status.CRIT, "naked_position", f"{bot} status'ta stop'u olmayan acik pozisyon: {ids}",
                    len(a.unprotected_ids), 0)
    return _res(name, Status.OK, "ok", f"{bot} stopsuz pozisyon yok")


def _c_exchange(snap, bot, cfg):
    name = f"exchange_reachable:{bot}"
    a = snap.api[bot]
    r = a.exchange_reachable
    if r is None:
        return _unknown(name, "exchange_unknown", f"{bot} borsa erisilebilirligi (exchange.reachable) okunamadi")
    if r:
        return _res(name, Status.OK, "ok", f"{bot} borsa erisilebilir")
    t = a.exchange_last_sync
    age = None
    if t is not None:
        try:
            age = _age_s(snap.now, t, cfg)
        except _Skew:
            age = None
    if age is None:
        return _res(name, Status.CRIT, "exchange_unreachable", f"{bot} borsaya ulasilamiyor; son basarili esitleme bilinmiyor")
    if age > cfg.exchange_unreachable_s:
        return _res(name, Status.CRIT, "exchange_unreachable",
                    f"{bot} borsaya {age:.0f} sn'dir ulasilamiyor (esik {cfg.exchange_unreachable_s} sn)", age,
                    cfg.exchange_unreachable_s)
    return _res(name, Status.WARN, "exchange_unreachable",
                f"{bot} borsaya ulasilamiyor ({age:.0f} sn)", age, cfg.exchange_unreachable_s)


def _c_exchange_ban(snap, cfg):
    """DD-7 §6: borsa yasak penceresi. Acik pozisyon = herhangi bir `has_exchange` yoklamasinda open_trade_ids bos degil ya da
    None (bilinmiyor = var say). Oncelik: CRIT exchange_ban_open_positions > WARN exchange_ban > WARN exchange_ban_file_corrupt > OK."""
    name = "exchange_ban"
    bans = snap.bans or ()
    active = [b for b in bans if b.until is not None and b.until > snap.now]
    if active:
        top = max(active, key=lambda b: b.until)
        left = (top.until - snap.now).total_seconds()
        mins = max(1, int(-(-left // 60)))
        info = f"host={top.host} kalan_dk={mins} http={top.http} kaynak={top.source}"
        open_pos = any((p.has_exchange or p.expect_exchange) and (p.open_trade_ids is None or len(p.open_trade_ids) > 0)
                       for p in snap.api.values())       # DD-9 §8.2: durum dosyasi okunamasa da canli beklenen bot'ta bilinmeyen = var
        if open_pos:
            return _res(name, Status.CRIT, "exchange_ban_open_positions", f"borsa engeli suruyor, acik pozisyon var: {info}", left)
        return _res(name, Status.WARN, "exchange_ban", f"borsa engeli suruyor: {info}", left)
    bad = [b for b in bans if b.corrupt]
    if bad:
        return _res(name, Status.WARN, "exchange_ban_file_corrupt",
                    f"ban dosyasi bozuk/okunamiyor: host={bad[0].host}")
    return _res(name, Status.OK, "ok", "borsa engeli yok")


def _c_pause_audit(snap, bot, cfg):
    """11 §9.2: (a) tutus var ama gunlukte o neden icin SON islem "add" degil -> kimse eklemedi (CRIT);
    (b) onceki turda vardi, simdi yok ve gunlukte "remove" yok -> dosya elle silindi/kayboldu (CRIT, bir tur)."""
    name = f"pause_audit:{bot}"
    p = snap.pause[bot]
    if p.holds is None:
        return _unknown(name, "pause_unknown", f"{bot} PAUSE dosyasi okunamadi")
    if not p.audit_ok:
        return _unknown(name, "pause_audit_unreadable", f"{bot} pause denetim gunlugu okunamadi")
    unaudited = [h for h in p.holds if p.last_ops.get(h) != "add"]
    if unaudited:
        return _res(name, Status.CRIT, "pause_hold_unaudited",
                    f"{bot} duraklatma tutusu denetim gunlugunde 'add' satiri olmadan duruyor: {', '.join(unaudited[:5])}",
                    len(unaudited), 0)
    prev = snap.prev_pause_holds.get(bot) or ()
    lost = [h for h in prev if h not in p.holds and p.last_ops.get(h) != "remove"]
    if lost:
        return _res(name, Status.CRIT, "pause_hold_lost",
                    f"{bot} duraklatma tutusu denetim gunlugunde 'remove' olmadan kayboldu: {', '.join(lost[:5])}",
                    len(lost), 0)
    return _res(name, Status.OK, "ok", f"{bot} duraklatma tutuslari denetim gunluguyle tutarli ({len(p.holds)})")


# 12 §11: risk kademe denetimi alarmlari (status.json risk_ladder blogundan). Zaman esikleri alarm zamanlamasidir (risk sabiti degil).
LADDER_MISMATCH_CRIT_S = 30 * 60
LADDER_STEP_DOWN_WINDOW_S = 24 * 3600
LADDER_HOLD_STALE_S = 10 * 60
_LADDER_RANK = {Status.CRIT: 2, Status.WARN: 1, Status.OK: 0}


def _z(s):
    return _from_iso(s) if isinstance(s, str) else None


def _num_s(x, nd=2) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "?"


_LADDER_WARMUP_OK = frozenset({"ladder_missing", "capital_missing", "ladder_invalid", "equity_unreadable"})


def _c_ladder(snap, bot, cfg):
    """19 Kasim: motor yeni basladiysa (isinma, cfg.warmup_s) kademe blogu henuz yazilmamis/ilklenmemis olabilir; bu
    gecici durum alarm degildir (guncelleme sirasinda yanlis 'Risk kademesi sorunlu' CRIT'i). Isinma bitince aynen denetlenir.
    Gercek kademe olaylari (taban, -%20 durma, aktarim uyusmazligi, basamak inisi) isinmada da bildirilir."""
    r = _c_ladder_inner(snap, bot, cfg)
    if r.code in _LADDER_WARMUP_OK and _in_warmup(snap, bot, cfg):
        return _res(r.name, Status.OK, "ok", f"{bot} kademe denetimi: motor isiniyor ({r.code} gecici)")
    return r


def _c_ladder_inner(snap, bot, cfg):
    """12 §11 tablosu: en agir tek sonuc. Blok yoksa yalniz testnet/live'da CRIT `ladder_missing`."""
    name = f"risk_ladder:{bot}"
    a = snap.api[bot]
    b = a.ladder
    if not isinstance(b, Mapping):
        if a.mode in ("live", "testnet"):
            return _res(name, Status.CRIT, "ladder_missing",
                        f"{bot} kademe denetimi calismiyor (status.json'da risk_ladder blogu yok)")
        return _res(name, Status.OK, "ok", f"{bot} kademe blogu yok (kagit/bilinmeyen kip)")
    now = snap.now
    state = b.get("state")
    gate = b.get("gate_code")
    enforce = bool(b.get("enforce"))
    n_open = len(a.open_trade_ids) if a.open_trade_ids is not None else "?"
    found: list[CheckResult] = []

    def add(status, code, detail, value=None, threshold=None):
        found.append(_res(name, status, code, detail, value, threshold))

    if state == "floor":
        add(Status.CRIT, "capital_floor",
            f"{bot} son taban: ozsermaye {_num_s(b.get('equity'))}, yatirilan {_num_s(b.get('dep_net'))}; girisler kapali; "
            "hepsini kapatmak icin /hepsini_kapat; yeniden baslama yazili kararla (sunucuda)")
    if state == "review":
        add(Status.CRIT, "drawdown_review",
            f"{bot} -%20 durma: taban {_num_s(b.get('base'))}, ozsermaye {_num_s(b.get('equity'))}, acik pozisyon {n_open}; "
            "/hepsini_kapat secenegi; mentor degerlendirmesi <= 3 gun; devam /kademe_devam")
    if enforce and (state in ("uninitialized", "invalid") or gate in ("capital_missing", "ladder_invalid", "equity_unreadable")):
        code = {"uninitialized": "capital_missing", "invalid": "ladder_invalid"}.get(state) or gate
        add(Status.CRIT, code, f"{bot} kademe kapisi: {code}; girisler kapali; sunucuda bakilmali")
    if gate == "capital_mismatch":
        since = _z(b.get("gate_since"))
        old = since is not None and (now - since).total_seconds() > LADDER_MISMATCH_CRIT_S
        add(Status.CRIT if old else Status.WARN, "capital_mismatch",
            f"{bot} borsadaki aktarim ile sermaye kaydi eslesmiyor")
    if gate == "capital_unverified":
        add(Status.WARN, "capital_unverified", f"{bot} aktarim kayitlari okunamiyor")
    if b.get("near") is True and state == "ok":
        add(Status.WARN, "ladder_near",
            f"{bot} durma esigine yaklasildi (ozsermaye {_num_s(b.get('equity'))} <= tabanin %85'i)")
    ld = _z(b.get("last_down_at"))
    if state == "ok" and ld is not None and 0 <= (now - ld).total_seconds() <= LADDER_STEP_DOWN_WINDOW_S:
        add(Status.WARN, "ladder_step_down", f"{bot} basamak indi: {b.get('step_name')}")
    if isinstance(b.get("pause_holds"), (list, tuple)) and any(
            isinstance(h, Mapping) and h.get("reason") == "capital_latch" for h in b["pause_holds"]):
        add(Status.WARN, "capital_latch",
            f"{bot} ana para kilidi (capital_latch): ozsermaye {_num_s(b.get('equity'))} <= yatirilanin %85'i "
            f"({_num_s(b.get('dep_net'))}); yeni girisler kapali; acmak icin Telegram /devam")
    if state == "ok":
        for h in b.get("pause_holds") or ():
            if isinstance(h, Mapping) and h.get("reason") == "drawdown_review":
                t = _z(h.get("at"))
                if t is not None and (now - t).total_seconds() > LADDER_HOLD_STALE_S:
                    add(Status.WARN, "ladder_hold_stale",
                        f"{bot} devam yarim kaldi (kademe ok ama drawdown_review tutusu duruyor); /kademe_devam yinelenmeli")
                    break
    w = b.get("would")
    if isinstance(w, Mapping):
        wt = _z(w.get("at"))
        if wt is not None and 0 <= (now - wt).total_seconds() <= LADDER_STEP_DOWN_WINDOW_S:
            add(Status.WARN, "ladder_would", f"{bot} kagitta: canli olsaydi {w.get('kind')}")
    if not found:
        return _res(name, Status.OK, "ok", f"{bot} kademe denetimi normal")
    return max(found, key=lambda r: _LADDER_RANK.get(r.status, 0))      # esitlikte tablo sirasi (ilk bulunan)


def _safe(name, fn, *args) -> CheckResult:
    try:
        r = fn(*args)
        if not isinstance(r, CheckResult):
            raise TypeError("kontrol sonucu gecersiz")
        return r
    except Exception:  # noqa: BLE001 - fail-closed: hicbir istisna sizmaz
        return _unknown(name, "internal_error", "kontrol hesaplanirken beklenmeyen hata")


def combine(results, cfg: HealthConfig = DEFAULT_CFG) -> Status:
    """Birlestirme kurali (spec Bolum 2); `missing_check` ekleme `evaluate` icindedir."""
    rs = [r.status for r in results if r.status is not Status.SKIPPED]
    if not rs:
        return Status.UNKNOWN
    for s in (Status.CRIT, Status.UNKNOWN, Status.WARN):
        if s in rs:
            return s
    return Status.OK


def evaluate(snap: HealthSnapshot, cfg: HealthConfig = DEFAULT_CFG) -> HealthReport:
    results: list[CheckResult] = []
    bots = list(dict.fromkeys(list(cfg.require_bots) + list(snap.api) + list(snap.ledger) + list(snap.pause)))
    for bot in bots:
        if bot in snap.api:
            results.append(_safe(f"api_reachable:{bot}", _c_api, snap, bot, cfg))
            results.append(_safe(f"bot_loop_age:{bot}", _c_loop, snap, bot, cfg))
            results.append(_safe(f"candle_age:{bot}", _c_candle, snap, bot, cfg))
            if snap.api[bot].open_pairs is not None and snap.market is not None and snap.market.db_state == "ok":
                results.append(_safe(f"acik_pozisyon_fiyat_bayat:{bot}", _c_open_price, snap, bot, cfg))
            if _live_mode(snap.api[bot]):
                results.append(_safe(f"naked_position:{bot}", _c_naked, snap, bot, cfg))
                results.append(_safe(f"exchange_reachable:{bot}", _c_exchange, snap, bot, cfg))
            if _live_mode(snap.api[bot]):
                results.append(_safe(f"account_mode:{bot}", _c_account_mode, snap, bot, cfg))
            if snap.api[bot].ladder is not None or snap.api[bot].mode in ("live", "testnet"):
                results.append(_safe(f"risk_ladder:{bot}", _c_ladder, snap, bot, cfg))
        if bot in snap.pause:
            results.append(_safe(f"pause_audit:{bot}", _c_pause_audit, snap, bot, cfg))
        if bot in snap.ledger:
            results.append(_safe(f"ledger_write_age:{bot}", _c_ledger_age, snap, bot, cfg))
            results.append(_safe(f"ledger_gate:{bot}", _c_gate, snap, bot, cfg))
            results.append(_safe(f"spool_corrupt:{bot}", _c_spool_corrupt, snap, bot, cfg))
    if snap.bans is not None:
        results.append(_safe("exchange_ban", _c_exchange_ban, snap, cfg))
    if snap.live_path_issues is not None:
        results.append(_safe("live_paths", _c_live_paths, snap, cfg))
    results.append(_safe("disk_free", _c_disk, snap, cfg))
    results.append(_safe("memory", _c_mem, snap, cfg))
    results.append(_safe("swap", _c_swap, snap, cfg))
    keys = list(snap.containers)
    for bot in cfg.require_bots:
        k = _container_key(snap, bot)
        if k not in keys:
            keys.append(k)
    seen_keys = set()
    for k in keys:
        if k in seen_keys or k not in snap.containers:
            continue
        seen_keys.add(k)
        results.append(_safe(f"container_restarts:{k}", _c_container, snap, k, cfg))
    results.append(_safe("backup_age", _c_backup, snap, cfg))
    results.append(_safe("veto_file_age", _c_veto, snap, cfg))
    results.append(_safe("budget_status", _c_budget, snap, cfg))

    if snap.market is not None:
        results.append(_safe("feed_status_age", _c_feed_status, snap, cfg))
        results.append(_safe("market_bar_age", _c_market_bars, snap, cfg))
        results.append(_safe("rules_coverage", _c_rules_count, snap, cfg))
        results.append(_safe("rules_age", _c_rules_age, snap, cfg))
        for bot in cfg.require_bots:
            results.append(_safe(f"rules_missing:{bot}", _c_rules_missing, snap, bot, cfg))

    if snap.haber_sinyal is not None:
        results.append(_safe("haber_sinyal_age", _c_haber_sinyal, snap, cfg))
    if snap.dl1_paket is not None:
        results.append(_safe("dl1_paket_age", _c_dl1_paket, snap, cfg))
    if snap.ml is not None:
        for bot in snap.ml:
            results.append(_safe(f"ml_package:{bot}", _c_ml, snap, bot, cfg))
    for bot in dict.fromkeys(list(cfg.require_bots) + list(snap.drift or {})):
        ap = snap.api.get(bot)
        if ap is not None and (ap.expect_exchange or ap.mode == "live"):
            continue                        # DD-9 §8.4: canli bot icin sapma izleyicisi denetimi uretilmez (canli yol destegi ayri paket)
        results.append(_c_drift(snap, bot, cfg))

    have = {r.name for r in results}
    required = []
    for base in REQUIRED_CHECKS:
        if base in _PER_BOT:
            for bot in cfg.require_bots:
                key = _container_key(snap, bot) if base == "container_restarts" else bot
                required.append(f"{base}:{key}")
        else:
            required.append(base)
    for n in required:
        if n not in have:
            results.append(_unknown(n, "missing_check", "zorunlu kontrol sonucu yok"))
            have.add(n)
    overall = combine(results, cfg)
    return HealthReport(snap.now, tuple(results), overall, overall in (Status.OK, Status.WARN))


def should_send_ok(report: HealthReport) -> bool:
    """Nabiz karari: yalnizca OK/WARN iken `ok()` gider (spec Bolum 4)."""
    return report.overall in (Status.OK, Status.WARN) and report.healthy


# ---------------------------------------------------------------------------------------------
# Uyari yolu
# ---------------------------------------------------------------------------------------------
IMMEDIATE_CODES = frozenset({"account_mode_drift", "live_paths_mismatch", "disk_low", "unledgered_trades", "spool_pending", "spool_corrupt", "schema", "oom_killed",
                             "rules_missing_increase", "naked_position", "pause_hold_unaudited",
                             "pause_hold_lost", "capital_floor", "drawdown_review", "ladder_missing",
                             "capital_missing", "ladder_invalid", "equity_unreadable", "ml_expired", "ml_no_model",
                             "exchange_ban_open_positions"})


# Kirmizi (CRIT/UNKNOWN) cift dogrulama: hicbir kirmizi alarm tek basarisiz kontrolle gitmez; ilk gorulen tur "sari"
# (izlenir, mesaj yok), ust uste 2. basarisiz turda kirmizi gider. Emin degilsek sari: tek seferlik okuma hatasi uyari uretmez.
# IMMEDIATE_CODES artik yalniz WARN-disi eski ayrim icin tutulur; kirmizi icin alt sinir RED_CONFIRM_RUNS'tir.
RED_CONFIRM_RUNS = 2
# Tek istisna: canli/testnet para guvenligi kodlari (DD-7/8/9 belirtimleri: ilk turda uyar). Bunlar motorun kendi yapisal
# durum alanindan okunur (olcum gurultusu degil); kagit modda hic uretilmez.
RED_SINGLE_OK = frozenset({"naked_position", "exchange_ban_open_positions", "account_mode_drift", "live_paths_mismatch"})

# Kurulum sonrasi sessizlik penceresinde (QUIET_MINUTES) YALNIZ bu kodlar iletilir (olumcul: islem/para/veri butunlugu ya da
# motor tamamen duruyor); digerleri tutulur ve pencere bitince tek ozetle bildirilir.
FATAL_CODES = frozenset({"naked_position", "account_mode_drift", "unledgered_trades", "schema", "oom_killed",
                         "container_not_running", "restart_loop", "api_unreachable", "spool_corrupt",
                         "exchange_ban_open_positions", "capital_floor", "live_paths_mismatch"})
QUIET_MINUTES = 15


# WARN olup ilk turda uyaran kodlar (taban her tur guncellendigi icin uyari tek tur gorunur; confirm_runs bekleyemez).
IMMEDIATE_WARN_CODES = frozenset({"account_mode_unverified", "ml_score_errors", "exchange_ban", "exchange_ban_file_corrupt"})


@dataclass(frozen=True)
class Alert:
    level: Status
    code: str
    title: str
    body: str
    fingerprint: str
    created_at: datetime


class Notifier(Protocol):
    def send(self, alert: Alert) -> bool: ...


class LogNotifier:
    """stderr/journal'a yazar; her zaman True doner."""

    def __init__(self, logger: logging.Logger | None = None):
        self._log = logger or log

    def send(self, alert: Alert) -> bool:
        try:
            lvl = logging.WARNING if alert.level in (Status.WARN, Status.OK) else logging.CRITICAL
            self._log.log(lvl, "ALERT %s %s: %s", alert.level.value, alert.title, alert.body)
        except Exception:  # noqa: BLE001
            pass
        return True


class NullNotifier:
    """Testler: cagrilari listeler."""

    def __init__(self, result: bool = True):
        self.sent: list[Alert] = []
        self.result = result

    def send(self, alert: Alert) -> bool:
        self.sent.append(alert)
        return self.result


def empty_state() -> dict:
    return {"schema": 1, "restart_counts": {}, "fingerprints": {}, "last_overall": None, "last_run_at": None}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _from_iso(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_maintenance(text: str | None, now: datetime) -> datetime | None:
    """Bakim dosyasi icerigi (ISO UTC). Gelecekte ve en cok 4 saat ileride ise o zaman, aksi None."""
    if not isinstance(text, str):
        return None
    s = text.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None
    dt = dt.astimezone(timezone.utc)
    if dt <= now or dt - now > timedelta(hours=4):
        return None
    return dt


def _cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


# Kullanıcıya giden uyarı metinleri (sade Türkçe). Anahtar: kontrol adının ":bot" ekinden önceki kısmı.
# Değer: (sorun cümlesi, düzeldi cümlesi, ne anlama geliyor). Sorun/düzeldi cümleleri <= 68 karakter (başlık 80 sınırı).
_HEALTH_TR: dict[str, tuple[str, str, str]] = {
    "api_reachable": ("Motor yanıt vermiyor", "Motor yeniden yanıt veriyor",
                      "Bot çalışmıyor olabilir; yeni işlem açılmaz, açık pozisyonları kontrol et."),
    "bot_loop_age": ("Motor döngüsü durmuş görünüyor", "Motor döngüsü yeniden işliyor",
                     "Motor takılmış olabilir; yeni işlemler bekletilebilir."),
    "candle_age": ("Piyasa mumları güncel değil", "Piyasa mumları yeniden güncel",
                   "Güncel fiyat verisi yok; yeni işlem kararı verilemez."),
    "ledger_write_age": ("Kayıt defterine uzun süredir yazılmadı", "Kayıt defterine yeniden yazılıyor",
                         "Kayıtlar gecikmiş olabilir; panoyu kontrol et."),
    "ledger_gate": ("İşlem kayıt sistemi giriş kapısı kapalı", "İşlem kayıt sistemi yeniden açıldı",
                    "Kayıt sistemi hazır olmadığı için yeni işlemler bekletiliyor."),
    "spool_corrupt": ("Deftere yazılamayan bozuk kayıt var", "Bozuk kayıt dosyası temizlendi",
                      "Bazı işlem/karar kayıtları okunamadığı için deftere yazılamadı; dosya incelenip taşınmalı."),
    "disk_free": ("Sunucuda boş disk alanı azaldı", "Boş disk alanı yeniden yeterli",
                  "Disk dolarsa kayıtlar yazılamaz ve bot durabilir; yer açılmalı."),
    "memory": ("Sunucuda bellek azaldı", "Bellek durumu yeniden normal",
               "Bellek biterse bot kapanabilir; sunucuyu kontrol et."),
    "swap": ("Sunucu yavaşlıyor (takas belleği yüksek)", "Sunucu takas belleği yeniden normal",
             "Sunucu yavaşlayabilir; bellek durumunu kontrol et."),
    "container_restarts": ("Bot sık sık yeniden başlıyor", "Bot yeniden kararlı çalışıyor",
                           "Bot kendini toparlıyor ama sorun sürebilir; kayıtlara bak."),
    "backup_age": ("Yedek alınmıyor ya da çok eski", "Yedekleme yeniden düzenli",
                   "Veri kaybı riskine karşı yedeğin alındığından emin ol."),
    "veto_file_age": ("Veto (yapay zekâ filtresi) güncel değil — yeni işlemler bekletiliyor",
                      "Veto (yapay zekâ filtresi) yeniden güncel",
                      "Yön filtresi güncellenene kadar yeni işlem açılmaz; açık pozisyonlar korunur."),
    "budget_status": ("Yapay zekâ bütçesi azaldı", "Yapay zekâ bütçesi yeniden yeterli",
                      "Bütçe biterse yapay zekâ filtresi çalışmaz ve yeni işlemler durur."),
    "feed_status_age": ("Fiyat akışı durmuş görünüyor", "Fiyat akışı yeniden çalışıyor",
                        "Güncel fiyat gelmiyor; yeni işlemler bekletilir."),
    "acik_pozisyon_fiyat_bayat": ("Açık pozisyonun fiyatı gelmiyor", "Açık pozisyonun fiyatı yeniden geliyor",
                                  "Stop, fiyat gelince işlenir; seans kapalıyken bu uyarı çıkmaz."),
    "market_bar_age": ("Piyasa verisi güncel değil", "Piyasa verisi yeniden güncel",
                       "Eski veriyle işlem açılmaz; yeni işlemler bekletilir."),
    "rules_coverage": ("Borsa kuralları eksik", "Borsa kuralları yeniden tam",
                       "Bazı paritelerde kural yok; o pariteler için işlem açılmaz."),
    "rules_age": ("Borsa kuralları eski", "Borsa kuralları yeniden güncel",
                  "Kurallar tazelenmeli; acil değil ama uzarsa işlem engellenebilir."),
    "rules_missing": ("Bazı paritelerin borsa kuralı alınamadı", "Borsa kuralı eksikliği düzeldi",
                      "Etkilenen pariteler için yeni işlem açılmaz."),
    "naked_position": ("Stop'u olmayan açık pozisyon var!", "Stopsuz pozisyon kalmadı",
                       "Pozisyon korumasız; hemen kontrol et ya da /kapat kullan."),
    "exchange_reachable": ("Borsaya ulaşılamıyor", "Borsa bağlantısı yeniden sağlandı",
                           "Emir gönderilemeyebilir; açık pozisyonları borsadan kontrol et."),
    "exchange_ban": ("Borsa geçici engel koydu", "Borsa engeli kalktı",
                     "Bot engel bitene kadar emir göndermez; engel kendiliğinden kalkar."),
    "pause_audit": ("Duraklatma kaydı tutarsız", "Duraklatma kaydı yeniden tutarlı",
                    "Yeni işlemler güvenlik için kapalı tutulur; kayıtlar incelenmeli."),
    "risk_ladder": ("Risk kademesi sorunlu", "Risk kademesi yeniden normal",
                    "Sermaye koruma kuralları devrede; yeni işlemler kısıtlanabilir."),
    "ml_package": ("Yapay zekâ modeli sorunlu", "Yapay zekâ modeli yeniden normal",
                   "Modelin durumu için günlük rapora bak."),
    "haber_sinyal_age": ("Haber sinyali güncel değil", "Haber sinyali yeniden güncel",
                         "Haber kolunun (HB1) yeni girişleri durur; diğer kollar ve açık pozisyonlar etkilenmez."),
    "dl1_paket_age": ("DL1 modeli güncel değil", "DL1 modeli yeniden güncel",
                      "Derin öğrenme kolunun (DL1) yeni girişleri durur ya da duracak; diğer kollar ve açık pozisyonlar etkilenmez."),
    "drift_monitor": ("Bot beklenenden farklı davranıyor", "Bot yeniden beklendiği gibi davranıyor",
                      "Bot durdurulmadı; ayrıntı günlük raporda. İnceleme gerekir."),
}
_ML_YENILENDI = "Model yenilendi"
_DRIFT_YOK = ("Davranış izleyicisi çalışmıyor", "Davranış izleyicisi yeniden çalışıyor",
              "Günlük karşılaştırma yapılamıyor; işlemler etkilenmez.")
_HEALTH_TR_CODE: dict[str, tuple[str, str, str]] = {
    "ml_expired": ("Modelin süresi doldu — yeni işlemler durdu", "Model yenilendi, yeni işlemler yeniden açık",
                   "Model 21 günden eski olduğu için bot yeni işlem açmıyor; açık pozisyonlar korunuyor. "
                   "Model yenilenip motor yeniden başlatılmalı."),
    "ml_no_model": ("Model yüklenemedi — yeni işlemler durdu", "Model yüklendi, yeni işlemler yeniden açık",
                    "Model dosyası yok, geçersiz ya da süresi dolmuş; bot yeni işlem açmıyor, açık pozisyonlar korunuyor."),
    "ml_shadow_down": ("Gölgedeki model çalışmıyor", "Gölgedeki model yeniden çalışıyor",
                       "İşlemler etkilenmiyor; yalnız modelin izleme kaydı duruyor."),
    "ml_expiring_7d": ("Modelin süresi 7 gün içinde doluyor", _ML_YENILENDI,
                       "Yenilenmezse süre dolduğunda yeni işlemler durur."),
    "ml_expiring_3d": ("Modelin süresi 3 gün içinde doluyor", _ML_YENILENDI,
                       "Yenilenmezse süre dolduğunda yeni işlemler durur."),
    "ml_expiring_1d": ("Modelin süresi yarın doluyor!", _ML_YENILENDI,
                       "Bugün yenilenmezse yeni işlemler durur."),
    "ml_restart_needed": ("Yeni model hazır ama devrede değil", "Yeni model devrede",
                          "Motor yeniden başlatılana kadar eski model kullanılır."),
    "ml_stale_data": ("Yeni model eski veriyle üretilmiş", "Model güncel veriyle yenilendi",
                      "Model dosyası yeni ama içindeki veri ilerlememiş; veri toplama ve eğitim hattı kontrol edilmeli."),
    "ml_file_invalid": ("Model dosyası okunamıyor", "Model dosyası yeniden okunuyor",
                        "Sıradaki yeniden başlatmada model yüklenemeyebilir."),
    "ml_score_errors": ("Model bazı fırsatları puanlayamıyor", "Model yeniden puanlıyor",
                        "Puanlanamayan fırsatlar alınmaz; işlem sayısı düşebilir."),
    "drift_missing": _DRIFT_YOK,
    "drift_stale": _DRIFT_YOK,
    "drift_unreadable": _DRIFT_YOK,
    "budget_exhausted": ("Yapay zekâ bütçesi tükendi — yeni işlemler durdu", "Yapay zekâ bütçesi yeniden yeterli",
                         "Bütçe yenilenene kadar yapay zekâ filtresi çalışmaz; yeni işlem açılmaz."),
    "api_unreachable": ("Motor yanıt vermiyor", "Motor yeniden yanıt veriyor",
                        "Bot çalışmıyor olabilir; yeni işlem açılmaz, açık pozisyonları kontrol et."),
}
_BAN_CRIT_SENTENCE = ("Bot engel bitene kadar emir gönderemez. Borsadaki zarar-kes emirleri yerinde durur. "
                      "Gerekirse pozisyonu Binance uygulamasından elle kapatın.")
_HEALTH_TR_CODE.update({
    "exchange_ban_open_positions": ("Borsa geçici engel koydu, açık pozisyon var", "Borsa engeli kalktı", _BAN_CRIT_SENTENCE),
    "exchange_ban": ("Borsa geçici engel koydu", "Borsa engeli kalktı",
                     "Bot engel bitene kadar emir göndermez; açık pozisyon yok. Engel kendiliğinden kalkar."),
    "exchange_ban_file_corrupt": ("Borsa engel kaydı bozuk", "Borsa engel kaydı yeniden okunuyor",
                                  "Engel dosyası okunamıyor; bot güvenlik için bir süre emir göndermeyebilir."),
})
_HEALTH_TR_CODE.update({
    "account_mode_drift": ("Hesap ayarı değişmiş, yeni işlem açılmadı", "Hesap ayarı yeniden doğru",
                           "Kaldıraç ya da marjin tipi botun ayarından farklı; Binance'te elle değiştirildiyse eski haline getirin."),
    "account_mode_unverified": ("Hesap ayarı doğrulanamadı, bir giriş atlandı", "Hesap ayarı yeniden doğrulanıyor",
                                "Bot giriş öncesi hesap ayarını borsadan okuyamadı; güvenlik için o giriş gönderilmedi."),
    "account_mode_unknown": ("Hesap ayarı bilgisi okunamıyor", "Hesap ayarı bilgisi yeniden okunuyor",
                             "Botun durum dosyasında hesap ayarı sayaçları yok; motor ve sağlık sürümleri kontrol edilmeli."),
    "live_paths_mismatch": ("Canlı bot ayar yolları tutarsız", "Canlı bot ayar yolları düzeldi",
                            "Telegram ya da sağlık yanlış dosyaya bakıyor olabilir; sunucuda kurulum yeniden çalıştırılmalı."),
})
_HEALTH_TR.update({
    "account_mode": _HEALTH_TR_CODE["account_mode_unknown"],
    "live_paths": _HEALTH_TR_CODE["live_paths_mismatch"],
})
_BAN_DETAIL = re.compile(r"host=(\S+) kalan_dk=(\d+)")
_HEALTH_TR_GENERIC = ("Bir sistem kontrolü sorunlu", "Sistem kontrolü yeniden normal",
                      "Ayrıntı için panoya ya da kayıtlara bak.")


def _health_tr(name: str, code: str, detail: str = "") -> tuple[str, str, str]:
    """(sorun, düzeldi, anlamı) - ham kontrol adı/kodu kullanıcıya sızdırılmaz.
    `detail` yalnız gölge kipteki süre uyarısının anlam cümlesini ayırmak için okunur."""
    base, _, _suffix = name.partition(":")
    sorun, duzeldi, anlam = _HEALTH_TR_CODE.get(code) or _HEALTH_TR.get(base) or _HEALTH_TR_GENERIC
    if base == "exchange_ban" and code in ("exchange_ban_open_positions", "exchange_ban"):
        m = _BAN_DETAIL.search(detail or "")
        if m:
            anlam = f"Borsa: {m.group(1)}, kalan yaklaşık {m.group(2)} dk. {anlam}"
    if base == "acik_pozisyon_fiyat_bayat" and "için fiyat gelmiyor" in (detail or ""):
        anlam = detail
    if base == "ml_package" and code.startswith("ml_expiring_") and "kip=shadow" in detail:
        anlam = "Yenilenmezse gölge izleme durur; işlemler etkilenmez."
    return sorun, duzeldi, anlam


def plan_alerts(report: HealthReport, state: Mapping | None, now: datetime,
                cfg: HealthConfig = DEFAULT_CFG, *, maintenance_until: datetime | None = None):
    """Saf: (alerts, new_state). `new_state` uyarilarin iletildigini varsayar; iletilemeyenler icin
    `revert_failed_alerts` kullanilir. Bakim penceresinde uyari listesi bos doner (nabiz etkilenmez)."""
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("now tz-aware olmali")
    st = state if isinstance(state, Mapping) else {}
    prev_fp = st.get("fingerprints") if isinstance(st.get("fingerprints"), Mapping) else {}
    maint = (maintenance_until is not None and now < maintenance_until
             and maintenance_until - now <= timedelta(hours=4))

    new_fp: dict[str, dict] = {}
    due: list[tuple[CheckResult, str]] = []
    failing = report.failing()
    for r in failing:
        fp = f"{r.name}|{r.code}"
        old = prev_fp.get(fp) if isinstance(prev_fp.get(fp), Mapping) else None
        ent = {
            "first_seen": old.get("first_seen") if old and old.get("first_seen") else _iso(now),
            "consecutive": (int(old.get("consecutive", 0)) if old else 0) + 1,
            "last_alert_at": old.get("last_alert_at") if old else None,
            "alerted": bool(old.get("alerted")) if old else False,
            "level": r.status.value,
        }
        new_fp[fp] = ent
        if r.status is Status.WARN:
            need = 1 if r.code in IMMEDIATE_WARN_CODES else cfg.confirm_runs
            repeat = cfg.warn_repeat_min
        else:
            need = 1 if r.code in IMMEDIATE_CODES else cfg.confirm_runs
            if r.code not in RED_SINGLE_OK:
                need = max(need, RED_CONFIRM_RUNS)
            repeat = cfg.crit_repeat_min
        is_due = False
        if not ent["alerted"]:
            is_due = ent["consecutive"] >= need
        else:
            last = _from_iso(ent["last_alert_at"])
            is_due = last is None or (now - last) >= timedelta(minutes=repeat)
        if is_due:
            due.append((r, fp))

    alerts: list[Alert] = []
    if not maint:
        if len(failing) >= cfg.multiple_threshold and due:
            descs = list(dict.fromkeys(_health_tr(r.name, r.code)[0] for r in failing[:5]))
            names = "; ".join(descs)
            worst = Status.CRIT if any(r.status is Status.CRIT for r in failing) else (
                Status.UNKNOWN if any(r.status is Status.UNKNOWN for r in failing) else Status.WARN)
            mark = "🚨 Sorun" if worst is Status.CRIT else "⚠️ Dikkat"
            alerts.append(Alert(worst, "multiple", _cut(f"{mark}: {len(failing)} sağlık kontrolü sorunlu", 80),
                                _cut(f"Sorunlar (ilk 5): {names}", 500), "multiple|multiple", now))
        else:
            for r, fp in due:
                sorun, _duz, anlam = _health_tr(r.name, r.code, r.detail)
                mark = "⚠️ Dikkat" if r.status is Status.WARN else "🚨 Sorun"
                alerts.append(Alert(r.status, r.code, _cut(f"{mark}: {sorun}", 80), _cut(anlam, 500), fp, now))
        for r, fp in due:
            new_fp[fp]["alerted"] = True
            new_fp[fp]["last_alert_at"] = _iso(now)
        for fp, old in prev_fp.items():
            if fp not in new_fp and isinstance(old, Mapping) and old.get("alerted"):
                name, _, code = fp.partition("|")
                _sorun, duzeldi, _anlam = _health_tr(name, code)
                alerts.append(Alert(Status.OK, code, _cut(f"✅ Düzeldi: {duzeldi}", 80),
                                    _cut("Her şey yeniden normal.", 500), fp, now))

    new_state = dict(st)
    new_state.update({"schema": 1, "fingerprints": new_fp, "last_overall": report.overall.value,
                      "last_run_at": _iso(now)})
    new_state.setdefault("restart_counts", {})
    return alerts, new_state


def quiet_split(alerts: list, report: HealthReport, now: datetime, quiet_until: datetime | None):
    """Kurulum sonrasi sessizlik: (gonderilecek, tutulan). Pencere disinda hepsi gonderilir. Pencerede yalniz FATAL_CODES
    kirmizilari (ve en az bir FATAL kirmizi varken 'multiple') gider; 'Duzeldi' ve digerleri tutulur."""
    if quiet_until is None or now >= quiet_until or quiet_until - now > timedelta(minutes=QUIET_MINUTES + 1):
        return list(alerts), []
    fatal_failing = any(r.status in (Status.CRIT, Status.UNKNOWN) and r.code in FATAL_CODES for r in report.failing())
    send, held = [], []
    for a in alerts:
        fatal = (a.level is Status.CRIT and a.code in FATAL_CODES) or (a.code == "multiple" and fatal_failing)
        (send if fatal else held).append(a)
    return send, held


def revert_failed_alerts(new_state: Mapping, prev_state: Mapping | None, failed: list[Alert]) -> dict:
    """`Notifier.send` False donen uyarilar icin last_alert_at/alerted onceki degere doner
    (sonraki turda yeniden denenir)."""
    out = dict(new_state)
    fps = {k: dict(v) for k, v in dict(new_state.get("fingerprints", {})).items()}
    prev_fps = (prev_state or {}).get("fingerprints", {}) if isinstance(prev_state, Mapping) else {}
    for a in failed:
        if a.level is Status.OK:
            if a.fingerprint in prev_fps:  # duzeldi bildirimi iletilemedi: kaydi koru, yine denensin
                fps.setdefault(a.fingerprint, dict(prev_fps[a.fingerprint]))
            continue
        targets = list(fps) if a.fingerprint == "multiple|multiple" else [a.fingerprint]
        for fp in targets:
            if fp not in fps:
                continue
            old = prev_fps.get(fp) if isinstance(prev_fps.get(fp), Mapping) else None
            if a.fingerprint == "multiple|multiple" and fps[fp].get("last_alert_at") != _iso(a.created_at):
                continue
            fps[fp]["alerted"] = bool(old.get("alerted")) if old else False
            fps[fp]["last_alert_at"] = old.get("last_alert_at") if old else None
    out["fingerprints"] = fps
    return out


# ---------------------------------------------------------------------------------------------
# Dis nabiz
# ---------------------------------------------------------------------------------------------
class HeartbeatSender(Protocol):
    def ok(self, report: HealthReport) -> bool: ...
    def fail(self, report: HealthReport) -> bool: ...


def heartbeat_message(report: HealthReport) -> str:
    """En cok 200 bayt duz metin; sir icermez."""
    codes = ",".join(f"{r.name}:{r.code}" for r in report.failing())
    return (f"overall={report.overall.value} {codes}").encode("utf-8")[:200].decode("utf-8", "ignore")


def _check_https(url: str, name: str) -> str:
    if not isinstance(url, str):
        raise ValueError(f"{name} metin olmali")
    p = urlsplit(url.strip())
    if p.scheme != "https" or not p.netloc or not p.hostname:
        raise ValueError(f"{name} https:// ile baslamali")
    return url.strip()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # yonlendirme izlenmez
        return None


class HttpsHeartbeat:
    """`HEARTBEAT_URL`'e HTTPS GET. Adres gunluge asla basilmaz (yalniz ana makine ve durum kodu)."""

    def __init__(self, url: str, fail_url: str | None = None, *, timeout: float = 10.0,
                 delays: tuple[float, ...] = (2.0, 5.0), opener: Callable | None = None,
                 sleep: Callable[[float], None] | None = None):
        self._url = _check_https(url, "HEARTBEAT_URL")
        self._fail_url = _check_https(fail_url, "HEARTBEAT_FAIL_URL") if fail_url and fail_url.strip() else None
        self._timeout = timeout
        self._delays = tuple(delays)
        self._sleep = sleep if sleep is not None else (lambda x: time.sleep(x))
        self._opener = opener if opener is not None else urllib.request.build_opener(_NoRedirect).open
        self.last_status: int | None = None
        self.last_error: str | None = None

    def __repr__(self) -> str:  # adres sizmasin
        return f"HttpsHeartbeat(host={urlsplit(self._url).hostname!r})"

    def _get(self, url: str) -> bool:
        host = urlsplit(url).hostname
        attempts = len(self._delays) + 1
        for i in range(attempts):
            try:
                req = urllib.request.Request(url, method="GET", headers={"User-Agent": "trader-health/1"})
                resp = self._opener(req, timeout=self._timeout)
                code = getattr(resp, "status", None) or resp.getcode()
                try:
                    resp.close()
                except Exception:  # noqa: BLE001
                    pass
                self.last_status = int(code)
                if 200 <= int(code) < 300:
                    self.last_error = None
                    return True
                self.last_error = f"http_{int(code)}"
                log.warning("nabiz %s durum=%s deneme=%d", host, code, i + 1)
            except urllib.error.HTTPError as e:
                self.last_status = int(e.code)
                self.last_error = f"http_{int(e.code)}"
                log.warning("nabiz %s durum=%s deneme=%d", host, e.code, i + 1)
            except Exception as e:  # noqa: BLE001
                self.last_status = None
                self.last_error = type(e).__name__
                log.warning("nabiz %s hata=%s deneme=%d", host, type(e).__name__, i + 1)
            if i < attempts - 1:
                try:
                    self._sleep(self._delays[i])
                except Exception:  # noqa: BLE001
                    pass
        return False

    def ok(self, report: HealthReport) -> bool:
        if not should_send_ok(report):  # savunma: bozuk raporla nabiz asla gitmez
            return False
        return self._get(self._url)

    def fail(self, report: HealthReport) -> bool:
        if self._fail_url is None:
            return False
        return self._get(self._fail_url)


# ---------------------------------------------------------------------------------------------
# Ortam dosyasi (saf ayristirma; systemd EnvironmentFile tuzaklari)
# ---------------------------------------------------------------------------------------------
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


def parse_env_text(text: str) -> dict[str, str]:
    """Satir: bos, '#' ile baslayan tam satir yorum ya da AD=deger (bosluk, '#', tirnak yok).
    Hata iletileri deger icermez (sir)."""
    out: dict[str, str] = {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r\n")
        if line == "" or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"satir {n}: AD=deger bicimi gerekli")
        name, _, val = line.partition("=")
        if not _ENV_NAME.match(name):
            raise ValueError(f"satir {n}: gecersiz ad (bosluk/kucuk harf?)")
        if val != val.strip() or any(c in val for c in " \t#\"'"):
            raise ValueError(f"satir {n}: deger bosluk, '#' ya da tirnak iceremez ({name})")
        if name in out:
            raise ValueError(f"satir {n}: {name} tekrar tanimli")
        out[name] = val
    return out
