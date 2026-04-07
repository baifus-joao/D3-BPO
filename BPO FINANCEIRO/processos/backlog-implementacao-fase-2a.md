# Backlog de Implementacao - Fase 2A

## Objetivo

Quebrar a Fase 2A em entregas executáveis, para permitir implementação incremental no sistema atual.

## Epic 1 - Estrutura financeira básica

### Status atual

- implementado em 2026-03-26
- models criados em `webapp/finance_models.py`
- migration criada em `alembic/versions/20260326_0004_finance_base.py`
- validado com `alembic upgrade head` em SQLite limpo

### Entregas

- criar `finance_models.py`
- adicionar tabelas de contas bancárias
- adicionar tabelas de categorias
- adicionar tabelas de centros de custo
- adicionar tabelas de fornecedores
- adicionar tabelas de formas de pagamento

### Critério de pronto

- migrations aplicam em banco limpo
- cliente consegue ter estrutura financeira própria

## Epic 2 - Serviços de cadastro financeiro

### Status atual

- implementado em 2026-03-26
- serviços criados em `webapp/finance_services.py`
- validado em SQLite temporário com criação real de registros

### Entregas

- criar serviços de criação, edição e listagem
- validar client_id em todas as operações
- impedir cadastro em cliente arquivado

### Critério de pronto

- dados são carregados por cliente e usados nas telas

## Epic 3 - Tela de configurações financeiras

### Status atual

- implementado em 2026-03-26
- rota criada em `/operacoes/financeiro/configuracoes`
- template criado em `webapp/templates/finance_settings.html`
- navegação adicionada ao menu de `Operacoes`

### Entregas

- criar rota de configurações financeiras
- criar template de configuração
- permitir cadastro rápido por bloco
- mostrar listas já cadastradas

### Critério de pronto

- operador consegue preparar um cliente para uso financeiro sem sair da tela

## Epic 4 - Modelo de contas a pagar

### Status atual

- implementado em 2026-03-26
- tabelas adicionadas em `webapp/finance_models.py`
- migration criada em `alembic/versions/20260326_0005_finance_payables.py`
- validado com `alembic upgrade head` em SQLite limpo

### Entregas

- criar tabela de títulos a pagar
- criar tabela de baixas
- criar tabela de eventos do título
- definir enums de status

### Critério de pronto

- lançamento e histórico estão persistidos

## Epic 5 - Serviços de contas a pagar

### Status atual

- implementado em 2026-03-26
- serviços criados em `webapp/finance_payables_services.py`
- fluxo validado com criação, edição, baixa parcial, cancelamento e reativação em SQLite temporário

### Entregas

- criar título
- editar título aberto
- cancelar título
- registrar baixa parcial
- calcular status automaticamente
- registrar eventos

### Critério de pronto

- fluxo principal do pagar funciona sem intervenção manual no banco

## Epic 6 - Tela de contas a pagar

### Entregas

- criar rota de listagem
- criar filtros operacionais
- criar cards de resumo
- criar formulário de lançamento
- criar ação de baixa
- criar ação de cancelamento

### Critério de pronto

- a operação diária de pagar consegue acontecer pela interface

## Epic 7 - Resumo financeiro no cliente

### Entregas

- adicionar aba ou bloco financeiro no detalhe do cliente
- mostrar contas bancárias
- mostrar fornecedores
- mostrar títulos em aberto
- mostrar próximos vencimentos

### Critério de pronto

- a visão do cliente concentra operação e financeiro inicial

## Ordem de execução

1. Epic 1 - concluído
2. Epic 2 - concluído
3. Epic 3 - concluído
4. Epic 4 - concluído
5. Epic 5 - concluído
6. Epic 6
7. Epic 7

## Riscos

- misturar domínio financeiro do cliente com domínio interno da D3
- crescer `app_modular.py` em excesso
- não tratar corretamente baixa parcial
- permitir ações em cliente arquivado

## Estratégia de implementação

- criar novos serviços em arquivos dedicados
- manter mudanças pequenas por commit
- validar cada epic com banco SQLite isolado
- atualizar o vault ao final de cada bloco relevante

## Links relacionados

- [[financeiro/fase-2a-base-e-contas-a-pagar]]
- [[processos/backlog-fase-2-erp-clientes]]
- [[processos/uso-codex]]
