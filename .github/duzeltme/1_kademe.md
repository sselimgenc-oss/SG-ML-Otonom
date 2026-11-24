Sen kidemli bir risk yonetimi ve kod uzmanisin. Proje: Binance USDT-M vadeli islem botu "ML Otonom" (kod trader/). Yalniz okuyabilirsin.
Kullanici kurali: kagit = canli, ikisi AYNI davranmali.

SORUN (denetimde dogrulandi): risk kademesi kagitta enforce=False (yalniz gozlem), canlida enforce=True. Canlida risk %0,5'e inebiliyor, -%20 durmasi,
taban durmasi ve aktarim eslestirmesi calisiyor; kagitta hicbiri calismiyor. Bak: trader/src/trader_engine/ladder.py (107, 204 civari),
trader/src/trader_core/risk_ladder.py, trader/src/trader_engine/engine.py (2660 civari), trader/config/engine.paper.json ve engine.live.json,
otonom-trading-arastirma/tasarim-kararlari.md (kademe ile ilgili kararlar).

KULLANICI: "Bu karari Fable versin. %0,5 az gibi; %1 ikisinde de mantikli gibi." Islem basi temel risk zaten %1.

GOREV: Kademenin ne yaptigini (hangi kosulda riski dusurur, hangi kosulda durdurur) kisaca cikar. Sonra TEK bir karar ver, kagit ve canli icin AYNI:
ornegin (a) kademe ikisinde de uygulanir ama dusurulmus risk %0,5 yerine X olur, (b) risk dusurme kaldirilir, risk hep %1 kalir; durma esikleri (-%20, taban)
ikisinde de uygulanir, (c) baska. Kullanicinin %1 tercihini dikkate al; buna karsi guclu bir neden varsa acikca yaz.
Son mesajinda YALNIZ Markdown, sade Turkce:
# Risk kademesi karari
## Kademe bugun ne yapiyor (kisa tablo)
## Karar (tek cumle) ve gerekce (3-5 madde)
## Uygulama talimati (uygulayici bunu AYNEN kodlayacak: hangi dosya, hangi ayar/sabit, kagit ve canli icin ne olacak, hangi testler)
