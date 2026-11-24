"""Model paketi okuyucu (M1 paketleri): motor tarafi. Yalniz stdlib + numpy; trader_ml/lightgbm/sklearn/scipy yok.

`load_package`: kapidan gecmemis (`meta.gate_passed` True degil) ya da esiksiz paket REDDEDILIR; hash'ler tutmali; 21 gunu asan
paket REDDEDILIR. `MlModelView` paketten yuklenmis SALT OKUNUR modeldir (`PackageSet.view`)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from .ml_eval import TreeModel

MODEL_EXPIRY_DAYS = 21


class PackageError(ValueError):
    pass


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def feature_list_hash(names: list[str]) -> str:
    return sha256_text("\n".join(names))


def _utc(s: str) -> datetime:
    d = datetime.fromisoformat(s)
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def expires_at(pkg: dict) -> datetime:
    """Gecerlilik siniri: meta.expires_at ile created_at + 21 gunun ERKENI (uzatilmis expires_at dolanamaz)."""
    meta = pkg["meta"]
    lim = _utc(meta["expires_at"])
    try:
        lim = min(lim, _utc(meta["created_at"]) + timedelta(days=MODEL_EXPIRY_DAYS))
    except (KeyError, ValueError, TypeError):
        pass
    return lim


def is_expired(pkg: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return now >= expires_at(pkg)


def load_package(path: str | Path | dict, *, now: datetime | None = None, check_expiry: bool = True,
                 require_gate: bool = True) -> dict:
    """Okur, hash'leri dogrular (tutmuyorsa PackageError), suresi dolmussa PackageError. Kapidan gecmemis
    (meta.gate_passed true degil) ya da esiksiz paket require_gate=True iken REDDEDILIR; yalniz egitim hatti
    kendi gidis-donus kontrolunde ve inceleme icin require_gate=False kullanir."""
    pkg = path if isinstance(path, dict) else json.loads(Path(path).read_text(encoding="utf-8"))
    meta = pkg["meta"]
    if require_gate:
        if meta.get("gate_passed") is not True:
            raise PackageError(f"paket kapidan gecmedi (gate_passed={meta.get('gate_passed')!r}); yuklenemez")
        if pkg.get("threshold") is None:
            raise PackageError("paketin esigi yok (threshold null); yuklenemez")
    body = {"model": pkg["model"], "calibration": pkg["calibration"], "threshold": pkg["threshold"]}
    if sha256_text(canon(body)) != meta["model_hash"]:
        raise PackageError("model hash tutmuyor")
    if feature_list_hash(meta["features"]) != meta["feature_list_hash"]:
        raise PackageError("ozellik listesi hash tutmuyor")
    if check_expiry and is_expired(pkg, now):
        raise PackageError("model suresi dolmus")
    return pkg


@dataclass(frozen=True)
class MlModelView:
    """Stratejiye salt okunur verilen yuklenmis model (05 §13.2). Dosya/ag/saat gormez; `expired(D)` karar anina gore."""
    model_id: str
    threshold: float
    features: tuple[str, ...]
    expires_at: datetime
    user_approved: bool
    _tree: TreeModel = field(repr=False, compare=False)

    def expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def score(self, X) -> np.ndarray:
        """X: (n, len(features)) sutun sirasi `features` ile ayni; kalibre olasilik (n,)."""
        return self._tree.predict_proba(X)


def view_from_package(pkg: dict) -> MlModelView:
    meta = pkg["meta"]
    thr = pkg["threshold"]
    return MlModelView(
        model_id=f"{meta.get('version', '?')}@{meta['model_hash'][:12]}", threshold=0.5 if thr is None else float(thr),
        features=tuple(meta["features"]), expires_at=expires_at(pkg), user_approved=meta.get("user_approved") is True,
        _tree=TreeModel(pkg["model"], pkg["calibration"]))


# ---------------------------------------------------------------------------------------------------------------------
# DD-12 WP-10: CELI PAKET (arm_id basina) + SICAK YUKLEME. Motor API'si:
#   ps = PackageSet(models_dir)                 # models_dir/<guvenli_arm_id>.json ; <...>.prev.json yedektir (yuklenmez)
#   ps.reload(now=...)        -> {"loaded": [...], "removed": [...], "rejected": {arm: neden}}   (bar kapanisinda cagir; dosya
#                                degismediyse (mtime_ns, size) ucuz atlanir; bozuk/suresi dolmus paket YALNIZ o kolu paketsiz birakir,
#                                oncekini silmez ama suresi dolmussa kullanmaz; motor hic durmaz)
#   ps.view(arm_id)           -> MlModelView | None   (puan: view.score(X); paket yoksa None)
# `paper_only` paketler (meta.paper_only) yalniz `allow_paper_only=True` ile yuklenir (testnet/canliya kapidan gecmemis model yuklenmez).
# ---------------------------------------------------------------------------------------------------------------------
def safe_arm_name(arm_id: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._@-]", "_", str(arm_id))
    if not s or s.startswith("."):
        raise ValueError(f"gecersiz arm_id: {arm_id!r}")
    return s


class PackageSet:
    def __init__(self, models_dir: str | Path, *, allow_paper_only: bool = True,
                 fallback_dirs: tuple[str | Path, ...] = ()) -> None:
        # models_dir: calisma zamani dizini (gece egitimi burayi yazar); fallback_dirs: depodaki tohum (seed) paketler.
        # Ayni dosya adi iki dizinde de varsa calisma zamani kazanir; yalniz tohumda olan dosya tohumdan yuklenir.
        self.dir = Path(models_dir)
        self.fallback_dirs = tuple(Path(d) for d in fallback_dirs)
        self.allow_paper_only = allow_paper_only
        self._views: dict[str, MlModelView] = {}
        self._sig: dict[str, tuple] = {}
        self._rejected: dict[str, str] = {}

    def arms(self) -> list[str]:
        return sorted(self._views)

    def rejected(self) -> dict[str, str]:
        return dict(self._rejected)

    def view(self, arm_id: str) -> MlModelView | None:
        return self._views.get(arm_id)

    def reload(self, *, now: datetime | None = None) -> dict:
        loaded, removed = [], []
        files: dict[str, Path] = {}
        for d in (self.dir, *self.fallback_dirs):          # calisma zamani once; tohum yalniz eksik dosyayi tamamlar
            if not d.is_dir():
                continue
            for p in sorted(d.glob("*.json")):
                if p.name.endswith(".prev.json") or p.name.startswith(".") or p.name in files:
                    continue
                files[p.name] = p
        new_views: dict[str, MlModelView] = {}
        new_sig: dict[str, tuple] = {}
        rejected: dict[str, str] = {}
        by_file = {self._file_of(a): a for a in self._views}
        for name, p in files.items():
            try:
                st = p.stat()
                sig = (st.st_mtime_ns, st.st_size)
                prev_arm = by_file.get(name)
                if prev_arm is not None and self._sig.get(prev_arm) == sig and not is_expired(
                        {"meta": {"expires_at": self._views[prev_arm].expires_at.isoformat()}}, now):
                    new_views[prev_arm], new_sig[prev_arm] = self._views[prev_arm], sig
                    continue
                pkg = load_package(p, now=now)
                meta = pkg["meta"]
                if meta.get("paper_only") is True and not self.allow_paper_only:
                    raise PackageError("paper_only paket bu modda yuklenemez")
                arm = meta.get("arm_id")
                if not arm or safe_arm_name(arm) + ".json" != name:
                    raise PackageError("meta.arm_id dosya adiyla uyusmuyor")
                new_views[arm], new_sig[arm] = view_from_package(pkg), sig
                loaded.append(arm)
            except (PackageError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
                rejected[name[:-5]] = f"{type(e).__name__}: {e}"
        removed = sorted(set(self._views) - set(new_views))
        self._views, self._sig, self._rejected = new_views, new_sig, rejected      # referans atamasi: okuyucular eski ya da yeni gorur
        return {"loaded": sorted(loaded), "removed": removed, "rejected": dict(rejected)}

    @staticmethod
    def _file_of(arm_id: str) -> str:
        return safe_arm_name(arm_id) + ".json"
