"""Türkçe metin normalizasyonu ve BM25 için tokenizasyon."""
from __future__ import annotations

import re
import unicodedata

# Türkçe eklemeli bir dil: "borçlanmalar", "borçlanmaların", "borçlanmaya" aynı kökten gelir.
# Basit ama etkili bir yöntem: her kelimenin ilk 5 harfini almak ("F5 stemming").
# Türkçe bilgi erişimi çalışmalarında tam bir kök bulucuya yakın sonuç verdiği bilinir.
PREFIX_LEN = 5

STOPWORDS = {
    "ve", "ile", "bir", "bu", "da", "de", "icin", "olan", "olarak", "gibi", "veya",
    "ya", "ki", "en", "cok", "daha", "her", "ise", "mi", "mu", "ne", "nasil",
    "nedir", "hangi", "olup", "tarafindan", "uzere", "kadar", "sonra", "once",
}


def norm(text: str) -> str:
    """Büyük harf, Türkçe karakterler ve şapkasız (eşleştirme amaçlı)."""
    text = text.replace("ı", "I").replace("İ", "I")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.upper()


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z]+|\d+", norm(text).lower())
    out = []
    for w in words:
        if w in STOPWORDS:
            continue
        if w.isdigit():
            if len(w) >= 2:  # yıl, not numarası gibi
                out.append(w)
            continue
        if len(w) >= 2:
            out.append(w[:PREFIX_LEN])
    return out
