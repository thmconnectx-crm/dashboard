# Deploy online

Este projeto e um backend FastAPI com frontend servido pelo proprio app. Para funcionar online com OAuth do Google e da Meta, ele precisa rodar em uma hospedagem que aceite Python/backend, variaveis de ambiente e disco persistente.

## Caminho recomendado: Render

1. Suba este projeto para um repositorio GitHub privado ou publico.
2. Acesse Render e crie um novo `Blueprint`.
3. Aponte para o repositorio que contem `render.yaml`.
4. Depois que o servico for criado, configure as variaveis marcadas como `sync: false`.

Variaveis principais:

```env
BASE_URL="https://seu-app.onrender.com"
TRUSTED_HOSTS="seu-app.onrender.com"
GOOGLE_ADS_CLIENT_ID="..."
GOOGLE_ADS_CLIENT_SECRET="..."
GOOGLE_ADS_DEVELOPER_TOKEN="..."
GOOGLE_ADS_LOGIN_CUSTOMER_ID="..."
META_APP_ID="..."
META_APP_SECRET="..."
APP_SECRET_KEY="uma-chave-forte-e-estavel"
AUTO_SYNC_ENABLED="true"
AUTO_SYNC_TIME="03:00"
```

Se quiser restringir contas:

```env
GOOGLE_ADS_CUSTOMER_IDS="1234567890,9876543210"
META_AD_ACCOUNT_IDS="act_1234567890,act_9876543210"
```

## Redirects OAuth em producao

Depois de publicar, configure estes redirects nas plataformas:

Google Cloud Console:

```text
https://seu-app.onrender.com/auth/google/callback
```

Meta Developers:

```text
https://seu-app.onrender.com/auth/meta/callback
```

O valor precisa bater exatamente com `BASE_URL`.

## Sincronizacao automatica em producao

O `render.yaml` ja inclui as variaveis:

```env
AUTO_SYNC_ENABLED
AUTO_SYNC_TIME
AUTO_SYNC_PERIOD_DAYS
AUTO_SYNC_PLATFORMS
```

Ative `AUTO_SYNC_ENABLED=true` quando as credenciais Google/Meta ja estiverem configuradas. O horario usa UTC.

## Logs em producao

Os logs da aplicacao ficam em:

```text
/app/data/app.log
```

Como o Render usa disco persistente em `/app/data`, o historico do SQLite, status da ultima sincronizacao e logs sobrevivem a redeploys.

## Teste depois do deploy

1. Abra `https://seu-app.onrender.com/health`.
2. Deve responder:

```json
{"status":"ok"}
```

3. Abra o dashboard.
4. Clique em `Google Ads` no topo e autorize.
5. Clique em `Meta Ads` no topo e autorize.
6. Clique em `Atualizar contas`.
7. Selecione conta/campanha e clique em `Sincronizar dados`.
8. Teste `PDF` e `Excel`.

## Observacao sobre SQLite online

O `render.yaml` cria um disco persistente em `/app/data`, e o banco fica em:

```text
/app/data/traffic_reports.sqlite3
```

Para uso pessoal ou MVP, isso e suficiente. Para uso com muitos usuarios/clientes, o ideal depois e migrar para Postgres.

## Rodar via Docker localmente

```powershell
docker build -t paid-traffic-dashboard .
docker run --rm -p 8000:8000 --env-file .env paid-traffic-dashboard
```

Abra:

```text
http://127.0.0.1:8000
```
