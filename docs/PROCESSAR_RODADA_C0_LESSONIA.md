# Processar a rodada C0 + 36 variantes no Lessonia

Esta rodada contém 37 cenários, com 50 STATELOGs por cenário (1.850 no total).
C0 é a referência com apenas helicópteros, sem estágio de vertiportos e sem
corredor UAM. Sua definição adicional vem de
`rmsp-uam-simulations/uam_sim/scenarios/nominal.py:C0_DEFINITION`; as 36 variantes
da planilha mantêm seus identificadores. O pós-processamento inclui C0 no
catálogo, na seleção dos logs e nas métricas e rankings de recursos REH.
A apresentação de C0 nos seletores do frontend deve oferecer vertiportos `0`
como “Não se aplica”; essa alteração de interface é tratada separadamente.

## 1. Atualizar o código e identificar a RUN

As mudanças locais deste suporte precisam chegar ao clone do servidor antes
do processamento. Depois de disponibilizadas no remoto do projeto:

```bash
cd ~/post-processing
git pull --ff-only
.venv/bin/python -m pip install -r requirements.txt
ls -1 /dados/matosdfm/runs
```

Se o ambiente ainda não existir, crie com `python3 -m venv .venv` antes do pip.
Use o ID da RUN completa nova, não o piloto. Confirme `completed` no orquestrador
ou nos arquivos `lifecycle.json` e `summary.json` da RUN. Ter 1.850 arquivos
não basta se o executor ainda estiver ativo ou houver réplicas com erro.

## 2. Executar o processamento completo

Substitua o valor de `RUN_ID` pelo identificador real:

```bash
cd ~/post-processing
RUN_ID='SUBSTITUA_PELO_ID_DA_RUN_NOVA'
.venv/bin/python generate_reports.py \
  --config run_config.json \
  --run-id "$RUN_ID" \
  --runs-root /dados/matosdfm/runs \
  --workers 25
```

O config inclui os 37 códigos. Fixar `--run-id` exige todos eles na mesma RUN;
não há fallback para resultados de outubro. Antes de gerar relatórios, a seleção
exige conclusão sem erros, 50 STATELOGs por cenário, índices de réplica 1–50,
pareamento único com SCNs P100/OFF e geometrias dedicadas compatíveis. A seleção
é gravada em `run_config.local.json`. O fluxo não inicia novas simulações.

Para deixar o processamento continuar após desconectar o SSH, use este comando
no lugar da execução em primeiro plano:

```bash
nohup .venv/bin/python -u generate_reports.py \
  --config run_config.json \
  --run-id "$RUN_ID" \
  --runs-root /dados/matosdfm/runs \
  --workers 25 \
  > "postprocess_${RUN_ID}.log" 2>&1 < /dev/null &
tail -f "postprocess_${RUN_ID}.log"
```

O `Ctrl+C` encerra somente o acompanhamento do `tail`. A conclusão bem-sucedida
é registrada por `Dashboard and waypoint ranking ready in docs/`; consulte
também eventuais erros anteriores no log. Dashboard e ranking executam em
sequência, cada um com até 25 processos. Evite executar junto de outra rodada
pesada de simulação ou de outro gerador de relatórios neste mesmo clone.

## 3. Interpretar e recuperar os resultados

O dashboard usa a média dos KPIs calculados por réplica, com cobertura e
análise de estabilidade/IC por bootstrap. Não escolhe a réplica de melhor
resultado. Mapas de eventos e trajetórias ilustram uma réplica identificada.
O ranking de waypoints usa o P95 das janelas completas agrupadas; esse estimador
é diferente da média dos P95 individuais usada em cartões do dashboard.

A análise de estabilidade verifica se o IC atende aos critérios configurados
ao longo das réplicas. Cinquenta réplicas não garantem confirmação para todos
os KPIs. Resultados indisponíveis não se tornam zero. C0 não é automaticamente
usado como referência de atraso dos cenários mistos: a composição de tráfego
é diferente.

A saída publicável fica em `docs/`, incluindo fragmentos de cenário em
`docs/assets/data/runs/`, gráficos e rankings em
`docs/assets/data/critical_waypoints/`. Auditorias completas ficam no servidor,
conforme `PUBLICACAO.md`. Transfira o conjunto publicado e seus assets de forma
coerente; preserve uma cópia da publicação anterior antes de substituí-la.

A calibração de capacidade por WPPASS é um fluxo independente
(`prepare_baseline_manifest.py` + `generate_reports.py --baseline-manifest ...`).
Ela continua dedicada aos quatro baselines C1.1/C1.2/C2.1/C2.2, não aos 37 cenários.
Caso seja necessária uma nova calibração, use os JSONs originais e WPPASS
**desta rodada**. A política REH mudou para `legacy_right_hand_v1`; não reutilize
automaticamente os números antigos como se fossem medições desta geometria.

## Mapas por área de desempenho

Os boxplots usam os valores individuais por réplica já publicados. As novas
camadas de eficiência, quadrícula e previsibilidade precisam dos STATELOGs
e SCNs. Para regenerar as camadas para todos os 37 cenários, no Lessonia:

```bash
cd ~/post-processing
git pull --ff-only
.venv/bin/python generate_reports.py --config run_config.json \
  --run-id 20261103_155621_68fee947 \
  --runs-root /dados/matosdfm/runs --workers 25
```

O ID fixa a mesma RUN dos 37 cenários publicados em novembro. O gerador
não executa novas simulações.

- **Eficiência:** agrupa voos pela geometria planejada e calcula uma trajetória
  média com amostras alinhadas pela fração da distância percorrida. As cores
  usam o excesso médio sobre a distância direta ou sobre o plano, com piso
  zero para excesso negativo. A comparação usa voos com pelo menos duas
  observações e início e fim a até 1 km das extremidades planejadas.
- **Capacidade:** exibe waypoints elegíveis com passagens observadas e P95
  estimado. A quadrícula analítica de 0,01° mostra a média dos picos de
  voos distintos por célula em janelas completas de 5 min. Cada voo conta
  uma vez por célula e janela. As duas camadas medem carga observada e
  ajudam a localizar concentrações de tráfego.
- **Previsibilidade:** agrupa as durações observadas por par OD planejado e
  sentido, usando o mesmo critério de cobertura da eficiência. O mapa mostra
  IQR ou desvio padrão amostral com pelo menos dois voos. A pontualidade de
  chegada e os atrasos em solo exigem outras fontes.
- **Segurança:** os eventos e o 3D mostram a réplica ilustrativa. Em
  **Equidade**, a geometria OD é exibida como contexto.

Ao final, revise e publique os arquivos gerados:

```bash
git add -A docs/
git diff --cached --stat
git commit -m "Publica camadas temáticas dos 37 cenários"
git push origin HEAD:main
```

As auditorias locais `waypoints_by_replica.csv` e `passage_events.jsonl`
ficam fora da publicação, assim como as cópias JSON completas por cenário.
