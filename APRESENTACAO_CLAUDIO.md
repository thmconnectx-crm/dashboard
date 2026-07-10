# Paid Traffic Dashboard

MVP de dashboard para consolidar relatorios de trafego pago em Google Ads e Meta Ads.

## O que o projeto faz

- Conecta com Google Ads e Meta Ads via OAuth/API.
- Puxa metricas por campanha.
- Consolida dados em um dashboard unico.
- Salva historico local em SQLite.
- Exporta relatorios em PDF e Excel.
- Usa conectores separados para facilitar TikTok Ads, LinkedIn Ads etc no futuro.
- Criptografa tokens OAuth em repouso.
- Pode sincronizar automaticamente 1x por dia.
- Registra logs locais para depuracao.

## Status atual

Este pacote contem a base funcional do MVP em FastAPI, com interface web, conectores, banco local e documentacao.

Tambem inclui `preview-server.js`, uma previa visual com dados demonstrativos para avaliar a interface sem depender das credenciais reais.

Na ultima rodada, foram adicionados retries de API, mensagens de erro legiveis, criptografia de tokens, agendamento automatico, status da ultima sincronizacao, testes automatizados e PDF com resumo executivo.

## Proximo passo sugerido

Publicar online em um ambiente com backend Python, banco persistente e variaveis de ambiente seguras. Depois disso, configurar os redirects OAuth oficiais do Google e da Meta apontando para o dominio publicado.

O pacote ja vem com `Dockerfile`, `render.yaml` e `DEPLOY_ONLINE.md` para facilitar a publicacao em Render ou outra plataforma que rode Docker.
