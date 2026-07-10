# Paid Traffic Dashboard

Aplicacao web local em Python para consolidar relatorios de Google Ads e Meta Ads em um dashboard unico, com historico em SQLite e exportacao em PDF/Excel.

## O que ja esta implementado

- Backend FastAPI com rotas de autenticacao, sincronizacao, historico e exportacao.
- Frontend local servido pelo proprio FastAPI.
- Banco SQLite local em `data/traffic_reports.sqlite3`.
- Interface comum de conectores em `app/connectors/base.py`.
- Conector Google Ads em `app/connectors/google_ads.py`.
- Conector Meta Ads em `app/connectors/meta_ads.py`.
- Exportacao `.pdf` e `.xlsx`.
- Configuracao por `.env`, sem credenciais hardcoded.
- Tokens OAuth criptografados em repouso com Fernet, usando chave derivada de `APP_SECRET_KEY`.
- Retry com backoff para erros temporarios de rede, HTTP 429 e HTTP 5xx.
- Mensagens de erro legiveis para falhas comuns de API, permissao, token, developer token e rate limit.
- Sincronizacao automatica diaria opcional com APScheduler.
- Status da ultima sincronizacao visivel na interface.
- Logs locais em `data/app.log`.
- Testes automatizados com pytest.

## Estrutura

```text
paid-traffic-dashboard/
  app/
    connectors/
      base.py
      google_ads.py
      meta_ads.py
      registry.py
    routers/
      api.py
      auth.py
    services/
      date_ranges.py
      history.py
      metrics.py
      scheduler.py
      sync.py
      tokens.py
    static/
      app.js
      styles.css
    templates/
      index.html
    config.py
    db.py
    exporters.py
    main.py
    models.py
    schemas.py
  data/
  tests/
  .env.example
  DEPLOY_ONLINE.md
  Dockerfile
  render.yaml
  requirements.txt
```

## Como rodar localmente

Pre-requisito: Python 3.11 ou superior instalado e disponivel no terminal como `python` ou `py`. No Windows, se aparecer a mensagem da Microsoft Store ao rodar `python --version`, instale o Python em [python.org](https://www.python.org/downloads/windows/) e marque a opcao `Add python.exe to PATH`.

No PowerShell, dentro da pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Depois abra:

```text
http://127.0.0.1:8000
```

## Seguranca

`APP_SECRET_KEY` pode ficar vazio no ambiente local. Nesse caso, o app gera uma chave forte em:

```text
data/.app_secret_key
```

Em producao, defina `APP_SECRET_KEY` como uma chave aleatoria estavel nas variaveis de ambiente. Nao troque essa chave depois de salvar tokens, porque ela e usada para descriptografar `access_token` e `refresh_token`.

Os tokens salvos no SQLite recebem prefixo `fernet:` e ficam criptografados em repouso.

## Sincronizacao automatica

Configure no `.env`:

```env
AUTO_SYNC_ENABLED="true"
AUTO_SYNC_TIME="03:00"
AUTO_SYNC_PERIOD_DAYS="1"
AUTO_SYNC_PLATFORMS="google,meta"
```

O horario e interpretado em UTC. A ultima execucao fica registrada em:

```text
data/sync_status.json
```

E tambem aparece na sidebar do dashboard.

## Logs

O app grava logs estruturados em:

```text
data/app.log
```

Sincronizacoes bem-sucedidas entram como `INFO`; falhas de API entram como `ERROR`.

## Testes

Depois de instalar dependencias:

```powershell
pytest
```

Os testes cobrem:

- periodos em `date_ranges.py`
- persistencia/agregacao em `history.py`
- calculo de CTR, CPC, custo por conversao e ROAS
- endpoints principais de leitura/exportacao usando SQLite em memoria, sem chamar Google/Meta

## Como publicar online

Este pacote ja inclui:

- `Dockerfile`
- `.dockerignore`
- `render.yaml`
- `DEPLOY_ONLINE.md`

O caminho recomendado para a primeira publicacao e Render, porque ele aceita backend Python/FastAPI, variaveis de ambiente e disco persistente para SQLite.

Leia:

```text
DEPLOY_ONLINE.md
```

Resumo: publique o projeto em um repositorio GitHub, crie um Blueprint no Render usando `render.yaml`, configure `BASE_URL`, `TRUSTED_HOSTS` e as chaves Google/Meta, depois cadastre os redirects OAuth usando o dominio publicado.

Se o PowerShell bloquear o script de ativacao, use:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Configuracao do Google Ads

Referencia oficial usada: [OAuth 2.0 no Google Ads API](https://developers.google.com/google-ads/api/docs/oauth/overview) e [release notes da Google Ads API](https://developers.google.com/google-ads/api/docs/release-notes).

Em 10/07/2026, a versao default configurada aqui e `v24`. Se a Google mudar a versao suportada, altere `GOOGLE_ADS_API_VERSION` no `.env`.

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie ou selecione um projeto.
3. Ative a Google Ads API no projeto.
4. Configure a tela de consentimento OAuth.
5. Crie uma credencial OAuth do tipo Web application.
6. Adicione este redirect URI autorizado:

```text
http://127.0.0.1:8000/auth/google/callback
```

7. Copie `Client ID` e `Client secret` para o `.env`:

```env
GOOGLE_ADS_CLIENT_ID="..."
GOOGLE_ADS_CLIENT_SECRET="..."
```

8. No Google Ads, acesse as configuracoes de API e solicite/copiei o Developer Token:

```env
GOOGLE_ADS_DEVELOPER_TOKEN="..."
```

9. Se voce usa uma conta MCC/manager, informe o customer id da manager sem hifens:

```env
GOOGLE_ADS_LOGIN_CUSTOMER_ID="1234567890"
```

10. Rode o app e clique em `Google Ads` no topo para concluir o OAuth. O app pede o escopo:

```text
https://www.googleapis.com/auth/adwords
```

Opcional: se voce ja tiver um refresh token, pode preencher diretamente:

```env
GOOGLE_ADS_REFRESH_TOKEN="..."
```

Opcional: para evitar a busca automatica de contas acessiveis, informe IDs especificos:

```env
GOOGLE_ADS_CUSTOMER_IDS="1234567890,9876543210"
```

## Configuracao do Meta Ads

Referencias oficiais usadas: [Access Tokens - Meta for Developers](https://developers.facebook.com/documentation/facebook-login/guides/access-tokens), [Graph API Get Started](https://developers.facebook.com/docs/graph-api/get-started/) e [Marketing API changelog](https://developers.facebook.com/documentation/ads-commerce/marketing-api/marketing-api-changelog).

Em 10/07/2026, a versao default configurada aqui e `v25.0`. Se a Meta mudar a versao suportada, altere `META_GRAPH_API_VERSION` no `.env`.

1. Acesse [Meta for Developers](https://developers.facebook.com/).
2. Crie um app ou selecione um app existente.
3. Adicione/configure Facebook Login para OAuth.
4. Adicione este redirect URI valido:

```text
http://127.0.0.1:8000/auth/meta/callback
```

5. Copie App ID e App Secret para o `.env`:

```env
META_APP_ID="..."
META_APP_SECRET="..."
```

6. Garanta que seu usuario tenha acesso ao Business Manager e as contas de anuncio.
7. Para leitura de relatorios, o app usa os escopos:

```text
ads_read,business_management
```

8. Rode o app e clique em `Meta Ads` no topo para concluir o OAuth.

Opcional: se voce ja tiver um token valido, pode preencher diretamente:

```env
META_ACCESS_TOKEN="..."
```

Opcional: para restringir contas:

```env
META_AD_ACCOUNT_IDS="act_1234567890,act_9876543210"
```

Observacao: em apps fora do modo desenvolvimento ou para usuarios que nao sao admins/testers do app, a Meta pode exigir App Review para permissoes como `ads_read`.

## Metricas consolidadas

O app grava uma linha por plataforma, conta, campanha e dia com:

- impressoes
- cliques
- CTR
- CPC
- investimento
- conversoes
- custo por conversao
- valor de conversao
- ROAS

Google Ads usa GAQL via endpoint `googleAds:searchStream`. Meta Ads usa o endpoint `/{ad_account_id}/insights` em nivel de campanha.

## Fluxo de uso

1. Preencha `.env`.
2. Inicie o servidor.
3. Clique em cada plataforma no topo para autenticar.
4. Clique em `Atualizar contas`.
5. Selecione periodo, conta/campanha se quiser.
6. Clique em `Sincronizar dados`.
7. Use `PDF` ou `Excel` para exportar o periodo filtrado.

O PDF inclui resumo executivo no topo com periodo, investimento total, conversoes totais e ROAS medio, seguido por resumo por plataforma e detalhamento por campanha.

## Como conectar contas dos seus clientes

Este MVP foi desenhado para uso pessoal/local. Ele salva um token OAuth por plataforma (`google` e `meta`) no SQLite local. Na pratica, o melhor fluxo para atender varios clientes e centralizar os acessos em contas gerenciadoras suas:

### Google Ads

Fluxo recomendado:

1. Crie ou use uma conta manager/MCC do Google Ads.
2. Peça para cada cliente vincular a conta Google Ads dele a sua MCC.
3. No `.env`, configure `GOOGLE_ADS_LOGIN_CUSTOMER_ID` com o ID da sua MCC.
4. Autentique no dashboard com o Google que tem acesso a essa MCC.
5. Clique em `Atualizar contas`.
6. As contas vinculadas aparecem no filtro `Conta`.
7. Selecione a conta/campanha do cliente, sincronize e exporte o relatorio.

Alternativa: se voce nao usar MCC, pode preencher `GOOGLE_ADS_CUSTOMER_IDS` com IDs especificos de contas as quais seu usuario Google ja tem acesso.

### Meta Ads

Fluxo recomendado:

1. Peça para o cliente adicionar seu usuario ao Business Manager dele.
2. O cliente precisa liberar acesso a conta de anuncios.
3. Autentique no dashboard com seu usuario Meta.
4. Clique em `Atualizar contas`.
5. As contas de anuncios acessiveis aparecem no filtro `Conta`.
6. Selecione a conta/campanha do cliente, sincronize e exporte o relatorio.

Alternativa: preencha `META_AD_ACCOUNT_IDS` com IDs especificos, como `act_1234567890`.

### Observacao importante

Se voce quiser que cada cliente entre em uma tela e conecte a propria conta separadamente, o proximo passo tecnico e adicionar suporte multi-cliente: tabela de clientes, tokens OAuth por cliente/plataforma, permissao por conta e uma tela de onboarding. O nucleo de conectores ja foi separado para facilitar essa evolucao.

## Como adicionar outro conector depois

1. Crie um arquivo em `app/connectors/`, por exemplo `tiktok_ads.py`.
2. Implemente a classe herdando `AdsConnector`.
3. Retorne objetos `ConnectorAccount`, `ConnectorCampaign` e `ConnectorMetric`.
4. Registre a classe em `app/connectors/registry.py`.

O nucleo de banco, dashboard e exportacao nao precisa mudar se o novo conector respeitar a interface comum.
