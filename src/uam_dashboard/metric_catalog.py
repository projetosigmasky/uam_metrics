"""Rastreabilidade do Produto 3 final (versão 2.0) e diagnósticos do painel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SOURCE_DOCUMENT = "Produto3_vfinal_ProjetoSIGMASky.pdf"
SOURCE_VERSION = "Produto 3 v2.0 (31/07/2026)"
REVIEWED_ON = "2026-10-29"


def _metric(identifier: str, kpa: str, name: str, formula: str, page: str,
            equation: str | None, code: str, status: str, required: str,
            current: str, pending: str) -> dict[str, Any]:
    reference = f"{SOURCE_VERSION}, p. {page}"
    if equation:
        reference += f", Eq. {equation}"
    return {
        "reviewed_on": REVIEWED_ON,
        "presentation_group": "apoio" if identifier in {"spatial_diagnostics", "severity_exposure"} else "kpi",
        "id": identifier, "kpa": kpa, "name": name, "formula": formula,
        "pdf_reference": reference, "source_document": SOURCE_DOCUMENT,
        "code_reference": code, "status": status, "availability": status,
        "data_required": required, "implemented": current,
        "improvements_needed": pending,
    }


METRIC_CATALOG: list[dict[str, Any]] = [
    _metric('loss_of_separation', 'Segurança', 'Perdas de separação (LoWC)', 'Sh(t)<Smin_h e Sv(t)<Smin_v', '19', '3.1', 'metrics.py::detect_lowc_events', 'implementada', 'STATELOG 4D e mínimos do cenário', 'Detecta H e V estritamente abaixo dos limites; agrupa amostras do mesmo par com lacuna até 1,5×cadência. Conta LoWC, incluindo NMAC, e calcula taxas por hora e por 100 operações.', 'Validar mínimos por cenário e cobertura temporal; taxas do cenário são médias das taxas por réplica, não razão de totais.'),
    _metric('nmac', 'Segurança', 'Eventos NMAC', 'Sh<152 m e Sv<30 m', '20', None, 'metrics.py::detect_lowc_events', 'implementada', 'STATELOG 4D e limiares NMAC', 'Marca um evento LoWC como NMAC se qualquer amostra tiver H<152 m e V<30 m (padrões configuráveis).', 'Cap. 3, p. 20 usa 152 m/30 m; seção 5.5 cita 150 m. O código segue a definição do capítulo 3. Validar parâmetros por cenário.'),
    _metric('severity_exposure', 'Segurança', 'Severidade e exposição dos encontros', 'sev=min(H/Hlim,V/Vlim); exposição=Σ amostras LoWC×cadência', '38–39', None, 'metrics.py::_summarize_lowc_event; metrics.py::_safety_summary', 'implementada', 'amostras LoWC e cadência', 'Severidade mínima por evento e soma das durações dos encontros. Encontros simultâneos de pares diferentes somam exposição; não é tempo único de relógio.', 'Complemento de segurança descrito na seção 5.4, sem equação própria no capítulo 3. Sem eventos, mínimo não sustenta inferência; validar cadência.'),
    _metric('estimated_mac', 'Segurança', 'MAC esperado', 'N̂_MAC=P(MAC|NMAC)·β·N_NMAC', '20', '3.2', 'metrics.py::_safety_summary', 'parcial', 'NMAC, probabilidade condicional e β', 'NMAC×β×P(MAC|NMAC); padrões β=0,005 e P=0,005038. Calcula estimativa, sem detectar colisões MAC diretamente.', 'Calibrar P(MAC|NMAC) por Monte Carlo local; validar hipótese β para eVTOL.'),
    _metric('safety_level', 'Segurança', 'Nível de segurança e TLS', 'λ100k=N̂_MAC/H_voo×100000; λh≤TLSh; margem=TLSh/(λh+ε)', '21', '3.3–3.4', 'metrics.py::_safety_summary', 'parcial', 'MAC esperado, horas de voo e TLS', 'Normaliza por horas observadas; compara em MAC/h com TLS=8,9×10⁻⁶ (equivalente a 0,89/100 mil h). Margem usa ε=10⁻¹⁵. Agregado: média das taxas por réplica.', 'Homologar TLS; margem com ε é implementação complementar. Réplicas sem horas válidas não sustentam inferência estatística.'),
    _metric('risk_ratio', 'Segurança', 'Razão de risco', 'RR_s=MAC_100k,s/MAC_100k,ref', '21', '3.5', 'generate_dashboard.py::comparison_payload', 'parcial', 'taxas MAC e cenário sem intervenção', 'Razão entre taxas médias MAC/100 mil h do cenário e da referência definida nos metadados. Referência ausente ou taxa de referência ≤0 produz indisponível.', 'Validar referência nominal sem intervenção e comparabilidade de configuração/estágio; não estima IC pareado da razão.'),
    _metric('ground_delay', 'Eficiência', 'Atraso em solo', 'GD_f=max(0,R_f−S_f)', '22', '3.6', 'generate_dashboard.py::analyze_log', 'indisponivel', 'horários solicitado e reprogramado', 'O pipeline define available=False: não usa CRE nem primeira observação como horário autorizado. scenario_parser.py::ground_delay_metrics é função legada, não chamada pelo pipeline.', 'Ingerir horários solicitado S_f e autorizado R_f por voo e conectar cálculo formal ao pipeline.'),
    _metric('airborne_delay', 'Eficiência', 'Atraso no ar', 'AD_f=max(0,(A_f−D_f)−T_f)', '23', '3.7', 'metrics.py::airborne_delay_metrics; generate_dashboard.py::find_reference_off_log', 'parcial', 'partida, chegada e tempo nominal', 'Diferença positiva de duração observada frente a log sem desconflito pareado por instância. Para a família produto2, find_reference_off_log retorna None: indisponível nos cenários atuais.', 'Fornecer T_f nominal homologado e pareamento de mesma configuração; habilitar referência válida para os cenários atuais.'),
    _metric('total_delay', 'Eficiência', 'Atraso total', 'TD_f=GD_f+AD_f', '24', '3.8', 'metrics.py::total_delay_metrics', 'indisponivel', 'GD_f e AD_f por voo', 'Soma médias de solo e ar somente se ambos disponíveis; atualmente fica indisponível porque o pipeline não fornece GD formal.', 'Implementar componentes formais e combinação por voo com denominadores e cobertura compatíveis.'),
    _metric('flight_time', 'Eficiência', 'Tempo médio de voo', 'T̄_voo=(1/N)Σ_f(A_f−D_f)', '24', '3.9', 'metrics.py::efficiency_metrics', 'parcial', 'duração por voo e par OD', 'Média, mediana e P95 de (último−primeiro timestamp)/60 por instância de voo, com separação de reutilizações de ID.', 'Duração observada pode truncar partida/chegada; validar marcos e agregar por OD, tipo e modelo.'),
    _metric('distance', 'Eficiência', 'Distância média executada', 'd̄_real=(1/N)Σ_f d_real,f', '24', '3.10', 'metrics.py::efficiency_metrics', 'implementada', 'distância executada por voo', 'Por instância: (máximo−mínimo do odômetro distflown)/1852; exporta média, mediana e P95 em NM.', 'Validar cobertura completa do voo e odômetro; desagregar por OD, tipo e modelo.'),
    _metric('horizontal_efficiency', 'Eficiência', 'Ineficiência horizontal planejada e executada', 'HFE_plan=(d_plan−d_gc)/d_gc; HFE_real=(d_real−d_gc)/d_gc', '25', '3.11–3.12', 'metrics.py::efficiency_metrics; metrics.py::trajectory_conformity', 'parcial', 'rotas planejada/executada e grande círculo', 'HFE executada no card usa odômetro e grande círculo entre primeira/última posição observada. Pareamento ao plano também exporta HFE planejada/executada por instância e médias.', 'Grande círculo usa extremos observados; validar contra vertiportos OD. Expor ambas HFE e desagregações; cobertura sem plano permanece parcial.'),
    _metric('trajectory_conformity', 'Eficiência', 'Conformidade e distância adicional', 'TC_f=(d_real−d_plan)/d_plan; ED_f=d_real−d_plan', '26', '3.13–3.14', 'metrics.py::trajectory_conformity', 'parcial', 'trajetória executada e rota planejada', 'Pareia por ID e horário de início mais próximo, sem reutilizar plano. TC=(d_real−d_plan)/d_plan e ED=d_real−d_plan; plano de comprimento não positivo é excluído.', 'Validar pareamentos e cobertura por cenário; preservar negativos. Aderência espacial à REH é diagnóstico separado.'),
    _metric('throughput', 'Capacidade', 'Throughput por recurso', 'THR_r,Δt=N_r,Δt/|Δt|', '26', '3.15', 'capacity.py::_throughput_metrics; capacity.py::_resource_throughput; critical_waypoints.py::process_replica', 'parcial', 'passagens por recurso e janela', 'Painel: conta inícios de voo por OD/grupo e atribuição à REH planejada em janelas, normalizando para ops/h. Ranking separado: passagens interpoladas em waypoints nomeados, com reentrada e janelas completas.', 'Início/atribuição de rota não equivale a passagem efetiva em todos os recursos. Falta throughput de vertiportos; validar cobertura e janelas entre cenários.'),
    _metric('practical_capacity', 'Capacidade', 'Capacidade prática P95', 'C_r,Δt=P95(THR_r,Δt)', '27', '3.16', 'capacity.py::_resource_throughput; aggregation.py::average_resource_group; critical_waypoints.py::main', 'implementada', 'throughput por recurso em múltiplas janelas', 'Painel: P95 das taxas por janela de cada réplica, incluindo zeros; agregado é média dos P95 individuais. Ranking de waypoints: P95 das janelas completas agrupadas entre réplicas.', 'Estimadores distintos devem ser identificados. Painel mantém janela final parcial com denominador integral. Validar duração de janela e estabilidade; não é limite seguro demonstrado.'),
    _metric('utilization', 'Capacidade', 'Utilização de recurso', 'U_r,Δt=THR_r,Δt/C_r,Δt', '27', '3.17', 'capacity.py::_resource_throughput; aggregation.py::average_resource_group', 'implementada', 'throughput e capacidade prática P95', 'Por réplica, pico/P95 e média/P95 quando P95>0. No cenário, razão da média dos picos pela média dos P95. Não calcula violação de fluxo nem capacidade declarada.', 'U>1 indica excedente ao P95 empírico; validar recursos e janelas. Não interpretar como certificação de saturação operacional.'),
    _metric('flight_time_variability', 'Previsibilidade', 'Variabilidade do tempo de voo', 'σ_Tvoo e IQR=P75(T_voo)−P25(T_voo)', '28', '3.18', 'metrics.py::efficiency_metrics', 'indisponivel', 'duração por voo e par OD', 'efficiency_metrics exporta mediana e P95 de duração, mas não calcula σ_Tvoo nem IQR da Eq. 3.18.', 'Implementar desvio padrão e IQR por par OD; percentis atuais não substituem os indicadores formais.'),
    _metric('punctuality', 'Previsibilidade', 'Pontualidade', 'OTP_τ=(1/N)Σ_f I(|A_f−A_plan,f|≤τ)', '28', '3.19', '-', 'indisponivel', 'chegada/partida planejada e real', 'Não há cálculo de OTP no pipeline nem horários formais completos de partida/chegada planejada e real.', 'Definir tolerância τ, ingerir marcos e calcular OTP por OD e vertiporto.'),
    _metric('relative_degradation', 'Previsibilidade', 'Degradação relativa off-nominal', 'RD_M=|M_perturbado−M_nominal|/(M_nominal+ε)', '29', '3.20', 'generate_dashboard.py::comparison_payload', 'indisponivel', 'cenários perturbado e nominal pareados', 'comparison_payload exporta deltas absolutos de tempo/distância. Não calcula RD normalizada da Eq. 3.20.', 'Parear nominal e perturbado de mesma configuração e implementar RD por indicador.'),
    _metric('group_mean_delay', 'Equidade', 'Atraso médio por grupo', 'TD̄_g=(1/N_g)Σ_f∈g TD_f', '30', '3.21', '-', 'indisponivel', 'atraso total por voo e tipo/modelo', 'Não agrega TD por grupo; modelo/tipo podem ser anotados, mas TD formal não está disponível.', 'Calcular atraso por grupo.'),
    _metric('delay_dispersion', 'Equidade', 'Dispersão de atraso entre grupos', 'DD=(max_g TD̄_g−min_g TD̄_g)/(TD̄+ε)', '30', '3.22', '-', 'indisponivel', 'atraso médio por grupo', 'Não calculada.', 'Publicar DD com atrasos absolutos por grupo.'),
    _metric('delay_cv', 'Equidade', 'Coeficiente de variação do atraso', 'CV_delay=σ_TD/(TD̄+ε)', '30', '3.23', '-', 'indisponivel', 'atraso médio por grupo', 'Não calculado.', 'Calcular DP entre grupos.'),
    _metric('spatial_diagnostics', 'Diagnóstico complementar', 'Densidade, hotspots e cruzamentos', 'análise espacial de uso e concentração', '38–39', None, 'capacity.py::_corridor_density; capacity.py::_complexity_components', 'diagnostico', 'geometria REH/UAM e trajetórias', 'Densidade por área de corredores, hotspots, geometrias e candidatos 3D. Identificação de cruzamento não atribui capacidade. Aderência espacial permanece diagnóstico auxiliar.', 'Manter como apoio à análise de recursos, separado dos KPIs formais do capítulo 3; parâmetros geométricos e de cobertura ficam no dropdown auxiliar.'),
]


def metric_catalog_payload() -> list[dict[str, Any]]:
    return METRIC_CATALOG


def write_metric_matrix(path: Path) -> None:
    """Publish the same reviewed inventory used by the website, without recalculating results."""
    def cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")

    lines = [
        "# Matriz de KPIs aderente ao Produto III",
        "",
        f"Fonte: {SOURCE_DOCUMENT}, {SOURCE_VERSION}, capítulo 3 e seção 5.4. Revisão do código: {REVIEWED_ON}.",
        "",
        "Gerada de `src/uam_dashboard/metric_catalog.py`, a mesma fonte da tabela do site. "
        "Atualize o catálogo e execute `python prepare_publication.py` para sincronizar esta matriz e a interface publicada.",
        "",
        "Os estados descrevem a implementação no código, não a disponibilidade de cada cenário nem homologação operacional. "
        "Implementada: cálculo descrito existe; parcial: cobertura ou formulação incompleta; indisponível: cálculo formal não está conectado ou faltam entradas; diagnóstico: apoio à análise. "
        "A revisão não reprocessa STATELOGs nem altera resultados já publicados.",
        "",
        "| Área | Indicador | Fórmula / cálculo | Referência (páginas impressas) | Código | Estado | Implementado hoje | Pendências |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for metric in METRIC_CATALOG:
        keys = ("kpa", "name", "formula", "pdf_reference", "code_reference", "status", "implemented", "improvements_needed")
        lines.append("| " + " | ".join(cell(metric[key]) for key in keys) + " |")
    lines += [
        "", "## Organização da interface", "",
        "KPIs de avaliação aparecem primeiro. Recursos e hotspots têm seção própria de apoio em Capacidade. "
        "Registros, aeronaves, pico simultâneo, duração/cadência/cobertura, altitude, aderência espacial e contagens geométricas ficam em dropdowns auxiliares fechados. "
        "A estabilidade separa KPIs de diagnósticos e configurações; não modifica as séries calculadas.",
        "",
        "Severidade e exposição são complementos dos encontros de segurança; a seção 5.4 descreve severidade sem lhe atribuir uma equação própria no capítulo 3. "
        "A margem TLS com epsilon também é uma implementação complementar da comparação com TLS.",
        "",
        "Capacidade P95 é definida pela Eq. 3.16 do Produto III. A média dos P95 por réplica do painel e o P95 das janelas agrupadas do ranking de waypoints são estimadores distintos. "
        "Nenhum deles representa, por si só, limite operacional seguro demonstrado.", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_metric_catalog_asset(output_dir: Path) -> None:
    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    payload = {"document": SOURCE_DOCUMENT, "version": SOURCE_VERSION, "reviewed_on": REVIEWED_ON, "metrics": METRIC_CATALOG}
    (assets / "metric_catalog.js").write_text(
        "window.__UAM_METRIC_CATALOG__ = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Atualiza o catálogo estático do Produto 3 final.")
    parser.add_argument("--output-dir", type=Path, default=Path("docs"))
    write_metric_catalog_asset(parser.parse_args().output_dir)
