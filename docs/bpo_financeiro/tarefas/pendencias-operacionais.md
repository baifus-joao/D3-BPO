# Pendências Operacionais

## Objetivo

Transformar divergências detectadas pela conciliação em itens operacionais acompanháveis, com status e contexto por cliente.

## Situação implementada

- cada divergência persistida em `bpo_conciliation_items`
- tela central de pendências operacionais
- filtro por cliente, status e tipo
- atualização manual de status
- visão resumida das pendências dentro do detalhe do cliente

## Status atualmente usados

- `aberto`
- `em_analise`
- `aguardando_cliente`
- `resolvido`
- `descartado`

## Papel no fluxo do BPO

As pendências conectam a conciliação à operação diária. Elas evitam que uma divergência fique presa apenas no relatório final da planilha e permitem rastrear:

- o que está em aberto
- o que depende do cliente
- o que já foi tratado

## Próximas evoluções possíveis

- responsável por pendência
- prazo/SLA por pendência
- comentários estruturados
- anexos e evidências
- geração automática de tarefa derivada da pendência

## Links relacionados

- [[sistema/arquitetura]]
- [[decisoes/decisoes-iniciais]]
- [[clientes/README]]
