# UAM KPI/KPA Dashboard

Dashboard estatico para analisar logs `STATELOG` do BlueSky em cenarios de corredor aereo urbano na RMSP.

O projeto gera uma pasta `docs/` pronta para GitHub Pages, com mapas Leaflet, camadas georreferenciadas, graficos PNG e uma tabela comparativa quando houver mais de um log.

## 1. Organizacao Dos Logs

Coloque os arquivos `STATELOG*.log` em:

```text
data/
```

A pasta `data/` esta no `.gitignore`, entao os logs ficam fora do versionamento.

Exemplo:

```text
data/
  STATELOG_1_maior_movimento_20260527_134549_mvp_20260527_14-03-34.log
  STATELOG_2_maior_movimento_20260527_134756_mvp_20260527_14-16-21.log
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

## 3. Saida Gerada

O gerador publica em `docs/`:

- `docs/index.html`: dashboard principal.
- `docs/assets/data_bundle.js`: pacote de dados usado pela pagina.
- `docs/assets/data/dashboard.json`: metricas agregadas ou medias.
- `docs/assets/data/comparison.json`: linhas da tabela comparativa.
- `docs/assets/data/runs/*.json`: dados por log processado.
- `docs/assets/data/tracks.geojson`: rotas do primeiro log, para compatibilidade.
- `docs/assets/data/conflicts.geojson`: eventos LoWC do primeiro log.
- `docs/assets/data/heatmap_points.json`: pontos de densidade do primeiro log.
- `docs/assets/charts/*.png`: graficos estaticos por log.

## 4. Como A Comparacao Funciona

Quando ha dois ou mais logs:

- os cards superiores mostram a media das metricas principais;
- a tabela `Cenarios processados` mostra cada log e uma linha `Media`;
- o seletor `Cenario no mapa` troca o mapa e os graficos para o log escolhido;
- o botao `Carregar STATELOGs` permite comparar arquivos localmente no navegador como preview.

As medias incluem aeronaves, pico simultaneo, duracao, tempo medio, distancia media, eficiencia de rota, baixa altitude e eventos LoWC.

## 5. Responsabilidades Dos Modulos

### `generate_dashboard.py`

Orquestra o processo inteiro:

1. encontra logs em `data/` ou usa os caminhos passados na linha de comando;
2. chama o parser;
3. calcula metricas;
4. gera graficos;
5. exporta JSON/GeoJSON;
6. monta o bundle usado pela pagina;
7. copia `web/` para `docs/`.

### `src/uam_dashboard/config.py`

Centraliza constantes e parametros:

- colunas do `STATELOG`;
- conversoes de unidade;
- thresholds LoWC;
- altitude critica;
- amostragem de conflitos;
- amostragem de rotas e heatmap.

### `src/uam_dashboard/log_parser.py`

Le o arquivo de log, aplica nomes de colunas, converte campos numericos e ordena os registros.

### `src/uam_dashboard/metrics.py`

Contem as formulas principais:

- distancia Haversine;
- resumo do cenario;
- eficiencia operacional;
- eficiencia de rota;
- impacto ambiental por baixa altitude;
- serie temporal de aeronaves simultaneas;
- deteccao de LoWC.

### `src/uam_dashboard/exports.py`

Converte DataFrames em estruturas para a interface:

- rotas em GeoJSON;
- conflitos em GeoJSON;
- pontos de heatmap;
- timeline.

### `src/uam_dashboard/plots.py`

Gera os graficos PNG:

- aeronaves simultaneas;
- distribuicao de separacao horizontal;
- distribuicao de altitude;
- distancia por aeronave.

### `web/index.html`

Define a estrutura da pagina: cards de KPI, seletor de cenario, mapa, tabela comparativa e graficos.

### `web/assets/dashboard.js`

Renderiza a aplicacao no navegador:

- carrega o bundle;
- alterna cenarios;
- desenha camadas do mapa;
- monta a tabela comparativa;
- faz preview local de uploads multiplos.

### `web/assets/dashboard.css`

Controla layout, visual do dashboard e CSS critico do Leaflet.

## 6. Parametros Mais Importantes

Os principais parametros oficiais estao em `src/uam_dashboard/config.py`:

```python
low_altitude_ft = 1500.0
lowc_horizontal_m = 500.0
lowc_vertical_m = 30.0
conflict_sample_seconds = 10
same_altitude_band_m = 150.0
track_sample_stride = 20
heatmap_sample_stride = 10
```

Alguns podem ser alterados pela linha de comando:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py --lowc-horizontal-m 600 --lowc-vertical-m 40
```

## 7. Publicacao No GitHub Pages

Configure o GitHub Pages para publicar a pasta:

```text
docs/
```

Os logs ficam em `data/`, ignorados pelo Git, e o site final fica em `docs/`.
