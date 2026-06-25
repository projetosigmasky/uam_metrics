# UAM KPI/KPA Dashboard

Dashboard estatico para analisar logs `STATELOG` do BlueSky em cenarios de corredor aereo urbano na RMSP.

Este repositorio implementa, em codigo, metricas de seguranca e eficiencia descritas no estudo `Projeto_SIGMA_Sky_Produto_3_Versao_1.pdf`. A saida principal e a pasta `docs/`, pronta para GitHub Pages.

## 1. Preparar Os Logs

Coloque os arquivos de entrada em:

```text
data/
  logs/
    bimtra_top1_2025_11_09_mvp.log
    bimtra_top1_2025_11_09_off.log
  scenarios/
    bimtra_top1_2025_11_09_mvp.scn
    bimtra_top1_2025_11_09_off.scn
```

A pasta `data/` fica fora do Git pelo `.gitignore`, entao os logs brutos nao entram no GitHub.

O formato esperado pelo parser e:

```text
simt,id,lat,lon,distflown,alt,cas,tas,gs
```

## 2. Gerar O Dashboard

Para processar todos os logs em `data/logs/`:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py
```

Para processar logs especificos:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py .\data\logs\bimtra_top1_2025_11_09_mvp.log
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
nmac_horizontal_m = 150.0
mac_beta = 5.038e-3
mac_probability_given_nmac = 0.005
tls_target_per_flight_hour = 9.4e-6
tls_epsilon = 1e-15
conflict_sample_seconds = 10
track_sample_stride = 20
trajectory_shape_points = 12
trajectory_cluster_distance_m = 1200.0
trajectory_endpoint_tolerance_m = 2500.0
conformity_tolerance_m = 250.0
capacity_window_seconds = 3600
capacity_reference_percentile = 0.95
heatmap_sample_stride = 10
```

Alguns parametros podem ser alterados pela linha de comando:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py --lowc-horizontal-m 600 --nmac-horizontal-m 150
.\.venv\Scripts\python.exe generate_dashboard.py --conformity-tolerance-m 250
```

## 4. Saida Gerada

O gerador publica em `docs/`:

- `docs/index.html`: dashboard principal.
- `docs/assets/data_bundle.js`: pacote de dados usado pela pagina.
- `docs/assets/data/dashboard.json`: metricas agregadas ou medias.
- `docs/assets/data/comparison.json`: tabela comparativa.
- `docs/assets/data/runs/*.json`: dados por log processado.
- `docs/assets/data/tracks.geojson`: trajetorias executadas do primeiro log, com grupos e frequencias.
- `docs/assets/data/planned_routes.geojson`: trajetorias planejadas extraidas dos cenarios BlueSky.
- `docs/assets/data/conflicts.geojson`: eventos LoWC/NMAC do primeiro log.
- `docs/assets/data/heatmap_points.json`: pontos de densidade do primeiro log.
- `docs/assets/charts/*.png`: graficos estaticos por log.

## 5. Responsabilidades Dos Modulos

| Arquivo | Responsabilidade |
|---|---|
| `generate_dashboard.py` | Orquestra leitura, metricas, graficos, JSON/GeoJSON e copia `web/` para `docs/`. |
| `src/uam_dashboard/config.py` | Centraliza colunas, unidades, limiares horizontais LoWC/NMAC, amostragem e coeficientes MAC. |
| `src/uam_dashboard/log_parser.py` | Le o `STATELOG`, converte campos numericos e ordena os registros. |
| `src/uam_dashboard/experiment.py` | Classifica automaticamente dia, MVP, distúrbio e variante pela nomenclatura. |
| `src/uam_dashboard/scenario_parser.py` | Extrai origens e waypoints planejados dos arquivos BlueSky `.scn`. |
| `src/uam_dashboard/metrics.py` | Implementa formulas de seguranca, eficiencia, exposicao e severidade. |
| `src/uam_dashboard/metric_catalog.py` | Mantem a rastreabilidade entre metrica, formula, PDF, codigo e status. |
| `src/uam_dashboard/exports.py` | Agrupa trajetorias semelhantes e converte trajetorias planejadas, executadas e eventos para GeoJSON. |
| `src/uam_dashboard/plots.py` | Gera PNGs de aeronaves simultaneas, separacao, altitude, distancia e severidade. |
| `web/index.html` | Estrutura estatica da pagina. |
| `web/assets/dashboard.js` | Renderiza os dados, mapas, comparacoes e metricas previamente processados pelo Python. |
| `web/assets/dashboard.css` | Layout visual e regras criticas do Leaflet. |

## 6. Rastreabilidade Das Formulas

| Metrica | Formula implementada | Referencia no PDF | Codigo |
|---|---|---|---|
| Frequencia de trajetorias | Contagem de instancias com origem, destino e forma dentro das tolerancias configuradas | Secoes 3.2 e 6, apoio visual a volume/utilizacao | `exports.py::tracks_geojson` |
| LoWC | `Sh(t) < Smin_h` | Produto 3 v1, criterio simplificado para separacao horizontal | `metrics.py::detect_lowc_events` |
| LoWC por hora de voo | `N_lowc / sum(H_f)` | Secao 3.3, Eq. 3.2 | `metrics.py::_safety_summary` |
| LoWC por 100 operacoes | `N_lowc / N_voos * 100` | Secao 3.3 | `metrics.py::_safety_summary` |
| LoWC por 1000 km | `N_lowc / km_voados * 1000` | Secao 3.3 | `metrics.py::_safety_summary` |
| Severidade | `sev_ij = min_t(Sh/Smin_h)` | Produto 3 v1, criterio horizontal simplificado | `metrics.py::_summarize_lowc_event` |
| Tempo abaixo do limiar | `amostras consecutivas em LoWC * conflict_sample_seconds` | Secao 4.2.3 | `metrics.py::_summarize_lowc_event` |
| NMAC | `Sh(t) < S_NMAC_h` | Produto 3 v1, criterio horizontal simplificado | `metrics.py::_safety_summary` |
| MAC esperado | `MAC = 5.038e-3 * 0.005 * N_NMAC`; `MAC_100k = MAC / H_voo * 100000` | Produto 3 v1, seguranca | `metrics.py::_safety_summary` |
| Margem TLS | `M_TLS = TLS / (lambda_MAC_obs + epsilon)` | Produto 3 v1, Eq. 4.12 | `metrics.py::_safety_summary` |
| Tempo medio de voo | `mean(max(simt_f) - min(simt_f))` | Secao 4.3.4 | `metrics.py::efficiency_metrics` |
| Distancia media | `mean(max(distflown_f))` | Secao 4.3.4 | `metrics.py::efficiency_metrics` |
| Ineficiencia horizontal executada | `(d_real - d_gc) / d_gc * 100` | Secao 4.3.6, Eq. 4.19 | `metrics.py::efficiency_metrics` |
| Conformidade de trajetoria | `TC_f = (d_real - d_plan) / d_plan`; `ED_f = d_real - d_plan` | Secao 4.3.5, Eq. 4.16-4.17 | `metrics.py::trajectory_conformity` |
| Aderencia espacial a REH | Percentual de amostras dentro da tolerancia configurada | Diagnostico complementar | `metrics.py::trajectory_conformity` |
| Atraso em solo | `GD_f = max(0, R_f - S_f)` | Secao 4.3.1 | `scenario_parser.py::ground_delay_metrics` |
| Atraso no ar | `AD_f = max(0, (A_f - D_f) - T_f)` | Produto 3 v1, Eq. 4.14 | `metrics.py::airborne_delay_metrics` |
| Atraso total | `TD_f = GD_f + AD_f` | Produto 3 v1, eficiencia | `metrics.py::total_delay_metrics` |
| Densidade de trafego aereo | `ATD_dt = N_simultaneo_dt / A` | Produto 3 v1, Eq. 4.23 | `capacity.py::capacity_metrics` |
| Throughput por recurso | `THR_r,dt = N_r,dt / \|dt\|` | Produto 3 v1, Eq. 4.24 | `capacity.py::_resource_throughput` |
| Utilizacao de recurso | `U_r,dt = N_r,dt / C_r,dt`; `C_r,dt = P95(THR_r,dt)` | Produto 3 v1, Eq. 4.25 | `capacity.py::_resource_throughput` |
| Razao de risco | `RR_s = MAC_100k_s / MAC_100k_ref` | Produto 3 v1, Eq. 4.10 | `generate_dashboard.py::comparison_payload` |

O dashboard tambem exporta esta matriz por meio de `metric_catalog.py` e mostra a tabela na propria pagina.

## 7. Metricas Ainda Indisponiveis

O `STATELOG` atual nao contem todos os campos minimos citados no PDF. Por isso, as metricas abaixo ficam documentadas como indisponiveis ate que novos dados sejam fornecidos:

- pontualidade operacional: requer horarios planejados, autorizados e reais de chegada;
- tempo ate conflito: requer tempo de deteccao `tdet`;
- carga de deconfliction: requer comandos de velocidade, proa ou altitude;

## 8. Comparacao Entre Logs

Os nomes `bimtra_topN_DATA_[disturbed_seedX_]mvp|off.log` sao classificados automaticamente.
Para cada dia, o dashboard compara MVP ligado/desligado, com e sem disturbios.

A tabela diaria apresenta metricas de seguranca e eficiencia, diferencas contra o cenario OFF
pareado e a razao de risco da Eq. 4.10. A referencia de risco e o cenario sem intervencao e sem perturbacao (`OFF / sem disturbios`). Os seletores `Dia comparado` e `Cenario no mapa` controlam
a tabela, os cards, o mapa e os graficos exibidos.

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

## 10. REH Planejada E Conformidade

Coloque os arquivos BlueSky `.scn` em `data/scenarios/`. O gerador associa automaticamente cada
log ao cenario de mesmo nome-base.

A camada `REH planejada` conecta a origem e os waypoints definidos por `CRE`, `ADDWPT` e `DEFWPT`.
A conformidade formal segue as Eq. 4.16-4.17 do PDF, comparando distancia executada e planejada.
Separadamente, a aderencia espacial informa o percentual de amostras executadas cuja menor
distancia horizontal ate a REH e menor ou igual a `conformity_tolerance_m`.

As instancias planejadas e executadas sao associadas por matricula e horario de criacao mais
proximo. Isso evita deslocar a sequencia quando uma matricula e reutilizada e alguma instanciacao
planejada nao aparece no `STATELOG`.

## 11. Diagnostico Da Severidade LoWC

Por aderencia ao Produto 3 v1, nos cenarios em que as aeronaves operam no mesmo nivel ou em corredores
com separacao vertical fixa, o dashboard usa o criterio simplificado horizontal. Assim, LoWC, NMAC e
severidade sao calculados apenas por `Sh`.

Um evento pode ter severidade proxima de zero quando a distancia horizontal entre duas aeronaves fica
muito pequena em relacao ao limiar `Smin_h`. NMAC e identificado quando essa distancia tambem cruza o
limiar horizontal mais restritivo `S_NMAC_h`.

## 12. Capacidade, Densidade E Utilizacao

A densidade formal usa corredores derivados da REH planejada. A largura do corredor e a mesma tolerancia
usada na aderencia espacial (`conformity_tolerance_m`). A area `A` da Eq. 4.23 e estimada como a area
dos corredores planejados, aproximados por capsulas ao redor das polilinhas da REH.

O throughput da Eq. 4.24 e calculado em janelas de 1 hora para tres tipos de recurso:

- pares origem-destino observados;
- grupos de trajetoria executada;
- REHs planejadas associadas aos voos.

Como ainda nao ha capacidade declarada externa, a utilizacao da Eq. 4.25 usa uma referencia nominal
interna: `C_r,dt = P95(THR_r,dt)` por tipo de recurso. Assim, a utilizacao informa quao proximo o recurso
ficou do envelope operacional observado no proprio conjunto de simulacoes.

## 13. Testes

Rode os testes unitarios com:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## 14. Publicacao No GitHub Pages

Configure o GitHub Pages para publicar a pasta:

```text
docs/
```

Depois de gerar novamente o dashboard, faca commit dos arquivos de `docs/` e envie para o GitHub. Os logs brutos continuam apenas em `data/`.
