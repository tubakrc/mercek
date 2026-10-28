"""
Mercek - Adım 2: Finansal tabloları ayrıştır, standart kalemlere eşle, kontrol et

Girdi : data/interim/{sirket}/{rapor}/{bilanco|gelir|nakit}.md   (01_parse_test.py çıktısı)
Çıktı : data/processed/all_rows.csv   (her sayısal satır; tanınan kalemlerde 'kalem' dolu)
        + konsolda özet: bulunan/eksik kalemler ve muhasebe kimlik kontrolleri

Önemli: Bu script hangi sütunun hangi dönem olduğuna KARAR VERMEZ.
        Değerler v0, v1, ... olarak sütun sırasıyla yazılır. Sütun-dönem eşlemesini
        PDF'e bakarak sen doğrularsın (Adım 3). Kontroller her sütunda ayrı çalışır.

Kullanım:
  python scripts/02_extract_tables.py
  python scripts/02_extract_tables.py --sirket bim
"""
import argparse
import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path

INTERIM = Path("data/interim")
OUT = Path("data/processed")

# Sayı: 1.234.567 | (1.234) | -1.234 | 31,12 | tek tire (sıfır)
NUM = re.compile(r"^\(?-?\d{1,3}(?:\.\d{3})*(?:,\d+)?\)?$|^-$")
# "Güçlü" sayı: binlik ayraçlı ya da ondalıklı (küçük dipnot numaralarından ayırır)
STRONG = re.compile(r"^\(?-?(?:\d{1,3}(?:\.\d{3})+|\d+,\d+)\)?$")

# Standart kalemler: (anahtar, regex). Etiket norm() ile sadeleştirilip aranır.
# Her kalem için tabloda İLK eşleşen satır alınır.
ITEMS = {
    "bilanco": [
        ("toplam_varliklar", r"^TOPLAM VARLIKLAR"),
        ("donen_varliklar", r"^DONEN VARLIKLAR$"),
        ("duran_varliklar", r"^DURAN VARLIKLAR$"),
        ("nakit_ve_benzerleri", r"^NAKIT VE NAKIT BENZERLERI"),
        ("ticari_alacaklar", r"^TICARI ALACAKLAR$"),
        ("stoklar", r"^STOKLAR"),
        ("kisa_vadeli_yukumlulukler", r"^KISA VADELI YUKUMLULUKLER$"),
        ("uzun_vadeli_yukumlulukler", r"^UZUN VADELI YUKUMLULUKLER$"),
        ("ozkaynaklar", r"^(TOPLAM )?OZKAYNAKLAR$"),
        ("ana_ortaklik_ozkaynaklari", r"^ANA ORTAKLIGA AIT OZKAYNAKLAR"),
        ("toplam_kaynaklar", r"^TOPLAM KAYNAKLAR"),
        ("kisa_vadeli_borclanmalar", r"^KISA VADELI BORCLANMALAR$"),
        ("uzun_vadeli_borclanmalarin_kisa_kismi", r"^UZUN VADELI BORCLANMALARIN KISA VADELI KISIMLARI"),
        ("uzun_vadeli_borclanmalar", r"^UZUN VADELI BORCLANMALAR$"),
        # Üçüncü eleman: kaçıncı eşleşme (BİM'de 1. = kısa vadeli, 2. = uzun vadeli kira borcu).
        # Etiket başka bir satırla birleşmiş olabilir ("Banka Kredileri 870.698 - Kiralama..."),
        # bu yüzden regex satırın herhangi bir yerinde aranır.
        ("banka_kredileri", r"^BANKA KREDILERI"),
        ("kiralama_borclari_kv", r"KIRALAMA ISLEMLERINDEN BORC", 1),
        ("kiralama_borclari_uv", r"KIRALAMA ISLEMLERINDEN BORC", 2),
    ],
    "gelir": [
        ("hasilat", r"^HASILAT"),
        ("satislarin_maliyeti", r"^SATISLARIN MALIYETI"),
        ("brut_kar", r"^BRUT (KAR|ZARAR)"),
        ("esas_faaliyet_diger_gelir", r"^ESAS FAALIYETLERDEN DIGER GELIRLER"),
        ("esas_faaliyet_diger_gider", r"^ESAS FAALIYETLERDEN DIGER GIDERLER"),
        ("esas_faaliyet_kari", r"^ESAS FAALIYET (KARI|ZARARI)"),
        ("finansman_gelirleri", r"^FINANSMAN GELIRLERI"),
        ("finansman_giderleri", r"^FINANSMAN GIDERLERI"),
        ("parasal_kazanc_kayip", r"^(NET )?PARASAL (KAZANC|KAYIP|POZISYON)"),
        ("vergi_oncesi_kar", r"VERGI ONCESI (KAR|ZARAR)"),
        ("donem_kari", r"^(SURDURULEN FAALIYETLER )?(NET )?DONEM (NET )?(KARI|KAR|ZARARI)"),
        ("ana_ortaklik_payi", r"^ANA ORTAKLIK PAY"),
        ("kgop_payi", r"^KONTROL GUCU OLMAYAN PAY"),
    ],
    "nakit": [
        # "faaliyetlerinden" (sağlanan) ve "faaliyetlerinde" (kullanılan) ikisi de olabilir
        ("isletme_nakit_akisi", r"^(A\. )?ISLETME FAALIYETLERINDE"),
        ("yatirim_nakit_akisi", r"^(B\. )?YATIRIM FAALIYETLERINDE"),
        ("finansman_nakit_akisi", r"^(C\. )?FINANSMAN FAALIYETLERINDE"),
    ],
}

# Her şirkette bulunması beklenmeyen kalemler: eksikse hata sayılmaz
OPTIONAL = {
    "uzun_vadeli_borclanmalarin_kisa_kismi", "banka_kredileri",
    "kiralama_borclari_kv", "kiralama_borclari_uv", "stoklar", "ana_ortaklik_ozkaynaklari",
}

# Kimlik kontrolleri: (ad, sol toplam kalemleri, sağ toplam kalemleri). Gider kalemleri
# parantezli (negatif) okunur, bu yüzden düz toplama yeterli.
CHECKS = {
    "bilanco": [
        ("toplam varlik = toplam kaynak", ["toplam_varliklar"], ["toplam_kaynaklar"]),
        ("donen + duran = toplam varlik", ["donen_varliklar", "duran_varliklar"], ["toplam_varliklar"]),
        ("KV + UV yukumluluk + ozkaynak = toplam kaynak",
         ["kisa_vadeli_yukumlulukler", "uzun_vadeli_yukumlulukler", "ozkaynaklar"], ["toplam_kaynaklar"]),
    ],
    "gelir": [
        ("hasilat + maliyet = brut kar", ["hasilat", "satislarin_maliyeti"], ["brut_kar"]),
        ("ana ortaklik + KGOP = donem kari", ["ana_ortaklik_payi", "kgop_payi"], ["donem_kari"]),
    ],
}


def norm(text: str) -> str:
    text = text.replace("ı", "I").replace("İ", "I")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.upper()


def to_float(tok: str) -> float:
    if tok == "-":
        return 0.0
    neg = tok.startswith("(") or tok.startswith("-")
    value = float(tok.strip("()-").replace(".", "").replace(",", "."))
    return -value if neg else value


def clean(line: str) -> str:
    line = line.replace("**", " ").replace("|", " ").replace("`", " ")
    line = re.sub(r"(?<!\w)_+|_+(?!\w)", " ", line)  # italik alt çizgiler
    line = re.sub(r"^\s*[-•]\s+", "", line)           # madde işareti
    return re.sub(r"\s+", " ", line).strip()


def split_row(line: str) -> tuple[str, list[str]]:
    """Satırı (etiket, sondaki sayısal token'lar) olarak ayırır."""
    toks = line.split(" ")
    tail: list[str] = []
    while toks and NUM.match(toks[-1]):
        tail.append(toks.pop())
    tail.reverse()
    label = re.sub(r"[\d,\s]+$", "", " ".join(toks)).strip()  # dipnot kalıntıları ("8, 29")
    return label, tail


def split_merged(line: str) -> list[str]:
    """PDF'te yan yana duran iki satır tek satıra düşebilir. Sayısal bir değerden
    (veya '-') sonra harfle başlayan metin gelirse ve solda en az bir güçlü sayı varsa böl."""
    toks, parts, cur = line.split(" "), [], []
    for i, t in enumerate(toks):
        cur.append(t)
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if (NUM.match(t) and nxt[:1].isalpha()
                and any(STRONG.match(c) for c in cur)):
            parts.append(" ".join(cur))
            cur = []
    if cur:
        parts.append(" ".join(cur))
    return parts


def parse_table(text: str) -> list[dict]:
    rows, pending = [], ""
    lines = [part for raw in text.splitlines() for part in split_merged(clean(raw))]
    for line in lines:
        if not line:
            continue
        label, tail = split_row(line)
        is_data = bool(label) and any(STRONG.match(t) or t == "-" for t in tail)
        if is_data:
            # Etiket iki satıra bölünmüş olabilir: önceki metin satırını da sakla
            ctx = f"{pending} {label}".strip() if pending else label
            rows.append({"label": label, "ctx": ctx, "tail": tail})
            pending = ""
        else:
            pending = line
    return rows


def detect_ncols(rows: list[dict]) -> int:
    counts = Counter(sum(1 for t in r["tail"] if STRONG.match(t)) for r in rows)
    counts.pop(0, None)
    n = counts.most_common(1)[0][0] if counts else 2
    return min(max(n, 2), 4)


def map_items(tablo: str, rows: list[dict]) -> dict[str, int]:
    """kalem -> rows içindeki indeks. Varsayılan: ilk eşleşen satır; (anahtar, regex, n) ise n. eşleşen."""
    found: dict[str, int] = {}
    entries = ITEMS.get(tablo, [])
    start = 0
    if tablo == "gelir":
        # Gelir tablosu 'Hasılat' ile başlar. Öncesindeki satırlar (örn. bilançonun son
        # sayfasındaki 'Kontrol gücü olmayan paylar') yanlış eşleşmeye yol açabilir.
        for idx, r in enumerate(rows):
            if re.search(r"^HASILAT", norm(r["label"])):
                start = idx
                break
    seen: Counter = Counter()
    patterns = {e[1] for e in entries}
    for idx, r in enumerate(rows):
        if idx < start:
            continue
        n_label, n_ctx = norm(r["label"]), norm(r["ctx"])
        hit = {p: bool(re.search(p, n_label) or re.search(p, n_ctx)) for p in patterns}
        for p in patterns:
            if hit[p]:
                seen[p] += 1
        for entry in entries:
            key, pattern = entry[0], entry[1]
            nth = entry[2] if len(entry) > 2 else 1
            if key not in found and hit[pattern] and seen[pattern] == nth:
                found[key] = idx
                break
    return found


def run_checks(tablo: str, values: dict[str, list[float]], ncols: int) -> list[str]:
    lines = []
    for name, left, right in CHECKS.get(tablo, []):
        if not all(k in values for k in left + right):
            lines.append(f"    [ATLANDI] {name} (eksik kalem)")
            continue
        results = []
        for j in range(ncols):
            lhs = sum(values[k][j] for k in left)
            rhs = sum(values[k][j] for k in right)
            diff = lhs - rhs
            ok = abs(diff) <= max(5, abs(rhs) * 1e-6)
            results.append(f"v{j}:{'OK' if ok else f'HATA(fark {diff:,.0f})'}")
        lines.append(f"    {name}: " + "  ".join(results))
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interim", default=str(INTERIM))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--sirket")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(Path(args.interim).glob("*/*/*.md"))
    if args.sirket:
        files = [f for f in files if f.parent.parent.name == args.sirket]
    if not files:
        print("md dosyası bulunamadı. Önce 01_parse_test.py çalıştırılmalı.")
        return

    csv_rows = []
    for f in files:
        sirket, rapor, tablo = f.parent.parent.name, f.parent.name, f.stem
        rows = parse_table(f.read_text(encoding="utf-8"))
        if not rows:
            print(f"\n{sirket}/{rapor}/{tablo}: sayısal satır bulunamadı")
            continue
        ncols = detect_ncols(rows)
        rows = [r for r in rows if len(r["tail"]) >= ncols]
        found = map_items(tablo, rows)
        key_by_idx = {i: k for k, i in found.items()}
        values = {}
        for i, r in enumerate(rows):
            vals = [to_float(t) for t in r["tail"][-ncols:]]
            key = key_by_idx.get(i, "")
            if key:
                values[key] = vals
            csv_rows.append(
                {"sirket": sirket, "rapor": rapor, "tablo": tablo, "ncols": ncols,
                 "kalem": key, "etiket": r["label"],
                 **{f"v{j}": (vals[j] if j < ncols else "") for j in range(4)}}
            )

        wanted = [e[0] for e in ITEMS.get(tablo, [])]
        missing = [k for k in wanted if k not in found and k not in OPTIONAL]
        missing_opt = [k for k in wanted if k not in found and k in OPTIONAL]
        print(f"\n{sirket}/{rapor}/{tablo}: sütun={ncols}, satır={len(rows)}, "
              f"kalem {len(found)}/{len(wanted)}")
        if missing:
            print(f"    EKSIK: {', '.join(missing)}")
        if missing_opt:
            print(f"    (opsiyonel, bulunamadı: {', '.join(missing_opt)})")
        for line in run_checks(tablo, values, ncols):
            print(line)

    path = out_dir / "all_rows.csv"
    fields = ["sirket", "rapor", "tablo", "ncols", "kalem", "etiket", "v0", "v1", "v2", "v3"]
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(csv_rows)
    print(f"\nYazıldı: {path} ({len(csv_rows)} satır)")


if __name__ == "__main__":
    main()
