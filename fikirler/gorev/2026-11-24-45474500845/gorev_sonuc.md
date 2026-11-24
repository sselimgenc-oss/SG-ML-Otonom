# Formasyon kütüphanesi tasarımı

Bu tasarım kod okunarak yazıldı; hiçbir test ya da kod çalıştırılmadı. 42 formasyon çıktı (12 mum, 13 grafik, 17 indikatör); 4 zaman diliminde 166 kol eder. Geçmiş testteki 12 setup dışındaki 30 formasyon hiç test edilmedi; eşikleri kitap sayı vermediği yerde ben doldurdum.

Onayınızı bekleyen dört seçim var:
- **Kapasite sayıları:** aile başına 4 açık pozisyon, formasyon x ZD başına 2 (bölüm 3). Bunlar benim önerim.
- **Ön değer:** geçmiş testte ekside olan hücreler yarım boyutla başlar; hiçbir kol kapanmaz (bölüm 4). İstemezseniz dosya boş bırakılır, hepsi tam boyutla başlar.
- **Stopsuz setuplara 2 ATR stop:** motor stopsuz pozisyon kabul etmiyor. Bu stop kitapta ve testte yok, sonucu değiştirir.
- **İç çubuk girişi:** testte bekleyen stop emriydi; motorda bekleyen giriş emri bulmadım, kapanış teyidine çevirdim.

## 1. Formasyon listesi

**Ortak kurallar (hepsi için)**
- Karar yalnız kapanmış son mumda (`t`) verilir. `planned_entry = c[t]`; motor bir sonraki açılışta girer.
- Short, long'un fiyat aynasıdır (`_pa.mirror`). Aynı mumda iki yön çıkarsa aday yok (`tab.both`).
- `[k]` = k mum önce. `dipN` = `t` dahil son N mumun en düşüğü. ATR = ATR(14), Wilder.
- Pivot: sol 10, sağ 2, kesin eşitsizlik. Pivot ancak indeksi ≤ `t-2` ise kullanılır.
- "Yakın" = `|a-b| ≤ 0.03 * min(|a|,|b|)`. Tampon yok: stop seviyenin kendisidir.
- Atla (`skip="stop_width"`): stop mesafesi girişin %0,6'sından küçükse ya da stop yanlış taraftaysa. Hedef yanlış taraftaysa `skip="other"`.
- Zaman stopu (ZS) yazmıyorsa 48 mum. "2R" = giriş + 2 x (giriş − stop).
- Kendi filtremiz yok (rejim, hacim, üst ZD eklenmez). Motorun ortak kapıları (uzun_yon, seans dışı, korelasyon, risk) bu kollara da uygulanır.
- "Test" sütunu E = geçmiş testteki 12 setuptan biri; mantık `setuplar_v3.py` ile aynı olmalı.

**MF1 — mum formasyonları (12)**

| Kod | Giriş (long) | Stop | Hedef / çıkış | Test |
|---|---|---|---|---|
| PINBAR | Alt gölge ≥ 2 x gövde; üst gölge < aralığın %10'u; `c ≥ l + 0.5*aralık`; `l ≤ dip10` | `l` | 2R | E |
| ICCUBUK | Ana mum `m`, iç mum `m+1` (`h<h[m]`, `l>l[m]`), `t ∈ {m+2, m+3}`; `c > h[m]`; aradaki mum `h[m]` üstünde kapanmamış | `l[m]` | 2R | E (giriş uyarlandı) |
| YUTAN | `c[1]<o[1]`, `c>o`, `o ≤ c[1]`, `c ≥ o[1]`; `l[1] ≤` (`t-1` dahil) son 5 mumun dibi | `l` | 2R | E |
| YILDIZ | 1. mum (`t-2`): `c ≤ o*0.985`, `l ≤ l[t-3]`. 2. mum: gövde ≤ `o`'nun %0,3'ü, gövde üstü ≤ 1. mumun kapanışı. 3. mum: `c>o`, `c >` 1. mumun gövde ortası | `c*0.97` | `c*1.09`; ZS 20 | E |
| DELICI | `c[1]<o[1]`, gövde[1] ≥ 0.5 x aralık[1]; `o ≤ c[1]`; `(o[1]+c[1])/2 < c < o[1]`; `min(l,l[1]) ≤ dip10` | `min(l,l[1])` | 2R | — |
| HARAMI | `c[1]<o[1]`, gövde[1] ≥ 0.6 x aralık[1]; `c>o`; gövde tümüyle önceki gövdenin içinde; `l[1] ≤` (`t-1` dahil) son 5 dip | `min(l,l[1])` | 2R | — |
| TERSCEKIC | Mum `t-1`: üst gölge ≥ 2 x gövde, alt gölge < aralığın %10'u, `l[1] ≤` (`t-1` dahil) son 10 dip. Onay: `c > h[1]` | `l[1]` | 2R | — |
| UCASKER | Son 3 mum yükseliş; her kapanış öncekinden yüksek; 2. ve 3. açılış önceki gövdenin içinde; her gövde ≥ 0.6 x aralık; `l[2] ≤` (`t-2` dahil) son 10 dip | `l[2]` | 2R | — |
| CIMBIZ | `c[1]<o[1]`, `c>o`; `abs(l-l[1]) ≤ 0.1*ATR`; `min(l,l[1]) ≤ dip10`; YUTAN koşulu sağlanmıyor | `min(l,l[1])` | 2R | — |
| MARUBOZU | `c>o`; gövde ≥ 0.9 x aralık; aralık ≥ 1.5 x ATR | `l` | 2R | — |
| ICSAHTE | Ana mum `t-2`, iç mum `t-1`; `l < l[2]` (aşağı sahte kopuş); `c > l[1]` ve `c > o` | `l` | 2R | — |
| DISBAR | `h>h[1]`, `l<l[1]`, `c>h[1]`; `l ≤ dip5` | `l` | 2R | — |

Short karşılıkları: kayan yıldız, ayı yutan, akşam yıldızı, kara bulut, ayı harami, asılı adam, üç karga.

**GF1 — grafik formasyonları (13)**

T1, T2 = onaylı son iki pivot tepe; D1, D2 = son iki pivot dip. "İlk kırılım" = ilgili pivottan `t-1`'e kadar hiçbir kapanış seviyenin ötesinde değil ve `c[t]` ötesinde.

| Kod | Giriş (long) | Stop | Hedef | Test |
|---|---|---|---|---|
| YATAY | T1, T2 yakın; `L = max`; T1'den beri ilk kırılım `c > L` | `min(L, l)` | `L + (L − T1..T2 arası en düşük dip)` | E |
| UCGEN | (a) Yükselen: T1, T2 yakın, arada ≥ 2 yükselen pivot dip, `c > L`. (b) Simetrik: tepeler düşüyor, dipler yükseliyor; üst çizgi dışında ilk kapanış; en eski pivottan en fazla 100 mum | son onaylı pivot dip | kırılım seviyesi + (ilk tepe − ilk dip) | E |
| IKILI | D1, D2 yakın, arası 5–25 mum; boyun = aradaki en yüksek; ilk kırılım `c > boyun` | `min(l[D1], l[D2])` | boyun + (boyun − dip) | E |
| OBO | TOBO: 3 pivot dip, ortadaki en düşük, omuzlar yakın; boyun = aradaki iki en yüksek pivot tepeden geçen doğru; önceki hareket ≥ 2 x (baş–boyun); ilk kırılım | baş dibi | boyun(t) + (baş–boyun) | E |
| UCLU | Son 3 pivot dip ikişer ikişer yakın, ilk–son arası ≤ 60 mum; boyun = aradaki en yüksek; ilk kırılım | üç dibin en düşüğü | boyun + (boyun − dip) | — |
| BAYRAK | Direk tepesi `P` = `[t-20, t-3]` en yükseği, `P ≥ t-15`; taban = `[P-10, P]` en düşüğü; `H = h[P] − taban ≥ 3*ATR[P]`; bayrak = `P+1..t-1`; bayrak dibi `≥ h[P] − 0.5*H`; `c > ` bayrağın en yükseği; daralma YOK | bayrak dibi | kırılım seviyesi + `H` | — |
| FLAMA | BAYRAK ile aynı, ama daralma VAR: bayrağın ikinci yarısının aralığı < ilk yarısının 0.7 katı; bayrak ≥ 6 mum | bayrak dibi | kırılım seviyesi + `H` | — |
| KAMA | Düşen kama: T2<T1, D2<D1; üst çizgi eğimi alt çizgiden dik (yakınsıyor); üst çizgi üstünde ilk kapanış; yaş ≤ 100 | `l[D2]` | `h[T1]` | — |
| TREND | T2<T1, D2<D1, çizgiler yakınsamıyor (düşen kanal); tepe çizgisi üstünde ilk kapanış; yaş ≤ 100 | `l[D2]` | 2R | — |
| KANAL | T1, T2 yakın (direnç `R = max`), D1, D2 yakın (destek `S = min`); `R − S ≥ 3*ATR`; `l ≤ S + 0.25*ATR`, `c > S`, `c > o` | `min(l, S)` | `R` | — |
| RETEST | Son 20 mumda YATAY kırılımı olmuş (seviye `L`); o günden beri `L` altında kapanış yok; `l ≤ L + 0.25*ATR`, `c > L`, `c > o`; kırılımdan sonraki ilk böyle mum | `min(l, L)` | YATAY hedefi | — |
| SAHTE | D1, D2 yakın, `S = min`; son 3 mumdan biri `S` altında kapanmış; `c > S`; kırılımdan sonra ilk geri alma | kırılımdan beri en düşük | 2R | — |
| KUPA | YATAY koşulları + T1–T2 arası 20–100 mum + derinlik `(L − aradaki en düşük) ≥ 3*ATR` + kulp: `t − T2 ≥ 3` ve T2'den beri en düşük `≥ L − 0.5*derinlik` | kulp dibi | `L +` derinlik | — |

Not: simetrik üçgen (dipler yükseliyor), KAMA (dipler düşüyor, yakınsıyor) ve TREND (dipler düşüyor, yakınsamıyor) birbirini dışlar.

**IN1 — indikatör setupları (17)**

"Çıkış" sütunundaki koşul kural çıkışıdır: her kapanan mumda bakılır, sağlanırsa piyasa emriyle çıkılır (bölüm 2).

| Kod | Giriş (long) | Stop | Hedef / çıkış | Test |
|---|---|---|---|---|
| RSI | RSI(14) `< 30` ve `[1] ≥ 30`; SMA50 > SMA200; `dip10 < c` | `dip10` | RSI > 70 | E |
| MAKESISIM | SMA50, SMA200'ü yukarı keser | `c − 2*ATR` | SMA50 < SMA200 | E (stop eklendi) |
| BOLL | Bollinger(20,2): `l ≤` alt bant ve `l < c` | `l` | hedef = sinyaldeki SMA20; ayrıca `h ≥ SMA20[1]` olunca çık | E (hedef yaklaşık) |
| FIYATMA | `c > SMA50` ve `c[1] ≤ SMA50[1]` | `c − 2*ATR` | `c < SMA50` | E (stop eklendi) |
| MACD | MACD(12,26,9) çizgisi sinyali yukarı keser | `c − 2*ATR` | ters kesişim | — |
| STOK | Stokastik(14,3,3): %K, %D'yi yukarı keser, ikisi de < 20; `c > SMA50` | `dip10` | %K > 80 | — |
| RSIDONUS | RSI(14) `> 30` ve `[1] ≤ 30` | `dip10` | RSI > 70 | — |
| RSI2 | RSI(2) `< 15`; `c > SMA200` | `c − 2*ATR` | RSI(2) > 85 | — |
| UYUMSUZ | D1, D2 arası 5–50 mum; `l[D2] < l[D1]`, `RSI[D2] > RSI[D1]`; `t = D2+2`; `c > h[D2]` | `l[D2]` | D1–D2 arası en yüksek; girişin altındaysa 2R | — |
| HIZLIMA | EMA4, EMA9'u yukarı keser | `c − 2*ATR` | ters kesişim | — |
| BOLLKIR | `c >` üst bant, `c[1] ≤` üst bant[1]; MACD > sinyal | SMA20 | `c < SMA20` | — |
| TK | Tenkan(9), Kijun(26)'yı yukarı keser; `c >` bulut üstü | Kijun | Tenkan < Kijun ya da `c < Kijun` | — |
| KUMO | `c >` bulut üstü, `c[1] ≤` bulut üstü[1] | Kijun (girişin üstündeyse bulut altı) | `c < Kijun` | — |
| HACIM | `v ≥ 2 * SMA20(v)[1]`; `c >` önceki 20 mumun en yükseği; `c > o` | `l` | 2R | — |
| VWAP | UTC gününe demirli VWAP: `c > VWAP`, `c[1] ≤ VWAP[1]`. Yalnız 15m ve 1h | `c − 2*ATR` | `c < VWAP` | — |
| FIBO | Pivot dip A, sonra pivot tepe B; `H = h[B] − l[A] ≥ 3*ATR`; `l ≤ h[B] − 0.5*H`, `c ≥ h[B] − 0.618*H`, `c > o`; B'den beri ilk temas | `h[B] − 0.786*H` | `h[B]` | — |
| MAGERI | EMA20 > EMA50, `c > EMA50`; `l ≤ EMA20`, `c > EMA20`, `c > o`; önceki 5 mumun dibi EMA20 üstünde | `l` | 2R | — |

Bulut: Span A ve B, `t`'de çizilen değerdir; `t-26` ve öncesinin verisinden hesaplanır.

**Dışarıda bırakılanlar ve nedeni**
- Mekanik tanımı yok: Elliott/EFW, harmonik (Gartley), Quasimodo, elmas, yuvarlak dip, arz/talep bölgeleri.
- Boşluk ya da seans gerektiriyor: açılış boşluğu, açılış aralığı kırılımı, karşı saldırı, önceki gün seviyeleri (PDH/PDC).
- Tek kitapta geçiyor (önceki turun ölçütü): Alligator, %R, PMax, SSL, MIDAS, Parabolic SAR, Trend Magic, Gauss kanalı.
- Dış veri gerektiriyor: Arms/TRIN, ISM, petrol envanteri, carry.
- Doji: kitaplarda yalnız stop yeri ve seviye tarifi var, giriş kuralı yok.

## 2. Kimlik ve keşif

**Kimlik**
- Kurulum kodu = `<AİLE>-<FORMASYON>`, örnek `MF1-YUTAN`. Kol kimliği = `MF1-YUTAN@1h`.
- Motorda her formasyon ayrı kurulum sayılır. Böylece tavan, karantina, kol küçültme, `arm_conflict` ve alınsaydı kayıtları kendiliğinden formasyon x ZD bazında çalışır.
- Kurulum kodu kalıbı dört yerde genişletilir: `[A-Z][A-Z0-9]{1,7}(-[A-Z0-9]{2,10})?`
  - `strategies/arms/__init__.py` (`_SETUP_RE`, `_ARM_ID_RE`)
  - `trader_engine/config.py` (`_ARM_ID_RE`, `_ARM_SETUP_RE`)
  - `trader_core/ledger.py` (`_SETUP_RE`, `_setup_code` hata metni)
  - `trader_core/exit_modes.py` (`_valid_key`)
- Uygulayıcı `{1,7}` kalıbını `src`, `scripts`, `research` altında arar; kalan her yeri aynı biçimde günceller. Telegram `/karantina_kaldir` ve CLI `arm-quarantine release` tireli kodu kabul etmeli. Bunları ben doğrulamadım.

**Dosyalar**
- `arms/_kutuphane.py` (keşfe girmez): `Formasyon` veri sınıfı, ortak hazırlık ve tablo yazımı.
  - `Formasyon(kod, ad, sira, tfs, zaman_stopu, bul, cikis)`. `bul(F) -> None | dict(stop, hedef, seviye, olcu, yas, etiket)` long uzayında son mumu değerlendirir. `cikis(F) -> bool` ya da `None`.
  - `ortak(inp)`: gösterge ve pivotları çift x ZD x D başına BİR kez hesaplar. Tek girişli önbellek; anahtar `(pair, tf, D, len(trig), trig.index[-1])`.
  - Aday yoksa aynı önbellekteki boş tablo nesnesi döner (kopya yok). Aday varsa yeni `P.Table` yazılır.
- `arms/mf1.py`, `arms/gf1.py`, `arms/in1.py`: `SETUP = "MF1"`, `FORMASYONLAR = {kod: Formasyon}`, `PRIORITY` taban değeri, `compute(kod, inp)`.
- Ortak `FEATURES`: `{"body_ratio": "body_ratio", "wick_ratio": "wick_ratio", "rr": "rr", "f_seviye": "ema_value", "f_olcu_atr": "edge_dist_atr", "f_yas": "pullback_ema"}`.

**Keşif (`discover`)**
- Modülde `FORMASYONLAR` varsa aile kodu (`MF1`) kol olarak kaydedilmez. Her formasyon için sanal kurulum nesnesi (`types.SimpleNamespace`) kaydedilir:
  - `SETUP="MF1-YUTAN"`, `TIMEFRAMES=f.tfs`, `CORE=False`, `EXIT_MODE="target"`, `FEATURES`, `PRIORITY=taban+f.sira`, `TIME_STOP=f.zaman_stopu`, `EXIT_RULE=f.cikis`, `compute=partial(mod.compute, kod)`.
- `find_arm`, `exit_mode`, `features_of`, `priority_of`, `list_arms` değişmeden çalışır. `lab.py` değişmez.
- Yeni yardımcılar: `time_stop_of(setup)` (yoksa 48), `exit_rule_of(setup)` (yoksa `None`), `family_of(setup)` (`-` öncesi).
- Paket belge dizgisi güncellenir: "her kurulum tek dosya; kütüphane dosyası birden çok kurulum kaydeder".

**Çıkış (yeni: formasyona özel zaman stopu ve kural çıkışı)**
- `position_manager.ExitContext`'e `rule_exit: bool = False` alanı eklenir.
- `evaluate_exit`, `target` kipinde sırayla: hedef; `ctx.rule_exit` ise `ExitDecision("exit", "other")`; `time_stop_due(ctx.n_closed, time_stop_of(pos.setup))`.
  - Çıkış nedeni `other` kullanılır, çünkü defterde `exit_reason` için CHECK kısıtı var; şema göçü gerekmez.
- `engine._position_for_arms` demeti `(trigger_tf, entry_bar_open, setup, side)` olur.
- `strategy_runner`: pozisyonun ZD'si için çıkış görünümü kurulurken `exit_rule_of(setup)` varsa `ortak` hazırlığıyla çağrılır, sonuç `rule_exit`'e yazılır. Hata olursa `False` kalır ve sayaç artar; stop ve zaman stopu yine çalışır.
- Mevcut 10 kolun çıkışı değişmez (`TIME_STOP` yok → 48, `EXIT_RULE` yok).

**Ayar**
- `engine.paper.json` ve `engine.live.json` `arms` listesine 166 kimlik açıkça yazılır (panel ham listeyi okuyor; kısaltma kullanılmaz).
- Liste elle yazılmaz: `scripts/` altına küçük bir üretici eklenir, test listeyi `discover()` ile karşılaştırır.

**Ders kapsamı**
- Kütüphane dosyaları hiçbir ders parametresini (`inp.params.*`) OKUMAZ; kitap kuralları sabittir. `LESSON_SCOPE` değişmez; `test_ders_kapsam.py` bunu zaten tarar.
- `EXIT_MODE="target"` olduğu için `trail_atr` kapsamına da girmezler.

## 3. Çatışma ve kapasite

**Öncelik**
- Mevcut sıra korunur: önce büyük zaman dilimi, sonra `PRIORITY` (küçük kazanır).
- Mevcut 10 kol aynı ZD'de her zaman kütüphaneden öncedir. Kütüphane tabanları: GF1 = 200, MF1 = 300, IN1 = 400. Uygulayıcı HB1 ve DL1 önceliklerinin 200'ün altında olduğunu doğrular.
- Aile içi sıra (seyrek ve yapısı net olan önce):
  - GF1: OBO 1, UCLU 2, KUPA 3, IKILI 4, KAMA 5, UCGEN 6, BAYRAK 7, FLAMA 8, RETEST 9, SAHTE 10, TREND 11, KANAL 12, YATAY 13.
  - MF1: YILDIZ 1, UCASKER 2, DELICI 3, ICSAHTE 4, DISBAR 5, YUTAN 6, HARAMI 7, TERSCEKIC 8, CIMBIZ 9, PINBAR 10, ICCUBUK 11, MARUBOZU 12.
  - IN1: UYUMSUZ 1, MAKESISIM 2, KUMO 3, TK 4, FIBO 5, HACIM 6, RSI 7, RSIDONUS 8, RSI2 9, STOK 10, MACD 11, MAGERI 12, BOLLKIR 13, VWAP 14, FIYATMA 15, HIZLIMA 16, BOLL 17.
- Aynı mumda aynı çiftte birden çok formasyon: en öncelikli girer, diğerleri `arm_conflict` yazılır. Kazanan kola özgü bir nedenle (tavan, uzun_yon) reddedilirse sıradaki denenir. Bu yol `_pair_entries` içinde zaten var; değişmez.

**Tavanlar**
- Değişmeyenler: `max_positions` 24, küme tavanları, `max_open_risk` %12, `max_same_dir_risk` %6, günlük kayıp %8, korelasyon grubu, çift başına tek pozisyon. Toplam riski bunlar korur.
- Sorun: `default: 6` kol x ZD başınadır; 166 yeni kolla bağlayıcı olmaz ve kütüphane 24 yerin hepsini doldurup mevcut kolları aç bırakabilir.
- Çözüm 1, formasyon x ZD tavanı: `arm_max_positions`'a joker anahtar `"MF1-*": 2, "GF1-*": 2, "IN1-*": 2`.
  - `arm_guard.arm_cap` arama sırası: tam kimlik → kurulum → `"<AİLE>-*"` → `default`. Joker, `default` gibi kol x ZD başına sayılır.
  - `config._build_arm_caps` joker anahtarı kabul eder.
- Çözüm 2, aile tavanı: yeni ayar `arm_family_max_positions: {"MF1": 4, "GF1": 4, "IN1": 4}`.
  - `gates.py`'de kol tavanından hemen sonra denetlenir: ailenin tüm formasyon ve ZD'lerindeki açık pozisyon sayısı.
  - Doluysa `max_positions` kodu ve `veto_reason = "gate:arm_cap:MF1"`. Bu önek "adaya özgü red" sayıldığı için sıradaki aday denenir.
  - `config.py` izinli anahtar listelerine (kağıt ve canlı) eklenir; `cluster_counts` çıktısına `families` bölümü eklenir.
- Sonuç: kütüphane en çok 12 pozisyon tutar; mevcut kollara en az 12 yer kalır.
- Sinyal seli için başka süzgeç yok. Bollinger 15m gibi kollar en çok 2 yer tutar; zarar ettikçe kol küçültme boyutu %30'a indirir.

## 4. Öğrenme

**Kendiliğinden doğru çalışanlar (kod değişmez, test eklenir)**
- Kol küçültme: `kol_kucultme.aile_ortalamasi` ve `ledger.arm_family_mean_r` aileyi `@` öncesinden alır. `MF1-YUTAN@1h` için aile = YUTAN'ın diğer ZD'leri. İstenen davranış budur.
- Karantina: birim anahtarı kurulum kodudur; her formasyon x ZD ayrı karantinaya girer.
- Alınsaydı ve karşı-olgu: `arm_id` karar satırından gelir; `arm_conflict` kayıpları formasyon x ZD bazında raporlanır.
- Gece dersleri: parametre dersleri kütüphaneye dokunmaz (kapsam dışı). Kol karnesi `arm_id` ile gruplanır.
- `arms_off` yaşam döngüsü: tireli kimliği okuyup yazabildiği testle doğrulanır; davranışı değişmez.

**Bilinen sınır**
- Karşı-olgu "plan" yöntemi sabit 48 mum ufuk kullanır ve kural çıkışını bilmez. YILDIZ (20 mum) ve kural çıkışlı IN1 formasyonlarında alınsaydı R'si yaklaşıktır. Bu turda değiştirilmez; rapora not düşülür.

**Geçmiş testin ilk bilgi olarak verilmesi (ön değer)**
- Yeni dosya `trader/config/formasyon_on_deger.json`: 48 hücre, `{"MF1-PINBAR@15m": {"r": -0.235, "n": 5951}, ...}`.
  - Değer = kilitli dönem ortalama net R; kaynak `sonuc_v3_kilitli/sonuc.json`.
  - Ad eşlemesi: MUM_PINBAR→MF1-PINBAR, MUM_IC_CUBUK→MF1-ICCUBUK, MUM_YUTAN→MF1-YUTAN, MUM_YILDIZ→MF1-YILDIZ, FOR_YATAY_KIRILIM→GF1-YATAY, FOR_UCGEN→GF1-UCGEN, FOR_IKILI_DIP→GF1-IKILI, FOR_OBO→GF1-OBO, IND_RSI_3070→IN1-RSI, IND_MA_KESISIM→IN1-MAKESISIM, IND_BOLL_DONUS→IN1-BOLL, IND_FIYAT_MA→IN1-FIYATMA.
- Kullanım: `gates._kol_karari` içinde gerçek aile ortalaması `None` ise ön değer aile ortalaması yerine verilir. Başka yerde kullanılmaz.
- Etki (mevcut büzülme formülüyle, K = 10):
  - Ön değeri eksi hücre ilk işlemden itibaren %50 boyutla başlar. %30'a ancak 10 gerçek işlemden sonra iner.
  - Ailede gerçek işlem birikince ön değer devreden çıkar. Kol toparlarsa boyut kendiliğinden %100'e döner.
  - Hiçbir kol kapanmaz; "hepsi açık" kararı bozulmaz.
- Test edilmemiş 30 formasyonda ön değer yok: tam boyutla başlar, 5 işlemden sonra ham kural devreye girer.
- Uyarı: ICCUBUK, MAKESISIM, FIYATMA ve BOLL'un motor sürümü testtekinden farklı (giriş, stop ya da hedef); bu 16 hücrenin ön değeri yaklaşıktır.
- Ayrıca rapor: 48 hücrelik tablo panelde "geçmiş test" sütunu olarak kağıt sonucunun yanında gösterilir.

## 5. Göstergeler, ileriye bakış, görünüm, testler

**Göstergeler (`trader_core/indicators.py`; yalnız ekleme, mevcut fonksiyonlara dokunulmaz)**
- `rsi(c, n)` Wilder, `std_pop`, `bollinger(c, 20, 2)`, `macd(12, 26, 9)`, `stoch(14, 3, 3)`, `ichimoku(9, 26, 52)`, `vwap_gunluk` (UTC günü), `pivot_tepe` / `pivot_dip` (sol 10, sağ 2).
- RSI, SMA, standart sapma ve pivot tanımları `yeni_kollar/gostergeler.py` ve `setuplar_v3.py` ile aynı sonucu vermeli.
- Pencere yeterli: 1d 600 mum (SMA200 için 200 gerekir). Isınma dolmadan aday çıkmaz, hata vermez.

**İleriye bakış kuralları**
- Dedektör yalnız `inp.trig`'in son satırını değerlendirir; `trig` yalnız kapanmış mumları içerir.
- Pivot indeksi ≤ `t-2`. Ichimoku bulutu `t-26` ve öncesinden. Hacim ortalaması ve "önceki N mum" pencereleri `t`'yi içermez.
- Kural çıkışı da yalnız son kapanmış mumu okur.

**Panel, Telegram, rapor**
- `tg_sade.KURULUM_AD`'a 42 Türkçe ad eklenir (örnek: `"MF1-YUTAN": "Mum: yutan"`). `kurulum_adi` tireli kodu çözer.
- Panel kol karnesi: satırlar aileye göre gruplanır, kapalı gelir, aile toplamı görünür; açınca formasyon x ZD satırları ve "geçmiş test" sütunu.
- Telegram günlük özet: aile başına tek satır (işlem, net R) ile en iyi 3 ve en kötü 3 formasyon x ZD. Kol listesi tek tek basılmaz.
- `tur1_olcum.py`: kütüphane kolları "32 kol" karnesine karışmaz; `UST_LIG_KOLLARI` gibi ayrı "Formasyon kütüphanesi" bölümü (aile = `-` öncesi).
- Kural çıkışı (`other`) kütüphane kollarında "kural çıkışı" olarak etiketlenir.

**Testler**
- Her formasyon için sentetik örnek: long tetikler, short aynası tetikler, bir koşul bozulunca tetiklemez; stop ve hedef beklenen değerde (42 x 3).
- Eşdeğerlik: 12 test setupu için `setuplar_v3.py` ve `gostergeler.py` test verisi klasörüne referans olarak kopyalanır. Rastgele yürüyüş serisinde, her önek için kütüphane sonucu `gercek_sinyaller` ile aynı `(t, yön, stop, hedef)` vermeli. ICCUBUK hariç; MAKESISIM ve FIYATMA'da yalnız `t` ve yön.
- İleriye bakış: `t`'den sonraki mumlar değiştirilince `t`'deki karar değişmez; 500 ve 5000 mumluk pencere aynı adayı verir (1e-9).
- Kağıt = canlı: iki ayar dosyasında `arms`, `arm_max_positions`, `arm_family_max_positions` birebir eşit; `arms` kütüphane kısmı `discover()` ile eşit.
- Kimlik: tireli kod `config`, `ledger`, `exit_modes`, `arms_off`, karantina, karşı-olgu yollarından geçer.
- Tavan: formasyon x ZD 2 ve aile 4 sınırı; dolunca sıradaki aday denenir.
- Öğrenme: ön değerli eksi hücre ilk girişte %50; ön değersiz hücre %100; gerçek aile verisi gelince ön değer kullanılmaz.
- Çıkış: YILDIZ 20. mumda zaman stopuyla çıkar; FIYATMA `c < SMA50` kapanışında `other` ile çıkar; mevcut kolların çıkışı aynı kalır.
- Hız: 5000 mumluk bir çift x ZD için 42 formasyonun toplamı 50 ms'nin altında.

**Hash ve sayı sabitleyen testler**
- `test_m1_tf_paper.py`: kol sayısı 37 → 203 (37 + 166).
- `ayar_surumu` hash'i kendiliğinden değişir; sabit değer varsa güncellenir.
- Kütüphane kolu içermeyen koşuların işlem ve özet özetleri (`test_dd12_wp11_spec.py` ve benzerleri) DEĞİŞMEMELİ. Değişirse hata vardır; hash güncellenmez, neden bulunur.
- `signals.py` dondurulmuştur, dokunulmaz.

## 6. İş bölümü

**Adım 1 — altyapı + MF1**
- Kimlik kalıpları, `_kutuphane.py`, `discover` genişletmesi, zaman stopu ve kural çıkışı, iki tavan, ön değer dosyası ve kapı bağlantısı, `mf1.py` (12 formasyon), 48 MF1 kimliğinin iki ayara eklenmesi.
- Kabul: tüm eski testler geçer; kütüphanesiz koşu özetleri bit bit aynı; MF1 sentetik, eşdeğerlik (PINBAR, YUTAN, YILDIZ), ileriye bakış, tavan, ön değer ve çıkış testleri geçer; kağıt = canlı testi geçer.

**Adım 2 — GF1**
- Pivot yardımcıları, `gf1.py` (13 formasyon), 52 kimlik.
- Kabul: 13 sentetik test; YATAY, UCGEN, IKILI, OBO eşdeğerliği; simetrik üçgen, KAMA ve TREND'in aynı mumda birlikte tetiklemediği test; hız ölçütü.

**Adım 3 — IN1**
- Yeni göstergeler, `in1.py` (17 formasyon), 66 kimlik (VWAP yalnız 15m ve 1h).
- Kabul: 17 sentetik test; RSI ve BOLL eşdeğerliği, MAKESISIM ve FIYATMA sinyal eşdeğerliği; gösterge değerleri referansla 1e-9 içinde; kural çıkışı testleri.

**Adım 4 — görünüm ve kapanış**
- Panel gruplama ve "geçmiş test" sütunu, Telegram aile özeti, `tur1_olcum` ayrı bölüm, 42 ad.
- Kabul: her keşfedilen kolun Türkçe adı var; panel ve rapor testleri geçer; 43 çift x 4 ZD tam adım süresi ölçülüp rapora yazılır; tüm test takımı yeşil.