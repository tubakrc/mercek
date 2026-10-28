"""
Mercek - Adım 6: Arama kalitesini gözle karşılaştır (BM25 vs vektör vs hybrid)

Kullanım:
  uv run python scripts/06_search_test.py
  uv run python scripts/06_search_test.py "Aselsan'ın alınan avansları ne kadar?" --sirket aselsan
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mercek.retriever import Retriever, format_citation  # noqa: E402

DEFAULT_QUERIES = [
    ("Finansal borçların vade yapısı nedir?", "tupras", "2025_12"),
    ("Kiralama yükümlülükleri ne kadar ve nasıl ölçülüyor?", "bim", "2025_12"),
    ("Sözleşme varlıkları ve alınan avanslar", "aselsan", "2025_12"),
    ("TMS 29 enflasyon muhasebesi hangi endeksle uygulandı?", None, "2025_12"),
    ("Koşullu yükümlülükler ve verilen teminatlar", "tupras", "2026_6"),
]


def show(r: Retriever, q: str, sirket, rapor, k: int) -> None:
    print("\n" + "=" * 100)
    print(f"SORU: {q}   [şirket={sirket or 'hepsi'}, rapor={rapor or 'hepsi'}]")
    for mode in ("bm25", "vector", "hybrid"):
        print(f"\n  -- {mode}")
        for i, h in enumerate(r.search(q, sirket, rapor, k=k, mode=mode), 1):
            print(f"  {i}. {format_citation(h)[:85]:85s} {h['ranks']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?")
    ap.add_argument("--sirket")
    ap.add_argument("--rapor")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()
    r = Retriever()
    if args.query:
        show(r, args.query, args.sirket, args.rapor, args.k)
    else:
        for q, s, rp in DEFAULT_QUERIES:
            show(r, q, s, rp, args.k)


if __name__ == "__main__":
    main()
