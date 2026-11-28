# 200 / 300 işlemde bakılacak sorular

Çıktı: `var/learner/olcum/ozet.json` (ham satırlar `satirlar-YYYY-MM.jsonl`, 14 ay). Ölçümlerin kaydı `src/trader_engine/olcumler.py` (`KAYIT`); bu tablo ile birebir aynı olmak zorundadır (`tests/test_olcum_kaydi.py`).
Karar kuralları sonradan değiştirilmez; değişirse tarihli not düşülür.

| soru | ölçüm | ne zaman | karar kuralı (önceden yazıldı) |
|---|---|---|---|
| Eksik dakikalar ölçümü bozuyor mu? | `eksik_dakika_stop` | 200 | Temkinli stopla kapanan işlem, kapanan gerçek işlemlerin %5'inden fazlaysa veri akışı (feed) hata düzeltmesi olarak ele alınır; ≤ %5 ise yalnız izlenir. |
| Sanal (gölge) satırlar tam ağırlıkla eğitime girmeli mi? | `golge_gercek` | 200 | n ≥ 30 iken yön uyumu < %85 ya da ort. \|ΔR\| > 0,30 ise sanal ağırlık 0,5 (otomatik, kodda). 300'de uyum < %70 ise sahibe "sanal öğrenmeyi kapat" kararı sorulur. |
| İz süren stop ve zaman çıkışı 1 dk / 5 dk / 15 dk'da mı güncellenmeli? | `iz_kadans` | 300 | İz kipli ≥ 100 gerçek işlemde ort. (R_1dk − R_15dk) ya da (R_5dk − R_15dk) > +0,05 R ve eşli t ≥ 2 ise kadans değişikliği sahibe önerilir (dondurma sonrası). Değilse 15 dk kalır, soru kapanır. |
