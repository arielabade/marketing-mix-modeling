# Notas para entrevista — marketing-mix-modeling

Documento interno. Não faz parte da documentação pública do projeto.

---

## As 3 decisões técnicas mais importantes

### 1. Simular com parâmetros conhecidos, em vez de usar dado real

**O que fiz:** gerei os dados a partir de um processo cujos adstock, saturação, beta e baseline estão
escritos no `config.py`. O modelo recebe só data, verba semanal por canal e receita.

**Por quê:** contribuição incremental **nunca é observada**. Em dado real, a saída de um MMM pode ser
inspecionada mas não pontuada — todo mundo olha o mesmo gráfico de decomposição e ninguém consegue
dizer se está certo.

Simular é a única forma de responder "o modelo recupera a verdade?" com um número em vez de uma
opinião. É o mesmo raciocínio do meu `ab-testing-toolkit`: quando a quantidade de interesse não é
observável, você valida contra um processo que você mesmo construiu.

**O custo que aceito:** nenhuma conclusão sobre ROI real sai daqui. O que transfere é o método e o
diagnóstico. Está escrito no README em letra grande.

### 2. Baseline com tendência e sazonalidade, e sazonalidade no modelo

**O que fiz:** o baseline simulado tem intercepto, tendência linear, sazonalidade anual e ruído. O
modelo tem `yearly_seasonality=2`.

**Por quê:** sem isso o teste seria fácil demais. A forma mais comum de um MMM lisonjear um canal é
atribuir a ele a força sazonal: se o canal gasta mais no Natal e a receita sobe no Natal, o modelo
credita o canal.

Mídia explica 44% da receita na simulação. Os outros 56% o modelo tem que **não** reivindicar.

### 3. Sinal/ruído como diagnóstico antes do ajuste

**O que fiz:** razão entre o desvio-padrão da contribuição semanal do canal e o desvio-padrão do ruído
da receita. Dá 0,88 para TV e **0,04** para o affiliate.

**Por quê:** foi isso que explicou o resultado. O `affiliate` dá 1,2% da receita e a variação semanal
dele é 4% do ruído. Não existe informação nos dados sobre o ROI dele — o modelo devolve essencialmente
o prior, e devolve com intervalo de credibilidade tão confiante quanto os outros.

O equivalente no mundo real é a razão entre a variação de verba do canal e a variância não explicada
da receita. É a pergunta que deveria vir **antes** de rodar o modelo.

---

## 5 perguntas prováveis, com resposta

### 1. "A correlação de ordenação deu -0,200. O modelo não funcionou?"

Funcionou para três dos quatro canais, e eu mostro os dois números.

Incluindo o `affiliate`: correlação -0,200, erro médio de ROI 0,396. Excluindo: correlação **1,000**,
erro 0,161. O modelo acerta a ordem de **todo canal acima do piso de ruído**, perfeitamente.

A ordenação geral desaba por causa de um canal, e o diagnóstico de sinal/ruído identifica qual **antes
de rodar o modelo**. Esse é o resultado do projeto: não é "MMM funciona" nem "MMM não funciona", é
"MMM funciona acima de um limiar de sinal mensurável, e aqui está como medir o limiar".

### 2. "E daí que ele erra o canal pequeno? É 1% da receita."

Essa era a minha pergunta também, até rodar o otimizador.

O otimizador **dobra a verba do affiliate**, até o teto de 200%, e só para porque eu coloquei o teto.
Ao mesmo tempo corta TV em 32%. Ou seja: o erro num canal de 1% da receita move dinheiro de verdade,
porque o otimizador não sabe que aquele número é ruído — ele vê ROI 0,915 e realoca.

É por isso que a recomendação no README não é "ignore o canal pequeno na leitura", é **fixe ele na
verba atual e tire da otimização**. A diferença entre as duas é dinheiro.

### 3. "Por que não deu só mais dados para o canal pequeno ser identificável?"

Porque não é problema de quantidade de linhas, é de variância.

O `affiliate` precisaria de variação de verba muito maior — ligar e desligar, mudar nível de forma
abrupta — para gerar sinal acima do ruído semanal da receita. Isso é um **experimento**, não mais
histórico. Com dois anos de gasto estável, mais dois anos de gasto estável não acrescentam informação.

A resposta correta para medir canal pequeno é teste geo ou holdout. Modelo maior não resolve.

### 4. "Sobraram 22 divergências. Por que você não subiu o target_accept de novo?"

Porque seria tratar o sintoma, e eu acho que elas têm a mesma causa do erro no affiliate.

O histórico: no default deu **93 divergências**. Subindo `target_accept` para 0,95 caiu para **22**.
Divergência significa que a cadeia não conseguiu explorar parte da posterior, então os intervalos não
são confiáveis.

Mas pensa no que é o parâmetro do affiliate. A verossimilhança não carrega informação sobre ele —
sinal/ruído 0,04. Então ele é determinado só pelo prior, o que deixa uma direção praticamente plana na
posterior. NUTS não atravessa cordilheira plana. **As divergências e o erro de 636% no ROI dele são o
mesmo problema visto de dois ângulos.**

Apertar o amostrador faria ele trabalhar mais para explorar uma direção que o dado nunca restringiu. A
correção certa é tirar o canal do modelo ou dar um prior informativo para ele.

O que eu **não** fiz foi rodar com o default, ver o aviso e seguir em frente.

### 5. "Esse resultado vale para dado real?"

O método sim, o número não — e tem uma ressalva que eu faria antes de alguém perguntar.

Aqui o modelo **conhece a forma funcional certa**: a simulação e o modelo usam o mesmo adstock
geométrico e a mesma saturação logística. Então os 19% de erro médio medem estimação sob
especificação correta. Campanha real não vem com a forma funcional anexada.

Ou seja, 25% é o **piso otimista** do erro, não o esperado. O próximo passo que coloquei no README é
exatamente isso: repetir o teste de recuperação com saturação mal especificada e reportar quanto do
erro é estimação e quanto é especificação. Esse é o número que um praticante realmente precisa.

---

## Números para ter na ponta da língua

| | |
| --- | --- |
| Período | 104 semanas, 4 canais |
| Mídia como % da receita | 44% |
| Correlação de ordenação (todos os canais) | -0,200 |
| Correlação de ordenação (sem o affiliate) | **1,000** |
| Erro médio de ROI (sem o affiliate) | 0,161 (25,3% relativo) |
| Sinal/ruído: tv / search / social / affiliate | 0,88 / 0,45 / 0,30 / **0,04** |
| Divergências: antes / depois do target_accept 0,95 | 93 / 22 |
| Recomendação do otimizador para o pior canal | +100%, no teto |
