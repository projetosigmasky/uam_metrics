# UAM KPI/KPA Dashboard

Dashboard estatico para analisar logs `STATELOG` do BlueSky em cenarios de corredor aereo urbano na RMSP.

Este repositorio vincula as metricas ao `Produto3_vfinal_ProjetoSIGMASky.pdf` (Produto 3, versao 2.0, 31/07/2026). A saida principal e a pasta `docs/`, pronta para GitHub Pages. O PDF local e ignorado pelo Git; o catalogo versionado registra suas paginas e equacoes.


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

As replicas de cada cenario C1/C2 sao agrupadas pelo identificador do cenario, demanda e modo (`off`/`mvp`). Cada valor numerico publicado para o cenario e a media dos resultados calculados separadamente por replica, inclusive contagens, totais e picos. O P95 que aparece em algumas metricas e um percentil **dos resultados simulados**, nao um perfil de demanda P95. O mapa, os eventos, os graficos e a visualizacao 3D usam a primeira replica do grupo em ordem de nome como ilustracao. O seletor mostra um item por cenario, com a quantidade de replicas no nome. Para evitar um pacote excessivo, as trajetorias das demais replicas nao entram em `docs/`.

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

Antes de publicar, confira as contagens por cenario e o tamanho do pacote. Se `data_bundle.js` ficar grande demais para publicar, reduza a resolucao das camadas ilustrativas. Publique apenas a saida processada:

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

O gerador publica em `docs/`:

- `docs/index.html`: dashboard principal.
- `docs/assets/data_bundle.js`: pacote de dados usado pela pagina.
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

O horizonte `DTLOOK` e um parametro de diagnostico, nao um KPI formal do Produto 3 final.

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
é excluído dos recursos UAM por essa regra; o fixo REH Clube Sírio permanece selecionado.
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

REH: identidade = rede, nome normalizado, posição explícita e conjunto dos envelopes
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
