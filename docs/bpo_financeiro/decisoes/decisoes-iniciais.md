# Decisões Iniciais

## Diretrizes já definidas

- Não reescrever o sistema do zero.
- Não trocar a stack sem necessidade crítica.
- Evoluir de forma incremental.
- Aproveitar o máximo da base já existente.
- Priorizar baixo esforço com alto impacto nas primeiras entregas.

## Decisões de produto

- O sistema será um operacional completo de BPO financeiro.
- O produto combinará ERP financeiro e gestão de tarefas.
- A operação da D3 e a operação dos clientes devem permanecer separadas.

## Decisões de arquitetura

- Manter `FastAPI`, `SQLAlchemy` e `Alembic`.
- Preservar o domínio `d3_*` para dados internos da D3.
- Criar domínio `bpo_*` para clientes, tarefas e conciliações.
- Não reutilizar `d3_financial_transactions` para o ERP dos clientes.
- Fazer refatoração gradual, extraindo novos serviços sem grande ruptura.

## Decisões sobre roadmap

### Fase 1

- clientes
- contatos
- tarefas
- fila operacional
- conciliação vinculada a cliente/período/tarefa

### Fase 2

- ERP financeiro dos clientes
- cadastro financeiro do cliente
- contas a pagar
- contas a receber
- tesouraria e caixa
- fechamento
- relatórios financeiros
- governança e aprovações
- anexos e evidências
- agenda financeira e alertas
- importações e automações simples
- levantamento explícito dos requisitos pendentes documentado em [[financeiro/requisitos-fase-2]]
- backlog priorizado documentado em [[processos/backlog-fase-2-erp-clientes]]
- desenho técnico da Fase 2A documentado em [[financeiro/fase-2a-base-e-contas-a-pagar]]
- backlog de implementação da Fase 2A documentado em [[processos/backlog-implementacao-fase-2a]]
- Epic 1 da Fase 2A implementado com a base financeira do cliente
- Epic 2 e Epic 3 da Fase 2A implementados com serviços e tela de configurações financeiras em [[financeiro/configuracoes-financeiras]]
- Epic 4 e Epic 5 da Fase 2A implementados com modelo e serviços de contas a pagar em [[financeiro/contas-a-pagar-modelo-e-servicos]]

### Fase 3

- BI
- dashboards avançados
- automações
- alertas

## Decisões operacionais já implementadas

- O dashboard de operações passou a representar fila de trabalho.
- A conciliação agora exige cliente e período.
- O resultado da conciliação é persistido no banco.
- A tarefa vinculada pode ser concluída automaticamente pela conciliação.
- As divergências da conciliação passaram a ser tratadas como pendências operacionais com status próprio.
- O cliente agora concentra tarefas, conciliações e pendências em uma mesma visão.

## Cuidados já assumidos

- Evitar misturar log técnico com log de negócio.
- Não perder compatibilidade com o sistema em produção.
- Tratar o vault como memória oficial do projeto.

## Links relacionados

- [[sistema/visao-geral]]
- [[sistema/arquitetura]]
- [[processos/uso-codex]]
