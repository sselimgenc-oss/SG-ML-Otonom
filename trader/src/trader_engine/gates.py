"""Giris kapisi (05 §4): kapi zinciri, hesap durumu ve risk. Risk sayisi yoktur: tek kaynak
trader_core.risk.LOCKED_CFG (cfg.risk_config: yalniz daha siki target_trade_risk). Strateji yalniz SignalRow verir; kapi kararini ve boyutu etkileyemez."""
from __future__ import annotations


import logging
import math
from collections import Counter
from collections.abc import Callable, Collection, Mapping
import dataclasses
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from trader_core import etiket_kurallari as EK
from trader_core import ledger as L
from trader_core import risk as K

from . import arm_guard as AG
from .bars import tf_delta
from .brokers.base import Broker
from .clock import Clock
from .config import EngineConfig
from .errors import DataError
from .killswitch import Killswitch
from .pause import EntryPause
from . import seans_disi as SD
from . import stop_tabani as ST
from .state import StateStore, parse_iso_z
from .strategies import arms as AR
from .strategy_runner import SignalFrame, SignalRow
from .types import SymbolRules

log = logging.getLogger("engine.gates")

_YUKLENMEDI = object()
_FILTERED_SKIPS = ("stop_width", "rr_below_min")


@dataclass(frozen=True)
class VetoLookup:
    """Giris karar satirina yazilan veto durumu. AI veto 18.11'de kaldirildi; yalniz backtest tekrar-oynatma ve ledger semasi
    (eski satirlar) bu alani tasir."""
    status: str
    reason: str | None
    blocks: bool


class VetoSource(Protocol):
    def begin_step(self, now: datetime) -> None: ...

    def lookup(self, pair: str, side: str, now: datetime) -> VetoLookup: ...


class NoVeto:
    """Backtest/testnet: veto degerlendirilmez."""

    def begin_step(self, now: datetime) -> None:
        return None

    def lookup(self, pair: str, side: str, now: datetime) -> VetoLookup:
        return VetoLookup("allowed", "not_evaluated:backtest", False)


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
    hesap_duzeyi: bool | None = None      # 25.11: risk reddi hesap duzeyinde mi (yapisal; kapi bir kez belirler). None = bilinmiyor


def entry_leverage(cfg=None) -> int:
    """11 §3.1: cfg.leverage (varsayilan 3 = risk kilidi alt siniri => kagit sonuclari ayni). cfg yoksa alt sinir."""
    if cfg is None:
        return int(max(1, K.LOCKED_CFG.min_leverage))
    return int(max(1, cfg.leverage))


def _fin(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


_INT_CARRIERS = ("pullback_ema", "rh_touches", "rl_touches")


def ml1_risk_orani(ml1_cfg: Mapping | None, skor: object) -> float | None:
    """26.11 ML1 guven bandi riski (yalniz kagit). Ogrenme asamasi (puan yok), ozellik kapali/yok ya da puan ilk bandin altinda ->
    None (sabit target_trade_risk). Aksi halde puani en yuksek saglayan bandin riski, `tavan` ile sinirli."""
    rb = (ml1_cfg or {}).get("risk_bantlari")
    if not rb or not rb.get("aktif") or isinstance(skor, bool) or not isinstance(skor, (int, float)) or not math.isfinite(skor):
        return None
    r = None
    for esik, risk in rb["bantlar"]:
        if skor >= esik:
            r = float(risk)
    return None if r is None else min(r, float(rb["tavan"]))


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
    if getattr(row, "stop_dogal", None) is not None:          # 27.11 stop tabani: dogal stop fiyati + genisletildi mi (kayit)
        out["stop_dogal"] = float(row.stop_dogal)
        out["stop_genisletildi"] = bool(row.stop_genisletildi)
    for k in ("vol_tahmin", "vol_asim"):                     # fikir 10: yalniz gece suzgecinin ek girdisi (f_vol_*); eksikse yazilmaz
        v = getattr(row, k, None)
        if _fin(v):
            out[k] = float(v)
    return out


# 24.11 (cift ici yedek aday): bir adayin reddi YALNIZ aday-ozgu nedenlerle ise siradaki aday denenir; cift/hesap duzeyindeki
# nedenlerde (kapi kapali, hesap tavani, etiket_*, gunluk zarar, ...) ayni cift icin durulur ve kalan sinyal adaylari
# `arm_conflict` yazilir. TEK TANIM: bilinmeyen kod cift duzeyi sayilir (guvenli taraf: ek satir/deneme yok).
ADAY_OZGU_RED_KODLARI = frozenset({"flat_bar", "ml1_esik_alti", "ml1_ayni_olay", "ml1_paket_yok",
                                   "tasfiye_mesafesi", "tasfiye_okunamadi"})
_HESAP_RISK_IZLERI = ("günlük", "toplam açık risk", "toplam teminat", "zaten açık pozisyon", "iç hata")


def hesap_duzeyi_risk(neden: str) -> bool:
    """Risk reddi metni hesap duzeyinde mi (tek yer; kapi sonucu `hesap_duzeyi` alanina yazar)."""
    return any(z in neden for z in _HESAP_RISK_IZLERI)


def aday_ozgu_red(out) -> bool:
    """True: red yalniz bu adaya ozgu (boyut/tasfiye ...): siradaki aday denenebilir.
    False: cift/hesap duzeyi (kapi, hesap max_positions, etiket_*, seans, gunluk zarar ...): durulur."""
    code = getattr(out, "code", None)
    if code in ADAY_OZGU_RED_KODLARI:
        return True
    ev = getattr(out, "event", None)
    if code == "risk_denied":
        hd = getattr(out, "hesap_duzeyi", None)
        if hd is None:                                       # yapisal alan yoksa eski metin siniflamasi (yedek)
            hd = hesap_duzeyi_risk(str(getattr(ev, "risk_reason", "") or ""))
        return not hd
    return False


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
        final_action="skipped", skip_reason=None, arm_id=row.arm_id)
    base.update(override)
    return L.DecisionEvent(**base)


class EntryGate:
    ml1 = None                                    # 25.11 ML1 kapisi (ml1_gate.Ml1Gate | None; yalniz paper'da motor baglar); None = onceki davranis

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
        # Kagitta rejim etiketi kurali girisi YALNIZ atlatabilir (docs/etiket-kurallari-spec.md); sabit kural (otomatik acma/kapama yok).
        # etiket_cfg = dogrulanmis cfg.etiket_kurallari ({} = kapali).
        self.etiket_cfg: Mapping | None = None
        self.seans_takvimi_yolu: str | None = None             # None = config/seans_takvimi.json (varsayilan); testler yol verir
        self._takvim = _YUKLENMEDI
        self.seans_disi_aktif: bool = True                     # uretimde hep True; yalniz eski testler hafta sonu girisi icin kapatir
        self.arms_off: Collection[str] | Callable[[], Collection[str]] | None = None  # DD-12 WP-13: ders kapattigi kurulumlar (arm_id); yok = hepsi acik
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

    # ------------------------------------------------------------------ 23.11 kullanici karari: asama B esikleri (yalniz giris)
    def _seans_disi_karari(self, row: SignalRow, tf: str, D: datetime, cls: str, tk: dict) -> EntryOutcome | None:
        """Hafta sonu / tatil / buyuk haber penceresinde hisse+emtia icin YENI giris yok (seans_disi.py). Acik pozisyon ve kripto etkilenmez.
        Takvim eksik/bozuk -> tatil+haber engellemez, sayac `seans_disi_takvim_yok` (hafta sonu takvimsiz calisir). Kagit ve canli ayni kod."""
        if not self.seans_disi_aktif or cls not in (SD.CLASS_EMTIA, SD.CLASS_HISSE):
            return None
        if self._takvim is _YUKLENMEDI or self._takvim is None:
            self._takvim = SD.yukle(self.seans_takvimi_yolu)
        if self._takvim is None:
            self.counters[SD.SAYAC_TAKVIM_YOK] += 1
        elif SD.takvim_eski_mi(self._takvim, D):
            self.counters[SD.SAYAC_TAKVIM_ESKI] += 1
        kod = SD.karar(cls, D, self._takvim)
        if kod is None:
            return None
        self.counters[kod] += 1
        return self._skip(row, tf, kod, skip_reason="session_closed", veto_reason="gate:" + kod, **tk)

    def _tasfiye_mesafesi_karari(self, row: SignalRow, tf: str, cand: K.Candidate, lev: int, vs: str,
                                 veto_reason: str | None, tk: dict) -> EntryOutcome | None:
        """Izole tasfiye fiyati, girisle stop arasindaki mesafenin liq_safety_factor (1,5) katindan YAKINSA giris yok
        (`gate:tasfiye_mesafesi`). Izole teminatta tasfiye fiyati buyukluge bagli degildir ve kaldirac hesap ayaridir
        (motor degistirmez) => kucultme cozum degildir; atla. MMR: sinif sabiti (risk.MMR_SINIF) ile cfg'nin buyugu.
        Guvenliyse etkisi yok (None). Hata => atla (fail-closed)."""
        try:
            rc = self.cfg.risk_config
            sinif = AG.asset_class(cand.pair, self.cfg.clusters)
            mmr = K.sinif_mmr(sinif, rc.maint_margin_rate)
            t = K.tasfiye_mesafesi(cand.entry, cand.stop, cand.side, lev, mmr, rc.liq_safety_factor)
            if t["guvenli"]:
                return None
            self.counters["tasfiye_mesafesi"] += 1
            return self._skip(row, tf, "tasfiye_mesafesi", skip_reason="risk_denied", veto_status=vs, veto_reason="gate:tasfiye_mesafesi",
                              risk_allowed=False,
                              risk_reason=(f"tasfiye mesafesi yetersiz: liq {t['liq_fiyat']:.6g} (mesafe {t['liq_mesafe']:.6g}) < "
                                           f"{t['guvenlik']:g} x stop mesafesi {t['stop_mesafe']:.6g}; kaldirac {lev}, mmr {mmr:g}, "
                                           f"izin verilen en yuksek kaldirac {t['max_kaldirac']}"), **tk)
        except Exception as e:  # noqa: BLE001
            self.counters["tasfiye_mesafesi_hata"] += 1
            log.error("tasfiye mesafesi hesaplanamadi, GIRIS YOK (fail-closed): %s: %s", type(e).__name__, e)
            return self._skip(row, tf, "tasfiye_okunamadi", skip_reason="risk_denied", veto_status=vs, veto_reason="gate:tasfiye_mesafesi",
                              risk_allowed=False, risk_reason="tasfiye mesafesi hesaplanamadi: giris yok", **tk)

    def stop_tabani_uygula(self, pair: str, D: datetime, cands: tuple, params: Mapping | None, ml1=None) -> tuple:
        """27.11 sahip karari: STOP TABANI (stop_tabani.py). Adaylari (`SignalFrame` demeti) puanlamadan (ML1) VE boyutlamadan ONCE
        gecirir: sinyal satirlarinin `planned_stop`u (genisletildiyse), `stop_dist_atr`, `rr` ve `stop_dogal`/`stop_genisletildi`
        yeni haliyle SignalRow'a yazilir; elenen aday `signal=False` + `skip_reason` (stop_width | rr_below_min) olur (mevcut
        'filtrelenmis aday' yolu: karar satiri `decide` 1b'de yazilir). ML1 tamponu (`ml1`) genisletilen adayin SON stopuyla guncellenir
        (elenen aday tamponda KALIR: konfluans baglami egitim/cevrimdisi tarama ile ayni; puanlanmaz, cunku signal=False). Sira: sinyal > elenmis > diger (kararli; tf sirasi korunur) - elenen aday kalan sinyalleri engellemesin.
        Kapali (bos/aktif=false) => ayni demet doner (eski davranis). Hata => o aday degismez (fail-open degil: satir ayni kalir,
        sayac `stop_tabani_hata`)."""
        cfg = self.cfg.stop_tabani
        if not cfg or not cfg.get("aktif"):
            return cands
        out = []
        changed = False
        for c in cands:
            r = c.last
            if r is None or not r.signal or not r.side or not (r.planned_entry > 0):
                out.append(c)
                continue
            try:
                paper = self.cfg.mode in ("paper", "live")
                tag = AG.session_tag(AG.asset_class(pair, self.cfg.clusters), D) if paper else None
                c_rt = ST.rt_maliyet(self.cfg.risk_config, self.cfg.cost, self.cfg.cost_overrides if paper else None, pair, tag)
                nr, kod = ST.uygula(r, cfg, c_rt, ST.rr_min_of(r.setup, params), ST.max_atr_of(r.setup))
            except Exception as e:  # noqa: BLE001
                self.counters["stop_tabani_hata"] += 1
                log.error("stop tabani hesaplanamadi %s %s: %s: %s", pair, r.arm_id, type(e).__name__, e)
                out.append(c)
                continue
            self.counters["stop_tabani_" + (kod or ("genisletildi" if nr.stop_genisletildi else "degismedi"))] += 1
            if ml1 is not None and r.arm_id and kod is None and nr.stop_genisletildi:
                try:
                    ml1.stop_guncelle(pair, D, r.arm_id, r.side, nr.planned_stop, nr.stop_dist_atr)
                except Exception:  # noqa: BLE001 - ML1 yardimi karari etkilemez
                    self.counters["stop_tabani_ml1_hata"] += 1
            out.append(dataclasses.replace(c, last=nr))
            changed = True
        if not changed:
            return cands
        rank = lambda f: 0 if (f.last is not None and f.last.signal) else (  # noqa: E731
            1 if (f.last is not None and f.last.setup and f.last.side and f.last.skip_reason in _FILTERED_SKIPS) else 2)
        return tuple(sorted(out, key=rank))

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
        mv = self.ml1.verdict(row) if self.ml1 is not None else None                    # 25.11 ML1: puanlanmis aday kaybederse de puani kayitta
        if mv is not None:
            tk["features"] = {**_features(row), **mv.features}
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
        mv = self.ml1.verdict(row) if (paper and self.ml1 is not None) else None        # 25.11 ML1 (yalniz paper): bu adimda puanlanmis aday karari
        if mv is not None:
            tk["features"] = {**_features(row), **mv.features}                          # puan/sha/grup: girilen ya da atlanan HER puanlanmis adayda
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
        if mv is not None and mv.code is not None:                                      # 25.11 ML1: esik alti / ayni olay / paket yok (aday-ozgu red)
            return self._skip(row, tf, mv.code, skip_reason=mv.ledger_reason, veto_reason="gate:" + mv.code, **tk)
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
            sd = self._seans_disi_karari(row, tf, D, cls, tk)                                # 23.11 karar (fikir 9 a): seans disi YENI giris yok
            if sd is not None:
                return sd
            held = [p.pair for p in self.state.open_positions()]
            if AG.account_full(len(held), self.cfg.max_positions):
                return self._skip(row, tf, "max_positions", skip_reason="max_positions",
                                  veto_reason="gate:max_positions", **tk)
            et_skip = self._etiket_karari(row, tf, tk)                                   # rejim etiketi kurali (risk'ten once)
            if et_skip is not None:
                return et_skip
            lk = VetoLookup("allowed", "not_evaluated:paper", False)
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
        src = self.ladder if self.ladder is not None else self.cfg
        rk = None
        if paper and mv is not None:                                                    # 26.11 ML1 guven bandi riski (puansiz/ogrenme: sabit)
            rk = ml1_risk_orani(self.cfg.ml1, mv.features.get("ml1_skor"))
            if rk is not None:
                rk = min(rk, src.risk_config.target_trade_risk) if src.risk_config.target_trade_risk < self.cfg.risk_config.target_trade_risk else rk
                tk["features"] = {**tk["features"], "ml1_risk": rk}
        cand = K.Candidate(pair, row.side, float(ref), float(row.planned_stop), float(lev),
                           rules.step, rules.min_notional, rk)
        dec = K.check_entry(acct, cand, src.risk_config)
        if not dec.allowed:
            o = self._skip(row, tf, "risk_denied", skip_reason="risk_denied", veto_status=vs,
                           veto_reason=lk.reason, risk_allowed=False, risk_reason=dec.reason, **tk)
            return dataclasses.replace(o, hesap_duzeyi=hesap_duzeyi_risk(str(dec.reason or "")))
        td = self._tasfiye_mesafesi_karari(row, tf, cand, lev, vs, lk.reason, tk)        # 23.11: kagit = canli, ayni kod
        if td is not None:
            return td
        size = dec.size                                                                 # 12
        self.counters["enter"] += 1
        ev = build_decision_event(
            row, tf, veto_status=vs, veto_reason=lk.reason, risk_allowed=True, risk_reason=dec.reason,
            size_qty=size.qty, size_notional=size.notional, size_margin=size.margin,
            size_risk_amount=size.risk_amount, leverage=lev, final_action="entered", skip_reason=None, **tk)
        return EntryOutcome("enter", ev, size, lev, "entered", True)
