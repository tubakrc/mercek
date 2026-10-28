"""
Hybrid retriever: vektör arama (Chroma + OpenAI embedding) + BM25, RRF ile birleştirme.

Neden hybrid?
  - Vektör arama anlamı yakalar: "borç vadesi" sorusu "kredilerin geri ödeme takvimi" metnini bulur.
  - BM25 kelimeyi yakalar: "TFRS 16", "Not 7", "Eurobond" gibi terim ve rakamlarda güçlüdür.
  - RRF (Reciprocal Rank Fusion) iki listeyi skor ölçeklerini dert etmeden sıra üzerinden birleştirir:
        skor(d) = Σ 1 / (RRF_K + sıra(d))
"""
from __future__ import annotations

import json
from typing import Callable

from rank_bm25 import BM25Okapi

from mercek import config
from mercek.textnorm import tokenize

RRF_K = 60
EmbedFn = Callable[[list[str]], list[list[float]]]


def openai_embed(texts: list[str], batch: int = 100) -> list[list[float]]:
    from openai import OpenAI

    client = OpenAI()
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        resp = client.embeddings.create(model=config.EMBED_MODEL, input=texts[i:i + batch])
        out.extend(d.embedding for d in resp.data)
    return out


def load_chunks(path=config.CHUNKS_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _where(sirket: str | None, rapor: str | None) -> dict | None:
    conds = [{"sirket": sirket}] if sirket else []
    conds += [{"rapor": rapor}] if rapor else []
    if not conds:
        return None
    return conds[0] if len(conds) == 1 else {"$and": conds}


META_KEYS = ["sirket", "rapor", "donem_tipi", "not_no", "not_baslik", "alt_baslik", "sayfa_bas", "sayfa_bit"]


def build_collection_from_npz(client, chunks: list[dict], npz_path=None):
    """embeddings.npz (scripts/10_export_index.py çıktısı) ile Chroma koleksiyonunu kurar."""
    import numpy as np

    npz_path = npz_path or config.EMBED_NPZ
    if not npz_path.exists():
        raise RuntimeError(f"Vektör indeksi bulunamadı ve {npz_path} yok. Önce scripts/05_build_index.py, "
                           "ardından scripts/10_export_index.py çalıştırın.")
    data = np.load(npz_path, allow_pickle=False)
    vec_by_id = dict(zip(data["ids"].tolist(), data["vectors"]))
    missing = [c["id"] for c in chunks if c["id"] not in vec_by_id]
    if missing:
        raise RuntimeError(f"embeddings.npz {len(missing)} chunk için vektör içermiyor (örn. {missing[0]}). "
                           "05_build_index.py ve 10_export_index.py'yi yeniden çalıştırın.")
    try:
        client.delete_collection(config.COLLECTION)
    except Exception:
        pass
    col = client.create_collection(config.COLLECTION, metadata={"hnsw:space": "cosine",
                                                               "embed_model": str(data["model"])})
    for i in range(0, len(chunks), 500):
        part = chunks[i:i + 500]
        col.add(ids=[c["id"] for c in part], documents=[c["text"] for c in part],
                embeddings=[vec_by_id[c["id"]].tolist() for c in part],
                metadatas=[{k: c[k] for k in META_KEYS} for c in part])
    return col


class Retriever:
    def __init__(self, embed_fn: EmbedFn = openai_embed, chroma_dir=config.CHROMA_DIR,
                 chunks_path=config.CHUNKS_PATH):
        import chromadb

        self.embed_fn = embed_fn
        self.chunks = load_chunks(chunks_path)
        self.by_id = {c["id"]: c for c in self.chunks}
        # BM25 her açılışta yeniden kurulur (1-2 bin chunk için milisaniyeler sürer)
        self.bm25 = BM25Okapi([tokenize(c["text"]) for c in self.chunks])
        client = chromadb.PersistentClient(path=str(chroma_dir))
        try:
            self.col = client.get_collection(config.COLLECTION)
            if self.col.count() != len(self.chunks):
                raise ValueError("indeks ile chunks.jsonl uyumsuz")
        except Exception:
            # İndeks yok veya eski: embeddings.npz'den kur (OpenAI'a istek atılmaz). Bulutta ilk açılışta çalışır.
            self.col = build_collection_from_npz(client, self.chunks)

    # --- tekil aramalar -------------------------------------------------------
    def vector_search(self, query: str, sirket=None, rapor=None, n=20) -> list[str]:
        emb = self.embed_fn([query])[0]
        res = self.col.query(query_embeddings=[emb], n_results=n, where=_where(sirket, rapor))
        return res["ids"][0]

    def bm25_search(self, query: str, sirket=None, rapor=None, n=20) -> list[str]:
        scores = self.bm25.get_scores(tokenize(query))
        idxs = [i for i, c in enumerate(self.chunks)
                if (not sirket or c["sirket"] == sirket) and (not rapor or c["rapor"] == rapor)]
        idxs.sort(key=lambda i: scores[i], reverse=True)
        return [self.chunks[i]["id"] for i in idxs[:n] if scores[i] > 0]

    # --- hybrid ----------------------------------------------------------------
    def search(self, query: str, sirket: str | None = None, rapor: str | None = None,
               k: int = 6, mode: str = "hybrid", max_per_note: int | None = 2) -> list[dict]:
        """mode: 'hybrid' | 'vector' | 'bm25'. Dönen her sonuç: chunk alanları + score + ranks.

        max_per_note: Aynı dipnottan en fazla kaç chunk dönsün. Not 2 (muhasebe politikaları)
        gibi uzun notlar her konuya değindiği için sonuçları doldurur; sınır diğer notlara yer açar.
        None verilirse sınır yok."""
        lists = {}
        if mode in ("hybrid", "vector"):
            lists["vector"] = self.vector_search(query, sirket, rapor, n=k * 4)
        if mode in ("hybrid", "bm25"):
            lists["bm25"] = self.bm25_search(query, sirket, rapor, n=k * 4)

        fused: dict[str, float] = {}
        ranks: dict[str, dict] = {}
        for name, ids in lists.items():
            for r, cid in enumerate(ids, start=1):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + r)
                ranks.setdefault(cid, {})[name] = r

        top, per_note = [], {}
        for cid in sorted(fused, key=fused.get, reverse=True):
            c = self.by_id[cid]
            note = (c["sirket"], c["rapor"], c["not_no"])
            if max_per_note and per_note.get(note, 0) >= max_per_note:
                continue
            per_note[note] = per_note.get(note, 0) + 1
            top.append(cid)
            if len(top) == k:
                break
        return [{**self.by_id[cid], "score": round(fused[cid], 5), "ranks": ranks[cid]} for cid in top]


def format_citation(hit: dict) -> str:
    """Örn: 'Tüpraş 2025/12, Not 7 - Borçlanmalar, s.34'"""
    sayfa = (f"s.{hit['sayfa_bas']}" if hit["sayfa_bas"] == hit["sayfa_bit"]
             else f"s.{hit['sayfa_bas']}-{hit['sayfa_bit']}")
    return (f"{config.SIRKETLER.get(hit['sirket'], hit['sirket'])} {hit['rapor'].replace('_', '/')}, "
            f"Not {hit['not_no']} - {hit['not_baslik']}, {sayfa}")
