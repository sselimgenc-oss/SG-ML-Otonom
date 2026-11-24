"""Derin denetim, tarama adimi (Haiku). Bir alani salt okuma araclariyla tarar, bulgulari bulgu-<alan>.json'a yazar.

Ortam: ALAN_ID, ALAN_AD, DOSYALAR (bosluklu liste), ANTHROPIC_API_KEY. Kod degistirmez (yalniz Read/Grep/Glob).
"""
import asyncio
import json
import os
import re

from claude_agent_sdk import ClaudeAgentOptions, query

ALAN_ID = os.environ["ALAN_ID"]
ALAN_AD = os.environ["ALAN_AD"]
DOSYALAR = os.environ["DOSYALAR"].split()

PROMPT = f"""Sen bir kod denetcisisin. Proje: Binance USDT-M vadeli islem botu "ML Otonom" (kod trader/ altinda). Kagit modda calisiyor;
canli ayar dosyasi kagitla AYNI davranmali. Yalniz okuyabilirsin (Read, Grep, Glob). Kod degistirme.

DENETLENECEK ALAN: {ALAN_AD}
BASLANGIC DOSYALARI (gerekirse cagrilan/cagiran yerlere Grep ile git): {' '.join(DOSYALAR)}

Ara:
1. Ayar dosyasinda (trader/config/*.json) ya da kodda tanimli olup HIC okunmayan / hicbir etkisi olmayan degerler (olu ayar).
2. Hic cagrilmayan ya da hep ayni sonucu veren kod (olu kod, etkisiz dal).
3. Belgede (docstring, yorum, trader/docs, otonom-trading-arastirma/tasarim-kararlari.md) yazan davranis ile kodun gercek davranisinin farkli oldugu yerler.
4. Kagit ile canli arasinda farkli davranan yerler.
5. Gercek hatalar: yanlis isaret/yon (long/short), birim hatasi (bps/yuzde, ms/s, UTC/TSI), sinir kosulu, bos veri, ileriye bakis (kapanmamis mum), cift sayim, yaris.
6. Yanlis seyi dogrulayan ya da hicbir sey dogrulamayan testler (yalniz alanla ilgiliyse).

KURALLAR: Her bulgu icin dosya ve satiri kendin okuyarak dogrula; tahmin yazma. Emin olmadigini "emin_degil" isaretle.
Kullanici kararlariyla celisen tasarim tercihlerini (kalite kapisiz model yayini, onaysiz ders, 5 dk otomatik guncelleme) hata sayma.
Kucuk stil konularini yazma. En fazla 15 bulgu; en onemliler once.

CIKTI: Son mesajinda YALNIZ su JSON'u yaz (baska metin yok):
{{"alan": "{ALAN_ID}", "bulgular": [{{"dosya": "...", "satir": 0, "tur": "olu_ayar|olu_kod|belge_farki|kagit_canli|hata|test", "onem": "yuksek|orta|dusuk",
"sorun": "kisa Turkce", "kanit": "kodda ne gordun (kisa alinti/aciklama)", "emin_degil": false}}]}}
"""


async def main() -> None:
    opts = ClaudeAgentOptions(model="claude-haiku-5-5", allowed_tools=["Read", "Grep", "Glob"], max_turns=80, cwd=".")
    son = ""
    maliyet = None
    async for m in query(prompt=PROMPT, options=opts):
        r = getattr(m, "result", None)
        if r:
            son = r
        c = getattr(m, "total_cost_usd", None)
        if c is not None:
            maliyet = c
    veri = {"alan": ALAN_ID, "bulgular": [], "ham": son[-4000:]}
    j = re.search(r"\{.*\}", son, re.S)
    if j:
        try:
            veri = json.loads(j.group(0))
        except json.JSONDecodeError:
            pass
    veri["maliyet_usd"] = maliyet
    with open(f"bulgu-{ALAN_ID}.json", "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=1)
    print(f"{ALAN_ID}: {len(veri.get('bulgular', []))} bulgu, maliyet {maliyet}")


asyncio.run(main())
