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
   - `D3_BOOTSTRAP_ADMIN_EMAIL`
   - `D3_BOOTSTRAP_ADMIN_PASSWORD`
5. Faça o primeiro deploy.
6. Entre com o admin bootstrap e crie os demais usuarios.
7. No Cloudflare, aponte o dominio/subdominio para o host do Render e deixe o proxy habilitado.
8. Defina `SESSION_DOMAIN` com o dominio final publicado.

## Health check
O endpoint de saude para Render e monitoramento e:
```text
/healthz
```

## Arquivos de deploy
- `render.yaml`: configuracao do servico web no Render.
- `.env.example`: modelo de variaveis de ambiente para producao.
