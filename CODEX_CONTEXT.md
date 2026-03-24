# Codex Context

## Projeto
- Nome: `VpsToolsPy`
- Tipo: toolkit operacional para VPS Linux com interface de terminal em Python.
- Objetivo: instalar, configurar, publicar, monitorar e recuperar serviços de uma VPS, com foco em banco de dados, backend, Nginx/HTTPS e DR.

## Stack principal
- Backend do toolkit: Python
- UI principal original: terminal interativo
- Painel web novo: Spring Boot + React
- Publicacao web: Nginx
- Banco mais usado nos fluxos atuais: PostgreSQL

## O que o projeto faz hoje
- Gerencia servicos de VPS
- Gerencia usuarios SSH
- Prepara bancos:
  - PostgreSQL
  - MySQL
  - MariaDB
  - MongoDB
  - Redis
- Prepara backend Spring Boot
- Configura Nginx e Certbot
- Instala painel web de bancos
- Possui modulo de recuperacao / DR:
  - RPO/RTO
  - backup logico
  - checksum
  - retencao
  - criptografia
  - copia secundaria
  - offsite via `scp`
  - restore test automatico
  - export de configs
  - monitoramento e alertas
  - runbooks
  - exercicios

## Arquivos mais importantes
- Menu principal: [vps_tools/main.py](C:/Users/rodne/PycharmProjects/Generico/vps_tools/main.py)
- Acoes de sistema: [vps_tools/core/system.py](C:/Users/rodne/PycharmProjects/Generico/vps_tools/core/system.py)
- Ponte Python do painel web: [vps_tools/panel_bridge.py](C:/Users/rodne/PycharmProjects/Generico/vps_tools/panel_bridge.py)
- Template do painel administrativo:
  - [frontend/src/App.jsx](C:/Users/rodne/PycharmProjects/Generico/vps_tools/panel_templates/admin_web_panel/frontend/src/App.jsx)
  - [frontend/src/styles.css](C:/Users/rodne/PycharmProjects/Generico/vps_tools/panel_templates/admin_web_panel/frontend/src/styles.css)
  - [frontend/vite.config.js](C:/Users/rodne/PycharmProjects/Generico/vps_tools/panel_templates/admin_web_panel/frontend/vite.config.js)
  - [backend/pom.xml](C:/Users/rodne/PycharmProjects/Generico/vps_tools/panel_templates/admin_web_panel/backend/pom.xml)

## Internacionalizacao
- Base de strings: [vps_tools/i18n/strings.json](C:/Users/rodne/PycharmProjects/Generico/vps_tools/i18n/strings.json)
- Loader: [vps_tools/core/i18n.py](C:/Users/rodne/PycharmProjects/Generico/vps_tools/core/i18n.py)
- O projeto foi migrado para suportar multiplos idiomas via arquivo externo.

## Painel administrativo web
- Existe como opcao de instalacao no menu inicial.
- Roda localmente no servidor e pode ser publicado via Nginx.
- Usa login proprio da aplicacao.
- Foi criado para expor visualmente o que antes existia apenas no terminal.

### Estado atual do painel
- Ja instalado e funcional no servidor principal.
- Publicado em subcaminho:
  - painel de bancos: `/`
  - painel administrativo: `/admin/`
- O frontend usa assets relativos; isso e importante para funcionar em subpath.

### Arquitetura do painel
- React renderiza:
  - dashboard
  - automacoes
  - tarefas
  - metadados
- Spring Boot expoe:
  - autenticacao
  - overview
  - lista de acoes
  - fila de tarefas
  - stream de progresso
- O backend chama o script Python via `panel_bridge.py`.

## Regra operacional importante do usuario
- Sempre que mexer no painel web, tambem atualizar o painel instalado no servidor.
- Nao parar no codigo local; rebuildar e validar no servidor quando a alteracao afetar a interface.

## Servidor principal de validacao
- Host: `api.dinvendas.com`
- Usuario SSH: `ubuntu`
- Repositorio remoto: `/root/VpsToolsPy`
- App do painel administrativo: `/opt/vps-tools-admin-panel`
- Publicacao:
  - DB panel: `http://54.94.104.70/`
  - Admin panel: `http://54.94.104.70/admin/`

## Fluxo que funcionou para atualizar o painel no servidor
1. Enviar arquivos com `sftp` para `/home/ubuntu/vps-tools-upload/`
2. Copiar com `sudo` para:
   - `/root/VpsToolsPy/...`
   - `/opt/vps-tools-admin-panel/source/...`
3. Rebuildar com Python remoto usando o venv do repositorio:
   - `PYTHONPATH=/root/VpsToolsPy /root/VpsToolsPy/venv/bin/python /home/ubuntu/vps-tools-upload/rebuild_admin_panel.py`
4. Validar `http://54.94.104.70/admin/`

## Armadilhas ja descobertas
- Root SSH direto nao funciona; usar `ubuntu` + `sudo`.
- `scp` foi instavel em alguns momentos; `sftp -b` funcionou melhor.
- Para o painel sob `/admin/`, o frontend precisa usar assets relativos.
- O `vite.config.js` do painel administrativo precisa manter:
  - `base: "./"`
- Em alguns casos o rebuild incremental nao refletiu o CSS novo.
  - Solucao que funcionou:
    - sobrescrever explicitamente os arquivos em `/opt/vps-tools-admin-panel/source`
    - remover `frontend/dist` e `backend/target`
    - rebuildar limpo
- Se o usuario disser que nao viu mudancas, verificar o bundle realmente servido em `/admin/assets/...`, nao so o codigo local.

## Docker / painel de bancos
- Houve problema real com Docker alterando rede e derrubando acesso.
- O instalador foi endurecido.
- Para o painel de bancos, o Docker precisa respeitar:
  - `ip-forward-no-drop`
- Se houver novo problema de rede, revisar com cuidado a parte de Docker no `system.py`.

## Visual / referencia aprovada pelo usuario
- O usuario quer o painel administrativo com a "pegada" visual do projeto:
  - `C:\Users\rodne\Desktop\Sistema Hospitalar`
- Direcao visual desejada:
  - fundo claro
  - topo limpo
  - sidebar profissional
  - cards brancos
  - linguagem de dashboard hospitalar/operacional
  - menos efeito glassmorphism

## Arquivos de referencia visual externos
- [frontend/src/layout/AppShell.tsx](C:/Users/rodne/Desktop/Sistema%20Hospitalar/frontend/src/layout/AppShell.tsx)
- [frontend/src/theme.ts](C:/Users/rodne/Desktop/Sistema%20Hospitalar/frontend/src/theme.ts)
- [frontend/src/pages/admin/AdminDashboardPage.tsx](C:/Users/rodne/Desktop/Sistema%20Hospitalar/frontend/src/pages/admin/AdminDashboardPage.tsx)

## Seguranca / cuidado
- Existe uma chave local:
  - [vps_tools/chaves-hospital-dev.pem](C:/Users/rodne/PycharmProjects/Generico/vps_tools/chaves-hospital-dev.pem)
- Nao commitar essa chave.
- Nao colocar segredos sensiveis em commits.

## Ultimos pontos relevantes ja concluidos
- i18n externo via arquivo de strings
- modulo DR ampliado
- painel web de bancos com publicacao
- painel administrativo web com instalacao via menu
- painel administrativo publicado em `/admin/`
- estilo visual do painel foi retrabalhado para ficar mais proximo do projeto Celiora/Sistema Hospitalar

## Quando abrir uma nova sessao Codex
- Ler este arquivo primeiro.
- Depois abrir, nesta ordem:
  1. [vps_tools/main.py](C:/Users/rodne/PycharmProjects/Generico/vps_tools/main.py)
  2. [vps_tools/core/system.py](C:/Users/rodne/PycharmProjects/Generico/vps_tools/core/system.py)
  3. [vps_tools/panel_templates/admin_web_panel/frontend/src/App.jsx](C:/Users/rodne/PycharmProjects/Generico/vps_tools/panel_templates/admin_web_panel/frontend/src/App.jsx)
  4. [vps_tools/panel_templates/admin_web_panel/frontend/src/styles.css](C:/Users/rodne/PycharmProjects/Generico/vps_tools/panel_templates/admin_web_panel/frontend/src/styles.css)

## Ultima intencao do usuario
- Continuar evoluindo o painel administrativo web.
- Deixar o visual mais proximo do Celiora/Sistema Hospitalar.
- Sempre aplicar as mudancas tambem no servidor, nao apenas localmente.
