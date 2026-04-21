# Requisitos da Fase 2

## Objetivo

Registrar os requisitos que o sistema ainda não contempla para que a próxima fase introduza o ERP financeiro dos clientes de forma estruturada.

## O que o sistema já contempla

- clientes
- contatos
- tarefas operacionais
- fila operacional
- conciliação vinculada a cliente, tarefa e período
- pendências operacionais da conciliação

## Requisitos ainda não contemplados

### Cadastro financeiro do cliente

- contas bancárias do cliente
- categorias financeiras do cliente
- centros de custo simplificados
- fornecedores por cliente
- clientes finais/sacados para contas a receber

### Contas a pagar

- lançamento de títulos a pagar
- vencimento e competência
- baixa de pagamento
- pagamento parcial
- cancelamento de título
- integração com conta bancária do cliente
- histórico de pagamentos

### Contas a receber

- lançamento de títulos a receber
- previsão de recebimento
- baixa parcial e total
- inadimplência
- situação por vencimento
- histórico de recebimentos

### Caixa e saldos

- saldo inicial por conta
- movimentações financeiras do cliente
- fluxo de caixa previsto e realizado
- posição de caixa por cliente
- conciliação entre pagar/receber e conta bancária

### Fechamento mensal

- competência financeira
- travamento de período
- checklist de fechamento
- status do fechamento
- resumo mensal consolidado

### Relatórios financeiros

- contas a pagar por vencimento
- contas a receber por vencimento
- fluxo de caixa por cliente
- resumo por categoria
- realizado versus previsto
- posição consolidada por competência

### Governança operacional

- SLA financeiro
- responsável por lançamento
- trilha de auditoria de alterações
- justificativas e observações por baixa
- anexos ou evidências financeiras

## Ordem recomendada

1. contas bancárias do cliente
2. categorias e fornecedores
3. contas a pagar
4. contas a receber
5. caixa
6. fechamento
7. relatórios

## Observação arquitetural

Esses requisitos devem entrar em um domínio separado do financeiro interno da D3, preservando a distinção entre:

- `d3_*` para operação interna
- `bpo_*` ou `bpo_fin_*` para ERP dos clientes

## Links relacionados

- [[financeiro/README]]
- [[sistema/arquitetura]]
- [[decisoes/decisoes-iniciais]]
