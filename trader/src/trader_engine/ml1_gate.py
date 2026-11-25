"""ML1 kagit giris kapisi (25.11 sahip karari; yalniz mode="paper", config `ml1.aktif`).

Kural kollarinin adaylarindan hangisinin islem olacagina ML1 modeli karar verir. Ozellikler cevrimdisi hatla AYNI islevlerle hesaplanir
(`trader_ml.ml1.features.confluence` ve `bar_features`; yeniden yazim YOK): konfluans, motorun adim adim biriktirdigi aday tamponundan;
mum ozellikleri, kolun o adimda zaten yukledigi mum pencerelerinden (yalniz aday satirlari icin; her mumda degil).

Akis (karar adimi D):
  1) `observe`   : kol degerlendirmesinde (MultiArmSignalSource) sinyali dogru olan HER kural kolu adayi (post_filter ONCESI, cevrimdisi
                   tarama ile ayni anlam) cift tamponuna yazilir; (trig, h4) pencereleri adim sonuna kadar tutulur.
  2) `prepare`   : cift icin giris degerlendirmesi baslarken sinyal adaylari puanlanir, puana gore (yuksek once) siralanir, karar
                   (`Verdict`) hazirlanir. Esik alti -> "ml1_esik_alti"; ayni olay penceresinde onayli giris var -> "ml1_ayni_olay";
                   gecerli paket yok -> "ml1_paket_yok". Defter skip_reason'u CHECK kisiti nedeniyle mevcut `ml_filter` / `ml_no_model`
                   degerlerine eslenir; ML1 nedeni `veto_reason` ("gate:ml1_...") ve features'ta durur.
  3) `note_entry`: giris yapilan (cift, yon, tf) icin olay penceresi baslatilir (olay = features.events anahtari pair|side|tf, k mum).
Hicbir yontem yukari firlatmaz: hata = bu adimda ML1 adaylari atlanir (fail-closed, "ml1_paket_yok") ve sayac/CRIT log; motor durmaz.
Konfluans tamponu bellektedir; yeniden baslatmada defterdeki son kararlardan kurulur (defter yalniz KAYDEDILEN kararlari tutar:
pozisyon varken yok sayilan adaylar eksiktir) => yeniden baslatmadan sonra en cok k mum (<= 3 gun) konfluans eksik sayilabilir."""
from __future__ import annotations

import logging
import math
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from trader_core import arm_time as AT
from trader_ml.ml1 import features as F
from trader_ml.ml1 import groups as G
from trader_ml.ml1 import model as M

log = logging.getLogger("engine.ml1")

ESIK_ALTI, AYNI_OLAY, PAKET_YOK = "ml1_esik_alti", "ml1_ayni_olay", "ml1_paket_yok"
LEDGER_NEDENI = {ESIK_ALTI: "ml_filter", AYNI_OLAY: "ml_filter", PAKET_YOK: "ml_no_model"}   # defter skip_reason CHECK kisiti (sema degismez)
K_BARS = F.K_BARS
TAMPON_OMRU = timedelta(days=K_BARS + 1)                      # en uzun konfluans penceresi: k x 1g; +1 gun pay
CRIT_ARALIGI = timedelta(hours=1)
_FILTRELENMIS = ("stop_width", "rr_below_min")                # defterde aday olmayan (sinyal=False) satirlar
_ROOT = Path(__file__).resolve().parents[2]
TOHUM_PAKET = _ROOT / "models" / "ml1" / "ml1_package.json"   # depodaki tohum (salt okunur)
KOS_PAKET_ALT = Path("ml1") / "ml1_package.json"


def kos_paket_yolu() -> Path:
    """Calisma zamani paketi: var/learner/models/ml1/ml1_package.json (m1 ile ayni kok: TRADER_ML_RUNTIME_DIR ya da depo/var)."""
    return Path(os.environ.get("TRADER_ML_RUNTIME_DIR") or (_ROOT / "var" / "learner" / "models")) / KOS_PAKET_ALT


@dataclass(frozen=True)
class Verdict:
    code: str | None                 # None = esigi gecti; aksi halde ml1_esik_alti | ml1_ayni_olay | ml1_paket_yok
    score: float | None
    features: Mapping[str, Any]      # deftere yazilacak ml1_* alanlari (yalniz sonlu sayi/metin)

    @property
    def ledger_reason(self) -> str | None:
        return LEDGER_NEDENI.get(self.code) if self.code else None


class Ml1Gate:
    def __init__(self, cfg: Mapping[str, Any] | None = None) -> None:
        cfg = cfg or {}
        self._paths: tuple[Path, ...] = (Path(cfg["paket_yolu"]) if cfg.get("paket_yolu") else kos_paket_yolu(),
                                         Path(cfg["tohum_yolu"]) if cfg.get("tohum_yolu") else TOHUM_PAKET)
        self.counters: Counter = Counter()
        self._pkg: dict | None = None
        self._sig: tuple | None = None            # son bakilan dosyalarin (yol, mtime_ns, boyut) imzasi
        self._chk_d: datetime | None = None       # paket denetimi adim basina bir kez
        self._crit_at: datetime | None = None
        self._buf: dict[str, dict[tuple, dict]] = {}          # cift -> {(arm_id, decision_ts, side): aday}
        self._bars: dict[tuple[str, str], tuple] = {}         # (cift, tf) -> (trig, h4); yalniz adim boyunca
        self._bars_d: datetime | None = None
        self._verd: dict[tuple[str, str], Verdict] = {}
        self._verd_d: datetime | None = None
        self._son_giris: dict[tuple[str, str, str], datetime] = {}   # (cift, yon, tf) -> onayli son giris karar zamani

    # ------------------------------------------------------------------ paket
    def _paket(self, D: datetime) -> dict | None:
        """Adim basina bir kez: runtime paketi, yoksa/gecersizse tohum. mtime/boyut degisince yeniden yuklenir; gecerli paket yoksa None."""
        if self._chk_d == D:
            return self._pkg
        self._chk_d = D
        sig = []
        for p in self._paths:
            try:
                st = os.stat(p)
                sig.append((str(p), st.st_mtime_ns, st.st_size))
            except OSError:
                sig.append((str(p), None, None))
        sig_t = tuple(sig)
        if sig_t == self._sig:
            return self._pkg
        self._sig = sig_t
        pkg = None
        for p, (_, mt, _sz) in zip(self._paths, sig_t):
            if mt is None:
                continue
            got, why = M.load_package(p)
            thr = None if got is None else got.get("threshold")
            if got is not None and (isinstance(thr, bool) or not isinstance(thr, (int, float)) or not math.isfinite(thr)):
                got, why = None, f"esik gecersiz: {thr!r}"
            if got is not None:
                pkg = got
                log.info("ML1 paketi yuklendi: %s sha=%s esik=%s", p, str(got["sha256"])[:12], got["threshold"])
                break
            log.error("ML1 paketi gecersiz (%s): %s", p, why)
        if pkg is None:
            log.error("ML1: gecerli paket yok (%s)", ", ".join(str(p) for p in self._paths))
        self._pkg = pkg
        return pkg

    # ------------------------------------------------------------------ kol degerlendirmesi: aday tamponu
    def observe(self, pair: str, D: datetime, tf: str, r, trig: pd.DataFrame, h4: pd.DataFrame) -> None:
        """Sinyali dogru kural kolu adayi (post_filter oncesi satir `r`). Asla firlatmaz."""
        try:
            setup, side = r["setup"], r["side"]
            grp = G.GRUPLAR.get(setup) if isinstance(setup, str) else None
            if grp is None or side not in ("long", "short"):
                return                                   # kural kolu degil (M1 vb.)
            if self._bars_d != D:
                self._bars.clear()
                self._bars_d = D
            self._bars[(pair, tf)] = (trig, h4)
            ts = pd.Timestamp(D)
            tgt = r["planned_target"]
            self._buf.setdefault(pair, {})[(f"{setup}@{tf}", ts, side)] = {
                "bar_ts": ts - AT.arm_tf_delta(tf), "decision_ts": ts, "pair": pair, "tf": tf, "arm_id": f"{setup}@{tf}", "setup": setup,
                "group": grp, "side": side, "entry_ref": float(r["planned_entry"]), "stop": float(r["planned_stop"]),
                "target": float("nan") if tgt is None else float(tgt), "stop_dist_atr": float(r["stop_dist_atr"])}
            self.counters["ml1_aday_tampon"] += 1
            self._prune(pair, D)                         # pozisyon acikken puanlama olmaz: tampon yine de sinirli kalsin
        except Exception as e:  # noqa: BLE001
            self.counters["ml1_hata"] += 1
            log.error("ML1 aday tamponu hatasi %s: %r", pair, e)

    def end_step(self) -> None:
        """Karar adimi sonu: mum pencere referanslari ve adim kararlari birakilir; eski adaylar tampondan atilir."""
        self._bars.clear()
        self._bars_d = None
        self._verd.clear()
        self._verd_d = None

    def _prune(self, pair: str, D: datetime) -> None:
        b = self._buf.get(pair)
        if not b:
            return
        lim = pd.Timestamp(D) - TAMPON_OMRU
        for k in [k for k in b if k[1] < lim]:
            del b[k]

    # ------------------------------------------------------------------ yeniden baslatma: defterden tampon
    def warm(self, ledger, now: datetime) -> int:
        """Defterdeki son kararlardan tampon ve olay penceresi kurar (yalniz KAYDEDILEN kararlar). Doner: eklenen aday sayisi. Firlatmaz."""
        n = 0
        try:
            recs = ledger.list_decisions(since_ts=now - TAMPON_OMRU, until_ts=now)
            for r in recs:
                grp = G.GRUPLAR.get(r.setup)
                if grp is None or r.skip_reason in _FILTRELENMIS:
                    continue
                ts = pd.Timestamp(r.bar_close_ts)
                aid = r.arm_id or f"{r.setup}@{r.trigger_tf}"
                self._buf.setdefault(r.pair, {})[(aid, ts, r.side)] = {
                    "bar_ts": ts - AT.arm_tf_delta(r.trigger_tf), "decision_ts": ts, "pair": r.pair, "tf": r.trigger_tf, "arm_id": aid,
                    "setup": r.setup, "group": grp, "side": r.side, "entry_ref": float("nan"), "stop": float("nan"),
                    "target": float("nan"), "stop_dist_atr": float("nan")}
                n += 1
                if r.final_action == "entered" and "ml1_skor" in (r.features or {}):
                    k = (r.pair, r.side, r.trigger_tf)
                    if k not in self._son_giris or self._son_giris[k] < ts.to_pydatetime():
                        self._son_giris[k] = ts.to_pydatetime()
            log.info("ML1 tamponu defterden kuruldu: %d aday (%s oncesi eksik olabilir)", n, now.isoformat())
        except Exception as e:  # noqa: BLE001
            self.counters["ml1_hata"] += 1
            log.error("ML1 tamponu defterden kurulamadi (bos baslanir): %r", e)
        return n

    def seed(self, cands: pd.DataFrame) -> None:
        """Sicak tampon (test/arac): cevrimdisi aday tablosu satirlari (CAND_COLUMNS). Firlatmaz."""
        try:
            for r in cands.to_dict("records"):
                ts = pd.Timestamp(r["decision_ts"])
                self._buf.setdefault(r["pair"], {})[(r["arm_id"], ts, r["side"])] = {
                    k: r[k] for k in ("bar_ts", "pair", "tf", "arm_id", "setup", "group", "side", "entry_ref", "stop", "target", "stop_dist_atr")
                } | {"decision_ts": ts}
        except Exception as e:  # noqa: BLE001
            self.counters["ml1_hata"] += 1
            log.error("ML1 tampon tohumlama hatasi: %r", e)

    # ------------------------------------------------------------------ giris: puanlama / siralama
    @staticmethod
    def _uygun(c) -> bool:
        r = None if c is None else c.last
        return r is not None and bool(r.signal) and r.setup in G.GRUPLAR and r.side in ("long", "short") and bool(r.arm_id)

    def verdict(self, row) -> Verdict | None:
        """Bu adimda puanlanmis adayin karari (yoksa None: kural kolu degil / puanlanmadi)."""
        if self._verd_d is None or self._verd_d != row.bar_close_ts or not row.signal:
            return None
        return self._verd.get((row.pair, row.arm_id))

    def note_entry(self, pair: str, side: str, tf: str, D: datetime) -> None:
        try:
            self._son_giris[(pair, side, tf)] = D
        except Exception:  # noqa: BLE001
            pass

    def _crit(self, D: datetime, msg: str) -> None:
        if self._crit_at is None or D - self._crit_at >= CRIT_ARALIGI or D < self._crit_at:
            self._crit_at = D
            log.critical("%s", msg)

    def prepare(self, pair: str, D: datetime, cands: tuple) -> tuple:
        """Cift adaylarini puanlar ve ML1 puanina gore (yuksek once; yalniz kural kolu adaylarinin kendi yuvalari arasinda) siralar.
        Asla firlatmaz: hata olursa uygun adaylar fail-closed `ml1_paket_yok` alir ve sira degismez."""
        try:
            uygun = [i for i, c in enumerate(cands) if self._uygun(c)]
        except Exception:  # noqa: BLE001
            return cands
        if not uygun:
            return cands
        if self._verd_d != D:
            self._verd.clear()
            self._verd_d = D
        try:
            return self._prepare(pair, D, cands, uygun)
        except Exception as e:  # noqa: BLE001
            self.counters["ml1_hata"] += 1
            self._crit(D, f"ML1 puanlama hatasi {pair}: {type(e).__name__}: {e}")
            log.error("ML1 puanlama hatasi %s", pair, exc_info=True)
            for i in uygun:
                self._koy(cands[i].last, Verdict(PAKET_YOK, None, {"ml1_neden": "hata"}))
            return cands

    def _koy(self, row, v: Verdict) -> None:
        self._verd[(row.pair, row.arm_id)] = v
        self.counters[v.code or "ml1_gecti"] += 1

    def _prepare(self, pair: str, D: datetime, cands: tuple, uygun: list[int]) -> tuple:
        pkg = self._paket(D)
        if pkg is None:
            self.counters["ml1_paket_yok_adim"] += 1
            self._crit(D, "ML1: gecerli paket yok; kural kolu adaylari atlaniyor (ml1_paket_yok)")
            for i in uygun:
                self._koy(cands[i].last, Verdict(PAKET_YOK, None, {"ml1_neden": "paket_yok"}))
            return cands
        self._prune(pair, D)
        b = self._buf.get(pair, {})
        buf = pd.DataFrame(list(b.values())).reset_index(drop=True)
        keys = {k: j for j, k in enumerate(b)}
        rows, sel = [], []
        for i in uygun:
            r = cands[i].last
            j = keys.get((r.arm_id, pd.Timestamp(D), r.side))
            if j is None:
                raise RuntimeError(f"aday tamponda yok: {r.arm_id}")
            rows.append(i)
            sel.append(j)
        conf = F.confluence(buf)
        cur = buf.iloc[sel]
        bf = F.bar_features(cur, self._lookup)
        full = pd.concat([cur, conf.loc[cur.index], bf], axis=1)
        pr = M.score(pkg, full)
        if not np.all(np.isfinite(pr)):
            raise ValueError("ML1 puani sonlu degil")
        thr = float(pkg["threshold"])
        sha = str(pkg["sha256"])[:12]
        out = []
        for n, i in enumerate(rows):
            r = cands[i].last
            tf = r.tf
            p = float(pr[n])
            code = None
            if p < thr:
                code = ESIK_ALTI
            else:
                e = self._son_giris.get((pair, r.side, tf))
                if e is not None and timedelta(0) <= D - e <= K_BARS * AT.arm_tf_delta(tf):
                    code = AYNI_OLAY
            cr = conf.loc[cur.index[n]]
            feats = {"ml1_skor": p, "ml1_esik": thr, "ml1_sha": sha, "ml1_grup": str(cur.iloc[n]["group"]),
                     "ml1_conf_same_tf": int(cr["conf_same_tf"]), "ml1_conf_all_tf": int(cr["conf_all_tf"]),
                     "ml1_conf_groups": int(cr["conf_groups"]), "ml1_conf_opp": int(cr["conf_opp"])}
            self._koy(r, Verdict(code, p, feats))
            out.append((-p, n, i))
        # puana gore (yuksek once; esitlikte mevcut sira) yalniz uygun adaylarin yuvalarinda yeniden diz
        yeni = list(cands)
        for (_, _, src), slot in zip(sorted(out), rows):
            yeni[slot] = cands[src]
        return tuple(yeni)

    def _lookup(self, pair: str, tf: str):
        return self._bars.get((pair, tf))
