"""
Mercek MCP sunucusu

Mercek'in veri araçlarını Model Context Protocol üzerinden sunar. Claude Desktop, Cursor veya başka bir MCP
istemcisi bu sunucuya bağlanarak BİM, Tüpraş ve Aselsan'ın finansal raporlarını sorgulayabilir.

Sunulanlar
  Araçlar (tools)
    sirket_listesi     KAP 'members' karşılığı
    bildirim_listesi   KAP 'disclosures' karşılığı (finansal raporlar)
    bildirim_detay     KAP 'disclosureDetail' karşılığı (raporun dipnot içindekiler listesi)
    finansal_ozet      Ana kalemler + kodla hesaplanmış oranlar (Streamlit agent'ı ile aynı fonksiyon)
    finansal_trend     Dönemler arası seyir, TMS 29'a göre aynı satın alma gücünde
    dipnot_ara         Dipnotlarda hybrid arama (OpenAI anahtarı yoksa BM25)
    fiyat_verisi       Hisse fiyatı, getiriler, piyasa değeri, F/K, PD/DD
  Kaynak (resource)
    mercek://metodoloji   TMS 29 yaklaşımı, enflasyon katsayıları, veri kapsamı
  Prompt
    sirket_analizi        Bir şirket/rapor için yapılandırılmış analiz talimatı

Çalıştırma (stdio):
  uv run python -m mercek.mcp_server
Test istemcisi:
  uv run python scripts/09_mcp_test.py
İnceleme arayüzü (Node.js gerekir):
  npx @modelcontextprotocol/inspector uv run python -m mercek.mcp_server

NOT: stdio taşımasında stdout protokole aittir; bu modülde print() kullanılmamalıdır.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # "python mercek/mcp_server.py" ile de çalışsın

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from mercek import config, financials, market  # noqa: E402
from mercek.kap import get_adapter  # noqa: E402
from mercek.tools import dipnot_ara_text  # noqa: E402

Sirket = Literal["bim", "tupras", "aselsan"]
Rapor = Literal["2024_12", "2025_12", "2026_6"]

INSTRUCTIONS = """Mercek: BİM, Tüpraş ve Aselsan'ın konsolide finansal raporları (2024 yıllık, 2025 yıllık, 2026 ilk 6 ay).
- Rakam ve oranları yalnızca finansal_ozet / finansal_trend araçlarından al; tahmin etme.
- Farklı yılları karşılaştırırken finansal_trend kullan (TMS 29: aynı satın alma gücü).
- "Neden/nasıl" sorularında dipnot_ara ile kanıt bul ve atıf ver (Not N, sayfa).
- Dipnot tutarları bin TL'dir. Yatırım tavsiyesi verme."""

server = _Server(name="mercek", instructions=INSTRUCTIONS)


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


def _safe(fn, *args):
    try:
        return _json(fn(*args))
    except NotImplementedError as e:
        return _json({"hata": str(e)})


# --- KAP benzeri servisler -------------------------------------------------------------------
@server.tool()
def sirket_listesi() -> str:
    """Kapsamdaki şirketleri listeler (KAP 'members' servisi karşılığı): unvan, borsa kodu, sektör."""
    return _safe(get_adapter().members)


@server.tool()
def bildirim_listesi(sirket: Optional[Sirket] = None) -> str:
    """Mevcut finansal rapor bildirimlerini listeler (KAP 'disclosures' karşılığı). bildirim_id döner,
    örn. 'tupras-2025_12'. sirket verilmezse tüm şirketler."""
    return _safe(get_adapter().disclosures, sirket)


@server.tool()
def bildirim_detay(bildirim_id: str) -> str:
    """Bir finansal raporun dipnot içindekiler listesini döndürür (KAP 'disclosureDetail' karşılığı):
    not numarası, başlık, PDF sayfa aralığı. bildirim_id örneği: 'bim-2026_6'."""
    return _safe(get_adapter().disclosure_detail, bildirim_id)


# --- Mercek analiz araçları (Streamlit agent'ı ile aynı fonksiyonlar) --------------------------------
@server.tool()
def finansal_ozet(sirket: Sirket, rapor: Rapor) -> str:
    """Bir raporun ana kalemleri (milyar TL), kodla hesaplanmış oranları (brüt/esas faaliyet/net kâr marjı,
    cari oran, finansal borç, net borç, kira dahil/hariç borç, parasal kazanç/kayıp etkisi, vergi etkisi) ve
    aynı rapor içindeki reel değişimler. rapor: 2024_12, 2025_12 veya 2026_6 (2026 ilk 6 ay; 'önceki' sütunu
    geçen yılın aynı 6 aylık dönemidir)."""
    return _json(financials.ozet(sirket, rapor))


@server.tool()
def finansal_trend(sirket: Sirket, kalem: str) -> str:
    """Bir kalemin 2024 sonu, 2025 sonu ve Haziran 2026 değerleri, hepsi Haziran 2026 satın alma gücünde
    (TMS 29), dönemler arası reel değişimlerle. kalem örnekleri: hasilat, brut_kar, donem_kari, ozkaynaklar,
    finansal_borc, net_finansal_borc, toplam_yukumlulukler; oran serileri: net_finansal_borc_ozkaynak, cari_oran,
    brut_kar_marji_%, net_kar_marji_%."""
    return _json(financials.trend(sirket, kalem))


@server.tool()
def dipnot_ara(soru: str, sirket: Optional[Sirket] = None, rapor: Optional[Rapor] = None, k: int = 5) -> str:
    """Dipnotlarda (açıklayıcı notlar) arama yapar; her sonuç şirket, rapor, not numarası ve sayfa atfıyla
    gelir. Muhasebe politikaları, borç vadesi/döviz yapısı, riskler, taahhütler, koşullu yükümlülükler için."""
    return dipnot_ara_text(soru, sirket, rapor, k)


@server.tool()
def fiyat_verisi(sirket: Sirket) -> str:
    """Hisse fiyatı ve piyasa verisi (Yahoo Finance): son kapanış ve tarihi, 1/3/12 aylık getiri, 52 haftalık aralık,
    piyasa değeri, F/K (son 12 ay ana ortaklık kârı, Haziran 2026 satın alma gücü) ve PD/DD. Fiyatlar nominal TL'dir."""
    return _json(market.fiyat_ozeti(sirket))


# --- Kaynak ve prompt ----------------------------------------------------------------------
@server.resource("mercek://metodoloji")
def metodoloji() -> str:
    """Veri kapsamı ve TMS 29 (enflasyon muhasebesi) yaklaşımı."""
    try:
        katsayilar = {k: round(v, 4) for k, v in financials.enflasyon_katsayilari().items()}
    except FileNotFoundError:
        katsayilar = {}
    return _json({
        "kapsam": {"sirketler": list(config.SIRKETLER.values()), "raporlar": list(financials.RAPORLAR),
                   "tur": "konsolide finansal raporlar"},
        "veri_kaynagi": get_adapter().kaynak,
        "tms29": ("Her rapor kendi tarihindeki satın alma gücüyle hazırlanır. Aynı raporun güncel/önceki "
                  "sütunları karşılaştırılabilir (reel değişim). Farklı raporlar, raporların karşılaştırmalı "
                  "sütunlarından türetilen katsayılarla en güncel satın alma gücüne taşınır."),
        "enflasyon_katsayilari": katsayilar,
        "dogrulama": ("Ana tablolar muhasebe kimlikleriyle (toplam varlık = toplam kaynak vb.) ve katsayıların "
                      "üç şirkette aynı çıkmasıyla doğrulanmıştır."),
        "birimler": "finansal_ozet/finansal_trend: milyar TL; dipnot tabloları: bin TL",
    })


@server.prompt()
def sirket_analizi(sirket: str, rapor: str = "2026_6") -> str:
    """Bir şirketin bir raporu için yapılandırılmış finansal analiz talimatı."""
    return (
        f"{sirket} şirketinin {rapor} raporunu analiz et.\n"
        "1. finansal_ozet ile kârlılık (brüt, esas faaliyet, net marj), likidite (cari oran) ve borçluluğu çıkar.\n"
        "2. Parasal kazanç/kayıp (TMS 29) ve vergi etkisinin net kâra katkısını parasal_etki_haric_vergi_oncesi_kar "
        "ile açıkla.\n"
        "3. finansal_trend ile özkaynak ve hasılatın dönemler arası seyrini ver.\n"
        "4. dipnot_ara ile borçların vade yapısını ve önemli riskleri dipnot atfıyla özetle.\n"
        "Rakamları yalnızca araçlardan al, her iddiaya kaynak göster, yatırım tavsiyesi verme."
    )


def main() -> None:
    server.run()  # varsayılan taşıma: stdio


if __name__ == "__main__":
    main()
