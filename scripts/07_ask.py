"""
Mercek - Adım 7: Agent'a komut satırından soru sor

Kullanım:
  uv run python scripts/07_ask.py "Tüpraş'ın 2026 ilk yarı hasılat artışı ne kadar ve nedeni ne?"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mercek import agent, multi_agent  # noqa: E402

DEMO = [
    "Tüpraş'ın 2026 ilk yarı hasılatı geçen yılın aynı dönemine göre ne kadar arttı ve dipnotlarda bunun nedeni hakkında ne var?",
    "BİM'in finansal borcu ne kadar ve bunun ne kadarı kira yükümlülüğü? Kira yükümlülükleri nasıl ölçülüyor?",
    "Aselsan'ın son üç dönemde özkaynakları nasıl değişti?",
]

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--multi"]
    ask = multi_agent.ask if "--multi" in sys.argv else agent.ask
    questions = [" ".join(args)] if args else DEMO
    for q in questions:
        print("=" * 100 + f"\nSORU: {q}\n")
        out = ask(q)
        for i, s in enumerate(out["adimlar"], 1):
            print(f"  adım {i}: [{s.get('agent', 'agent')}] {s['arac']}({json.dumps(s['girdi'], ensure_ascii=False)})")
        print("\n" + out["cevap"] + "\n")
