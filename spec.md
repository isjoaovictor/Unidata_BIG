# Spec: Painel de inteligência de e-commerce

## 1. Visão geral

Construir um MVP acadêmico de analytics para e-commerce, com uso plausível por um analista de negócio. O produto transforma a base pública da Olist em indicadores, segmentos de clientes, análise mensal de vendas e recomendações explicáveis para apoiar decisões de campanhas e destaque de produtos.

**Título acadêmico sugerido:** Padrões de Comportamento de Compra em E-commerce: Uma Abordagem de Big Data para Segmentação de Clientes e Análise de Sazonalidade.

**Nome de trabalho do MVP:** E-commerce Insights.

## 2. Problema e valor

Os registros transacionais são distribuídos em vários arquivos e não apresentam diretamente os padrões necessários para priorizar grupos de clientes, entender períodos de maior venda ou escolher categorias para campanhas. O MVP prepara uma visão consolidada e navegável com métricas rastreáveis aos dados de origem.

## 3. Usuário e decisões

Usuário primário: analista de e-commerce ou negócio, sem restringir o projeto a um cargo específico.

Decisões apoiadas:

1. Quais segmentos de clientes podem ser priorizados em campanhas.
2. Em quais meses históricos a atividade de vendas foi maior ou menor.
3. Quais categorias de produtos merecem atenção em campanhas, segundo vendas observadas.

O produto oferece evidências e recomendações indicativas. Não executa campanhas nem prevê vendas futuras.

## 4. Escopo do MVP

### Incluído

- Uma base fixa: Brazilian E-Commerce Public Dataset by Olist, disponibilizada no Kaggle.
- Dados referentes ao Brasil e ao período histórico coberto pela base, aproximadamente setembro de 2016 a setembro de 2018.
- Pipeline local de carregamento, validação, limpeza, junção e agregação dos arquivos CSV necessários.
- Painel interativo, em português brasileiro, com período mensal, indicadores, gráficos, segmentos RFM por K-means e recomendações explicáveis.
- Fonte, período, critérios de cálculo e limitações visíveis no produto.
- Interface desenvolvida seguindo a referência visual REKKI incluída em `upload/DESIGN(1).md` e a skill Impeccable disponível no agente executor.

### Fora de escopo

- Upload de bases pelo usuário ou troca de dataset em tempo de execução.
- API externa, atualização automática, autenticação, múltiplos clientes ou persistência de dados operacionais.
- Disparo de campanhas, previsão de demanda ou recomendação individual de produtos.
- Alegações de representatividade de todo o comércio eletrônico brasileiro.
- Uso comercial dos dados. A página do Kaggle declara licença CC BY-NC-SA 4.0.

## 5. Fonte e proveniência

Fonte oficial: Olist, *Brazilian E-Commerce Public Dataset*, Kaggle: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

A página descreve dados comerciais reais anonimizados, cerca de 100 mil pedidos feitos entre 2016 e 2018, e licença CC BY-NC-SA 4.0. O painel e a documentação devem atribuir a fonte e indicar a licença. O dataset é de pedidos feitos na operação/marketplace Olist, embora abranja clientes de diferentes estados brasileiros; não representa uma amostra garantidamente representativa de todos os e-commerces do país.

Arquivos mínimos esperados: `olist_orders_dataset.csv`, `olist_order_items_dataset.csv`, `olist_customers_dataset.csv`, `olist_products_dataset.csv`, `product_category_name_translation.csv` (tradução opcional para exibição). Permitir nomes de colunas originais do dataset. A cópia local não deve ser publicada sem confirmar as condições da licença.

## 6. Jornada principal

1. O usuário inicia a aplicação.
2. A aplicação carrega e valida a base fixa.
3. O painel informa estado de carregamento, sucesso ou erro acionável.
4. O usuário consulta os KPIs gerais.
5. O usuário explora vendas por mês e categoria.
6. O usuário inspeciona os segmentos e compara suas métricas RFM.
7. O usuário lê recomendações e a evidência numérica que as originou.
8. O usuário consulta metodologia, fonte e limitações.

## 7. Definições analíticas

### 7.1 Universo de pedidos

- Considerar pedidos com status `delivered` para vendas e RFM.
- Excluir cancelados, indisponíveis e demais status não entregues das métricas principais. Exibir a regra em metodologia.
- Usar `order_purchase_timestamp` como data de compra. Converter para data/hora, derivar ano-mês local e ordenar cronologicamente.
- Remover registros sem chaves ou valores essenciais para a métrica correspondente; reportar contagens descartadas no diagnóstico de dados.

### 7.2 Receita, pedidos e ticket médio

- Receita de produtos = soma de `price` em linhas de itens associadas a pedidos entregues.
- Frete não integra a receita de produtos. Pode ser mostrado separadamente apenas se for implementado sem ambiguidade.
- Pedido = `order_id` distinto.
- Ticket médio = receita de produtos dividida pelo número de pedidos entregues no mesmo recorte.
- Clientes = `customer_unique_id` distinto. Não usar `customer_id` como identidade longitudinal, pois a base pode atribuir IDs de cadastro diferentes a uma mesma pessoa em compras diferentes.
- Não somar `payment_value` para receita junto com `price`: pagamentos parcelados/vouchers e itens múltiplos podem duplicar ou alterar a semântica.

### 7.3 Sazonalidade mensal

- Agregar por mês calendário (`YYYY-MM`) a partir da data de compra.
- Exibir receita de produtos, pedidos e ticket médio mensais.
- Comparações entre anos devem comparar o mesmo mês calendário quando houver dados.
- Exibir meses sem observação como lacunas ou zero somente após confirmar que a ausência significa zero e não falha de cobertura.
- Chamar o resultado de padrão histórico observado. Não inferir causalidade ou previsão.

### 7.4 RFM e K-means

Gerar uma linha por `customer_unique_id`, usando pedidos entregues:

- **Recency:** dias entre a data máxima de compra observada na base e a última compra do cliente. Menor é mais recente.
- **Frequency:** quantidade de `order_id` distintos do cliente.
- **Monetary:** soma de `price` das linhas de itens do cliente, sem frete.
- A data de referência do RFM é a data máxima observada nos pedidos entregues, não a data atual.
- Aplicar transformação `log1p` em Frequency e Monetary se necessário para reduzir assimetria, documentando os dados de entrada usados no K-means.
- Padronizar as três dimensões com `StandardScaler` antes do K-means.
- Fixar `random_state=42` e `n_init=10` (ou opção explícita equivalente na versão instalada) para reprodutibilidade.
- MVP usa `k=4` fixo para evitar seleção automática opaca; se não houver dados suficientes ou clusters distintos, retornar erro interpretável em vez de rotular resultados inválidos.
- Não atribuir significado de negócio aos IDs numéricos do cluster. Ordenar/rotular clusters após ajuste com base nos perfis observados: recência, frequência e gasto médios/medianos.
- Criar rótulos heurísticos legíveis apenas quando as regras forem explícitas; caso contrário usar “Segmento A/B/C/D” e apresentar perfil numérico.
- Mostrar contagem e percentual de clientes, recência mediana, frequência mediana, gasto mediano e ticket médio por segmento.
- Não tratar cluster como verdade natural nem como propensão comprovada de conversão.

### 7.5 Categorias e recomendações

- Ligar itens a produtos por `product_id`; usar tradução da categoria quando disponível, caso contrário usar o valor original e “Não informado” para nulos.
- Métricas de categoria: receita de produtos, quantidade de itens e pedidos distintos.
- Gerar recomendações por regras determinísticas, exibindo evidência e cautela. Exemplos:
  - “Avalie campanhas para o segmento X: representa Y% dos clientes e tem gasto mediano de R$ Z.”
  - “Investigue os meses A e B para planejamento de campanhas: tiveram maior receita observada no período disponível.”
  - “Considere destacar a categoria X: lidera em receita observada no recorte.”
- Recomendações não podem declarar que uma ação aumentará vendas. Usar termos como “considere”, “avalie” e “indica”.
- Não gerar uma recomendação quando a evidência for insuficiente ou métrica indisponível.

## 8. Experiência e interface

Produto de uso operacional, com foco em leitura rápida, comparação e exploração, não página de marketing.

- Idioma: português brasileiro.
- Moeda: BRL, formatada em reais; declarar que os valores são nominais do período da base e não foram corrigidos por inflação.
- Tema escuro baseado na referência REKKI: canvas `#000000`, superfícies `#040910` e `#0d0d0d`, azul `#0063e1`, texto principal branco, texto secundário `#858585`, linhas discretas.
- Tipografia substituta: Inter ou system sans; usar família monoespaçada discreta somente em rótulos técnicos/dados tabulares. Não depender de fontes comerciais indisponíveis.
- Cartões com borda interna sutil, radius aproximado 16px e padding 24px. A densidade dos gráficos deve priorizar legibilidade; não aplicar displays gigantes do site REKKI no painel.
- Navegação enxuta: Visão geral, Clientes, Sazonalidade e Categorias/Recomendações podem ser seções da mesma página ou abas, sem criar páginas artificiais.
- Responsivo para desktop e tablet; em telas estreitas, cartões e gráficos empilham, tabelas permitem rolagem ou alternativa resumida.
- Contraste acessível; não depender apenas de azul para codificar séries ou estados. Estados de foco visíveis e textos alternativos/nomes acessíveis para controles.
- Gráficos incluem títulos, unidade, eixos, tooltips com valores e estados vazios. Evitar gráficos 3D.
- Recomendações apresentam texto, tipo de decisão, métrica(s) de evidência, período e caveat quando aplicável.

## 9. Arquitetura de referência

Manter arquitetura simples adequada ao MVP. Proposta padrão: Python com Streamlit para aplicação e pandas para ETL; scikit-learn para padronização/K-means; biblioteca de gráficos compatível com a interface escolhida. O agente deve inspecionar o repositório antes de criar ou alterar estrutura e preferir convenções já existentes. Não adicionar backend/API se não houver requisito que justifique.

Separar responsabilidades em módulos simples: carregamento/validação, transformações analíticas, segmentação, recomendações e interface. Evitar lógica de cálculo extensa embutida nos componentes visuais.

## 10. Tratamento de falhas

- Arquivos ausentes: explicar quais arquivos faltam e como posicionar/baixar a base.
- Coluna obrigatória ausente ou esquema inválido: apresentar nome da coluna esperada e arquivo associado.
- CSV inválido/encoding: erro claro, sem traceback técnico apresentado ao usuário.
- Sem pedidos entregues, sem clientes válidos ou base menor que necessária: estado vazio com explicação, nunca inventar resultados.
- Falha no cálculo do K-means: manter as seções independentes utilizáveis e indicar que a segmentação não foi calculada.
- Se a aplicação não puder baixar a fonte por autenticação/restrição, suportar instrução de download manual e leitura dos CSVs locais.

## 11. Critérios globais de aceite

O MVP é aceito quando:

1. Inicia localmente seguindo instruções curtas no README.
2. Carrega a base fixa e valida esquema/arquivos.
3. Calcula KPIs por definições desta especificação sem duplicação de receita causada por junções.
4. Mostra série mensal ordenada e categoria por receita.
5. Segmenta clientes reprodutivelmente com RFM e K-means e mostra perfis interpretáveis.
6. Recomendações exibem evidência rastreável e linguagem cautelosa.
7. Interface segue a direção visual definida em `design.md`, incluindo estados responsivos e de erro.
8. Atribui dataset e declara período, limitações, licença e metodologia.
9. Não reivindica previsão nem representatividade nacional.

## 12. Premissas registradas

- “API gratuita” foi interpretada como preferência por fonte pública acessível; a decisão final aprovada é dataset fixo em arquivos CSV, sem API ao vivo.
- A análise nacional refere-se a compras em uma operação/marketplace brasileiro da Olist, com cobertura de vários estados.
- O relatório acadêmico de 8 a 12 páginas é produto do estudo, mas este MVP entrega somente o painel interativo.
