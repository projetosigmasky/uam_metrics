# Matriz de KPIs aderente ao Produto 3

Fonte normativa: *Projeto SIGMA-Sky - Produto 3*, seção 4 e Tabela 4.1 (páginas impressas 28-44). Este arquivo relaciona somente métricas que permanecem no projeto. Diagnósticos sem amparo como KPI (frequência de trajetórias, aderência espacial à REH, perfil cinemático, taxa por 1.000 km e proxy de tempo até conflito) foram removidos do cálculo de avaliação e do catálogo.

| Nome do KPI | Formulação matemática | Função da métrica | Situação no projeto | Página que ampara |
|---|---|---|---|---|
| Perda de separação / LoWC | `Sh(t) < Smin_h e Sv(t) < Smin_v`; total, por hora de voo e por 100 operações | Frequência de encontros abaixo do mínimo operacional | Implementada; eventos e localização preservados | 28, Eq. 4.1 |
| NMAC | Evento de proximidade crítica com limiares do cenário | Mede quase-colisões | Implementada | 29-31 |
| MAC estimado | `N_MAC = P(MAC\|NMAC) * beta * N_NMAC`; `MAC_100k = N_MAC/H_voo * 100000` | Risco esperado normalizado | Implementada; parâmetros rotulados conforme o PDF | 30-31, Eqs. 4.3-4.8 |
| Severidade e permanência sob limiar | `sev_ij = min_t(Sh/Smin_h, Sv/Smin_v)` | Gradua o pior instante e a duração do encontro | Implementada e corrigida para `min` | 32-33, Eq. 4.9 |
| Razão de risco | `RR_s = MAC_100k,s / MAC_100k,ref` | Compara risco ao cenário de referência | Implementada | 33, Eq. 4.10 |
| Conformidade com TLS | `lambda_MAC <= TLS`; `M_TLS = TLS/(lambda_MAC + epsilon)` | Critério de aceitação e margem de segurança | Implementada | 33-34, Eqs. 4.11-4.12 |
| Atraso em solo | `GD_f = max(0, R_f - S_f)` | Penalidade antes da partida | Indisponível sem dados formais | 34, Eq. 4.13 |
| Atraso no ar | `AD_f = max(0, (A_f-D_f)-T_f)` | Custo de manobra, espera ou desvio | Parcial; aceita referência nominal homologada | 35, Eq. 4.14 |
| Atraso total | `TD_f = GD_f + AD_f` | Custo temporal total | Indisponível enquanto `GD_f` não existir | 35, Eq. 4.15 |
| Pontualidade operacional | `OTP_tau = (1/N) sum I(\|A_f-Aplan_f\| <= tau)` | Chegadas dentro da tolerância | Indisponível sem horários de chegada | 36, Eq. 4.16 |
| Tempo médio e variabilidade de voo | `T_voo = (1/N) sum(A_f-D_f)`; DP, IQR e P85-P15 por OD | Duração e previsibilidade de voo | Parcial: duração observada e percentis globais | 36 e 43, Eq. 4.17 |
| Distância média executada | `d_real_bar = (1/N) sum d_real,f` | Extensão percorrida | Implementada | 36-37, Eq. 4.18 |
| Conformidade e distância adicional | `TC_f=(d_real-d_plan)/d_plan`; `ED_f=d_real-d_plan` | Desvio da execução frente ao plano | Implementada | 37, Eqs. 4.19-4.20 |
| Eficiência horizontal planejada/executada | `HFE_plan=(d_plan-d_gc)/d_gc`; `HFE_real=(d_real-d_gc)/d_gc` | Extensão frente à rota ideal | Implementada | 38, Eqs. 4.21-4.22 |
| Densidade de tráfego e hotspots | `ATD_dt=N_simultaneo,dt/A` | Concentração espacial de tráfego | Implementada | 39, Eq. 4.23 |
| Proxies de complexidade | Cruzamentos, convergências, waypoints restritivos e conflitos potenciais | Contextualiza hotspots; não é índice composto | Implementada como apoio | 39 |
| Throughput por recurso | `THR_r,dt=N_r,dt/\|dt\|` | Fluxo por recurso e janela | Implementada | 40, Eq. 4.24 |
| Utilização, ocupação e violação de fluxo | `U=N/C`; `VFC=max(0,N-C)` | Saturação e excedente por recurso | Indisponível sem capacidade declarada | 41-42, Eqs. 4.25-4.26 |
| Variabilidade de atrasos e confiabilidade | Dispersão/percentis de atraso e planejado versus real por OD | Regularidade temporal | Indisponível sem dados de horários/atrasos formais | 43 |
| Equidade na gestão do tráfego | `TD_g=(1/N_g)sum TD_f`; `EQ_delay=(max(TD_g)-min(TD_g))/(TD_bar+epsilon)` | Assimetria de atraso entre tipos/modelos | Indisponível enquanto `TD_f` não existir | 43-44, Eqs. 4.27-4.28 |

## Pontos que dependem de decisão ou dados do responsável

1. **Atraso em solo:** definir e fornecer, por voo, o horário solicitado `S_f` e o autorizado/reprogramado `R_f`. O comando `CRE` e a primeira amostra do STATELOG não serão mais usados como proxy.
2. **Atraso no ar, pontualidade, confiabilidade e variabilidade:** definir a fonte oficial de `D_f`, `A_f`, `Aplan_f` e do tempo nominal `T_f`; confirmar se uma execução nominal pareada pode representar `T_f`.
3. **Utilização e violação de capacidade:** fornecer `C_r,dt` declarado ou aprovar um protocolo de ensaio de saturação para cada vertiporto, rota, corredor e waypoint. O P95 do throughput observado não é capacidade e foi retirado como denominador.
4. **MAC/TLS:** homologar o TLS e decidir entre calibração local de `P(MAC|NMAC)` por Monte Carlo ou manutenção temporária do valor de Chen et al. (2024). Também registrar, por cenário, os limiares horizontais e verticais de LoWC/NMAC/MAC.
5. **Referência para razão de risco:** confirmar qual cenário nominal sem intervenção será a referência quando houver mais de uma alternativa comparável.
