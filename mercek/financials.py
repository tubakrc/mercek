"""
Yapısal finansal veri katmanı: financials.csv'den kalem okur, oranları KODLA hesaplar.

LLM rakam tahmin etmez; agent bu fonksiyonları araç olarak çağırır.

TMS 29 notu:
  Her rapor kendi tarihindeki satın alma gücüyle hazırlanır. Bu yüzden
  - Aynı raporun 'guncel' ve 'onceki' sütunları birbiriyle karşılaştırılabilir (reel değişim).
  - Farklı raporların rakamları doğrudan karşılaştırılamaz. trend() bunları, verinin kendisinden
    türetilen enflasyon katsayılarıyla en son raporun satın alma gücüne taşır.
"""
from __future__ import annotations

import csv
import statistics
from functools import lru_cache

from mercek import config

RAPORLAR = ["2024_12", "2025_12", "2026_6"]

KALEM_ADLARI = {
    "hasilat": "Hasılat", "satislarin_maliyeti": "Satışların maliyeti", "brut_kar": "Brüt kâr",
    "esas_faaliyet_kari": "Esas faaliyet kârı", "finansman_gelirleri": "Finansman gelirleri",
    "finansman_giderleri": "Finansman giderleri", "parasal_kazanc_kayip": "Parasal kazanç/kayıp (TMS 29)",
    "vergi_oncesi_kar": "Vergi öncesi kâr", "donem_kari": "Dönem kârı",
    "ana_ortaklik_payi": "Ana ortaklık payı (net kâr)", "kgop_payi": "Kontrol gücü olmayan paylar",
    "toplam_varliklar": "Toplam varlıklar", "donen_varliklar": "Dönen varlıklar",
    "duran_varliklar": "Duran varlıklar", "nakit_ve_benzerleri": "Nakit ve nakit benzerleri",
    "ticari_alacaklar": "Ticari alacaklar", "stoklar": "Stoklar",
    "kisa_vadeli_yukumlulukler": "Kısa vadeli yükümlülükler",
    "uzun_vadeli_yukumlulukler": "Uzun vadeli yükümlülükler", "ozkaynaklar": "Özkaynaklar",
    "kisa_vadeli_borclanmalar": "Kısa vadeli borçlanmalar",
    "uzun_vadeli_borclanmalarin_kisa_kismi": "Uzun vadeli borçlanmaların kısa vadeli kısmı",
    "uzun_vadeli_borclanmalar": "Uzun vadeli borçlanmalar", "banka_kredileri": "Banka kredileri",
    "kiralama_borclari_kv": "Kiralama borçları (KV)", "kiralama_borclari_uv": "Kiralama borçları (UV)",
    "isletme_nakit_akisi": "İşletme faaliyetlerinden nakit akışı",
    "yatirim_nakit_akisi": "Yatırım faaliyetlerinden nakit akışı",
    "finansman_nakit_akisi": "Finansman faaliyetlerinden nakit akışı",
}


@lru_cache(maxsize=1)
def _facts() -> tuple[dict, dict]:
    """(sirket, rapor, kalem, kolon) -> değer (bin TL), ve aynı anahtar -> (başlangıç, bitiş)."""
    vals, periods = {}, {}
    with open(config.FINANCIALS_PATH, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            key = (r["sirket"], r["rapor"], r["kalem"], r["kolon"])
            vals.setdefault(key, float(r["deger"]))  # aynı kalem iki tabloda varsa ilki
            periods.setdefault(key, (r["donem_baslangic"], r["donem_bitis"]))
    return vals, periods


def get(sirket: str, rapor: str, kalem: str, kolon: str = "guncel") -> float | None:
    return _facts()[0].get((sirket, rapor, kalem, kolon))


def _milyar(v: float | None) -> float | None:
    return None if v is None else round(v / 1e6, 2)  # bin TL -> milyar TL


def _div(a, b, pct=True):
    if a is None or b in (None, 0):
        return None
    return round(100 * a / b, 1) if pct else round(a / b, 2)


def _sum(*xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) if xs else None


def oranlar_kolon(sirket: str, rapor: str, kolon: str) -> dict:
    g = lambda k: get(sirket, rapor, k, kolon)
    fin_borc = _sum(g("kisa_vadeli_borclanmalar"), g("uzun_vadeli_borclanmalarin_kisa_kismi"),
                    g("uzun_vadeli_borclanmalar"))
    kira = _sum(g("kiralama_borclari_kv"), g("kiralama_borclari_uv"))
    toplam_yuk = _sum(g("kisa_vadeli_yukumlulukler"), g("uzun_vadeli_yukumlulukler"))
    net_borc = None if fin_borc is None else fin_borc - (g("nakit_ve_benzerleri") or 0)
    out = {
        "brut_kar_marji_%": _div(g("brut_kar"), g("hasilat")),
        "esas_faaliyet_kar_marji_%": _div(g("esas_faaliyet_kari"), g("hasilat")),
        "net_kar_marji_%": _div(g("donem_kari"), g("hasilat")),
        "parasal_kazanc_kayip_vergi_oncesi_kara_orani_%": _div(g("parasal_kazanc_kayip"), g("vergi_oncesi_kar")),
        # TMS 29 etkisini ayrıştırmak için hazır hesaplar (LLM'in çıkarım yapmasına gerek kalmasın)
        "parasal_kazanc_kayip_milyar_TL": _milyar(g("parasal_kazanc_kayip")),
        "parasal_etki_haric_vergi_oncesi_kar_milyar_TL": _milyar(
            None if g("vergi_oncesi_kar") is None or g("parasal_kazanc_kayip") is None
            else g("vergi_oncesi_kar") - g("parasal_kazanc_kayip")),
        # dönem kârı - vergi öncesi kâr: negatifse vergi gideri, pozitifse vergi geliri (örn. ertelenmiş vergi)
        "vergi_etkisi_milyar_TL": _milyar(
            None if g("donem_kari") is None or g("vergi_oncesi_kar") is None
            else g("donem_kari") - g("vergi_oncesi_kar")),
        "cari_oran": _div(g("donen_varliklar"), g("kisa_vadeli_yukumlulukler"), pct=False),
        "toplam_yukumluluk_ozkaynak": _div(toplam_yuk, g("ozkaynaklar"), pct=False),
        "finansal_borc_milyar_TL": _milyar(fin_borc),
        "net_finansal_borc_milyar_TL": _milyar(net_borc),
        "net_finansal_borc_ozkaynak": _div(net_borc, g("ozkaynaklar"), pct=False),
    }
    if kira is not None:
        out["kiralama_borclari_milyar_TL"] = _milyar(kira)
        out["kira_haric_finansal_borc_milyar_TL"] = _milyar(None if fin_borc is None else fin_borc - kira)
    return out


def net_kar_koprusu(sirket: str, rapor: str) -> dict | None:
    """Dönem kârındaki değişimi (güncel - önceki, aynı rapor = aynı satın alma gücü) bileşenlerine ayırır.
    esas faaliyet + yatırım/finansman/diğer + parasal kazanç/kayıp + vergi = dönem kârı değişimi (tam olarak)."""
    g = lambda k, c: get(sirket, rapor, k, c)
    keys = ("esas_faaliyet_kari", "parasal_kazanc_kayip", "vergi_oncesi_kar", "donem_kari")
    if any(g(k, c) is None for k in keys for c in ("guncel", "onceki")):
        return None
    d = lambda k: g(k, "guncel") - g(k, "onceki")
    vergi = lambda c: g("donem_kari", c) - g("vergi_oncesi_kar", c)
    d_efk, d_par, d_dk = d("esas_faaliyet_kari"), d("parasal_kazanc_kayip"), d("donem_kari")
    d_vergi = vergi("guncel") - vergi("onceki")
    items = {"esas_faaliyet_kari": d_efk, "yatirim_finansman_ve_diger": d_dk - d_efk - d_par - d_vergi,
             "parasal_kazanc_kayip": d_par, "vergi": d_vergi}
    out = {f"{k}_degisimi_milyar_TL": _milyar(v) for k, v in items.items()}
    out["donem_kari_degisimi_milyar_TL"] = _milyar(d_dk)
    neg = min(items, key=items.get)
    pos = max(items, key=items.get)
    out["en_buyuk_olumsuz_etki"] = neg if items[neg] < 0 else None
    out["en_buyuk_olumlu_etki"] = pos if items[pos] > 0 else None
    out["aciklama"] = ("Bileşenlerin toplamı dönem kârı değişimine eşittir. Faaliyet kârı ile net kâr farklı yönlere "
                       "gidiyorsa farkı en_buyuk_olumsuz_etki / en_buyuk_olumlu_etki açıklar.")
    return out


def ozet(sirket: str, rapor: str) -> dict:
    """Bir raporun ana kalemleri, oranları ve aynı rapor içindeki (reel) değişimler."""
    vals, periods = _facts()
    if not any(k[0] == sirket and k[1] == rapor for k in vals):
        return {"hata": f"{sirket} için {rapor} raporu yok. Mevcut raporlar: {RAPORLAR}"}

    def donem(kalem, kolon):
        p = periods.get((sirket, rapor, kalem, kolon))
        return None if p is None else (p[1] if p[0] == p[1] else f"{p[0]} / {p[1]}")

    kalemler = {}
    for kolon in ("guncel", "onceki"):
        kalemler[kolon] = {KALEM_ADLARI.get(k, k): _milyar(v) for (s, r, k, c), v in vals.items()
                           if s == sirket and r == rapor and c == kolon}
    degisim = {}
    for k in ("hasilat", "brut_kar", "esas_faaliyet_kari", "donem_kari", "toplam_varliklar",
              "ozkaynaklar", "isletme_nakit_akisi"):
        a, b = get(sirket, rapor, k, "guncel"), get(sirket, rapor, k, "onceki")
        if a is not None and b is not None:
            degisim[KALEM_ADLARI[k] + " fark milyar TL"] = _milyar(a - b)
            if b > 0:
                degisim[KALEM_ADLARI[k] + " reel değişim %"] = round(100 * (a / b - 1), 1)
    return {
        "sirket": config.SIRKETLER.get(sirket, sirket), "rapor": rapor, "birim": "milyar TL",
        "donemler": {
            "guncel": {"gelir_tablosu": donem("hasilat", "guncel"), "bilanco": donem("toplam_varliklar", "guncel")},
            "onceki": {"gelir_tablosu": donem("hasilat", "onceki"), "bilanco": donem("toplam_varliklar", "onceki")},
        },
        "kalemler": kalemler,
        "oranlar": {kol: oranlar_kolon(sirket, rapor, kol) for kol in ("guncel", "onceki")},
        "degisim": degisim,
        "net_kar_koprusu": net_kar_koprusu(sirket, rapor),
        "not": ("Tutarlar TMS 29'a göre bu raporun tarihindeki satın alma gücüyle ifade edilmiştir; "
                "guncel/onceki karşılaştırması reel değişimdir. Ara dönem (2026_6) gelir tablosunda 'onceki' "
                "geçen yılın aynı 6 aylık dönemidir, bilançoda ise önceki yıl sonudur. "
                "UYARI: Farklı raporların finansal_ozet tutarlarını birbiriyle karşılaştırma (farklı satın "
                "alma gücündedir); yıllar arası seyir için finansal_trend kullan."),
        "kaynak": f"financials.csv ({config.SIRKETLER.get(sirket, sirket)} {rapor.replace('_', '/')} konsolide finansal tablolar)",
    }


@lru_cache(maxsize=1)
def enflasyon_katsayilari() -> dict[str, float]:
    """Ardışık raporlar arası TMS 29 katsayısı, verinin kendisinden (3 şirketin medyanı).
    rapor -> o raporun 'guncel' bilanço değerini bir sonraki raporun satın alma gücüne taşıyan katsayı."""
    out = {}
    for old, new in zip(RAPORLAR, RAPORLAR[1:]):
        rs = []
        for s in config.SIRKETLER:
            a = get(s, new, "toplam_varliklar", "onceki")
            b = get(s, old, "toplam_varliklar", "guncel")
            if a and b:
                rs.append(a / b)
        if rs:
            out[old] = statistics.median(rs)
    return out


# finansal_trend'in desteklediği hesaplanmış kalemler (rapor bazında bileşenlerden hesaplanır)
def _fin_borc(g):
    return _sum(g("kisa_vadeli_borclanmalar"), g("uzun_vadeli_borclanmalarin_kisa_kismi"), g("uzun_vadeli_borclanmalar"))


TUREV_TUTAR = {
    "finansal_borc": ("Finansal borç (KV + UV borçlanmalar, kira dahil)", _fin_borc),
    "net_finansal_borc": ("Net finansal borç (finansal borç - nakit)",
                          lambda g: None if _fin_borc(g) is None else _fin_borc(g) - (g("nakit_ve_benzerleri") or 0)),
    "kira_haric_finansal_borc": ("Kira hariç finansal borç",
                                 lambda g: None if _fin_borc(g) is None or _sum(g("kiralama_borclari_kv"), g("kiralama_borclari_uv")) is None
                                 else _fin_borc(g) - _sum(g("kiralama_borclari_kv"), g("kiralama_borclari_uv"))),
    "toplam_yukumlulukler": ("Toplam yükümlülükler",
                             lambda g: _sum(g("kisa_vadeli_yukumlulukler"), g("uzun_vadeli_yukumlulukler"))),
}
# Oranlar aynı raporun pay ve paydasından hesaplandığı için enflasyon düzeltmesi gerektirmez
TUREV_ORAN = {
    "net_finansal_borc_ozkaynak": "Net finansal borç / özkaynak",
    "toplam_yukumluluk_ozkaynak": "Toplam yükümlülük / özkaynak",
    "cari_oran": "Cari oran",
    "brut_kar_marji_%": "Brüt kâr marjı (%)",
    "esas_faaliyet_kar_marji_%": "Esas faaliyet kâr marjı (%)",
    "net_kar_marji_%": "Net kâr marjı (%)",
}


def trend(sirket: str, kalem: str) -> dict:
    """Bir kalemin raporlar boyunca seyri. Tutarlar en son raporun satın alma gücüne taşınır; oranlar olduğu gibi
    verilir (pay ve payda aynı rapordan olduğu için enflasyon düzeltmesi gerekmez)."""
    gecerli = sorted(KALEM_ADLARI) + sorted(TUREV_TUTAR) + sorted(TUREV_ORAN)
    if kalem not in gecerli:
        return {"hata": f"Bilinmeyen kalem '{kalem}'. Geçerli kalemler: {gecerli}"}
    f = enflasyon_katsayilari()
    hedef = RAPORLAR[-1]
    oran = kalem in TUREV_ORAN
    ad = TUREV_ORAN.get(kalem) or (TUREV_TUTAR[kalem][0] if kalem in TUREV_TUTAR else KALEM_ADLARI[kalem])
    deg_key = "deger" if oran else f"{hedef}_satin_alma_gucuyle_milyar_TL"

    def value(rapor):
        g = lambda k: get(sirket, rapor, k, "guncel")
        if oran:
            return oranlar_kolon(sirket, rapor, "guncel").get(kalem)
        if kalem in TUREV_TUTAR:
            return TUREV_TUTAR[kalem][1](g)
        return g(kalem)

    seri = []
    for i, rapor in enumerate(RAPORLAR):
        v = value(rapor)
        if v is None:
            continue
        carpan = 1.0
        for r in RAPORLAR[i:-1]:
            carpan *= f.get(r, float("nan"))
        p = _facts()[1].get((sirket, rapor, "toplam_varliklar", "guncel"), ("", ""))
        if kalem in KALEM_ADLARI:
            p = _facts()[1][(sirket, rapor, kalem, "guncel")]
        seri.append({
            "rapor": rapor, "donem": p[1] if p[0] == p[1] else f"{p[0]} / {p[1]}",
            "donem_tipi": "6 aylık" if rapor.endswith("_6") else "12 aylık",
            deg_key: v if oran else _milyar(v * carpan),
        })
    # Gelir/nakit kalemlerinde 12 aylık -> 6 aylık karşılaştırması anlamsızdır; yalnızca aynı dönem tipleri
    akim = kalem in KALEM_ADLARI and get(sirket, "2025_12", kalem, "guncel") is not None and \
        _facts()[1][(sirket, "2025_12", kalem, "guncel")][0] != _facts()[1][(sirket, "2025_12", kalem, "guncel")][1]
    akim = akim or kalem in ("brut_kar_marji_%", "esas_faaliyet_kar_marji_%", "net_kar_marji_%")
    degisimler = []
    for a, b in zip(seri, seri[1:]):
        if akim and a["donem_tipi"] != b["donem_tipi"]:
            continue
        d = {"donem": f"{a['rapor']} -> {b['rapor']}"}
        if oran:
            d["fark_puan"] = round(b[deg_key] - a[deg_key], 2)
        else:
            d["fark_milyar_TL"] = round(b[deg_key] - a[deg_key], 2)
            if a[deg_key] and a[deg_key] > 0 and b[deg_key] is not None:
                d["reel_degisim_%"] = round(100 * (b[deg_key] / a[deg_key] - 1), 1)
        degisimler.append(d)
    if seri and not oran and len(seri) >= 2 and not akim:
        a, b = seri[0], seri[-1]
        tot = {"donem": f"{a['rapor']} -> {b['rapor']} (toplam)", "fark_milyar_TL": round(b[deg_key] - a[deg_key], 2)}
        if a[deg_key] and a[deg_key] > 0:
            tot["reel_degisim_%"] = round(100 * (b[deg_key] / a[deg_key] - 1), 1)
        degisimler.append(tot)
    return {
        "sirket": config.SIRKETLER.get(sirket, sirket), "kalem": ad, "seri": seri, "degisimler": degisimler,
        "enflasyon_katsayilari": {k: round(v, 4) for k, v in f.items()},
        "not": ("Oran serisi: enflasyon düzeltmesi gerekmez, değerler doğrudan karşılaştırılabilir." if oran else
                "Tüm tutarlar aynı satın alma gücündedir; seriyi ve değişimleri doğrudan kullan. Bu değerleri "
                "finansal_ozet'in rapor bazlı tutarlarıyla KARIŞTIRMA. Gelir tablosu kalemlerinde 6 aylık dönem "
                "12 aylıkla kıyaslanmaz; 6 aylık için finansal_ozet'teki geçen yılın aynı dönemini kullan."),
        "kaynak": "financials.csv; katsayılar raporların karşılaştırmalı sütunlarından türetildi",
    }
