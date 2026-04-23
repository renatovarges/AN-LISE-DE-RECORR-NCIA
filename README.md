# HANDOFF FASE 1 — ANÁLISE DE RECORRÊNCIA / CARTOLA

## 1. Objetivo do projeto

Criar uma plataforma de análise para Cartola baseada em recorrência estatística, capaz de cruzar scouts conquistados e cedidos por posição, com filtros por janela de jogos e mando, entregando um painel visual rápido, limpo e intuitivo para identificar padrões e oportunidades de escalação.

---

## 2. Problema que o projeto resolve

Hoje a análise de confrontos exige leitura manual, dispersa e lenta. Médias simples não distinguem recorrência real de eventos isolados. A plataforma resolve isso ao medir a frequência de ocorrência de scouts relevantes, separar conquistado de cedido e destacar visualmente os cruzamentos estatísticos mais fortes.

---

## 3. Público e uso principal

### Público principal
- criador de conteúdo e analista de Cartola
- alunos e membros que consomem estudo de rodada

### Uso principal
- estudar posição por posição
- identificar rapidamente bons encaixes estatísticos por scout e confronto
- filtrar os sinais mais fortes sem poluição visual

---

## 4. Funcionalidades essenciais

- ler base de scouts jogo a jogo do Brasileirão
- analisar por posição:
  - goleiro
  - lateral
  - zagueiro
  - volante
  - meia
  - ponta direita
  - ponta esquerda
  - atacante central
- separar scouts conquistados e cedidos
- aplicar filtro por janela de jogos
- aplicar filtro por mando
- calcular recorrência por scout com base em limiares definidos
- classificar força por cor:
  - verde: `>= 75%`
  - amarelo: `>= 61% e < 75%`
  - vermelho: `>= 50% e < 61%`
  - abaixo de 50%: não exibir
- exibir painel por posição, não por confronto
- usar visual espelhado:
  - lado esquerdo = conquistado
  - lado direito = cedido
- exibir no centro apenas scout + janela
  - exemplos: `1PG`, `2DS`, `3FIN`, `3DEF`, `75%DE`, `50%SG`, `últ. 5J`
- exibir percentuais e frações de recorrência
  - exemplos: `75% / 3-4` e `80% / 4-5`
- priorizar exibição pelos percentuais mais fortes e pelo melhor cruzamento entre conquistado e cedido

---

## 5. Funcionalidades secundárias

- foto do jogador no card
- escudos dos times
- visual premium estilo sports dashboard
- múltiplos scouts no mesmo card
- refinamento estético avançado
- microtextos auxiliares
- expansão futura para hover, drill-down ou detalhamento por jogo

---

## 6. Itens em aberto

- regra exata de seleção dos jogadores que entram no painel final por scout e posição
- limite máximo de jogadores por bloco
- regra final de rankeamento quando houver percentuais próximos
- forma de associação entre scout, jogador, posição e time adversário
- distribuição final de foto, nome e escudos dentro do card
- critérios de desempate entre sinal unilateral forte e cruzamento equilibrado
- necessidade ou não de filtros adicionais na interface
- definição técnica final da ingestão da planilha e da estrutura dos dados

---

## 7. Escopo consolidado

A plataforma deve analisar scouts jogo a jogo do Brasileirão e calcular, por posição e por mando, a frequência com que um time conquista ou cede eventos relevantes dentro de uma janela filtrável de jogos. O sistema deve destacar apenas os padrões estatísticos mais úteis para estudo e escalação, em vez de exibir tudo. A visualização principal deve ser organizada por posição, com barras espelhadas, conquistado à esquerda, cedido à direita, cores por faixa de força e notação curta de scout no centro. O foco do produto é velocidade de leitura, clareza visual e identificação objetiva de oportunidades.

---

## 8. Regras funcionais já definidas

### Regra de ouro
O filtro de últimos jogos deve ser cronológico por data real da partida, e não por número da rodada.

### Convenção visual
- esquerda = conquistado
- direita = cedido
- a cor da barra já comunica a força
- não usar símbolo extra para dizer forte/médio/fraco

### Faixa de cor
- verde: `>= 75%`
- amarelo: `>= 61% e < 75%`
- vermelho: `>= 50% e < 61%`
- abaixo de 50%: não exibir

### Scouts por posição

#### Goleiro
- SG
- defesas
- %DE

#### Lateral
- SG
- desarmes
- participação em gol

#### Zagueiro
- SG
- desarmes
- participação em gol
- finalizações

#### Volante
- desarmes
- passes-chave
- finalizações

#### Meia
- participação em gol
- finalizações
- passes-chave

#### Ponta direita / ponta esquerda
- participação em gol
- finalizações
- passes-chave

#### Atacante central
- participação em gol
- finalizações

### Notação curta
- `1PG`
- `2DS`
- `3DEF`
- `3FIN`
- `75%DE`
- `50%SG`
- `últ. 3J`
- `últ. 4J`
- `últ. 5J`
- `últ. 6J`

### Regra de %DE
Calcular por jogo:

`%DE = FD / (FD + GS) * 100`

Regra obrigatória:
- se `FD + GS = 0`, então `%DE = 0`

---

## 9. Ordem prática de execução

### Etapa 1 — Base e leitura
- ler a planilha principal
- entender a aba `Por jogo`
- mapear colunas relevantes
- validar dicionário de scouts com `SCOUTS.txt`

### Etapa 2 — Normalização mínima
- padronizar nomes de times
- padronizar posições
- integrar:
  - `classificacao_meias_volantes.csv`
  - `separação atacantes.txt`
- garantir separação correta entre:
  - volante e meia
  - ponta direita, ponta esquerda e atacante central

### Etapa 3 — Motor de recorrência
- implementar filtro por mando
- implementar filtro por últimos N jogos por data real
- calcular conquistado e cedido por scout
- calcular percentual e fração de recorrência
- aplicar faixas de cor

### Etapa 4 — Organização do painel
- agrupar por posição
- priorizar os percentuais mais fortes
- estruturar saída visual inicial
- montar a linha espelhada com:
  - conquistado à esquerda
  - scout + janela no centro
  - cedido à direita

### Etapa 5 — Refinamento visual inicial
- usar escudos
- testar foto do jogador
- aplicar visual limpo
- evitar excesso de texto
- manter foco em legibilidade

---

## 10. Restrições de execução

- não expandir o projeto inteiro de uma vez
- não reconstruir tudo a cada ajuste
- não abrir brainstorm amplo sem necessidade
- não gastar tokens com alternativas demais
- fazer primeiro funcionar, depois refinar
- cada etapa deve gerar saída objetiva e validável

---

## 11. Resultado esperado da Fase 1

Ao fim da Fase 1, deve existir uma primeira versão funcional que:

- lê a base corretamente
- calcula recorrência com regra correta de data e mando
- organiza os dados por posição
- mostra conquistado e cedido com barras espelhadas
- usa notação curta de Cartola
- exibe percentuais, frações e cor por faixa de força
- já permita validar a lógica central da plataforma antes do refinamento visual avançado