"""Mercek: finansal raporlar için RAG + agent araştırma sistemi."""

# Chroma, sqlite3 >= 3.35 ister. Bazı Linux bulut imajlarında (ör. Streamlit Community Cloud) sistem sqlite3
# daha eski olabilir; pysqlite3-binary kuruluysa onu kullan. Windows/macOS'ta bu paket kurulmaz, etkisi yoktur.
try:
    import sys as _sys

    __import__("pysqlite3")
    _sys.modules["sqlite3"] = _sys.modules.pop("pysqlite3")
except ImportError:
    pass
