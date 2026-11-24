Sen kidemli bir Python/kantitatif gelistiricisin. Proje: Binance USDT-M vadeli botu "ML Otonom" (kod trader/).
trader/research/yeni_kollar/ altinda onceki turun geri test cercevesi var (veri indirme, gostergeler, pivotlar, cikis simulasyonu, maliyet, fonlama, ablation, rastgele kiyas,
testler). Once kodu ve README/notlari oku.
YENI GOREV: setup_secimi.md dosyasindaki 12 setupu bu cerceveye ekle (her biri ayri setup kimligi, kategorisi MF1/GF1/IN1). Mevcut cikis simulasyonu, maliyet, fonlama,
ileriye bakis kurallari AYNEN gecerli (karar t kapanisi, giris t+1 acilisi, ayni mumda stop+hedef -> stop, bosluk dolumu, pivot onay gecikmesi, ust ZD yalniz kapanmis mum).
Setuplari KITAPTA YAZDIGI GIBI kodla; kendi teyidini ekleme.

Calistirici: trader/research/yeni_kollar/calistir.py'ye --setuplar v3 secenegi ekle (12 setup x 4 ZD (15m,1h,4h,1d) x yon). Ciktida her setup x ZD icin:
islem, kazanma %, ort net R, toplam R, kar faktoru, en buyuk dusus R, yil yil R, cift dagilimi, rastgele kiyas (setup basina 200 cekilis), cikis turleri.
EVREN: kilitli donemle ayni olsun: engine.paper.json'daki TUM ciftler (hisse/emtia arsivde yoksa o ciftin gecmisi kisadir; raporda yaz).
Donemler: --donem gelistirme (veri basi..2025-07-01) ve --donem kilitli --kilidi-ac (2025-07-01..bugun). Sen kilitli donemi CALISTIRMA.
Testler: her yeni setup icin sentetik ornekte beklenen sinyal + ileriye bakis testi (gelecek mumlar degisince t sinyali degismez). pytest hepsi gecmeli, skip/xfail yok.
Calistirma: `cd trader && PYTHONPATH=src:paket python -m pytest -q research/yeni_kollar` ve kisa duman (3 cift, 1h, 2024-01..2024-04).
Tam gelistirme kosusu 2,5 saati gecmesin (multiprocessing kullan). git komutu yok. Yalniz trader/research/yeni_kollar/ altina yaz.
Son mesajinda kisa Turkce: eklenen setuplar, test sonucu, duman sayilari, bilinen eksikler.
