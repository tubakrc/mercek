"""
Mercek - Adım 1: PDF parse testi

Ne yapar?
  1. data/raw/{sirket}/{rapor}.pdf dosyalarını tarar
  2. Taranmış (metinsiz) sayfa var mı kontrol eder
  3. Bilanço / gelir tablosu / nakit akış sayfalarını bulur
  4. Bu sayfaları markdown olarak data/interim/ altına yazar (gözle kontrol için)

Kullanım:
  python scripts/01_parse_test.py
  python scripts/01_parse_test.py --sirket bim
"""
import argparse
import re
import unicodedata
from pathlib import Path

import pymupdf
import pymupdf4llm

RAW = Path("data/raw")
OUT = Path("data/interim")

# Başlıklar şirketten şirkete değişir (TABLOSU/TABLOLARI, KAR/KÂR...).
# Bu yüzden kökler aranır; metin önce norm() ile sadeleştirilir.
KEYS = {
    "bilanco": ["FINANSAL DURUM TABLO"],
    "gelir": ["KAR VEYA ZARAR", "KAR/ZARAR"],
    "nakit": ["NAKIT AKIS"],
}

# Başlık eşleşse bile sayfada bu satır etiketlerinden biri olmalı
# (dipnot sayfalarındaki yanlış eşleşmeleri eler).
MARKERS = {
    "bilanco": ["TOPLAM VARLIKLAR", "TOPLAM KAYNAKLAR", "KISA VADELI YUKUMLULUKLER", "TOPLAM OZKAYNAKLAR"],
    "gelir": ["HASILAT", "BRUT KAR", "DONEM KARI"],
    "nakit": ["ISLETME FAALIYETLERINDEN"],
}


def norm(text: str) -> str:
    """Türkçe karakterleri, şapkalı harfleri (Â, Î, Û) ve büyük/küçük farkını sadeleştirir."""
    text = text.replace("ı", "I").replace("İ", "I")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.upper()


def first_cluster(idxs: list[int]) -> list[int]:
    """Ana tablolar belgenin başında ardışık sayfalarda durur; sonraki eşleşmeler dipnotlardır."""
    if not idxs:
        return []
    out = [idxs[0]]
    for i in idxs[1:]:
        if i != out[-1] + 1:
            break
        out.append(i)
    return out


def numeric_tokens(text: str) -> int:
    """Sayfadaki sayı benzeri token sayısı (içindekiler sayfasını elemek için)."""
    return len(re.findall(r"\(?\d{1,3}(?:\.\d{3})+\)?", text))


def find_statement_pages(doc: pymupdf.Document) -> dict[str, list[int]]:
    found = {k: [] for k in KEYS}
    for i, page in enumerate(doc):
        text = page.get_text()
        if numeric_tokens(text) < 15:
            continue
        head = norm(text[:700])
        body = norm(text)
        for kind, keys in KEYS.items():
            if any(k in head for k in keys) and any(m in body for m in MARKERS[kind]):
                found[kind].append(i)
    return {kind: first_cluster(idxs) for kind, idxs in found.items()}


def process(pdf_path: Path) -> None:
    sirket = pdf_path.parent.name
    rapor = pdf_path.stem
    doc = pymupdf.open(pdf_path)

    empty = [i + 1 for i, p in enumerate(doc) if len(p.get_text().strip()) < 30]
    print(f"\n=== {sirket} / {rapor} === ({len(doc)} sayfa)")
    if len(empty) > len(doc) * 0.2:
        print(f"  UYARI: {len(empty)} sayfada metin yok, PDF taranmış olabilir (OCR gerekir).")
    elif empty:
        print(f"  Metinsiz sayfalar (muhtemelen görsel/boş): {empty[:10]}")

    pages = find_statement_pages(doc)
    out_dir = OUT / sirket / rapor
    out_dir.mkdir(parents=True, exist_ok=True)

    for kind, idxs in pages.items():
        if not idxs:
            print(f"  {kind:8s}: BULUNAMADI -> anahtar kelimeleri kontrol et")
            continue
        print(f"  {kind:8s}: sayfa {[i + 1 for i in idxs]}")
        md = pymupdf4llm.to_markdown(doc, pages=idxs)
        (out_dir / f"{kind}.md").write_text(md, encoding="utf-8")

    print(f"  Çıktı: {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sirket", help="Sadece bu klasördeki PDF'leri işle (örn. bim)")
    args = ap.parse_args()

    pdfs = sorted(RAW.glob("*/*.pdf"))
    if args.sirket:
        pdfs = [p for p in pdfs if p.parent.name == args.sirket]
    if not pdfs:
        print(f"PDF bulunamadı. Beklenen düzen: {RAW}/bim/2025_12.pdf")
        return
    for p in pdfs:
        process(p)


if __name__ == "__main__":
    main()
