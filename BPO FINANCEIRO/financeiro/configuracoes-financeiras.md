# Configuracoes Financeiras

## Objetivo

Registrar a implementacao inicial do cadastro financeiro dos clientes dentro de `Operacoes`.

## O que foi implementado

- menu `Financeiro` em `Operacoes`
- tela `/operacoes/financeiro/configuracoes`
- selecao de cliente para estruturar a base financeira
- cadastro de contas bancarias
- cadastro de categorias financeiras
- cadastro de centros de custo
- cadastro de fornecedores
- cadastro de formas de pagamento

## Arquivos principais

- `webapp/finance_models.py`
- `webapp/finance_services.py`
- `webapp/templates/finance_settings.html`
- `webapp/app_modular.py`
- `webapp/erp.py`

## Regras aplicadas

- cliente arquivado nao recebe novos cadastros financeiros
- nao permitir duplicidade basica por cliente nos cadastros principais
- toda estrutura financeira permanece separada do dominio `d3_*`
- a tela trabalha com foco em um cliente por vez

## Status na Fase 2A

- Epic 1 concluido
- Epic 2 concluido
- Epic 3 concluido

## Proximo bloco

Entrar no modelo e servicos de `Contas a Pagar`, usando essa base como dependencia.

## Links relacionados

- [[financeiro/fase-2a-base-e-contas-a-pagar]]
- [[processos/backlog-implementacao-fase-2a]]
- [[decisoes/decisoes-iniciais]]
