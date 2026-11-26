# ortak_ogrenme (SURUM 1.2.1)

Ortak öğrenme paketi: aday kaydı (`Aday`), kodla yazılan işlem notu (`notlar.not_yaz`) ve aday ders yaşam döngüsü
(`ders`). Yalnız Python 3.11+ standart kütüphane kullanılır (ortak filtre modülü `filtre.py` 24.11'de kaldırıldı). `trader_core` / `trader_engine` / `trader_ml` içe aktarılmaz.
Paket yalnız puan, rapor ve etiket üretir; hiçbir işlemi engellemez. Spec: `docs/standart/ortak-ogrenme-paketi-spec.md`.

## Kopyalama

1. Bu klasörü (`trader/paket/ortak_ogrenme/`) alan projenin paket dizinine olduğu gibi kopyalayın.
2. Kaynak yolu ve commit'i not edin, örnek: `Kaynak: trader/paket/ortak_ogrenme @ <commit>, SURUM 1.2.1`.
3. Paketi değiştirmeyin. Projeye özgü çeviri yalnız adaptörde yapılır.
4. Adaptörünüzü yazın (aşağıdaki örnek) ve kendi testinizde ML/başka bir referansla eşdeğerliği doğrulayın.
   (25.11: ML'deki `trader_core/trade_notes.py` ve onun parite testi kaldirildi; paket kendi spec testleriyle (`test_ortak_ogrenme_spec.py`) dogrulanir.)

## Adaptör örneği

Kendi işlem kaydınızı `Aday`'a çevirin. Kapanmış işlemler için `cikis` ve `ozellikler` alanlarını doldurun.

```python
from datetime import timezone
from ortak_ogrenme.kayit import Aday
from ortak_ogrenme import notlar, ders

def adaya_cevir(islem, karar):
    """islem: kapanmış işlem kaydınız; karar: karar anı kaydınız (yoksa None)."""
    ozellikler = dict(karar.features) if karar else {}
    if karar and karar.atr_ratio is not None:
        ozellikler["atr_ratio"] = karar.atr_ratio   # yuksek_vol bu anahtarı okur
    return Aday(
        id=str(islem.trade_id), proje="ML", kurulum=islem.setup, enstruman=islem.pair,
        varlik_sinifi="kripto", yon=islem.side,
        ts=(karar.bar_close_ts if karar else islem.entry_ts).astimezone(timezone.utc),
        alindi=True, r=islem.r_multiple,
        seans=karar.session_tag if karar else None, rejim=islem.regime,
        ozellikler=ozellikler,
        cikis={"entry_price": islem.entry_price, "planned_entry": islem.planned_entry,
               "planned_stop": islem.planned_stop, "exit_reason": islem.exit_reason,
               "bars_held": islem.bars_held, "mfe_r": islem.mfe_r, "mae_r": islem.mae_r},
    )

# Kullanım:
# etiketler, metin = notlar.not_yaz(adaya_cevir(islem, karar))
# etki, n = ders.ders_etkisi(adaylar, "seans_kapali:T1", "2026-05-01", as_of, shrink_n=10)
```

## Önemli notlar

- `kurulum` değeri ders kimliğinde doğrudan kullanılır (`ders:<kod>:<kurulum>`). Etiket sözlüğü yalnız
  harf, rakam ve `_` kabul eder. `@` içeren bir kurulum (örn. `T1@1h`) kayıpta ders etiketi üretirken `ValueError`
  verir. Adaptörde kurulumu `@` öncesi kısımla verin.
- `ders_etkisi` varsayılan `shrink_n = 0` (spec). ML kâğıt kararı da 0'dır.
  Eşdeğerlik testlerinde iki taraf da açıkça aynı değerle çağrılır.
- Durum dosyası (`gece_adimi`) atomik yazılır; bozuk veya eksik dosya boş durum sayılır.

## Parça 2: karne, sanal kasa, drift

Girdi her yerde `Aday` listesidir. Paket yine yalnız puan ve rapor üretir; bir işlemi engelleyip engellemediği
adaptörün kararıdır.

### `karne.py` (standart kütüphane)

- `karne(adaylar, kurulumlar=())`: kurulum başına `aday`, `alinan`, `cozulen`, `ort_r_alinan`, `ort_r_tum`,
  varlık sınıfına göre `sinif` ve `kasa`. `kurulumlar` içindeki adaysız kurulumlar sıfır satırla yer alır.
- `sanal_kasa(adaylar, *, baslangic=1000.0, risk=0.01, kurulumlar=())`: ML'deki `arm_virtual_bankroll` ile aynı
  kural. Seri `{n, kasa, getiri_pct, en_derin_pct}`; `en_derin_pct` tepe noktasından pozitif yüzde olarak verilir.
  `alinan` yalnız alınan işlemleri, `tum` alınmayan ("alınsaydı") işlemleri de içerir.

### `drift.py` (standart kütüphane)

- `cusum(rs)`: ML `cusum_replay` ile aynı sabitler ve kurallar. `alarms` 1-tabanlı indekslerdir.
- `kurulum_drift(adaylar)`: alınmış ve R'si bilinen adaylar üzerinden kurulum başına CUSUM. `durum` alanı son
  alarmdan beri 30 işlemden az geçtiyse `uyari`, değilse `normal` olur.

### Parça 2 eşdeğerlik testleri

`tests/paket/test_ortak_ogrenme_parca2_parity.py`: `karne` / `sanal_kasa` ↔ `arm_scorecard` / `arm_virtual_bankroll`
(alan adı eşlemesiyle), `cusum` ↔ `cusum_replay`.

## Parça 3: Telegram çekirdeği (`telegram_cekirdek.py`, standart kütüphane)

Telegram standardının (`trader/docs/standart/telegram-standardi.md`) çekirdeği: metin temizleme, proje etiketi,
istemci, kuyruk, bildirici ve iki adımlı onay. Ağ çağrısı enjekte edilir (`http_post(url, json=..., timeout=...)
-> (status, body)`); verilmezse `urllib` kullanılır. Token hiçbir çıktıda bulunmaz (`mask`).

- Sabitler: `MAX_TEXT=3500`, `CODE_TTL_S=120`, `INFO_MAX_AGE_S=86400`, `RATE_PER_MIN=15`, `SEVERITIES`, `PROJELER=("ML","1L3A","CT")`.
- `mask`, `neutralize`, `fit_text`: ML `trader_core.telegram` ile birebir (parite testi).
- `etiketle(proje, metin)`: ilk satıra `[PROJE] ` ekler; zaten etiketliyse eklemez; bilinmeyen proje `ValueError`.
- `TelegramClient`, `Outbox`: ML ile aynı hata sınıfları, 429 `retry_after`, hız sınırı ve INFO yaşlanması.
- `TelegramNotifier(client, chat_id, outbox, now_fn, proje)`: `send_text(metin, severity, dedup_key, ...)`
  metni etiketler, kuyruğa alır, tekrarı önler. Dönüş `bool`: teslim edildiyse `True`.
- `OnayKapisi(dosya, now_fn, rng=secrets)`: `baslat(komut, ozet) -> kod` (4 hane, mesajla gönderilir) ve
  `dogrula(komut, kod) -> bool`. Kod 120 sn geçerlidir, tek kullanımlıktır; yanlış kod bekleyen isteği siler;
  başka komut için doğrulama reddedilir ve istek kalır. Dosyada yalnız `sha256(kod)` tutulur. Denetim kaydı
  `<dosya-adı>.denetim.jsonl` dosyasına `zaman, olay, komut, sonuc` alanlarıyla yazılır.

### Kullanım örneği

```python
from datetime import datetime, timezone
from pathlib import Path
from ortak_ogrenme.telegram_cekirdek import TelegramClient, TelegramNotifier, Outbox, OnayKapisi
simdi = lambda: datetime.now(timezone.utc)
var = Path("var/telegram")
istemci = TelegramClient(token)                       # http_post verilmezse urllib
kuyruk = Outbox(var, simdi)
bildirici = TelegramNotifier(istemci, chat_id, kuyruk, simdi, "1L3A")
bildirici.send_text("Giriş: BTC long, 65000, stop 64000", "INFO", dedup_key="giris:T1:42")
bildirici.send_text("Kapanış: kayıp -1.0R", "WARN", dedup_key="cikis:T1:42")
kuyruk.drain(istemci, chat_id)                        # kuyruktakileri gönder (hız sınırı burada)
onay = OnayKapisi(var / "onay.json", simdi)
kod = onay.baslat("/durdur", "Yeni girişler durdurulacak")
bildirici.send_text(f"120 sn içinde yalnız şu kodu yanıtla: {kod}", "WARN", dedup_key="onay:durdur")
ok = onay.dogrula("/durdur", yanit.strip())           # yanit: kullanıcının mesajı; True ise durdur
```

### Parça 3 eşdeğerlik testleri

`tests/paket/test_ortak_ogrenme_parca3_parity.py`: `mask` / `neutralize` / `fit_text` ↔ `trader_core.telegram`,
`TelegramClient` hata sınıfları, `Outbox` (kuyruk, hız sınırı, INFO yaşlanması, tekrar önleme) ve bildirici
tekrar önleme/yeniden deneme davranışı ML ile aynı sahte HTTP ve sahte saatle karşılaştırılır. Onay kapısı,
etiketleme ve denetim kaydı için ayrı testler vardır. Testler ağ kullanmaz.

## Sürüm notları
- 1.2.1: `telegram_cekirdek.default_http_post` requests tarzı `(bağlantı, okuma)` zaman aşımı demetini urllib'in tek sayısına çevirir (önceden her çağrı TypeError → `(0, {})` → "transient 0"; varsayılan istemciyle hiçbir çağrı çalışmıyordu).
