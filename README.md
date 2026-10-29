# UAM KPI/KPA Dashboard

Dashboard estatico para analisar logs `STATELOG` do BlueSky em cenarios de corredor aereo urbano na RMSP.

Este repositorio vincula as metricas ao `Produto3_vfinal_ProjetoSIGMASky.pdf` (Produto 3, versao 2.0, 31/07/2026). A saida principal e a pasta `docs/`, pronta para GitHub Pages. O PDF local e ignorado pelo Git; o catalogo versionado registra suas paginas e equacoes.

Contexto para novas iteracoes: [historico tecnico](ITERATION_LOG.md). Para o relatorio de referencias de 1/2 movimentos por waypoint/5 min: [figuras selecionadas, tabelas e ressalvas](reports/baseline_capacity_2026-10-20/README.md).


## Seleção dos cenários nominais — 29/10/2026

A publicação agora separa os dados em fragmentos e carrega os detalhes por cenário. As auditorias brutas e os JSONs completos duplicados permanecem no servidor, fora do Git. Para converter resultados já calculados, use `.venv/bin/python prepare_publication.py`, sem repetir o processamento. Veja [formato de publicação e recuperação de push recusado por arquivos grandes](PUBLICACAO.md).

O padrão de `run_config.json` agora é `run_name: "auto"`: busca em `~/runs` as **36 variantes nominais** do catálogo canônico de `rmsp-uam-simulations`, selecionando a RUN concluída mais recente por código (ordem dos nomes datados do orquestrador). Cada variante exige 50 STATELOGs, índices 1–50, SCNs correspondentes e geometria validada. As réplicas de uma variante nunca são misturadas entre RUNs. Runs incompletas, pilotos e associações inválidas são descartados com aviso; variantes sem resultados completos são informadas. `require_all_scenarios: true` exige as 36 antes de gerar qualquer relatório. A seleção validada é fixada em `run_config.local.json` (`scenario_runs`), garantindo que dashboard e ranking usem as mesmas RUNs mesmo que outras simulações terminem durante o processamento. Reexecute com o config padrão para fazer nova descoberta; use `--config run_config.local.json` para reproduzir a seleção fixada.

No Lessonia, após atualizar este clone:

```bash
cd ~/post-processing
.venv/bin/python generate_reports.py --config run_config.json --workers 25
```

Para outra raiz de resultados, acrescente `--runs-root /caminho/dos/runs`. Para fixar uma RUN, use `--run-id ID`; para restringir os códigos, acrescente, por exemplo, `--scenario-codes C1.1 C1.2 C2.1 C2.2`. Overrides são validados antes de salvar `run_config.local.json`. A busca lê resultados já executados no servidor; não inicia simulações nem faz transferência SSH.

O cabeçalho do site oferece cinco seletores encadeados: **tipo de corredor, desconflito, condição operacional, vertiportos e tempo de separação**. As opções dependem dos resultados disponíveis no grupo selecionado. Combinações ausentes ficam desabilitadas; o código e a quantidade de réplicas aparecem abaixo dos filtros. O tempo não se aplica aos baselines e ao DCB. “Perturbado” permanece indisponível enquanto só houver resultados nominais. Os filtros se reorganizam em telas menores. `web/` e a interface publicada em `docs/` foram atualizados; os dados numéricos existentes são preservados até reprocessamento no servidor.

`data/scenario_catalog.json` é o snapshot das 44 linhas (36 nominais e 8 off-nominal) de `rmsp-uam-simulations/data/scenarios/nominal_catalog_20261027.xlsx`, com SHA-256 da fonte. A planilha original estava bloqueada para leitura; foi usada a cópia versionada documentada pelo gerador. Os nomes Micro Chen e Micro Moolchandani correspondem aos algoritmos do gerador. Códigos micro atuais seguem `C4/C8.algoritmo.estágio.perfil`: estágio 1 = 6 vertiportos; estágio 2 = 12; perfis 1/2/3 = 11/23/38 segundos e LOWC horizontal 0,3/0,6/1 NM. O pós-processamento aplica esses limiares por cenário. Códigos micro históricos sem perfil mantêm o tempo desconhecido e não são substituídos pelos novos.

## Dados publicados anteriormente — 21/10/2026

O pacote publicado anterior contém **C1.1, C1.2, C2.1 e C2.2**, com **50 réplicas de cada cenário** na RUN `20261015_112401_6cddab52`. `run_config.json` associa o estágio 1 ao CSV de 6 vertiportos e o estágio 2 ao CSV validado de 12 vertiportos. A seleção exige réplicas 1–50, pareamento único com SCNs e valida a geometria dos cenários dedicados antes de publicar.

Após enviar estas alterações ao remoto, no Lessonia:

```bash
cd ~/post-processing
git pull --ff-only
.venv/bin/python generate_reports.py --config run_config.json --workers 25
```

O comando regenera o dashboard completo a partir dos STATELOGs e o ranking por cenário. Para outra RUN concluída, use `--run-id NOVA_RUN --runs-root ~/runs`; a seleção validada será salva em `run_config.local.json`. A calibração nativa via `--baseline-manifest` continua sendo um fluxo independente: **ela não recalcula os demais KPIs do dashboard**.

O heatmap reúne **todos os registros de posição de todas as réplicas**, em células de `0,001°` (aproximadamente 100 m). Sua intensidade é a média de registros por célula e réplica, com uma escala comum entre cenários. Isso representa ocupação observada; não conta aeronaves únicas nem movimentos por janela. Comparações quantitativas dessa intensidade pressupõem cadência e cobertura compatíveis dos logs. `density` registra a contagem de réplicas, registros, tamanho da célula e escala; os limites do mapa abrangem todas as réplicas.

Os cards usam médias entre réplicas, com contagem real e cobertura válida no detalhamento. Os seis gráficos de Visão Geral, Segurança e Eficiência passam a usar agregação por réplica no protocolo `analysis_schema_version=1`. Mapa de eventos, tabela e reprodução 3D são ilustrações de uma réplica identificada por índice e arquivo. O 3D foi restaurado em Segurança; os timestamps da tabela posicionam sua reprodução. Trajetórias e planejamento no mapa 2D continuam em observação. A página pública de calibração continua retirada e seus dados e relatórios estão preservados. Pacotes antigos mantêm seus KPIs e heatmaps, mas os gráficos representativos são suprimidos até reprocessamento; nenhuma curva é reconstruída da média final.

O pacote numérico publicado neste clone já contém os quatro cenários e 200 réplicas da RUN selecionada, incluindo 40.732.394 registros no heatmap. Ele usa o formato anterior, sem os resumos individuais necessários aos novos gráficos e ICs. Cards, heatmap e dados ilustrativos são preservados; as novas distribuições e a estabilidade ficam indisponíveis até o reprocessamento dos STATELOGs reais. Nenhum resultado legado C1/C2 é renomeado como os quatro cenários atuais. Depois de processar no Lessonia, traga os arquivos atualizados de `docs/` para o fluxo de publicação habitual.

A união visual UAM e as junções geométricas 3D estão documentadas em [auditoria VP-005–VP-006](reports/uam_geometry_2026-10-21/README.md). As rotas originais e a seleção analítica de recursos de capacidade permanecem preservadas. O parser aceita os demais identificadores da planilha; `C5/C6/C9/C10` exigem geometria explicitamente selecionada, pois seus sufixos identificam algoritmos, e não automaticamente o número de vertiportos.

## Calibracao dos quatro baselines nominais

O modulo de calibracao compara **C1.1, C1.2, C2.1 e C2.2**, separadamente, em janelas de **300, 900 e 3600 segundos**. C1 usa arquitetura compartilhada, C2 usa corredores dedicados; o sufixo `.1` corresponde a 6 vertiportos e `.2` a 12. Este fluxo e independente do dashboard completo: nao reutiliza automaticamente suas metricas ou geometrias. As instrucoes C1/C2 posteriores sao historicas.

No Lessonia, mantenha acessiveis os **JSONs originais da geracao nominal**, com `product2.resource_manifest`, e os arquivos **WPPASS** dos runs concluidos. Somente SCN ou STATELOG nao substituem esse catalogo de recursos fisicos. Os eventos sao conferidos por aeronave, recurso e ocorrencia na rota; eventos ausentes, duplicados ou divergentes interrompem a geracao. A descoberta recusa arquivos ambiguos e exige as 50 replicas de cada baseline, mesmo quando estao distribuidas em runs diferentes.

```bash
cd ~/post-processing
.venv/bin/python prepare_baseline_manifest.py \
  --scenario-root ~/rmsp/scenarios/product2/nominal_20261013 \
  --run-dirs ~/runs/RUN_CONCLUIDO \
  --output baseline_manifest.local.json

.venv/bin/python generate_reports.py \
  --baseline-manifest baseline_manifest.local.json \
  --audit-dir calibration_audit \
  --workers 25
```

Ajuste o caminho do clone e o identificador do run. Se os quatro baselines estiverem em runs distintos, passe todos os diretorios depois de `--run-dirs`. Logs de outras variantes sao ignorados na descoberta; os runs selecionados precisam estar concluidos sem erro. Nao ha acesso remoto ou disparo de simulacoes nesses comandos. A calibracao tambem pode ser executada diretamente por `generate_baseline_calibration.py --manifest baseline_manifest.local.json --output-dir docs --workers 25`.

`--workers 25` distribui os waypoints fisicos dos quatro cenarios em ate 25 **processos**, aproveitando CPUs diferentes no Lessonia. Cada tarefa calcula as tres janelas, ambas as politicas de zeros e os bootstraps de um waypoint. Os sorteios sao preparados uma unica vez com a mesma semente e a saida e ordenada, preservando os resultados do modo sequencial. Cada processo numerico usa um thread BLAS/OpenMP para evitar multiplicacao de threads. Leitura/validacao dos logs, graficos e gravacao dos arquivos permanecem sequenciais. O progresso informa o numero efetivo de processos e os waypoints concluidos.

A prioridade e `--workers` > campo `workers` na raiz do manifesto > **1 processo**. O manifesto e independente de `dashboard_workers`/`ranking_workers` do fluxo legado. Para persistir a escolha, acrescente `"workers": 25` ao manifesto. Para comparar ou diagnosticar, use `--workers 1`. A quantidade efetiva e limitada ao numero de waypoints; valores zero ou negativos sao rejeitados.

A saída de calibração permanece nos CSVs, JSON e PNGs de `docs/assets/data/baseline_calibration/`, para auditoria e relatório. Desde 21/10/2026, não é exibida no dashboard e `docs/calibration.html` não é publicado.

### Definicoes e comparabilidade

- Recurso: ponto fisico/pista/altitude do manifesto de simulacao, com `capacity_key=physical_point_track`, elegivel e nomeado. Nomes iguais nao somam capacidades, e esse universo nao e o filtro legado de juncoes de grau >=3.
- Tempo: origem em 0 s, intervalos semiabertos `[k*w,(k+1)*w)`, somente janelas inteiramente observadas. No modo nativo, o intervalo padrao e a duracao declarada da simulacao concluida. Um intervalo menor pode ser informado por replica em `observation_start_s`/`observation_end_s`. A cobertura registra os segundos parciais e passagens excluidos.
- Unidades: contagem por janela **e** taxa equivalente em operacoes/h. Uma operacao corresponde a 12 op/h na janela de 5 min, 4 op/h em 15 min e 1 op/h em 60 min. As comparacoes entre escalas usam operacoes/h.
- Referencia empirica: P95 `higher` das janelas reunidas das replicas, calculado de novo para cada tamanho de janela. Nao e a media dos P95 individuais nem um limite operacional demonstrado.
- Zeros: “somente positivas” reproduz a selecao configurada para calibracao no gerador; “todas” inclui ociosidade. Waypoints sem uso observado ficam identificados separadamente, sem atribuir capacidade zero ou aplicar piso artificial de uma operacao. Falta de janela completa em alguma replica invalida a estimativa final para aquela escala.
- Rede: o histograma conta cada waypoint uma vez por cenario/janela. Nao ha soma de capacidades dos waypoints para estimar capacidade da rede.

### Estabilidade e incerteza

O bootstrap usa **replicas inteiras como blocos**, preservando a dependencia temporal das janelas de cada simulacao. Calcula IC percentil para o P95 reunido e a media das janelas reunidas, alem das curvas acumuladas. As sementes C1/C2 do mesmo estagio sao verificadas, mas nao se publica um efeito pareado entre recursos de identidades fisicas distintas.

Padroes: 95% de confianca, minimo de 30 replicas, tolerancia relativa de 5%, absoluta de 0 op/h, 15 avaliacoes consecutivas e 1.000 reamostragens com semente 1729. A primeira confirmacao possivel e em 44 replicas. O resultado final exige que a sequencia de 15 confirmacoes se mantenha ate a ultima replica. Media e P95 possuem resultados de estabilidade independentes. Sao criterios de precisao empirica, nao prova de seguranca nem garantia de que 50 replicas bastam para todos os KPIs. Percentis discretos podem produzir intervalos degenerados; poucos eventos ou reamostragens sem uso nao devem ser interpretados como evidencia de capacidade maxima.

Ajustes opcionais no manifesto:

```json
"stability": {
  "minimum_replications": 30,
  "confirmation_window": 15,
  "confidence_level": 0.95,
  "relative_tolerance": 0.05,
  "absolute_tolerance_per_hour": 0.0,
  "bootstrap_samples": 1000,
  "seed": 1729
}
```

### Auditoria e alternativa geometrica

`docs/assets/data/baseline_calibration/` recebe 16 PNGs de histogramas/distribuicoes acumuladas, `comparison.csv`, `replica_metrics.csv`, `convergence.csv` e `calibration.json` com cobertura, parametros e hashes das fontes. `docs/assets/baseline_calibration_data.js` permite visualizar os resultados sem fetch. Os CSVs opcionais de passagens e janelas positivas ficam em `calibration_audit/`, fora da publicacao e ignorados pelo Git; zeros omitidos desse CSV esparso sao reconstruiveis pela cobertura. As curvas e coberturas do JSON usam linhas compactas com os campos descritos em `trace_columns` e `coverage_columns`; os CSVs mantem cabecalhos explicitos. Os logs brutos permanecem no servidor.

Se nao houver WPPASS, edite explicitamente o manifesto: `allow_geometric_estimate: true` na raiz e `passage_source: "geometric"` com `statelog` em cada replica. Continue fornecendo o JSON original e o run concluido. O estimador usa cilindros de 250 m (configuraveis por `capture_radius_m`), competicao entre posicoes e interpolacao 3D, limitado a cobertura efetiva do STATELOG. Nao mistura fontes nativas e geometricas dentro de um mesmo cenario e nao faz fallback silencioso. Os resultados ficam identificados como estimativa geometrica.

Os dados e figuras de calibração podem ser mantidos para auditoria. A atualização do dashboard via `generate_reports.py --config ...` preserva esses arquivos, sem carregar sua interface na página pública.

## Fluxo atual no Lessonia

Os novos runs ficam em `~/runs`. Atualize o código do orquestrador e do gerador antes de executar. O gerador exporta um contrato headless e os plugins UAMLOG/WPPASS; os logs só entram neste projeto após conclusão sem erros.

```bash
cd ~/post-processing
git pull --ff-only
.venv/bin/python generate_reports.py --run-id RUN_ID_CONCLUIDO --runs-root ~/runs
```

O comando valida o resumo, o estado do executor e os pareamentos P100/OFF antes de alterar os relatórios; salva a seleção em `run_config.local.json` (ignorado pelo Git). Runs ativos, pilotos incompletos e execuções com erro são rejeitados. A validação de passagens nativas pertence ao orquestrador; o dashboard atual continua calculando suas métricas a partir dos STATELOGs. A seção de preparação histórica abaixo descreve o run antigo, não o caminho padrão atual.

## 1. Preparar Os Logs

Os STATELOGs desta fase estao no Lessonia, na execucao P100 do orquestrador:

```text
bluesky-orchestrator/runs/20260924_104519_aba5878d/
  output/C1/ e output/C2/      # 50 STATELOGs por cenario
  scenario/C1/ e scenario/C2/  # planejamento .scn de cada replica
```

O `data/scenarios/` versionado contem cenarios P95 historicos e nao e entrada desta fase. Os logs P100 usam todos os outliers dos bins horarios como referencia da simulacao. Somente `data/logs/` e ignorada pelo Git; o CSV dos corredores em `data/` e versionado.

O formato esperado pelo parser e:

```text
simt,id,lat,lon,distflown,alt,hdg,trk,cas,tas,gs,vs
```

## 2. Gerar O Dashboard

Execute o lote P100 com `run_config.json`, conforme as instrucoes abaixo. O gerador rejeita entradas Produto 2 de demanda diferente de P100 antes de alterar `docs/`.

As réplicas de cada cenário C1.1/C1.2/C2.1/C2.2 são agrupadas pelo identificador do cenario, demanda e modo (`off`/`mvp`). Cada valor numerico publicado para o cenario e a media dos resultados calculados separadamente por replica, inclusive contagens, totais e picos. O P95 que aparece em algumas metricas e um percentil **dos resultados simulados**, nao um perfil de demanda P95. Mapa de eventos, tabela e visualização 3D usam a primeira réplica por índice como ilustração; os seis gráficos usam resumos de todas as réplicas. Índices são ordenados antes de agregar, independentemente da conclusão dos workers. O seletor mostra um item por cenario, com a quantidade de replicas no nome. Para evitar um pacote excessivo, as trajetorias das demais replicas nao entram em `docs/`.

Nos logs do orquestrador, o gerador reconhece a demanda P100, o cenario e a replica (`r022`, por exemplo), associando cada STATELOG ao respectivo `.scn`. Se o nome for opaco, pode usar a pasta pai `output/C1` ou `output/C2`, mas somente quando houver um unico `.scn` compativel. A geracao para estas pastas para antes de modificar `docs/` caso nao consiga associar um planejamento sem ambiguidade.

### Executar no Lessonia e publicar somente os resultados

O arquivo `run_config.json` guarda a raiz das execucoes, o nome da RUN, o numero esperado de replicas e `dashboard_workers`/`ranking_workers`. Para processar outra RUN equivalente, altere apenas `run_name`. Os workers usam **processos** para aproveitar CPUs diferentes; o dashboard e o ranking rodam em sequencia, cada um com 25 processos por padrao no Lessonia de 32 CPUs. O gerador localiza automaticamente `output/C1`, `output/C2`, `scenario/C1` e `scenario/C2` dentro dessa RUN. Cada log e pareado a seu `.scn` P100. O XML oficial da REH esta versionado em `data/xml/CV_REH_XP_SAO_PAULO.xml`; nao e necessario informar um caminho no comando. O `data/scenarios/` versionado contem P95 historico e **nao** e usado com os logs P100.

Apos publicar as alteracoes de codigo, execute no Lessonia:

```bash
cd ~/post-processing
git pull --ff-only
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python generate_reports.py
```

`generate_reports.py` valida as 50 replicas C1 e 50 C2, os 100 pareamentos STATELOG/SCN e a demanda P100 antes de calcular. Ele gera o dashboard e o ranking de waypoints em `docs/`. O ranking e calculado pela media do throughput de cada replica, separadamente para C1 e C2, e aparece no painel de capacidade.

Antes de publicar, confira as contagens por cenario e o tamanho dos arquivos. O formato atual divide os dados sem reduzir a resolução das camadas. Para resultados antigos, converta com `prepare_publication.py`; o procedimento de recuperação de um commit recusado está em [PUBLICACAO.md](PUBLICACAO.md). Publique apenas a saida processada:

```bash
.venv/bin/python - <<'PY'
import csv
import json
from pathlib import Path
runs = [json.loads(path.read_text()) for path in Path('docs/assets/data/runs').glob('*.json')]
counts = {run['metadata'].get('scenario_key'): run['replica_count'] for run in runs}
print('Replicas no dashboard:', counts)
assert counts == {'C1': 50, 'C2': 50}
with Path('docs/assets/data/critical_waypoints/critical_waypoints.csv').open(newline='', encoding='utf-8') as stream:
    ranking = list(csv.DictReader(stream))
print('Waypoints avaliados:', len(ranking))
assert {row['scenario'] for row in ranking} == {'C1', 'C2'}
PY
du -h docs/assets/data_bundle.js
git add docs run_config.json
git commit -m "Atualiza dashboard com medias das replicas C1 e C2"
git push
```

Depois, no computador local, execute `git pull --ff-only`. Os STATELOGs brutos permanecem no Lessonia.

## 3. Parametros E Hiperparametros

Os parametros principais ficam em `src/uam_dashboard/config.py`:

```python
flight_instance_gap_seconds = 300.0
flight_instance_reset_distance_m = 250.0
flight_instance_jump_m = 5000.0
lowc_horizontal_m = 500.0
lowc_vertical_m = 137.16
nmac_horizontal_m = 152.0
nmac_vertical_m = 30.0
mac_beta = 0.005
mac_probability_given_nmac = 5.038e-3
tls_target_per_flight_hour = 8.9e-6
tls_epsilon = 1e-15
conflict_sample_seconds = 1
visualization_3d_sample_seconds = 5
visualization_3d_ground_msl_ft = 2621.0
conflict_detection_horizon_seconds = 60.0
track_sample_stride = 20
trajectory_shape_points = 12
trajectory_cluster_distance_m = 1200.0
trajectory_endpoint_tolerance_m = 2500.0
conformity_tolerance_m = 250.0
capacity_window_seconds = 900
capacity_reference_percentile = 0.95
crossing_capture_radius_m = 250.0
heatmap_sample_stride = 10
```

Alguns parametros podem ser alterados pela linha de comando:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py --lowc-horizontal-m 600 --lowc-vertical-m 137.16
.\.venv\Scripts\python.exe generate_dashboard.py --nmac-horizontal-m 152 --nmac-vertical-m 30
.\.venv\Scripts\python.exe generate_dashboard.py --conformity-tolerance-m 250
.\.venv\Scripts\python.exe generate_dashboard.py --visualization-3d-sample-seconds 5
.\.venv\Scripts\python.exe generate_dashboard.py --visualization-3d-ground-msl-ft 2621
.\.venv\Scripts\python.exe generate_dashboard.py --crossing-capture-radius-m 250
```

## 4. Saida Gerada

O mapa 2D usa Leaflet com o basemap padrao do OpenStreetMap, sem cadastro ou chave de API. Trajetorias, corredores, eventos e densidade sao camadas desenhadas sobre esse fundo. Os tiles sao carregados pela internet de `https://tile.openstreetmap.org/{z}/{x}/{y}.png`, com atribuicao visivel aos contribuidores. O servico publico segue a [politica de uso de tiles do OpenStreetMap](https://operations.osmfoundation.org/policies/tiles/), sem garantia de disponibilidade e sem downloads em massa ou uso offline. Para visualizar o dashboard localmente, sirva a pasta `docs/` por HTTP em vez de abrir o HTML diretamente.

O gerador publica em `docs/`:

- `docs/index.html`: dashboard principal.
- `docs/assets/data_bundle.js`: índice e resumos dos cenários; os detalhes são carregados de `docs/assets/run_data/` conforme a seleção.
- `docs/assets/data/dashboard.json`: metricas agregadas ou medias.
- `docs/assets/data/comparison.json`: tabela comparativa.
- `docs/assets/data/runs/*.json`: dados por cenario, com metricas medias das replicas e uma trajetoria ilustrativa.
- `docs/assets/data/critical_waypoints/critical_waypoints.csv`: ranking C1/C2 pelo throughput medio entre replicas.
- `docs/assets/data/critical_waypoints/waypoints_by_replica.csv`: valores individuais para auditoria.
- `docs/assets/waypoint_rankings.js`: ranking exibido na secao Capacidade do dashboard.
- `docs/assets/data/tracks.geojson`: trajetorias executadas do primeiro log, com grupos e frequencias.
- `docs/assets/data/planned_routes.geojson`: trajetorias planejadas extraidas dos cenarios BlueSky.
- `docs/assets/data/conflicts.geojson`: eventos LoWC/NMAC do primeiro log.
- `docs/assets/data/heatmap_points.json`: pontos de densidade do primeiro log.
- `docs/assets/data/trajectory_3d.json`: trajetorias temporais amostradas para a visualizacao 3D.
- `docs/assets/charts/*.png`: gráficos agregados por cenário (protocolo v1).

## 5. Responsabilidades Dos Modulos

| Arquivo | Responsabilidade |
|---|---|
| `generate_dashboard.py` | Orquestra leitura, metricas, graficos, JSON/GeoJSON e copia `web/` para `docs/`. |
| `src/uam_dashboard/config.py` | Centraliza colunas, unidades, limiares 3D LoWC/NMAC, amostragem e coeficientes MAC. |
| `src/uam_dashboard/log_parser.py` | Le o `STATELOG`, converte campos numericos e ordena os registros. |
| `src/uam_dashboard/experiment.py` | Agrupa C1/C2 como variantes comparaveis do Produto 2. |
| `src/uam_dashboard/scenario_parser.py` | Extrai tipo/modelo, horario, origem e waypoints dos `.scn`. |
| `src/uam_dashboard/metrics.py` | Implementa formulas de seguranca, eficiencia, exposicao e severidade. |
| `src/uam_dashboard/metric_catalog.py` | Mantem a rastreabilidade entre metrica, formula, PDF, codigo e status. |
| `src/uam_dashboard/exports.py` | Agrupa trajetorias e exporta GeoJSON e a serie temporal compacta usada na visualizacao 3D. |
| `src/uam_dashboard/plots.py` | Gera PNGs de aeronaves simultaneas, separacao, altitude, distancia e severidade. |
| `web/index.html` | Estrutura estatica da pagina. |
| `web/assets/dashboard.js` | Renderiza os dados, mapas, comparacoes e metricas previamente processados pelo Python. |
| `web/assets/dashboard.css` | Layout visual e regras criticas do Leaflet. |

## 6. Rastreabilidade Das Formulas

O catalogo executavel em `src/uam_dashboard/metric_catalog.py` e a fonte unica da
rastreabilidade. Para cada metrica ele publica, em portugues:

- formula, referencia e ponto do codigo;
- status: implementada, parcial ou indisponivel;
- dados necessarios;
- o que o software efetivamente calcula hoje;
- melhorias, parametros a validar e entradas ainda ausentes.

O dashboard renderiza as cinco KPAs do Produto 3 final: seguranca, eficiencia,
capacidade, previsibilidade e equidade. Densidade e cruzamentos espaciais sao
identificados como diagnosticos complementares. O arquivo
`docs/assets/metric_catalog.js` atualiza a rastreabilidade sem reprocessar logs;
o painel avisa quando os numeros publicados ainda pertencem ao protocolo anterior.

## 7. Metricas Parciais Ou Indisponiveis

As lacunas completas ficam no catalogo e na tabela do dashboard. As principais sao:

- atraso no ar: requer execucao nominal pareada para cada cenario;
- atraso operacional de solo e pontualidade: requerem marcos programados,
  autorizados e reais de saida/chegada;
- capacidade pratica P95: calculada a partir do throughput observado; sua estabilidade requer varias janelas e replicas;
- MAC/TLS: requerem validacao dos limites e parametros probabilisticos.

Previsibilidade por OD, degradacao relativa off-nominal e equidade entre grupos
continuam parciais ou indisponiveis, conforme a tabela de rastreabilidade.

O diagnóstico tático de horizonte de detecção foi retirado da interface. Parâmetros legados permanecem por compatibilidade; não representam tempo observado até conflito e não entram na estabilidade dos KPIs.

## 8. Comparacao Entre Logs

Os nomes `produto2_C1_<data>_off` e `produto2_C2_<data>_off` sao agrupados
automaticamente como variantes da mesma demanda. C1 e a referencia da comparacao;
C2 representa o corredor UAM dedicado. A tabela mostra diferencas de tempo e
distancia contra C1 e a razao de risco da Eq. 3.5.

Todo processamento dos `STATELOGs` acontece em Python durante a execucao de `generate_dashboard.py`. O JavaScript da pagina apenas apresenta os arquivos gerados.

### Visualizacao 3D temporal

A pagina inclui uma representacao 3D em `canvas`, sem dependencia externa. Ela usa o mesmo seletor C1/C2 do restante do painel, mostra as trajetorias completas como contexto e anima as aeronaves com silhuetas vetoriais distintas para eVTOL e helicoptero. LoWC aparece em amarelo e NMAC em laranja no mapa 2D, no 3D e na lista temporal clicavel. A amostragem padrao e de 5 segundos; o usuario pode reproduzir, pausar, percorrer a linha do tempo, alterar a velocidade, girar, aproximar e modificar o exagero vertical. O intervalo pode ser alterado com `--visualization-3d-sample-seconds` caso seja necessario equilibrar fluidez e tamanho do pacote.

NMAC e um subconjunto de LoWC. Para evitar sobreposicao de marcadores, cada evento recebe a classe mais severa: LoWC fora de NMAC em amarelo e NMAC em laranja. Vermelho fica reservado para MAC observado. Os logs atuais nao possuem uma flag nem um timestamp de colisao; portanto, o MAC probabilistico calculado a partir de NMAC nao e desenhado artificialmente como evento vermelho.

O plano horizontal de referencia usa 2.621 pes MSL, equivalentes a 798,8808 m, configuraveis por `--visualization-3d-ground-msl-ft`. Esse plano representa uma elevacao media unica para Sao Paulo; nao substitui um modelo digital de terreno e nao altera as altitudes registradas no `STATELOG`.

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

## 10. REH Formal, Planejamento E Conformidade

O gerador associa cada STATELOG P100 ao `.scn` da mesma replica no diretorio `scenario/`
da RUN escolhida. O XML `data/xml/CV_REH_XP_SAO_PAULO.xml` e uma copia versionada da REH oficial;
todos os scripts usam essa mesma referencia por padrao. `--reh-xml` permanece disponivel para uma
substituicao explicita.

A camada `REH formal` desenha os poligonos WFS/GML do XML, incluindo a semilargura oficial de cada
trecho. A camada `Planejamento do cenario` conecta a origem e os waypoints definidos por `CRE`,
`ADDWPT` e `DEFWPT` no arquivo `.scn`.

A geometria oficial do corredor UAM dedicado desta fase fica em
`data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv`. Ela representa a rede completa
entre tres aeroportos e seis vertiportos (`VP-001` a `VP-006`), com 36 pares OD e duas trilhas
paralelas por par. O gerador a descobre automaticamente; `--uam-corridor-csv` permite informar uma
copia equivalente. Arquivos com outra quantidade de vertiportos sao rejeitados enquanto o escopo
do estudo permanecer limitado aos seis pontos UAM.
No mapa, `Corredores UAM (projeção 2D)` mostra a pegada horizontal desses 72 corredores,
com a largura do CSV. A camada usa contorno rosa tracejado e preenchimento translúcido
para contrastar com os polígonos azuis e verdes da REH. O painel informa a faixa de
altitude e a altura original de cada corredor ao clicar; a projeção não representa
seu volume vertical. `generate_uam_projection.py` atualiza o arquivo estático
`assets/uam_projection.js` diretamente do CSV.

A conformidade da trajetoria segue as Eqs. 3.13-3.14 do PDF final, comparando distancia executada e planejada.
Separadamente, a aderencia espacial informa o percentual de amostras executadas que estao dentro
de algum poligono oficial da REH. O parametro `conformity_tolerance_m` continua sendo usado apenas
no diagnostico de proximidade da linha planejada quando o XML nao esta disponivel.

As instancias planejadas e executadas sao associadas por matricula e horario de criacao mais
proximo. Isso evita deslocar a sequencia quando uma matricula e reutilizada e alguma instanciacao
planejada nao aparece no `STATELOG`.

## 11. Diagnostico Da Severidade LoWC

LoWC exige simultaneamente `Sh < Smin_h` e `Sv < Smin_v`; NMAC usa os dois
limites mais restritivos. Os padroes atuais sao 500 m/137,16 m para LoWC e
152 m/30 m para NMAC. Eles sao parametros configuraveis e permanecem
marcados como pendentes de validacao operacional.

A severidade diagnostica de cada amostra e `min(Sh/Smin_h, Sv/Smin_v)`. A severidade do
evento e o menor valor ao longo de sua duracao. O resultado tambem informa a
separacao vertical e a combinacao eVTOL-eVTOL, eVTOL-helicoptero ou
helicoptero-helicoptero.

## 12. Capacidade dos waypoints explicitamente nomeados

`critical_waypoints.py` usa somente `type=Waypoint` com nome válido no CSV UAM e
`fixo_a_nome`/`fixo_b_nome` com coordenadas explícitas no XML REH. A REH não exige grau mínimo;
os recursos UAM agora exigem **três ou mais arestas físicas distintas**, referência REH
compatível e pelo menos uma ocorrência fora de acesso terminal. Essa regra substitui
para UAM a seleção anterior de todos os waypoints nomeados.
Geometric Node, vertiportos, interpolação e cruzamentos virtuais não viram recursos de
capacidade. Cruzamentos UAM × REH permanecem como diagnóstico geométrico separado.
Os indicadores antigos de OD, trajetória e trecho são diagnósticos legados; não representam
capacidade dos waypoints nomeados.

| Exportação UAM | Rotas | Vertiportos | Nomes Waypoint | Inventário de posições | Junções elegíveis |
| --- | ---: | ---: | ---: | ---: | ---: |
| scenario_horizontal_3000ft_expanded_displaced.csv | 72 | 6 | 26 | 96 | 16 |
| new_scenario_horizontal_3000ft_displaced.csv | 210 | 12 | 35 | 177 | 28 |

O XML disponível contém 106 trechos e 91 posições de fixos explicitamente nomeados.
As cinco extremidades sem nome não entram. A geometria servida em `docs/` continua
usando **expanded**, como a projeção UAM já publicada. A cópia **new** permanece separada;
não foi associada aos logs históricos. Não há STATELOGs nem o RUN publicado neste
workspace: o ranking anterior foi retirado, os resultados novos têm status
`unavailable_raw_logs`, métricas vazias e nenhuma classificação. Outros KPAs históricos
não foram recalculados. A associação da geometria com esses logs precisa ser confirmada
na máquina de origem antes da recomputação.

### Seleção UAM ancorada na REH e exclusão de terminais

O grau é o número de vizinhos físicos exatos em arestas consecutivas não direcionadas,
com latitude, longitude, altitude e dimensões. Duplicatas de uma mesma aresta em rotas
não elevam o grau. Pontos geométricos continuam descrevendo a linha central e podem
ser vizinhos de uma junção; eles nunca se tornam recursos de capacidade. Uma correspondência
com a REH não transfere o grau nem a capacidade da REH para o UAM.

A primeira/última ocorrência de `Waypoint` após/antes de um `Airport` ou `Vertiport` é
um acesso terminal, mesmo que haja pontos geométricos entre ela e o terminal. Uma posição
é exclusivamente terminal se não aparecer em nenhum outro uso interior. `CLUBE_SIRIO`
é excluído dos recursos UAM por essa regra; o fixo REH Clube Sírio permanece no cadastro de referências, sujeito ao filtro de junções REH.
Uma posição com uso tanto interior quanto terminal pode entrar, se atender aos demais critérios.

Os nomes são comparados pela normalização já descrita abaixo e por aliases explícitos:
`AVENIDA_MORUMBI` ↔ `MORUMBI`, `VD_ANTARTICA` → `VIADUTO_ANTARTICA`,
`VD_SAO_CARLOS` → `VIADUTO_SAO_CARLOS` e `VD_GRANDE_SAO_PAULO` → `VIADUTO_GRANDE_SAO_PAULO`.
Não há casamento difuso irrestrito ou seleção somente pelo fixo geograficamente mais próximo.
No XML atual, o nome já é Avenida Morumbi, portanto a correspondência é normalizada exata.
O nome original das duas redes permanece disponível.

A associação também exige distância horizontal ≤500 m, um filtro conservador de qualidade
da referência para as posições deslocadas/paralelas. Não é tolerância de fusão, raio de captura
nem evidência de conexão entre redes. Nomes iguais fora desse limite ficam na auditoria
como associação distante; por exemplo, as duas junções Shopping Tatuapé no expanded estão
a aproximadamente 731 e 1266 m do fixo homônimo e não são aceitas automaticamente.
Esse filtro e os aliases devem ser revistos explicitamente caso a exportação seja alterada.
As posições UAM não são movidas para o fixo REH, nem agrupadas analiticamente com ele.

`assets/data/uam_node_selection_audit.geojson` lista todas as posições UAM nomeadas, grau,
vizinhos, usos interiores/terminais, referência e distância, inclusão/exclusão e seus motivos.
O mapa inclui apenas as elegíveis e o popup explica o grau e permite abrir o fixo REH associado.
GN_94/GN_95 não constam como candidatos: são `Geometric Node` na exportação.

### Geometria visual dos corredores

O deslocamento simplificado das bordas pelo vetor médio dos segmentos produzia 10 polígonos
UAM auto-intersectantes entre os 72 publicados. Foi substituído por buffer da linha central
em projeção métrica local, com semilargura `width/2`, junções e extremidades arredondadas,
união dos segmentos e preservação de eventuais furos. Shapely é uma dependência do projeto; instale/atualize `pip install -r requirements.txt` na máquina de geração.
Os pontos geométricos originais são preservados na linha central: removê-los para limpar a
seleção de capacidade deformaria o traçado. Todos os buffers dos cenários de 72 e 210 rotas
passam a ser válidos. A projeção publicada e o gerador completo usam a mesma construção;
nenhuma largura física ou waypoint de origem foi editado. Métricas históricas de tráfego
não foram recomputadas com essa correção visual.

### Identidade, níveis, nomes e visualização

UAM: identidade = rede, nome normalizado, latitude e longitude exatas da exportação,
envelope vertical (`altitude ± height/2`), altura e largura. Duplicatas em rotas no mesmo
recurso físico são eliminadas. Nenhuma aproximação por arredondamento ou proximidade é
usada. Trilhas coincidentes com os mesmos atributos representam a mesma posição física;
trilhas deslocadas e níveis/dimensões distintos permanecem separados.

REH: mantém-se o critério original de junção com três ou mais vizinhos distintos em
arestas não direcionadas, unindo extremos a seis casas decimais apenas para determinar
o grau. São 31 junções elegíveis entre 91 fixos nomeados; o cadastro completo continua
disponível como referência para UAM, sem incluir os outros fixos como recursos REH.
Identidade = rede, nome normalizado, posição explícita e conjunto dos envelopes
verticais dos trechos incidentes. Preservam-se todas as faixas, inclusive disjuntas;
não se inventa uma altitude central. Qualquer trecho incidente com altitude desconhecida
ou envelope inválido desabilita a contagem 3D dessa posição, sem fabricar zero. O mapa
mantém a localização 2D e explica a indisponibilidade.

Normalização: NFKD, remoção de acentos, maiúsculas, separadores não alfanuméricos
convertidos para `_`. `Cebolão` e `CEBOLAO` indexam o mesmo nome, com nomes originais
preservados. A rede faz parte do índice: REH e UAM não são fundidas. IDs `UAM-WP-` e
`REH-WP-` usam 20 dígitos hexadecimais de SHA256 desses atributos; a ordem das rotas não
altera os IDs. As referências de rotas/trechos e os hashes dos arquivos permitem auditoria.

**Não há consolidado analítico por nome nem soma de P95.** O índice visual por nome lista
as posições reais, sem centroides ou deslocamento de marcadores. No inventário do CSV novo, CEBOLAO tem
16 posições e PONTE_ESTAIADA tem 20; o índice no mapa informa quantas são elegíveis
para capacidade pela nova regra e quantas existem no inventário. Hover informa nome, rede, coordenadas, envelope e P95
quando disponível. Clique mostra origem/hash, rotas/trechos e links para cada posição;
recursos coincidentes em 2D também podem ser inspecionados. A tabela abre o popup no mapa.
O frontend recusa métricas cujo hash de origem ou versão do método de seleção não corresponda à geometria exibida.

### Passagem, interpolação e sobreposição

Cada STATELOG é lido em ordem de tempo. Amostras duplicadas idênticas por aeronave/tempo
não contam novamente; duplicatas conflitantes causam erro. Reutilização de identificador
abre nova instância quando há intervalo >300 s, recuo de distância >250 m ou salto
horizontal >5000 m (limiares configuráveis). Não se interpola através dessas descontinuidades.
Sem uma descontinuidade observável, reutilização de ID não pode ser inferida.

Um segmento linear entre amostras intersecta o cilindro horizontal (raio padrão 250 m)
e os envelopes verticais do recurso, em metros MSL. Isso detecta passagem mesmo sem
amostra dentro do volume; a interpolação não cria recursos. REH usa a união das faixas
válidas dos trechos; UAM usa a altura exportada, evitando a antiga esfera de 250 m que
misturava níveis. Todos os veículos observados são incluídos.

Um episódio contínuo de contato com volumes sobrepostos **da mesma rede** conta uma
passagem, atribuída à posição com menor distância horizontal ao segmento. Empates abaixo
de 1 mm são ambíguos e excluídos das operações, com contagem de ambiguidades por réplica.
Saída e reentrada contam outra passagem, inclusive em direção contrária. Contatos
separados em um segmento de amostragem são episódios diferentes. Uma passagem pode
pertencer a um recurso UAM e a um REH: são redes analisadas separadamente. O evento registra
instância, tempo interpolado de aproximação mínima, direção e número de posições competidoras.
`passage_events.jsonl` permite auditar essa atribuição.

Limites materiais: trajetórias entre amostras são aproximações lineares; curvas não
amostradas não podem ser recuperadas. Cadeias densas de volumes sobrepostos podem formar
um único episódio e reduzir contagens individuais. Um retorno que permaneça dentro do
mesmo episódio não é contado como nova passagem. Contatos já presentes na primeira
amostra ou ainda presentes na última são censurados, mas entram como contatos observados;
não demonstram necessariamente travessia completa. Estudos operacionais devem testar
sensibilidade ao raio, frequência de registro e esses casos.

### Janelas e P95 empírico

Janelas de duração configurável (padrão 900 s) começam no primeiro tempo válido do log,
com intervalos `[início,fim)`. Só janelas completas até o último tempo entram em THR/P95;
a sobra final é excluída e registrada em `excluded_partial_seconds`. Janelas completas
sem operações contribuem com zero. Eventos exatamente no último limite e eventos na
sobra não entram nas taxas, embora permaneçam no total `operations`; `full_window_operations`
registra o total usado nas taxas. Um log sem janela completa não produz média, pico ou P95.

`THR = operações × 3600 / duração_em_segundos`, em ops/h. O P95 usa interpolação linear
na posição `0,95 × (n−1)` dos valores ordenados. Por cenário/recurso, o ranking usa o P95
do conjunto de **todas as janelas completas de todas as réplicas**, peso igual por janela;
réplicas mais longas contribuem mais janelas. Não é média de P95, nem soma de P95 individuais.
A média de operações tem peso igual por réplica e a média do THR tem peso igual por janela.
O arquivo por réplica contém as taxas com zeros, P95 individual e exclusão parcial.

`capacity_reference_per_hour` é esse P95: **referência empírica de demanda/dimensionamento**,
não um limite operacional seguro demonstrado ou capacidade declarada pelo DECEA.
`capacity_declared_per_hour` permanece vazio. Ordenação: P95 decrescente, desempate por ID;
altitude ou logs insuficientes não recebem rank.

## 13. Recomposição no servidor e seleção do cenário

Configure `uam_corridor_csv` em `run_config.local.json` para o arquivo que pertence ao RUN;
o caminho relativo é resolvido contra o arquivo de configuração. Campos opcionais
`expected_vertiports` (lista dos VP-NNN esperados) e `uam_corridor_sha256` fixam o conjunto
e a versão. O parser aceita ambos os cenários, mas valida identificadores, coordenadas
finitas, dimensões positivas e IDs únicos por rota. Não troca automaticamente o CSV.

`--config` valida o RUN completo e pareamento das réplicas. A seleção de corredor também
verifica que cada waypoint intermediário planejado de eVTOL nos SCN C2 esteja a até 2 m
das linhas centrais do CSV (tolerância para arredondamento da exportação); origens e último
fixo de chegada são procedimentos terminais e ficam fora dessa checagem. C1 compartilhado
com REH não é usado para inferir o corredor dedicado. Incompatibilidade interrompe a geração
antes de alterar relatórios. A validação SCN é horizontal: o parser de planos não expõe
altitudes por waypoint, e essa limitação fica registrada. Se o SCN acrescentar procedimentos
intermediários fora do corredor, será necessário identificar esses procedimentos na origem,
sem simplesmente ampliar a tolerância. O RUN antigo em `run_config.json` não foi substituído.

```bash
.venv/bin/python generate_reports.py --config run_config.local.json --workers 4
# ou somente a nova análise de waypoints:
.venv/bin/python critical_waypoints.py --config run_config.local.json --workers 4
```

`--manifest` aceita CSV `scenario,path`; caminhos relativos são resolvidos contra o manifesto.
`--logs-root` descobre STATELOG C1/C2. Esses modos exigem `--uam-csv` e registram associação
SCN **não verificada**; são destinados a uma seleção explicitamente conferida pelo analista.
Não misture exports distintos nas réplicas de uma análise.

Para atualizar somente a geometria e retirar resultados sem recomputação:

```bash
python critical_waypoints.py --geometry-only \
  --uam-csv data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv
```

São publicados `docs/assets/candidate_nodes.js`, `waypoint_rankings.js` e
`docs/assets/data/{candidate_nodes.geojson,critical_waypoints/*}`. Os últimos contêm
CSV por cenário, CSV por réplica, GeoJSON, eventos JSONL e metadados com fontes/hashes,
regra de seleção, parâmetros, janelas e limitações. A auditoria UAM fica ao lado do GeoJSON de candidatos. `crossing_waypoints.geojson` dessa
análise fica vazio; diagnósticos geométricos usam `crossing_waypoints_3d.js` separadamente.
`generate_reports.py` gera o dashboard e o ranking e atualiza os hashes de cache dos assets.
Copie os resultados publicados e seus assets correspondentes do servidor; valores legados
não podem ser convertidos para o novo universo sem os logs brutos.

## 14. Testes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_metrics.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*waypoints.py'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_corridor_buffers.py
```

Há verificações dos dois exports, seleção de nomes/tipos, identidade estável, posições de
CEBOLAO/PONTE_ESTAIADA, reentrada e reutilização de ID, interpolação, duplicatas, competição
de volumes, níveis, zeros, janelas parciais, percentil e ausência de capacidade em cruzamentos.
A apresentação em `docs/` foi verificada no navegador com popup e índice de posições.


## Agregação por réplica e estabilidade (protocolo v1, 21/10/2026)

`src/uam_dashboard/replica_analysis.py` prepara histogramas compactos nos mesmos workers de métricas, mantendo `--workers 25`. O processo principal ordena por cenário, índice da réplica e arquivo e gera os gráficos; não carrega trajetórias de todas as réplicas no navegador. O JSON de cada cenário inclui `analysis_schema_version`, `aggregate_analysis`, `stability` e `dashboard.chart_aggregation_version`. Valores individuais completos dos KPIs e resumos originais ficam em `docs/assets/data/replica_metrics/*.json` para auditoria; o navegador recebe somente resumos e as estimativas individuais dos KPIs da estabilidade.

| Visualização | Estimando e cobertura |
| --- | --- |
| Aeronaves simultâneas | Média das contagens nos timestamps exatos do tempo de simulação; cada ponto informa seu denominador. Não interpola nem transforma timestamps ausentes, mesmo dentro da duração do log, em zero. Cadências diferentes só contribuem nos instantes efetivamente observados. A faixa é mínimo–máximo das réplicas válidas naquele instante. |
| Altitude | Classes de 25 m MSL, origem zero; média das contagens de **registros de posição**, incluindo todas as aeronaves. Não são aeronaves únicas nem percentuais. Cadência/duração diferentes alteram essas contagens: não há normalização; início/fim, timestamps observados, cadência mediana e registros por réplica são exportados em `coverage`. |
| Separação horizontal | Classes de 100 m, origem zero; percentual por réplica das amostras de pares não ordenados com separação <5.000 m, depois média desses percentuais. Réplica sem amostras é indisponível. Não são eventos. |
| Severidade LoWC | Classes de 0,05, origem zero; média das contagens de **eventos** por réplica. Inclui eventos classificados NMAC; réplica analisada sem LoWC contribui com zero em cada classe. Usa a razão mínima existente do evento, sem alterar sua definição. |
| Distância executada | Classes de 2 NM; percentual por réplica e média com peso igual. Usa instâncias de voo e diferença máximo–mínimo do odômetro, como o KPI de distância, evitando misturar reutilizações do mesmo ID. |
| Distância adicional/plano | Classes de 5 pontos percentuais, origem zero, incluindo valores negativos. Variável `(d_real−d_plan)/d_plan*100`, somente pareamentos válidos com plano de comprimento positivo. Não pareados e planos degenerados não viram zero; contagens pareadas/totais por réplica ficam na cobertura e no detalhamento. |

Classes têm largura/origem fixas em todos os cenários; classes vazias em todas as réplicas podem ser omitidas da representação compacta. Barras mostram a média, intervalos azuis mostram mínimo–máximo entre réplicas: **dispersão observada, não IC da média**. Réplicas com números diferentes de voos válidos têm peso igual nas distribuições percentuais. A contagem válida aparece em cada gráfico. O heatmap mantém todos os registros, média por célula/réplica na grade de 0,001° e escala comum; não foi alterado.

Cada aba possui um detalhamento recolhido “Estabilidade dos KPIs entre réplicas”, com cada cenário e KPI dos cards, além dos componentes dos recursos de throughput exibidos. X é a quantidade de réplicas incorporadas, na ordem do índice; Y é a média acumulada das estimativas válidas por réplica. IC de 95% por bootstrap percentil de **réplicas**, 1.000 sorteios por prefixo, seed base 1729 (`seed+n`, determinístico). Não se reamostram voos, registros ou janelas dentro de uma réplica. São necessários pelo menos 30 valores válidos, desvio máximo de um extremo do IC à média ≤5% do módulo da média e 15 prefixos consecutivos atendendo ao critério. O primeiro prefixo elegível é 30 e a primeira confirmação possível é 44, sem pressupor que o conjunto real atende ao critério. O resumo distingue início do trecho estável, ponto de confirmação e primeira confirmação histórica; só declara confirmação atual se a sequência permanece válida no final.

A calibração preservada estima P95 de janelas agrupadas e reamostra clusters de réplicas; esta análise estima a **média dos KPIs por réplica**. Não se aplica mecanicamente o estimador de P95 da calibração. A tolerância absoluta continua zero porque as unidades são diferentes entre KPIs; médias próximas de zero precisam satisfazer o mesmo critério relativo estrito. Valores constantes (inclusive contagens zero de eventos) são apresentados descritivamente, sem inferir estabilidade por IC degenerado. Indisponíveis são nulos, não zeros; não aumentam a quantidade válida e interrompem a sequência de confirmação no prefixo ausente. Severidade mínima não existe em réplicas sem eventos e é agregada apenas entre réplicas com LoWC. Taxas sem horas de voo não fornecem estimativas válidas. Configurações, área e geometria não recebem inferência estatística.

A margem TLS preserva a fórmula do card `TLS/(média das taxas MAC+epsilon)`, em vez da média das margens individuais: cada prefixo e reamostragem aplica a transformação à média da taxa, com critério sobre o intervalo transformado. Utilização de recursos preserva a razão entre a média dos picos e a média das referências P95, reamostrando numerador e denominador conjuntamente. Recursos sem uso em uma réplica concluída contribuem com zero conforme o agregador existente; um grupo de recursos indisponível fica separado. O ranking externo de waypoints continua usando o P95 das janelas completas agrupadas, conforme seus próprios metadados e CSVs, e não é reinterpretado como média de P95 individuais. Envelopes REH desconhecidos permanecem indisponíveis. Os ICs são marginais por prefixo, sem garantia de cobertura simultânea ou correção por inspeções sucessivas; o critério é um diagnóstico de precisão do conjunto. Estabilidade deste conjunto não demonstra capacidade máxima nem segurança operacional.

Segurança permanece com os limiares estritos `H<500 m e V<137,16 m` (LoWC), `H<152 m e V<30 m` (NMAC), amostragem configurada de 1 s. Amostras do mesmo par formam um evento até uma lacuna maior que `1,5*sample_seconds`. LoWC inclui NMAC; um evento é NMAC se qualquer amostra o for. Timestamp e posição representativos são os da amostra com menor razão de severidade existente (`min(H/Hlim,V/Vlim)`), e a posição é o ponto médio entre as aeronaves nessa amostra. O 3D usa sua própria cadência visual exportada (padrão 5 s); ela não muda a detecção de segurança.

Os STATELOGs das 200 réplicas da RUN não estão neste clone. Nenhum agregado ou IC real foi inventado. Para atualizar o pacote após levar este código ao Lessonia, execute no servidor:

```bash
cd ~/post-processing
git pull --ff-only
.venv/bin/python generate_reports.py --config run_config.json --workers 25
```

`--baseline-manifest` executa a calibração independente e não substitui o reprocessamento completo. Esta implementação não faz push, publicação ou execução no Lessonia.


## Hierarquia dos indicadores e revisão de rastreabilidade (29/10/2026)

O Produto III final é a referência dos KPIs. Os cartões e gráficos diretamente associados a esses indicadores aparecem primeiro. A aba Capacidade apresenta throughput, capacidade prática P95 e utilização antes da análise de recursos e hotspots. Essa análise espacial permanece como apoio, conforme a seção 5.4 do Produto III.

Cada aba termina com “Métricas auxiliares e cobertura dos dados”, fechado por padrão: registros (rotulados como observações válidas do STATELOG), aeronaves, pico simultâneo, duração, perfil de altitude, cadência, cobertura, amostras de separação, aderência espacial à REH e contagens geométricas. A estabilidade dos KPIs exclui essas séries e parâmetros; sua estabilidade e cobertura continuam disponíveis dentro do dropdown auxiliar. A classificação da estabilidade está em `web/assets/dashboard.js::isPrimaryStabilityMetric`; essa separação só afeta a apresentação.

A tabela de rastreabilidade e `docs/MATRIZ_KPIS_PRODUTO_3.md` são produzidas pelo mesmo catálogo em `src/uam_dashboard/metric_catalog.py`. O estado descreve implementação no código, separado da disponibilidade dos dados de cada cenário. A revisão registrou que atraso no ar não recebe referência para a família produto2, GD não usa a função legada de atraso em solo, TD depende de componentes formais e DP/IQR do tempo de voo ainda não são calculados. A fórmula P95 da Eq. 3.16 foi preservada: o painel usa média dos P95 individuais, enquanto o ranking de waypoints usa P95 das janelas completas agrupadas. Essas diferenças e as limitações de recursos/janelas estão explícitas no catálogo.

Para publicar as alterações de interface e de rastreabilidade sem reprocessar STATELOGs:

```bash
python prepare_publication.py
```

O comando atualiza `docs/index.html`, JS/CSS, catálogo e matriz; preserva os resultados numéricos, rankings e geometrias. A atualização de textos não homologa os parâmetros nem transforma indicadores indisponíveis em calculados.
