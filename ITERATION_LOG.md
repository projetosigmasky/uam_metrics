# Histórico técnico e passagem de contexto — atualizado em 21/10/2026

Este arquivo registra as decisões e os resultados desta sequência de trabalho para orientar novas iterações com outras LLMs. Não substitui os dados nem o código. A base quantitativa é o snapshot publicado no commit `f30f4de` (`Publica calibracao dos quatro baselines`).

**Atualização:** a seção 11 registra as mudanças de 21/10/2026 e substitui as descrições anteriores da interface pública e da seleção C1/C2. A análise quantitativa de capacidade de 20/10 permanece preservada.

## Leitura inicial para a próxima iteração

1. Ler este histórico e o [pacote de evidências para o relatório](reports/baseline_capacity_2026-10-20/README.md).
2. Consultar `docs/assets/data/baseline_calibration/comparison.csv` e `calibration.json` antes de interpretar os gráficos.
3. Distinguir três conceitos: **fluxo observado**, **capacidade configurada no algoritmo** e **capacidade operacional máxima demonstrada**.
4. Não assumir que os valores 1 da calibração atual vieram de fallback. A auditoria desta iteração mostrou que vieram de P95 de janelas positivas com passagens observadas.
5. Não atribuir uma capacidade única apenas pelo nome do waypoint. O identificador analítico é o recurso físico/pista/altitude; nomes iguais podem corresponder a recursos diferentes.

## 1. Escopo e ambiente

- Repositório de pós-processamento local: `post-processing`, remoto `https://github.com/projetosigmasky/uam_metrics`, branch `main`.
- Repositório do gerador consultado localmente: `../rmsp-uam-simulations`.
- No Lessonia o clone do gerador tem outro nome: **`/home/matosdfm/rmsp`**. O caminho inicialmente sugerido `~/rmsp-uam-simulations` não existia no servidor.
- JSONs originais da rodada: `/home/matosdfm/rmsp/scenarios/product2/nominal_20261013`.
- Logs reais usados: `/home/matosdfm/runs/20261015_112401_6cddab52`.
- A execução dos comandos no Lessonia e os pushes foram feitos pelo usuário. Nesta conversa o assistente implementou e testou código localmente e analisou os resultados recebidos, sem executar simulações remotas.
- O pedido inicial era apenas conversar, sem executar ações. Posteriormente o usuário autorizou explicitamente as implementações de basemap, layout, calibração, paralelismo e, nesta iteração, o registro e a seleção de evidências.

## 2. Alterações de interface anteriores à calibração

### Basemap

O dashboard usa Leaflet e desenha trajetórias, corredores e conflitos sobre uma camada de fundo. A troca Carto → OpenStreetMap foi feita em `web/assets/dashboard.js` e `docs/assets/dashboard.js`:

- Tiles: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`, sem chave de API.
- Atribuição ao OpenStreetMap mantida; `maxNativeZoom=19`, `maxZoom=20`.
- Camadas analíticas e cálculos dos KPIs preservados.
- O serviço continua dependendo de internet e da política de uso dos tiles públicos; não é uma base hospedada pelo projeto.

### Layout

Todas as abas começam com cards de indicadores. Mapas, visualização 3D e gráficos ficam abertos abaixo dos cards; tabelas e explicações extensas ficam recolhidas em “Ver detalhes”, usando `details/summary`. A linha do tempo de eventos da visualização 3D também possui seu próprio bloco recolhível.

O seletor de cenário da **calibração** é independente do seletor do mapa e dos KPIs legados. Gerar a calibração não recalcula automaticamente todos os KPIs dos quatro baselines no fluxo legado C1/C2.

## 3. KPIs e agregação existentes

O fluxo legado calcula por réplica e depois agrega por cenário. A quantidade esperada de 50 réplicas é uma validação estrutural, não um teste automático de suficiência estatística.

O catálogo em `src/uam_dashboard/metric_catalog.py` descreve segurança (LoWC/NMAC, taxas, exposição, severidade, MAC estimado, TLS e razão de risco), eficiência (tempo, distância, ineficiência horizontal, conformidade e atraso no ar quando há referência), capacidade (throughput/P95/utilização) e diagnósticos espaciais. Atraso formal em solo/total, pontualidade e equidade possuem limitações ou indisponibilidade no fluxo atual. MAC/TLS dependem de coeficientes provisórios. Não tratar cards de indisponibilidade como valores zero.

O dashboard legado usa, em vários resultados, médias de estatísticas por réplica. A nova calibração de capacidade tem outra definição: **P95 das janelas reunidas das réplicas**, calculado separadamente para cada recurso, cenário, tamanho de janela e política de zeros. Não confundir média dos P95 com P95 do conjunto de janelas.

## 4. Parâmetros encontrados no gerador de simulações

Fontes consultadas: `uam_sim/scenarios/product2.py`, `uam_sim/scenarios/nominal.py`, `data/product2_scenario_parameters.json`, `configuracao_experimento.json`, `docs/RODADA_NOMINAL_20261013.md` e amostras dos JSONs gerados no outro repositório.

| Método/parâmetro | Regra encontrada |
|---|---|
| DCB MILP por waypoint, Chen | Referência provisória uniforme de **4 movimentos por 300 s** |
| Bins de waypoint | Fixos, época 0 s, intervalos semiabertos |
| DCB MILP por quadrícula | Ocupação: **1 aeronave**, reservas em bins de **1 s**; malha sintética de 18 células |
| Micro MILP e Micro Moolchandani adaptado | Headway de **23 s**, com margem numérica de **0,02 s** no agendamento |
| Ação da variante Micro Moolchandani usada | Somente atraso em solo, com reavaliação da rota |
| Separação vertical micro | 1.000 ft; não é o limiar LoWC/NMAC do dashboard |
| Máximo de atraso em solo | 3.600 s; exceção C7.2.2: 7.200 s |
| Limite do solver | 60 s; quadrículas: 10 s; viabilidade não implica prova de otimalidade |

Os quatro baselines desta calibração não têm gestão estratégica. Nenhum desses parâmetros foi alterado para 1 ou 2 durante esta iteração. Throughput em 5 min não verifica sozinho headway de 23 s nem simultaneidade de quadrícula.

## 5. Decisão de comparar três escalas temporais

O usuário pediu preservar **5, 15 e 60 minutos**, para avaliar a sensibilidade da referência de throughput.

| Janela | Contagem | Conversão para taxa equivalente |
|---|---|---|
| 300 s | movimentos/5 min | multiplicar por 12 → operações/h |
| 900 s | movimentos/15 min | multiplicar por 4 → operações/h |
| 3.600 s | movimentos/h | mesma contagem → operações/h |

Usam-se somente janelas completas, alinhadas à época 0 s e semiabertas. Um evento exatamente em 300 s pertence à janela `[300,600)`. Na execução real, o horizonte declarado é de 90.000 s (25 h), de modo que há 300 janelas completas de 5 min por réplica e 15.000 nas 50 réplicas por recurso. A janela horária da geração de demanda não é a mesma coisa que a janela de análise do throughput.

## 6. Módulo implementado

Arquivos principais:

- `prepare_baseline_manifest.py`: descoberta dos JSONs e WPPASS dos quatro baselines, com recusa de duplicidades/ambiguidade.
- `generate_baseline_calibration.py`: validação, análise, publicação e atualização de versões dos assets.
- `src/uam_dashboard/baseline_calibration.py`: ocorrências nativas, bins, quantis, bootstrap e exportações.
- `generate_reports.py --baseline-manifest ...`: integração com o comando principal, independente de `--run-id` legado.
- `web/calibration.html`, `web/assets/baseline_calibration*`: interface e cópia publicada em `docs/`.
- `tests/test_baseline_calibration.py`: cobertura de limites temporais, quantil, políticas de zero, integridade das ocorrências, descoberta, publicação e workers.

### Fontes e elegibilidade

A fonte principal é **WPPASS nativo**. O JSON original traz `product2.resource_manifest`, com `capacity_key=physical_point_track`. Cada evento é conferido por aeronave, ID físico e ocorrência da rota; eventos duplicados, ausentes ou inconsistentes interrompem o processamento. O universo é o de recursos elegíveis nomeados do manifesto; não é o filtro legado de junções com grau >=3.

A alternativa geométrica via STATELOG exige escolha explícita no manifesto e é identificada como estimativa. Não há fallback silencioso de fonte e não se misturam fontes nativas e geométricas dentro de um cenário. A execução real analisada aqui usou **native** nos quatro casos.

### Zeros e P95

- `positive`: elimina bins zerados antes de calcular o P95 `higher`; reúne os bins positivos das 50 réplicas.
- `all`: inclui todos os bins completos observados, inclusive zeros.
- Um recurso sem uso fica como `no_observed_use`, com referência indisponível. Não recebe capacidade 0 nem piso artificial 1.
- Falta de cobertura integral por alguma réplica invalida a referência final daquela escala.
- Cada recurso aparece uma vez no histograma por cenário/política/janela. Não se somam capacidades para obter capacidade de rede.

### Estabilidade

No outro repositório havia `uam_sim/analysis/stability.py`, com média acumulada e critério de confiança, mas ele não estava integrado ao fluxo deste pós-processamento. O novo módulo usa bootstrap de **réplicas inteiras** para a média das janelas reunidas e para seu P95, preservando a dependência temporal interna de cada réplica.

Padrões do snapshot: IC95%, mínimo de 30 réplicas, tolerância relativa de 5%, absoluta de 0 operações/h, 15 verificações consecutivas, 1.000 reamostragens e semente 1729. A confirmação mais precoce é em 44 réplicas. `confirmed_at_n` registra a primeira confirmação; `stable_at_final` exige manutenção do critério na sequência final. Média e P95 são avaliados separadamente. Intervalos degenerados em dados discretos/raros não são prova de capacidade máxima ou segurança.

Os JSONs/JS usam curvas e coberturas compactadas: consultar `trace_columns` e `coverage_columns`. Os CSVs mantêm cabeçalhos explícitos.

### Paralelismo

Adicionado após solicitação explícita do usuário: cálculo por recurso físico, distribuído em processos. `--workers 25` usa até 25 workers; cada um calcula as três escalas e ambas as políticas de zeros de um waypoint. Sorteios feitos uma vez no processo principal e ordem de saída preservada. Cada worker usa um thread BLAS/OpenMP. Leitura, gráficos e gravação permanecem sequenciais.

Prioridade: `--workers` > `workers` na raiz do manifesto > 1. O fluxo não herda automaticamente `dashboard_workers`/`ranking_workers` do legado. Foram registrados **62 testes aprovados**, incluindo equivalência sequencial/paralela dos resultados estatísticos.

## 7. Execução efetiva no Lessonia e publicação

O primeiro preparo falhou com todos os JSONs ausentes, mas nenhum WPPASS ausente. A busca no servidor encontrou os JSONs em `~/rmsp`, corrigindo a hipótese inicial de caminho. Não foi necessário repetir simulações.

```bash
cd ~/post-processing
CALIBRATION_SCENARIOS="$HOME/rmsp/scenarios/product2/nominal_20261013"
CALIBRATION_RUNS=("$HOME/runs/20261015_112401_6cddab52")

.venv/bin/python prepare_baseline_manifest.py \
  --scenario-root "$CALIBRATION_SCENARIOS" \
  --run-dirs "${CALIBRATION_RUNS[@]}" \
  --output baseline_manifest.local.json

.venv/bin/python generate_reports.py \
  --baseline-manifest baseline_manifest.local.json \
  --audit-dir calibration_audit \
  --workers 25
```

Execução concluída: **200 réplicas**, **1.602 recursos físicos**, **25 processos**, saída `/home/matosdfm/post-processing/docs/calibration.html`. O manifesto processado tem SHA-256 `ad67679118309f02d320b6484389224290f30404b8bac775a1b3e4050f4765c2`.

Resultados compactos foram publicados no commit `f30f4de`. Logs brutos e auditoria opcional permanecem no servidor. A auditoria detalhada `calibration_audit/` e o manifesto local são ignorados pelo Git. Depois de um eventual processamento legado que recrie `docs/assets`, executar a calibração por último para repor seus dados.

Página: `https://projetosigmasky.github.io/uam_metrics/calibration.html`.

Houve um incidente de publicação: localmente os dados abriam, mas o Pages mostrava o estado vazio antigo. A execução [pages-build-deployment #23](https://github.com/projetosigmasky/uam_metrics/actions/runs/39438808370), commit `f30f4de`, teve build bem-sucedido e **deploy HTTP 500**. A orientação foi reexecutar os jobs que falharam; não recalcular métricas. Este histórico registra o incidente verificado, sem afirmar o estado atual do deploy após eventual nova tentativa.

## 8. Achado desta iteração: predominância de 1 ou 2 movimentos/5 min

O usuário observou a concentração e lembrou que 1 havia sido um fallback histórico para não chamar ausência de movimento de capacidade zero. A checagem do código e dos CSVs exige separar essa lembrança do algoritmo que gerou os gráficos atuais.

### Resultado real — P95 condicionado a janelas positivas

| Cenário | Arquitetura / estágio | Recursos | P95 = 1 | P95 = 2 | P95 = 3 | Com P95 1 ou 2 | P95 estável |
|---|---|---:|---:|---:|---:|---:|---:|
| C1.1 | Compartilhada / 6 vertiportos | 544 | 487 | 57 | 0 | 100,0% | 215 |
| C1.2 | Compartilhada / 12 vertiportos | 594 | 477 | 108 | 9 | 98,5% | 236 |
| C2.1 | Dedicada / 6 vertiportos | 193 | 114 | 79 | 0 | 100,0% | 127 |
| C2.2 | Dedicada / 12 vertiportos | 271 | 125 | 129 | 17 | 93,7% | 167 |
| **Total** | Cenários mantidos separados na análise | **1.602** | **1.203** | **373** | **26** | **98,4%** | **745** |

Esta soma é um resumo de registros recurso/cenário. Um mesmo ponto físico pode estar presente em mais de um cenário. Não são necessariamente 1.602 nomes de waypoint distintos. Os 98,4% se referem a recursos, **não a 98,4% das operações**.

Somente **745/1.602 (46,5%)** confirmaram a precisão final do P95 positivo no critério adotado. Portanto, concentração das referências em 1/2 e estabilidade entre réplicas são afirmações diferentes. Os gráficos de exemplos foram selecionados com boa cobertura e precisão confirmada; não autorizam generalizar estabilidade aos recursos restantes.

### Resultado real — incluindo janelas zeradas

| Cenário | P95 = 0 | P95 = 1 | P95 = 2 |
|---|---:|---:|---:|
| C1.1 | 496 | 48 | 0 |
| C1.2 | 527 | 65 | 2 |
| C2.1 | 145 | 46 | 2 |
| C2.2 | 196 | 73 | 2 |
| **Total** | **1.364** | **232** | **6** |

Os 1.364 zeros são percentis de fluxo incluindo ociosidade. Não demonstram impossibilidade de atender movimentos. A distinção entre as duas políticas é central para justificar o parâmetro experimental escolhido.

### Auditoria da regra de piso 1

No outro repositório, `uam_sim/analysis/capacity.py::reference_capacity` contém a regra histórica:

```python
positive = sorted(x for x in counts if x > 0)
return max(positive[math.ceil(percentile * (len(positive) - 1))], minimum) if positive else minimum
# default: minimum=1
```

Isso aplica o piso quando não há janelas positivas; quando existem contagens inteiras positivas, o percentil já é >=1. Não equivale a calcular P95 com zeros e depois trocar seus zeros por 1.

Na calibração atual, `estimate` zera a frequência do bin 0 apenas na política positiva e chama `quantile_hist`, sem `max(...,1)`. Recursos sem uso retornam referência indisponível. **Todos os 1.602 registros deste snapshot têm janelas positivas.** Assim, os valores 1 atuais são observados no percentil condicionado, não imputados pela regra histórica.

Exemplo verificável no CSV: C1.1, `R016620E6B2EB5EBB921B` (CEBOLINHA), 101 janelas positivas de 15.000; P95 positivo = 1 movimento/5 min (12 operações/h), P95 incluindo zeros = 0. Nenhuma substituição de 0 por 1 foi necessária para produzir essas duas estatísticas.

O condicionamento cria, por definição, um mínimo de 1 em qualquer percentil calculável das janelas positivas. Ele descreve intensidade durante uso, sem demonstrar um limite físico. O relatório deve explicitar essa opção metodológica.

## 9. Figuras selecionadas e material entregue para o relatório

Pacote: [reports/baseline_capacity_2026-10-20](reports/baseline_capacity_2026-10-20/README.md).

- Uma comparação geral dos quatro cenários em movimentos/5 min.
- Por cenário: distribuição discreta comparando janelas positivas e todas as completas; curvas de P95 e média de exemplos das classes 1 e 2.
- Por cenário: referências aos histogramas e CDFs originais de 5/15/60 min. Nesses originais, o eixo é operações/h; converter 12 → 1 e 24 → 2 movimentos/5 min.
- PNGs derivados a 300 dpi e SVGs editáveis, legendas sugeridas e texto-base para o relatório.
- `scenario_summary.csv`, `network_summary.csv`, `waypoint_capacity_evidence.csv`, `selected_waypoints.csv` e `stage_sensitivity.csv`.
- `evidence_manifest.json`: hashes das fontes, figuras, commit e regra de seleção.
- Reprodutor: `scripts/build_baseline_capacity_evidence.py`, que não altera os resultados originais nem os parâmetros de simulação.

Regra de escolha dos oito exemplos: P95 positivo igual a 1 ou 2; precisão final confirmada; pelo menos 100 janelas positivas; cobertura mais próxima da mediana da classe; desempate pelo ID físico. Nos compartilhados, a classe 1 tem mediana de apenas 9 janelas positivas; portanto, os exemplos de cobertura >=100 são intencionalmente mais informativos que o recurso raro típico.

### Sensibilidade ao estágio

- C1.1 → C1.2: 544 recursos físicos em comum; 42 mudam de classe. Transições: 34 de 1→2, 6 de 2→3 e 2 de 1→3. Há 50 recursos adicionais em C1.2.
- C2.1 → C2.2: 185 em comum; 41 mudam de classe. Transições: 26 de 1→2, 11 de 2→3, 3 de 2→1 e 1 de 1→3. Há 86 adicionais em C2.2 e 8 presentes apenas em C2.1.

Isso reforça que P95 observado depende da demanda e do cenário. Ainda é uma decisão de modelagem escolher limites por estágio ou uma referência comum para os cenários comparados.

## 10. Conclusões permitidas e decisões pendentes

**Sustentado pelos dados:** usar a distribuição dos baselines como base empírica para estudar parâmetros individualizados de 1/2 movimentos por waypoint/5 min, explicando a política de zeros e mantendo exceções e incerteza visíveis.

**Ainda não demonstrado:** que 1 ou 2 seja a capacidade máxima segura de cada waypoint, que todos os recursos tenham convergido, que uma soma dessas referências seja a capacidade da rede, ou que truncar os 26 casos de classe 3 para 2 seja justificável.

Antes de alterar o gerador, decidir:

1. Tratamento dos recursos com P95 3 e dos recursos sem precisão final confirmada.
2. Limites específicos por estágio/arquitetura ou uma regra comum para comparações.
3. Tratamento de um recurso futuro sem observações: referência indisponível versus piso operacional declarado como hipótese, sem atribuí-lo aos dados.
4. Validação posterior do efeito dos limites em atraso, throughput, conflitos e ocupação. O P95 dos baselines não substitui essa avaliação.

O objetivo desta iteração é **registrar e preparar evidências**, não modificar as capacidades dos algoritmos nem redigir uma conclusão de segurança.


## 11. Atualização de 21/10/2026 — cenários e mapa UAM

### Pedido e resultado implementado

O usuário autorizou atualizar o dashboard para C1.1/C1.2/C2.1/C2.2, retirar trajetórias e planejamento do mapa, retirar a calibração da página pública e investigar as sobreposições no trajeto VP-005–VP-006. Foi consultada a planilha original de cenários e o repositório de simulação.

- `run_config.json` agora seleciona a RUN `20261015_112401_6cddab52`, os quatro baselines, 50 réplicas por cenário e CSVs de geometria distintos por etapa. A seleção reconhece pastas com ponto ou underscore e exige réplicas 1–50, SCNs distintos e geometria compatível antes de publicar.
- `experiment.py` reconhece identificadores com múltiplos níveis, como C3.1.2 e C8.2.1. O pareamento não substitui uma réplica ausente por outra e recusa fontes ambíguas. C5/C6/C9/C10 não inferem tamanho da rede a partir do sufixo de algoritmo; é preciso mapeamento explícito de geometria.
- Comparações dos baselines usam C1 da mesma etapa (C2.1 vs C1.1; C2.2 vs C1.2). Para famílias dedicadas futuras, a referência configurada por metadados é C2 da mesma etapa; compartilhadas usam C1. Essas referências só produzem comparação se o baseline correspondente tiver sido selecionado.
- O heatmap usa todos os registros de posição das réplicas, em grade fixa de 0,001°. Contagens são somadas e divididas pelo número de réplicas, incluindo réplicas sem amostras em determinada célula. Uma escala comum evita amplificação visual por quantidade de réplicas. A unidade é média de registros de posição por célula e réplica; não é throughput nem contagem de aeronaves únicas. Cadência/cobertura devem ser compatíveis para comparação quantitativa.
- A geometria UAM e os nós passam a ser selecionados por cenário. C1.1/C1.2 exibem a rede REH, sem uma rede UAM dedicada fictícia. As regras e fontes REH foram preservadas.
- Os gráficos temporais e eventos continuam de uma réplica representativa, explicitamente identificada. A linha do tempo permanece recolhida; seus links agora levam ao local do evento no mapa.
- A interface não oferece trajetórias, planejamento nem visualização 3D. Esses recursos ficam **em observação**; métricas de distância, conformidade, throughput por grupo, exports e código de cálculo permanecem disponíveis. Atalhos de mapa para grupos de trajetória e pares OD também foram retirados. O heatmap é a exibição de densidade; os indicadores numéricos ATD/hotspots continuam disponíveis.
- `docs/calibration.html` e seus links/scripts no dashboard foram retirados. O gerador nativo continua produzindo CSV/JSON/PNG para auditoria, sem voltar a publicar essa página. A atualização dos assets preserva dados e figuras de calibração já calculados.

### Aglutinação dos corredores

Novo módulo `src/uam_dashboard/corridor_geometry.py`; exportador `generate_uam_projection.py` atualizado. Relatório e figuras: [auditoria UAM](reports/uam_geometry_2026-10-21/README.md).

1. A área 2D é a união dos buffers métricos existentes, preservando inclusive vazios internos. Isso elimina o escurecimento por repetição de rotas OD.
2. Um grafo geométrico elimina segmentos coincidentes/invertidos e divide sobreposições parciais e interseções onde a altitude interpolada coincide com precisão de 1 mm e as dimensões são iguais. Não há união por proximidade nem por nome. Pistas distintas e níveis separados permanecem distintos.
3. O grafo identifica junções não terminais de grau >=3: 72 na rede de 6 vertiportos e 199 na rede validada de 12. São diagnósticos, com `capacity_resource: false`; não modificam os recursos nativos nem os valores calibrados.
4. Na rede inicial, 858 ocorrências de segmentos correspondem a 222 únicos (636 repetições); na rede de 12, 2.156 correspondem a 412 (1.744 repetições). Após dividir nas interseções, são 280 e 642 arestas geométricas únicas.
5. O CSV validado de 12 vertiportos foi copiado do repositório de simulação, mantendo seu hash `c66e8a39665cbee3f44145d80fb66d2052877b5c3390803c7be9a445d7a2e0bc`. O CSV anterior permanece para rastreabilidade.
6. SCNs reais originais r001 de C2.1/C2.2: 1.732/4.113 posições internas, desvios máximos 0,057/0,065 m, dentro da tolerância horizontal de 2 m. Altitudes dos SCNs não são validadas por esse método.
7. A malha de entrada e o repositório de simulação não foram alterados. Alterações operacionais nessa malha exigiriam atualização do gerador/manifests e avaliação de novas simulações.

Durante a validação foi acrescentado um filtro por caixas envolventes ao diagnóstico UAM × REH. Ele descarta apenas pares sem possibilidade de interseção e preserva a rotina anterior nos pares restantes; reduz o custo do processamento das réplicas.

### Situação dos dados e próximo passo no Lessonia

Este clone contém KPIs completos antigos C1/C2 e calibração nativa dos quatro baselines; os STATELOGs reais novos estão no Lessonia. **Não renomear C1/C2 como C1.1/C1.2/C2.1/C2.2.** A interface já oculta esses resultados antigos e informa que aguarda reprocessamento.

Após o push feito pelo usuário:

```bash
cd ~/post-processing
git pull --ff-only
.venv/bin/python generate_reports.py --config run_config.json --workers 25
```

Esse comando produz o dashboard completo e o ranking para os quatro cenários. `generate_reports.py --baseline-manifest ...` continua sendo somente calibração nativa, independente. Não é necessário recalcular a calibração nem rodar novas simulações apenas para atualizar esta interface/heatmap. Se os logs estiverem distribuídos em outras RUNs, a seleção de dashboard precisa ser adaptada explicitamente; não substituir pela RUN antiga.

A validação incluiu testes unitários de identificação e seleção, média espacial com 50 réplicas, sobreposições parciais, reversões, cruzamentos 3D, preservação da área e geração completa com dois workers e duas réplicas de cada baseline. Os testes de contrato DOM/Leaflet verificam a ocultação de dados legados, ausência de controles retirados, densidade e troca de cenário. As figuras da auditoria foram inspecionadas visualmente. O navegador integrado não alcançou o servidor HTTP local nesta sessão; não houve verificação visual do dashboard em navegador nem publicação remota.

Verificação final: **75 testes Python passaram**, incluindo geração completa com dois workers. `node tests/dashboard_ui.test.cjs`, validação sintática do JavaScript, estrutura HTML e sincronismo `web/` → `docs/` também passaram. A referência desta verificação é o código local de 21/10/2026; os dados reais ainda precisam do processamento no Lessonia indicado acima.


## 21/10/2026 — Gráficos agregados, estabilidade por réplica e restauração do 3D

Execução das decisões de planejamento no commit de partida `9750739`; árvore inicialmente limpa, sem AGENTS.md aplicável encontrado. Sem push, publicação ou execução no Lessonia. Os relatórios `baseline_capacity_2026-10-20` e `uam_geometry_2026-10-21` permanecem intactos.

- Novo `replica_analysis.py`: histogramas compactos por worker, classes fixas entre cenários, média das distribuições percentuais por réplica e média das contagens de altitude/eventos. Distância usa instâncias de voo e delta do odômetro. Séries alinhadas por timestamp de simulação; ausências não viram zero. Exporta cobertura temporal, cadência e voos pareados. Faixas dos gráficos são mínimo–máximo, não IC. Intervalos discretos nos histogramas evitam sugerir interpolação entre classes vazias.
- Protocolo `analysis_schema_version=1`, `aggregate_analysis.schema_version=1`, `dashboard.chart_aggregation_version=1` e `stability.schema_version=1`. A UI exige as versões de gráfico antes de exibir imagens agregadas. Pacote legado fica com indisponibilidade explícita; seus seis gráficos representativos não recebem rótulos de agregados. Arquivos reais de dados, heatmap de todas as réplicas, geometrias e rankings não foram regenerados ou modificados.
- Ordenação por cenário, índice real da réplica e arquivo antes de distribuir/coletar tarefas; mesmos resultados com entradas invertidas e workers em ordens diferentes. Mantidos até 25 workers. Preservam-se valores individuais completos em arquivos de auditoria por cenário; não se descarta informação antes da estabilidade.
- Bloco recolhido em cada aba: curvas por cenário e KPI dos cards, mais componentes de throughput dos recursos exibidos; média acumulada, IC bootstrap percentil de 95%, 1.000 reamostragens de réplicas, seed base 1729 (seed+n por prefixo), mínimo 30 estimativas válidas, tolerância relativa 5%, tolerância absoluta zero e 15 prefixos consecutivos. Distingue início do trecho, confirmação e primeira confirmação histórica; queda posterior retira a confirmação atual. Constantes/zeros são descritivos, ausências interrompem confirmação e ficam fora da quantidade válida. Geometria/configuração não recebe inferência. Margem TLS e utilização preservam seus estimandos derivados e o bootstrap aplica as mesmas transformações/razões. Não se reutilizou o estimador de P95 agrupado da calibração para a média dos KPIs.
- Retirado o card de diagnóstico tático de horizonte de detecção e a referência pública que sugeria TTC. Compatibilidade dos parâmetros legados mantida. Limiares, amostragem e agrupamento LoWC/NMAC não mudaram. Apenas a conformidade recebeu uma correção necessária de indisponibilidade: plano de comprimento zero não gera desvio zero. Severidade mínima é indisponível em réplicas sem eventos; o card usa somente réplicas válidas, com explicação no detalhamento.
- Restaurados HTML e controles 3D em Segurança, com índice/arquivo ilustrativos. Timestamps da tabela posicionam o 3D no instante solicitado; reprodução cancelada e dados/timeline substituídos na troca de cenário. Não reativadas trajetórias/plano no mapa 2D. Tabelas, método e estabilidade permanecem recolhidos.
- Atualizados somente HTML/JS/CSS de `docs/` e respectivos hashes de cache, preservando todos os dados reais publicados. Não restaurada a calibração pública.

Validação: 87 testes unittest passaram, incluindo doze testes novos e geração completa de quatro cenários sintéticos com duas réplicas, comparada serial/paralela com ordem de entrada invertida. Testes DOM/Leaflet passaram com desenho do canvas, clique de timestamp, play, cancelamento na troca de cenário, cenário sem 3D, proteção de versão de gráficos, heatmap e mapa 2D sem trajetórias. JavaScript passou na checagem de sintaxe. O arquivo pytest isolado `test_reports_selection.py` não foi executado: pytest não está instalado e a tentativa de instalação não alcançou o índice; o mesmo caso de seleção de RUN falha foi exercitado pelo teste unittest correspondente. Foi necessário direcionar TEMP/TMP para diretório de teste dentro do workspace devido à permissão do TEMP padrão do sandbox.

QA visual: PNGs agregados inspecionados com dados sintéticos identificados como testes; evidências em `reports/dashboard_aggregation_2026-10-21/`. Navegador integrado tentou `http://127.0.0.1:8765/docs/index.html` e retornou `ERR_CONNECTION_TIMED_OUT`; não se afirma QA visual de navegador. Contratos DOM/canvas foram exercitados localmente.

Pendente de dados reais: os STATELOGs das 200 réplicas da RUN `20261015_112401_6cddab52` não estão no clone. Os novos histogramas, faixas e curvas reais só existirão após `cd ~/post-processing`, `git pull --ff-only` e `.venv/bin/python generate_reports.py --config run_config.json --workers 25` no Lessonia. Não usar `--baseline-manifest` para essa atualização. A indisponibilidade atual é intencional e não estima resultados a partir da representante/média final.
