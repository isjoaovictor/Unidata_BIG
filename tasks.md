# Tasks: E-commerce Insights MVP

## Orientação ao agente executor

Implemente de ponta a ponta, com intervenção humana mínima. Antes de editar, inspecione o repositório, `AGENTS.md`, estrutura e dependências já existentes. Preserve decisões já presentes que não contradigam este SDD. Não solicite escolha humana para detalhes rotineiros; use os padrões deste documento e registre decisões técnicas. Não invente dados. Não coloque os CSVs licenciados no repositório público sem confirmar as condições da licença.

## Fase 0 — Descoberta e plano

- [ ] Ler `AGENTS.md` e examinar a estrutura do projeto e estado do Git.
- [ ] Identificar linguagem/framework existentes; se projeto vazio, usar Python e Streamlit conforme `spec.md`.
- [ ] Confirmar a presença dos arquivos da Olist; se ausentes, criar instrução de download e diretório esperado sem tentar contornar autenticação.
- [ ] Registrar plano técnico breve e mapa de módulos antes de implementar.

**Aceite:** nenhuma estrutura existente foi sobrescrita sem inspeção; dados faltantes resultam em fluxo de instalação documentado.

## Fase 1 — Contratos e dependências

- [ ] Definir dependências mínimas e fixar versões compatíveis.
- [ ] Criar configuração central para caminhos de dados, nomes de colunas e parâmetros RFM.
- [ ] Definir interfaces de funções para carregar/validar, transformar, agregar, clusterizar e gerar recomendações.
- [ ] Preparar fixtures sintéticas pequenas apenas para validação automatizada, claramente separadas da base real.

**Aceite:** processamento pode ser executado sem a interface e sem acessar rede.

## Fase 2 — Pipeline de dados

- [ ] Carregar CSVs necessários com encoding apropriado e erros legíveis.
- [ ] Validar esquema mínimo por arquivo.
- [ ] Converter timestamps, preços e identificadores, preservando IDs como texto.
- [ ] Filtrar pedidos entregues conforme regras.
- [ ] Juntar orders, order_items, customers e products sem multiplicar linhas de itens por junções 1:N desnecessárias.
- [ ] Deduplicar ou sinalizar chaves inconsistentes sem apagar transações silenciosamente.
- [ ] Gerar diagnóstico: linhas lidas, descartadas, chaves ausentes, intervalo temporal e pedidos elegíveis.
- [ ] Aplicar cache de leitura/preparo se suportado pelo framework.

**Aceite:** fixture com pedido de múltiplos itens mantém soma correta; junção com múltiplos pagamentos não multiplica receita.

## Fase 3 — Métricas analíticas

- [ ] Calcular KPIs gerais segundo `spec.md`.
- [ ] Calcular série mensal, garantindo ordenação e tratamento honesto de meses ausentes.
- [ ] Calcular agregações por categoria e rótulos para nulos/traduções ausentes.
- [ ] Criar tabela RFM por `customer_unique_id`, usando data de referência observada.
- [ ] Transformar/padronizar features e aplicar K-means com parâmetros fixos.
- [ ] Produzir perfis descritivos por cluster e rótulos transparentes.
- [ ] Tratar base pequena, features constantes e falhas de convergência sem saída enganosa.

**Aceite:** métricas consistentes com as fórmulas; repetição com mesmos dados resulta em clusters reprodutíveis.

## Fase 4 — Recomendações

- [ ] Implementar regras determinísticas para segmentos, meses e categorias.
- [ ] Incluir valor(es), período e explicação que disparou cada recomendação.
- [ ] Omitir recomendação sem evidência suficiente.
- [ ] Adotar linguagem não causal e caveat sobre histórico da Olist.

**Aceite:** cada recomendação pode ser rastreada a valores calculados e não promete resultado futuro.

## Fase 5 — Interface com Impeccable

- [ ] Carregar a skill Impeccable no ambiente do agente conforme instruções da skill. Usar o caminho da skill já instalado; não reinstalar nem presumir comandos inexistentes.
- [ ] Fornecer à skill a referência `upload/DESIGN(1).md` e este `design.md`.
- [ ] Aplicar a interface no modo **Operate**: hierarquia de leitura, precisão, padrões familiares de analytics e identidade REKKI em detalhes.
- [ ] Implementar cabeçalho com nome, fonte/período e filtro temporal.
- [ ] Implementar visão geral com KPIs, tendência mensal, segmentos, categorias e recomendações.
- [ ] Implementar navegação/âncoras/abas somente quando ajudarem a explorar; sem páginas decorativas.
- [ ] Implementar estados carregando, sucesso, vazio, erro e falha parcial.
- [ ] Aplicar BRL, formatos de data, unidades e textos em pt-BR.
- [ ] Garantir responsividade, acessibilidade básica, foco e alternativa textual/tabela para gráficos.
- [ ] Renderizar/capturar em viewport desktop e estreita; inspecionar e corrigir falhas visuais importantes.
- [ ] Se Impeccable não estiver instalado no executor, registrar no README como instalar/ativar para o agente-alvo e seguir `design.md` sem afirmar que a skill foi executada.

**Aceite:** visual atende à direção do `design.md`, dados seguem legíveis e controles funcionam nos tamanhos alvo.

## Fase 6 — Validação funcional e acadêmica

- [ ] Adicionar verificações automatizadas para fórmulas, granularidade e regras de recomendações.
- [ ] Executar a suíte e corrigir falhas antes de concluir.
- [ ] Iniciar a aplicação localmente e percorrer a jornada principal.
- [ ] Conferir contagens plausíveis da base versus diagnóstico, sem hardcode de resultados.
- [ ] Conferir gráficos, moeda, datas, textos de estado e consistência dos filtros.
- [ ] Conferir atribuição Kaggle/Olist, licença CC BY-NC-SA 4.0, período e caveats.

**Aceite:** app executa com base local; resultados e interface não mostram dados simulados como reais.

## Fase 7 — Entrega

- [ ] Escrever README curto com pré-requisitos, download manual da base, estrutura dos arquivos e comandos de execução.
- [ ] Documentar módulos, definições de métricas, K-means, limitações e licença.
- [ ] Manter dados Olist fora do versionamento salvo se a licença e escopo do repositório permitirem explicitamente.
- [ ] Resumir alterações, como executar, validações realizadas, limitações e itens não executados.

**Aceite:** outro estudante consegue iniciar o MVP com a documentação e a base obtida da fonte citada.

## Dependências e ordem

Ordem recomendada: Fase 0 → Fase 1 → Fase 2 → Fase 3 → Fase 4 → Fase 5 → Fase 6 → Fase 7. A interface pode iniciar com contratos e fixtures enquanto o pipeline é construído, mas não deve apresentar fixtures como dados de produção.
