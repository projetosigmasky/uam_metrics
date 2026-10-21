"""Select reproducible evidence for the capacity report; never change calibration data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

BASELINES = ("C1.1", "C1.2", "C2.1", "C2.2")
ROOT = Path(__file__).resolve().parents[1]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.fonttype": "none", "svg.hashsalt": "baseline-capacity-2026-10-20"})


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def percentage(count, total):
    return f"{100*count/total:.1f}%".replace(".", ",") if total else "—"


def save_figure(fig, folder, stem):
    fig.savefig(folder / f"{stem}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(folder / f"{stem}.svg", bbox_inches="tight", facecolor="white", metadata={"Date": None})
    plt.close(fig)


def distribution(ax, resources, policy, maximum, title):
    values = [r["estimates"][f"300:{policy}"]["p95_operations_per_window"] for r in resources
              if r["estimates"][f"300:{policy}"]["status"] == "observed"]
    counts = Counter(int(value) for value in values)
    categories = list(range(maximum + 1))
    bars = ax.bar(categories, [counts[k] for k in categories], width=.7,
                  color=["#94a3b8" if k == 0 else "#2563eb" if k == 1 else "#0f766e" if k == 2 else "#d97706" for k in categories])
    for k, bar in zip(categories, bars):
        if counts[k]:
            ax.annotate(f"{counts[k]}\n({percentage(counts[k], len(values))})", (bar.get_x()+bar.get_width()/2, bar.get_height()),
                        xytext=(0, 5), textcoords="offset points", ha="center", fontsize=10)
    ax.set_xticks(categories)
    ax.set_ylim(0, max(counts.values(), default=1)*1.25)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel("P95 empírico (movimentos por janela de 5 min)")
    ax.set_ylabel("Quantidade de recursos físicos")
    ax.set_title(f"{title}\nN = {len(values)} recursos com estimativa")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=.15)
    ax.set_axisbelow(True)


def build(source, destination):
    data = json.loads((source / "calibration.json").read_text(encoding="utf-8"))
    comparisons = list(csv.DictReader((source / "comparison.csv").open(encoding="utf-8")))
    csv_index = {(r["scenario"], r["waypoint_id"], r["window_seconds"], r["zero_policy"]): r for r in comparisons}
    figures = destination / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    summaries, resources_out, selections, stage_rows, network_rows = [], [], [], [], []
    all_values = [e["p95_operations_per_window"] for s in data["scenarios"].values() for r in s["resources"]
                  for key, e in r["estimates"].items() if key.startswith("300:") and e["p95_operations_per_window"] is not None]
    maximum = int(max(all_values))
    selected_figures = []
    selection_rule = "P95 positivo = 1 ou 2; estabilidade final confirmada; >=100 janelas positivas; contagem mais próxima da mediana da classe; desempate pelo ID físico"
    for code in BASELINES:
        scenario = data["scenarios"][code]
        assert scenario["replica_count"] == 50 and scenario["passage_source"] == "native"
        resources = scenario["resources"]
        for policy in ("positive", "all"):
            estimates = [r["estimates"][f"300:{policy}"] for r in resources]
            observed = [e for e in estimates if e["status"] == "observed"]
            counts = Counter(int(e["p95_operations_per_window"]) for e in observed)
            summaries.append({"scenario": code, "zero_policy": policy, "physical_resources": len(resources),
                              "observed_estimates": len(observed), "p95_0": counts[0], "p95_1": counts[1],
                              "p95_2": counts[2], "p95_above_2": sum(v for k, v in counts.items() if k > 2),
                              "p95_1_or_2": counts[1]+counts[2], "p95_1_or_2_pct": 100*(counts[1]+counts[2])/len(observed),
                              "stable_p95": sum(e["stable_at_final"] for e in estimates),
                              "stable_mean": sum(e["mean_stable_at_final"] for e in estimates),
                              "no_observed_use": sum(e["status"] == "no_observed_use" for e in estimates),
                              "insufficient_full_windows": sum(e["status"] == "insufficient_full_windows" for e in estimates)})
        for resource in resources:
            positive, all_ = resource["estimates"]["300:positive"], resource["estimates"]["300:all"]
            for policy, estimate in (("positive", positive), ("all", all_)):
                row = csv_index[code, resource["waypoint_id"], "300", policy]
                assert float(row["p95_operations_per_window"]) == estimate["p95_operations_per_window"]
                assert int(row["positive_window_count"]) == estimate["positive_window_count"]
                assert (row["stable_at_final"] == "True") == estimate["stable_at_final"]
            assert positive["positive_window_count"] > 0
            record = {"scenario": code, "waypoint_id": resource["waypoint_id"], "label": resource["label"],
                      "network": resource["network"], "lat": resource["lat"], "lon": resource["lon"], "altitude_ft": resource["altitude_ft"],
                      "positive_p95_movements_5min": positive["p95_operations_per_window"],
                      "all_p95_movements_5min": all_["p95_operations_per_window"],
                      "positive_windows": positive["positive_window_count"], "all_windows": all_["window_count"],
                      "active_window_fraction": positive["positive_window_count"]/all_["window_count"],
                      "stable_positive_p95": positive["stable_at_final"], "stable_positive_mean": positive["mean_stable_at_final"],
                      "positive_ci_lower_movements_5min": positive["ci95"][0]/12 if positive["ci95"] else None,
                      "positive_ci_upper_movements_5min": positive["ci95"][1]/12 if positive["ci95"] else None,
                      "fallback_applied_current_calibration": False,
                      "needs_review_before_1_or_2_assignment": positive["p95_operations_per_window"] > 2 or not positive["stable_at_final"]}
            resources_out.append(record)
        for network in sorted({r["network"] for r in resources}):
            group = [r for r in resources if r["network"] == network]
            counts = Counter(r["estimates"]["300:positive"]["p95_operations_per_window"] for r in group)
            network_rows.append({"scenario": code, "network": network, "resources": len(group),
                                 "p95_1": counts[1], "p95_2": counts[2], "p95_above_2": sum(v for k,v in counts.items() if k>2)})
        for target in (1, 2):
            group = [r for r in resources if r["estimates"]["300:positive"]["p95_operations_per_window"] == target]
            median_windows = statistics.median(r["estimates"]["300:positive"]["positive_window_count"] for r in group)
            eligible = [r for r in group if r["estimates"]["300:positive"]["stable_at_final"]
                        and r["estimates"]["300:positive"]["positive_window_count"] >= 100]
            chosen = min(eligible, key=lambda r: (abs(r["estimates"]["300:positive"]["positive_window_count"]-median_windows), r["waypoint_id"]))
            selections.append({**next(r for r in resources_out if r["scenario"]==code and r["waypoint_id"]==chosen["waypoint_id"]),
                               "target_class": target, "class_positive_window_median": median_windows,
                               "eligible_example_candidates": len(eligible), "selection_rule": selection_rule})
        stem = code.replace(".", "_")
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
        distribution(axes[0], resources, "positive", maximum, "Somente janelas positivas")
        distribution(axes[1], resources, "all", maximum, "Todas as janelas completas, incluindo zeros")
        fig.suptitle(f"{code} · 50 réplicas · P95 por recurso físico", fontweight="bold")
        fig.text(.5, .015, "O valor 1 nos positivos é observado; a calibração atual não substitui zeros por 1. Referência empírica, não limite operacional.", ha="center", fontsize=9)
        fig.tight_layout(rect=(0,.045,1,.94))
        save_figure(fig, figures, f"{stem}_distribuicao_5min")
        fig, axes = plt.subplots(2, 2, figsize=(12, 7.5), sharex=True)
        for index, example in enumerate([r for r in selections if r["scenario"] == code]):
            chosen = next(r for r in resources if r["waypoint_id"] == example["waypoint_id"])
            estimate = chosen["estimates"]["300:positive"]
            trace = [dict(zip(data["trace_columns"], row)) if isinstance(row, list) else row for row in estimate["convergence"]]
            for column, (field, ci_field, label, flag) in enumerate((("p95_per_hour", "ci95", "P95", "stable_at_final"),
                                                                   ("mean_per_hour", "mean_ci95", "Média condicional", "mean_stable_at_final"))):
                ax = axes[index,column]
                x = [p["replicas"] for p in trace]
                y = [p[field]/12 if p[field] is not None else float("nan") for p in trace]
                ax.plot(x, y, color="#2563eb" if not column else "#0f766e", linewidth=1.8)
                interval = [p for p in trace if p[ci_field]]
                if interval:
                    ax.fill_between([p["replicas"] for p in interval], [p[ci_field][0]/12 for p in interval],
                                    [p[ci_field][1]/12 for p in interval], color="#60a5fa", alpha=.3, label="IC bootstrap 95%")
                ax.axvline(data["criteria"]["minimum_replications"], color="#64748b", linestyle=":", label="Mínimo: 30 réplicas")
                ax.set_title(f"{chosen['label']} · {chosen['network']} · {chosen['waypoint_id'][-8:]}\n{label} · classe P95 = {example['target_class']} mov./5 min", fontsize=10)
                ax.set_ylabel(f"{label} (mov./5 min)")
                ax.set_xlabel("Réplicas acumuladas")
                ax.set_ylim(bottom=0); ax.grid(alpha=.15); ax.legend(loc="best", fontsize=8)
                ax.text(.98,.03,"Precisão final confirmada" if estimate[flag] else "Precisão final não confirmada", transform=ax.transAxes, ha="right", fontsize=8)
        fig.suptitle(f"{code} · Exemplos auditáveis das classes P95 = 1 e P95 = 2", fontweight="bold")
        fig.text(.5,.01,"Exemplos selecionados por regra explícita de cobertura/estabilidade; não representam os recursos raros ou instáveis.", ha="center", fontsize=9)
        fig.tight_layout(rect=(0,.035,1,.94))
        save_figure(fig, figures, f"{stem}_exemplos_1_2")
        for name in (f"{stem}_distribuicao_5min", f"{stem}_exemplos_1_2"):
            selected_figures.append({"scenario": code, "role": "primary", "path": f"figures/{name}.png", "vector_path": f"figures/{name}.svg"})
        for kind in ("positive_histogram", "positive_cdf"):
            selected_figures.append({"scenario": code, "role": "sensitivity_5_15_60min", "path": f"../../docs/assets/data/baseline_calibration/{code}_{kind}.png"})
    for a,b in (("C1.1","C1.2"),("C2.1","C2.2")):
        left = {r["waypoint_id"]:r for r in data["scenarios"][a]["resources"]}
        right = {r["waypoint_id"]:r for r in data["scenarios"][b]["resources"]}
        for rid in sorted(left.keys()|right.keys()):
            r = left.get(rid) or right[rid]
            v1 = left[rid]["estimates"]["300:positive"]["p95_operations_per_window"] if rid in left else None
            v2 = right[rid]["estimates"]["300:positive"]["p95_operations_per_window"] if rid in right else None
            stage_rows.append({"scenario_6_vertiports":a,"scenario_12_vertiports":b,"waypoint_id":rid,"label":r["label"],
                               "network":r["network"],"p95_6_vertiports":v1,"p95_12_vertiports":v2,
                               "same_physical_resource":rid in left and rid in right,
                               "changed_class":v1 != v2 if v1 is not None and v2 is not None else None})
    fig, axes = plt.subplots(2,2,figsize=(12,8),sharex=True)
    for code,ax in zip(BASELINES,axes.flat): distribution(ax,data["scenarios"][code]["resources"],"positive",maximum,code)
    fig.suptitle("Referência empírica por waypoint · Janelas positivas de 5 minutos",fontweight="bold")
    fig.tight_layout(rect=(0,0,1,.95))
    save_figure(fig,figures,"00_comparacao_quatro_baselines_5min")
    selected_figures.append({"scenario": "all", "role": "overview", "path": "figures/00_comparacao_quatro_baselines_5min.png",
                             "vector_path": "figures/00_comparacao_quatro_baselines_5min.svg"})
    write_csv(destination/"scenario_summary.csv",summaries)
    write_csv(destination/"waypoint_capacity_evidence.csv",resources_out)
    write_csv(destination/"selected_waypoints.csv",selections)
    write_csv(destination/"network_summary.csv",network_rows)
    write_csv(destination/"stage_sensitivity.csv",stage_rows)
    snapshots = {}
    for filename in ("comparison.csv","calibration.json","replica_metrics.csv","convergence.csv"):
        snapshots[f"../../docs/assets/data/baseline_calibration/{filename}"] = sha256(source/filename)
    try:
        data_commit = subprocess.check_output(["git","log","-1","--format=%H","--",str((source/"comparison.csv").resolve())],cwd=ROOT,text=True).strip()
    except subprocess.CalledProcessError: data_commit = None
    for figure in selected_figures:
        path=(destination/figure["path"]).resolve()
        figure["sha256"]=sha256(path)
        if figure.get("vector_path"):
            figure["vector_sha256"] = sha256(destination/figure["vector_path"])
    metadata={"date":"2026-10-20","data_commit":data_commit,"sources_sha256":snapshots,
              "criteria":data["criteria"],"calibration_manifest":data["manifest"],
              "selection_rule":selection_rule,"current_fallback_applied":False,
              "builder_sha256": sha256(Path(__file__)),
              "tables_sha256": {name: sha256(destination/name) for name in ("scenario_summary.csv", "waypoint_capacity_evidence.csv", "selected_waypoints.csv", "network_summary.csv", "stage_sensitivity.csv")},
              "figures":selected_figures,"summary":summaries}
    (destination/"evidence_manifest.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    rows=[s for s in summaries if s["zero_policy"]=="positive"]
    table="\n".join(f"| {s['scenario']} | {s['physical_resources']} | {s['p95_1']} | {s['p95_2']} | {s['p95_above_2']} | {percentage(s['p95_1_or_2'],s['observed_estimates'])} | {s['stable_p95']} |" for s in rows)
    sections=[]
    for code in BASELINES:
        stem=code.replace(".","_")
        examples=[s for s in selections if s["scenario"]==code]
        example_lines="\n".join(f"- Classe {s['target_class']}: **{s['label']}**, rede `{s['network']}`, ID `{s['waypoint_id']}`, altitude {s['altitude_ft']} ft; {s['positive_windows']} janelas positivas. IC95% final do P95: [{s['positive_ci_lower_movements_5min']}; {s['positive_ci_upper_movements_5min']}] movimentos/5 min." for s in examples)
        sections.append(f"""## {code}

![Distribuição do P95 em 5 minutos](figures/{stem}_distribuicao_5min.png)

**Legenda sugerida:** Distribuição do P95 de passagens por recurso físico no cenário {code}, reunindo 50 réplicas. À esquerda, somente janelas positivas; à direita, todas as janelas completas de 300 s. A diferença decorre da inclusão da ociosidade, sem substituição de zeros por um. O eixo horizontal está em movimentos por janela, não em operações/h. [Versão vetorial](figures/{stem}_distribuicao_5min.svg).

![Convergência de exemplos das classes 1 e 2](figures/{stem}_exemplos_1_2.png)

**Legenda sugerida:** Evolução acumulada do P95 e da média condicional para dois recursos físicos de {code}, selecionados por regra explícita de cobertura e estabilidade. As faixas mostram IC95% por reamostragem de réplicas inteiras. Esses exemplos ilustram referências de um e dois movimentos por 5 min; não comprovam capacidade operacional máxima. [Versão vetorial](figures/{stem}_exemplos_1_2.svg).

{example_lines}

**Sensibilidade à janela:** [histogramas originais de 5/15/60 min](../../docs/assets/data/baseline_calibration/{code}_positive_histogram.png) e [distribuições acumuladas originais](../../docs/assets/data/baseline_calibration/{code}_positive_cdf.png). Nos originais, o eixo horizontal é operações/h: 12 e 24 correspondem a 1 e 2 movimentos por 5 min.
""")
    total=sum(s["physical_resources"] for s in rows); one_two=sum(s["p95_1_or_2"] for s in rows)
    text=f"""# Evidências para o relatório: referência de 1 ou 2 movimentos por waypoint

Snapshot de 20/10/2026. Dados reais do commit `{data_commit}`, obtidos de 50 réplicas nativas de cada baseline. Gráficos derivados dos resultados publicados, sem reprocessar logs nem alterar a calibração. O [histórico completo e contexto para outras LLMs](../../ITERATION_LOG.md) registra as decisões, comandos e incidentes.

## Resultado principal e ressalva sobre o fallback

**{one_two}/{total} recursos físicos ({percentage(one_two,total)}) apresentam P95 positivo de 1 ou 2 movimentos por janela de 5 min.** Essa é uma proporção de recursos, não de movimentos. Há recursos com P95 igual a 3, que não devem ser arredondados para 2 para adequar uma narrativa.

O cálculo atual não tem piso 1. Ele remove os zeros somente na política positiva, calcula P95 `higher` e retorna indisponível para recurso sem uso. A regra histórica no outro repositório devolvia `minimum=1` na ausência de janelas positivas. Como todos os recursos atuais têm janelas positivas, o valor 1 mostrado aqui é observado; não é uma imputação por fallback. O condicionamento em janelas positivas também implica que qualquer percentil definido será pelo menos 1.

| Cenário | Recursos físicos | P95 = 1 | P95 = 2 | P95 > 2 | Fração com 1 ou 2 | P95 estável no critério |
|---|---:|---:|---:|---:|---:|---:|
{table}

![Visão dos quatro baselines](figures/00_comparacao_quatro_baselines_5min.png)

[Figura vetorial de comparação](figures/00_comparacao_quatro_baselines_5min.svg). `scenario_summary.csv` também registra os resultados com zeros, a estabilidade da média e a cobertura.

## Critério de seleção dos exemplos

{selection_rule}. A mediana considera toda a classe, antes dos filtros. Em C1.1/C1.2 a mediana de cobertura da classe 1 é baixa; o piso de 100 seleciona intencionalmente exemplos com mais evidência, não uma amostra representativa dos recursos raros. As distribuições usam **todos** os recursos, sem filtro por estabilidade. `selected_waypoints.csv` explicita os candidatos e as medianas.

Os PNGs novos têm 300 dpi; os SVGs preservam os elementos vetoriais e textos. Os gráficos originais permanecem em `docs/assets/data/baseline_calibration/`. As tabelas detalhadas para o relatório estão em `waypoint_capacity_evidence.csv` (um registro por recurso/cenário) e `network_summary.csv` (REH/UAM separados).

"""+"\n".join(sections)+"""
## Texto-base tecnicamente sustentado

“Adotou-se o P95 do fluxo observado em janelas positivas de 300 s como referência empírica para parametrização dos recursos físicos. A predominância de referências de um ou dois movimentos por janela fundamenta a análise de parâmetros individualizados por waypoint, em lugar de um valor uniforme. A escolha é condicionada à demanda dos baselines, ao cenário e ao tratamento da ociosidade; não constitui comprovação de capacidade operacional máxima ou de segurança. Recursos com referência superior a dois ou precisão não confirmada são tratados separadamente.”

## Antes de fixar a capacidade operacional

- Não confundir P95 de demanda atendida, capacidade configurada e capacidade máxima demonstrada. A ausência de movimento não comprova capacidade zero.
- Não atribuir um mesmo limite a todas as posições que compartilham um nome. Use ID físico, rede, coordenadas e altitude.
- Examinar os casos P95 > 2 e a estabilidade de cada recurso, não apenas os oito exemplos selecionados.
- Verificar a sensibilidade ao estágio de demanda em `stage_sensitivity.csv`. O mesmo recurso físico pode mudar de classe entre 6 e 12 vertiportos; a referência observada não é uma propriedade intrínseca imutável do waypoint.
- Não somar referências de waypoints para calcular capacidade da rede; um voo pode atravessar vários recursos.
- Não interpretar IC bootstrap degenerado ou P95 incondicional zero como prova de suficiência/segurança. Há muitos recursos raros e janelas ociosas.
- Mudanças nos limites dos algoritmos exigem validação posterior de atrasos, conflitos e ocupação. Este pacote não altera parâmetros de simulação.

## Reprodução e integridade

```bash
.venv/bin/python scripts/build_baseline_capacity_evidence.py
```

`evidence_manifest.json` registra SHA-256 dos dados e das figuras selecionadas. O script confere o CSV contra o JSON, usa os intervalos de confiança já calculados e faz apenas conversões de unidade. Ao regenerar sobre outros dados, reavalie as conclusões históricas deste snapshot e preserve a versão anterior para rastreabilidade.
"""
    (destination/"README.md").write_text(text,encoding="utf-8")
    print(f"Evidence package: {destination}")
    print(f"P95 = 1 or 2: {one_two}/{total} ({percentage(one_two,total)})")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=ROOT/"docs/assets/data/baseline_calibration")
    parser.add_argument("--output",type=Path,default=ROOT/"reports/baseline_capacity_2026-10-20")
    args=parser.parse_args()
    build(args.source.resolve(),args.output.resolve())


if __name__=="__main__": main()
