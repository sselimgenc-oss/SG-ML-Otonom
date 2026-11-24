# Ortak öğrenme paketi — parça 2: karne + sanal kasa, ortak filtre (ridge-lojistik) + paket, drift (CUSUM)

> **[24 Kasım 2026]** `filtre.py` (ortak filtre) silindi (kullanıcı kararı: ML filtreleri kaldırıldı); `karne.py` ve `drift.py` geçerlidir. §2 ve filtre testleri yalnız tarihçedir.

Parça 1 ile aynı paket (`trader/paket/ortak_ogrenme/`), sürüm `1.1.0`. Girdi her yerde parça 1'in `kayit.Aday` nesneleri. İlke aynı: **yalnız puan/rapor**; engelleme kararı adaptörün.
Bağımlılık: `karne.py` ve `drift.py` yalnız standart kütüphane; `filtre.py` **numpy** ister (içe aktarma yalnız bu modülde).

## 1. `karne.py`
- `karne(adaylar, kurulumlar=()) -> dict[str, dict]`: kurulum başına `{"aday": n, "alinan": n_alindi, "cozulen": r'si olan, "ort_r_alinan": alınanların r ortalaması | None, "ort_r_tum": r'si olan tümünün ortalaması | None, "sinif": {varlik_sinifi: aynı alanlar (kasa hariç)}, "kasa": sanal_kasa(...)[kurulum]}`. `kurulumlar` listesindeki adaysız kurulumlar da sıfır satırla yer alır; sıra: önce `kurulumlar`, sonra görülme sırası.
- `sanal_kasa(adaylar, *, baslangic=1000.0, risk=0.01, kurulumlar=()) -> dict`: ML'deki `counterfactual.arm_virtual_bankroll` ile **birebir aynı** kural: kurulum başına `{"alinan": seri, "tum": seri}`, seri `{"n", "kasa", "getiri_pct", "en_derin_pct"}`; ts'ye göre kararlı sıralama, `eq = max(0, eq*(1+risk*r))`, 2 ondalık; `baslangic<=0` ya da `risk<=0` → `ValueError`.
- Ortalama tanımı ML `_arm_block` ile aynı (`_mean_or_none`).

## 2. `filtre.py` (numpy)
- `fit_logistic(X, y, ridge=5.0, iters=40) -> dict`: ML `trader_ml/setup_filter/train.py::fit_logistic` ile **sayısal olarak aynı** (Newton/IRLS, kesişim cezasız, NaN doldurma ortalamayla, std<1e-12 → 1).
- `ozellik_adlari(adaylar) -> list[str]`: adayların `ozellikler` anahtarlarının sıralı birleşimi (sayı olmayan değerler yok sayılır).
- `matris(adlar, adaylar) -> np.ndarray`: eksik/sayı olmayan → NaN.
- `egit(kurulum, adaylar, *, olusturma=None, kilit=(), azami=50000) -> dict | None`: yalnız `alindi` ve `r is not None` adaylar; `kilit`: `[(baslangic, bitis), ...]` tz'li aralıklar — `ts` bu aralıklardaysa satır eğitimden **düşer** (sayılır: `meta.kilit_dusen`). Son `azami` satır (ts sıralı). Etiket `r > 0`. Veri yok ya da tek sınıf → `None`. Eşik = `0.9 * taban_oran`.
- Paket biçimi (JSON): `{"meta": {...}, "model": <fit_logistic sözlüğü>, "esik": float}`; `meta`: `paket_surumu=1, tur="ortak_filtre", kurulum, olusturma (ISO), son_kullanma (olusturma+21 gün), ozellikler, ozellik_hash (sha256 "\n".join), n_egitim, n_pozitif, taban_oran, kilit_dusen, model_hash` (`model_hash` = sha256 of canonical JSON (`sort_keys`, `separators=(",",":")`) of `{"model":..., "esik":...}`).
- `kaydet(paket, klasor) -> Path`: `<güvenli_ad>.json`, eskisi `.prev.json`; atomik; yazmadan önce `yukle` ile gidiş-dönüş doğrulaması. Güvenli ad: `[^A-Za-z0-9._@-]` → `_`; boş ya da `.` ile başlayan → `ValueError`.
- `yukle(yol_ya_da_sozluk, *, simdi=None, sure_kontrol=True) -> dict`: hash ve özellik hash'i tutmazsa ya da süresi dolmuşsa `PaketHatasi(ValueError)`.
- `puan(paket, ozellikler: Mapping[str, float]) -> float`: standardize + sigmoid (z [-35, 35] kırpılır); eksik özellik `fill` değeriyle. 0..1.

## 3. `drift.py`
- ML `trader_core/drift_monitor.py` ile aynı sabitler: `CUSUM_MU0=-0.111, CUSUM_SIGMA0=1.224, CUSUM_K=0.5, CUSUM_CLIP=(-1.5, 3.0), CUSUM_UYARI=4.0, CUSUM_COOLDOWN=30, MIN_N=20`.
- `cusum(rs) -> dict`: ML `cusum_replay` ile birebir: `{"S", "n", "cooldown", "alarms": [1-tabanlı indeksler]}`.
- `kurulum_drift(adaylar) -> dict[str, dict]`: kurulum başına alınan ve r'si olan adayların (ts sıralı) r dizisiyle `cusum`; ek alan `"durum": "uyari"` (son alarm varsa ve son alarmdan beri < 30 işlem) | `"normal"`.

## 4. Eşdeğerlik testleri (ML ile)
- `karne`/`sanal_kasa` ↔ `counterfactual.arm_scorecard` / `arm_virtual_bankroll` (alan adı eşlemesiyle).
- `fit_logistic` ↔ `trader_ml.setup_filter.train.fit_logistic` (rastgele veri, NaN dahil; katsayılar `allclose`).
- `cusum` ↔ `drift_monitor.cusum_replay`.

## 5. README
Parça 2 bölümü: hangi modül numpy ister, filtrenin yalnız puan verdiği, kilit aralıklarının (holdout) eğitimden yapısal olarak düştüğü.
