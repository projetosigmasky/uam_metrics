# Recalibração por waypoint: manutenção de 2 movimentos por 300 s

Registro de conclusão em 29/10/2026, referente à rodada nominal de 27/10/2026.

## Decisão

**Mantém-se o parâmetro experimental uniforme de 2 movimentos por recurso físico e por janela de 300 s no DCB por waypoint.** Pela regra adotada de tomar o menor dos quatro máximos de P95, a nova calibração retorna o mesmo parâmetro usado na rodada nominal. Não é necessário regenerar nem executar novamente C3.1.1, C3.1.2, C7.1.1 e C7.1.2 por motivo de alteração desse parâmetro.

Essa conclusão não altera parâmetros de DCB por quadrícula ou de desconflito micro e não constitui demonstração de capacidade operacional máxima ou de segurança.

## Origem e escopo

- RUN no Lessonia: `20261027_145945_d5905919`.
- Lote de JSONs indicado para a recalibração: `~/rmsp/scenarios/product2/nominal_36_20261027`.
- Baselines sem gestão: C1.1, C1.2, C2.1 e C2.2, com 50 réplicas de cada cenário, totalizando 200.
- Passagens: WPPASS nativos da execução, associados aos JSONs originais dos recursos físicos.
- Não foram necessárias novas simulações para obter a calibração.

A revisão foi motivada, conforme informado pela equipe, pelo descarte da rodada de 15/10 devido ao fallback de modelo de aeronave B744 e pelas mudanças de velocidade para 70–90 kt e realinhamento de B06/AS65 na rodada nova. O fallback de aeronave é distinto da antiga discussão sobre um piso numérico de uma operação em recursos sem uso.

## Método e resultado informado

O estimando é o P95 empírico, com quantil `higher`, das contagens em janelas completas e positivas de 300 s, reunidas entre as réplicas e calculadas separadamente por recurso físico. A calibração utiliza bootstrap por réplica inteira para avaliar incerteza. Não se trata da média dos P95 individuais, da soma de capacidades de waypoints nem de uma agregação de recursos apenas pelo nome.

Para cada cenário, toma-se o maior P95 entre seus recursos com estimativa observada. Em seguida, a regra experimental de escolha do parâmetro uniforme toma o menor desses quatro máximos:

| Cenário | Vertiportos | Réplicas | Maior P95 positivo (movimentos/300 s) |
| --- | ---: | ---: | ---: |
| C1.1 | 6 | 50 | 2 |
| C1.2 | 12 | 50 | 3 |
| C2.1 | 6 | 50 | 2 |
| C2.2 | 12 | 50 | 3 |

**Parâmetro adotado = mínimo(2, 3, 2, 3) = 2 movimentos/300 s.** O valor é uma contagem por janela; não representa um headway uniforme de 150 s entre passagens.

Os quatro máximos coincidem com os valores informados para a calibração anterior. Isso não implica igualdade entre as duas rodadas nas distribuições por recurso, nas sequências de passagem, nos intervalos de confiança ou nos resultados de estabilidade.

## Rastreabilidade e limites deste registro

Os valores acima foram transcritos da saída de terminal fornecida pelo usuário após a recalibração no Lessonia. O script de extração leu `docs/assets/data/baseline_calibration/calibration.json`, selecionou `300:positive` e verificou, para cada baseline:

- 50 réplicas e `passage_source == "native"`;
- estados dos recursos restritos a `observed` ou `no_observed_use`;
- existência de pelo menos uma estimativa observada antes de calcular o máximo.

Este registro documenta a decisão a partir dessa saída; não apresenta uma auditoria independente dos arquivos da nova rodada. Os IDs dos recursos que atingem os máximos, seus ICs e sua estabilidade não constam da saída recebida e não são inferidos aqui.

No momento deste registro, o `calibration.json` deste clone local ainda referencia a RUN de 15/10. Ele não deve ser citado como evidência numérica da rodada de 27/10. Os arquivos detalhados da nova calibração devem ser sincronizados do Lessonia com sua proveniência e hashes antes da publicação das evidências completas.

## Fechamento das evidências

1. Sincronizar os CSVs, JSON e figuras reais da nova calibração, preservando a rastreabilidade do histórico de 20/10.
2. Adequar `scripts/build_baseline_capacity_evidence.py` antes de gerar as evidências da rodada nova: retirar a data fixa de 20/10 e tratar classes ou exemplos estáveis ausentes sem supor que o novo lote repete a distribuição anterior.
3. Gerar as figuras e tabelas detalhadas nesta pasta, sem sobrescrever o pacote histórico de 20/10. Este arquivo `CONCLUSAO.md` é separado do `README.md` produzido pelo gerador para preservar a decisão registrada.
4. Registrar os recursos responsáveis pelos máximos e examinar seus ICs e estabilidade, sem atribuir comprovação de segurança ao parâmetro escolhido.

Esta atualização é documental e não modifica configurações nem inicia simulações. Se evidências posteriores mudarem o parâmetro ou revelarem problemas de validade, a decisão deverá ser revista com a equipe antes de novas simulações.

## Texto para o relatório

> A recalibração dos quatro baselines sem gestão da execução `20261027_145945_d5905919`, com 50 réplicas por cenário e passagens WPPASS nativas, resultou em máximos de P95 de fluxo de 2, 3, 2 e 3 movimentos por janela positiva de 300 s para C1.1, C1.2, C2.1 e C2.2, respectivamente. Pela regra de seleção do menor desses quatro máximos, manteve-se o parâmetro experimental uniforme de 2 movimentos por recurso físico e por janela de 300 s no DCB por waypoint. A manutenção desse parâmetro não exige regeneração dos cenários que já o utilizam. Trata-se de referência empírica condicionada à demanda e ao tratamento da ociosidade, sem demonstração de capacidade operacional máxima ou de segurança.
