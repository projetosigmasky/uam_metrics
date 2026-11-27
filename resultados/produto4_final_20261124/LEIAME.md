# Resultados do Produto 4: campanha final (rodadas de 18 a 24/11/2026)

Dashboards das quatro condições da campanha final do Produto 4, gerados com este código (`83ea889`) a partir das
rodadas completas (50 réplicas por configuração):

| Pasta | Condição | Configurações | Registros |
|---|---|---|---|
| `nominal/` | nominal | 37 (C0 e 36 variantes) | 1.850 |
| `departure/` | atraso de partida | 36 | 1.800 |
| `wind/` | vento | 36 | 1.800 |
| `blockage/` | bloqueio de espaço aéreo (SBMT IFR) | 36 | 1.800 |

Cada pasta é um site completo (`index.html` + `assets/`, cerca de 0,8 GB). Ficaram fora, como no `.gitignore` de
`docs/`, as cópias locais `assets/data/runs/`, `assets/data/critical_waypoints/passage_events.jsonl` e
`waypoints_by_replica.csv`; elas permanecem no servidor em `/dados/orbolato/uam_metrics_runs/final_83ea889/`.

Publicação, como na rodada de 06/11/2026: `nominal/` substitui `docs/` deste repositório e as demais vão para os
sites próprios (`uam_metrics_departure`, `uam_metrics_wind`, `uam_metrics_blockage`), pois juntas passariam do limite
de 1 GB do GitHub Pages.

## Parâmetros

    python -u generate_dashboard.py --config configs/full_COND.json --workers 8 --output docs_full_COND \
      --lowc-horizontal-m 1852 --lowc-vertical-m 152.4 --airport-lowc-horizontal-m 1852 --airport-lowc-vertical-m 152.4 \
      --tls-target-per-flight-hour 8.9e-6 --mac-probability-given-nmac 0.19054441260744986

- LoWC: 1 NM (1.852 m) horizontal e 500 ft (152,4 m) vertical, também para o tráfego dos aeroportos.
- TLS do Produto III v2.0: 0,89 MAC por 10^5 h de voo (8,9e-6 por hora de voo).
- P(MAC|NMAC) = 133/698 = 0,1905, calibrada nos NMAC da C0 com esfera de colisão de 15,2 m.
- `configs/full_COND.json`: configurações usadas; os caminhos são os do servidor de processamento.

Os indicadores são os mesmos dos dashboards gerados em 24/11/2026 com o commit `513a275`; esta geração acrescenta
a ocupação das quadrículas CIRCEA e a grade de capacidade dos commits posteriores.
