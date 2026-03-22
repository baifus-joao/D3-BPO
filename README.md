# Painel D3

## Stack atual
- `FastAPI` para backend web.
- `SQLAlchemy` para persistencia.
- `SQLite` por padrao em desenvolvimento, com `DATABASE_URL` pronta para PostgreSQL.
- `psycopg` ja preparado para conexao com Postgres/Neon.

## Principais modulos
- `conciliador/core/parsers.py`: leitura e normalizacao dos relatorios Excel.
- `conciliador/core/aggregations.py`: regras de conciliacao.
- `conciliador/core/writer.py`: escrita do Excel final.
- `conciliador/service.py`: orquestracao da conciliacao.
- `webapp/db.py`: engine e sessao do banco.
- `webapp/models.py`: tabelas de usuarios e historico.
- `webapp/security.py`: hash e verificacao de senha.
- `webapp/main.py`: autenticacao, painel, admin e fluxo web.

## Instalar dependencias
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Executar localmente
```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Abra `http://127.0.0.1:8000`.

## Migrações de banco com Alembic
Aplicar as migrations existentes:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Gerar uma nova migration depois de mudar os modelos:

```powershell
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "descricao da mudanca"
```

## Usuario admin inicial
Na primeira inicializacao, se nao existir nenhum admin, o sistema cria um automaticamente.

Variaveis opcionais:
```powershell
$env:D3_BOOTSTRAP_ADMIN_NAME="Administrador D3"
$env:D3_BOOTSTRAP_ADMIN_EMAIL="admin@d3financeiro.local"
$env:D3_BOOTSTRAP_ADMIN_PASSWORD="Admin123!"
```

## Banco de dados
Localmente, sem `DATABASE_URL`, o sistema usa `app.db`.

Para PostgreSQL no futuro:
```powershell
$env:DATABASE_URL="postgresql://usuario:senha@host:5432/database"
```

O app converte automaticamente `postgres://` e `postgresql://` para o driver `psycopg`.

## Inferencia de layout com IA
O parser continua tentando primeiro o layout conhecido.

Se o cabecalho nao for encontrado ou o layout fugir do padrao esperado, o sistema pode usar a OpenAI para:
- inferir o tipo do relatorio
- identificar a linha de cabecalho
- mapear colunas para o schema canonico de `vendas` ou `recebimentos`

Variaveis:
```powershell
$env:OPENAI_API_KEY="sua-chave"
$env:OPENAI_LAYOUT_MODEL="gpt-4.1-mini"
```

Sem `OPENAI_API_KEY`, o fallback por IA fica desativado e o sistema usa apenas o parser classico.

## Rodar localhost com IA habilitada
```powershell
$env:OPENAI_API_KEY="sua-chave"
$env:D3_BOOTSTRAP_ADMIN_EMAIL="admin@d3financeiro.local"
$env:D3_BOOTSTRAP_ADMIN_PASSWORD="Admin123!"
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

## Usuarios e perfis
- `admin`: cria usuarios, altera dados, ativa/desativa conta e redefine senhas.
- `colaborador`: usa o painel e executa conciliacoes.

Os usuarios sao criados apenas por um `admin`.

## Deploy com Neon + Render + Cloudflare
1. Crie um banco no Neon.
2. Copie a connection string do Postgres com `sslmode=require`.
3. No Render, crie o servico web a partir deste repositorio ou use `render.yaml`.
4. Configure no Render:
   - `DATABASE_URL`
   - `SESSION_SECRET`
   - `SESSION_HTTPS_ONLY=true`
   - `SESSION_SAME_SITE=lax`
   - `SESSION_MAX_AGE_SECONDS=28800`
   - `LOGIN_MAX_ATTEMPTS=5`
   - `LOGIN_WINDOW_SECONDS=900`
   - `LOGIN_LOCK_SECONDS=600`
   - `DOWNLOAD_TTL_SECONDS=3600`
   - `D3_BOOTSTRAP_ADMIN_EMAIL`
   - `D3_BOOTSTRAP_ADMIN_PASSWORD`
   - `OPENAI_API_KEY` se quiser inferencia de layout por IA em producao
5. Se voce for usar apenas a URL `*.onrender.com`, deixe `SESSION_DOMAIN` vazio.
6. O `startCommand` do Render executa `scripts/render_start.py`, que:
   - aplica `alembic stamp head` se o banco ja tiver as tabelas antigas sem controle do Alembic
   - executa `alembic upgrade head`
   - sobe o `uvicorn`
7. Faça o primeiro deploy.
8. Entre com o admin bootstrap e crie os demais usuarios.
9. Se no futuro publicar dominio proprio, defina `SESSION_DOMAIN` com o dominio final.

## Health check
O endpoint de saude para Render e monitoramento e:
```text
/healthz
```

## Arquivos de deploy
- `render.yaml`: configuracao do servico web no Render.
- `.env.example`: modelo de variaveis de ambiente para producao.
