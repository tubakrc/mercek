"""
Mercek - Adım 10: Embedding'leri deploy için tek bir sıkıştırılmış dosyaya aktar

Girdi : data/processed/chunks.jsonl, data/index/embeddings.jsonl (05_build_index.py önbelleği)
Çıktı : data/index/embeddings.npz   (ids + float32 vektörler; ~7 MB, repoya girer)

Uygulama açılırken Chroma indeksi yoksa bu dosyadan OpenAI'a istek atmadan kurulur.
05_build_index.py'yi her yeniden çalıştırdığında bunu da çalıştır.

Kullanım:
  uv run python scripts/10_export_index.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mercek import config  # noqa: E402
from mercek.retriever import load_chunks  # noqa: E402


def cache_key(text: str) -> str:  # 05_build_index.py ile aynı anahtar
    return hashlib.sha1(f"{config.EMBED_MODEL}|{text}".encode("utf-8")).hexdigest()


def main() -> None:
    if not config.EMBED_CACHE.exists():
        sys.exit(f"{config.EMBED_CACHE} yok. Önce scripts/05_build_index.py çalıştır.")
    chunks = load_chunks()
    cache = {}
    with config.EMBED_CACHE.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                cache[r["k"]] = r["e"]
    missing = [c["id"] for c in chunks if cache_key(c["text"]) not in cache]
    if missing:
        sys.exit(f"{len(missing)} chunk'ın embedding'i önbellekte yok (örn. {missing[0]}). Önce 05_build_index.py.")
    ids = np.array([c["id"] for c in chunks])
    vectors = np.array([cache[cache_key(c["text"])] for c in chunks], dtype=np.float32)
    np.savez_compressed(config.EMBED_NPZ, ids=ids, vectors=vectors, model=np.array(config.EMBED_MODEL))
    size = config.EMBED_NPZ.stat().st_size / 1e6
    print(f"Yazıldı: {config.EMBED_NPZ} ({len(ids)} vektör x {vectors.shape[1]} boyut, {size:.1f} MB)")


if __name__ == "__main__":
    main()
