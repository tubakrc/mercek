# Mercek eval — 20261028_2132

Agent: gpt-5.4-mini

| Yapılandırma | Tam doğru | Oran | Ort. puan | birim | dipnot | donem | guardrail | karsilastirma | rakam | tms29 | trend | yorum | Yeniden yazım | Ort. süre | Soru başı maliyet |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| yok | 67/69 | 97% | 99% | 100% | 100% | 83% | 100% | 100% | 100% | 100% | 100% | 100% | 4 | 3.4 sn | $0.0077 |
| nano | 60/69 | 87% | 96% | 92% | 98% | 58% | 98% | 100% | 100% | 100% | 96% | 87% | 58 | 7.8 sn | $0.0137 |
| mini | 62/69 | 90% | 97% | 92% | 100% | 83% | 96% | 100% | 100% | 100% | 100% | 80% | 18 | 4.8 sn | $0.0121 |

Her soru 3 kez çalıştırıldı. Kararsız sorular:
- yok: {'R12': '1/3'}; her tekrarda başarısız: -
- nano: {'R04': '2/3', 'R06': '1/3', 'D02': '2/3', 'R13': '2/3', 'G05': '2/3'}; her tekrarda başarısız: ['R12']
- mini: {'R12': '1/3', 'R13': '2/3', 'G05': '2/3'}; her tekrarda başarısız: ['R06']
