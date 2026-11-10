"""
Mercek arayüz ekleri: cevaptaki trend grafikleri ve Şirket kartı görünümü.

app.py'den çağrılır. Sayılar LLM'den değil, financials / sirket_karti / market modüllerinden gelir.
"""
from __future__ import annotations

import streamlit as st

from mercek import config as _config

GORUNUMLER = ["💬 Soru-cevap", "📋 Şirket kartı"]

# Grafiklerde 6 aylık dönemin 12 aylıklarla doğrudan kıyaslanamayacağı akım (gelir/nakit) kalemleri
AKIM_KALEMLER = {"hasilat", "satislarin_maliyeti", "brut_kar", "esas_faaliyet_kari", "finansman_gelirleri",
                 "finansman_giderleri", "parasal_kazanc_kayip", "vergi_oncesi_kar", "donem_kari",
                 "ana_ortaklik_payi", "kgop_payi", "isletme_nakit_akisi", "yatirim_nakit_akisi",
                 "finansman_nakit_akisi"}
DONEM_ETIKET_AKIM = {"2024_12": "2024 · 12 ay", "2025_12": "2025 · 12 ay", "2026_6": "2026 İY · 6 ay"}
DONEM_ETIKET_STOK = {"2024_12": "Ara 2024", "2025_12": "Ara 2025", "2026_6": "Haz 2026"}
RENK_ANA, RENK_ACIK = "#2D198A", "#9C8FE0"


def _tr_sayi(v: float, ondalik: int = 1) -> str:
    s = f"{v:,.{ondalik}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def secici(label: str, secenekler: list, key: str, format_func=str, varsayilan=None):
    """Yeni Streamlit'te segmented control, eskisinde yatay radio. Seçim kaldırılırsa varsayılan."""
    varsayilan = varsayilan or secenekler[0]
    if st.session_state.get(key) is None:  # ilk açılış veya kullanıcı seçimi kaldırdı
        st.session_state[key] = varsayilan
    if hasattr(st, "segmented_control"):
        sec = st.segmented_control(label, secenekler, key=key, format_func=format_func,
                                   label_visibility="collapsed")
    else:
        sec = st.radio(label, secenekler, key=key, format_func=format_func, horizontal=True,
                       label_visibility="collapsed")
    return sec or varsayilan


def trend_grafikleri(adimlar: list) -> None:
    """Cevapta finansal_trend kullanıldıysa seriyi doğrudan financials.trend'den çizer.
    Sayılar LLM'den değil araçtan gelir; grafik cevaptaki rakamlarla aynı kaynaktan beslenir."""
    import altair as alt
    import pandas as pd
    from mercek import financials

    istekler = []
    for s in adimlar or []:
        if s.get("arac") == "finansal_trend":
            g = s.get("girdi") or {}
            anahtar = (g.get("sirket"), g.get("kalem"))
            if all(anahtar) and anahtar not in istekler:
                istekler.append(anahtar)
    istekler = istekler[:3]
    if not istekler:
        return

    cols = st.columns(len(istekler)) if len(istekler) > 1 else [st.container()]
    for col, (sirket, kalem) in zip(cols, istekler):
        try:
            t = financials.trend(sirket, kalem)
        except Exception:
            continue
        if "hata" in t or len(t.get("seri", [])) < 2:
            continue
        oran = "deger" in t["seri"][0]
        deger_k = "deger" if oran else next(k for k in t["seri"][0] if k.endswith("_milyar_TL"))
        akim = kalem in AKIM_KALEMLER
        etiketler = DONEM_ETIKET_AKIM if akim else DONEM_ETIKET_STOK
        yuzde = kalem.endswith("_%")
        satirlar = []
        for r in t["seri"]:
            v = r[deger_k]
            if v is None:
                continue
            alti_ay = akim and r["rapor"].endswith("_6")
            satirlar.append({"Dönem": etiketler.get(r["rapor"], r["rapor"]), "Değer": v,
                             "Etiket": ("%" if yuzde else "") + _tr_sayi(v, 1 if (yuzde or not oran) else 2),
                             "Tip": "6 aylık" if alti_ay else "Karşılaştırılabilir"})
        if len(satirlar) < 2:
            continue
        df = pd.DataFrame(satirlar)
        eksen = "%" if yuzde else ("kat" if oran else "milyar TL")
        base = alt.Chart(df).encode(
            x=alt.X("Dönem:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Değer:Q", title=eksen))
        bars = base.mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=48).encode(
            color=alt.Color("Tip:N", legend=None,
                            scale=alt.Scale(domain=["Karşılaştırılabilir", "6 aylık"], range=[RENK_ANA, RENK_ACIK])),
            tooltip=["Dönem", "Etiket"])
        # Etiket pozitif çubukta üstte, negatif çubukta altta
        yazi = (base.transform_filter(alt.datum["Değer"] >= 0)
                .mark_text(dy=-10, color=RENK_ANA, fontWeight="bold").encode(text="Etiket:N")
                + base.transform_filter(alt.datum["Değer"] < 0)
                .mark_text(dy=12, color=RENK_ANA, fontWeight="bold").encode(text="Etiket:N"))
        with col:
            st.markdown(f"**{t['sirket']} · {t['kalem']}**")
            st.altair_chart((bars + yazi).properties(height=240), use_container_width=True)
            not_ = ("Oran; pay ve payda aynı rapordan, enflasyon düzeltmesi gerekmez." if oran
                    else "Milyar TL, Haziran 2026 satın alma gücüyle (TMS 29).")
            if any(r["Tip"] == "6 aylık" for r in satirlar):
                not_ += " Açık renkli çubuk 6 aylıktır, 12 aylıklarla doğrudan kıyaslanmaz."
            st.caption(not_)


@st.cache_data(ttl=3600, show_spinner=False)
def _piyasa_tablosu():
    from mercek import sirket_karti
    return sirket_karti.piyasa_karsilastirma()


def render_sirket_karti() -> None:
    import pandas as pd
    from mercek import sirket_karti as sk

    st.subheader("Şirket kartı")
    st.caption("Soru sormadan bakılan özet. Tüm değerler finansal tablolardan kodla hesaplanır, LLM kullanılmaz.")
    rapor = secici("Rapor", list(sk.RAPOR_ETIKET), key="kart_rapor", format_func=sk.RAPOR_ETIKET.get,
                   varsayilan="2026_6")

    st.markdown("##### Temel metrikler")
    st.dataframe(pd.DataFrame(sk.karsilastirma(rapor)), hide_index=True, use_container_width=True)
    st.caption("Aynı tarihli raporlar aynı satın alma gücündedir; şirketler yan yana karşılaştırılabilir."
               + (" Kâr marjları 6 aylık döneme aittir." if rapor.endswith("_6") else ""))

    st.markdown("##### Piyasa verisi (güncel)")
    try:
        satirlar, kaynak = _piyasa_tablosu()
        st.dataframe(pd.DataFrame(satirlar), hide_index=True, use_container_width=True)
        st.caption(f"Kaynak: {kaynak}. F/K son 12 ay ana ortaklık kârıyla, PD/DD 30.06.2026 özkaynağıyla "
                   "hesaplanır. Değerleme oranları tek başına ucuz/pahalı yargısı değildir.")
    except Exception as e:  # piyasa verisi kartın geri kalanını engellemesin
        st.caption("Piyasa verisine şu anda ulaşılamadı.")
        print(f"[mercek] piyasa: {type(e).__name__}: {e}")

    st.markdown("##### Risk işaretleri")
    cols = st.columns(len(_config.SIRKETLER))
    for col, (s, ad) in zip(cols, _config.SIRKETLER.items()):
        with col, st.container(border=True):
            st.markdown(f"**{ad}**")
            isaretler = sk.risk_isaretleri(s, rapor)
            if not isaretler:
                st.markdown("Belirgin bir işaret yok.")
            for i in isaretler:
                st.markdown(f"{sk.SEVIYE_IKON[i['seviye']]} **{i['seviye']}: {i['baslik']}**  \n{i['aciklama']}")
    with st.expander("İşaretler nasıl hesaplanıyor?"):
        for e in sk.ESIK_ACIKLAMA:
            st.markdown(f"- {e}")
        st.caption("Kurallar seçilen raporun cari ve önceki dönem sütunlarını karşılaştırır; bu iki sütun TMS 29'a "
                   "göre aynı satın alma gücündedir. İşaretler tanımlayıcıdır, yatırım tavsiyesi değildir.")
