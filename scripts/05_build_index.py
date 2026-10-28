"""
Mercek - Adım 5: Dipnot chunk'larını embedding'leyip Chroma indeksine yaz

Girdi : data/processed/chunks.jsonl
Çıktı : data/index/embeddings.jsonl  (embedding önbelleği; yeniden kurulumda API çağrısı yapılmaz)
        CHROMA_DIR                    (varsayılan data/index/chroma; .env ile değiştirilebilir)

Gereken: .env dosyasında OPENAI_API_KEY (önbellekte olmayan chunk'lar için)

Kullanım:
  uv run python scripts/05_build_index.py          # yeni embedding gerekiyorsa onay ister
  uv run python scripts/05_build_index.py --yes
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mercek import config  # noqa: E402
from mercek.retriever import load_chunks, openai_embed  # noqa: E402

META_KEYS = ["sirket", "rapor", "donem_tipi", "not_no", "not_baslik", "alt_baslik", "sayfa_bas", "sayfa_bit"]


def cache_key(text: str) -> str:
    return hashlib.sha1(f"{config.EMBED_MODEL}|{text}".encode("utf-8")).hexdigest()


def load_cache() -> dict[str, list[float]]:
    if not config.EMBED_CACHE.exists():
        return {}
    with config.EMBED_CACHE.open(encoding="utf-8") as fh:
        return {r["k"]: r["e"] for r in map(json.loads, fh) if r}


def path_warning(p: Path) -> None:
    s = str(p.resolve())
    if os.name == "nt" and (not s.isascii() or "onedrive" in s.lower()):
        print(f"UYARI: Chroma yolu '{s}' ASCII dışı karakter veya OneDrive içeriyor.")
        print("       Windows'ta indeks okunamayabilir. .env dosyasına örn. CHROMA_DIR=C:/mercek_index ekle.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    chunks = load_chunks()
    cache = load_cache()
    todo = [c for c in chunks if cache_key(c["text"]) not in cache]
    print(f"{len(chunks)} chunk, önbellekte {len(chunks) - len(todo)}, yeni embedding gereken {len(todo)}")

    if todo:
        if not os.getenv("OPENAI_API_KEY"):
            sys.exit("OPENAI_API_KEY bulunamadı. .env dosyasına OPENAI_API_KEY=sk-... ekle.")
        chars = sum(len(c["text"]) for c in todo)
        print(f"~{chars // 3:,} token, model: {config.EMBED_MODEL} (fiyat: platform.openai.com/pricing)")
        if not args.yes and input("Devam edilsin mi? [e/h] ").strip().lower() not in ("e", "evet", "y"):
            return
        t0 = time.time()
        embs = openai_embed([c["text"] for c in todo])
        config.EMBED_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with config.EMBED_CACHE.open("a", encoding="utf-8") as fh:
            for c, e in zip(todo, embs):
                k = cache_key(c["text"])
                cache[k] = e
                fh.write(json.dumps({"k": k, "e": e}) + "\n")
        print(f"Embedding tamam: {len(embs)} vektör, {time.time() - t0:.1f} sn")

    import chromadb

    path_warning(config.CHROMA_DIR)
    config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    try:
        client.delete_collection(config.COLLECTION)  # temiz yeniden kurulum
    except Exception:
        pass
    col = client.create_collection(config.COLLECTION, metadata={"hnsw:space": "cosine",
                                                               "embed_model": config.EMBED_MODEL})
    for i in range(0, len(chunks), 500):
        part = chunks[i:i + 500]
        col.add(ids=[c["id"] for c in part], documents=[c["text"] for c in part],
                embeddings=[cache[cache_key(c["text"])] for c in part],
                metadatas=[{k: c[k] for k in META_KEYS} for c in part])

    # Okuma testi: indeks yazıldığı yerden geri okunabiliyor mu?
    col = chromadb.PersistentClient(path=str(config.CHROMA_DIR)).get_collection(config.COLLECTION)
    probe = cache[cache_key(chunks[0]["text"])]
    got = col.query(query_embeddings=[probe], n_results=1)["ids"][0]
    status = "OK" if got and got[0] == chunks[0]["id"] else f"BEKLENMEDİK SONUÇ {got}"
    print(f"Yazıldı: {config.CHROMA_DIR} ({col.count()} kayıt), okuma testi: {status}")


if __name__ == "__main__":
    main()
