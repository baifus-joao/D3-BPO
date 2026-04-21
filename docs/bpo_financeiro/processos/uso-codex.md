# Uso do Codex

## Objetivo deste guia

Padronizar como o Codex deve ser usado no projeto para manter qualidade, custo previsível e continuidade de contexto.

## Estratégia de intensidade

### `low`

Use para tarefas simples e localizadas:

- ajustes pequenos de layout
- correções pontuais
- comandos rápidos
- dúvidas específicas sobre um arquivo

### `medium`

Use para a maioria das entregas:

- implementar funcionalidade incremental
- revisar fluxo existente
- criar telas ou rotas novas
- modelar pequenas evoluções de banco

### `high`

Use quando houver risco maior ou acoplamento alto:

- mudanças estruturais
- redesign de módulos
- modelagem mais ampla de ERP
- refatoração de regras centrais
- investigação de falhas difíceis

## Estratégia de contexto

- Sempre partir do código real do projeto.
- Ler os arquivos principais antes de propor mudanças.
- Persistir decisões e conclusões relevantes neste vault.
- Evitar depender apenas da conversa corrente.
- Atualizar a documentação quando houver mudança estrutural.

## Uso de tokens e escopo

- Escopo pequeno: atacar um bloco de cada vez.
- Evitar pedir mudanças muito amplas sem segmentação.
- Preferir fases e subfases.
- Quando a mudança for grande, registrar primeiro decisão e arquitetura.

## Fluxo recomendado

1. Entender o contexto do código.
2. Registrar decisões relevantes no vault.
3. Implementar incrementalmente.
4. Validar localmente.
5. Atualizar a memória persistente.

## Quando atualizar o vault

- nova decisão arquitetural
- novo módulo
- mudança de roadmap
- alteração relevante de fluxo
- nova convenção de uso do sistema

## Links relacionados

- [[decisoes/decisoes-iniciais]]
- [[sistema/obsidian-integracao]]
