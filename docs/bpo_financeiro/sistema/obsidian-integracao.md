# Integração com Obsidian

## Papel do vault

Este vault é a memória oficial do sistema de BPO financeiro. Ele existe para reduzir dependência do contexto temporário da conversa e deixar o conhecimento acessível para qualquer desenvolvedor ou operador técnico do projeto.

## Como o Obsidian está sendo usado

- documentação viva do sistema
- registro de decisões
- organização de arquitetura
- base de apoio para roadmap
- memória persistente do projeto

## Como o Codex interage com o vault

O Codex deve:

- ler a estrutura existente do vault
- criar e editar arquivos `.md`
- persistir o conhecimento relevante do que foi discutido e implementado
- evitar duplicação desnecessária
- conectar os arquivos por links quando fizer sentido

## Regras práticas adotadas

- usar Markdown estruturado
- não apagar conteúdo importante sem preservar contexto
- registrar evolução por tema, não de forma solta
- tratar o vault como fonte oficial de memória do sistema

## Organização atual do vault

- `sistema/`: visão do produto, arquitetura e integrações
- `processos/`: modo de trabalho e uso do Codex
- `decisoes/`: decisões arquiteturais e estratégicas
- `clientes/`: conhecimento futuro sobre carteira e operação por cliente
- `financeiro/`: ERP e operação financeira
- `tarefas/`: gestão operacional e fila

## Regra de atualização contínua

A partir desta base:

- novas decisões devem atualizar `decisoes/`
- mudanças estruturais devem atualizar `sistema/`
- novos módulos financeiros devem atualizar `financeiro/`
- novos fluxos operacionais devem atualizar `tarefas/` e `processos/`

## Links relacionados

- [[Bem-vindo]]
- [[sistema/visao-geral]]
- [[sistema/arquitetura]]
- [[processos/uso-codex]]
