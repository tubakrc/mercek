"""
Mercek - Adım 9: MCP sunucusunu gerçek bir MCP istemcisiyle test et

Sunucuyu alt süreç olarak (stdio) başlatır, araç/kaynak/prompt listesini alır ve her aracı örnek
girdilerle çağırır. Claude Desktop'un yaptığının aynısıdır.

Kullanım:
  uv run python scripts/09_mcp_test.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent

CALLS = [
    ("sirket_listesi", {}),
    ("bildirim_listesi", {"sirket": "tupras"}),
    ("bildirim_detay", {"bildirim_id": "bim-2026_6"}),
    ("finansal_ozet", {"sirket": "aselsan", "rapor": "2026_6"}),
    ("finansal_trend", {"sirket": "bim", "kalem": "ozkaynaklar"}),
    ("dipnot_ara", {"soru": "kiralama yükümlülükleri TFRS 16", "sirket": "bim", "rapor": "2026_6", "k": 2}),
    ("fiyat_verisi", {"sirket": "aselsan"}),
    ("bildirim_detay", {"bildirim_id": "garanti-2025_12"}),  # hata yolu
]


def attr(obj, snake: str, camel: str):
    """mcp 2.x alan adları snake_case (server_info), 1.x camelCase (serverInfo)."""
    return getattr(obj, snake) if hasattr(obj, snake) else getattr(obj, camel)


def text_of(result) -> str:
    parts = [getattr(c, "text", str(c)) for c in result.content]
    return "\n".join(parts)


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "mercek.mcp_server"],
                                   cwd=str(ROOT), env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"Sunucu: {attr(init, 'server_info', 'serverInfo').name}  "
                  f"(protokol {attr(init, 'protocol_version', 'protocolVersion')})")

            tools = (await session.list_tools()).tools
            print(f"\nAraçlar ({len(tools)}):")
            for t in tools:
                params_ = ", ".join(attr(t, "input_schema", "inputSchema").get("properties", {}).keys())
                print(f"  - {t.name}({params_})")

            resources = (await session.list_resources()).resources
            print(f"\nKaynaklar: {[str(r.uri) for r in resources]}")
            prompts = (await session.list_prompts()).prompts
            print(f"Promptlar: {[p.name for p in prompts]}")

            for name, args in CALLS:
                res = await session.call_tool(name, args)
                out = text_of(res)
                print(f"\n>>> {name}({args})" + ("  [HATA]" if (getattr(res, "is_error", None) or getattr(res, "isError", False)) else ""))
                print(out[:600] + (" …" if len(out) > 600 else ""))

            meta = await session.read_resource("mercek://metodoloji")
            print("\n>>> mercek://metodoloji\n" + text_of_resource(meta)[:400])
            pr = await session.get_prompt("sirket_analizi", {"sirket": "Tüpraş", "rapor": "2025_12"})
            print("\n>>> prompt sirket_analizi\n" + pr.messages[0].content.text[:200])


def text_of_resource(res) -> str:
    return "\n".join(getattr(c, "text", "") for c in res.contents)


if __name__ == "__main__":
    asyncio.run(main())
