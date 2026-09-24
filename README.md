# UAM KPI/KPA Dashboard

Dashboard estatico para analisar logs `STATELOG` do BlueSky em cenarios de corredor aereo urbano na RMSP.

Este repositorio implementa, em codigo, metricas de seguranca e eficiencia descritas no estudo `Projeto_SIGMA_Sky_Produto_3_Versao_1.pdf`. A saida principal e a pasta `docs/`, pronta para GitHub Pages.

## 1. Preparar Os Logs

Coloque os arquivos de entrada em:

```text
data/
  logs/
    STATELOG_produto2_C1_2025-11-09_off_<execucao>.log
    STATELOG_produto2_C2_2025-11-09_off_<execucao>.log
  scenarios/
    produto2_C1_2025-11-09_off.scn
    produto2_C2_2025-11-09_off.scn
```

A pasta `data/` fica fora do Git pelo `.gitignore`, entao os logs brutos nao entram no GitHub.

O formato esperado pelo parser e:

```text
simt,id,lat,lon,distflown,alt,hdg,trk,cas,tas,gs,vs
```

## 2. Gerar O Dashboard

Para processar todos os logs em `data/logs/`:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py
```

Para processar logs especificos:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py .\data\logs\STATELOG_produto2_C1_2025-11-09_off_<execucao>.log
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
lowc_vertical_m = 137.16
nmac_horizontal_m = 150.0
nmac_vertical_m = 30.48
mac_beta = 5.038e-3
mac_probability_given_nmac = 0.005
tls_target_per_flight_hour = 9.4e-6
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
capacity_window_seconds = 3600
capacity_reference_percentile = 0.95
crossing_capture_radius_m = 250.0
heatmap_sample_stride = 10
```

Alguns parametros podem ser alterados pela linha de comando:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py --lowc-horizontal-m 600 --lowc-vertical-m 137.16
.\.venv\Scripts\python.exe generate_dashboard.py --nmac-horizontal-m 150 --nmac-vertical-m 30.48
.\.venv\Scripts\python.exe generate_dashboard.py --conformity-tolerance-m 250
.\.venv\Scripts\python.exe generate_dashboard.py --visualization-3d-sample-seconds 5
.\.venv\Scripts\python.exe generate_dashboard.py --visualization-3d-ground-msl-ft 2621
.\.venv\Scripts\python.exe generate_dashboard.py --crossing-capture-radius-m 250
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
- `docs/assets/data/trajectory_3d.json`: trajetorias temporais amostradas para a visualizacao 3D.
- `docs/assets/charts/*.png`: graficos estaticos por log.

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

O dashboard renderiza todas essas colunas. LoWC e NMAC usam simultaneamente
separacao horizontal e vertical. Resultados dependentes de limites operacionais,
parametros probabilisticos ou capacidade declarada permanecem marcados como
`parcial`, mesmo quando o calculo ja esta implementado.

## 7. Metricas Parciais Ou Indisponiveis

As lacunas completas ficam no catalogo e na tabela do dashboard. As principais sao:

- TTC observado: requer instante de alerta/deteccao ou previsao de CPA;
- atraso no ar: requer execucao nominal pareada para cada cenario;
- atraso operacional de solo e pontualidade: requerem marcos programados,
  autorizados e reais de saida/chegada;
- capacidade real: requer capacidade declarada por recurso;
- MAC/TLS: requerem validacao dos limites e parametros probabilisticos.

O valor de 60 s continua disponivel somente como horizonte `DTLOOK`; ele nao e
rotulado como TTC observado.

## 8. Comparacao Entre Logs

Os nomes `produto2_C1_<data>_off` e `produto2_C2_<data>_off` sao agrupados
automaticamente como variantes da mesma demanda. C1 e a referencia da comparacao;
C2 representa o corredor UAM dedicado. A tabela mostra diferencas de tempo e
distancia contra C1 e a razao de risco da Eq. 4.10.

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

Coloque os arquivos BlueSky `.scn` em `data/scenarios/`. O gerador associa automaticamente cada
log ao cenario de mesmo nome-base.

Coloque `CV_REH_XP_SAO_PAULO.xml` em `data/xml/` ou informe seu caminho com
`--reh-xml caminho/para/CV_REH_XP_SAO_PAULO.xml`. O gerador tambem procura automaticamente o XML
no projeto irmao `../rmsp-uam-simulations/data/xml/`.

A camada `REH formal` desenha os poligonos WFS/GML do XML, incluindo a semilargura oficial de cada
trecho. A camada `Planejamento do cenario` conecta a origem e os waypoints definidos por `CRE`,
`ADDWPT` e `DEFWPT` no arquivo `.scn`.

A geometria oficial do corredor UAM dedicado desta fase fica em
`data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv`. Ela representa a rede completa
entre tres aeroportos e seis vertiportos (`VP-001` a `VP-006`), com 36 pares OD e duas trilhas
paralelas por par. O gerador a descobre automaticamente; `--uam-corridor-csv` permite informar uma
copia equivalente. Arquivos com outra quantidade de vertiportos sao rejeitados enquanto o escopo
do estudo permanecer limitado aos seis pontos UAM.

A conformidade formal segue as Eq. 4.16-4.17 do PDF, comparando distancia executada e planejada.
Separadamente, a aderencia espacial informa o percentual de amostras executadas que estao dentro
de algum poligono oficial da REH. O parametro `conformity_tolerance_m` continua sendo usado apenas
no diagnostico de proximidade da linha planejada quando o XML nao esta disponivel.

As instancias planejadas e executadas sao associadas por matricula e horario de criacao mais
proximo. Isso evita deslocar a sequencia quando uma matricula e reutilizada e alguma instanciacao
planejada nao aparece no `STATELOG`.

## 11. Diagnostico Da Severidade LoWC

LoWC exige simultaneamente `Sh < Smin_h` e `Sv < Smin_v`; NMAC usa os dois
limites mais restritivos. Os padroes atuais sao 500 m/137,16 m para LoWC e
150 m/30,48 m para NMAC. Eles sao parametros configuraveis e permanecem
marcados como pendentes de validacao operacional.

A severidade de cada amostra e `max(Sh/Smin_h, Sv/Smin_v)`. A severidade do
evento e o menor valor ao longo de sua duracao. O resultado tambem informa a
separacao vertical e a combinacao eVTOL-eVTOL, eVTOL-helicoptero ou
helicoptero-helicoptero.

## 12. Capacidade, Densidade E Utilizacao

A densidade formal usa os poligonos oficiais de cada trecho REH. A area `A` da Eq. 4.23 e calculada
diretamente da geometria WFS/GML; a semilargura deixa de ser imposta globalmente e passa a ser a do
cadastro oficial (100 m ou 250 m, conforme o trecho). Os hotspots ATD tambem passam a ser agregados
por trecho oficial.

O throughput da Eq. 4.24 e calculado em janelas de 1 hora para quatro tipos de recurso:

- pares origem-destino observados;
- grupos de trajetoria executada;
- trechos REH oficiais atravessados pelo planejamento de cada voo;
- waypoints virtuais de cruzamento entre corredor UAM e REH.

Nos cenarios dedicados C2--C6, os waypoints de cruzamento sao calculados pela sobreposicao horizontal
entre os corredores UAM oficiais do CSV de seis vertiportos e os poligonos oficiais dos trechos REH no
XML. Nos demais cenarios, permanece o fallback para as rotas planejadas do `.scn`. Cada ponto virtual
representa o centro aproximado da area de sobreposicao e recebe um identificador `XUAMREHnnn`.
O resultado e explicitamente 2D: uma classificacao volumetrica depende dos envelopes verticais oficiais
do corredor UAM e da REH.

Para cada waypoint, o processamento conta uma passagem por instancia de voo dentro do raio configurado,
agrega as passagens nas janelas de capacidade e usa `P95(THR)` como limite operacional observado. Esse
limite e uma referencia interna, nao uma capacidade declarada ou homologada. A tabela ordena os pontos
mais criticos e permite destaca-los no mapa, assim como pares OD, grupos de trajetoria e trechos REH.

Como ainda nao ha capacidade declarada externa, a utilizacao da Eq. 4.25 usa uma referencia nominal
interna: `C_r,dt = P95(THR_r,dt)` por tipo de recurso. Assim, a utilizacao informa quao proximo o recurso
ficou do envelope operacional observado no proprio conjunto de simulacoes.

## 13. Testes

Rode os testes unitarios com:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## 14. Waypoints criticos em todas as replicas C1/C2 no Lessonia

Execute `critical_waypoints.py` **no Lessonia**, no diretorio deste repositorio.
Os logs brutos permanecem no servidor; cada processo le uma replica em fluxo.
Ele combina dois criterios para selecionar os pontos candidatos:

- cruzamentos virtuais 2D: sobreposicao entre o corredor UAM do CSV e os poligonos REH do XML;
- nos do corredor UAM com mais de duas arestas fisicas distintas conectadas.
- fixes da REH oficial com mais de duas arestas distintas da linha central conectadas.

Para o segundo criterio, cada par consecutivo de pontos de uma rota forma uma
aresta nao direcionada. Arestas repetidas em diferentes rotas contam apenas uma
vez. Os nos sao identificados pelas coordenadas do CSV arredondadas a seis casas
decimais, evitando unir trilhas paralelas ou pontos de mesmo nome em locais
distintos. Somente pontos do tipo `Waypoint` ou `Geometric Node` entram pelo
criterio topologico; aeroportos e vertiportos nao entram por esse criterio.
No CSV atual, essa regra identifica 52 nos UAM; no XML REH oficial disponivel
no projeto irmao, identifica 31 nos REH. A geometria candidata e unica para
C1 e C2, permitindo comparar os mesmos pontos. Cada voo e contado uma vez por
waypoint dentro do raio de 250 m. Todos os veiculos no STATELOG sao incluidos.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python critical_waypoints.py \
  --logs-root /caminho/no/lessonia/replicas \
  --reh-xml /caminho/no/lessonia/CV_REH_XP_SAO_PAULO.xml \
  --uam-csv data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv \
  --output-dir /caminho/no/lessonia/resultados_waypoints \
  --workers 4
```

O descobridor aceita arquivos `STATELOG` `.log` ou `.csv` cujos nomes contenham
`_C1_` ou `_C2_` (inclusive nas subpastas). Para nomes diferentes, ou para
selecionar explicitamente as replicas, use um manifesto CSV com cabecalho
`scenario,path` e troque `--logs-root` por `--manifest manifesto.csv`. Caminhos
relativos no manifesto sao resolvidos a partir da pasta do manifesto.

O ranking em `critical_waypoints.csv` inclui **todos** os pontos candidatos para
cada cenario. A coluna `criterion` identifica `uam_reh_crossing` ou
`uam_junction` ou `reh_junction`; `network_degree` informa o grau dos nos. A coluna
`mean_throughput_per_hour` e a media, com peso igual entre replicas, do
throughput medio por janela de uma hora de cada replica. O ranking decresce por
essa coluna; em caso de empate, usa a media dos picos horarios. Uma replica sem
passagens em um waypoint contribui com zero. `waypoints_by_replica.csv` permite
auditar os valores de cada execucao. `critical_waypoints.geojson` contem todos os
pontos e identificadores; `crossing_waypoints.geojson` preserva apenas os
cruzamentos UAM-REH. `run_metadata.json` registra parametros e arquivos processados.
Os valores sao fluxos observados em pontos definidos pela geometria horizontal
2D, nao capacidades declaradas nem uma avaliacao de separacao vertical.

O dashboard mostra os nos UAM e REH candidatos em uma camada propria do mapa
e em uma tabela na secao Capacidade. A listagem e puramente geometrica; a
classificacao por movimento depende das replicas. Ao gerar o dashboard completo,
`generate_dashboard.py` produz `assets/data/candidate_nodes.geojson` e
`assets/candidate_nodes.js`. Para atualizar apenas esses dois arquivos, sem
reprocessar logs, execute:

```bash
python generate_candidate_nodes.py \
  --uam-csv data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv \
  --reh-xml /caminho/CV_REH_XP_SAO_PAULO.xml \
  --output-dir docs
```

Para trazer somente os resultados ao computador local, execute localmente,
substituindo usuario e diretorios:

```bash
scp -r usuario@lessonia:/caminho/no/lessonia/resultados_waypoints ./resultados_waypoints
```
