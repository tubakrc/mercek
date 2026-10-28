"""
KAP Veri Yayın Servisi arayüzü (adaptör kalıbı).

KAP REST API dokümanındaki servis adları birebir korunur:
  members            Şirket Listesi Servisi
  memberDetail       Şirket Detay Servisi
  disclosures        Bildirim Listesi Servisi
  disclosureDetail   Bildirim Detay Servisi
  (diğerleri: downloadAttachment, lastDisclosureIndex, memberSecurities, funds, fundDetail,
   blockedDisclosures, caEventStatus — bu projede kullanılmıyor)

İki uygulama:
  LocalKapAdapter  : Bu projede elle indirilen finansal raporlardan beslenir. Demo bununla çalışır.
  RemoteKapAdapter : Gerçek KAP API için taslak. Dokümana göre erişim; Borsa İstanbul ile veri dağıtım
                     sözleşmesi, MKK'nın IP bazlı yetkilendirmesi ve e-postayla iletilen API KEY gerektirir.
                     Uç nokta adresleri, parametreler ve kimlik doğrulama biçimi abonelikte iletildiği için
                     burada UYDURULMAMIŞTIR; metotlar NotImplementedError verir.

Ajan ve MCP sunucusu yalnızca KapAdapter arayüzünü bilir. Gerçek erişim sağlandığında tek değişiklik
get_adapter() içindeki seçimdir (KAP_ADAPTER=remote).
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from functools import lru_cache

from mercek import config

# Şirket kimlik bilgileri (borsa kodları kamuya açık ve yaygın biçimde bilinir)
SIRKET_BILGI = {
    "bim": {"unvan": "BİM Birleşik Mağazalar A.Ş.", "borsa_kodu": "BIMAS", "sektor": "Perakende"},
    "tupras": {"unvan": "Türkiye Petrol Rafinerileri A.Ş.", "borsa_kodu": "TUPRS", "sektor": "Enerji / Rafineri"},
    "aselsan": {"unvan": "Aselsan Elektronik Sanayi ve Ticaret A.Ş.", "borsa_kodu": "ASELS",
                "sektor": "Savunma Sanayii"},
}
RAPOR_ACIKLAMA = {
    "2024_12": "2024 yıllık (1 Ocak - 31 Aralık 2024) konsolide finansal rapor",
    "2025_12": "2025 yıllık (1 Ocak - 31 Aralık 2025) konsolide finansal rapor",
    "2026_6": "2026 ara dönem (1 Ocak - 30 Haziran 2026) konsolide finansal rapor",
}


class KapAdapter(ABC):
    """KAP servislerinin bu projede kullanılan alt kümesi."""

    kaynak: str = ""

    @abstractmethod
    def members(self) -> list[dict]: ...

    @abstractmethod
    def member_detail(self, sirket: str) -> dict: ...

    @abstractmethod
    def disclosures(self, sirket: str | None = None) -> list[dict]: ...

    @abstractmethod
    def disclosure_detail(self, bildirim_id: str) -> dict: ...


class LocalKapAdapter(KapAdapter):
    kaynak = "lokal (elle indirilmiş finansal raporlar)"

    @staticmethod
    @lru_cache(maxsize=1)
    def _notes() -> dict:
        """(sirket, rapor) -> {not_no: (başlık, ilk sayfa, son sayfa, chunk sayısı)}"""
        out: dict = defaultdict(dict)
        if not config.CHUNKS_PATH.exists():
            return {}
        with open(config.CHUNKS_PATH, encoding="utf-8") as fh:
            for line in fh:
                c = json.loads(line)
                key, n = (c["sirket"], c["rapor"]), c["not_no"]
                prev = out[key].get(n)
                if prev is None:
                    out[key][n] = [c["not_baslik"], c["sayfa_bas"], c["sayfa_bit"], 1]
                else:
                    prev[1], prev[2], prev[3] = min(prev[1], c["sayfa_bas"]), max(prev[2], c["sayfa_bit"]), prev[3] + 1
        return dict(out)

    def members(self) -> list[dict]:
        return [{"sirket": k, **v} for k, v in SIRKET_BILGI.items()]

    def member_detail(self, sirket: str) -> dict:
        if sirket not in SIRKET_BILGI:
            return {"hata": f"Bilinmeyen şirket '{sirket}'. Geçerli: {list(SIRKET_BILGI)}"}
        raporlar = [d["bildirim_id"] for d in self.disclosures(sirket)]
        return {"sirket": sirket, **SIRKET_BILGI[sirket], "raporlar": raporlar}

    def disclosures(self, sirket: str | None = None) -> list[dict]:
        notes = self._notes()
        out = []
        for s in SIRKET_BILGI:
            if sirket and s != sirket:
                continue
            for r, aciklama in RAPOR_ACIKLAMA.items():
                if (s, r) in notes:
                    out.append({"bildirim_id": f"{s}-{r}", "sirket": s, "borsa_kodu": SIRKET_BILGI[s]["borsa_kodu"],
                                "rapor": r, "konu": "Finansal Rapor", "aciklama": aciklama,
                                "konsolide": True, "dipnot_sayisi": len(notes[(s, r)])})
        return out

    def disclosure_detail(self, bildirim_id: str) -> dict:
        try:
            sirket, rapor = bildirim_id.split("-", 1)
        except ValueError:
            return {"hata": f"Geçersiz bildirim_id '{bildirim_id}'. Biçim: <sirket>-<rapor>, örn. tupras-2025_12"}
        notes = self._notes().get((sirket, rapor))
        if not notes:
            return {"hata": f"'{bildirim_id}' bulunamadı. bildirim_listesi ile mevcut bildirimleri gör."}
        return {
            "bildirim_id": bildirim_id, "sirket": sirket, "rapor": rapor,
            "aciklama": RAPOR_ACIKLAMA.get(rapor, rapor),
            "dipnotlar": [{"not_no": n, "baslik": b, "sayfalar": f"{p1}-{p2}" if p1 != p2 else str(p1), "parca": k}
                          for n, (b, p1, p2, k) in sorted(notes.items())],
            "not": "Sayfa numaraları PDF sayfa numaralarıdır. Ana tablolar için finansal_ozet aracını kullanın.",
        }


class RemoteKapAdapter(KapAdapter):
    """Gerçek KAP Veri Yayın Servisi için taslak (TEST EDİLMEDİ).

    Erişim için: Borsa İstanbul ile veri dağıtım sözleşmesi -> MKK IP yetkilendirmesi -> API KEY (e-posta).
    Uç nokta adresi, parametre ve kimlik doğrulama biçimi abonelikte iletilir; tahmin edilip yazılmamıştır.
    Erişim sağlandığında her metot ilgili servise (members, memberDetail, disclosures, disclosureDetail)
    istek atıp çıktıyı LocalKapAdapter ile aynı sözlük biçimine dönüştürmelidir.
    """

    kaynak = "KAP Veri Yayın Servisi (REST API)"

    def __init__(self) -> None:
        self.api_key = os.getenv("KAP_API_KEY")
        self.base_url = os.getenv("KAP_BASE_URL")

    def _not_ready(self, servis: str):
        raise NotImplementedError(
            f"KAP '{servis}' servisi için gerçek API erişimi yapılandırılmadı. Erişim Borsa İstanbul ile veri dağıtım "
            "sözleşmesi ve MKK yetkilendirmesi gerektirir (bkz. kapdestek@mkk.com.tr). KAP_ADAPTER=local kullanın.")

    def members(self):
        self._not_ready("members")

    def member_detail(self, sirket):
        self._not_ready("memberDetail")

    def disclosures(self, sirket=None):
        self._not_ready("disclosures")

    def disclosure_detail(self, bildirim_id):
        self._not_ready("disclosureDetail")


@lru_cache(maxsize=1)
def get_adapter() -> KapAdapter:
    return RemoteKapAdapter() if os.getenv("KAP_ADAPTER", "local") == "remote" else LocalKapAdapter()
