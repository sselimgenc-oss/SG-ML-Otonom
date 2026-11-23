"""Seans disi giris kapisi (23.11 kullanici karari, fikir 9 a): YALNIZ YENI giris; acik pozisyonlara dokunmaz, kripto etkilenmez.
Saf fonksiyonlar + stdlib (zoneinfo); trader_core import YOK; saat disaridan verilen karar zamani D (datetime.now yok).

  1. hafta sonu : emtia Cum 21:00 -> Paz 22:00 UTC; hisse Cum 16:00 ET (kapanis) -> Pzt 09:30 ET (acilis), ET->UTC DST'ye gore.
  2. tatil      : takvimdeki NYSE tam gun tatilleri: onceki islem gunu 16:00 ET kapanisindan sonraki islem gunu 09:30 ET acilisina kadar
                  (hisse ve emtia; emtia icin de ayni NYSE listesi uygulanir).
  3. haber      : takvimdeki olaylar (FOMC/CPI/NFP): olaydan 2 sa once -> 30 dk sonra (hisse ve emtia).
Takvim config/seans_takvimi.json (mühürlü engine.*.json DEGIL). Eksik/bozuk takvim -> tatil ve haber engellemez (sayac); hafta sonu takvimsiz calisir."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CLASS_EMTIA = "emtia"
CLASS_HISSE = "hisse"

# Emtia (CME vadeli) hafta sonu kapanisi, UTC: Cuma 21:00 -> Pazar 22:00. (weekday: Pzt=0 ... Paz=6)
EMTIA_HS_BASLANGIC = (4, time(21, 0))
EMTIA_HS_BITIS = (6, time(22, 0))
# Hisse (ABD borsasi): kapanis 16:00 ET, acilis 09:30 ET; hafta sonu = Cuma kapanisindan Pazartesi acilisina.
NY = ZoneInfo("America/New_York")
HISSE_KAPANIS = time(16, 0)
HISSE_ACILIS = time(9, 30)
# Haber penceresi: olaydan once / sonra.
HABER_ONCE = timedelta(hours=2)
HABER_SONRA = timedelta(minutes=30)

KOD_HAFTA_SONU = "seans_disi_hafta_sonu"
KOD_TATIL = "seans_disi_tatil"
KOD_HABER = "seans_disi_haber"
SAYAC_TAKVIM_YOK = "seans_disi_takvim_yok"

DEFAULT_TAKVIM_YOLU = Path(__file__).resolve().parents[2] / "config" / "seans_takvimi.json"


@dataclass(frozen=True)
class Takvim:
    tatil_pencereleri: tuple[tuple[datetime, datetime], ...]
    olaylar: tuple[datetime, ...]


def yukle(path: str | Path | None = None) -> Takvim | None:
    """Okunamaz/bozuk/bos -> None (cagiran engellemez + sayar)."""
    p = Path(path) if path is not None else DEFAULT_TAKVIM_YOLU
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        tatiller = {date.fromisoformat(str(t["tarih"])) for t in raw["tatiller"]}
        olaylar = tuple(sorted(datetime.fromisoformat(str(o["ts"]).replace("Z", "+00:00")).astimezone(timezone.utc)
                               for o in raw["olaylar"]))
        if not tatiller and not olaylar:
            return None
        return Takvim(_tatil_pencereleri(tatiller), olaylar)
    except Exception:  # noqa: BLE001 - fail-open (ek kapi)
        return None


def _islem_gunu(d: date, tatiller: set[date], adim: int) -> date:
    d += timedelta(days=adim)
    while d.weekday() >= 5 or d in tatiller:
        d += timedelta(days=adim)
    return d


def _tatil_pencereleri(tatiller: set[date]) -> tuple[tuple[datetime, datetime], ...]:
    out = []
    for h in sorted(tatiller):
        onceki, sonraki = _islem_gunu(h, tatiller, -1), _islem_gunu(h, tatiller, 1)
        out.append((datetime.combine(onceki, HISSE_KAPANIS, tzinfo=NY).astimezone(timezone.utc),
                    datetime.combine(sonraki, HISSE_ACILIS, tzinfo=NY).astimezone(timezone.utc)))
    return tuple(out)


def hafta_sonu_mu(cls: str, D: datetime) -> bool:
    if cls == CLASS_EMTIA:
        u = D.astimezone(timezone.utc)
        wd, hm = u.weekday(), u.time()
        return wd == 5 or (wd == EMTIA_HS_BASLANGIC[0] and hm >= EMTIA_HS_BASLANGIC[1]) or (
            wd == EMTIA_HS_BITIS[0] and hm < EMTIA_HS_BITIS[1])
    if cls == CLASS_HISSE:
        t = D.astimezone(NY)
        wd, hm = t.weekday(), t.time()
        return (wd == 4 and hm >= HISSE_KAPANIS) or wd in (5, 6) or (wd == 0 and hm < HISSE_ACILIS)
    return False


def karar(cls: str, D: datetime, takvim: Takvim | None) -> str | None:
    """Engelleyen veto kodu veya None. Bilinmeyen/kripto sinif -> None. D tz-bilincli olmali."""
    if cls not in (CLASS_EMTIA, CLASS_HISSE):
        return None
    if D.tzinfo is None:
        raise ValueError("D tz-bilincli olmali")
    if hafta_sonu_mu(cls, D):
        return KOD_HAFTA_SONU
    if takvim is None:
        return None
    u = D.astimezone(timezone.utc)
    if any(a <= u < b for a, b in takvim.tatil_pencereleri):
        return KOD_TATIL
    if any(o - HABER_ONCE <= u < o + HABER_SONRA for o in takvim.olaylar):
        return KOD_HABER
    return None
