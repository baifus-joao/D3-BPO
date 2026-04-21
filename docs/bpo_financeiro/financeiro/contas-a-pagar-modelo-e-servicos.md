# Contas a Pagar - Modelo e Servicos

## Objetivo

Registrar a implementacao da camada de dados e da regra de negocio de `Contas a Pagar` na Fase 2A.

## O que foi implementado

- modelo `bpo_fin_payables`
- modelo `bpo_fin_payable_payments`
- modelo `bpo_fin_payable_events`
- migration `20260326_0005_finance_payables`
- servicos de criacao de titulo
- servicos de edicao de titulo aberto ou parcial
- servicos de baixa parcial e total
- servico de cancelamento
- servico de reativacao
- calculo automatico de `paid_amount`
- calculo automatico de status
- carga de overview pronta para a futura tela de contas a pagar

## Regras aplicadas

- cliente arquivado nao recebe novos titulos
- referencias financeiras devem pertencer ao mesmo cliente
- responsavel precisa ser usuario ativo
- baixa nao pode exceder valor em aberto
- titulo pago ou cancelado nao pode ser editado
- titulo com baixa registrada nao pode ser cancelado
- reativacao so vale para titulo cancelado

## Arquivos principais

- `webapp/finance_models.py`
- `webapp/finance_payables_services.py`
- `alembic/versions/20260326_0005_finance_payables.py`

## Status na Fase 2A

- Epic 4 concluido
- Epic 5 concluido

## Proximo passo

Criar a tela `finance_payables.html` e as rotas de operacao diaria para fechar o Epic 6.

## Links relacionados

- [[financeiro/fase-2a-base-e-contas-a-pagar]]
- [[processos/backlog-implementacao-fase-2a]]
- [[financeiro/configuracoes-financeiras]]
