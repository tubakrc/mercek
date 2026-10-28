"""
Yardımcı: all_rows.csv içinden satırları filtreleyip gösterir.

Kullanım:
  python scripts/show_rows.py tupras 2025_12 gelir
  python scripts/show_rows.py tupras 2025_12 gelir "DONEM|ANA ORTAKLIK|KONTROL|PARASAL"
  python scripts/show_rows.py bim 2025_12 bilanco "BORC|KIRA|FINANSAL"

Regex büyük harfle ve Türkçe karaktersiz yazılır (İ, Ş, Ğ, Ü, Ö, Ç -> I, S, G, U, O, C).
"""
import argparse
import csv
import re
import unicodedata
from pathlib import Path


def norm(text: str) -> str:
    text = text.replace("ı", "I").replace("İ", "I")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.upper()


def fmt(v: str) -> str:
    return "" if v == "" else f"{float(v):,.0f}".replace(",", ".")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sirket")
    ap.add_argument("rapor")
    ap.add_argument("tablo", choices=["bilanco", "gelir", "nakit"])
    ap.add_argument("regex", nargs="?", default="")
    ap.add_argument("--csv", default="data/processed/all_rows.csv")
    args = ap.parse_args()

    path = Path(args.csv)
    if not path.exists():
        print(f"{path} yok. Önce 02_extract_tables.py çalıştırılmalı.")
        return

    pattern = re.compile(args.regex) if args.regex else None
    n = 0
    with path.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if (r["sirket"], r["rapor"], r["tablo"]) != (args.sirket, args.rapor, args.tablo):
                continue
            if pattern and not pattern.search(norm(r["etiket"])):
                continue
            n += 1
            vals = " | ".join(f"{fmt(r[f'v{j}']):>16s}" for j in range(int(r["ncols"])))
            print(f"{r['kalem'] or '-':26s} {r['etiket'][:58]:58s} {vals}")
    if n == 0:
        print("Eşleşen satır yok.")


if __name__ == "__main__":
    main()
