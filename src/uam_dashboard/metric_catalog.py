"""Catálogo dos KPIs do Produto 3, sem proxies ou diagnósticos extras."""
from __future__ import annotations

from typing import Any


def _metric(metric_id: str, name: str, formula: str, reference: str, code: str,
            status: str, data_required: str, note: str) -> dict[str, Any]:
    return {"id": metric_id, "name": name, "formula": formula,
            "pdf_reference": reference, "code_reference": code, "status": status,
            "availability": status, "data_required": data_required,
            "implemented": note, "improvements_needed": note}


METRIC_CATALOG: list[dict[str, Any]] = [
    _metric("loss_of_separation", "Perda de separação / LoWC", "Sh(t)<Smin_h e Sv(t)<Smin_v; taxas por H_voo e 100 operações", "Produto 3, p. 28, Eq. 4.1", "metrics.py::detect_lowc_events", "implementada", "STATELOG 4D, limites do cenário e instâncias", "Conta encontros, preserva localização e normaliza por exposição."),
    _metric("nmac", "NMAC", "evento NMAC; taxa por H_voo e 100 operações", "Produto 3, pp. 29-31", "metrics.py::detect_lowc_events", "implementada", "STATELOG 4D e limiares NMAC", "Os limiares devem ser definidos e versionados por cenário."),
    _metric("estimated_mac", "MAC estimado", "N_MAC=P(MAC|NMAC)*beta*N_NMAC; MAC_100k=N_MAC/H_voo*100000", "Produto 3, pp. 30-31, Eqs. 4.3-4.8", "metrics.py::_safety_summary", "implementada", "NMAC, beta, P(MAC|NMAC) e H_voo", "Usa calibração provisória; decisão de calibração local permanece pendente."),
    _metric("proximity_severity", "Severidade mínima e permanência sob limiar", "sev_ij=min_t(Sh/Smin_h, Sv/Smin_v)", "Produto 3, pp. 32-33, Eq. 4.9", "metrics.py::detect_lowc_events", "implementada", "separação horizontal e vertical por evento", "Calculada por evento e agregada por distribuição."),
    _metric("risk_ratio", "Razão de risco", "RR_s=MAC_100k,s/MAC_100k,ref", "Produto 3, p. 33, Eq. 4.10", "generate_dashboard.py::comparison_payload", "implementada", "taxas MAC e cenário de referência", "A referência é o cenário nominal sem intervenção quando disponível."),
    _metric("tls", "Conformidade e margem TLS", "lambda_MAC<=TLS; M_TLS=TLS/(lambda_MAC+epsilon)", "Produto 3, pp. 33-34, Eqs. 4.11-4.12", "metrics.py::_safety_summary", "implementada", "taxa MAC e TLS homologado", "O TLS é critério de aceitação, não evento observado."),
    _metric("ground_delay", "Atraso em solo", "GD_f=max(0,R_f-S_f)", "Produto 3, p. 34, Eq. 4.13", "scenario_parser.py::ground_delay_metrics", "indisponivel", "horários solicitado e autorizado/reprogramado", "O STATELOG atual não contém R_f; nenhuma proxy é publicada."),
    _metric("airborne_delay", "Atraso no ar", "AD_f=max(0,(A_f-D_f)-T_f)", "Produto 3, p. 35, Eq. 4.14", "metrics.py::airborne_delay_metrics", "parcial", "marcos D_f/A_f e tempo nominal T_f", "Pode usar execução nominal pareada como T_f, se homologada."),
    _metric("total_delay", "Atraso total", "TD_f=GD_f+AD_f", "Produto 3, pp. 35-36, Eq. 4.15", "metrics.py::total_delay_metrics", "indisponivel", "GD_f e AD_f por voo", "Fica indisponível até haver atraso em solo formal."),
    _metric("punctuality", "Pontualidade operacional", "OTP_tau=(1/N)*sum I(|A_f-Aplan_f|<=tau)", "Produto 3, p. 36, Eq. 4.16", "-", "indisponivel", "chegada real, chegada planejada e tolerância", "Campos de chegada planejada e real não estão disponíveis."),
    _metric("flight_time", "Tempo médio e variabilidade de voo", "T_voo=(1/N)*sum(A_f-D_f); DP, IQR e P85-P15 por OD", "Produto 3, pp. 36 e 43, Eq. 4.17", "metrics.py::efficiency_metrics", "parcial", "marcos D_f/A_f e par OD", "A duração observada e percentis existem; faltam marcos formais e agregação por OD."),
    _metric("distance", "Distância média executada", "d_real_bar=(1/N)*sum d_real,f", "Produto 3, pp. 36-37, Eq. 4.18", "metrics.py::efficiency_metrics", "implementada", "distância executada por voo", "Reportada com distribuição."),
    _metric("trajectory_conformity", "Conformidade e distância adicional", "TC_f=(d_real-d_plan)/d_plan; ED_f=d_real-d_plan", "Produto 3, p. 37, Eqs. 4.19-4.20", "metrics.py::trajectory_conformity", "implementada", "trajetória executada e rota planejada", "Não confundir com aderência espacial a polígonos REH."),
    _metric("horizontal_efficiency", "Eficiência horizontal planejada e executada", "HFE_plan=(d_plan-d_gc)/d_gc; HFE_real=(d_real-d_gc)/d_gc", "Produto 3, p. 38, Eqs. 4.21-4.22", "metrics.py::trajectory_conformity", "implementada", "rotas planejada/executada e grande círculo", "Mantém as duas variantes formais."),
    _metric("traffic_density", "Densidade de tráfego e hotspots", "ATD_dt=N_simultaneo,dt/A", "Produto 3, p. 39, Eq. 4.23", "capacity.py::_corridor_density", "implementada", "posição, tempo e área do recurso", "Densidade é distinta de utilização."),
    _metric("complexity", "Proxies de complexidade", "cruzamentos, waypoints restritivos, conflitos potenciais e fluxos convergentes", "Produto 3, p. 39", "capacity.py::_complexity_components", "implementada", "geometria da rede e eventos", "Métrica de apoio; não é índice composto."),
    _metric("throughput", "Throughput por recurso", "THR_r,dt=N_r,dt/|dt|", "Produto 3, p. 40, Eq. 4.24", "capacity.py::_resource_throughput", "implementada", "uso do recurso e janela temporal", "Distingue fluxo observado de capacidade declarada."),
    _metric("utilization", "Utilização, ocupação e violação de capacidade", "U_r,dt=N_r,dt/C_r,dt; VFC_r,dt=max(0,N_r,dt-C_r,dt)", "Produto 3, pp. 41-42, Eqs. 4.25-4.26", "capacity.py", "indisponivel", "capacidade declarada por recurso/janela", "Sem C_r,dt homologada, utilização e violação não são calculadas."),
    _metric("delay_variability", "Variabilidade de atrasos e confiabilidade", "DP/IQR/percentis de atrasos; planejado versus realizado por OD", "Produto 3, p. 43", "-", "indisponivel", "atrasos e horários planejados/reais por OD", "Depende dos mesmos dados de atraso e pontualidade."),
    _metric("equity", "Equidade na gestão do tráfego", "TD_g=(1/N_g)*sum TD_f; EQ_delay=(max(TD_g)-min(TD_g))/(TD_bar+epsilon)", "Produto 3, pp. 43-44, Eqs. 4.27-4.28", "-", "indisponivel", "atraso total e tipo/modelo por voo", "Tipo/modelo existe; atraso total formal ainda não."),
]


def metric_catalog_payload() -> list[dict[str, Any]]:
    return METRIC_CATALOG
