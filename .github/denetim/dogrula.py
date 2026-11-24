"""Derin denetim, dogrulama adimi (Fable). Haiku bulgularini kodda tek tek dogrular, sade Turkce rapor yazar.

Kullanim: python dogrula.py <bulgu dizini> <rapor.md>. Kod degistirmez (yalniz Read/Grep/Glob).
"""
import asyncio
import glob
import json
import os
import sys

from claude_agent_sdk import ClaudeAgentOptions, query

dizin, cikti = sys.argv[1], sys.argv[2]
bulgular = []
maliyet_tarama = 0.0
for p in sorted(glob.glob(os.path.join(dizin, "*.json"))):
    with open(p, encoding="utf-8") as f:
        v = json.load(f)
    maliyet_tarama += v.get("maliyet_usd") or 0.0
    for b in v.get("bulgular", []):
        b["alan"] = v.get("alan")
        bulgular.append(b)

PROMPT = f"""Sen kidemli bir kod denetcisisin. Proje: Binance vadeli islem botu "ML Otonom" (kod trader/ altinda; kagit = canli olmali).
Asagida Haiku ajanlarinin buldugu {len(bulgular)} aday bulgu var. Yalniz okuyabilirsin (Read, Grep, Glob).

GOREV: Her bulguyu kodda KENDIN dogrula. Sinifla: DOGRU (kodda gercekten var), YANLIS (ajan yanilmis), KISMEN.
Yanlislari ayikla. Ayni sorunu tekrarlayanlari birlestir. Kullanici kararlariyla celisen tasarim tercihlerini (kalite kapisiz model yayini,
onaysiz ders, 5 dk otomatik guncelleme) hata sayma. Taramanin kacirdigi cok onemli bir sey gorursen ekle (en fazla 5).

CIKTI: Son mesajinda YALNIZ Markdown rapor yaz, sade Turkce, kisa cumleler:
# Derin denetim raporu
## Ozet (kac aday, kac dogru, kac yanlis; en onemli 5 madde tek satir)
## Dogrulanan sorunlar (tablo: # | Onem | Alan | Dosya:satir | Sorun | Ne yapilmali) — onem sirasiyla
## Yanlis cikan aday bulgular (tablo: Alan | Iddia | Neden yanlis) — kisa
## Notlar (emin olunamayanlar)

ADAY BULGULAR (JSON):
{json.dumps(bulgular, ensure_ascii=False)}
"""


async def main() -> None:
    opts = ClaudeAgentOptions(model="claude-fable-5-2", allowed_tools=["Read", "Grep", "Glob"], max_turns=250, cwd=".")
    son = ""
    maliyet = None
    async for m in query(prompt=PROMPT, options=opts):
        r = getattr(m, "result", None)
        if r:
            son = r
        c = getattr(m, "total_cost_usd", None)
        if c is not None:
            maliyet = c
    alt = f"\n\n---\nMaliyet: tarama {maliyet_tarama:.2f} $, dogrulama {(maliyet or 0):.2f} $ (Agent SDK, promosyon kredisi).\n"
    with open(cikti, "w", encoding="utf-8") as f:
        f.write((son or "# Derin denetim raporu\n\nDogrulama ciktisi alinamadi.") + alt)
    print(alt)


asyncio.run(main())
