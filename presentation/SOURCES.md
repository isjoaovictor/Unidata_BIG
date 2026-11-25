# Fontes da apresentação

Lidas em 25/11/2026. Cada afirmação do `showcase.html` vem de uma destas fontes.

| Afirmação | Fonte | Status |
|---|---|---|
| Propósito, escopo, usuário e decisões apoiadas | `../spec.md` (seções 1–4) | Documentado |
| Definições de receita, pedidos, clientes, sazonalidade, RFM e K-means | `../spec.md` (seção 7) e `../src/unidata/` | Implementado |
| Pipeline de módulos (loader → pipeline → analytics/segmentation → recommendations → UI) | `../src/unidata/*.py`, `../app.py` | Implementado |
| Tokens visuais e estrutura do painel | `../design.md` | Implementado (`../src/unidata/ui/theme.py`) |
| Testes automatizados | `../tests/` | Implementado |
| Números de KPIs, mês e categorias exibidos no capítulo 6 | Cálculo das funções do projeto sobre `../tests/fixtures/standard_olist` | **Fixture sintética, não é a base Olist** |
| Descrição, período (≈ 09/2016 a 09/2018), licença CC BY-NC-SA 4.0 | <https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce> | Citado da spec; a página do Kaggle não foi reconsultada nesta geração |
| Formato da apresentação (capítulos, simulações rotuladas, status honestos) | <https://github.com/isjoaovictor/project_showcase_skill> (`SKILL.md`, `references/`) | Aplicado |

## Fontes consultadas no repositório

Arquivos locais lidos para esta apresentação: `spec.md`, `requirements.md`, `design.md`, `tasks.md`, `README.md` (raiz do projeto), `src/unidata/*.py`, `app.py` e `tests/`.

## Itens que exigem atualização

- Execução sobre a base real da Olist: `não verificado` (os CSVs não estão no repositório).
- Autoria e créditos da equipe: não documentados, por isso não aparecem na apresentação.
- Logotipo: o projeto não tem logotipo oficial; a marca é exibida como texto.
