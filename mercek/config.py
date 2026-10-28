"""Ortak ayarlar. Değerler .env dosyasından veya ortam değişkenlerinden okunur."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
CHUNKS_PATH = DATA / "processed" / "chunks.jsonl"
FINANCIALS_PATH = DATA / "processed" / "financials.csv"
# Windows'ta Chroma, ASCII dışı karakter (ü, ş...) içeren veya OneDrive altındaki yollarda
# indeksi okuyamayabilir. Gerekirse .env'de CHROMA_DIR=C:/mercek_index gibi bir yol ver.
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(DATA / "index" / "chroma")))
# Embedding önbelleği: indeksi yeniden kurmak için OpenAI'a tekrar istek atılmaz
EMBED_CACHE = DATA / "index" / "embeddings.jsonl"
# Deploy için sıkıştırılmış embedding dosyası (repoya girer); Chroma indeksi buradan otomatik kurulur
EMBED_NPZ = DATA / "index" / "embeddings.npz"
COLLECTION = "dipnotlar"

# Model adı .env'den değiştirilebilir. Güncel modeller ve fiyatlar: platform.openai.com
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

SIRKETLER = {"bim": "BİM", "tupras": "Tüpraş", "aselsan": "Aselsan"}

# LLM modelleri (.env'den değiştirilebilir). Güncel model ID'lerini OpenAI panelinden doğrula.
AGENT_MODEL = os.getenv("AGENT_MODEL", "gpt-5.4-mini")  # araç seçimi + cevap sentezi
FAST_MODEL = os.getenv("FAST_MODEL", "gpt-5.4-nano")     # basit adımlar (sınıflandırma, guardrail)
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "12"))  # sonsuz araç döngüsüne karşı sınır
# Eleştirmen agent ile aynı model: nano rakam karşılaştırmada iyi ama muhasebe mantığında hata yapabiliyor.
# Maliyet için CRITIC_MODEL=gpt-5.4-nano denenebilir; seçim eval setiyle ölçülmeli.
CRITIC_MODEL = os.getenv("CRITIC_MODEL", AGENT_MODEL)
# Eval (23 soru x 3 tekrar) sonucu: eleştirmensiz %97, mini eleştirmen %90, nano %87 tam doğru; eleştirmen
# ayrıca süreyi ve maliyeti artırdı. Bu yüzden varsayılan KAPALI. Deney için CRITIC_ENABLED=1.
CRITIC_ENABLED = os.getenv("CRITIC_ENABLED", "0") == "1"

# Tahmini maliyet hesabı için (USD / 1M token: giriş, çıkış). Güncel fiyatları OpenAI'dan doğrula.
PRICES = {
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
}
