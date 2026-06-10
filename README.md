# UAM KPI/KPA Dashboard

Dashboard estatico para analisar logs `STATELOG` do BlueSky em cenarios de corredor aereo urbano na RMSP.

Este repositorio implementa, em codigo, metricas de seguranca e eficiencia descritas no estudo `Projeto_SIGMA_Sky_Produto_3_Versao_0.pdf`. A saida principal e a pasta `docs/`, pronta para GitHub Pages.

## 1. Preparar Os Logs

Coloque os arquivos `STATELOG*.log` em:

```text
data/
```

A pasta `data/` fica fora do Git pelo `.gitignore`, entao os logs brutos nao entram no GitHub.

Exemplo:

```text
data/
  STATELOG_1_maior_movimento.log
  STATELOG_2_maior_movimento.log
```

O formato esperado pelo parser e:

```text
simt,id,lat,lon,distflown,alt,cas,tas,gs
```

## 2. Gerar O Dashboard

Para processar todos os logs em `data/`:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py
```

Para processar logs especificos:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py .\data\STATELOG_1.log .\data\STATELOG_2.log
```

Para escolher outra pasta de entrada:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py --data-dir logs_brutos
```

## 3. Parametros E Hiperparametros

Os parametros principais ficam em `src/uam_dashboard/config.py`:

```python
flight_instance_gap_seconds = 300.0
flight_instance_reset_distance_m = 250.0
flight_instance_jump_m = 5000.0
lowc_horizontal_m = 500.0
lowc_vertical_m = 30.0
nmac_horizontal_m = 150.0
nmac_vertical_m = 30.0
mac_probability_bands = (0.001, 0.01, 0.05)
conflict_sample_seconds = 10
same_altitude_band_m = 150.0
track_sample_stride = 20
trajectory_shape_points = 12
trajectory_cluster_distance_m = 1200.0
trajectory_endpoint_tolerance_m = 2500.0
heatmap_sample_stride = 10
```

Alguns parametros podem ser alterados pela linha de comando:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py --lowc-horizontal-m 600 --lowc-vertical-m 40 --nmac-horizontal-m 150
```

## 4. Saida Gerada

O gerador publica em `docs/`:

- `docs/index.html`: dashboard principal.
- `docs/assets/data_bundle.js`: pacote de dados usado pela pagina.
- `docs/assets/data/dashboard.json`: metricas agregadas ou medias.
- `docs/assets/data/comparison.json`: tabela comparativa.
- `docs/assets/data/runs/*.json`: dados por log processado.
- `docs/assets/data/tracks.geojson`: trajetorias executadas do primeiro log, com grupos e frequencias.
- `docs/assets/data/conflicts.geojson`: eventos LoWC/NMAC do primeiro log.
- `docs/assets/data/heatmap_points.json`: pontos de densidade do primeiro log.
- `docs/assets/charts/*.png`: graficos estaticos por log.

## 5. Responsabilidades Dos Modulos

| Arquivo | Responsabilidade |
|---|---|
| `generate_dashboard.py` | Orquestra leitura, metricas, graficos, JSON/GeoJSON e copia `web/` para `docs/`. |
| `src/uam_dashboard/config.py` | Centraliza colunas, unidades, limiares LoWC/NMAC, amostragem e bandas MAC. |
| `src/uam_dashboard/log_parser.py` | Le o `STATELOG`, converte campos numericos e ordena os registros. |
| `src/uam_dashboard/metrics.py` | Implementa formulas de seguranca, eficiencia, exposicao e severidade. |
| `src/uam_dashboard/metric_catalog.py` | Mantem a rastreabilidade entre metrica, formula, PDF, codigo e status. |
| `src/uam_dashboard/exports.py` | Agrupa trajetorias semelhantes e converte trajetorias/eventos para GeoJSON. |
| `src/uam_dashboard/plots.py` | Gera PNGs de aeronaves simultaneas, separacao, altitude, distancia e severidade. |
| `web/index.html` | Estrutura estatica da pagina. |
| `web/assets/dashboard.js` | Renderiza os dados, mapas, comparacoes e metricas previamente processados pelo Python. |
| `web/assets/dashboard.css` | Layout visual e regras criticas do Leaflet. |

## 6. Rastreabilidade Das Formulas

| Metrica | Formula implementada | Referencia no PDF | Codigo |
|---|---|---|---|
| Frequencia de trajetorias | Contagem de instancias com origem, destino e forma dentro das tolerancias configuradas | Secoes 3.2 e 6, apoio visual a volume/utilizacao | `exports.py::tracks_geojson` |
| LoWC | `Sh(t) < Smin_h and Sv(t) < Smin_v` | Secao 4.2.1, Eq. 4.1 | `metrics.py::detect_lowc_events` |
| LoWC por hora de voo | `N_lowc / sum(H_f)` | Secao 3.3, Eq. 3.2 | `metrics.py::_safety_summary` |
| LoWC por 100 operacoes | `N_lowc / N_voos * 100` | Secao 3.3 | `metrics.py::_safety_summary` |
| LoWC por 1000 km | `N_lowc / km_voados * 1000` | Secao 3.3 | `metrics.py::_safety_summary` |
| Severidade | `sev_ij = min_t(Sh/Smin_h, Sv/Smin_v)` | Secao 4.2.3, Eq. 4.5 | `metrics.py::_summarize_lowc_event` |
| Tempo abaixo do limiar | `amostras consecutivas em LoWC * conflict_sample_seconds` | Secao 4.2.3 | `metrics.py::_summarize_lowc_event` |
| NMAC | `Sh(t) < S_NMAC_h and Sv(t) < S_NMAC_v` | Secao 4.2.2 | `metrics.py::_safety_summary` |
| MAC esperado | `E[MAC] = N_NMAC * P(MAC\|NMAC)` | Secao 4.2.2, Eq. 4.2-4.4 | `metrics.py::_safety_summary` |
| Tempo medio de voo | `mean(max(simt_f) - min(simt_f))` | Secao 4.3.4 | `metrics.py::efficiency_metrics` |
| Distancia media | `mean(max(distflown_f))` | Secao 4.3.4 | `metrics.py::efficiency_metrics` |
| Eficiencia horizontal | `d_gc / d_real * 100` | Secoes 4.1 e 4.3.6 | `metrics.py::efficiency_metrics` |

O dashboard tambem exporta esta matriz por meio de `metric_catalog.py` e mostra a tabela na propria pagina.

## 7. Metricas Ainda Indisponiveis

O `STATELOG` atual nao contem todos os campos minimos citados no PDF. Por isso, as metricas abaixo ficam documentadas como indisponiveis ate que novos dados sejam fornecidos:

- atraso em solo: requer `S_f`, `R_f` e/ou `D_f`;
- atraso em voo: requer tempo nominal `T_f`;
- atraso total e pontualidade: requer horarios planejados, autorizados e reais;
- conformidade com trajetoria planejada: requer rota planejada ou `dplan_f`;
- tempo ate conflito: requer tempo de deteccao `tdet`;
- carga de deconfliction: requer comandos de velocidade, proa ou altitude;
- razao de risco entre cenarios: requer pareamento explicito entre baseline e mitigacao.

## 8. Comparacao Entre Logs

Quando ha dois ou mais logs:

- os cards superiores mostram medias das metricas principais;
- a tabela `Cenarios processados` mostra cada log e uma linha `Media`;
- o seletor `Cenario no mapa` troca mapa e graficos para o log escolhido;

As medias incluem aeronaves, pico simultaneo, duracao, tempo medio, distancia media, eficiencia, LoWC, NMAC, taxas normalizadas e severidade.

Todo processamento dos `STATELOGs` acontece em Python durante a execucao de `generate_dashboard.py`. O JavaScript da pagina apenas apresenta os arquivos gerados.

## 9. Como As Trajetorias Sao Agrupadas

O `STATELOG` contem a trajetoria efetivamente executada, nao a REH planejada. O processamento:

1. separa possiveis instancias de voo do mesmo `id` por intervalo de tempo, reinicio de `distflown` ou salto geografico;
2. representa cada instancia por pontos igualmente espacados pela distancia percorrida;
3. compara origem, destino e distancia media entre os pontos das formas;
4. agrupa instancias dentro das tolerancias configuradas;
5. usa a quantidade de instancias no grupo como frequencia/volume.

As cores do mapa representam volume relativo ao grupo mais frequente:

- azul: menor volume;
- amarelo: volume intermediario;
- vermelho: maior volume.

Esse agrupamento e uma aproximacao configuravel baseada nas trajetorias observadas. Ele nao identifica formalmente uma REH.

## 10. Testes

Rode os testes unitarios com:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## 11. Publicacao No GitHub Pages

Configure o GitHub Pages para publicar a pasta:

```text
docs/
```

Depois de gerar novamente o dashboard, faca commit dos arquivos de `docs/` e envie para o GitHub. Os logs brutos continuam apenas em `data/`.
