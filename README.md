# UAM KPI/KPA Dashboard

Gerador estatico para visualizar metricas de KPI/KPA de corredores aereos urbanos a partir de logs `STATELOG` do BlueSky.

## Como gerar

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py
```

Por padrao, o script procura o ultimo arquivo `STATELOG*.log` na pasta atual e publica a saida em `docs/`.

Tambem e possivel informar outro log:

```powershell
.\.venv\Scripts\python.exe generate_dashboard.py .\STATELOG_exemplo.log --output docs
```

## Saida

- `docs/index.html`: dashboard interativo pronto para GitHub Pages.
- `docs/assets/data/dashboard.json`: metricas agregadas.
- `docs/assets/data/tracks.geojson`: rotas amostradas por aeronave.
- `docs/assets/data/conflicts.geojson`: eventos LoWC amostrados.
- `docs/assets/data/heatmap_points.json`: pontos do heatmap.
- `docs/assets/charts/*.png`: graficos estaticos incorporados ao dashboard.

## GitHub Pages

Configure o GitHub Pages para publicar a pasta `docs/`. A pagina usa Leaflet e OpenStreetMap via CDN, entao o mapa base aparece quando ha acesso a internet.

## Fluxo planejado

O dashboard ja carrega a analise pre-processada em `docs/assets/data/`, e a interface tambem aceita upload local de outro `STATELOG` para uma leitura exploratoria no navegador. Para analises oficiais, prefira rodar o gerador Python para recalcular todos os graficos e arquivos GeoJSON.
