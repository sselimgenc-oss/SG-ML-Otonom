"""Giris kapisi (05 §4): kapi zinciri, veto kaynaklari, hesap durumu ve risk. Risk sayisi yoktur: tek kaynak
trader_core.risk.LOCKED_CFG (cfg.risk_config: yalniz daha siki target_trade_risk). Strateji yalniz SignalRow verir; kapi kararini ve boyutu etkileyemez."""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol

from trader_core import etiket_kurallari as EK
from trader_core import kayip_freni as KF
from trader_core import kol_kucultme as KK
from trader_core import ledger as L
from trader_core import risk as K
from trader_core import veto

from . import arm_guard as AG
from .bars import tf_delta
from .brokers.base import Broker
from .clock import Clock
from .config import EngineConfig
from .errors import DataError
from .killswitch import Killswitch
from .korelasyon_grubu import KorelasyonGruplari
from .uzun_yon import UzunYon, reddeder as _uy_reddeder
from .pause import EntryPause
from .state import StateStore, parse_iso_z
from .strategies import arms as AR
from .strategy_runner import SignalFrame, SignalRow
from .types import SymbolRules

log = logging.getLogger("engine.gates")

_FILTERED_SKIPS = ("stop_width", "rr_below_min", "ml_filter")


class VetoSource(Protocol):
    def begin_step(self, now: datetime) -> None: ...

    def lookup(self, pair: str, side: str, now: datetime) -> veto.VetoLookup: ...


class FileVeto:
    """paper/canli: veto_mode="required". Anahtar yok/dosya bozuk/bayat -> lookup missing|stale (giris yok)."""

    def __init__(self, vcfg: veto.VetoConfig, env: Mapping[str, str]) -> None:
        self.cfg = vcfg
        self._key = env.get(vcfg.hmac_key_env)
        self._state: veto.VetoState | None = None

    def begin_step(self, now: datetime) -> None:
        self._state = veto.read_veto_file(self.cfg.veto_path, self._key, now, self.cfg)

    def lookup(self, pair: str, side: str, now: datetime) -> veto.VetoLookup:
        if self._state is None:
            return veto.VetoLookup("missing", "not_loaded", True)
        return veto.lookup(self._state, pair, side, now)


class NoVeto:
    """Yalniz backtest (veto_mode="off")."""

    def begin_step(self, now: datetime) -> None:
        return None

    def lookup(self, pair: str, side: str, now: datetime) -> veto.VetoLookup:
        return veto.VetoLookup("allowed", "not_evaluated:backtest", False)


@dataclass(frozen=True)
class GateVerdict:
    ok: bool
    code: str
    skip_reason: str | None   # "entry_gate_closed" | "other" | None


@dataclass(frozen=True)
class EntryOutcome:
    action: Literal["enter", "skip", "ignore"]
    event: L.DecisionEvent | None
    size: K.SizeResult | None
    leverage: int | None
    code: str
    mandatory_record: bool
    mark_decided: bool = True


def entry_leverage(cfg=None) -> int:
    """11 §3.1: cfg.leverage (varsayilan 3 = risk kilidi alt siniri => kagit sonuclari ayni). cfg yoksa alt sinir."""
    if cfg is None:
        return int(max(1, K.LOCKED_CFG.min_leverage))
    return int(max(1, cfg.leverage))


def _fin(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


_INT_CARRIERS = ("pullback_ema", "rh_touches", "rl_touches")


def _features(row: SignalRow) -> dict:
    """Defter ozellikleri: ortak anahtarlar + kurulumun `FEATURES` eslemesi (DD-12 WP-12a, K-7 madde 2). Tasiyici sutun
    adi tamsayiysa (pullback_ema) defterde tamsayi yazilir. T1/R1 eslemesi eski anahtar kumesiyle ayni sirada."""
    out: dict = {}

    def put(key: str, carrier: str) -> None:
        v = getattr(row, carrier)
        if _fin(v):
            out[key] = int(v) if carrier in _INT_CARRIERS else float(v)

    for k in ("atr_tf", "stop_dist_atr", "atr_4h"):
        put(k, k)
    for key, carrier in AR.features_of(row.setup).items():
        put(key, carrier)
    for k in ("rh_touches", "rl_touches"):
        put(k, k)
    if row.setup == "HB1":                                   # olay kimligi METIN: ML sayisal ozellik cikarimi (f_*) metni atlar
        oid = hb1_olay_of(row)
        if oid is not None:
            out["hb1_olay"] = oid
    return out


_HB1_OLAY_RE = re.compile(r"(?:^|[,:])hb1_olay=(\d+(?:\+\d+)*)(?:,|$)")
HB1_OLAY_PENCERE = timedelta(hours=6.0)      # = arms/hb1.HS_PENCERE_SAAT: bir olay en cok 6 sa canli (kol sabitiyle esitlik testle sinanir)


def _olay_kume(text) -> frozenset[int]:
    """'1,2,3' ya da '1+2+3' -> {1,2,3}; bozuk/bos -> bos kume (0 = olay yok sayilir)."""
    try:
        return frozenset(int(x) for x in str(text).replace("+", ",").split(",") if x.strip() and int(x) > 0)
    except ValueError:
        return frozenset()


def hb1_olay_of(row: SignalRow) -> str | None:
    """HB1 adayinin tum canli ayni yonlu olay kimlikleri (reasons etiketinden): kucukten buyuge virgullu metin. Yok / 0 -> None."""
    m = _HB1_OLAY_RE.search(row.reasons or "")
    k = _olay_kume(m.group(1)) if m else frozenset()
    return ",".join(str(i) for i in sorted(k)) if k else None


def _tf_of(row: SignalRow) -> str:
    if row.tf:                                               # DD-12 WP-11: bilesik strateji satiri zaman dilimini kendisi tasir
        return row.tf
    secs = int((row.bar_close_ts - row.bar_open_ts).total_seconds())
    for name, v in (("15m", 900), ("1h", 3600), ("4h", 14400), ("1d", 86400)):
        if secs == v:
            return name
    raise ValueError(f"tetik tf cozulemedi: {secs}s")


def build_decision_event(row: SignalRow, tf: str, **override) -> L.DecisionEvent:
    is_range = row.regime == "range"
    base = dict(
        bar_close_ts=row.bar_close_ts, trigger_tf=tf, pair=row.pair, side=row.side, setup=row.setup,
        regime=row.regime, atr_ratio=row.atr_ratio, rh=row.rh if is_range else None, rl=row.rl if is_range else None,
        rh_touches=int(row.rh_touches), rl_touches=int(row.rl_touches), features=_features(row),
        planned_entry=float(row.planned_entry), planned_stop=float(row.planned_stop),
        planned_target=row.planned_target, param_version_id=int(row.param_version_id),
        veto_status="not_evaluated", veto_reason=None, risk_allowed=None, risk_reason=None,
        size_qty=None, size_notional=None, size_margin=None, size_risk_amount=None, leverage=None,
        final_action="skipped", skip_reason=None, ml_score=row.ml_score, arm_id=row.arm_id)
    base.update(override)
    return L.DecisionEvent(**base)


class EntryGate:
    def __init__(self, cfg: EngineConfig, ledger: L.Ledger, state: StateStore, kill: Killswitch, veto: VetoSource,
                 clock: Clock, broker: Broker, rules_fn: Callable[[str], SymbolRules],
                 entry_ref_fn: Callable[[str, datetime, SignalRow], float] | None = None,
                 pause: EntryPause | None = None, ladder=None) -> None:
        self.cfg = cfg
        self.pause = pause
        self.ladder = ladder                                       # 12 §8.3: RiskLadder | None (backtest: hep None)
        self.ledger = ledger
        self.state = state
        self.kill = kill
        self.veto = veto
        self.clock = clock
        self.broker = broker
        self.rules_fn = rules_fn
        self.entry_ref_fn = entry_ref_fn
        self.counters: Counter = Counter()
        self.session_off: Mapping[str, Collection[str]] | Callable[[], Mapping[str, Collection[str]]] | None = None  # DD-12 D-T7: dersin kapattigi seanslar (sinif|cift -> etiketler); yok = hepsi acik
        # 19.11 kullanici karari: kagitta ML filtresi AKTIF (ogrenme_filtre.FiltreDeposu ya da None). YALNIZ bir girisi atlatabilir
        # (`ml_filter`); boyut/kaldirac/limit/risk yoluna girmez. Hata/paket yok => serbest.
        self.ml_filtre = None
        # Kagitta rejim etiketi kurali girisi YALNIZ atlatabilir (docs/etiket-kurallari-spec.md); sabit kural (otomatik acma/kapama yok).
        # etiket_cfg = dogrulanmis cfg.etiket_kurallari ({} = kapali).
        self.etiket_cfg: Mapping | None = None
        self.arms_off: Collection[str] | Callable[[], Collection[str]] | None = None  # DD-12 WP-13: ders kapattigi kurulumlar (arm_id); yok = hepsi acik
        # 23.11 kullanici karari: asama B esikleri (yalniz paper/live; ENTRY-only). Korelasyon grubu: matris kaynagini engine baglar
        # (yoksa sabit kume yedegi); kayip freni + toplam buyukluk tavani cfg'den okunur.
        kc = getattr(cfg, "korelasyon", None)
        self.korelasyon: KorelasyonGruplari | None = None
        if kc and cfg.mode in ("paper", "live"):
            self.korelasyon = KorelasyonGruplari(None, cfg.pairs, cfg.clusters, kc["esik"], int(kc["pencere_gun"]))
        uc = getattr(cfg, "uzun_yon", None)                      # fikir 7: uzun donem yon filtresi (bos = kapali); bars_fn'i engine baglar
        self.uzun_yon: UzunYon | None = UzunYon(uc) if uc and cfg.mode in ("paper", "live") else None
        self.memory_lock: str | None = None       # DD-8 O4: dosya tutusu yazilamadiysa bellek kilidi (kapi kodu); None = yok

    # ------------------------------------------------------------------ cift-bagimsiz kapilar (4-8)
    def pre(self, D: datetime, tf: str, params_ok: bool, active_tf: str) -> GateVerdict:
        closed = "entry_gate_closed"
        if not params_ok:
            return GateVerdict(False, "params_unavailable", closed)
        if active_tf != tf:
            return GateVerdict(False, "trigger_tf_changed", closed)
        try:
            h = self.ledger.entries_allowed()
            if not h.ok:
                return GateVerdict(False, h.code, closed)
        except Exception as e:  # noqa: BLE001 - fail-closed
            log.error("entries_allowed hatasi: %s", e)
            return GateVerdict(False, "degraded", closed)
        reason = self.state.kv_get("entries_blocked_reason")
        if reason:
            return GateVerdict(False, str(reason), closed)
        if self.kill.active():
            return GateVerdict(False, "kill", closed)
        if self.pause is not None and self.pause.active():          # 11 §9.3: kill'den sonra, stale_data'dan once
            return GateVerdict(False, self.pause.code() or "paused", closed)
        if self.memory_lock:                                        # DD-8 O4 (fail-closed): tutus dosyaya yazilamadi
            return GateVerdict(False, self.memory_lock, closed)
        if self.ladder is not None:                                 # 12 §8.3: duraklatmadan sonra, stale_data'dan once
            gc = self.ladder.gate_code()
            if gc:
                return GateVerdict(False, gc, closed)
        if self.clock.now() - D > self.cfg.stale_factor * tf_delta(tf):
            return GateVerdict(False, "stale_data", "other")
        return GateVerdict(True, "ok", None)

    # ------------------------------------------------------------------ hesap durumu (§4.2)
    def account_state(self, D: datetime) -> K.AccountState | None:
        day = D.strftime("%Y-%m-%d")
        ds = self.state.kv_get(f"day_start:{day}")
        if ds is None:
            init = self.state.kv_get("initialized_at")
            fresh = True
            if isinstance(init, str) and init != "unset":
                try:
                    fresh = parse_iso_z(init).strftime("%Y-%m-%d") >= day
                except ValueError:
                    fresh = False
            if not fresh:
                return None
            ds = self.cfg.wallet_start
        positions = [K.OpenPosition(p.pair, p.side, float(p.risk_amount), float(p.margin))
                     for p in self.state.open_positions()]
        return K.AccountState(equity=float(self.broker.account().equity), day_start_equity=float(ds),
                              open_positions=positions)

    # ------------------------------------------------------------------ karar
    def _ignore(self, code: str) -> EntryOutcome:
        self.counters["ignore:" + code] += 1
        return EntryOutcome("ignore", None, None, None, code, False, False)

    def _skip(self, row: SignalRow, tf: str, code: str, *, mark: bool = True, **ev) -> EntryOutcome:
        self.counters["skip:" + code] += 1
        return EntryOutcome("skip", build_decision_event(row, tf, **ev), None, None, code, False, mark)

    def _session_off(self) -> Mapping[str, Collection[str]] | None:
        so = self.session_off
        return so() if callable(so) else so

    def _etiket_karari(self, row: SignalRow, tf: str, tk: dict) -> EntryOutcome | None:
        """Rejim etiketi kurali (kagit, sabit): trend karsiti giris `etiket_rejim` ile atlanir (karar satiri; karsi-olgu mevcut yoldan).
        Veri yok (rejim bilinmiyor) -> engellemez (sayilir). Hata -> serbest. Boyut/kaldirac/limit'e hic girmez."""
        cfg = self.etiket_cfg
        if not cfg:
            return None
        try:
            tetik, veri_yok = EK.degerlendir(row.side, row.regime, cfg)
            for k in veri_yok:
                self.counters["etiket_veri_yok:" + k] += 1
            if not tetik:
                return None
            kod, detay = tetik[0]
            self.counters["etiket_atladi:" + kod] += 1
            return self._skip(row, tf, kod, skip_reason=kod, veto_reason=f"gate:{kod}:{detay}", **tk)
        except Exception as e:  # noqa: BLE001 - etiket hatasi giris engellemez
            log.warning("etiket kurallari hatasi, giris serbest: %s: %s", type(e).__name__, e)
            return None

    def _ml_filtre_karari(self, row: SignalRow, tf: str, D: datetime, tk: dict) -> EntryOutcome | None:
        """ML filtresi: esik alti puan => `ml_filter` ile atla (karar satiri + puan; karsi-olgu mevcut atlama yolundan).
        KAGIT: baska her durum (filtre yok/paket yok/hata) => None (giris serbest, fail-open). Asla istisna yaymaz.
        CANLI (23.11; yalniz ml_mode=active): filtre yok / paket yok / bozuk / suresi dolmus / hata => giris YOK (fail-closed;
        `gate:ml_filter_unavailable`); cikislar etkilenmez. Saglik uyarisi: engine._ml_status (status.json ml -> health)."""
        live_closed = self.cfg.mode == "live" and self.cfg.ml_mode == "active"
        flt = self.ml_filtre
        if flt is None:
            return self._ml_kapali(row, tf, tk) if live_closed else None
        try:
            from .ogrenme_filtre import canlida_engelle, ozellikler
            aid = row.arm_id or AG.arm_id_of(row.setup, tf)
            feats = tk.get("features") or _features(row)
            oz = ozellikler(side=row.side, regime=row.regime, atr_ratio=row.atr_ratio, session_tag=tk.get("session_tag"),
                            pair=row.pair, planned_entry=row.planned_entry, planned_stop=row.planned_stop,
                            planned_target=row.planned_target, rh_touches=int(row.rh_touches), rl_touches=int(row.rl_touches),
                            features=feats)
            k = flt.karar(aid, oz, self.clock.now())
            if k.neden == "ok":
                self.counters["ml_filtre_gecti"] += 1
            if k.izin:
                if live_closed and canlida_engelle(k.neden):
                    return self._ml_kapali(row, tf, tk)
                return None
            self.counters["ml_filtre_atladi"] += 1
            return self._skip(row, tf, "ml_filter", skip_reason="ml_filter", veto_reason="gate:ml_filter",
                              ml_score=k.puan, **tk)
        except Exception as e:  # noqa: BLE001
            if live_closed:
                log.error("ML filtre kapisi hatasi, CANLIDA giris yok: %s: %s", type(e).__name__, e)
                return self._ml_kapali(row, tf, tk)
            log.warning("ML filtre kapisi hatasi, giris serbest: %s: %s", type(e).__name__, e)
            return None

    def _ml_kapali(self, row: SignalRow, tf: str, tk: dict) -> EntryOutcome:
        self.counters["ml_filtre_kapali_blok"] += 1
        return self._skip(row, tf, "ml_filter", skip_reason="ml_filter", veto_reason="gate:ml_filter_unavailable", **tk)

    def _hb1_olay_karari(self, row: SignalRow, tf: str, D: datetime, tk: dict) -> EntryOutcome | None:
        """HB1: adayin olay kumesi (features["hb1_olay"]) son 6 saatte AYNI cift+yonde kapanmis TUM HB1 islemlerinin olay kumelerinin
        birlesiminin alt kumesiyse giris `hb1_ayni_olay` ile reddedilir (ayni haberle yeniden giris yok); kumede en az bir YENI kimlik varsa serbest.
        Canli yaris korumasi: bu cift icin HB1 pozisyonuna ait henuz defterde olmayan (outbox'ta bekleyen) cikis varsa giris reddedilir
        (`hb1_olay_bekleyen_cikis`; kagit ve canli ayni kod). Defter/durum okuma hatasi => fail-closed (yalniz HB1). Diger kollara dokunmaz."""
        if row.setup != "HB1":
            return None
        aid = row.arm_id or AG.arm_id_of(row.setup, tf)
        try:
            for ob in self.state.outbox_pending():
                if ob.kind != "exit":
                    continue
                p = self.state.get_position(ob.trade_id)
                if p is not None and p.pair == row.pair and getattr(p, "setup", None) == "HB1":
                    self.counters["hb1_olay_bekleyen_cikis"] += 1
                    return self._skip(row, tf, "hb1_olay_bekleyen_cikis", skip_reason="risk_denied", veto_status="not_evaluated",
                                      veto_reason="gate:hb1_olay_bekleyen_cikis", risk_allowed=False,
                                      risk_reason="HB1 çıkışı henüz defterde değil: olay kontrolü için bekleniyor", **tk)
            oid = hb1_olay_of(row)
            if oid is None:
                self.counters["hb1_olay_yok"] += 1
                return None
            fn = getattr(self.ledger, "closed_decision_features_since", None)
            if fn is None:
                raise RuntimeError("defter closed_decision_features_since yok")
            prev = fn(aid, row.pair, row.side, D - HB1_OLAY_PENCERE)
        except Exception as e:  # noqa: BLE001
            self.counters["hb1_olay_okunamadi"] += 1
            log.warning("HB1 olay kontrolu defter hatasi, giris yok: %s: %s", type(e).__name__, e)
            return self._skip(row, tf, "hb1_olay_okunamadi", skip_reason="risk_denied", veto_status="not_evaluated",
                              veto_reason="gate:hb1_olay_okunamadi", risk_allowed=False,
                              risk_reason="HB1 olay kimliği defterden okunamadı: giriş yok", **tk)
        eski: frozenset[int] = frozenset().union(*(_olay_kume(f.get("hb1_olay")) for f in prev)) if prev else frozenset()
        if not (_olay_kume(oid) <= eski):
            return None
        self.counters["hb1_ayni_olay"] += 1
        return self._skip(row, tf, "hb1_ayni_olay", skip_reason="risk_denied", veto_status="not_evaluated",
                          veto_reason="gate:hb1_ayni_olay", risk_allowed=False,
                          risk_reason=f"aynı haber olayları ({oid}) son 6 saatte kapanan HB1 işlemlerinde var: yeniden giriş yok", **tk)

    def _kol_karari(self, aid: str, D: datetime | None = None) -> KK.KolKarar | None:
        """Kademeli kucultme (kagit): kolun son kapanan islemlerinin net R'sinden carpan. Okunamazsa None (carpan yok = yapilandirma boyutu;
        hata yalniz kucultmeyi atlar, hicbir seyi arttirmaz/engellemez)."""
        fn = getattr(self.ledger, "arm_recent_results", None)
        if fn is None:
            return None
        try:
            fam = getattr(self.ledger, "arm_family_mean_r", None)
            aile = fam(aid, D) if fam is not None else None          # fikir 8: az islemli kol aile ortalamasina cekilir (buzulme)
            return KK.karar(fn(aid, KK.KAYIT_SAYISI), aile)
        except Exception as e:  # noqa: BLE001
            log.warning("kol kucultme okunamadi, tam boyut: %s: %s", type(e).__name__, e)
            return None

    # ------------------------------------------------------------------ 23.11 kullanici karari: asama B esikleri (yalniz giris)
    def _korelasyon_karari(self, row: SignalRow, tf: str, D: datetime, tk: dict) -> EntryOutcome | None:
        """Adayin korelasyon grubunda (30 gun 1s getiri korelasyonu >= esik; veri yoksa sabit kume) AYNI yonde acik pozisyon sayisi
        `yon_basina_max`e ulasmissa giris `korelasyon_grubu` ile atlanir. Hata => engellemez (sayilir); cikislara dokunmaz."""
        kg, kc = self.korelasyon, getattr(self.cfg, "korelasyon", None)
        if kg is None or not kc:
            return None
        try:
            n = kg.grup_sayisi(row.pair, row.side, self.state.open_positions(), self.clock.now())
            mx = int(kc["yon_basina_max"])
            if n < mx:
                return None
            self.counters["korelasyon_grubu_blok"] += 1
            return self._skip(row, tf, "korelasyon_grubu", skip_reason="risk_denied", veto_status="not_evaluated",
                              veto_reason="gate:korelasyon_grubu", risk_allowed=False,
                              risk_reason=f"korelasyon grubu sınırı: aynı yönde ({row.side}) {n} açık pozisyon var, en fazla {mx}", **tk)
        except Exception as e:  # noqa: BLE001
            self.counters["korelasyon_grubu_hata"] += 1
            log.warning("korelasyon grubu hatasi, giris serbest: %s: %s", type(e).__name__, e)
            return None

    def _uzun_yon_karari(self, row: SignalRow, tf: str, D: datetime, tk: dict) -> EntryOutcome | None:
        """Fikir 7: 1d rejimi boga ise short, ayi ise long girisi `uzun_yon` ile atlanir; yatay/veri yok serbest (veri yok sayilir).
        Rejim karar olayi features["uzun_yon"] alanina yazilir. Hata => engellemez (sayilir)."""
        uy = self.uzun_yon
        if uy is None:
            return None
        try:
            r = uy.rejim(row.pair, self.clock.now())
        except Exception as e:  # noqa: BLE001
            self.counters["uzun_yon_hata"] += 1
            log.warning("uzun yon hesabi hatasi, giris serbest: %s: %s", type(e).__name__, e)
            return None
        tk["features"] = {**(tk.get("features") or _features(row)), "uzun_yon": r}
        if r == "veri_yok":
            self.counters["uzun_yon_veri_yok"] += 1
            return None
        if not _uy_reddeder(r, row.side):
            return None
        self.counters["uzun_yon_blok"] += 1
        return self._skip(row, tf, "uzun_yon", skip_reason="risk_denied", veto_status="not_evaluated",
                          veto_reason="gate:uzun_yon", risk_allowed=False,
                          risk_reason=f"uzun dönem yön filtresi: 1d rejimi {r}, {row.side} girişi reddedildi", **tk)

    def _fren_karari(self, acct: K.AccountState, D: datetime) -> KF.FrenKarari | None:
        """Kayip freni: defterden (son kapananlar) + state gun basi kasadan TURETILIR (dosya yok). Hata => None (cagiran girisi atlar: fail-closed)."""
        fc = getattr(self.cfg, "kayip_freni", None)
        if not fc:
            return KF.YOK
        try:
            son = self.ledger.list_closed_trades(limit=max(50, int(fc["ardisik"]) * 10))
            return KF.karar(fc, son, acct.equity, acct.day_start_equity, D.replace(hour=0, minute=0, second=0, microsecond=0))
        except Exception as e:  # noqa: BLE001
            self.counters["kayip_freni_hata"] += 1
            log.error("kayip freni okunamadi, GIRIS YOK (fail-closed): %s: %s", type(e).__name__, e)
            return None

    def _toplam_buyukluk_karari(self, row: SignalRow, tf: str, acct: K.AccountState, size: K.SizeResult, vs: str,
                                veto_reason: str | None, tk: dict) -> EntryOutcome | None:
        """Acik pozisyonlarin nominali + aday <= toplam_buyukluk_kat x kasa; degilse `toplam_buyukluk`. Hata => engellemez."""
        kat = getattr(self.cfg, "toplam_buyukluk_kat", None)
        if not kat:
            return None
        try:
            acik = 0.0
            marks: dict = {}
            try:                                                                        # mark fiyat varsa o, yoksa giris fiyati
                marks = {bp.pair: float(bp.mark_price) for bp in self.broker.positions() if _fin(getattr(bp, "mark_price", None))}
            except Exception:  # noqa: BLE001
                marks = {}
            for p in self.state.open_positions():
                q, px = getattr(p, "qty", None), marks.get(p.pair, getattr(p, "entry_price", None))
                acik += float(q) * float(px) if _fin(q) and _fin(px) else float(p.margin) * float(p.leverage)
            tavan = float(kat) * float(acct.equity)
            if acik + float(size.notional) <= tavan:
                return None
            self.counters["toplam_buyukluk_blok"] += 1
            return self._skip(row, tf, "toplam_buyukluk", skip_reason="risk_denied", veto_status=vs, veto_reason=veto_reason,
                              risk_allowed=False,
                              risk_reason=f"toplam büyüklük tavanı: açık {acik:.2f} + aday {float(size.notional):.2f} > {kat:g} x kasa {tavan:.2f}", **tk)
        except Exception as e:  # noqa: BLE001
            self.counters["toplam_buyukluk_hata"] += 1
            log.error("toplam buyukluk tavani okunamadi, GIRIS YOK (fail-closed): %s: %s", type(e).__name__, e)
            return self._skip(row, tf, "buyukluk_okunamadi", skip_reason="risk_denied", veto_status=vs, veto_reason="gate:buyukluk_okunamadi",
                              risk_allowed=False, risk_reason="toplam büyüklük okunamadı: giriş yok", **tk)

    def _arms_off(self) -> Collection[str]:
        ao = self.arms_off
        return (ao() if callable(ao) else ao) or ()

    def conflict(self, frame: SignalFrame, winner: SignalRow) -> EntryOutcome:
        """DD-12 WP-11 (D-T16): ayni cift/adimda birden cok kurulum sinyal verdi; buyuk zaman dilimi kazandi, kaybeden
        `arm_conflict` ile yazilir (kagit; veto yok; `mark_decided` yok - kazananin karari isaretler)."""
        row = frame.last
        tk: dict = {}
        if self.cfg.mode in ("paper", "live"):                                          # 23.11 kullanici karari: canli = kagit
            tk = {"session_tag": AG.session_tag(AG.asset_class(row.pair, self.cfg.clusters), frame.last.bar_close_ts)}
        return self._skip(row, _tf_of(row), "arm_conflict", mark=False, skip_reason="arm_conflict",
                          veto_reason=f"gate:arm_conflict:{winner.arm_id or winner.setup}", **tk)

    def decide(self, frame: SignalFrame, D: datetime, pre: GateVerdict, active_version: int) -> EntryOutcome:
        if frame.status != "ok" or frame.last is None:                                  # 0
            return self._ignore(frame.status if frame.status != "ok" else "no_arm_closed")
        row = frame.last
        pair = row.pair
        tf = _tf_of(row)
        paper = self.cfg.mode in ("paper", "live")                                      # DD-12 WP-04: kagit sistemi; 23.11 kullanici karari: canli = kagit
        tk: dict = {}
        cls = ""
        if paper:
            cls = AG.asset_class(pair, self.cfg.clusters)
            tk = {"session_tag": AG.session_tag(cls, D)}                                # etiket yasak degil, kayit
        if not row.signal:                                                              # 1 / 1b
            if (row.setup and row.side and row.skip_reason in _FILTERED_SKIPS
                    and self.cfg.record_filtered_candidates and row.param_version_id >= 1):
                return self._skip(row, tf, row.skip_reason, mark=False, skip_reason=row.skip_reason, **tk)
            return self._ignore("no_signal")
        if self.state.is_decided(pair, D):                                              # 2
            return self._ignore("already_decided")
        if self.state.position_for_pair(pair) is not None:                              # 3
            return self._ignore("position_exists")
        if row.param_version_id < 1:
            return self._ignore("no_param_version")
        if not pre.ok:                                                                  # 4-8
            return self._skip(row, tf, pre.code, skip_reason=pre.skip_reason, veto_reason="gate:" + pre.code, **tk)
        sb = getattr(self, "symbol_blocked", None)                                      # 8b: saatlik sembol izleyici (4f)
        if sb is not None and sb(pair):                                                 # TRADING disi sembolde YENI giris yok
            return self._skip(row, tf, "symbol_not_trading", skip_reason="other", veto_reason="gate:symbol_not_trading", **tk)
        try:                                                                            # 9
            rules = self.rules_fn(pair)
        except Exception as e:  # noqa: BLE001 - DataError/RulesError/baska: fail-closed
            if not isinstance(e, DataError):
                log.error("rules_fn beklenmeyen hata %s: %r", pair, e)
            return self._skip(row, tf, "rules_missing", skip_reason="other", veto_reason="gate:rules_missing", **tk)
        now = self.clock.now()
        if paper:                                                                       # 9a-9c (DD-12 WP-04); veto adimi YOK
            aid = row.arm_id or AG.arm_id_of(row.setup, tf)
            # 19 Kasim (sahip karari): ders kurulum KAPATMAZ; arms_off yalniz karne/rapor bilgisidir, giris engellenmez.
            if aid in self._arms_off():
                self.counters["arm_would_close"] += 1
            if pair in self.cfg.retired_pairs:                                           # WP-18: evrenden cikmis, yeni giris yok
                return self._skip(row, tf, "arm_disabled", skip_reason="arm_disabled",
                                  veto_reason=f"gate:universe_retired:{pair}", **tk)
            if self.cfg.flat_bar_guard and frame.trigger_bar is not None and AG.is_flat_bar(
                    frame.trigger_bar[0], frame.trigger_bar[1], frame.trigger_bar[2]):
                return self._skip(row, tf, "flat_bar", skip_reason="flat_bar", veto_reason="gate:flat_bar", **tk)
            if AG.session_closed_by_lesson(self._session_off(), cls, pair, tk["session_tag"]):
                return self._skip(row, tf, "session_closed", skip_reason="session_closed",
                                  veto_reason="gate:session_closed", **tk)
            ho = self._hb1_olay_karari(row, tf, D, tk)                                      # HB1: ayni haberle yeniden giris yok
            if ho is not None:
                return ho
            held = [p.pair for p in self.state.open_positions()]
            cname = AG.full_cluster(pair, held, self.cfg.clusters)
            if cname is not None:
                return self._skip(row, tf, "cluster_cap", skip_reason="cluster_cap",
                                  veto_reason=f"gate:cluster_cap:{cname}", **tk)
            if self.cfg.arm_max_positions:                                               # WP-11: kurulum basina tavan
                aid = row.arm_id or AG.arm_id_of(row.setup, tf)
                cap = AG.arm_cap(self.cfg.arm_max_positions, aid, row.setup)
                held_arms = [AG.arm_id_of(p.setup, p.trigger_tf) for p in self.state.open_positions()
                             if getattr(p, "setup", None) and getattr(p, "trigger_tf", None)]
                if AG.arm_full(held_arms, aid, cap):
                    return self._skip(row, tf, "max_positions", skip_reason="max_positions",
                                      veto_reason=f"gate:arm_cap:{aid}", **tk)
            if AG.account_full(len(held), self.cfg.max_positions):
                return self._skip(row, tf, "max_positions", skip_reason="max_positions",
                                  veto_reason="gate:max_positions", **tk)
            uy = self._uzun_yon_karari(row, tf, D, tk)                                   # fikir 7: 1d rejimi (boga: short yok, ayi: long yok)
            if uy is not None:
                return uy
            kg = self._korelasyon_karari(row, tf, D, tk)                                 # 23.11 asama B: korelasyon grubu yon tavani
            if kg is not None:
                return kg
            ml_skip = self._ml_filtre_karari(row, tf, D, tk)
            if ml_skip is not None:
                return ml_skip
            et_skip = self._etiket_karari(row, tf, tk)                                   # rejim etiketi kurali (ML'den sonra, risk'ten once)
            if et_skip is not None:
                return et_skip
            lk = veto.VetoLookup("allowed", "not_evaluated:paper", False)
        else:
            lk = self.veto.lookup(pair, row.side, now)                                  # 10
        vs = "not_evaluated" if paper else "allowed"                                    # DD-12 WP-06a: kagitta veto yok
        if lk.blocks:
            return self._skip(row, tf, f"veto_{lk.status}", skip_reason=f"veto_{lk.status}",
                              veto_status=lk.status, veto_reason=lk.reason)
        acct = self.account_state(D)                                                    # 11
        if acct is None:
            return self._skip(row, tf, "day_start_missing", skip_reason="entry_gate_closed",
                              veto_reason="gate:day_start_missing", **tk)
        lev = entry_leverage(self.cfg)
        ref = self.entry_ref_fn(pair, D, row) if self.entry_ref_fn is not None else row.planned_entry
        cand = K.Candidate(pair, row.side, float(ref), float(row.planned_stop), float(lev),
                           rules.step, rules.min_notional)
        src = self.ladder if self.ladder is not None else self.cfg
        dec = None
        if paper:                                                                       # 20 Kasim: kademeli kucultme (yalniz kagit, yalniz kucultur)
            kk = self._kol_karari(aid, D)
            kol_mult = 1.0
            if kk is not None:
                tk["features"] = {**(tk.get("features") or _features(row)), **KK.ozellikler(kk)}
                kol_mult = float(kk.carpan)
            fren = self._fren_karari(acct, D)                                              # 23.11 asama B: kayip freni (yalniz kucultur)
            if fren is None:                                                               # okunamadi: fail-closed
                return self._skip(row, tf, "fren_okunamadi", skip_reason="risk_denied", veto_status=vs, veto_reason="gate:fren_okunamadi",
                                  risk_allowed=False, risk_reason="kayıp freni okunamadı: giriş yok", **tk)
            fren_mult = KF.goreli_carpan(fren, self.cfg.risk_config.target_trade_risk, src.risk_config.target_trade_risk)
            mult = min(kol_mult, fren_mult)                                             # asgari; kademe/mandal zaten src.risk_config icinde
            if fren.aktif:
                tk["features"] = {**(tk.get("features") or _features(row)), "kayip_freni": fren.neden, "kayip_freni_carpani": float(fren_mult)}
            if mult < 1.0:
                dec = K.check_entry_scaled(acct, cand, src.risk_config, mult)
                if dec.allowed:
                    if kol_mult < 1.0 and kol_mult <= fren_mult:
                        self.counters[f"kol_kucultme:{aid}"] += 1
                    if fren_mult < 1.0:
                        self.counters["kayip_freni_yarim:" + str(fren.neden)] += 1
                elif fren_mult < 1.0:                                                   # fren aktif: tam boyuta GERI DONULMEZ (asla artirmaz)
                    self.counters["kayip_freni_boyut_reddi"] += 1
                else:                                                                   # asgari boyut bile emir alt sinirinin altinda: kol kapanmaz, tam boyut denenir
                    dec = None
                    tk["features"] = {**tk["features"], "kol_boyut_carpani": 1.0, "kol_boyut_geri": 1}
        if dec is None:
            dec = K.check_entry(acct, cand, src.risk_config)
        if not dec.allowed:
            return self._skip(row, tf, "risk_denied", skip_reason="risk_denied", veto_status=vs,
                              veto_reason=lk.reason, risk_allowed=False, risk_reason=dec.reason, **tk)
        if paper:                                                                       # 23.11 asama B: toplam buyukluk tavani (boyut belli olduktan sonra)
            tb = self._toplam_buyukluk_karari(row, tf, acct, dec.size, vs, lk.reason, tk)
            if tb is not None:
                return tb
        size = dec.size                                                                 # 12
        self.counters["enter"] += 1
        ev = build_decision_event(
            row, tf, veto_status=vs, veto_reason=lk.reason, risk_allowed=True, risk_reason=dec.reason,
            size_qty=size.qty, size_notional=size.notional, size_margin=size.margin,
            size_risk_amount=size.risk_amount, leverage=lev, final_action="entered", skip_reason=None, **tk)
        return EntryOutcome("enter", ev, size, lev, "entered", True)
