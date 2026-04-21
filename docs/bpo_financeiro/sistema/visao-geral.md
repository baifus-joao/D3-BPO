# Visão Geral

## Descrição do sistema

O projeto é um sistema operacional para BPO financeiro construído sobre uma base já existente, sem reescrita completa. O sistema combina execução financeira, gestão operacional e controle da equipe em uma única aplicação.

## Objetivo do sistema

Transformar o sistema atual em uma plataforma completa para operação de BPO financeiro, reunindo:

- ERP financeiro para clientes
- gestão de tarefas por cliente e por competência
- conciliação financeira
- dashboard operacional
- automações futuras

## Conceito central

O sistema foi definido como a união de dois pilares:

- ERP financeiro
- gestão de tarefas e execução

Na prática, isso significa um produto híbrido:

- parte financeira para controlar pagar, receber, caixa, fechamento e relatórios
- parte operacional para controlar fila de trabalho, SLA, execução e pendências

## Contextos principais

- `D3 Gestão`: financeiro e controles internos da própria D3
- `D3 Operações`: execução dos serviços prestados aos clientes

## Estado atual do produto

### Base legada aproveitada

- autenticação e perfis
- conciliação de arquivos Excel
- fluxo de caixa interno da D3
- cadastros financeiros internos
- relatórios básicos

### Evolução já aplicada

- criação de domínio BPO separado do financeiro da D3
- clientes operacionais
- tarefas operacionais
- fila operacional
- conciliação vinculada a cliente, tarefa e período

## Links relacionados

- [[sistema/arquitetura]]
- [[decisoes/decisoes-iniciais]]
- [[financeiro/README]]
- [[tarefas/README]]
