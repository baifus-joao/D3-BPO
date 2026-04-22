# Pendencias Pos-Refatoracao e Deploy

## Contexto

Esta nota registra o que ficou pendente depois da rodada de:

- reducao de consumo indevido no Neon
- refatoracao inicial do webapp
- endurecimento de configuracao e seguranca
- ajuste do deploy no Render com `preDeployCommand`

## O que foi resolvido nesta rodada

- `healthz` deixou de consultar o banco
- `readyz` ficou dedicado para checagem real de banco
- consumo indevido em idle causado por health check frequente deixou de existir no codigo
- startup saiu de `@app.on_event` e foi movido para `lifespan`
- configuracao foi centralizada em `webapp/config.py`
- bootstrap e preparacao do banco foram separados em modulos proprios
- deploy do Render foi ajustado para usar:
  - `preDeployCommand`
  - `startCommand` limpo com `uvicorn webapp.main:app`
- documentacao funcional foi movida para `docs/bpo_financeiro/`

## Pendencias abertas

### 1. Banco de producao indisponivel por cota no Neon

Status:

- bloqueando deploy no Render
- erro observado no `preDeployCommand`
- mensagem principal retornada pelo Neon:
  - `Your account or project has exceeded the compute time quota`

Impacto:

- o deploy nao conclui
- o app nao sobe em producao com a URL atual
- qualquer operacao que dependa do banco segue bloqueada

Proximas acoes:

- restaurar a disponibilidade do banco atual no Neon
- ou trocar `D3_DATABASE_URL` para outro Postgres
- ou migrar definitivamente para outro provedor de banco

### 2. Validar em producao que o consumo em idle realmente caiu

Status:

- corrigido no codigo
- ainda precisa confirmacao observando o painel do provedor de banco

Checklist:

- acompanhar compute/usage apos novo deploy
- verificar se `healthz` e o unico endpoint configurado como health check
- confirmar que nao existem jobs externos batendo em `readyz`

### 3. Finalizar quebra de rotas restantes em routers dedicados

Status:

- `auth`, `health` e `dilmaria` ja foram extraidos
- `app_modular.py` ainda concentra rotas relevantes de gestao e operacoes

Proximos cortes sugeridos:

- router de operacoes
- router de gestao
- router de financeiro interno
- router de clientes e pendencias

### 4. Otimizacao de consultas mais pesadas

Pontos mais sensiveis:

- fila operacional
- fluxo de caixa
- consultas agregadas por dashboard
- persistencia de conciliacao por cliente/periodo

### 5. Revisao de deploy apos estabilizar banco

Checklist:

- validar `preDeployCommand`
- validar bootstrap do admin
- validar login
- validar health check em `/healthz`
- validar readiness manual em `/readyz`

### 6. Possivel simplificacao futura do deploy

Futuro desejado:

- usar apenas `python -m alembic upgrade head`
- aposentar heuristica de deteccao de schema legado

Pre-condicao:

- garantir que todos os ambientes relevantes ja estejam alinhados ao Alembic

## Decisao pratica recomendada agora

Ordem de prioridade:

1. resolver o banco de producao
2. validar deploy no Render
3. confirmar queda de consumo em idle
4. continuar a quebra de `app_modular.py`
5. otimizar consultas de maior custo

## Links relacionados

- [[sistema/arquitetura]]
- [[processos/backlog-implementacao-fase-2a]]
- [[tarefas/pendencias-operacionais]]
