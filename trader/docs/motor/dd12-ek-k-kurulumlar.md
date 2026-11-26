# DD-12 Ek-K: Yeni kurulumların kesin tanımı (TF1, B1, F1, S1, H2)

> **Not (sahip kararı, 26.11):** Kazanç/risk tabanı ve ATR cinsinden stop üst sınırı kütüphane kurulumlarında BİLEREK yoktur (sahip kararı, 26.11): ML1 zayıf oranlı adayları da görür; `rr_below_min` burada yalnız "hedef yanlış tarafta" demektir.

**Tarih:** 19 Kasım 2026 · **Yazan:** mentor · **Bağlı:** `dd12-capraz-varlik-spec.md` §3, §9 (WP-12a/12b), §12 (D-T17); katalog `otonom-trading-arastirma/price-action-kural-katalogu.md`; sözleşme `strategies/arms/__init__.py` (`2dc9d5c`).
**Durum:** WP-12a/12b bu belgeyle başlayabilir. Bütün sayılar **başlangıç değeridir, ayarlanmamıştır** (katalogdaki "varsayılan"lar dahil); kâğıtta deney etiketiyle çalışır, kârlılık iddiası yoktur.
**Kullanıcı kararlarına uyum:** her kurulum 15dk / 1s / 4s / 1g'de açıktır (`TIMEFRAMES` dördü de; §3 tablosundaki dar zaman dilimi sütununun yerine geçer); 44 enstrüman; seans yasağı yok; eleme ML ve dersin işidir, bu belge yalnız aday üretir.

## K-0. Ortak kurallar

**Gösterim.** `t` = son **kapanmış** tetik barı (`inp.trig` son satırı); `o,h,l,c` o zaman diliminin değerleri. Bütün pencereler kapalı aralıktır ve `t`'den ileriye bakmaz. `ATR` = `indicators.atr(trig, 14)[t]`; `EMAn` = `indicators.ema(close, n)[t]`; `body = |c−o|/(h−l)`. `rejim` = ortak tablonun `regime` sütunu (4s rejimi, o bara hizalı). Aşağıda yalnız **long** yazılır; **short tam aynadır** (`h↔l`, `max↔min`, `>↔<`, işaretler ters, `trend_up↔trend_down`).

| Kural | Tanım |
|---|---|
| Giriş | Sinyal barı kapanışında piyasa emri: `planned_entry = c[t]` (katalogdaki "(a) kapanışta piyasa" varyantı; stop/limit emirli varyantlar bu sürümde yok). |
| Stop genişliği | `sda = |c − stop| / ATR`; `sda < 0,5` ya da `sda > SDA_MAX` (kurulum başına) → satır yazılır, `signal=False`, `skip_reason="stop_width"`. |
| Ödül/risk | Hedefli kurulumda `rr = (hedef − c)/(c − stop)`; `rr < params.rr_min` (1,5) → `skip_reason="rr_below_min"`. Başka atlama kodu kullanılmaz (`base._SKIP_OK`). |
| Geçersiz girdi | `h−l ≤ 0`, `ATR ≤ 0`, kullanılan herhangi bir değer NaN, `len(trig) < LOOKBACK[tf]` → o satırda aday yok (`setup=None`); hata fırlatılmaz (D-T17 "yalnız o kurulum bekler"). |
| Çift yön | Aynı barda long ve short koşulu birlikte sağlanırsa aday yok (`reasons="<kod>:both_sides"`). |
| `volatile` rejim | Beş kurulumda da aday yok (PA-FLT-03). `unclear` ve `range` kurulum başına aşağıda. |
| Çıkış kipi | `EXIT_MODE="trail"`: T1 yolu (1R ilerlemeden sonra `trail_atr`×ATR iz süren stop, `regime_flip` çıkışı; hedef yok). `EXIT_MODE="target"`: R1 yolu (hedef + 48 bar zaman durdurma, bar = kurulumun zaman dilimi). |
| Ortak parametreler | `inp.params.stop_buffer_atr` (0,3), `rr_min` (1,5), motorun `trail_atr` (3,0) aynen kullanılır; kuruluma özel sabitler arm dosyasında modül sabitidir (ders bunları WP-13'ten önce değiştiremez). |

**Zaman dilimine bağlı pencereler** (1g ısınması 50 bar olduğu için kısa):

| Sabit | 15dk / 1s / 4s | 1g | Kullanan |
|---|---|---|---|
| `N_BRK` (kapanış kırılım penceresi) | 50 | 20 | TF1 |
| `EMA_F / EMA_S` | 20 / 50 | 10 / 30 | TF1 |
| `N_LVL` (seviye penceresi) | 40 | 20 | B1, F1 |
| `LOOKBACK` | TF1 120, B1 70, F1 60, S1 45, H2 60 | TF1 50, B1 45, F1 40, S1 45, H2 45 | hepsi |

## K-1. TF1 — trend yönünde kapanış kırılımı (momentum devamı)

- **Katalog:** PA-YAP-03 (kapanış bazlı BOS), PA-KIR-01 (N-bar kapanış kırılımı, net kırılım 0,2 ATR, gövde filtresi), PA-FLT-01/02 (üst zaman dilimi + MA yön filtresi), PA-FLT-04 (aşırı uzama), PA-STP-02a (ATR iz süren). Not: PA-YAP-03 "BOS'ta girme, geri çekilme bekle" der; o yol T1/H2'dir, TF1 bilerek TE'nin doğrudan kırılım varyantıdır.
- **Giriş (long), hepsi `t` barında:**
  1. `rejim == trend_up`
  2. `c > EMA_S` ve `EMA_F > EMA_S`
  3. `HC(k) = max(c[k−N_BRK .. k−1])`; `brk(k) = c[k] > HC(k) + 0,2·ATR[k]`; şart: `brk(t)` ve `not brk(t−1)` (taze kırılım)
  4. `c > o` ve `body ≥ 0,5`
  5. `ext = (c − EMA_S)/ATR ≤ 3,0`
- **Stop:** `HC(t) − 1,0·ATR` (kırılan seviyenin 1 ATR ötesi; TE). `SDA_MAX = 3,0`. **Hedef:** yok. **Çıkış:** `EXIT_MODE="trail"`.
- **Geçersizlik (aday üretilmez):** 3. koşulda `brk(t−1)` doğru; rejim `range/unclear/volatile` ya da ters trend.
- **Parametreler:** `N_BRK` 50/20, `EMA_F/S` 20/50 (1g 10/30), `BRK_ATR` 0,2, `BODY_MIN` 0,5, `EXT_MAX` 3,0, `STOP_ATR` 1,0.
- **`features`:** `brk_dist_atr` = `(c − HC)/ATR`, `ema_value` = `EMA_S`, `body_ratio`, `ext_atr`, `brk_n` = `N_BRK`.

## K-2. B1 — seviye kırılımı + yeniden test

- **Katalog:** PA-SDR-01/02 (yatay seviye, dokunma sayısı), PA-KIR-01 (kapanışla kırılım), PA-KIR-02 varyant (a) (retest, pencere 10 bar, bant 0,25 ATR, seviye altı kapanış geçersiz kılar), PA-STP-01 (retest dibi − tampon), PA-HDF-01 (2R), PA-STP-03.
- **Kırılım barı `i0` (long):** `RH(k) = max(h[k−N_LVL+1 .. k])`, `L = RH(i0−1)`;
  1. `c[i0] > L + 0,2·ATR[i0]` ve `c[i0−1] ≤ RH(i0−2) + 0,2·ATR[i0−1]`; `body[i0] ≥ 0,5`
  2. Seviye yaşı: `L`'yi veren barın (en son azami) indeksi `≤ i0 − 3`
  3. Dokunma: `[i0−N_LVL, i0−1]` içinde `h[k] ≥ L − 0,25·ATR[i0]` olan barların **ayrık koşu** sayısı `≥ 2`
- **Giriş (long) `t` barında:** `i0` = `1 ≤ t−i0 ≤ 10` aralığındaki **en son** kırılım barı;
  1. `(i0, t]` içinde en az bir `l[k] ≤ L + 0,25·ATR[k]` (retest dokunuşu)
  2. `(i0, t]` içindeki bütün `c[k] ≥ L`
  3. `c[t] > o[t]` ve `c[t] > L`
  4. `(i0, t)` içinde bu kırılım için B1 sinyali verilmemiş (kırılım başına tek sinyal)
  5. `rejim ∈ {trend_up, range, unclear}`
- **Stop:** `min(l[i0+1 .. t]) − stop_buffer_atr·ATR`. `SDA_MAX = 2,5`. **Hedef:** `c + 2,0·(c − stop)` (`rr = 2,0`). **Çıkış:** `EXIT_MODE="target"`.
- **Geçersizlik:** `(i0, t]` içinde `c[k] < L` → o kırılım ölür (yeni kırılım barı gerekir); pencere (10 bar) dolar; arada ters yönde kırılım barı oluşur.
- **Parametreler:** `N_LVL` 40/20, `BRK_ATR` 0,2, `TOUCH_ATR` 0,25, `MIN_TOUCH` 2, `LVL_AGE_MIN` 3, `RETEST_W` 10, `RETEST_ATR` 0,25, `TARGET_R` 2,0.
- **`features`:** `level` = `L`, `brk_dist_atr` = `(c[i0] − L)/ATR[i0]`, `retest_depth_atr` = `(min(l[i0+1..t]) − L)/ATR`, `body_ratio`, `bars_since_brk` = `t − i0`, `rr`.

## K-3. F1 — sahte kırılım / SFP dönüşü

- **Katalog:** PA-KIR-03 (seviyeyi delip geri kapanış; tampon 0,1 ATR; dönüş penceresi 2 bar; derinlik > 1,5 ATR ise atla), PA-YAP-01 (fraktal swing, N=2), PA-MUM-01 (ret fitili ölçüsü), PA-STP-01 (sinyal ekstremi − 0,2 ATR), PA-HDF-02 (önceki swing / karşı kenar, 0,2 ATR içeride).
- **Seviye (long):** `A = min(l[t−N_LVL .. t−5])`, `k*` = bu asgarinin en son indeksi; şart `k* ≥ t−N_LVL+2` (pencere kenarında değil → `A` iki yanında 2'şer bar olan gerçek bir swing dibidir).
- **Giriş (long) `t` barında:** `s` = `{t−1, t}` içinde `l`'si düşük olan (eşitlikte `t`); `Lsw = min(l[s..t])`, `Hsw = max(h[s..t])`;
  1. Süpürme: `Lsw < A − 0,1·ATR` ve `c[t−2] ≥ A`
  2. Geri alma: `c[t] > A` ve `c[t] > o[t]`
  3. Ret gücü: `rej = (c[t] − Lsw)/(Hsw − Lsw) ≥ 0,6`
  4. Derinlik: `(A − Lsw)/ATR ≤ 1,5`
  5. `t−1` barında aynı yönde F1 sinyali yok
  6. `rejim ∈ {range, unclear, trend_up}` (trend karşıtı süpürme dönüşü bu sürümde yok)
- **Stop:** `Lsw − 0,2·ATR`. `SDA_MAX = 2,0`. **Hedef:** `max(h[t−20 .. t−1]) − 0,2·ATR`; hedef `≤ c` ise `rr ≤ 0` sayılır → `rr_below_min`. **Çıkış:** `EXIT_MODE="target"`.
- **Geçersizlik:** `c[t] ≤ A` (gerçek kırılım: bu bar B1/TF1 short adayı olabilir); süpürmeden sonra 2 barda geri alma yok.
- **Parametreler:** `N_LVL` 40/20, `LVL_GAP` 5, `SWEEP_ATR` 0,1, `REJ_MIN` 0,6, `DEPTH_MAX` 1,5, `STOP_ATR` 0,2, `TGT_WIN` 20, `TGT_IN_ATR` 0,2.
- **`features`:** `level` = `A`, `sweep_depth_atr` = `(A − Lsw)/ATR`, `rej_ratio`, `body_ratio`, `level_age` = `t − k*`, `rr`.

## K-4. S1 — sıkışma kırılımı (iç bar / NR7 kutusu; bayrak devamı)

- **Katalog:** PA-MUM-05 (iç bar, NR7), PA-TRD-04 (birikim: M bar toplam aralık ≤ 3 ATR; birikim üstü kırılım; 3 ATR iz süren), PA-YTY-05 (dar sıkışma, çıkış barı), PA-KIR-07 (bayrak: güçlü bacak + konsolidasyon; çizgi tanımı öznel olduğu için kutu ile sayısallaştırıldı; stop konsolidasyonun karşı ucu − 0,2 ATR), PA-FLT-03.
- **Kutu (`t−1` itibarıyla):** barlar `t−8 .. t−1`; `BH = max(h)`, `BL = min(l)`; `A0 = ATR[t−9]` (kutu öncesi ATR; sıkışmanın kendi ATR'sini küçültmesi ölçüyü bozmasın);
  1. `(BH − BL) ≤ 3,0·A0`
  2. `nr_count ≥ 1`: `k ∈ {t−3, t−2, t−1}` içinde `iç(k)` ya da `NR7(k)` olan bar sayısı; `iç(k): h[k] ≤ h[k−1] ve l[k] ≥ l[k−1]`; `NR7(k): (h−l)[k] = min((h−l)[k−6 .. k])`
- **Giriş (long) `t` barında:**
  1. `c > BH + 0,1·ATR`, `c > o`, `body ≥ 0,5`
  2. `rejim ∈ {trend_up, range, unclear}` (4s trendine karşı kırılım yok)
  3. `t−3 .. t−1` barlarında aynı yönde S1 sinyali yok
- **Bayrak ölçüsü (koşul değil, özellik):** `pole_atr = (c[t−9] − c[t−19])/A0`, işlem yönüne göre işaretli; `≥ +2` "bayrak devamı" demektir, ML/ders ayırır.
- **Stop:** `BL − 0,2·ATR`. `SDA_MAX = 3,0`. **Hedef:** yok. **Çıkış:** `EXIT_MODE="trail"`.
- **Geçersizlik:** kutu genişliği > 3·A0; `nr_count = 0`; kapanış kutu içinde (fitille kırılım sayılmaz).
- **Parametreler:** `BOX_M` 8, `BOX_W_ATR` 3,0, `NR_WIN` 3, `NR_N` 7, `BRK_ATR` 0,1, `BODY_MIN` 0,5, `POLE_P` 10, `COOLDOWN` 3, `STOP_ATR` 0,2.
- **`features`:** `box_w_atr` = `(BH−BL)/A0`, `box_edge` = `BH` (short: `BL`), `pole_atr`, `body_ratio`, `nr_count`.

## K-5. H2 — trendde iki bacaklı geri çekilme (ek aile; mentor seçimi)

- **Neden:** katalogda en çok kaynaklı trend girişlerinden (BR, MI); T1'den farkı EMA'ya dokunma değil **yapı sayımı**dır, T1'in kaçırdığı sığ geri çekilmeleri yakalar.
- **Katalog:** PA-TRD-02 (H1/H2 sayımı, pencere ≤ 20 bar), PA-FLT-02 (`c > EMA20`, EMA20 yukarı), PA-YAP-05 (geri çekilme derinliği), PA-STP-01 (geri çekilme dibi − tampon), PA-STP-02.
- **Sayım (long):** `s` = `[t−20, t−3]` içinde `h`'si en yüksek barın en son indeksi (geri çekilme başlangıcı). `(s, t]` içinde `yukarı(k): h[k] > h[k−1]`, `aşağı(k): h[k] < h[k−1]`. `k1` = öncesinde `(s, k1)` içinde en az bir `aşağı` bulunan ilk `yukarı` bar (H1). `k2` = `(k1, k2)` içinde en az bir `aşağı` bulunan, `k1`'den sonraki ilk `yukarı` bar (H2).
- **Giriş (long) `t` barında:**
  1. `t == k2` ve `k2 − k1 ≤ 10`
  2. `c[t] > h[t−1]` (kapanış teyidi; fitille geçiş yetmez) ve `c[t] > o[t]`
  3. `rejim == trend_up`, `c > EMA20`, `EMA20[t] > EMA20[t−5]`
  4. Derinlik: `pb = (h[s] − min(l[s+1 .. t]))/ATR ≥ 1,0`
- **Stop:** `min(l[s+1 .. t]) − stop_buffer_atr·ATR`. `SDA_MAX = 2,5`. **Hedef:** yok. **Çıkış:** `EXIT_MODE="trail"`.
- **Geçersizlik:** `(s, t]` içinde `c[k] < EMA50[k]` (geri çekilme trendi bozdu; 1g'de `EMA30`); `t−s > 20`; H1'de giriş yapılmaz.
- **Parametreler:** `PB_WIN` 20, `PB_MIN_BARS` 3, `LEG_GAP_MAX` 10, `EMA_TREND` 20, `EMA_SLOPE_LAG` 5, `PB_MIN_ATR` 1,0, `EMA_GUARD` 50/30.
- **`features`:** `ema_value` = `EMA20`, `pb_depth_atr`, `pb_bars` = `t − s`, `body_ratio`, `leg_gap` = `k2 − k1`.

## K-6. Rejim uyumu ve öncelik

| Kurulum | trend (aynı yön) | trend (ters yön) | range | unclear | volatile | Çıkış kipi |
|---|---|---|---|---|---|---|
| T1 (mevcut) | evet | hayır | hayır | hayır | hayır | trail |
| R1 (mevcut) | hayır | hayır | evet | hayır | hayır | target |
| TF1 | evet | hayır | hayır | hayır | hayır | trail |
| B1 | evet | hayır | evet | evet | hayır | target |
| F1 | evet | hayır | evet | evet | hayır | target |
| S1 | evet | hayır | evet | evet | hayır | trail |
| H2 | evet | hayır | hayır | hayır | hayır | trail |

**Öncelik (aynı çift, aynı karar adımı):** (1) büyük zaman dilimi kazanır (§3, değişmedi). (2) Aynı zaman diliminde sıra sabittir: **`T1` > `R1` > `TF1` > `B1` > `H2` > `S1` > `F1`**. Gerekçe: T1/R1 puanlı (r03) ve geçmişi olan kurulumlardır, D-T18 eşdeğerliği bozulmaz; trend yönlüler dönüş kurulumundan önce gelir. Yön fark etmez (ör. `F1` short ile `TF1` long aynı barda → `TF1` girer). Kaybedenler `arm_conflict` ile yazılır ve "alınsaydı" karnesine girer; hiçbir aday sessizce düşmez.
**Beklenen çakışmalar:** `T1`–`H2` (aynı geri çekilme; T1 kazanır), `TF1`–`S1` (sıkışmadan trend kırılımı; TF1 kazanır), `R1`–`F1` (range kenarı süpürmesi; R1 kazanır), `B1` long – `F1` short aynı seviyede **aynı barda olamaz** (`c > L` ile `c < L` birbirini dışlar; K-B1-6 testi).

## K-7. Uygulayıcıya notlar

**Sözleşmede kapatılması gereken üç boşluk (WP-12a'nın ilk adımı; `T1`/`R1` davranışı bit bit aynı kalmalı, altın testler ve D-T18 değişmeden geçmeli):**

1. **Çıkış kipi.** `position_manager.evaluate_exit` ve `trail_stop_value` kurulum adına gömülüdür (`pos.setup == "R1"` → hedef yolu; iz süren stop yalnız `pos.setup == "T1"` iken kurulur). Bugünkü kodla `TF1`/`S1`/`H2` pozisyonunda iz süren stop **hiç devreye girmez**, `B1`/`F1` hedefi **hiç denetlenmez**. Çözüm: arm dosyasına zorunlu `EXIT_MODE: "trail" | "target"` sabiti; `position_manager`'daki üç karşılaştırma kurulum adı yerine kipe bakar (`T1→trail`, `R1→target` aynı). Bilinmeyen kurulum bugünkü gibi `force_exit`. `counterfactual.py` aynı ayrımı WP-13'te alır.
2. **Özellikler.** Tablo şeması tam `SIGNAL_COLUMNS` olmak zorunda (`base.validate_table` küme eşitliği arar), yeni sütun eklenemez; `gates._features` yalnız T1/R1 anahtarlarını bilir. Çözüm: arm dosyasına `FEATURES: dict[str, str]` (defter anahtarı → taşıyıcı sütun); `gates._features` (ve `shadow._features`) kurulumun eşlemesini okur. Taşıyıcılar: `ema_value`, `body_ratio`, `wick_ratio`, `edge_dist_atr`, `rr` (float), `pullback_ema` (int). **`rh`, `rl`, `rh_touches`, `rl_touches` taşıyıcı yapılmaz** (rejim anlamı var, pozisyona kopyalanıyor). Eşleme: her kurulumun `features` listesindeki sıra ile `ema_value`/`level`/`box_edge` → `ema_value`; `*_dist_atr`/`*_depth_atr`/`box_w_atr` → `edge_dist_atr`; `ext_atr`/`retest_depth_atr`/`rej_ratio`/`pole_atr`/`pb_bars` → `wick_ratio`; `body_ratio` → `body_ratio`; tamsayılar (`brk_n`, `bars_since_brk`, `level_age`, `nr_count`, `leg_gap`) → `pullback_ema`; `rr` → `rr`. Zorunlu ortak anahtarlar (`atr_tf`, `stop_dist_atr`, `atr_4h`, `rh_touches`, `rl_touches`) aynen yazılır. Defter (`_prep_features`) değişmez.
3. **Aynı zaman diliminde sıra.** `strategy_runner` eşitlikte tablo anahtarına göre alfabetik sıralıyor (`"B1" < … < "core"`): bugünkü kodla yeni kurulumlar T1/R1'in **önüne** geçer. Çözüm: arm dosyasına `PRIORITY: int` (T1 10, R1 20, TF1 30, B1 40, H2 50, S1 60, F1 70; `M1` 90) ve sıralama anahtarı `(sınıf·10 − zaman dilimi, PRIORITY)`; `core` tablosu için satırın kendi kurulumunun önceliği.

**Arm dosyası kalıbı.** `SETUP`, `TIMEFRAMES=("15m","1h","4h","1d")`, `CORE=False`, `ML_SCORED=False`, `EXIT_MODE`, `FEATURES`, `PRIORITY`, `compute(inp)`.
- `compute` saf fonksiyondur: girdi yalnız `inp.trig`, `inp.core()`, `inp.params`, `inp.tf`; saat, dosya, ağ, rastgelelik, modül seviyesinde durum yok. Aynı girdi → aynı çıktı (bit bit).
- Bağlam sütunları (`regime, rh, rl, rh_touches, rl_touches, atr_tf, atr_4h, atr_ratio, pullback_ema`) `inp.core()` kopyasından alınır; aday sütunları (`setup, side, signal, skip_reason, planned_*, rr, stop_dist_atr, ema_value, body_ratio, wick_ratio, edge_dist_atr, reasons`) önce boşaltılır, sonra kurulum doldurur. Girdi tablosu değiştirilmez (`copy`).
- Ek göstergeler (EMA 10/20/30/50, kayan en yüksek/en düşük, NR7, kutu) arm dosyasının içinde hesaplanır; `trader_core.indicators.ema/atr` **çağrılabilir**, `signals/regime/indicators` dosyaları **değiştirilmez**. İki kurulumun ortak yardımcıları `arms/_pa.py` içine konur (`_` önekli dosya kurulum sayılmaz).
- B1 ve H2 durum makinesidir: bar üzerinde düz döngü yazın (pencere ≤ 1500 bar; D-T20 süre ölçümü yeterlidir), vektörleştirme zorunlu değil. Durum her çağrıda `trig`'den yeniden kurulur, çağrılar arası saklanmaz.
- `reasons` biçimi: `"<KOD>_<long|short>:<etiket>,<etiket>"` (ör. `TF1_long:trend_up,close_brk,body_ok,stop_ok`); atlamada son etiket atlama kodu.
- 1g: bar motor içinde 6 × 4s'den toplanır; 1g'de `rejim` yine 4s rejimidir (günün son kapanmış 4s barı).

**Nedensellik (D-T17) test ipuçları.**
- **Kesme testi:** her `k` için `compute(trig[:k+1])` son satırı = `compute(trig)`'in `k`. satırı (bütün sütunlar; NaN = NaN). Rastgele yürüyüş + elle kurulmuş senaryo serilerinde, en az 300 bar.
- **Gelecek zehiri:** `t`'den sonraki barları `NaN`/aşırı değerle değiştir → `≤ t` satırları değişmez.
- **Kayma tuzakları:** `HC`, `RH`, `A`, kutu ve `A0` pencereleri `t`'yi **içermez**; `rolling(...).max()` kullanılıyorsa `shift(1)` unutulması bu testlerle yakalanır. F1'de `k* ≤ t−5`, S1'de `A0 = ATR[t−9]` ayrıca sınanır.
- **Belirlenimcilik:** aynı girdiyle iki çağrı ve satır sırası karıştırılıp yeniden sıralanmış girdi → `DataFrame.equals`.
- **Isınma:** `len(trig) = LOOKBACK−1` → bütün satırlar adaysız; hata yok; diğer kurulumlar etkilenmez.

## K-8. Bağımsız test durumları (test yazarı için; uygulayıcının testlerinden bağımsız yazılır)

Ortak (her kurulum için ayrı koşulur): **K-ORT-1** kesme testi; **K-ORT-2** gelecek zehiri; **K-ORT-3** ısınma eksik → adaysız; **K-ORT-4** short, long'un fiyat aynasında (`p → C − p`) aynı barlarda sinyal verir, stop/hedef aynalıdır; **K-ORT-5** çıktı `validate_table`'dan geçer, sinyal satırında stop/hedef doğru tarafta; **K-ORT-6** `rejim = volatile` → adaysız; **K-ORT-7** `FEATURES` anahtarları defter satırında sonlu sayı olarak bulunur.

| Kod | Davranış |
|---|---|
| K-TF1-1 | `trend_up`, 50 barlık kapanış tepesi + 0,2 ATR üstünde gövdeli kapanış → long; `planned_stop = HC − ATR`, hedef boş. |
| K-TF1-2 | Aynı seri, kırılım 0,2 ATR'nin altında (ör. +0,1) → aday yok. |
| K-TF1-3 | Ardışık iki kırılım barı → yalnız ilki sinyal (`not brk(t−1)`). |
| K-TF1-4 | Rejim `range` ya da `EMA_F < EMA_S` → aday yok; `ext > 3,0` → aday yok. |
| K-TF1-5 | `sda > 3,0` olacak kadar uzun kırılım mumu → satır var, `signal=False`, `skip_reason="stop_width"`. |
| K-TF1-6 | Pozisyon: 1R ilerleme sonrası stop `en yüksek − 3·ATR`'ye çekilir, geri gitmez; rejim `trend_down` olunca `regime_flip` (K-7 madde 1). |
| K-B1-1 | İki ayrık dokunuşlu seviye, kırılım barı, 4 bar sonra seviyeye dokunup üstünde boğa kapanış → long; hedef `c + 2R`, `rr = 2,0`. |
| K-B1-2 | Kırılımdan sonra retest yok (fiyat uzaklaşır) → 10 bar boyunca aday yok. |
| K-B1-3 | Retestte bir bar seviye altında kapanır, sonra üstüne döner → aday yok (kırılım öldü). |
| K-B1-4 | Tek dokunuşlu seviye ya da seviyeyi veren bar `i0−2`'de → kırılım barı sayılmaz. |
| K-B1-5 | Aynı kırılımda iki uygun retest barı → yalnız ilki; pencerenin 11. barındaki retest → aday yok. |
| K-B1-6 | Aynı seviyede aynı barda B1 long ile F1 short birlikte üretilemez. |
| K-B1-7 | Pozisyon: hedefe değen bar → `target`; 48 bar dolunca `time_stop`; iz süren stop kurulmaz. |
| K-F1-1 | Swing dibinin 0,3 ATR altına inip üstünde boğa kapanan tek bar (`rej ≥ 0,6`) → long; stop `Lsw − 0,2 ATR`; hedef son 20 bar tepesi − 0,2 ATR. |
| K-F1-2 | İki barlı: `t−1` seviye altında kapanır, `t` üstüne boğa kapanır → `t`'de long; `t−1`'de aday yok. |
| K-F1-3 | Derinlik 1,6 ATR → aday yok; `rej = 0,5` → aday yok; delme 0,05 ATR → aday yok. |
| K-F1-4 | Düşen seride asgari pencere kenarında (`k* < t−N_LVL+2`) ya da `k* > t−5` → aday yok. |
| K-F1-5 | Hedef çok yakın (`rr < 1,5`) → `skip_reason="rr_below_min"`; rejim `trend_down` iken long → aday yok. |
| K-F1-6 | Ardışık iki barda koşul sağlanır → yalnız ilki sinyal. |
| K-S1-1 | 8 barlık kutu (genişlik 2·A0, içinde bir iç bar), `t`'de `BH + 0,1 ATR` üstünde gövdeli kapanış → long; stop `BL − 0,2 ATR`; hedef boş. |
| K-S1-2 | Kutu genişliği 3,1·A0 → aday yok; `nr_count = 0` → aday yok. |
| K-S1-3 | Fitil `BH`'yi geçer, kapanış kutu içinde → aday yok. |
| K-S1-4 | Kutu öncesi 10 barda +4·A0 yükseliş → `pole_atr ≈ +4` özelliğe yazılır; aynı kutu direksiz → sinyal yine var, `pole_atr ≈ 0`. |
| K-S1-5 | Sinyalden sonraki 3 barda yeni koşul → aday yok (bekleme); 4. barda olabilir. `A0` kutu öncesi bardan okunur (kutu içi ATR değişimi sonucu etkilemez). |
| K-S1-6 | Rejim `trend_down` iken yukarı kırılım → aday yok; aşağı kırılım → short. |
| K-H2-1 | `trend_up`: tepe, 3 bar düşen tepeler, bir yukarı bar (H1), 2 bar düşen tepe, sonra `h[t−1]` üstünde kapanan boğa bar → `t`'de long; stop geri çekilme dibi − 0,3 ATR. |
| K-H2-2 | H1 barında aday yok; H2 barı `h[t−1]`'i fitille geçip altında kapanırsa aday yok. |
| K-H2-3 | Geri çekilme derinliği 0,8 ATR → aday yok; `k2 − k1 = 11` → aday yok. |
| K-H2-4 | Geri çekilme içinde `EMA50` altında bir kapanış → aday yok; `EMA20` eğimi negatif → aday yok. |
| K-H2-5 | Tepe 21 bar önce (`t−s > 20`) → aday yok; yeni tepe sayımı sıfırlar. |
| K-ONC-1 | Aynı çift, aynı 1s barında `T1` ve `H2` sinyali → `T1` girer, `H2` `arm_conflict`; `TF1@4h` ile `T1@1h` → `TF1@4h` girer. |
| K-ONC-2 | Yalnız `T1@1h` + `R1@1h` açıkken çıktı bu belgeden önceki ile aynı (D-T18 değişmedi); yeni sabitler T1/R1 arm dosyalarına eklendiğinde de. |
| K-ONC-3 | `EXIT_MODE` olmayan ya da geçersiz arm dosyası → `ArmError` (yükleme anında, işlem anında değil). |

## K-9. Bilinen sınırlar

- Kapanışta piyasa girişi, kırılım kurulumlarında (TF1, S1) fiyatı kovalar; stop/limit emirli varyantlar (katalog b, c) ayrı kurulum kodu olarak sonra denenebilir.
- Zaman durdurma 48 **bar**dır; 1g'de 48 gün, 15dk'da 12 saat eder. Zaman dilimine göre ölçekleme bu sürümde yok (`signals.TIME_STOP_BARS` donuk).
- F1 ve B1 seviyeleri kayan pencere uç değeridir; trend çizgisi, yuvarlak sayı, önceki gün seviyesi (PA-SDR-03/04/06) kullanılmaz.
- S1 üçgen/kama ayrımı yapmaz; hepsi "kutu + NR/iç bar" olarak sayısallaşır. Hacim teyidi (PA-FLT-05) hiçbir kurulumda yoktur (hisse/emtia hacmi seans dışında güvenilmez).
- Yeni kurulumlar puansız geçer (`ML_SCORED=False`), WP-10 süzgeci gelene kadar; kurulum dersi (WP-13) karneye göre aç/kapa yapar.
