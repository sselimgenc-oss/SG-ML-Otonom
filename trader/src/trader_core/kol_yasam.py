"""Kurulum (arm) yasam dongusu: ac/kapa karari, durum dosyasi (`var/<bot>/arms_off.json`) okuma/yazma.

Ders sistemi kaldirildi (25.11); kurulum karnesi icin gereken saf islevler `scripts/counterfactual_run.py` ve
`trader_core/panel_*` / `strateji_veri` tarafindan kullanildigi icin burada kalir. Standart kutuphane. Motor kapali kurulumu
ENGELLEMEZ (19 Kasim sahip karari): `arms_off.json` yalniz karne/rapor bilgisidir. Motor okuyucusu: `arm_guard.load_arms_off`.
Esik owner kararidir: minimum aday/islem sarti YOK; karar sonumlu ortalamayla (`damped_mean`) verilir; tek degisikligin geri
alinmasi `damped_effect` ile `rollback_r` (3 R) esigine gore yapilir. Pencere: en fazla son 40 aday (ust sinir, alt sinir degil).
"""
from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc
_EPS = 1e-9
SHRINK_N = 10                         # sonum payi (eski ders yapilandirmasindaki shrink_n)
ROLLBACK_EFFECT_R = 3.0               # geri alma esigi (eski ders yapilandirmasindaki rollback_effect_r)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def damped_mean(sum_r: float, n: int, shrink_n: int = 10) -> float:
    """Sonumlu ortalama (spec 6.3): `toplam R / (n + shrink_n)`; shrink_n = 0 => sonumsuz ortalama; payda 0 => 0."""
    den = n + max(0, int(shrink_n))
    return float(sum_r) / den if den > 0 else 0.0



def damped_effect(effect_sum: float, n: int, shrink_n: int = 10) -> float:
    """Sonumlu etki (R birimi): `effect * n / (n + shrink_n)` (= n * damped_mean(effect, n, shrink_n) ... n = farkli karar
    verilen aday sayisi). shrink_n = 0 => etki aynen; n = 0 => 0. Esikler (-3 R, -10 R) bu birimle karsilastirilir."""
    if n <= 0:
        return 0.0
    return float(effect_sum) * n / (n + max(0, int(shrink_n)))


ARM_CLOSE_R = -0.15                   # sonumlu ortalama <= bu: kurulum kapanir (kayit surer)
ARM_REOPEN_R = 0.05                   # sonumlu ortalama >= bu: kapali kurulum yeniden acilir
ARM_WINDOW_MAX = 40                   # pencere ust siniri (alt siniri yok)
ARM_STATE_SCHEMA = 1
ARM_KAPAT_MIN_N = 3                   # 24.11: aile verisi varken kapatma icin kolun kendi cozulmus aday asgarisi
ARM_CF_AGIRLIK = 0.5                  # 24.11: alinmayan adayin R'si toplamda ve sayida bu agirlikla girer
ARM_KAPAT_MIN_GUN = 3                 # ... ve bu adaylarin ayri gun sayisi asgarisi


def _arm_dt(s) -> datetime | None:
    if s is None:
        return None
    if isinstance(s, datetime):
        return _aware(s)
    return _aware(datetime.fromisoformat(str(s).replace("Z", "+00:00")))


def arm_lifecycle_step(prev: Mapping | None, cands: Sequence[tuple[datetime, float, bool]], now: datetime, *,
                       shrink_n: int = 0, rollback_r: float = 3.0,
                       close_r: float = ARM_CLOSE_R, reopen_r: float = ARM_REOPEN_R,
                       window_max: int = ARM_WINDOW_MAX, aile_ort: float | None = None,
                       cf_weight: float = 1.0) -> tuple[dict, str | None]:
    """Bir kurulumun bir gecelik adimi. `prev`: {"state": open|closed, "epoch_start": iso|None, "closed_at": iso|None}
    ya da None (acik, yeni). `cands`: (karar_ts, R, alindi_mi) — yalniz COZULMUS adaylar (alinan: gercek R; alinmayan:
    "alinsaydi" R). Donus: (yeni durum, olay) olay: None | closed | reopened | rolled_back.

    Kurallar (her biri ayni pencereyi kullanir: son `window_max` aday, yalniz `epoch_start` sonrasi):
      - acik: n > 0 ve sonumlu ortalama <= close_r  -> kapali (epoch = closed_at = now)
      - kapali, geri alma: kapanistan sonraki adaylarda sonumlu etki = -sumR (n) <= -rollback_r -> acik (epoch = now)
      - kapali, yeniden acma: sonumlu ortalama >= reopen_r -> acik (epoch = now)
    Geri alma kapanis kararini degerlendirir (kapanmis kurulum kaybettirdiyse, kapanis 3 R'yi asan kayip olarak geri
    alinir); yeniden acma karari yalniz ortalamaya bakar. Olaydan sonra yeni epoch baslar: eski adaylar sayilmaz.

    24.11 kullanici karari (ders hizi / aile destegi): `aile_ort` (ayni formasyonun, kolun kendisi HARIC diger ZD'lerdeki
    cozulmus adaylarinin sonumlu ortalamasi, `toplam R / (n_aile + shrink)`) verilirse (None/0 = aile yok) karar olcutu
    `m = (toplam_kol + shrink_n * aile_ort) / (n_kol + shrink_n)`; None/0 => bugunku davranis birebir. Aile verisi varken
    KAPATMA icin kolun kendi cozulmus adayi en az `ARM_KAPAT_MIN_N` ve en az `ARM_KAPAT_MIN_GUN` ayri gunden olmali (yalniz aile
    yuzunden kapanmaz). `cf_weight`: alinmayan ("alinsaydi") adayin toplamda ve sayida agirligi (varsayilan 1 = eski davranis;
    kurulum dersi 0,5 verir). Acma ve geri alma kurali degismez (geri alma -3 R sigortasi aynen)."""
    st = dict(prev or {})
    state = st.get("state") if st.get("state") in ("open", "closed") else "open"
    epoch = _arm_dt(st.get("epoch_start"))
    closed_at = _arm_dt(st.get("closed_at"))
    cs = sorted(((_aware(t), float(r), bool(tk)) for t, r, tk in cands), key=lambda c: c[0])
    win = [c for c in cs if epoch is None or c[0] >= epoch][-window_max:]
    n = len(win)
    wts = [1.0 if c[2] else float(cf_weight) for c in win]
    sum_w = math.fsum(w * c[1] for w, c in zip(wts, win))
    n_w = math.fsum(wts)
    aile = 0.0 if aile_ort is None or not math.isfinite(float(aile_ort)) else float(aile_ort)
    m = damped_mean(sum_w + max(0, int(shrink_n)) * aile, n_w, shrink_n)
    own_ok = aile == 0.0 or (n >= ARM_KAPAT_MIN_N and len({c[0].date() for c in win}) >= ARM_KAPAT_MIN_GUN)
    now = _aware(now)
    event = None
    if state == "open":
        if n > 0 and own_ok and m <= close_r + _EPS:
            state, epoch, closed_at, event = "closed", now, now, "closed"
    else:
        eff = damped_effect(-sum_w, n_w, shrink_n)
        if n > 0 and eff <= -rollback_r + _EPS:
            state, epoch, closed_at, event = "open", now, None, "rolled_back"
        elif n > 0 and m >= reopen_r - _EPS:
            state, epoch, closed_at, event = "open", now, None, "reopened"
    new = {"state": state, "epoch_start": epoch.isoformat() if epoch else None,
           "closed_at": closed_at.isoformat() if closed_at else None, "n": n,
           "mean_r": round(m, 4) if n else None, "last_event": event or st.get("last_event")}
    return new, event


def write_arms_state(path, arms: Mapping[str, Mapping], now: datetime) -> None:
    """`var/<bot>/arms_off.json` atomik yazimi (tmp + replace). Motor `arm_guard.load_arms_off` ile okur:
    {"schema": 1, "updated_at": iso, "arms": {arm_id: {state, epoch_start, closed_at, n, mean_r, last_event}}}."""
    doc = {"schema": ARM_STATE_SCHEMA, "updated_at": _aware(now).isoformat(),
           "arms": {k: dict(v) for k, v in sorted(arms.items())}}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def read_arms_state(path) -> dict[str, dict]:
    """Son yazilmis kurulum durumu ({arm_id: durum}); dosya yoksa ya da bozuksa {} (acik varsayilir)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        arms = doc.get("arms") if isinstance(doc, dict) else None
        return {str(k): dict(v) for k, v in arms.items()} if isinstance(arms, dict) else {}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}
