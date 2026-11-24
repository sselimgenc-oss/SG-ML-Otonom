# Risk kademesi kararı

## Kademe bugün ne yapıyor (kısa tablo)

| Koşul (60 sn'de bir ölçüm, art arda 2 ölçümle onay) | Sonuç | Canlı | Kâğıt |
|---|---|---|---|
| Başlangıç | Canlı K2 = %1; testnet K0 = %0,5 | uygulanır | risk hep %1 |
| Özsermaye ≤ tepenin %90'ı (tepeden −%10) | Bir basamak iner: %1 → %0,75 | uygulanır | yalnız "olsaydı" notu |
| Özsermaye ≤ tepenin %85'i (tepeden −%15) | %0,5'e iner; zaten %0,5'teyse ve yatırılan ≥ 1000 USD ise %0,35 | uygulanır | yalnız not |
| Özsermaye ≤ yatırılanın %85'i (ana para kilidi) | Yeni giriş kapanır, yalnız kullanıcı açar | uygulanır | uygulanır (tek ortak kural) |
| Özsermaye ≤ tabanın %80'i (−%20 durma) | Yeni giriş kapanır, açık pozisyonlar stoplarıyla kalır; devam kullanıcı onayıyla | uygulanır | yalnız not |
| Özsermaye ≤ yatırılanın %60'ı (son taban) | Yeni giriş kapanır; yeniden başlama yazılı kararla | uygulanır | yalnız not |
| −%20 sonrası "yeniden tabanla" devam, ya da taban sonrası yeniden başlatma | Basamak K0'a (%0,5) çekilir | uygulanır | yok |
| Geri çıkış | Yalnız kullanıcı onayıyla: 60 işlem, 42 gün, ortalama R ≥ 0, son inişten 56 gün | uygulanır | yok |
| Borsa aktarımı ile sermaye kaydı eşleşmiyor, günlük yok ya da bozuk | Yeni giriş kapanır | uygulanır | yok (kâğıtta günlük yalnız bellekte, her açılışta sıfırlanır) |

## Karar (tek cümle) ve gerekçe (3-5 madde)

**Karar (b): risk düşürme ikisinde de kaldırılır ve işlem başı risk hep %1 kalır; −%20 durma, %60 taban ve ana para kilidi kâğıtta da canlıda da aynen uygulanır.**

- **Kazancı küçük.** Tepe yatırılan paraya yakınken risk düşürme yalnız −%10 ile −%15 arasında çalışıyor; −%15'te ana para kilidi zaten bütün girişleri kapatıyor. Yani birkaç işlem için riski yarıya indiriyor.
- **Bedeli büyük.** İnen risk en az 56 gün ve 60 işlem geri çıkamıyor; bot bu sürede kaybını yarım boyla geri kazanmaya çalışıyor.
- **Asıl koruma durma eşikleri.** Zararı sınırlayan şey %85 kilit, −%20 durma ve %60 taban. Bugünkü gerçek fark, bunların kâğıtta çalışmaması; kâğıt bu yüzden canlının duracağı yerde işlem açmaya devam ediyor.
- **%1 sabit oran zaten kendini küçültür.** Kasa düştükçe %1'in dolar karşılığı da düşer.
- **%1 tercihine karşı güçlü bir neden bulmadım.** Tek açık nokta: kârdan sonra tepeden düşüşte fren yok (1000 yatırıp 2000'e çıkan kasa 850'ye kadar %1 ile iner). Eski kademe bunu da durdurmuyordu, yalnız yavaşlatıyordu. İstersen ayrı bir karar olarak "tepeden −%X'te dur" kuralı eklenebilir.

Bilmen gereken bir sonuç: kâğıt kasa bugün başlangıç tutarının %80'inin altındaysa, değişiklik devreye girer girmez kâğıt bot yeni girişi durdurur ve devam onayını bekler.

## Uygulama talimatı (uygulayıcı bunu AYNEN kodlayacak: hangi dosya, hangi ayar/sabit, kâğıt ve canlı için ne olacak, hangi testler)

**1. `trader/src/trader_core/risk_ladder.py`**
- Yeni kod sabiti: `STEP_RISK_ENABLED = False` (açıklama: 24.11 kullanıcı kararı, risk düşürme kapalı, risk hep yapılandırmadaki %1).
- `evaluate`: sabit `False` iken `dd_peak_15` ve `dd_peak_10` dalları atlanır, `step_down` hiç üretilmez. `floor_stop` ve `review_stop` sırası ve eşikleri değişmez.
- `step_config`: basamak doğrulamasından sonra, sabit `False` iken `base_cfg` aynen döner. Böylece eski günlükteki K0/K1, "yeniden tabanla" devam ve taban sonrası yeniden başlatma riski düşüremez.
- `fold`, `STEPS`, `_EXTRA` ve eşik sabitleri değişmez; eski günlükler (içinde `step_down` satırı olsa da) geçerli kalır.

**2. `trader/src/trader_engine/engine.py`, `_build_ladder` (2644–2663)**
- Backtest: değişmez (`None`).
- Kâğıt: bellek günlüğü yerine dosya günlüğü `RL.LadderLog(cfg.path("risk_ladder.jsonl"))` ve `enforce=True`; `transfers_fn=None`, `trades_fn` aynı.
- Kâğıtta günlük dosyası yok ya da boşsa motor açılışta bir kez `initial` yazar: `amount=cfg.wallet_start`, `by="engine:paper"`, `start_step=RL.LIVE_START_STEP`. Dosya doluysa dokunmaz; bozuksa canlıdaki gibi `ladder_invalid` ile giriş kapalı kalır.
- `follow=` parametresi kâğıtta artık verilmez.
- Testnet ve canlı satırı değişmez (`enforce=True`).

**3. `trader/src/trader_engine/ladder.py`**
- `risk_config` (101–113): `if not self.enforce: return base` dalı ve "gözlem" yorumu kaldırılır; sonuç 1. adımdaki sabit sayesinde her kipte `base` olur.
- Modül başlığındaki "Paper kipi GÖZLEM'dir" cümlesi düzeltilir.
- `tick` 4. adım (218) değişmez: aktarım eşleştirmesi yalnız `transfers_fn` varken çalışır. Kâğıtta borsa aktarımı olmadığı için uygulanamaz; bu, kâğıt ile canlı arasında belgelenen tek farktır.
- `status()`: `step_risk` alanı `STEPS[step]` yerine etkin riski (`self.risk_config.target_trade_risk`) verir.

**4. `trader/src/trader_engine/cli.py`**
- `_ladder_ctx` (531): yazan komut reddi yalnız `backtest` için kalır; kâğıtta `ladder` devam ve yeniden başlatma komutları ile `capital adjust` çalışır.
- `capital init` kâğıtta reddedilir (ilk satırı motor yazar).
- Satır 718: `start_step` yalnız canlı için değil, testnet için de yazılır (`cfg.mode in ("live", "testnet")`).

**5. `trader/src/trader_core/telegram.py` (654, 680, 986) ve `health.py` (1066, 1080)**
- Telegram metinleri "K0 %0,5" yerine etkin riski gösterir ("risk %1 (sabit)"); `step_risk` `RL.STEPS[...]` yerine durum bloğundaki `effective_risk`'ten okunur.
- `/kademe_devam` kâğıt botu için de çalışmalı; kip reddi varsa kaldırılır.
- `ladder_step_down` ve `ladder_would` uyarıları artık tetiklenmez; kod kalabilir.

**6. Yapılandırma**
- `trader/config/engine.paper.json` ve `engine.live.json`: `target_trade_risk` 0.01 olarak ikisinde de AYNEN kalır; yeni anahtar eklenmez (risk sabitleri yalnız kodda).
- `ladder_follow` kâğıt dosyasında varsa silinir; `config.py` içindeki alan dokunulmadan kalabilir.

**7. Belgeler**
- `otonom-trading-arastirma/tasarim-kararlari.md`: 24 Kasım 2026 kararı eklenir ("risk düşürme kaldırıldı, risk hep %1; −%20 durma, %60 taban, %85 kilit kâğıtta da zorlanır; tek fark aktarım eşleştirmesi"). 17 Kasım'daki "Kâğıt kipi yalnız gözlem" ve iniş basamakları satırları "[KALDIRILDI 24 Kasım]" diye işaretlenir.
- `trader/docs/motor/12-risk-kademe.md` §6.1, §8.1, §8.4 aynı şekilde güncellenir.

**8. Testler (`trader/tests`)**
- `engine/test_risk_ladder_spec.py`, `engine/test_risk_ladder_impl.py`:
  - tepeden −%10 ve −%15'te `evaluate` boş döner;
  - `step_config(cfg, s)` her basamak için `cfg`'yi aynen döndürür;
  - −%20 → `review_stop`, %60 → `floor_stop` (art arda 2 ölçüm) değişmeden geçer;
  - içinde `step_down` satırı olan eski günlük hâlâ katlanır ve etkin risk %1'dir.
- `engine/test_canli_kagit_parite.py`, yeni testler:
  - `build_engine` kâğıtta ve canlıda `ladder.enforce is True` verir;
  - aynı özsermaye dizisinde iki kipte aynı `gate_code`, aynı tutuşlar (`drawdown_review`, `capital_floor`, `capital_latch`) ve aynı `risk_config.target_trade_risk == 0.01` çıkar;
  - kâğıt yeniden başlatılınca `review` durumu korunur (dosya günlüğü);
  - günlük yokken kâğıt `initial`'ı kendisi yazar ve `capital_missing` vermez.
- `engine/test_capital_latch.py`, `engine/test_sanal_kasa_spec.py`: kâğıtta `enforce=False` ve bellek günlüğü varsayan beklentiler güncellenir.
- `test_telegram_ladder_spec.py`, `test_telegram_ladder_impl.py`, `test_health_ladder_spec.py`, `test_health_ladder_impl.py`: metinlerde etkin risk %1 beklenir; kâğıt botunda `review` ve `floor` alarmları ile `/kademe_devam` sınanır.
- CLI testi: kâğıtta `ladder` devam komutu satır yazar, `capital init` reddedilir, backtest'te yazan komutlar reddedilir.
- Backtest sonuçlarının bit-bit aynı kaldığını doğrulayan mevcut test değişmeden geçmelidir.