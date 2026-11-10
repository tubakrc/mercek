"""
Şirket kartı: üç şirketin temel metrikleri yan yana ve kural tabanlı risk işaretleri.

LLM kullanmaz; her şey financials.csv ve market.py'den KODLA hesaplanır.
Risk işaretleri aynı raporun 'guncel' ve 'onceki' sütunlarını karşılaştırır. Bu iki sütun TMS 29'a göre aynı
satın alma gücünde olduğu için enflasyon düzeltmesi gerekmez.
Bu işaretler tanımlayıcıdır; ucuz/pahalı yargısı veya yatırım tavsiyesi değildir.
"""
from __future__ import annotations

from mercek import config, financials

RAPOR_ETIKET = {"2024_12": "2024 yıllık", "2025_12": "2025 yıllık", "2026_6": "2026 ilk 6 ay"}

# (grup, metrik adı, oranlar_kolon anahtarı, birim)
METRIKLER = [
    ("Kârlılık", "Brüt kâr marjı", "brut_kar_marji_%", "%"),
    ("Kârlılık", "Esas faaliyet kâr marjı", "esas_faaliyet_kar_marji_%", "%"),
    ("Kârlılık", "Net kâr marjı", "net_kar_marji_%", "%"),
    ("Bilanço", "Cari oran", "cari_oran", "x"),
    ("Bilanço", "Toplam yükümlülük / özkaynak", "toplam_yukumluluk_ozkaynak", "x"),
    ("Bilanço", "Net finansal borç / özkaynak", "net_finansal_borc_ozkaynak", "x"),
    ("Bilanço", "Net finansal borç", "net_finansal_borc_milyar_TL", "milyar TL"),
]

# Eşikler tek yerde: arayüz bunları kullanıcıya da gösterir
ESIKLER = {
    "net_borc_ozkaynak_yuksek": 1.0,      # net finansal borç özkaynağı aşıyor
    "net_borc_ozkaynak_artis": 0.3,       # bir dönemde 0,3 puandan fazla artış
    "cari_oran_dusuk": 1.0,
    "parasal_etki_payi": 0.5,             # |parasal kazanç/kayıp| / |vergi öncesi kâr|
    "marj_degisim_puan": 3.0,
}

DIKKAT, IZLE, GUCLU = "Dikkat", "İzlenmeli", "Güçlü yön"
SEVIYE_SIRA = {DIKKAT: 0, IZLE: 1, GUCLU: 2}
SEVIYE_IKON = {DIKKAT: "🔴", IZLE: "🟡", GUCLU: "🟢"}

ETKI_ADI = {"esas_faaliyet_kari": "esas faaliyet kârı", "yatirim_finansman_ve_diger": "yatırım, finansman ve diğer",
            "parasal_kazanc_kayip": "TMS 29 parasal kazanç/kayıp", "vergi": "vergi"}


def _fmt(v: float | None, birim: str = "") -> str:
    if v is None:
        return "–"
    s = f"{v:,.2f}" if birim in ("x", "milyar TL") else f"{v:,.1f}"
    s = s.replace(",", "_").replace(".", ",").replace("_", ".")  # Türkçe sayı biçimi
    return {"%": f"%{s}", "x": f"{s}x", "milyar TL": f"{s} milyar TL"}.get(birim, s)


def karsilastirma(rapor: str) -> list[dict]:
    """Seçilen raporda üç şirketin metrikleri. Aynı tarihli raporlar aynı satın alma gücündedir, yan yana
    karşılaştırılabilir."""
    oranlar = {s: financials.oranlar_kolon(s, rapor, "guncel") for s in config.SIRKETLER}
    satirlar = []
    for grup, ad, anahtar, birim in METRIKLER:
        satir = {"Grup": grup, "Metrik": ad}
        for s, s_ad in config.SIRKETLER.items():
            satir[s_ad] = _fmt(oranlar[s].get(anahtar), birim)
        satirlar.append(satir)
    return satirlar


def piyasa_karsilastirma() -> tuple[list[dict], str]:
    """Güncel F/K, PD/DD, getiri ve piyasa değeri. (satırlar, kaynak notu)"""
    from mercek import market
    ozet = {s: market.fiyat_ozeti(s) for s in config.SIRKETLER}
    tanim = [("Piyasa değeri", "piyasa_degeri_milyar_TL", "milyar TL"), ("F/K (son 12 ay)", "F/K", ""),
             ("PD/DD", "PD/DD", "x"), ("12 aylık getiri (nominal)", "getiri_12ay_%", "%")]
    satirlar = []
    for ad, anahtar, birim in tanim:
        satir = {"Metrik": ad}
        for s, s_ad in config.SIRKETLER.items():
            satir[s_ad] = _fmt(ozet[s].get(anahtar), birim).rstrip("x")
        satirlar.append(satir)
    tarihler = sorted({o.get("kapanis_tarihi") for o in ozet.values() if o.get("kapanis_tarihi")})
    durumlar = sorted({o.get("veri_durumu") for o in ozet.values() if o.get("veri_durumu")})
    kaynak = "Yahoo Finance" + (f", kapanış {tarihler[-1]}" if tarihler else "") + \
             (f" ({', '.join(durumlar)})" if durumlar else "")
    return satirlar, kaynak


def risk_isaretleri(sirket: str, rapor: str) -> list[dict]:
    """Kural tabanlı işaretler: [{seviye, baslik, aciklama}], önem sırasına göre."""
    g = financials.oranlar_kolon(sirket, rapor, "guncel")
    o = financials.oranlar_kolon(sirket, rapor, "onceki")
    get = lambda k, c="guncel": financials.get(sirket, rapor, k, c)
    out: list[dict] = []

    def ekle(seviye, baslik, aciklama):
        out.append({"seviye": seviye, "baslik": baslik, "aciklama": aciklama})

    # 1. Zarar
    dk = get("donem_kari")
    if dk is not None and dk < 0:
        ekle(DIKKAT, "Dönem zararı", f"Dönem net sonucu {_fmt(dk / 1e6, 'milyar TL')}.")

    # 2. Borçluluk
    nb, nb_o = g.get("net_finansal_borc_ozkaynak"), o.get("net_finansal_borc_ozkaynak")
    if nb is not None:
        if nb < 0:
            ekle(GUCLU, "Net nakit pozisyonu", "Nakit ve benzerleri finansal borçlardan fazla.")
        elif nb > ESIKLER["net_borc_ozkaynak_yuksek"]:
            ekle(DIKKAT, "Net borç özkaynağı aşıyor", f"Net finansal borç / özkaynak {_fmt(nb, 'x')}.")
        if nb_o is not None and nb - nb_o > ESIKLER["net_borc_ozkaynak_artis"]:
            ekle(IZLE, "Borçluluk hızla arttı", f"Net finansal borç / özkaynak {_fmt(nb_o, 'x')} → {_fmt(nb, 'x')}.")

    # 3. Likidite
    co = g.get("cari_oran")
    if co is not None and co < ESIKLER["cari_oran_dusuk"]:
        ekle(IZLE, "Cari oran 1’in altında",
             f"Kısa vadeli yükümlülükler dönen varlıklardan fazla (cari oran {_fmt(co, 'x')}).")

    # 4. Faaliyet kârı ile net kâr ayrışıyor mu? (net kâr köprüsü)
    kopru = financials.net_kar_koprusu(sirket, rapor)
    if kopru:
        d_efk = kopru["esas_faaliyet_kari_degisimi_milyar_TL"]
        d_dk = kopru["donem_kari_degisimi_milyar_TL"]
        neg = kopru.get("en_buyuk_olumsuz_etki")
        if d_efk is not None and d_dk is not None and d_efk > 0 > d_dk and neg:
            etki = kopru[f"{neg}_degisimi_milyar_TL"]
            ekle(IZLE, "Faaliyet kârı arttı, net kâr düştü",
                 f"En büyük olumsuz etki: {ETKI_ADI.get(neg, neg)} ({_fmt(etki, 'milyar TL')}).")

    # 5. TMS 29 parasal etkinin ağırlığı
    par, vok = get("parasal_kazanc_kayip"), get("vergi_oncesi_kar")
    if par is not None and vok not in (None, 0) and abs(par) / abs(vok) > ESIKLER["parasal_etki_payi"]:
        yon = "kayıp" if par < 0 else "kazanç"
        ekle(IZLE, "Enflasyon muhasebesi kârı belirgin etkiliyor",
             f"Parasal {yon} {_fmt(abs(par) / 1e6, 'milyar TL')}; vergi öncesi kâra oranı "
             f"%{abs(par) / abs(vok) * 100:.0f}.")

    # 6. Kârın nakde dönüşü
    inak = get("isletme_nakit_akisi")
    if inak is not None and dk is not None:
        if inak < 0:
            ekle(DIKKAT, "İşletme nakit akışı negatif", f"İşletme faaliyetlerinden nakit akışı {_fmt(inak / 1e6, 'milyar TL')}.")
        elif dk > 0 and inak < dk:
            ekle(IZLE, "Kâr nakde tam dönmüyor",
                 f"İşletme nakit akışı ({_fmt(inak / 1e6, 'milyar TL')}) net kârın ({_fmt(dk / 1e6, 'milyar TL')}) altında.")

    # 7. Net kâr marjındaki değişim
    m, m_o = g.get("net_kar_marji_%"), o.get("net_kar_marji_%")
    if m is not None and m_o is not None:
        fark = m - m_o
        if fark < -ESIKLER["marj_degisim_puan"]:
            ekle(IZLE, "Net kâr marjı daraldı", f"{_fmt(m_o, '%')} → {_fmt(m, '%')}.")
        elif fark > ESIKLER["marj_degisim_puan"]:
            ekle(GUCLU, "Net kâr marjı genişledi", f"{_fmt(m_o, '%')} → {_fmt(m, '%')}.")

    return sorted(out, key=lambda x: SEVIYE_SIRA[x["seviye"]])


ESIK_ACIKLAMA = [
    f"Net finansal borç / özkaynak {_fmt(ESIKLER['net_borc_ozkaynak_yuksek'], 'x')} üstü → Dikkat; "
    f"bir dönemde {_fmt(ESIKLER['net_borc_ozkaynak_artis'], 'x').rstrip('x')} puandan fazla artış → İzlenmeli; "
    "sıfırın altı (net nakit) → Güçlü yön",
    f"Cari oran {_fmt(ESIKLER['cari_oran_dusuk'], 'x')} altı → İzlenmeli",
    "Esas faaliyet kârı artarken dönem kârı düşüyorsa → İzlenmeli (net kâr köprüsünden)",
    f"Parasal kazanç/kayıp, vergi öncesi kârın %{ESIKLER['parasal_etki_payi'] * 100:.0f}’inden büyükse → İzlenmeli",
    "İşletme nakit akışı negatif → Dikkat; net kârın altında → İzlenmeli",
    f"Net kâr marjı {ESIKLER['marj_degisim_puan']:.0f} puandan fazla daraldıysa → İzlenmeli, genişlediyse → Güçlü yön",
    "Dönem zararı → Dikkat",
]
