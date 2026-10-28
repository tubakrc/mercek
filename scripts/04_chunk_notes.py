"""
Mercek - Adım 4: Dipnotları (açıklayıcı notlar) chunk'la

Girdi : data/raw/{sirket}/{rapor}.pdf
Çıktı : data/processed/chunks.jsonl   (her satır bir chunk + metadata)
        konsolda her rapor için bulunan not başlıkları (gözle kontrol için)

Yaklaşım:
  1. Dipnotların başladığı sayfayı bul ("AÇIKLAYICI NOTLAR" / "DİPNOT" başlığı).
  2. Her sayfadaki tekrar eden başlık bloğunu ve basılı sayfa numarasını sil.
  3. Ana not başlıklarını ("7." / "NOT 7 -" / "7. BORÇLANMALAR") SIRA KONTROLÜYLE bul:
     not numarası yalnızca bir öncekinin aynısı (Devamı) veya 1-2 fazlası olabilir.
     Bu, metin içindeki "3." gibi rastgele satırların başlık sanılmasını engeller.
  4. Her notu ~1500 karakterlik, paragraf sınırına saygılı parçalara böl.
  5. Her chunk'ın başına bağlam başlığı ekle: [BİM | 2025/12 | Not 7 - Borçlanmalar]
     (contextual chunk header: chunk tek başına okunduğunda da kime/neye ait olduğu belli olur)

Kullanım:
  python scripts/04_chunk_notes.py
  python scripts/04_chunk_notes.py --sirket tupras --rapor 2025_12 --verbose
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

RAW = Path("data/raw")
OUT = Path("data/processed/chunks.jsonl")

SIRKET_ADI = {"bim": "BİM", "tupras": "Tüpraş", "aselsan": "Aselsan"}
# "DIPNOTLAR" (çoğul): tekil "Dipnot" / "Dipnot Referansları" tablo sütun başlığıdır, dipnot sayfası değil
NOTES_KEYS = ["ACIKLAYICI NOT", "DIPNOTLAR", "TABLOLARA ILISKIN NOTLAR"]
# Ana tablo tespiti 01_parse_test.py ile aynı mantık: başlık + satır etiketi + ilk ardışık sayfa kümesi.
# Dipnot başlangıcı en son ana tablo sayfasından sonra aranır.
STATEMENT_TITLES = {
    "bilanco": (["FINANSAL DURUM TABLO"], ["TOPLAM VARLIKLAR", "TOPLAM KAYNAKLAR", "TOPLAM OZKAYNAKLAR"]),
    "gelir": (["KAR VEYA ZARAR", "KAR/ZARAR"], ["HASILAT", "BRUT KAR", "DONEM KARI"]),
    "nakit": (["NAKIT AKIS"], ["ISLETME FAALIYETLERINDE"]),
    "ozkaynak": (["OZKAYNAK DEGISIM", "OZKAYNAKLAR DEGISIM"], ["ODENMIS SERMAYE", "SERMAYE"]),
}
CHUNK_CHARS = 1500
OVERLAP_CHARS = 200
MAX_NOTE = 60

# "7." | "7" yalnız değil (sayfa no ile karışır) | "NOT 7" | "NOT 7 -" | "7. BORÇLANMALAR" | "7 - BORÇLANMALAR"
HEAD_SAME = re.compile(r"^(?:NOT\s*)?(\d{1,2})\s*(?:\.|-|–|:)\s*([A-ZÇĞİÖŞÜa-zçğıöşü].{2,150})$", re.I)
HEAD_ALONE = re.compile(r"^(?:NOT\s*(\d{1,2})\s*[.\-–:]?|(\d{1,2})\s*[.\-–:])$", re.I)
SUBHEAD = re.compile(r"^(\d{1,2}(?:\.\d{1,2})+)\.?\s+([A-ZÇĞİÖŞÜa-zçğıöşü].{2,150})$")


def norm(text: str) -> str:
    text = text.replace("ı", "I").replace("İ", "I")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.upper()


def strip_header(text: str) -> list[str]:
    """Sayfa başındaki tekrar eden bloğu ve basılı sayfa numarasını atar."""
    lines = [l.strip() for l in text.splitlines()]
    cut = 0
    for i, l in enumerate(lines[:14]):
        n = norm(l)
        if "IFADE EDILMIS" in n or (any(k in n for k in NOTES_KEYS) and cut == 0):
            cut = i + 1
    lines = lines[cut:]
    # Boş satırları atlayıp ilk satır yalnızca sayıysa (basılı sayfa no) sil
    while lines and not lines[0]:
        lines.pop(0)
    if lines and re.fullmatch(r"\d{1,3}", lines[0]):
        lines.pop(0)
    return lines


def looks_like_title(t: str) -> bool:
    """Başlıklar kısa olur ve cümle gibi noktayla bitmez."""
    raw = re.sub(r"\(\s*devam[ıi]\s*\)", "", t, flags=re.I).strip()
    return 2 < len(raw) <= 110 and len(raw.split()) <= 14 and not raw.endswith((".", ",", ";"))


def clean_title(t: str) -> str:
    t = re.sub(r"\(\s*devam[ıi]\s*\)", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" -–:.")


def _numeric_tokens(text: str) -> int:
    return len(re.findall(r"\(?\d{1,3}(?:\.\d{3})+\)?", text))


def last_statement_page(pages: list[str]) -> int:
    """Ana tabloların (bilanço, gelir, özkaynak, nakit) son sayfasının indeksi; yoksa -1."""
    last = -1
    for titles, markers in STATEMENT_TITLES.values():
        idxs = [i for i, txt in enumerate(pages)
                if _numeric_tokens(txt) >= 15
                and any(t in norm(txt[:700]) for t in titles)
                and any(m in norm(txt) for m in markers)]
        if not idxs:
            continue
        cluster = [idxs[0]]  # ilk ardışık küme = asıl tablo; sonrakiler dipnot sayfaları
        for i in idxs[1:]:
            if i != cluster[-1] + 1:
                break
            cluster.append(i)
        last = max(last, cluster[-1])
    return last


def find_notes_start(pages: list[str], run: int = 3) -> int | None:
    """Son ana tablodan sonra, dipnot başlığını art arda en az `run` sayfada taşıyan ilk sayfa."""
    last_stmt = last_statement_page(pages)
    heads = [norm(txt[:700]) for txt in pages]
    hit = [i > last_stmt and any(k in h for k in NOTES_KEYS) for i, h in enumerate(heads)]
    for i in range(len(hit)):
        if len(hit[i:i + run]) == run and all(hit[i:i + run]):
            return i
    if any(hit):
        return hit.index(True)
    if 0 <= last_stmt < len(pages) - 1:
        print("    UYARI: dipnot başlığı bulunamadı, son ana tablodan sonraki sayfa kullanıldı")
        return last_stmt + 1
    return None


def segment_notes(pages: list[tuple[int, list[str]]]) -> list[dict]:
    """[(pdf_sayfa, satırlar)] -> [{not_no, baslik, paragraflar:[(sayfa, metin, alt_baslik)]}]"""
    notes: list[dict] = []
    cur_no, cur = 0, None
    sub = ""
    for page_no, lines in pages:
        buf: list[str] = []

        def flush():
            nonlocal buf
            text = re.sub(r"[ \t]+", " ", "\n".join(buf)).strip()
            if text and cur is not None:
                cur["paras"].append((page_no, text, sub))
            buf = []

        i = 0
        while i < len(lines):
            line = lines[i]
            num, title = None, None
            m = HEAD_SAME.match(line)
            if m and not SUBHEAD.match(line) and looks_like_title(m.group(2)):
                num, title = int(m.group(1)), m.group(2)
            else:
                m = HEAD_ALONE.match(line)
                if m:
                    j = i + 1
                    while j < len(lines) and not lines[j]:
                        j += 1
                    nxt = lines[j] if j < len(lines) else ""
                    if nxt and nxt[0].isalpha() and looks_like_title(nxt):
                        num, title = int(m.group(1) or m.group(2)), nxt
                        i = j  # başlık satırını da tüket
            explicit = norm(line).startswith("NOT")
            step_ok = num is not None and (num == cur_no or cur_no < num <= cur_no + (10 if explicit else 3))
            if step_ok and num <= MAX_NOTE:
                flush()
                if num != cur_no or cur is None:
                    cur_no = num
                    cur = {"not_no": num, "baslik": clean_title(title), "paras": []}
                    notes.append(cur)
                sub = ""
                i += 1
                continue
            sm = SUBHEAD.match(line)
            if sm and sm.group(1).split(".")[0] == str(cur_no):
                flush()
                sub = f"{sm.group(1)} {clean_title(sm.group(2))}"
            elif re.fullmatch(r"\d{1,2}(?:\.\d{1,2})+\.?", line) and i + 1 < len(lines):
                # "2.1." yalnız satır, başlık bir sonraki satırda
                flush()
                sub = f"{line.rstrip('.')} {clean_title(lines[i + 1])}"
                buf.append(sub)
                i += 2
                continue
            buf.append(line)
            i += 1
        flush()
    return notes


def split_text(text: str) -> list[str]:
    """Paragraf sınırlarını koruyarak ~CHUNK_CHARS uzunluğunda parçalar, OVERLAP_CHARS örtüşmeli."""
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        while len(p) > CHUNK_CHARS:  # tek paragraf çok uzunsa satırdan böl
            cut = p.rfind("\n", 0, CHUNK_CHARS)
            cut = cut if cut > CHUNK_CHARS // 2 else CHUNK_CHARS
            chunks.append((cur + "\n\n" + p[:cut]).strip() if cur else p[:cut])
            cur, p = "", p[cut:]
        if len(cur) + len(p) > CHUNK_CHARS and cur:
            chunks.append(cur.strip())
            cur = cur[-OVERLAP_CHARS:].split("\n", 1)[-1]
        cur = f"{cur}\n\n{p}" if cur else p
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def build_chunks(sirket: str, rapor: str, notes: list[dict]) -> list[dict]:
    out = []
    rapor_lbl = rapor.replace("_", "/")
    for note in notes:
        # Sayfa takibi: paragrafları sayfa işaretiyle birleştir
        text, spans = "", []
        for page, para, sub in note["paras"]:
            start = len(text)
            text += para + "\n\n"
            spans.append((start, page, sub))
        for k, chunk in enumerate(split_text(text)):
            pos = text.find(chunk[:80])
            pages = [p for s, p, _ in spans if s <= max(pos, 0) + len(chunk)]
            first = next((p for s, p, _ in reversed(spans) if s <= max(pos, 0)), spans[0][1])
            subs = [sb for s, _, sb in spans if s <= max(pos, 0) + len(chunk) and sb]
            header = f"[{SIRKET_ADI.get(sirket, sirket)} | {rapor_lbl} | Not {note['not_no']} - {note['baslik']}]"
            out.append({
                "id": f"{sirket}-{rapor}-n{note['not_no']}-{k}",
                "sirket": sirket, "rapor": rapor,
                "donem_tipi": "6m" if rapor.endswith("_6") or rapor.endswith("_06") else "12m",
                "not_no": note["not_no"], "not_baslik": note["baslik"],
                "alt_baslik": subs[-1] if subs else "",
                "sayfa_bas": first, "sayfa_bit": max(pages) if pages else first,
                "text": f"{header}\n{chunk}",
            })
    return out


def process(pdf: Path, verbose: bool) -> list[dict]:
    import pymupdf  # sadece burada gerekli; test için modül import'u hafif kalır

    sirket, rapor = pdf.parent.name, pdf.stem
    doc = pymupdf.open(pdf)
    texts = [p.get_text() for p in doc]
    start = find_notes_start(texts)
    if start is None:
        print(f"{sirket}/{rapor}: dipnot başlangıcı bulunamadı")
        return []
    pages = [(i + 1, strip_header(texts[i])) for i in range(start, len(texts))]
    notes = segment_notes(pages)
    chunks = build_chunks(sirket, rapor, notes)
    print(f"\n{sirket}/{rapor}: dipnot başlangıcı s.{start + 1}, {len(notes)} not, {len(chunks)} chunk")
    nums = [n["not_no"] for n in notes]
    gaps = sorted(set(range(1, max(nums) + 1)) - set(nums)) if nums else []
    if gaps:
        print(f"    UYARI: atlanan not numaraları {gaps} (başlık kalıbı farklı olabilir)")
    if verbose or len(notes) < 15:
        for n in notes:
            print(f"    Not {n['not_no']:>2}: {n['baslik'][:70]}")
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sirket")
    ap.add_argument("--rapor")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    pdfs = sorted(RAW.glob("*/*.pdf"))
    if args.sirket:
        pdfs = [p for p in pdfs if p.parent.name == args.sirket]
    if args.rapor:
        pdfs = [p for p in pdfs if p.stem == args.rapor]
    all_chunks = []
    for pdf in pdfs:
        all_chunks += process(pdf, args.verbose)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        for c in all_chunks:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    lens = [len(c["text"]) for c in all_chunks]
    if lens:
        print(f"\nYazıldı: {OUT} ({len(all_chunks)} chunk, ort. {sum(lens) // len(lens)} karakter)")


if __name__ == "__main__":
    main()
