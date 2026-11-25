# Apresentação do Unidata

Apresentação interativa gerada a partir do repositório, seguindo o formato da skill [`project-showcase`](https://github.com/isjoaovictor/project_showcase_skill).

## Como abrir

Abra `showcase.html` em qualquer navegador moderno. É um arquivo único, sem servidor, sem fontes externas e sem chaves de API.

- **Navegar**: botões *Anterior/Próximo*, índice lateral, ou teclas `←` `→` (e `1`–`8` para ir direto a um capítulo).
- **Capítulos**: 1 Introdução · 2 Objetivos · 3 Fundamentação teórica · 4 Metodologia / pipeline de dados · 5 Ferramentas utilizadas · 6 Resultados obtidos · 7 Discussão e limitações · 8 Conclusão e referências.

## Simulação x execução real

- O capítulo 4 tem um **percurso didático** dos dados, rotulado `Simulação ilustrativa`. Ele não executa o código nem lê arquivos.
- Os números do capítulo 6 foram **calculados com as funções reais do projeto** sobre a fixture sintética `tests/fixtures/standard_olist` e estão rotulados `Fixture sintética de teste, não é a base da Olist`. Nenhuma métrica da base real é exibida.

## Como personalizar

- Identidade, capítulos, funcionalidades e tecnologias estão em `showcase.config.json`. O HTML não lê esse arquivo em tempo de execução; ao alterar um, mantenha o outro coerente.
- Fontes e itens a confirmar: `SOURCES.md`.
- Cores: variáveis CSS no topo do `<style>` de `showcase.html` (tokens do `design.md`).
