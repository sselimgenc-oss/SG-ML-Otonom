"""ML1 golge (sanal) ogrenme: alinmayan adayin "ayni kurallarla ne olurdu" simulasyonu (27.11 sahip karari). Yalniz kagit; durum/broker/emir/defter
uzerinde YAZMA yok: sonuc yalniz ogrenicinin `sanallar-*.jsonl` dosyasina gider (defter islem tablolarina HICBIR ZAMAN girmez).

Simulasyon motorun 15 dk `last` mum izgarasinda, kagit brokerin dolum kurallarini yansitir:
  * giris : karar D'den (tf kapanisi) sonra ilk 15 dk mumunun ACILISI (kagit: sonraki dakika acilisi) + `slip_entry_bps` (aleyhe); ucret = taker.
  * cikis : her 15 dk mumunda STOP ONCE, sonra hedef (hedef kipi: dinlenen hedef emri; gap -> acilis, hedefte `min(.., high)` korumasi);
            stop dolumu: gap ise acilis degilse stop fiyati, `slip_stop_bps`; hedef/piyasa cikisi `slip_exit_bps`.
  * tf kapanisinda (motor `evaluate_exit` ayni sira): hedef kipi -> zaman stopu (`time_stop_of`, tf mumu); iz kipi -> rejim donusu, iz suren stop
    (`signals.trail_stop_path`, motorla ayni tek kaynak; ATR/rejim `arm_time.core_signals`), kapanis stopu astiysa piyasa cikisi; yeni stop sonraki 15 dk mumundan gecerli.
    Piyasa cikislari sonraki 15 dk mumunun acilisinda dolar.
  * ufuk: en cok 30 gun (hedef kipinde zaman stopu daha kisaysa o); asilirsa son fiyattan "kesildi" kapanis, etikete DAHIL.
  * net R: (brut - giris ucreti - cikis ucreti - funding) / planli risk; planli risk motorla ayni `risk.loss_at_stop` (birim adet). Funding: kagit broker
    gibi 8 saatlik izgarada (00/08/16) piyasa fonlama noktalari, birim adet.
Gercek kagit dolumundan farklar: 1 dk yerine 15 dk mum (stop/hedef ayni 15 dk icinde sirasi bilinmez: stop once), tetik mark yerine last, tick yuvarlamasi
yok, kutuphane kural cikisi (EXIT_RULE) ve kismi/basa-bas cikis kipleri yok, SignalParams varsayilan (surum parametresi degil), min notional/marjin reddi yok.
Golge-gercek kiyasi: `olcumler.golge_gercek` ayni `veri_al` + `simule` ile kapanan GERCEK islemi yeniden simule eder; uyum dusukse sanal agirlik otomatik 0,5 (docs/inceleme-200.md)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

import numpy as np
import pandas as pd

from trader_core import arm_time as AT
from trader_core import risk
from trader_core import signals as S

MAKS_GUN = 30
ADIM = pd.Timedelta(minutes=15)
ISINMA = 300                       # ATR/rejim isinma mumu (4s baslangic sayisi ile ayni mertebe)
VERI_YOK_GUN = 3                   # ilk 15 dk mumu bu kadar gun sonra hala yoksa aday etiketsiz kapatilir
KESME_TOLERANS_GUN = 1             # ufuk doldu ama veri daha once bittiyse bu kadar bekleyip eldeki son fiyattan kesilir


@dataclass(frozen=True)
class Maliyet:
    taker_fee: float = 0.0005
    slip_entry_bps: float = 2.0
    slip_exit_bps: float = 2.0
    slip_stop_bps: float = 5.0


@dataclass
class SanalCfg:
    """Ogrenicinin sanal ogrenme baglami (motor kurar). `maliyet_fn(cift, zaman) -> Maliyet` (cost + cost_overrides)."""
    view: Any
    maliyet_fn: Callable[[str, datetime], Maliyet]
    tavan: int = 5000
    butce: int = 40                      # karar adimi basina en cok bu kadar bekleyen kontrol edilir
    kontrol_aralik: pd.Timedelta = field(default_factory=lambda: pd.Timedelta(hours=1))


@dataclass(frozen=True)
class SanalSonuc:
    y: int
    r_net: float
    exit_reason: str
    exit_ts: pd.Timestamp
    kesildi: bool
    gross_r: float


def _slip(px: float, order_side: str, bps: float) -> float:
    f = bps / 1e4
    return px * (1.0 + f) if order_side == "buy" else px * (1.0 - f)


def simule(rec: dict, b15: pd.DataFrame, trig: pd.DataFrame | None, mal: Maliyet, fonlama, simdi) -> SanalSonuc | None:
    """Saf simulasyon. `b15`: karar D'den itibaren kapanmis 15 dk mumlari (open/high/low/close; UTC indeks); `trig`: iz kipinde tf mumlari
    (high/low/close/atr_tf/regime; D'den itibaren); `fonlama`: [(ts, rate, mark)] liste. Cozulmediyse None (bekler)."""
    side = rec["side"]
    long = side == "long"
    sgn = 1.0 if long else -1.0
    D = pd.Timestamp(rec["decision_ts"])
    simdi = pd.Timestamp(simdi)
    tfd = pd.Timedelta(AT.arm_tf_delta(rec["tf"]))
    mod, tl = rec["mod"], rec.get("time_stop")
    stop0 = float(rec["stop"])
    tgt = rec.get("target")
    tgt = None if tgt is None or not math.isfinite(float(tgt)) else float(tgt)
    if len(b15) == 0 or b15.index[0] != D:
        return None
    ufuk = pd.Timedelta(days=MAKS_GUN)
    zs_ufuk = mod == "target" and tl is not None and tl * tfd < ufuk
    son = D + (tl * tfd if zs_ufuk else ufuk)
    idx = b15.index
    o, h, lo, c = (b15[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(idx)
    ep = _slip(o[0], "buy" if long else "sell", mal.slip_entry_bps)
    risk_u = risk.loss_at_stop(1.0, float(rec["entry_ref"]), stop0, risk.LOCKED_CFG)
    if not risk_u > 0:
        return None
    xs = "sell" if long else "buy"
    path = reg = tc = None
    if mod == "trail":
        if trig is None or len(trig) == 0:
            return None
        t = trig[trig.index >= D]
        if len(t):
            path = S.trail_stop_path(side, ep, stop0, t["high"].to_numpy(float), t["low"].to_numpy(float), t["atr_tf"].to_numpy(float),
                                     float(rec["trail_atr"])).to_numpy()
            reg, tc = t["regime"].tolist(), t["close"].to_numpy(float)
    cur = stop0
    cikis: tuple[float, pd.Timestamp, str, bool] | None = None
    for i in range(n):
        b = idx[i]
        if b >= son:
            break
        gap = (o[i] <= cur) if long else (o[i] >= cur)
        if (lo[i] <= cur) if long else (h[i] >= cur):                       # stop once
            base = o[i] if gap else cur
            cikis = (_slip(base, xs, mal.slip_stop_bps), b, "trail_stop" if cur != stop0 else "stop", False)
            break
        if mod == "target" and tgt is not None and ((h[i] >= tgt) if long else (lo[i] <= tgt)):
            base = o[i] if ((o[i] >= tgt) if long else (o[i] <= tgt)) else tgt
            base = min(base, h[i]) if long else max(base, lo[i])
            cikis = (_slip(base, xs, mal.slip_exit_bps), b, "target", False)
            break
        k, rem = divmod(b + ADIM - D, tfd)
        if rem == pd.Timedelta(0) and k >= 1:                               # tf kapanisi: motorun cikis degerlendirmesi
            neden = None
            if mod == "target":
                if tl is not None and k >= tl:
                    neden = "time_stop"
            elif path is not None and k - 1 < len(path):
                j = int(k) - 1
                if S.regime_flip_exit(side, reg[j]):
                    neden = "regime_flip"
                else:
                    st = float(path[j])
                    if st != stop0 and ((st >= tc[j]) if long else (st <= tc[j])):
                        neden = "trail_stop"
                    elif (st > cur + 1e-9) if long else (st < cur - 1e-9):
                        cur = st                                           # yeni stop sonraki 15 dk mumundan gecerli
            if neden is not None:
                if i + 1 >= n:
                    return None                                            # piyasa cikisi sonraki mumun acilisinda: henuz yok
                cikis = (_slip(o[i + 1], xs, mal.slip_exit_bps), idx[i + 1], neden, False)
                break
    if cikis is None:
        if not (idx[-1] + ADIM >= son or simdi >= son + pd.Timedelta(days=KESME_TOLERANS_GUN)):
            return None
        j = max(int((idx < son).sum()) - 1, 0)                              # ufuktan onceki son mum: son fiyattan kesilir
        cikis = (_slip(c[j], xs, mal.slip_exit_bps), idx[j] + ADIM, "kesildi", True)
    xp, xt, why, kes = cikis
    gross = sgn * (xp - ep)
    ucret = (ep + xp) * mal.taker_fee
    fund = 0.0
    for ts, rate, mark in fonlama:
        ts = pd.Timestamp(ts)
        if D < ts <= xt and ts.hour % 8 == 0 and ts.minute == 0:
            m = mark if mark is not None and math.isfinite(mark) and mark > 0 else ep
            p = m * rate
            fund += p if long else -p
    net = gross - ucret - fund
    r = net / risk_u
    if not math.isfinite(r):
        return None
    return SanalSonuc(1 if r > 0 else 0, float(r), why, xt, kes, float(gross / risk_u))


def veri_al(view, rec: dict, simdi, trail: bool):
    """(b15, trig, fonlama) -- motor `view` (MarketView) uzerinden; yalniz kapanmis mumlar. Okuma hatasi yukari firlar (cagiran sayar)."""
    D = pd.Timestamp(rec["decision_ts"])
    simdi = pd.Timestamp(simdi)
    n15 = int((min(simdi, D + pd.Timedelta(days=MAKS_GUN + 1)) - D) / ADIM) + 2
    b15 = view.bars(rec["pair"], "15m", simdi.to_pydatetime(), n15)
    b15 = b15[b15.index >= D]
    trig = None
    if trail:
        from .bars import aggregate_4h_to_1d
        from trader_core import regime as R
        tfd = pd.Timedelta(AT.arm_tf_delta(rec["tf"]))
        need4 = int((simdi - D) / pd.Timedelta(hours=4)) + 3
        h4 = view.bars(rec["pair"], "4h", simdi.to_pydatetime(), need4 + (6 * 60 if rec["tf"] == "1d" else ISINMA))
        if rec["tf"] == "4h":
            tr = h4
        elif rec["tf"] == "1d":
            tr = aggregate_4h_to_1d(h4)
        else:
            tr = view.bars(rec["pair"], rec["tf"], simdi.to_pydatetime(), int((simdi - D) / tfd) + 3 + ISINMA)
        p = S.DEFAULT_SIGNAL_PARAMS
        reg = AT.regime_series(h4, p.regime_params())
        sig, _, _ = AT.core_signals(tr, reg, p)
        trig = pd.DataFrame({"high": tr["high"], "low": tr["low"], "close": tr["close"], "atr_tf": sig["atr_tf"], "regime": sig["regime"]})
    fon = [(f.ts, f.rate, f.mark) for f in view.funding(rec["pair"], D.to_pydatetime(), simdi.to_pydatetime())]
    return b15, trig, fon
