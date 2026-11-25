# Requirements: E-commerce Insights

## Objetivo

Definir requisitos funcionais e não funcionais verificáveis para um painel acadêmico de analytics de e-commerce implementado autonomamente por um agente de desenvolvimento.

## Requisitos funcionais

### FR-01 — Carregar base fixa

O sistema deve carregar os CSVs locais da base Olist definida em `spec.md` sem exigir API ou seleção de outra base.

**Aceite:** ao iniciar, a aplicação carrega a base disponível ou mostra instruções específicas para os arquivos ausentes; nunca exibe dados simulados como se fossem reais.

### FR-02 — Validar e preparar dados

O sistema deve validar colunas obrigatórias, converter datas e valores numéricos, filtrar pedidos conforme a especificação, resolver relacionamentos e registrar contagens de exclusão/ausência.

**Aceite:** esquema inválido produz mensagem legível com arquivo e coluna; transformações não duplicam a receita ao juntar tabelas de granularidades diferentes.

### FR-03 — KPIs de visão geral

Exibir receita de produtos, pedidos entregues, clientes únicos e ticket médio para a cobertura disponível.

**Aceite:** cada KPI usa as fórmulas de `spec.md`; moeda em BRL; período histórico e unidade visíveis.

### FR-04 — Explorar série mensal

Exibir receita, pedidos e ticket médio por mês calendário.

**Aceite:** meses cronológicos, valores identificáveis por eixo e tooltip; título e notas deixam claro que é histórico.

### FR-05 — Segmentar clientes

Calcular RFM por cliente único e aplicar K-means com parâmetros reprodutíveis definidos em `spec.md`.

**Aceite:** apresentar número de clientes e percentuais por cluster, além de estatísticas RFM por perfil. IDs arbitrários do K-means não são apresentados como hierarquia de valor.

### FR-06 — Explorar categorias

Agregar métricas de vendas por categoria de produto.

**Aceite:** categoria sem tradução continua identificável; nulos são rotulados; ranking indica métrica e período coberto.

### FR-07 — Recomendações explicáveis

Gerar recomendações por regras transparentes sobre segmento, sazonalidade e categoria.

**Aceite:** toda recomendação mostra ao menos uma métrica e período como evidência; linguagem não promete efeito causal ou aumento futuro de vendas.

### FR-08 — Filtros interativos

Permitir filtrar por ano ou intervalo de meses, propagando o recorte às métricas compatíveis. O painel deve identificar claramente quando uma métrica de segmento usa janela ou população distinta.

**Aceite:** filtro atualiza os gráficos e indicadores de maneira consistente; se o RFM permanecer calculado sobre a base completa, a interface deve declará-lo explicitamente. Preferir recalcular RFM no período selecionado somente se a janela resultar em contagem suficiente e metodologia coerente.

### FR-09 — Metodologia e proveniência

Exibir fonte, autoria/atribuição, licença, período, definição de métricas, regra de pedidos, data de referência do RFM e limitações.

**Aceite:** informação acessível no painel sem exigir consulta ao código.

### FR-10 — Estados operacionais

Apresentar estados de carregamento, pronto, base ausente/inválida, dados vazios e falha parcial de segmentação.

**Aceite:** falha de um módulo não derruba as análises válidas restantes; não são exibidos gráficos vazios sem explicação.

## Requisitos não funcionais

### NFR-01 — Reprodutibilidade

O mesmo dataset e configuração devem produzir os mesmos resultados de cluster, respeitados ambiente e versão de dependências. Fixar sementes e registrar versões.

### NFR-02 — Desempenho

Com a base Olist local, a primeira carga deve concluir em tempo razoável para demonstração acadêmica. Evitar reler e recalcular dados em cada interação quando o framework permitir cache seguro.

### NFR-03 — Usabilidade

Textos e rótulos em português brasileiro; KPIs e gráficos devem ser compreensíveis sem ler documentação técnica.

### NFR-04 — Acessibilidade

Contraste suficiente, foco visível, controles com rótulos, gráficos com alternativa textual/tabela e codificação que não dependa só da cor.

### NFR-05 — Responsividade

Conteúdo funcional em desktop, tablet e tela estreita, com adaptação sem corte de controles ou métricas essenciais.

### NFR-06 — Privacidade e escopo

Não coletar dados pessoais de usuários do painel, não exigir autenticação, não enviar dados carregados a terceiros e não persistir informações além do necessário à sessão local.

### NFR-07 — Licença e atribuição

Incluir a atribuição da fonte e observar CC BY-NC-SA 4.0. O projeto deve indicar restrição não comercial e compartilhamento sob a mesma licença nos materiais derivados, conforme aplicável.

### NFR-08 — Manutenibilidade

Separar processamento, análise, visualização e configuração. Usar nomes claros, dependências mínimas e instruções de execução no README.

### NFR-09 — Segurança de execução

Não executar conteúdo vindo de CSV, não construir SQL dinâmico desnecessário, não incluir segredos, e manter leitura restrita à pasta de dados configurada.

## Requisitos analíticos e regras de negócio

- Pedidos entregues compõem as métricas principais.
- Receita é soma de preços dos itens, excluindo frete.
- Ticket médio divide receita de itens por pedidos distintos.
- Cliente é `customer_unique_id`.
- Sazonalidade usa mês calendário e data de compra.
- RFM usa recência relativa ao último dia observado, frequência de pedidos distintos e valor de itens.
- K-means recebe features transformadas/padronizadas, parâmetros estáveis e saída semanticamente interpretada por perfil.
- Recomendações têm regra, evidência e ressalva; são apoio à decisão, não prescrição automática.

## Dependências externas

- Download manual da base pelo Kaggle pode requerer conta e aceitação de termos da plataforma.
- Kaggle indica licença CC BY-NC-SA 4.0 e ausência de atualização esperada.
- Não depender de disponibilidade de API externa em runtime.

## Critérios de pronto

- Todos os FRs aplicáveis têm implementação e evidência de aceite.
- Cálculos críticos têm validação automatizada com fixtures pequenos e casos de múltiplos itens por pedido, múltiplos registros de pagamento e IDs de cliente repetidos.
- README explica download, posicionamento dos CSVs e execução local.
- O painel apresenta metodologia, data, licença e limitações.
- Capturas desktop e estreita foram inspecionadas pelo agente implementador ao aplicar Impeccable.
