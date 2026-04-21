# Fase 2A - Base Financeira e Contas a Pagar

## Objetivo

Entregar o primeiro módulo de ERP financeiro dos clientes com uso real em operação, começando pela fundação cadastral e pelo fluxo de contas a pagar.

## Escopo da Fase 2A

Esta fase cobre:

1. base financeira do cliente
2. contas a pagar

Não cobre ainda:

- contas a receber
- tesouraria consolidada completa
- fechamento mensal
- relatórios avançados
- aprovações complexas

## Resultado esperado

Ao final da Fase 2A o sistema deve permitir:

- cadastrar a estrutura financeira básica de um cliente
- lançar títulos a pagar
- acompanhar vencimentos
- registrar pagamentos parciais e totais
- consultar histórico de pagamento
- filtrar e operar a carteira de títulos

## Módulos funcionais

### Cadastro financeiro do cliente

- contas bancárias
- categorias financeiras
- centros de custo simplificados
- fornecedores
- formas de pagamento

### Contas a pagar

- lançamento manual de título
- status do título
- baixa financeira
- cancelamento
- observações
- histórico

## Modelagem de dados sugerida

### `bpo_fin_bank_accounts`

- `id`
- `client_id`
- `bank_name`
- `account_name`
- `agency`
- `account_number`
- `pix_key`
- `initial_balance`
- `is_active`
- `created_at`
- `updated_at`

### `bpo_fin_categories`

- `id`
- `client_id`
- `name`
- `kind` (`entrada` ou `saida`)
- `parent_id`
- `is_active`
- `created_at`
- `updated_at`

### `bpo_fin_cost_centers`

- `id`
- `client_id`
- `name`
- `is_active`
- `created_at`
- `updated_at`

### `bpo_fin_suppliers`

- `id`
- `client_id`
- `name`
- `document`
- `email`
- `phone`
- `is_active`
- `created_at`
- `updated_at`

### `bpo_fin_payment_methods`

- `id`
- `client_id`
- `name`
- `is_active`
- `created_at`
- `updated_at`

### `bpo_fin_payables`

- `id`
- `client_id`
- `supplier_id`
- `category_id`
- `cost_center_id`
- `payment_method_id`
- `bank_account_id`
- `title`
- `description`
- `document_number`
- `issue_date`
- `due_date`
- `competence_date`
- `amount`
- `paid_amount`
- `status`
- `assigned_user_id`
- `created_by_user_id`
- `notes`
- `created_at`
- `updated_at`
- `cancelled_at`

### `bpo_fin_payable_payments`

- `id`
- `payable_id`
- `bank_account_id`
- `payment_date`
- `amount`
- `reference`
- `notes`
- `created_by_user_id`
- `created_at`

### `bpo_fin_payable_events`

- `id`
- `payable_id`
- `user_id`
- `event_type`
- `description`
- `created_at`

## Regras de negócio mínimas

- um título pertence a um único cliente
- um título pode ter múltiplas baixas
- `paid_amount` é a soma das baixas realizadas
- status do título:
  - `aberto`
  - `parcial`
  - `pago`
  - `cancelado`
- título `pago` ou `cancelado` não pode ser excluído
- baixa não pode exceder o valor em aberto
- cliente arquivado não recebe novos títulos

## Rotas sugeridas

### Cadastros financeiros

- `GET /operacoes/financeiro/configuracoes`
- `POST /operacoes/financeiro/contas-bancarias`
- `POST /operacoes/financeiro/categorias`
- `POST /operacoes/financeiro/centros-custo`
- `POST /operacoes/financeiro/fornecedores`
- `POST /operacoes/financeiro/formas-pagamento`

### Contas a pagar

- `GET /operacoes/financeiro/pagar`
- `POST /operacoes/financeiro/pagar`
- `POST /operacoes/financeiro/pagar/{payable_id}/editar`
- `POST /operacoes/financeiro/pagar/{payable_id}/baixar`
- `POST /operacoes/financeiro/pagar/{payable_id}/cancelar`
- `POST /operacoes/financeiro/pagar/{payable_id}/reativar`

## Telas sugeridas

### `finance_settings.html`

Função:

- concentrar os cadastros financeiros básicos por cliente

Blocos:

- contas bancárias
- categorias
- centros de custo
- fornecedores
- formas de pagamento

### `finance_payables.html`

Função:

- listar e operar títulos a pagar

Filtros:

- cliente
- status
- fornecedor
- vencimento
- responsável

Componentes:

- cards de resumo
- tabela/lista de títulos
- formulário de novo lançamento
- ação de baixa
- ação de cancelamento

### `client_financial_tab.html`

Função:

- mostrar, dentro do cliente, o resumo financeiro da Fase 2A

Blocos:

- contas bancárias
- fornecedores
- títulos em aberto
- vencimentos próximos

## Serviços sugeridos

- `webapp/finance_models.py`
- `webapp/services/finance_setup.py`
- `webapp/services/finance_payables.py`

## Integração com o sistema atual

- manter `d3_financial_transactions` apenas para a D3
- usar `bpo_clients` como entidade-mãe do ERP do cliente
- manter a navegação financeira dentro de `Operações`
- reutilizar autenticação, perfis e layout atual

## Sequência recomendada de implementação

1. modelagem SQLAlchemy - concluída
2. migration Alembic - concluída
3. serviços de cadastro financeiro
4. tela de configurações financeiras
5. serviços de contas a pagar
6. tela de contas a pagar
7. aba financeira no detalhe do cliente

## Critérios de aceite

- é possível cadastrar uma conta bancária por cliente
- é possível cadastrar fornecedor e categoria
- é possível criar um título a pagar
- é possível registrar baixa parcial
- é possível concluir o pagamento total do título
- é possível visualizar títulos por status e vencimento

## Status atual

- Epic 1 concluído com criação da base financeira do cliente
- Epic 2 concluído com serviços de cadastro financeiro
- Epic 3 concluído com tela e rotas de configurações financeiras
- Epic 4 concluído com o modelo de contas a pagar
- Epic 5 concluído com os serviços de contas a pagar
- próximo passo imediato: Epic 6

## Links relacionados

- [[financeiro/requisitos-fase-2]]
- [[processos/backlog-fase-2-erp-clientes]]
- [[sistema/arquitetura]]
