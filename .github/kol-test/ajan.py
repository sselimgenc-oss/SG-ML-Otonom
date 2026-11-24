"""Yeni kol testi: tek bir Agent SDK adimini calistirir (harcama ANTHROPIC_API_KEY_DENETIM = promosyon kredisi).

Kullanim: python ajan.py <model> <istem.md> <son_mesaj.md> <butce_usd> <max_turns> [yalniz_oku]
Maliyet maliyet.txt dosyasina eklenir (adim adi, $).
"""
import asyncio
import sys

from claude_agent_sdk import ClaudeAgentOptions, query

model, istem, cikti, butce, tur = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), int(sys.argv[5])
yalniz_oku = len(sys.argv) > 6 and sys.argv[6] == "yalniz_oku"
araclar = ["Read", "Grep", "Glob"] if yalniz_oku else ["Read", "Grep", "Glob", "Write", "Edit", "Bash"]


async def main() -> None:
    opts = ClaudeAgentOptions(model=model, allowed_tools=araclar, permission_mode="bypassPermissions",
                              max_turns=tur, max_budget_usd=butce, cwd=".")
    son, maliyet = "", 0.0
    async for m in query(prompt=open(istem, encoding="utf-8").read(), options=opts):
        r = getattr(m, "result", None)
        if r:
            son = r
        c = getattr(m, "total_cost_usd", None)
        if c is not None:
            maliyet = c
    with open(cikti, "w", encoding="utf-8") as f:
        f.write(son or "(ajan son mesaj vermedi)")
    with open("maliyet.txt", "a", encoding="utf-8") as f:
        f.write(f"{istem}\t{model}\t{maliyet:.2f}\n")
    print(f"{istem}: {maliyet:.2f} $")


asyncio.run(main())
