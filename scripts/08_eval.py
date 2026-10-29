"""
Mercek - Adım 8: Değerlendirme (eval)

eval/sorular.json içindeki soruları agent'a sorar ve cevapları otomatik puanlar.
Farklı yapılandırmaları (eleştirmensiz / nano eleştirmen / mini eleştirmen) karşılaştırır.

Kontroller (her soru için tanımlı olanlar):
  sayilar   : beklenen rakamlar cevapta geçiyor mu (±0,06 veya %0,5 tolerans)
  sayilar_herhangi : rakam grupları; her gruptan en az biri geçmeli (eşdeğer doğru cevaplar)
  araclar   : beklenen araçlar çağrıldı mı
  arac_yok  : hiç araç çağrılmadı mı (kapsam dışı / injection)
  gerekli   : cevapta olması gereken ifadeler (regex)
  yasak     : cevapta olmaması gereken ifadeler (regex)
  kaynak    : dipnot atfı (Not N) var mı
  dogrulama : "Doğrulanamayan rakamlar" uyarısı çıkmadı mı (her soruda)

Kullanım:
  uv run python scripts/08_eval.py                          # varsayılan: mini eleştirmen
  uv run python scripts/08_eval.py --configs yok,nano,mini  # üç yapılandırmayı karşılaştır
  uv run python scripts/08_eval.py --only R05,R07,G02       # belirli sorular
  uv run python scripts/08_eval.py --configs yok,mini --tekrar 3   # kararlılık için 3 tekrar
  uv run python scripts/08_eval.py --configs yok,multi --tekrar 3  # tek agent vs multi-agent
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mercek import config  # noqa: E402
from mercek import agent as agent_mod  # noqa: E402
from mercek import multi_agent  # noqa: E402

EVAL_DIR = config.ROOT / "eval"
CONFIGS = {
    "yok": {"AGENT_MODE": "single", "CRITIC_ENABLED": False},          # tek agent (varsayılan)
    "nano": {"AGENT_MODE": "single", "CRITIC_ENABLED": True, "CRITIC_MODEL": "gpt-5.4-nano"},
    "mini": {"AGENT_MODE": "single", "CRITIC_ENABLED": True, "CRITIC_MODEL": "gpt-5.4-mini"},
    "multi": {"AGENT_MODE": "multi", "CRITIC_ENABLED": False},         # supervisor + uzmanlar + sentez
}
CITATION = re.compile(r"Not\s*\d+")


def numbers_in(text: str) -> list[float]:
    return [v for _, v in agent_mod.answer_numbers(text)]


def has_number(expected: float, found: list[float]) -> bool:
    e = abs(expected)
    return any(abs(e - f) <= max(0.06, 0.005 * e) for f in found)


def score(q: dict, out: dict) -> dict[str, bool]:
    ans = out["cevap"].split("\n---\n")[0]  # uyarı satırını hariç tut
    used = [s["arac"] for s in out["adimlar"]
            if s["arac"] not in ("kontrol", "elestirmen", "kapsam", "supervisor", "bulgu")]
    checks: dict[str, bool] = {}
    found = numbers_in(ans)
    for v in q.get("sayilar", []):
        checks[f"sayi:{v}"] = has_number(v, found)
    for grp in q.get("sayilar_herhangi", []):  # gruptaki rakamlardan en az biri yeterli
        checks["sayi:" + "|".join(map(str, grp))] = any(has_number(v, found) for v in grp)
    for a in q.get("araclar", []):
        checks[f"arac:{a}"] = a in used
    if q.get("arac_yok"):
        checks["arac_yok"] = not used
    for i, pat in enumerate(q.get("gerekli", [])):
        checks[f"gerekli{i + 1}"] = bool(re.search(pat, ans, re.I))
    for i, pat in enumerate(q.get("yasak", [])):
        checks[f"yasak{i + 1}"] = not re.search(pat, ans, re.I)
    if q.get("kaynak"):
        checks["kaynak"] = bool(CITATION.search(ans))
    checks["dogrulama"] = "Doğrulanamayan rakamlar" not in out["cevap"]
    return checks


def cost_usd(usage: dict, critic_model: str | None) -> float:
    def c(u, model):
        pin, pout = config.PRICES.get(model, (0.0, 0.0))
        return (u.get("input_tokens", 0) * pin + u.get("output_tokens", 0) * pout) / 1e6
    total = c(usage.get("agent", {}), config.AGENT_MODEL)
    if critic_model:
        total += c(usage.get("critic", {}), critic_model)
    return total


def run_config(name: str, questions: list[dict], out_dir: Path, repeats: int = 1) -> dict:
    for k, v in CONFIGS[name].items():
        setattr(config, k, v)
    impl = multi_agent if config.AGENT_MODE == "multi" else agent_mod
    graph = impl.build_graph()
    critic_model = config.CRITIC_MODEL if (config.CRITIC_ENABLED and impl is agent_mod) else None
    rows = []
    print(f"\n=== Yapılandırma: {name} (mimari={config.AGENT_MODE}, model={config.AGENT_MODEL}, "
          f"eleştirmen={critic_model or 'yok'}) ===")
    for q, rep_i in [(q, r) for q in questions for r in range(repeats)]:
        t0 = time.time()
        try:
            out = impl.ask(q["soru"], graph=graph)
        except Exception as e:
            out = {"cevap": f"HATA: {type(e).__name__}: {e}", "adimlar": [], "kullanim": {}}
        dt = time.time() - t0
        checks = score(q, out)
        passed = sum(checks.values())
        rewrites = sum(1 for s in out["adimlar"] if s["arac"] in ("kontrol", "elestirmen")
                       and "yeniden yazdır" in s["cikti_ozeti"].lower())
        row = {
            "config": name, "id": q["id"], "tekrar": rep_i + 1, "kategori": q["kategori"],
            "puan": round(passed / len(checks), 3),
            "gecen": passed, "toplam": len(checks), "tam_dogru": passed == len(checks),
            "basarisiz": ", ".join(k for k, v in checks.items() if not v),
            "yeniden_yazim": rewrites, "sure_sn": round(dt, 1),
            "maliyet_usd": round(cost_usd(out.get("kullanim", {}), critic_model), 5),
            "araclar": ", ".join(s["arac"] for s in out["adimlar"]),
            "soru": q["soru"], "cevap": out["cevap"].split("\n---\n")[0],
        }
        rows.append(row)
        mark = "✓" if row["tam_dogru"] else "✗"
        tag = f"{q['id']}#{rep_i + 1}" if repeats > 1 else q["id"]
        print(f"  {mark} {tag:6s} {passed}/{len(checks)}  {dt:5.1f}sn  ${row['maliyet_usd']:.4f}"
              + (f"   başarısız: {row['basarisiz']}" if row["basarisiz"] else ""))

    path = out_dir / f"{name}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    # Soru bazında kararlılık: kaç tekrarda tam doğru
    by_q: dict[str, list[bool]] = {}
    for r in rows:
        by_q.setdefault(r["id"], []).append(r["tam_dogru"])
    kararsiz = {qid: f"{sum(v)}/{len(v)}" for qid, v in by_q.items() if 0 < sum(v) < len(v)}
    hep_basarisiz = [qid for qid, v in by_q.items() if not any(v)]
    if repeats > 1:
        print(f"  Kararsız sorular (bazen doğru): {kararsiz or '-'}")
        print(f"  Her tekrarda başarısız: {hep_basarisiz or '-'}")
    return {
        "config": name, "repeats": repeats, "kararsiz": kararsiz, "hep_basarisiz": hep_basarisiz,
        "tam_dogru": sum(r["tam_dogru"] for r in rows), "n": n,
        "ort_puan": sum(r["puan"] for r in rows) / n,
        "kategori": {k: sum(r["puan"] for r in rows if r["kategori"] == k) /
                     max(1, sum(1 for r in rows if r["kategori"] == k)) for k in sorted({r["kategori"] for r in rows})},
        "ort_sure": sum(r["sure_sn"] for r in rows) / n,
        "toplam_maliyet": sum(r["maliyet_usd"] for r in rows),
        "soru_basi_maliyet": sum(r["maliyet_usd"] for r in rows) / n,
        "yeniden_yazim": sum(r["yeniden_yazim"] for r in rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="mini", help="virgülle: yok,nano,mini")
    ap.add_argument("--only", help="virgülle soru id'leri (örn. R05,G02)")
    ap.add_argument("--tekrar", type=int, default=1, help="her soruyu kaç kez çalıştır (LLM rastgeleliği için)")
    args = ap.parse_args()

    data = json.loads((EVAL_DIR / "sorular.json").read_text(encoding="utf-8"))
    questions = data["sorular"]
    if args.only:
        ids = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in ids]
    names = [c.strip() for c in args.configs.split(",")]
    for n in names:
        if n not in CONFIGS:
            sys.exit(f"Bilinmeyen yapılandırma: {n}. Seçenekler: {list(CONFIGS)}")

    out_dir = EVAL_DIR / "sonuclar" / datetime.now().strftime("%Y%m%d_%H%M")
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = [run_config(n, questions, out_dir, args.tekrar) for n in names]

    cats = sorted({c for s in summaries for c in s["kategori"]})
    lines = ["| Yapılandırma | Tam doğru | Oran | Ort. puan | " + " | ".join(cats) +
             " | Yeniden yazım | Ort. süre | Soru başı maliyet |",
             "|---" * (7 + len(cats)) + "|"]
    for s in summaries:
        lines.append(f"| {s['config']} | {s['tam_dogru']}/{s['n']} | {s['tam_dogru'] / s['n']:.0%} | {s['ort_puan']:.0%} | "
                     + " | ".join(f"{s['kategori'].get(c, 0):.0%}" for c in cats)
                     + f" | {s['yeniden_yazim']} | {s['ort_sure']:.1f} sn | ${s['soru_basi_maliyet']:.4f} |")
    if args.tekrar > 1:
        lines.append("")
        lines.append(f"Her soru {args.tekrar} kez çalıştırıldı. Kararsız sorular:")
        for s in summaries:
            lines.append(f"- {s['config']}: {s['kararsiz'] or '-'}; her tekrarda başarısız: {s['hep_basarisiz'] or '-'}")
    table = "\n".join(lines)
    (out_dir / "ozet.md").write_text(f"# Mercek eval — {out_dir.name}\n\nAgent: {config.AGENT_MODEL}\n\n{table}\n",
                                     encoding="utf-8")
    print("\n" + table)
    print(f"\nAyrıntılar: {out_dir}")


if __name__ == "__main__":
    main()
