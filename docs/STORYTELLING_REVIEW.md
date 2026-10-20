# Revisão de gráficos: relatório do MMM

Revisão feita com o agente `revisor-graficos` de `arielabade/prompts` (*Storytelling com Dados*,
Cole Nussbaumer Knaflic) sobre a primeira versão da página (`src/mmm/report/assets/dashboard.html`)
e implementada em seguida seguindo o `implementador-graficos`.

## Contexto levantado
- Stack: Plotly.js 2.35 em HTML estático gerado por `mmm.jobs.report`; mapa em SVG próprio.
- Público: gestão de mídia / diretoria de marketing da loja [SUPOSIÇÃO], com base no brief e em `docs/MODEL_CARD.md`.
- Decisão que a página apoia: como dividir a verba de mídia do próximo mês entre canais.
- Mecanismo: leitura autônoma (GitHub Pages). Precisa de resumo no topo, títulos de ação e anotações.
- Tokens: ABADE em `src/mmm/brandviz.py`: Carbon `#050505`, Ivory `#F6F5F0`, Cobalt `#5B6CFF` (destaque), Slate `#3A3E46`, Steel `#9BA2AA`; Lato.

## Grande Ideia
- Atual: a página abre com o ganho da realocação, mas não diz por que a recomendação difere do que o histórico sugere.
- Proposta: "Com a mesma verba, dá para ganhar R$ X por mês levando dinheiro de <canais que rendem menos> para <canais que rendem mais>, e só sabemos disso porque um teste geográfico separou a Meta do TikTok, que o histórico sozinho não separava." (calculada de `allocation`, `roi`, `geolift`).

## Lógica horizontal

| Ordem | Título atual | Título proposto | Calculado a partir de |
|---|---|---|---|
| 0 | Mesma verba, R$ X a mais… | idem + bloco Grande Ideia | `allocation.gain_mean`, maiores/menores `change_pct` |
| 1 | — | O problema: "A verba do TikTok acompanha a da Meta todo dia (correlação r)" | correlação diária Meta × TikTok no mart |
| 2 | Desligar a Meta em 7 UFs custou… | O experimento: "Sem a Meta, as 7 UFs perderam X% da receita" | `geolift` |
| 3 | O MMM sem experimento confunde Meta e TikTok | O que o experimento corrigiu: "Meta de A para B por real, TikTok de C para D" | `roi.uncalibrated`, `roi.calibrated` |
| 4 | Quanto cada canal devolve por real | fundido no item 3 | — |
| 5 | O próximo real rende mais em X… | Onde cada canal satura (pequenos múltiplos) | `curves.*.marginal` |
| 6 | Mesma verba, outra divisão | A recomendação: "Mover R$ Z: +X, −Y" | `allocation.channels` |
| 7 | Quão certa é a recomendação | "Em P% dos cenários a nova divisão rende mais" | `gain_draws` |
| 8 | Verba do próximo mês | Próximo passo: "Testar <canal mais incerto>" | maior intervalo relativo de ROI fora a Meta |

## Achados

### [ALTO] Falta o começo da história: o problema que a calibração resolve não aparece
- Onde: seção `#s-calib` (só texto). Nível: Narrativa. Princípio: começo–meio–fim.
- Recomendação: gráfico de linhas do investimento semanal Meta × TikTok, Meta em cobalto, TikTok em cinza, rótulo na ponta, correlação diária no título.

### [ALTO] Sem × com calibração em barras agrupadas de 3 séries com legenda
- Onde: `renderCalib()`. Nível: Gráfico. Princípio: dois momentos → slopegraph; legenda → rótulo direto.
- Recomendação: slopegraph por canal; Meta e TikTok em cobalto, demais em cinza; verdade do simulador como marcador discreto.

### [ALTO] Barras verticais com rótulos girados (ROI, investimento × receita)
- Onde: `renderROI()`. Nível: Elemento. Princípio: texto horizontal; barras horizontais ordenadas.
- Recomendação: o retorno por real já está no slopegraph; investimento e receita vão para a tabela da recomendação.

### [ALTO] Curva de saturação atrás de um seletor
- Onde: `renderCurves()`. Nível: Gráfico. Princípio: pequenos múltiplos para comparar forma.
- Recomendação: 6 painéis, escala Y livre (declarada), ordenados pelo retorno do próximo real, ponto atual em cobalto.

### [MÉDIO] Cores além do destaque e cor que muda de significado
- Onde: âmbar/vermelho/verde em vários gráficos; barras de ROI coloridas por "≥ 1".
- Princípio: cinza + uma cor de destaque; nunca vermelho × verde como único diferenciador.
- Recomendação: cinza para contexto, cobalto para o que conta a história; mapa de variação em escala cinza ↔ cobalto.

### [MÉDIO] Legendas em quase todos os gráficos
- Recomendação: `showlegend: false` e anotações na ponta das séries.

### [MÉDIO] Seção de incerteza responde duas perguntas
- Recomendação: só a distribuição do ganho; ajuste, backtest, diagnóstico e poder do teste vão para o apêndice "Por dentro do modelo".

### [BAIXO] Alocação em barras agrupadas atual × recomendado
- Recomendação: barras horizontais da variação em R$ (cobalto para aumento, cinza para corte) + tabela compacta.

### Preservar
- Títulos calculados com alternativa neutra; aviso de dados simulados no topo; mapa em SVG.

## Quebras recomendadas
| Gráfico | Sinal | Forma | Escala Y | Destaque |
|---|---|---|---|---|
| Saturação com seletor | comparação escondida | pequenos múltiplos (6) | livre, declarada | investimento atual |
| Incerteza + ajuste | duas perguntas | principal + apêndice | — | intervalo de 90% |
