"""Rastreabilidade do Produto 3 final (versão 2.0) e diagnósticos do painel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SOURCE_DOCUMENT = "Produto3_vfinal_ProjetoSIGMASky.pdf"
SOURCE_VERSION = "Produto 3 v2.0 (31/07/2026)"


def _metric(identifier: str, kpa: str, name: str, formula: str, page: str,
            equation: str | None, code: str, status: str, required: str,
            current: str, pending: str) -> dict[str, Any]:
    reference = f"{SOURCE_VERSION}, p. {page}"
    if equation:
        reference += f", Eq. {equation}"
    return {
        "id": identifier, "kpa": kpa, "name": name, "formula": formula,
        "pdf_reference": reference, "source_document": SOURCE_DOCUMENT,
        "code_reference": code, "status": status, "availability": status,
        "data_required": required, "implemented": current,
        "improvements_needed": pending,
    }


METRIC_CATALOG: list[dict[str, Any]] = [
    _metric("loss_of_separation", "Segurança", "Perdas de separação (LoWC)", "Sh(t)<Smin_h e Sv(t)<Smin_v", "19", "3.1", "metrics.py::detect_lowc_events", "implementada", "STATELOG 4D e mínimos do cenário", "Conta eventos, localização e exposição.", "Validar mínimos operacionais por cenário."),
    _metric("nmac", "Segurança", "Eventos NMAC", "Sh<152 m e Sv<30 m", "20", None, "metrics.py::detect_lowc_events", "implementada", "STATELOG 4D e limiares NMAC", "Conta NMAC com padrões 152 m/30 m.", "Validar limiares em análises de sensibilidade."),
    _metric("estimated_mac", "Segurança", "MAC esperado", "N̂_MAC=P(MAC|NMAC)·β·N_NMAC", "20", "3.2", "metrics.py::_safety_summary", "parcial", "NMAC, probabilidade condicional e β", "Estima MAC com β=0,005 provisório.", "Calibrar P(MAC|NMAC) e validar β para eVTOL."),
    _metric("safety_level", "Segurança", "Nível de segurança e TLS", "λ_MAC=N̂_MAC/H_voo·100000; λ_MAC≤TLS", "21", "3.3–3.4", "metrics.py::_safety_summary", "parcial", "MAC esperado, horas de voo e TLS", "Calcula taxa e compara com TLS configurado.", "Usar referência provisória de 0,89 MAC/100 mil h ou meta nacional."),
    _metric("risk_ratio", "Segurança", "Razão de risco", "RR_s=MAC_100k,s/MAC_100k,ref", "21", "3.5", "generate_dashboard.py::comparison_payload", "parcial", "taxas MAC e cenário sem intervenção", "Compara quando o denominador é positivo.", "Parear réplicas e referência equivalente."),
    _metric("ground_delay", "Eficiência", "Atraso em solo", "GD_f=max(0,R_f−S_f)", "22", "3.6", "scenario_parser.py::ground_delay_metrics", "indisponivel", "horários solicitado e reprogramado", "Não publica proxy sem R_f.", "Registrar S_f, R_f e causa do atraso."),
    _metric("airborne_delay", "Eficiência", "Atraso no ar", "AD_f=max(0,(A_f−D_f)−T_f)", "23", "3.7", "metrics.py::airborne_delay_metrics", "parcial", "partida, chegada e tempo nominal", "Usa execução nominal pareada quando disponível.", "Validar T_f planejado por voo."),
    _metric("total_delay", "Eficiência", "Atraso total", "TD_f=GD_f+AD_f", "24", "3.8", "metrics.py::total_delay_metrics", "indisponivel", "GD_f e AD_f por voo", "Indisponível sem GD_f formal.", "Registrar ambos os componentes."),
    _metric("flight_time", "Eficiência", "Tempo médio de voo", "T̄_voo=(1/N)Σ_f(A_f−D_f)", "24", "3.9", "metrics.py::efficiency_metrics", "parcial", "duração por voo e par OD", "Calcula média e percentis gerais.", "Agregar por OD, tipo e modelo."),
    _metric("distance", "Eficiência", "Distância média executada", "d̄_real=(1/N)Σ_f d_real,f", "24", "3.10", "metrics.py::efficiency_metrics", "implementada", "distância executada por voo", "Calcula média e distribuição.", "Desagregar por OD, tipo e modelo."),
    _metric("horizontal_efficiency", "Eficiência", "Ineficiência horizontal planejada e executada", "HFE_plan=(d_plan−d_gc)/d_gc; HFE_real=(d_real−d_gc)/d_gc", "25", "3.11–3.12", "metrics.py::trajectory_conformity", "parcial", "rotas planejada/executada e grande círculo", "Calcula quando há .scn associado.", "Cobrir todos os voos e desagregar por OD."),
    _metric("trajectory_conformity", "Eficiência", "Conformidade e distância adicional", "TC_f=(d_real−d_plan)/d_plan; ED_f=d_real−d_plan", "26", "3.13–3.14", "metrics.py::trajectory_conformity", "parcial", "trajetória executada e rota planejada", "Calcula quando o plano é recuperado.", "Reportar por voo, OD e corredor."),
    _metric("throughput", "Capacidade", "Throughput por recurso", "THR_r,Δt=N_r,Δt/|Δt|", "26", "3.15", "capacity.py::_resource_throughput", "parcial", "passagens por recurso e janela", "Calcula fluxo de pares OD, trajetórias e REH.", "Acrescentar vertiportos e janelas curtas comparáveis."),
    _metric("practical_capacity", "Capacidade", "Capacidade prática P95", "C_r,Δt=P95(THR_r,Δt)", "27", "3.16", "capacity.py::_resource_throughput", "implementada", "throughput por recurso em múltiplas janelas", "Calcula o P95 empírico dos fluxos por janela.", "Validar janela de 5/10/15 min e estabilidade entre réplicas."),
    _metric("utilization", "Capacidade", "Utilização de recurso", "U_r,Δt=THR_r,Δt/C_r,Δt", "27", "3.17", "capacity.py::_resource_throughput", "implementada", "throughput e capacidade prática P95", "Calcula quando P95 é positivo.", "Interpretar U>1 como saturação relativa ao P95."),
    _metric("flight_time_variability", "Previsibilidade", "Variabilidade do tempo de voo", "σ_Tvoo e IQR=P75(T_voo)−P25(T_voo)", "28", "3.18", "metrics.py::efficiency_metrics", "parcial", "duração por voo e par OD", "Disponibiliza percentis gerais.", "Calcular DP e IQR por par OD."),
    _metric("punctuality", "Previsibilidade", "Pontualidade", "OTP_τ=(1/N)Σ_f I(|A_f−A_plan,f|≤τ)", "28", "3.19", "-", "indisponivel", "chegada/partida planejada e real", "Marcos completos indisponíveis.", "Definir τ e registrar horários por OD e vertiporto."),
    _metric("relative_degradation", "Previsibilidade", "Degradação relativa off-nominal", "RD_M=|M_perturbado−M_nominal|/(M_nominal+ε)", "29", "3.20", "generate_dashboard.py::comparison_payload", "indisponivel", "cenários perturbado e nominal pareados", "A tabela mostra diferenças absolutas, não RD formal.", "Parear réplicas e calcular RD por indicador."),
    _metric("group_mean_delay", "Equidade", "Atraso médio por grupo", "TD̄_g=(1/N_g)Σ_f∈g TD_f", "30", "3.21", "-", "indisponivel", "atraso total por voo e tipo/modelo", "Tipo/modelo existe; falta TD_f formal.", "Calcular atraso por grupo."),
    _metric("delay_dispersion", "Equidade", "Dispersão de atraso entre grupos", "DD=(max_g TD̄_g−min_g TD̄_g)/(TD̄+ε)", "30", "3.22", "-", "indisponivel", "atraso médio por grupo", "Não calculada.", "Publicar DD com atrasos absolutos por grupo."),
    _metric("delay_cv", "Equidade", "Coeficiente de variação do atraso", "CV_delay=σ_TD/(TD̄+ε)", "30", "3.23", "-", "indisponivel", "atraso médio por grupo", "Não calculado.", "Calcular DP entre grupos."),
    _metric("spatial_diagnostics", "Diagnóstico complementar", "Densidade, hotspots e cruzamentos", "análise espacial de uso e concentração", "38–39", None, "capacity.py::_corridor_density; capacity.py::_complexity_components", "diagnostico", "geometria REH/UAM e trajetórias", "Exibe área, densidade, candidatos e eventos.", "Seção 5.4 descreve a interface; não há fórmula correspondente no capítulo 3."),
]


def metric_catalog_payload() -> list[dict[str, Any]]:
    return METRIC_CATALOG


def write_metric_catalog_asset(output_dir: Path) -> None:
    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    payload = {"document": SOURCE_DOCUMENT, "version": SOURCE_VERSION, "metrics": METRIC_CATALOG}
    (assets / "metric_catalog.js").write_text(
        "window.__UAM_METRIC_CATALOG__ = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Atualiza o catálogo estático do Produto 3 final.")
    parser.add_argument("--output-dir", type=Path, default=Path("docs"))
    write_metric_catalog_asset(parser.parse_args().output_dir)
