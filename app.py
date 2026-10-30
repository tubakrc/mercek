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
from mercek import config as _config  # noqa: E402

MAX_QUESTIONS = int(os.getenv("MAX_QUESTIONS_PER_SESSION", "10"))
MAX_CHARS = 400

ORNEK_SORULAR = [
    "Tüpraş'ın 2026 ilk yarı hasılatı ne kadar arttı ve dipnotlarda nedeni hakkında ne var?",
    "BİM'in kârlılığı 2025'te arttı mı, azaldı mı? Enflasyon muhasebesinin etkisi ne?",
    "BİM'in finansal borcunun ne kadarı kira yükümlülüğü?",
    "Aselsan'ın özkaynakları son üç dönemde nasıl değişti?",
    "Tüpraş'ın koşullu yükümlülükleri ve verdiği teminatlar neler?",
    "Üç şirketin 2025 brüt kâr marjlarını karşılaştır.",
    "Aselsan'ın güncel piyasa değeri, F/K ve PD/DD oranları nedir?",
    "Tüpraş'ın borçluluğu son üç dönemde nasıl değişti ve dipnotlarda borçların vade yapısı nasıl açıklanıyor?",
]

ARAC_ADI = {"finansal_ozet": "📊 Finansal özet", "finansal_trend": "📈 Dönem karşılaştırması",
            "dipnot_ara": "🔎 Dipnot araması", "kontrol": "🛡️ Rakam/kural kontrolü",
            "elestirmen": "🧐 Eleştirmen", "kapsam": "🚦 Kapsam kontrolü",
            "fiyat_verisi": "💹 Piyasa verisi", "supervisor": "🧭 Supervisor planı", "bulgu": "📝 Uzman bulguları"}
AGENT_ADI = {"veri_agent": "Veri agent'ı", "dipnot_agent": "Dipnot agent'ı", "supervisor": "Supervisor",
             "router": "Router", "kontrol": "Kontrol"}
MODLAR = {"Multi-agent (supervisor + uzmanlar)": "multi", "Tek agent": "single"}

st.set_page_config(page_title="Mercek", page_icon="🔍", layout="centered")

st.markdown("""
<style>
[data-testid="stSidebar"] { background-color: #2D198A; }
[data-testid="stSidebar"] * { color: #D2F4FD; }
h1, h2, h3 { color: #2D198A; }

/* Varsayılan: koyu zemin, açık yazı */
.stButton > button,
.stButton > button:focus,
.stButton > button:active {
    background-color: #3F2AB0 !important;
    border: 2px solid #3F2AB0 !important;
}
.stButton > button,
.stButton > button * { color: #D2F4FD !important; }

/* Hover: açık zemin, koyu yazı */
.stButton > button:hover {
    background-color: #D2F4FD !important;
    border-color: #3F2AB0 !important;
}
.stButton > button:hover,
.stButton > button:hover * { color: #3F2AB0 !important; }

[data-testid="stSidebar"] .stButton > button { border-color: #D2F4FD !important; }

/* Radio: seçili olmayan = boş halka, seçili = dolu daire + kalın yazı */
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child,
[data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child {
    background-color: transparent !important;
    border: 2px solid #D2F4FD !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child > div,
[data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child > div {
    background-color: transparent !important;
}
[data-testid="stSidebar"] label:has(input:checked) > div > div:first-child,
[data-testid="stSidebar"] [data-baseweb="radio"]:has(input:checked) > div:first-child {
    background-color: #D2F4FD !important;
}
[data-testid="stSidebar"] label:has(input:checked) > div > div:first-child > div,
[data-testid="stSidebar"] [data-baseweb="radio"]:has(input:checked) > div:first-child > div {
    background-color: #2D198A !important;
}
[data-testid="stSidebar"] label:has(input:checked) p { font-weight: 700; }
[data-testid="stSidebar"] label:not(:has(input:checked)) p { opacity: 0.75; }
</style>
""", unsafe_allow_html=True)

def _code_version() -> str:
    """mercek/ içindeki .py dosyalarının değişim zamanları: kod değişince önbellek yenilensin."""
    from pathlib import Path
    pkg = Path(agent_mod.__file__).parent
    return "|".join(f"{p.name}:{p.stat().st_mtime_ns}" for p in sorted(pkg.glob("*.py")))


@st.cache_resource(show_spinner="Mercek hazırlanıyor…")
def get_runner(version: str, mode: str):
    """(graf, ask fonksiyonu). Kod değişince veya mod değişince yeniden kurulur."""
    import importlib
    from mercek import config, financials, market, tools, agent, multi_agent  # değişen modülleri yeniden yükle
    for mod in (config, financials, market, tools, agent, multi_agent):
        importlib.reload(mod)
    impl = multi_agent if mode == "multi" else agent
    graph = impl.build_graph()
    tools._retriever()  # indeksi ve BM25'i bir kez yükle
    return graph, impl.ask


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
                kim = AGENT_ADI.get(s.get("agent", ""), "")
                st.markdown(f"**{i}. {ARAC_ADI.get(s['arac'], s['arac'])}**" + (f" · *{kim}*" if kim else "")
                            + (f" `{girdi}`" if girdi else ""))
                st.code(s["cikti_ozeti"], language=None)
    if out.get("sure"):
        st.caption(f"{out['sure']:.1f} sn" + (f" · {out['mod']}" if out.get("mod") else ""))


# --- durum ----------------------------------------------------------------------------
st.session_state.setdefault("history", [])
st.session_state.setdefault("count", 0)
st.session_state.setdefault("pending", None)

# --- kenar çubuğu -------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Kapsam")
    st.markdown("**BİM · Tüpraş · Aselsan**  \nKonsolide finansal raporlar:  \n"
                "2024 yıllık · 2025 yıllık · 2026 ilk 6 ay")
    varsayilan = 0 if _config.AGENT_MODE == "multi" else 1
    mod_adi = st.radio("Mimari", list(MODLAR), index=varsayilan,
                       help="Multi-agent: supervisor soruyu veri ve dipnot uzmanlarına dağıtır, sentez agent'ı "
                            "bulguları birleştirir. Tek agent: tek bir agent tüm araçları kullanır.")
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
st.markdown("Finansal raporları sizin için okuyan yapay zeka araştırma asistanı. "
            "Her rakam tablolardan hesaplanır, her açıklama dipnot ve sayfa numarasıyla gelir.")


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
                    graph, ask_fn = get_runner(_code_version(), MODLAR[mod_adi])
                    out = ask_fn(question, graph=graph, on_step=lambda label: status.update(label=f"{label}…"))
                    out["mod"] = mod_adi.split(" (")[0]
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
