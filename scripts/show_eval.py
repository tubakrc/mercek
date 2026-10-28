"""
Son eval çalıştırmasındaki cevapları gösterir (varsayılan: yalnızca başarısızlar).

Kullanım:
  uv run python scripts/show_eval.py              # son çalıştırma, başarısız sorular
  uv run python scripts/show_eval.py R02 R09      # belirli sorular
  uv run python scripts/show_eval.py --all        # tüm sorular
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "sonuclar"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--run", help="klasör adı (varsayılan: en son)")
    args = ap.parse_args()

    runs = sorted(p for p in RESULTS.glob("*") if p.is_dir())
    if not runs:
        sys.exit("Henüz eval sonucu yok. Önce scripts/08_eval.py çalıştır.")
    run = RESULTS / args.run if args.run else runs[-1]
    for path in sorted(run.glob("*.csv")):
        with path.open(encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            if args.ids and r["id"] not in args.ids:
                continue
            if not args.ids and not args.all and r["tam_dogru"] == "True":
                continue
            print("=" * 90)
            tekrar = f"#{r['tekrar']}" if r.get("tekrar") else ""
            print(f"[{r['config']}] {r['id']}{tekrar} ({r['kategori']})  {r['gecen']}/{r['toplam']}  "
                  f"{r['sure_sn']} sn  ${r['maliyet_usd']}")
            print(f"SORU    : {r['soru']}")
            print(f"ARAÇLAR : {r['araclar']}")
            if r["basarisiz"]:
                print(f"BAŞARISIZ: {r['basarisiz']}")
            print(f"CEVAP   :\n{r['cevap']}\n")
    print(f"(klasör: {run.name})")


if __name__ == "__main__":
    main()
