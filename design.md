# Design: E-commerce Insights

## Direção do produto

### Superfície

Painel de analytics operacional, usado para explorar vendas históricas e apoiar decisões de negócio. O sucesso do usuário é entender rapidamente o desempenho, comparar grupos de clientes e localizar evidências para campanhas.

### Modo Impeccable

**Operate.** Precisão e leitura rápida prevalecem. A identidade visual vem de detalhes controlados, não de efeitos que competem com gráficos.

### Referência

Adaptar o documento `upload/DESIGN(1).md`, referência REKKI, para produto analítico. Preservar canvas escuro, superfícies quase pretas, azul Signal Blue e contornos discretos. Adaptar sua tipografia expressiva para uma hierarquia compacta de dashboard. Não copiar elementos de marketing como hero gigante ou CTA comercial.

## Princípios

1. **Dados antes de decoração:** cada bloco visual deve ajudar a responder uma pergunta.
2. **Evidência junto da interpretação:** toda recomendação aparece ao lado de suas métricas e período.
3. **Hierarquia previsível:** primeiro panorama, depois tendência, clientes e categorias, por fim metodologia.
4. **Precisão sem ruído:** superfícies escuras, poucos acentos, grades e escalas claras.
5. **Sem falsa certeza:** indicar que os achados são históricos e vêm de uma operação da Olist.

## Tokens visuais

| Uso | Token | Valor |
|---|---|---|
| Canvas | `--color-canvas` | `#000000` |
| Superfície base | `--color-surface` | `#040910` |
| Cartão | `--color-card` | `#0d0d0d` |
| Controle/hover | `--color-control` | `#1f1f1f` |
| Elevação máxima | `--color-elevated` | `#2b2c2e` |
| Acento/seleção | `--color-accent` | `#0063e1` |
| Texto principal | `--color-text` | `#ffffff` |
| Texto secundário | `--color-muted` | `#858585` |
| Ícones/contorno secundário | `--color-subtle` | `#979797` |
| Borda cartão | `--border-card` | `rgba(255,255,255,0.12)` |
| Foco | `--focus-ring` | `#69a7ff` ou equivalente com contraste adequado |

Estados semânticos devem usar cores legíveis e diferenciadas do azul de marca; sempre combinar cor com texto/ícone. Vermelho/verde não podem ser a única indicação de tendência.

## Tipografia

- Família principal: Inter; fallback system sans-serif.
- Valores numéricos: usar algarismos tabulares quando suportados (`font-variant-numeric: tabular-nums`).
- Labels técnicos ou metadados: família mono apenas de forma pontual.
- KPIs: 28–36px desktop, reduzindo proporcionalmente em telas estreitas; peso 400–600.
- Título de página: 28–36px; título de seção: 18–22px; corpo 14–16px; metadados nunca menores que 12px.
- Evitar tracking negativo extremo e pesos ultrafinos em valores, eixos e corpo.

## Espaçamento e formas

- Unidade base: 4px.
- Espaçamentos recorrentes: 8, 12, 16, 24 e 32px.
- Margem do conteúdo: 24–32px em desktop; 16px em mobile.
- Grade desktop: conteúdo máximo aproximado de 1440px; 12 colunas ou grid CSS equivalente; gutter 16–20px.
- Cartões: raio 16px, padding 20–24px, borda interna de 1px sutil.
- Controles: altura confortável de 40–48px, raio de 8px; ações primárias podem ser pill se fizer sentido, sem CTA comercial superdimensionado.
- Sombras mínimas; preferir contraste entre superfícies e borda interna.

## Estrutura do painel

### Cabeçalho

- Marca textual “E-commerce Insights” com detalhe azul pequeno.
- Texto de contexto: “Análise histórica da base Olist”.
- Intervalo coberto pela base e filtro de ano/mês, sem afirmar atualização recente.
- Link/controle “Sobre os dados” abre seção curta de fonte, metodologia e licença.

### Conteúdo principal

1. **KPIs:** Receita de produtos, pedidos entregues, clientes únicos, ticket médio. Cada cartão tem label, valor, unidade e nota de escopo quando necessária.
2. **Vendas mensais:** série temporal com seleção entre receita, pedidos e ticket médio, ou pequenos gráficos alinhados. Mostrar eixo mensal e tooltip completo.
3. **Clientes:** distribuição por segmentos e tabela comparativa RFM. A tabela prioriza legibilidade e mostra nome/perfil, clientes, participação, recência, frequência e gasto.
4. **Categorias:** ranking horizontal de categorias por receita, com itens/pedidos em tooltip ou tabela auxiliar.
5. **Recomendações:** cartões compactos ordenados pela força/clareza da evidência, cada um com decisão relacionada, observação, evidência e caveat.
6. **Metodologia:** detalhes recolhíveis de fonte, recorte, filtros, moeda nominal, cálculo e licença.

### Navegação

Para uma única página, usar navegação por âncoras ou abas simples: Visão geral, Clientes, Sazonalidade, Categorias e Recomendações. Em viewport pequena, converter em seletor compacto. Não esconder informações metodológicas essenciais atrás de hover.

## Gráficos

- Linha para tendência mensal; azul para a série principal, grade horizontal discreta e pontos/tooltip ao foco.
- Barras horizontais para rankings de categorias e distribuição comparativa de segmentos.
- Se usar scatter plot para clientes, limitar a interpretação a visualização exploratória; oferecer tabela que contém os números exatos.
- Não usar gráficos 3D, medidores decorativos, gradientes de fundo ou linhas sem escala.
- Tooltip inclui mês/categoria/segmento e valor com unidade.
- Gráfico deve ter título que descreve a métrica, não apenas “Performance”.
- Incluir resumo textual acessível da tendência principal.

## Recomendações visuais

Cada recomendação contém:

- Categoria: Clientes, Sazonalidade ou Produtos.
- Ação em forma cautelosa, por exemplo “Avalie priorizar…”.
- Evidência numérica no mesmo cartão.
- Período/base de comparação.
- Ressalva concisa de que o padrão é histórico e não prova causalidade.

Usar hierarquia tipográfica e borda/acento lateral discreto. Não adicionar status de urgência fictício ou pontuação de confiança não calculada.

## Estados e comportamento

- **Carregando:** skeletons discretos e mensagem de preparação da base.
- **Pronto:** painel preenchido com proveniência visível.
- **Arquivo ausente:** lista exata de arquivos necessários e passo de instalação.
- **Dados sem cobertura:** ilustração dispensável; explicar por texto e oferecer limpeza do filtro.
- **Falha parcial do K-means:** manter KPIs e sazonalidade, mostrar erro claro na seção de clientes.
- **Filtro sem dados:** explicar o recorte vazio; permitir voltar ao intervalo completo.
- **Recomendação insuficiente:** mostrar estado neutro explicando falta de evidência, não criar texto genérico.

## Responsividade e acessibilidade

- Desktop: KPIs em quatro colunas, gráficos em grade de duas colunas quando apropriado.
- Tablet: KPIs duas colunas, gráficos em uma ou duas colunas segundo largura útil.
- Mobile: uma coluna, controles empilhados, rótulos sem corte; tabela com rolagem horizontal controlada ou cartões compactos equivalentes.
- Manter contraste de texto adequado sobre cada superfície, foco de teclado visível e ordem semântica de títulos.
- Controles devem ter label textual; ícone sozinho só com nome acessível.
- Informação não pode depender apenas de hover, cor ou tooltip.
- Respeitar preferência por redução de movimento; animações, se houver, apenas para transições curtas e sem atrasar dados.

## Vocabulário da interface

- “Receita de produtos” em vez de “vendas” quando o valor soma `price` sem frete.
- “Ticket médio por pedido” para explicitar denominador.
- “Clientes únicos” usando `customer_unique_id`.
- “Período analisado” e “padrão histórico observado”.
- Evitar “previsão”, “clientes fiéis” ou “melhor segmento” sem definição/evidência explícita.

## Critério visual de aceite

O dashboard deve parecer um instrumento analítico REKKI: escuro, preciso e contido; um azul elétrico orienta seleção e foco, cartões são separados por contornos discretos e gráficos permanecem fáceis de ler. A interface deve funcionar sem confundir receita de itens com pagamentos, sem transformar padrões históricos em previsões e sem sacrificar legibilidade para imitar fielmente a página de marketing da referência.
