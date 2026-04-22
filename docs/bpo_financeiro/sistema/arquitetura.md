# Arquitetura

## Princípio arquitetural

Evolução incremental do sistema existente, preservando a stack atual e separando claramente:

- domínio interno da D3
- domínio operacional do BPO

## Stack atual

- backend web em `FastAPI`
- persistência em `SQLAlchemy`
- migrations com `Alembic`
- banco local em `SQLite`
- caminho futuro compatível com `PostgreSQL`
- interface server-rendered com templates Jinja

## Estrutura lógica atual

### Núcleo legado

- parser e normalização de relatórios Excel
- agregações e regras de conciliação
- geração de planilha final
- histórico técnico de execuções

### Webapp legado

- autenticação
- sessão e permissões
- dashboards
- fluxo de caixa interno
- cadastros internos
- relatórios internos e operacionais

### Domínio BPO introduzido

- clientes
- contatos do cliente
- templates de tarefa
- tarefas operacionais
- eventos de tarefa
- conciliações por cliente/período
- itens de divergência da conciliação
- pendências operacionais derivadas da conciliação

## Separação de domínios

### Domínio `d3_*`

Usado para a operação interna da própria D3:

- usuários
- execução técnica
- fluxo de caixa interno
- contas, categorias, lojas e formas de pagamento internas

### Domínio `bpo_*`

Usado para a operação entregue aos clientes:

- carteira de clientes
- fila operacional
- tarefas
- conciliações persistidas

## Módulos funcionais discutidos

- financeiro
- tarefas
- dashboard
- conciliação
- automações
- relatórios

## Roadmap arquitetural

### Fase 1

- clientes
- tarefas
- fila operacional
- conciliação vinculada ao cliente
- pendências operacionais com status

### Fase 2

Entrada do ERP financeiro completo dos clientes:

- contas a pagar
- contas a receber
- caixa e contas bancárias por cliente
- fechamento mensal
- relatórios financeiros por cliente

### Fase 3

- dashboards avançados
- indicadores operacionais
- automações
- alertas e inteligência operacional

## Diretriz de implementação

- manter o legado funcionando
- adicionar novos módulos em serviços separados
- evitar concentrar novas regras em um único arquivo
- expandir o sistema sem misturar financeiro da D3 com financeiro dos clientes

## Evolução arquitetural recente

- `healthz` passou a ser leve e sem consulta ao banco
- `readyz` ficou reservado para verificação real de banco
- startup foi movido para `lifespan`
- configuração foi centralizada em `webapp/config.py`
- bootstrap foi movido para `webapp/bootstrap.py`
- logging foi isolado em `webapp/logging_utils.py`
- autenticação, health e DilmarIA já usam routers dedicados

## Pendências arquiteturais abertas

- continuar a extração das rotas restantes de `app_modular.py`
- reduzir concentração de queries pesadas nas telas principais
- validar arquitetura de deploy com banco definitivo de produção
- após estabilização, simplificar fluxo de migration no deploy

## Links relacionados

- [[sistema/visao-geral]]
- [[decisoes/decisoes-iniciais]]
- [[financeiro/README]]
- [[tarefas/README]]
- [[processos/pendencias-pos-refatoracao-e-deploy]]
