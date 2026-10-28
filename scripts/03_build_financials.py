"""
Mercek - Adım 3: Sütun-dönem eşlemesi + raporlar arası TMS 29 tutarlılık kontrolü

Girdi : data/processed/all_rows.csv            (02_extract_tables.py çıktısı)
        data/config/column_overrides.json      (opsiyonel, sadece varsayılan yanlışsa)
Çıktı : data/processed/financials.csv          (uzun format, agent'ların okuyacağı tablo)

Varsayılan sütun düzeni (PDF'lerde gözlenen):
  2 sütun : v0 = güncel dönem, v1 = önceki dönem
  4 sütun : v0 = 6 ay güncel, v1 = 3 ay (Q2) güncel, v2 = 6 ay önceki, v3 = 3 ay önceki

Kontroller:
  A) 4 sütunlu tablolarda 6 aylık değer 3 aylıktan büyük olmalı (hasılat).
  B) TMS 29 katsayısı: Bir raporun 'önceki' sütunu, önceki raporun 'güncel' sütununun
     enflasyonla büyütülmüş hâlidir. Katsayı = TÜFE oranıdır, şirketten bağımsızdır.
     Yani aynı rapor çifti için ÜÇ ŞİRKETTE AYNI katsayı çıkmalı. Farklıysa ya sütun
     eşlemesi yanlıştır ya da şirket o kalemi yeniden sınıflandırmıştır.

Kullanım:
  python scripts/03_build_financials.py
"""
import argparse
import csv
import json
import statistics
from calendar import monthrange
from collections import defaultdict
from pathlib import Path

DEFAULT_LAYOUT = {
    2: ["guncel", "onceki"],
    4: ["guncel", "q_guncel", "onceki", "q_onceki"],
}
# Katsayı kontrolünde kullanılan kalemler (yeniden sınıflandırmaya en az maruz toplamlar)
CHECK_ITEMS = {"bilanco": ["toplam_varliklar", "toplam_kaynaklar"], "gelir": ["hasilat"]}
TOLERANCE = 0.01  # şirketler arası katsayı farkı için %1


def report_end(rapor: str) -> tuple[int, int]:
    """'2026_6' veya '2026_06' -> (2026, 6)"""
    y, m = rapor.split("_")
    return int(y), int(m)


def period(tablo: str, kolon: str, rapor: str) -> tuple[str, str]:
    """(başlangıç, bitiş) ISO tarih. Bilançoda başlangıç = bitiş (tarih itibarıyla)."""
    y, m = report_end(rapor)
    end = lambda yy, mm: f"{yy}-{mm:02d}-{monthrange(yy, mm)[1]:02d}"
    if tablo == "bilanco":
        # Bilançoda karşılaştırma her zaman bir önceki yıl sonudur (ara dönemde de)
        d = end(y, m) if kolon == "guncel" else end(y - 1, 12)
        return d, d
    yy = y if kolon in ("guncel", "q_guncel") else y - 1
    if kolon.startswith("q_"):
        return f"{yy}-{m - 2:02d}-01", end(yy, m)
    return f"{yy}-01-01", end(yy, m)


def load_overrides(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default="data/processed/all_rows.csv")
    ap.add_argument("--overrides", default="data/config/column_overrides.json")
    ap.add_argument("--out", default="data/processed/financials.csv")
    args = ap.parse_args()

    overrides = load_overrides(Path(args.overrides))
    with open(args.rows, encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh) if r["kalem"]]

    # (sirket, rapor, tablo, kalem, kolon) -> değer
    facts: dict[tuple, float] = {}
    out_rows = []
    for r in rows:
        key = f'{r["sirket"]}/{r["rapor"]}/{r["tablo"]}'
        n = int(r["ncols"])
        layout = overrides.get(key, DEFAULT_LAYOUT.get(n))
        if not layout or len(layout) != n:
            print(f"UYARI: {key} için {n} sütunluk düzen tanımlı değil, atlandı.")
            continue
        for j, kolon in enumerate(layout):
            if kolon in ("", "atla"):
                continue
            val = float(r[f"v{j}"])
            facts[(r["sirket"], r["rapor"], r["tablo"], r["kalem"], kolon)] = val
            bas, bit = period(r["tablo"], kolon, r["rapor"])
            out_rows.append({
                "sirket": r["sirket"], "rapor": r["rapor"], "tablo": r["tablo"],
                "kalem": r["kalem"], "kolon": kolon, "donem_baslangic": bas,
                "donem_bitis": bit, "deger": val, "birim": "bin TL", "etiket": r["etiket"],
            })

    sirketler = sorted({r["sirket"] for r in rows})
    raporlar = sorted({r["rapor"] for r in rows}, key=report_end)

    # --- Kontrol A: 6 aylık > 3 aylık
    print("Kontrol A: 4 sütunlu tablolarda 6 aylık > 3 aylık (hasılat)")
    for (s, rp, t, k, kol), v in sorted(facts.items()):
        if k == "hasilat" and kol in ("guncel", "onceki"):
            q = facts.get((s, rp, t, k, "q_" + kol))
            if q is not None:
                ok = v > q
                print(f"  {s:8s} {rp:8s} {kol:7s}: 6 ay {v:>16,.0f}  3 ay {q:>16,.0f}  "
                      f"{'OK' if ok else 'HATA: sütun sırası yanlış olabilir'}")

    # --- Kontrol B: TMS 29 katsayısı
    print("\nKontrol B: TMS 29 katsayısı (önceki raporun güncel sütunu -> sonraki raporun önceki sütunu)")
    ratios = defaultdict(dict)  # (rapor_yeni, rapor_eski, tablo, kalem) -> {sirket: katsayı}
    for s in sirketler:
        for new in raporlar:
            for old in raporlar:
                if old == new:
                    continue
                for tablo, kalemler in CHECK_ITEMS.items():
                    # 'önceki' dönemi, eski raporun 'güncel' dönemiyle aynı mı?
                    if period(tablo, "onceki", new) != period(tablo, "guncel", old):
                        continue
                    for k in kalemler:
                        a = facts.get((s, new, tablo, k, "onceki"))
                        b = facts.get((s, old, tablo, k, "guncel"))
                        if a and b:
                            ratios[(new, old, tablo, k)][s] = a / b

    flagged = 0
    for (new, old, tablo, k), by_s in sorted(ratios.items()):
        med = statistics.median(by_s.values())
        parts = []
        for s, r in sorted(by_s.items()):
            off = abs(r / med - 1) > TOLERANCE
            flagged += off
            parts.append(f"{s}={r:.4f}{' <-- FARKLI' if off else ''}")
        print(f"  {new} vs {old} {tablo:7s} {k:18s}: " + "  ".join(parts))
    if not ratios:
        print("  Karşılaştırılabilir rapor çifti bulunamadı.")
    elif flagged:
        print(f"\n  {flagged} sapma var. İlgili raporun PDF'ine bakıp sütun düzenini kontrol et;")
        print("  gerekiyorsa data/config/column_overrides.json ile düzelt.")
    else:
        print("\n  Tüm katsayılar şirketler arasında tutarlı: sütun eşlemesi doğru görünüyor.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"\nYazıldı: {out} ({len(out_rows)} satır)")


if __name__ == "__main__":
    main()
