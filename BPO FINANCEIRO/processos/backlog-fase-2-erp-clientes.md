# Backlog da Fase 2 - ERP dos Clientes

## Objetivo

Transformar a base operacional da Fase 1 em um ERP financeiro utilizável no dia a dia do BPO, cobrindo o ciclo financeiro do cliente sem misturar com o financeiro interno da D3.

## Premissas

- manter a stack atual
- manter separação entre `d3_*` e `bpo_*`/`bpo_fin_*`
- implementar em blocos pequenos e utilizáveis
- priorizar funcionalidades que fecham operação real antes de BI avançado

## Escopo funcional definido

O sistema passará a contemplar, além do que já existe na Fase 1:

1. cadastro financeiro do cliente
2. contas a pagar
3. contas a receber
4. tesouraria e caixa
5. fechamento mensal
6. relatórios financeiros operacionais
7. aprovações e governança
8. anexos e evidências financeiras
9. alertas e agenda financeira
10. importações e automações simples

## Backlog priorizado

### Bloco 1 - Base financeira do cliente

Objetivo: criar a fundação para todos os módulos financeiros.

- contas bancárias do cliente
- categorias financeiras
- centros de custo simplificados
- fornecedores
- clientes finais ou sacados
- formas de pagamento
- responsáveis financeiros por cliente

### Bloco 2 - Contas a pagar

Objetivo: permitir operação real de saída financeira do cliente.

- cadastro manual de títulos a pagar
- vencimento e competência
- status do título: aberto, agendado, pago, cancelado
- baixa total e parcial
- histórico de pagamento
- observações por lançamento
- vínculo com fornecedor, categoria, centro de custo e conta bancária
- filtro por cliente, status, vencimento e responsável

### Bloco 3 - Contas a receber

Objetivo: controlar entradas previstas e realizadas do cliente.

- cadastro de títulos a receber
- previsão de recebimento
- baixa total e parcial
- controle de atraso e inadimplência
- histórico de recebimentos
- vínculo com sacado, categoria e conta bancária
- filtro por cliente, status, vencimento e responsável

### Bloco 4 - Tesouraria e caixa

Objetivo: consolidar movimentação e saldo por cliente.

- saldo inicial por conta bancária
- lançamentos avulsos de entrada e saída
- extrato interno por conta
- saldo realizado
- saldo projetado
- vínculo automático com baixas de pagar e receber
- visão consolidada de caixa por cliente

### Bloco 5 - Fechamento mensal

Objetivo: institucionalizar o fechamento financeiro da carteira.

- competência financeira
- checklist de fechamento
- status do fechamento: aberto, em revisão, fechado
- trava de período fechado
- resumo mensal consolidado
- vínculo com tarefas recorrentes da operação

### Bloco 6 - Relatórios financeiros

Objetivo: entregar visibilidade operacional e gerencial.

- contas a pagar por vencimento
- contas a receber por vencimento
- fluxo de caixa por cliente
- posição de caixa
- realizado versus previsto
- resumo por categoria
- visão por competência

### Bloco 7 - Governança e aprovação

Objetivo: dar segurança operacional para uso em produção.

- trilha de auditoria de alterações financeiras
- responsável por lançamento
- responsável por baixa
- justificativa obrigatória em cancelamento e ajuste
- aprovação de pagamento em casos configuráveis
- bloqueios por perfil

### Bloco 8 - Evidências e documentos

Objetivo: reduzir operação fora do sistema.

- anexos em títulos a pagar
- anexos em títulos a receber
- comprovantes de pagamento
- comprovantes de recebimento
- observações internas por item financeiro

### Bloco 9 - Agenda e alertas

Objetivo: transformar o ERP em ferramenta de execução diária.

- agenda de vencimentos
- alerta de títulos vencendo
- alerta de títulos vencidos
- alerta de fechamento pendente
- fila de pendências financeiras

### Bloco 10 - Importações e automações simples

Objetivo: reduzir digitação manual e retrabalho.

- importação de títulos por planilha
- geração recorrente de lançamentos fixos
- criação automática de tarefa operacional a partir de fechamento
- alertas automáticos de inadimplência

## Ordem recomendada de entrega

### Fase 2A

- bloco 1 - base financeira do cliente
- bloco 2 - contas a pagar

### Fase 2B

- bloco 3 - contas a receber
- bloco 4 - tesouraria e caixa

### Fase 2C

- bloco 5 - fechamento mensal
- bloco 6 - relatórios financeiros

### Fase 2D

- bloco 7 - governança e aprovação
- bloco 8 - evidências e documentos
- bloco 9 - agenda e alertas
- bloco 10 - importações e automações simples

## MVP financeiro recomendado

O menor conjunto realmente útil para colocar clientes em operação é:

1. contas bancárias do cliente
2. fornecedores
3. categorias
4. contas a pagar
5. contas a receber
6. caixa consolidado
7. relatório simples de vencimentos

## Itens fora do escopo imediato

Não entram agora, salvo necessidade de negócio:

- integrações bancárias complexas
- CNAB
- emissão fiscal
- folha de pagamento
- multiempresa com consolidação societária avançada
- BI avançado da Fase 3

## Links relacionados

- [[financeiro/requisitos-fase-2]]
- [[financeiro/README]]
- [[sistema/arquitetura]]
- [[decisoes/decisoes-iniciais]]
