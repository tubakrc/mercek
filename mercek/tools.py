"""Agent'ın kullandığı araçlar. Docstring'ler LLM'e araç açıklaması olarak gider."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Literal, Optional

from langchain_core.tools import tool

from mercek import financials, market
from mercek.retriever import Retriever, format_citation

Sirket = Literal["bim", "tupras", "aselsan"]
Rapor = Literal["2024_12", "2025_12", "2026_6"]
MAX_CHUNK_CHARS = 1800


@lru_cache(maxsize=1)
def _retriever() -> Retriever:
    return Retriever()


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


@tool
def finansal_ozet(sirket: Sirket, rapor: Rapor) -> str:
    """Bir şirketin bir raporundaki ana finansal kalemleri, HESAPLANMIŞ oranları (brüt/esas faaliyet/net
    kâr marjı, cari oran, borç/özkaynak, finansal borç, net borç, kira dahil/hariç borç) ve aynı rapor
    içindeki reel değişimleri (güncel vs önceki dönem) döndürür. Tutarlar milyar TL.
    Rakam, oran veya büyüme soruları için HER ZAMAN bu aracı kullan; rakamı asla tahmin etme.
    rapor: '2024_12' (2024 yıllık), '2025_12' (2025 yıllık), '2026_6' (2026 ilk 6 ay)."""
    return _json(financials.ozet(sirket, rapor))


@tool
def finansal_trend(sirket: Sirket, kalem: str) -> str:
    """Bir kalemin 2024 sonu, 2025 sonu ve Haziran 2026 değerlerini, hepsi aynı (en güncel) satın alma
    gücüne taşınmış olarak döndürür. Farklı yılları karşılaştıran trend soruları için kullan.
    Borçluluk trendi için hesaplanmış kalemler: finansal_borc, net_finansal_borc, kira_haric_finansal_borc,
    toplam_yukumlulukler. Oran serileri (düzeltme gerekmez): net_finansal_borc_ozkaynak, toplam_yukumluluk_ozkaynak,
    cari_oran, brut_kar_marji_%, esas_faaliyet_kar_marji_%, net_kar_marji_%.
    Diğer kalemler: hasilat, brut_kar, donem_kari, toplam_varliklar, ozkaynaklar, nakit_ve_benzerleri,
    kisa_vadeli_borclanmalar, uzun_vadeli_borclanmalar, kiralama_borclari_uv, isletme_nakit_akisi.
    Aynı şirketin farklı raporları için finansal_ozet'i art arda çağırıp tutarları karşılaştırma; bunun yerine bunu kullan."""
    return _json(financials.trend(sirket, kalem))


def dipnot_ara_text(soru: str, sirket: Optional[str] = None, rapor: Optional[str] = None, k: int = 5) -> str:
    """Dipnot araması (agent ve MCP sunucusu ortak kullanır). OpenAI anahtarı yoksa yalnızca BM25 ile arar."""
    mode = "hybrid" if os.getenv("OPENAI_API_KEY") else "bm25"
    hits = _retriever().search(soru, sirket=sirket, rapor=rapor, k=max(1, min(k, 8)), mode=mode)
    if not hits:
        return "Sonuç bulunamadı. Daha genel terimlerle veya filtresiz tekrar dene."
    parts = ["(Not: Dipnot tablolarındaki tutarlar aksi belirtilmedikçe BİN TL'dir.)"]
    if mode == "bm25":
        parts.append("(Arama modu: yalnızca anahtar kelime / BM25; OPENAI_API_KEY tanımlı değil.)")
    for i, h in enumerate(hits, 1):
        text = h["text"]
        if len(text) > MAX_CHUNK_CHARS:
            text = text[:MAX_CHUNK_CHARS] + " …"
        parts.append(f"[K{i}] {format_citation(h)}\n{text}")
    return "\n\n".join(parts)


@tool
def dipnot_ara(soru: str, sirket: Optional[Sirket] = None, rapor: Optional[Rapor] = None, k: int = 5) -> str:
    """Finansal tablo dipnotlarında (açıklayıcı notlar) hybrid arama yapar ve ilgili metin parçalarını
    kaynak etiketiyle döndürür. NEDEN/NASIL soruları için kullan: muhasebe politikaları, borçların vade ve
    döviz yapısı, riskler, taahhütler, koşullu yükümlülükler, ilişkili taraflar, hasılat kırılımı, olaylar.
    Belirli bir şirket veya rapor soruluyorsa filtreleri mutlaka ver. 'soru' kısa ve terim odaklı olsun."""
    return dipnot_ara_text(soru, sirket, rapor, k)


@tool
def fiyat_verisi(sirket: Sirket) -> str:
    """Hisse fiyatı ve piyasa verisi: son kapanış ve tarihi, 1/3/12 aylık getiri, 52 haftalık aralık, piyasa değeri,
    F/K (son 12 ay ana ortaklık kârıyla) ve PD/DD. Fiyat, piyasa değeri, değerleme oranı veya hisse performansı
    soruları için kullan. Fiyatlar nominal TL'dir ve veri tarihi çıktıda yazar. Bu oranlar tek başına ucuz/pahalı
    yargısı değildir."""
    return _json(market.fiyat_ozeti(sirket))


TOOLS = [finansal_ozet, finansal_trend, dipnot_ara, fiyat_verisi]
# Multi-agent modunda uzman agent'ların araç grupları
VERI_TOOLS = [finansal_ozet, finansal_trend, fiyat_verisi]
DIPNOT_TOOLS = [dipnot_ara]
