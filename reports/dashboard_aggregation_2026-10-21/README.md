# Verificação local da agregação — 21/10/2026

As imagens deste diretório usam **dados sintéticos de teste**, sem resultados científicos da RUN. Quatro réplicas artificiais, com cobertura temporal e pareamento diferentes, exercitam as faixas mínimo–máximo e as médias por réplica. Não são gráficos das 50 réplicas reais.

- Série de aeronaves: cobertura ausente não vira zero; denominador varia por timestamp.
- Distância adicional: cada réplica válida tem peso igual; réplicas sem pareamento não entram no denominador.
- Faixa/intervalo azul: mínimo–máximo entre réplicas, não intervalo de confiança.

87 testes unittest e contratos DOM/Leaflet aprovados. Incluem comparação serial/paralela de geração de quatro cenários com entradas invertidas. Teste pytest isolado não executado por dependência ausente; caso equivalente coberto por unittest. Navegador integrado não alcançou localhost; não houve QA visual de navegador. Dados reais e relatórios anteriores preservados. Consulte README principal para metodologia e reprocessamento no Lessonia.
