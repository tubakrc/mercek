"""
Mercek - Adım 11: Piyasa verisinin anlık görüntüsünü al (deploy yedeği)

Yahoo Finance'ten üç şirketin fiyat verisini çeker ve data/market/snapshot.json dosyasına yazar.
Bu dosya repoya girer: bulutta Yahoo erişimi engellenirse uygulama bu veriyle (tarihini belirterek) çalışır.

Kullanım:
  uv run python scripts/11_fetch_prices.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mercek import market  # noqa: E402


def main() -> None:
    snap = {}
    for sirket, ticker in market.TICKERS.items():
        try:
            d = market.fetch_live(sirket)
            snap[sirket] = d
            mcap = d.get("piyasa_degeri_TL")
            print(f"{ticker:9s} kapanış {d['son_kapanis_TL']:>9} TL ({d['kapanis_tarihi']})  "
                  f"piyasa değeri {'-' if not mcap else f'{mcap / 1e9:,.1f} milyar TL'}")
        except Exception as e:
            print(f"{ticker:9s} HATA: {type(e).__name__}: {e}")
    if not snap:
        sys.exit("Hiç veri alınamadı; anlık görüntü yazılmadı.")
    market.MARKET_DIR.mkdir(parents=True, exist_ok=True)
    market.SNAPSHOT_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Yazıldı: {market.SNAPSHOT_PATH}")
    for s in snap:
        o = market.fiyat_ozeti(s)
        print(f"  {o['sirket']:8s} F/K={o.get('F/K')}  PD/DD={o.get('PD/DD')}  TTM kâr={o.get('ttm_net_kar_milyar_TL')} milyar TL")


if __name__ == "__main__":
    main()
