from __future__ import annotations

from typing import Any


def _metric(
    metric_id: str,
    name: str,
    formula: str,
    reference: str,
    code: str,
    status: str,
    availability: str,
    data_required: str,
    implemented: str,
    improvements_needed: str,
) -> dict[str, Any]:
    return {
        "id": metric_id,
        "name": name,
        "formula": formula,
        "pdf_reference": reference,
        "code_reference": code,
        "status": status,
        "availability": availability,
        "data_required": data_required,
        "implemented": implemented,
        "improvements_needed": improvements_needed,
    }


# A rastreabilidade separa deliberadamente disponibilidade tecnica de
# validade operacional. "Parcial" significa que o calculo existe, mas ainda
# depende de parametro, referencia ou validacao externa.
METRIC_CATALOG: list[dict[str, Any]] = [
    _metric(
        "fleet_mix", "Composicao da frota", "contagem de operacoes por tipo e modelo",
        "Diagnostico operacional complementar", "scenario_parser.py::annotate_aircraft_metadata",
        "Implementada com metadados dos cenarios C1/C2", "implementada",
        "CRE do SCN, id e instancias do STATELOG",
        "Tipo e modelo sao lidos do comando CRE e associados a cada amostra.",
        "Validar a taxonomia e manter um cadastro mestre de aeronaves.",
    ),
    _metric(
        "kinematic_profile", "Perfil cinematico observado",
        "estatisticas de altitude, CAS, TAS, GS, VS, rumo e trilha",
        "Diagnostico operacional complementar", "log_parser.py::load_state_log; metrics.py::build_summary",
        "Implementada com os campos estendidos do STATELOG", "implementada",
        "alt, cas, tas, gs, vs, hdg e trk", "Todos os campos estendidos sao preservados e resumidos.",
        "Definir envelopes e limites operacionais por modelo.",
    ),
    _metric(
        "interactive_3d_visualization", "Visualizacao 3D temporal",
        "posicao=(lon,lat,alt) em janelas temporais regulares",
        "Produto visual complementar", "exports.py::trajectory_3d_payload; web/assets/dashboard.js::draw3D",
        "Implementada com amostragem configuravel de 5 segundos", "implementada",
        "simt, id, lat, lon, alt e tipo de veiculo",
        "Anima aeronaves com silhuetas vetoriais e lista LoWC/NMAC por timestamp; o plano-base usa 2.621 pes MSL.",
        "Validar o MSL de referencia; substituir o plano medio por modelo digital de elevacao se houver terreno confiavel.",
    ),
    _metric(
        "trajectory_frequency", "Frequencia de trajetorias semelhantes",
        "contagem de instancias com origem, destino e forma dentro das tolerancias",
        "Produto 3 v1, secoes 3.2 e 6", "exports.py::tracks_geojson",
        "Implementada como agrupamento configuravel de trajetorias observadas", "implementada",
        "simt, id, lat, lon e distflown", "Agrupa formas executadas e informa frequencia e volume relativo.",
        "Calibrar tolerancias e validar grupos contra rotas reconhecidas.",
    ),
    _metric(
        "lowc_events", "Loss of Well Clear 3D", "Sh(t) < Smin_h e Sv(t) < Smin_v",
        "Produto 3 v1, criterio de separacao", "metrics.py::detect_lowc_events",
        "Implementada em 3D com limites horizontal e vertical configuraveis", "parcial",
        "simt, id, lat, lon, alt e limites de separacao",
        "Detecta e consolida eventos em 1 s e os separa por combinacao de veiculos.",
        "Validar os padroes atuais de 500 m e 137,16 m (450 ft).",
    ),
    _metric(
        "lowc_per_flight_hour", "Taxa LoWC por hora de voo", "N_lowc / soma(H_f)",
        "Produto 3 v1, secao 3.3, Eq. 3.2", "metrics.py::_safety_summary",
        "Implementada a partir das instancias observadas", "parcial",
        "LoWC 3D e duracao por instancia", "Normaliza eventos pela exposicao total em horas.",
        "Herdara a validacao pendente dos criterios LoWC.",
    ),
    _metric(
        "lowc_per_100_operations", "Taxa LoWC por 100 operacoes", "N_lowc / N_operacoes * 100",
        "Produto 3 v1, secao 3.3", "metrics.py::_safety_summary",
        "Implementada usando instancias, nao apenas IDs unicos", "parcial",
        "LoWC 3D e instancias de voo", "O denominador contabiliza reutilizacao de matricula.",
        "Herdara a validacao pendente dos criterios LoWC.",
    ),
    _metric(
        "lowc_per_1000_km", "Taxa LoWC por 1000 km", "N_lowc / km_voados * 1000",
        "Produto 3 v1, secao 3.3", "metrics.py::_safety_summary", "Implementada", "parcial",
        "LoWC 3D e distflown", "Normaliza eventos pela distancia executada.",
        "Herdara a validacao pendente dos criterios LoWC.",
    ),
    _metric(
        "severity_ratio", "Severidade de conflito 3D",
        "sev = min_t(max(Sh/Smin_h, Sv/Smin_v))", "Produto 3 v1, severidade de conflito",
        "metrics.py::_summarize_lowc_event", "Implementada com componentes horizontal e vertical", "parcial",
        "separacoes horizontal/vertical e limites", "Mede a penetracao no volume retangular 3D.",
        "Validar se o modelo retangular e a severidade combinada sao os adotados pelo projeto.",
    ),
    _metric(
        "time_below_threshold", "Tempo abaixo do limiar",
        "duracao das amostras consecutivas em LoWC 3D", "Produto 3 v1, secao 4.2.3",
        "metrics.py::_summarize_lowc_event", "Implementada com amostragem de 1 segundo", "implementada",
        "simt regular e eventos LoWC 3D", "Usa a resolucao integral dos novos STATELOGs.",
        "Tratar explicitamente logs futuros com amostragem irregular.",
    ),
    _metric(
        "time_to_conflict", "Tempo ate conflito observado", "TTC=t_conflito-t_deteccao",
        "Produto 3 v1, metrica de proximidade", "metrics.py::_summarize_lowc_event",
        "Indisponivel como observacao; exibido apenas como horizonte configurado", "indisponivel",
        "instante de alerta ou previsao de CPA", "O dashboard identifica 60 s como DTLOOK, nao TTC medido.",
        "Adicionar ao log o alerta e o conflito previsto correspondente.",
    ),
    _metric(
        "nmac_events", "Near Mid-Air Collision 3D", "Sh(t)<S_NMAC_h e Sv(t)<S_NMAC_v",
        "Produto 3 v1, criterio de separacao restritivo", "metrics.py::_safety_summary",
        "Implementada em 3D com limites configuraveis", "parcial", "simt, lat, lon, alt e limites NMAC",
        "Usa atualmente 150 m horizontal e 30,48 m vertical (100 ft).",
        "Validar formalmente os dois limites para operacoes UAM/helicoptero.",
    ),
    _metric(
        "expected_mac", "MAC esperado", "MAC=beta*P(MAC|NMAC)*N_NMAC",
        "Produto 3 v1, seguranca", "metrics.py::_safety_summary",
        "Implementada como estimativa condicionada a parametros externos", "parcial",
        "NMAC 3D, beta, P(MAC|NMAC) e horas", "Calcula valor esperado e taxa por 100 mil horas; nao inventa timestamp MAC.",
        "Validar beta e P(MAC|NMAC); fornecer flag/instante de colisao se MAC observado precisar ser georreferenciado.",
    ),
    _metric(
        "tls_margin", "Margem em relacao ao TLS", "M_TLS=TLS/(lambda_MAC+epsilon)",
        "Produto 3 v1, Eq. 4.12", "metrics.py::_safety_summary", "Implementada com TLS configuravel", "parcial",
        "MAC estimado, horas, TLS e epsilon", "Compara a taxa estimada ao alvo configurado.",
        "Homologar o TLS e os parametros de risco com a autoridade do estudo.",
    ),
    _metric(
        "mean_flight_time_min", "Tempo medio de voo", "media(max(simt_f)-min(simt_f))",
        "Produto 3 v1, secao 4.3.4", "metrics.py::efficiency_metrics",
        "Implementada como duracao observada no STATELOG", "implementada", "simt e instancias",
        "Calcula media, mediana e P95.", "Adicionar marcos de decolagem/pouso para medir airborne time estrito.",
    ),
    _metric(
        "mean_distance_nm", "Distancia media executada", "media(max(distflown_f)-min(distflown_f))",
        "Produto 3 v1, secao 4.3.4", "metrics.py::efficiency_metrics", "Implementada", "implementada",
        "distflown e instancias", "Calcula media, mediana, P95 e total.",
        "Validar distflown contra uma referencia independente.",
    ),
    _metric(
        "mean_route_efficiency_pct", "Ineficiencia horizontal executada",
        "(d_real-d_gc)/d_gc*100", "Produto 3 v1, secao 4.3.6, Eq. 4.19",
        "metrics.py::efficiency_metrics", "Implementada contra a distancia geodesica", "implementada",
        "extremos lat/lon e distflown", "Mede o alongamento da rota executada.",
        "Interpretar separadamente restricoes estruturais obrigatorias.",
    ),
    _metric(
        "delay_metrics", "Aderencia ao horario de criacao em solo",
        "max(0,t_primeira_amostra-t_CRE_planejado)", "Produto 3 v1, secao 4.3.1",
        "scenario_parser.py::observed_ground_delay_metrics",
        "Implementada como proxy de criacao, nao como atraso operacional", "parcial",
        "SCN pareado e primeira amostra", "Compara as instancias planejadas e executadas.",
        "Fornecer horarios programado, autorizado, pushback e decolagem.",
    ),
    _metric(
        "airborne_delay", "Atraso no ar", "AD_f=max(0,(A_f-D_f)-T_f)",
        "Produto 3 v1, Eq. 4.14", "metrics.py::airborne_delay_metrics",
        "Implementada no codigo, mas indisponivel para C1/C2", "indisponivel",
        "tempo nominal do mesmo modelo, rota e condicoes",
        "O mecanismo existe e nao confunde C1 com C2 como referencia nominal.",
        "Fornecer uma execucao nominal pareada para cada cenario.",
    ),
    _metric(
        "total_delay", "Atraso total", "TD_f=GD_f+AD_f", "Produto 3 v1, eficiencia",
        "metrics.py::total_delay_metrics", "Implementada no codigo, mas indisponivel para C1/C2", "indisponivel",
        "atrasos operacionais em solo e no ar", "So calcula quando ambos os componentes estao disponiveis.",
        "Obter marcos operacionais e referencia nominal.",
    ),
    _metric(
        "operational_punctuality", "Pontualidade operacional",
        "percentual de chegadas dentro da tolerancia planejada", "Produto 3 v1, eficiencia",
        "Ainda nao implementada", "Indisponivel por ausencia de horarios reais de chegada", "indisponivel",
        "horarios planejado, autorizado e real de chegada", "A lacuna e publicada na rastreabilidade.",
        "Adicionar os tres marcos por instancia.",
    ),
    _metric(
        "trajectory_conformity", "Conformidade de trajetoria",
        "TC_f=(d_real-d_plan)/d_plan; ED_f=d_real-d_plan", "Produto 3 v1, Eq. 4.16-4.17",
        "metrics.py::trajectory_conformity", "Implementada com os SCN C1/C2", "implementada",
        "STATELOG e waypoints do SCN", "Associa por ID/horario e compara distancia e geometria.",
        "Validar tolerancias por classe de rota e fase de voo.",
    ),
    _metric(
        "spatial_route_adherence", "Aderencia espacial a REH",
        "amostras dentro dos poligonos/amostras associadas*100", "Produto 3 v1, secao 4.3.5",
        "metrics.py::trajectory_conformity", "Implementada com XML WFS/GML oficial", "implementada",
        "STATELOG, SCN e XML REH", "Usa poligonos e semilarguras oficiais; em C2 avalia somente helicopteros na REH.",
        "Fornecer a geometria oficial do corredor eVTOL C2 e versionar a vigencia do cadastro.",
    ),
    _metric(
        "air_traffic_density", "Densidade de trafego aereo", "ATD_dt=N_simultaneo_dt/A",
        "Produto 3 v1, Eq. 4.23", "capacity.py::capacity_metrics",
        "Implementada sobre a area dos poligonos REH", "implementada", "STATELOG e XML REH",
        "Calcula densidade media, pico e hotspots.",
        "Homologar janelas temporais e areas operacionais para comparacao externa.",
    ),
    _metric(
        "complexity_components", "Componentes de complexidade",
        "cruzamentos, waypoints, grupos, LoWC e fluxos", "Produto 3 v1, secao 4.4.1",
        "capacity.py::_complexity_components", "Implementada como proxies sem indice composto validado", "parcial",
        "STATELOG, SCN, REH, grupos e LoWC", "Publica cada componente separadamente.",
        "Definir pesos, normalizacao e validacao do indice agregado.",
    ),
    _metric(
        "resource_throughput", "Throughput por recurso", "THR_r,dt=N_r,dt/|dt|",
        "Produto 3 v1, Eq. 4.24", "capacity.py::_resource_throughput",
        "Implementada em janelas de uma hora para OD, grupos e REH", "implementada",
        "instancias, SCN, trajetorias e REH", "Calcula throughput por tres familias de recurso.",
        "Homologar janela e definicao operacional dos recursos.",
    ),
    _metric(
        "resource_utilization", "Utilizacao de recurso", "U=N/C; C=P95(THR)",
        "Produto 3 v1, Eq. 4.25", "capacity.py::_resource_throughput",
        "Implementada como proxy do P95 observado, nao capacidade declarada", "parcial",
        "throughput e capacidade de referencia", "Mede proximidade ao envelope observado.",
        "Fornecer capacidade declarada/homologada por recurso.",
    ),
    _metric(
        "risk_ratio", "Razao de risco C2 versus C1", "RR_C2=MAC_100k_C2/MAC_100k_C1",
        "Produto 3 v1, Eq. 4.10", "generate_dashboard.py::comparison_payload",
        "Implementada usando C1 como referencia comparavel", "parcial",
        "MAC_100k C1/C2 e referencia", "Agrupa C1/C2 e calcula a razao.",
        "Herdara validacao de NMAC e parametros probabilisticos.",
    ),
]


def metric_catalog_payload() -> list[dict[str, Any]]:
    return METRIC_CATALOG
