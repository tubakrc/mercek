"""
Mercek — Streamlit arayüzü

Lokal:  uv run streamlit run app.py
Cloud:  Streamlit Community Cloud'da OPENAI_API_KEY 'Secrets' bölümüne yazılır.
"""
from __future__ import annotations

import os
import time

import streamlit as st

# Streamlit Cloud secrets -> ortam değişkenleri (mercek.config import edilmeden ÖNCE)
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:  # lokalde secrets.toml yoksa
    pass

from mercek import agent as agent_mod  # noqa: E402

MAX_QUESTIONS = int(os.getenv("MAX_QUESTIONS_PER_SESSION", "10"))
MAX_CHARS = 400

ORNEK_SORULAR = [
    "Tüpraş'ın 2026 ilk yarı hasılatı ne kadar arttı ve dipnotlarda nedeni hakkında ne var?",
    "BİM'in kârlılığı 2025'te arttı mı, azaldı mı? Enflasyon muhasebesinin etkisi ne?",
    "BİM'in finansal borcunun ne kadarı kira yükümlülüğü?",
    "Aselsan'ın özkaynakları son üç dönemde nasıl değişti?",
    "Tüpraş'ın koşullu yükümlülükleri ve verdiği teminatlar neler?",
    "Üç şirketin 2025 brüt kâr marjlarını karşılaştır.",
]

ARAC_ADI = {"finansal_ozet": "📊 Finansal özet", "finansal_trend": "📈 Dönem karşılaştırması",
            "dipnot_ara": "🔎 Dipnot araması", "kontrol": "🛡️ Rakam/kural kontrolü",
            "elestirmen": "🧐 Eleştirmen", "kapsam": "🚦 Kapsam kontrolü"}

st.set_page_config(page_title="Mercek", page_icon="🔍", layout="centered")


def _code_version() -> str:
    """mercek/ içindeki .py dosyalarının değişim zamanları: kod değişince önbellek yenilensin."""
    from pathlib import Path
    pkg = Path(agent_mod.__file__).parent
    return "|".join(f"{p.name}:{p.stat().st_mtime_ns}" for p in sorted(pkg.glob("*.py")))


@st.cache_resource(show_spinner="Mercek hazırlanıyor…")
def get_graph(version: str):
    import importlib
    from mercek import config, financials, tools, agent  # değişen modülleri yeniden yükle
    for mod in (config, financials, tools, agent):
        importlib.reload(mod)
    graph = agent.build_graph()
    from mercek.tools import _retriever
    _retriever()  # indeksi ve BM25'i bir kez yükle
    return graph


def render_answer(out: dict) -> None:
    st.markdown(out["cevap"])
    if out.get("kaynaklar"):
        with st.expander(f"Dipnot kaynakları ({len(out['kaynaklar'])})"):
            for k in out["kaynaklar"]:
                st.markdown(f"- {k}")
    if out.get("adimlar"):
        with st.expander(f"Agent adımları ({len(out['adimlar'])})"):
            for i, s in enumerate(out["adimlar"], 1):
                girdi = ", ".join(f"{k}={v}" for k, v in s["girdi"].items())
                st.markdown(f"**{i}. {ARAC_ADI.get(s['arac'], s['arac'])}**" + (f" `{girdi}`" if girdi else ""))
                st.code(s["cikti_ozeti"], language=None)
    if out.get("sure"):
        st.caption(f"{out['sure']:.1f} sn")


# --- durum ----------------------------------------------------------------------------
st.session_state.setdefault("history", [])
st.session_state.setdefault("count", 0)
st.session_state.setdefault("pending", None)

# --- kenar çubuğu -------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Kapsam")
    st.markdown("**BİM · Tüpraş · Aselsan**  \nKonsolide finansal raporlar:  \n"
                "2024 yıllık · 2025 yıllık · 2026 ilk 6 ay")
    st.markdown("### Örnek sorular")
    for q in ORNEK_SORULAR:
        if st.button(q, use_container_width=True):
            st.session_state.pending = q
    st.divider()
    kalan_ph = st.empty()  # soru işlendikten sonra doldurulur (sayaç güncel olsun)
    if st.button("Sohbeti temizle", use_container_width=True):
        st.session_state.history = []
        st.rerun()
    st.divider()
    st.caption("Rakamlar finansal tablolardan kodla hesaplanır ve TMS 29'a göre ilgili raporun satın "
               "alma gücüyle ifade edilir. Dönemler arası karşılaştırmalar aynı satın alma gücüne taşınır.")
    st.caption("Bu proje KAP, Borsa İstanbul veya ilgili şirketlerle bağlantılı değildir. "
               "Sorular kalite için kaydedilebilir; kişisel bilgi girmeyin.")

# --- başlık -----------------------------------------------------------------------------
st.title("🔍 Mercek")
st.markdown("Finansal raporları sizin için okuyan yapay zekâ araştırma asistanı. "
            "Her rakam tablolardan hesaplanır, her açıklama dipnot ve sayfa numarasıyla gelir.")
st.info("Eğitim amaçlı bir projedir, **yatırım tavsiyesi değildir.**", icon="ℹ️")

for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            render_answer(msg["content"])

# --- soru ---------------------------------------------------------------------------------
typed = st.chat_input("Bir soru sorun… (örn. Tüpraş'ın net borcu ne kadar?)", max_chars=MAX_CHARS)
question = typed or st.session_state.pending
st.session_state.pending = None

if question:
    if st.session_state.count >= MAX_QUESTIONS:
        st.warning("Bu oturumdaki soru hakkınız doldu. Demo maliyetini sınırlı tutmak için soru sayısı sınırlıdır.")
    elif not os.getenv("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY tanımlı değil. Lokal için .env dosyasına, Streamlit Cloud için Secrets'a ekleyin.")
    else:
        st.session_state.count += 1
        st.session_state.history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            t0 = time.time()
            with st.status("Araştırılıyor…", expanded=False) as status:
                try:
                    out = agent_mod.ask(question, graph=get_graph(_code_version()),
                                        on_step=lambda label: status.update(label=f"{label}…"))
                    status.update(label="Tamamlandı", state="complete")
                except Exception as e:  # kullanıcıya iç hata ayrıntısı gösterme
                    status.update(label="Bir hata oluştu", state="error")
                    out = {"cevap": "Üzgünüm, bu soruyu şu anda işleyemedim. Lütfen biraz sonra tekrar deneyin.",
                           "adimlar": [], "kaynaklar": []}
                    print(f"[mercek] hata: {type(e).__name__}: {e}")
            out["sure"] = time.time() - t0
            render_answer(out)
        st.session_state.history.append({"role": "assistant", "content": out})

kalan_ph.caption(f"Bu oturumda kalan soru hakkı: **{max(MAX_QUESTIONS - st.session_state.count, 0)}/{MAX_QUESTIONS}**")
