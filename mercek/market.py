"""
Piyasa verisi: hisse fiyatı, getiriler, piyasa değeri ve değerleme oranları.

Kaynak: Yahoo Finance (yfinance). Bulut ortamlarında Yahoo istekleri engellenebildiği için katmanlı yedek:
  1. Taze önbellek (data/market/cache.json, PIYASA_TTL_SAAT kadar geçerli)
  2. Canlı istek (yfinance)
  3. Eski önbellek
  4. Repodaki anlık görüntü (data/market/snapshot.json; scripts/11_fetch_prices.py üretir)
Her cevap verinin tarihini ve hangi katmandan geldiğini söyler.

Değerleme oranları KODLA hesaplanır:
  F/K   = piyasa değeri / son 12 ay ana ortaklık net kârı (TTM)
  PD/DD = piyasa değeri / ana ortaklığa ait özkaynaklar (30.06.2026)
  TTM   = 2025 yıllık x k(Ara25->Haz26) + 2026 ilk yarı - 2025 ilk yarı   (hepsi Haziran 2026 satın alma gücü)
Piyasa değeri ise güncel (nominal) TL'dir; bilanço tarihinden sonraki enflasyon nedeniyle oranlar bir miktar
yüksek çıkar. Bu, çıktıda açıkça belirtilir.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from mercek import config, financials

TICKERS = {"bim": "BIMAS.IS", "tupras": "TUPRS.IS", "aselsan": "ASELS.IS"}
MARKET_DIR = config.DATA / "market"
CACHE_PATH = MARKET_DIR / "cache.json"
SNAPSHOT_PATH = MARKET_DIR / "snapshot.json"
TTL = timedelta(hours=float(os.getenv("PIYASA_TTL_SAAT", "6")))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read(path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_cache(sirket: str, data: dict) -> None:
    try:
        MARKET_DIR.mkdir(parents=True, exist_ok=True)
        cache = _read(CACHE_PATH)
        cache[sirket] = data
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass  # salt okunur ortam: önbelleksiz devam


def fetch_live(sirket: str) -> dict:
    """Yahoo'dan ham piyasa verisi. Hata olursa istisna fırlatır."""
    import warnings

    import yfinance as yf

    t = yf.Ticker(TICKERS[sirket])
    with warnings.catch_warnings():  # yfinance'in kendi kodundaki pandas uyarılarını sustur
        warnings.simplefilter("ignore")
        hist = t.history(period="2y", auto_adjust=False)  # 12 aylık getiri için 1 yıldan uzun
    if hist is None or hist.empty:
        raise RuntimeError("Yahoo boş fiyat serisi döndürdü")
    close = hist["Close"].dropna()
    last_date = close.index[-1]
    last = float(close.iloc[-1])
    year = close[close.index > last_date - timedelta(days=365)]

    def ret(days: int):
        past = close[close.index <= last_date - timedelta(days=days)]
        return None if past.empty else round(100 * (last / float(past.iloc[-1]) - 1), 1)

    shares = mcap = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fi = t.fast_info
            shares = fi["shares"] if "shares" in fi else None
            mcap = fi["marketCap"] if "marketCap" in fi else None
    except Exception:
        pass
    if not mcap and shares:
        mcap = shares * last
    return {
        "borsa_kodu": TICKERS[sirket], "para_birimi": "TRY",
        "kapanis_tarihi": last_date.strftime("%Y-%m-%d"), "son_kapanis_TL": round(last, 2),
        "getiri_1ay_%": ret(30), "getiri_3ay_%": ret(91), "getiri_12ay_%": ret(365),
        "52h_en_yuksek_TL": round(float(year.max()), 2), "52h_en_dusuk_TL": round(float(year.min()), 2),
        "piyasa_degeri_TL": float(mcap) if mcap else None,
        "cekim_zamani": _now().isoformat(timespec="seconds"),
    }


def get_market(sirket: str) -> tuple[dict | None, str]:
    """(veri, durum). durum: 'canlı' | 'önbellek' | 'eski önbellek' | 'anlık görüntü' | hata mesajı"""
    cached = _read(CACHE_PATH).get(sirket)
    if cached:
        try:
            if _now() - datetime.fromisoformat(cached["cekim_zamani"]) < TTL:
                return cached, "önbellek"
        except (KeyError, ValueError):
            pass
    try:
        data = fetch_live(sirket)
        _write_cache(sirket, data)
        return data, "canlı"
    except Exception as e:  # ağ engeli, rate limit, paket yok...
        err = f"{type(e).__name__}"
    if cached:
        return cached, "eski önbellek"
    snap = _read(SNAPSHOT_PATH).get(sirket)
    if snap:
        return snap, "anlık görüntü"
    return None, f"Piyasa verisine ulaşılamadı ({err})"


def ttm_net_kar_bin_tl(sirket: str) -> float | None:
    """Son 12 ay ana ortaklık net kârı, Haziran 2026 satın alma gücünde (bin TL)."""
    g = financials.get
    a25 = g(sirket, "2025_12", "ana_ortaklik_payi", "guncel")
    h1_26 = g(sirket, "2026_6", "ana_ortaklik_payi", "guncel")
    h1_25 = g(sirket, "2026_6", "ana_ortaklik_payi", "onceki")
    k = financials.enflasyon_katsayilari().get("2025_12")
    if None in (a25, h1_26, h1_25, k):
        return None
    return a25 * k + h1_26 - h1_25


def fiyat_ozeti(sirket: str) -> dict:
    if sirket not in TICKERS:
        return {"hata": f"Bilinmeyen şirket '{sirket}'. Geçerli: {list(TICKERS)}"}
    data, durum = get_market(sirket)
    if data is None:
        return {"sirket": config.SIRKETLER.get(sirket, sirket), "hata": durum}

    out = {"sirket": config.SIRKETLER.get(sirket, sirket), **{k: v for k, v in data.items() if k != "cekim_zamani"},
           "veri_durumu": durum}
    mcap = data.get("piyasa_degeri_TL")
    if mcap:
        mcap_bin = mcap / 1e3
        out["piyasa_degeri_milyar_TL"] = round(mcap / 1e9, 2)
        ttm = ttm_net_kar_bin_tl(sirket)
        if ttm is not None:
            out["ttm_net_kar_milyar_TL"] = round(ttm / 1e6, 2)
            out["F/K"] = round(mcap_bin / ttm, 1) if ttm > 0 else None
            if ttm <= 0:
                out["F/K_notu"] = "Son 12 ay net kâr negatif; F/K anlamlı değil."
        oz = financials.get(sirket, "2026_6", "ana_ortaklik_ozkaynaklari", "guncel") or \
            financials.get(sirket, "2026_6", "ozkaynaklar", "guncel")
        if oz:
            out["ana_ortaklik_ozkaynaklari_milyar_TL"] = round(oz / 1e6, 2)
            out["PD/DD"] = round(mcap_bin / oz, 2)
    out.pop("piyasa_degeri_TL", None)
    out["notlar"] = [
        "Fiyat ve getiriler nominal TL'dir; enflasyondan arındırılmamıştır.",
        "F/K ve PD/DD: güncel piyasa değeri / Haziran 2026 satın alma gücündeki finansallar (TTM kâr ve özkaynak). "
        "Bilanço tarihinden sonraki enflasyon nedeniyle oranlar bir miktar yüksek çıkar.",
        "Değerleme oranları tek başına ucuz/pahalı yargısı veya yatırım tavsiyesi değildir.",
    ]
    out["kaynak"] = f"Yahoo Finance ({data.get('borsa_kodu')}, kapanış {data.get('kapanis_tarihi')}); " \
                    "financials.csv (TTM kâr, özkaynak)"
    return out
