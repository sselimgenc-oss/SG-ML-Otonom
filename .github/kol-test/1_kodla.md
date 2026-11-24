Sen kidemli bir Python/kantitatif gelistiricisin. Proje: Binance USDT-M vadeli islem botu "ML Otonom" (kod trader/ altinda).
Gorevin: fikirler/yeni-kollar/tasarim_v2.md dosyasindaki uc yeni kolu (MF1, GF1, IN1) YALNIZ ARASTIRMA amacli geri test olarak kodlamak.
Once o dosyayi oku. Turkce, ASCII dosya adlari; kod yorumlari kisa Turkce.

KAPSAM (cok onemli):
- Yalniz trader/research/yeni_kollar/ altina yaz. Motor (trader/src), ayar (trader/config), mevcut testler, .github DEGISMEZ. git komutu calistirma (commit/push yok).
- freqtrade/ccxt/python-binance kullanma. Kurulu paketler: numpy, pandas (trader/requirements.lock). Yeni paket kurma.

VERI:
- Mumlar: trader/research/dl1/veri.py icindeki indir(pairs, bas_ay, kesim, ham_dir, tf=...) (Binance Vision; ham_dir = trader/var/vision_raw, onbellekli).
  Ciftler: trader/config/engine.paper.json "pairs". 15m icin 2023-01'den, 1h/4h/1d icin 2021-01'den.
- Fonlama: trader/scripts/fetch_binance_vision.py fundingRate indirmeyi destekler; ayni yardimcilarla indir. Fonlama inmezse veto kapali calis ve raporda yaz.
- Maliyet: trader/research/dl1/cekirdek.py maliyet_tablosu() (motorun kagit maliyetleri: ucret + kayma, cift basina). Bu tabloyu kullan.

GERI TEST KURALLARI:
- Karar t mumunun kapanisinda; giris t+1 acilisinda (kayma dahil). Stop/hedef intrabar; ayni mumda ikisi de vurulursa STOP. Zaman stopu kolun mum sayisi; son mumun kapanisinda cik.
- Bosluk: acilis stopu astiysa acilistan dolum. R = (cikis - giris) / (giris - stop), maliyet dusulmus net R. Fonlama: pozisyon acikken gecen fonlama anlari R'ye eklenir.
- Ayni cift + ayni kol + ayni zaman diliminde acik pozisyon varken yeni giris yok.
- Ileriye bakis YASAK: pivot yalniz 3 mum sonra kesinlesir; ust ZD yalniz kapanmis mum (ornegin 15m'de t aninda kapanmis son 1h mumu); onceki gun/hafta seviyesi biten donemden;
  VWAP ve hacim ortalamasi yalniz gecmis mumlardan. Gostergeleri (RSI Wilder, MACD, EMA, ATR Wilder) kendin yaz, numpy ile vektorlestir.

DONEM:
- Gelistirme donemi: veri basi .. 2025-07-01 (haric). Kilitli donem (holdout): 2025-07-01 .. bugun.
- Calistirici: trader/research/yeni_kollar/calistir.py --donem gelistirme|kilitli --cikti <dizin>. "kilitli" yalniz --kilidi-ac bayragiyla calissin, yoksa hata versin.
  Sen kilitli donemi CALISTIRMA.

CIKTI (calistir.py):
- <dizin>/sonuc.json ve <dizin>/ozet.md. Her kol x zaman dilimi x yon icin: islem sayisi, kazanma orani, ortalama net R, toplam net R, kar faktoru, en buyuk dusus (R),
  yil yil toplam R, cift basina dagilim (en iyi/en kotu 5), ortalama tutma suresi, cikis turleri (stop/hedef/zaman).
- Teyit acma-kapama (ablation): her kol ve zaman dilimi icin ortak teyitlerin (ust ZD, seviye, hacim, fonlama, maliyet tabani) her birini TEK TEK kapatip ayni metrikleri yaz.
  Ayrica "hic teyit yok" (yalniz sekil) surumu.
- Rastgele karsilastirma: ayni sayida rastgele giris (ayni stop/hedef kurali, ayni yon dagilimi, tohum sabit) ortalama net R.
- Calisma suresi: tam gelistirme kosusu 2,5 saati gecmesin (gerekirse ablation'i paralel calistir: multiprocessing).

TESTLER: trader/research/yeni_kollar/test_yeni_kollar.py (pytest): her gosterge icin bilinen degerle karsilastirma; pivotun ve ust ZD'nin gelecegi
gormedigini kanitlayan test (gelecek mumlari degistirince t anindaki sinyal degismez); ayni mumda stop+hedef -> stop; bosluk dolumu; her kol icin elle kurulmus
kucuk bir sentetik ornekte beklenen sinyal. Testlerin hepsi gecmeli (skip/xfail YOK).

CALISMA SEKLI: is akisi testleri `cd trader && PYTHONPATH=src:paket python -m pytest -q research/yeni_kollar` ve
`cd trader && PYTHONPATH=src:paket python research/yeni_kollar/calistir.py --donem gelistirme --cikti ../sonuc_tur1` ile calistirir; kendin de boyle calistir.

SON ADIM: pytest calistir; sonra 3 cift (BTC/USDT, ETH/USDT, SOL/USDT), 1h, 2024-01..2024-04 ile kisa bir duman kosusu yap ve hatasiz bittigini gor.
Son mesajinda kisa Turkce: ne yaptin, dosyalar, test sonucu, duman kosusu sayilari, bilinen eksikler.
