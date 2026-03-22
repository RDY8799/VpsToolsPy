# VpsToolsPy

Suite de gerenciamento de VPS em Python para automacao de servicos, usuarios e ferramentas operacionais.

## Recursos

- Instalador e gerenciador de servicos:
  - Squid
  - SSLH
  - Stunnel
  - Dropbear
  - OpenVPN (com gerenciamento de clientes)
  - ShadowSocks
  - Xray (VLESS, VMESS, Trojan)
  - Hysteria
  - DNSTT
  - BadVPN
  - Trojan
  - OpenClaw (instalacao oficial + gerenciamento dedicado)
  - VNC (instalacao e gerenciamento completo)
- Gerenciamento de usuarios SSH
- Backup/restore de usuarios
- Power Tools:
  - Port changer
  - Dashboard de status
  - Logs viewer
  - Backup/restore de configuracoes
  - Firewall manager
  - Health check
  - Rollback de configuracao
  - Setup wizard
  - Idioma PT/EN
- Ferramentas do sistema:
  - Atualizacao do sistema
  - Criacao de swap
  - Teste de velocidade
  - Criacao de comando global (ex: `menu`)
  - Desinstalacao completa
- Banco de Dados / Backend:
  - painel compacto com status `ATIVO/INATIVO` de PostgreSQL, MySQL, MariaDB, MongoDB, Redis, Nginx e Certbot
  - PostgreSQL local com criacao de banco/usuario, bind configuravel e JDBC configuravel
  - MySQL com criacao de banco/usuario
  - MariaDB com criacao de banco/usuario
  - MongoDB com repositório oficial, usuario da aplicacao e auth opcional
  - Redis para cache, sessoes, filas leves e dados temporarios, com bind/porta/senha configuraveis
  - preparo de backend Spring Boot na EC2
  - criacao e gerenciamento de servico `systemd`
  - Nginx reverse proxy configuravel
  - HTTPS com Certbot
  - painel web opcional de bancos com Docker + Adminer + pgAdmin 4 + Redis Insight
- Internacionalizacao:
  - strings externas em `vps_tools/i18n/strings.json`
  - menu de idioma detecta automaticamente os codigos presentes no arquivo
  - suporte atual a PT/EN com base pronta para adicionar muitas linguas

## Requisitos

- Linux (Debian/Ubuntu/CentOS/RHEL)
- Acesso root
- Python 3.10+
- Git

## Instalacao (Debian/Ubuntu)

```bash
sudo -i
apt update -y
apt install -y git python3 python3-venv python3-pip
git clone https://github.com/RDY8799/VpsToolsPy.git
cd VpsToolsPy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m vps_tools.main
```

## Instalacao (CentOS/RHEL)

```bash
sudo -i
yum install -y git python3 python3-pip
git clone https://github.com/RDY8799/VpsToolsPy.git
cd VpsToolsPy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m vps_tools.main
```

## Modulo OpenClaw (destaque)

O OpenClaw foi integrado como modulo oficial no menu de servicos e em Ferramentas.

- Instalacao usa o comando oficial do projeto:

```bash
curl -fsSL https://openclaw.ai/install.sh | bash
```

- No app, o modulo OpenClaw oferece:
  - instalar
  - iniciar/parar
  - reiniciar
  - atualizar
  - visualizar logs
  - desinstalar
  - status em tempo real: `INSTALADO/NAO INSTALADO` e `ATIVO/INATIVO`

Referencias:
- Site: `https://openclaw.ai/`
- Instalador: `https://openclaw.ai/install.sh`

## Modulo VNC

Modulo dedicado para VNC com:

- instalar com porta personalizada
- senha manual ou automatica
- iniciar/parar/reiniciar
- alterar porta (com validacao de conflito)
- alterar senha
- logs
- desinstalacao
- status `INSTALADO/NAO INSTALADO`

## Uso rapido

1. Execute `python -m vps_tools.main`
2. Menu principal:
   - `01` Instalador/configuracao de servicos
   - `02` Gerenciamento de usuarios
   - `03` Ferramentas do sistema
   - `04` Banco de Dados / Backend
3. Todos os menus aceitam `1` e `01` (ou equivalente)
4. Acoes obvias aceitam `Enter` como confirmacao padrao; acoes destrutivas continuam pedindo confirmacao explicita
5. Selecao de usuario suporta setas + Enter ou digitacao manual

## Tutorial de uso (PT-BR)

### 1. Abrir o painel

No servidor, entre na pasta do projeto e execute:

```bash
cd ~/VpsToolsPy
source .venv/bin/activate
python -m vps_tools.main
```

Se voce ja criou o comando global, basta usar:

```bash
menu
```

### 2. Entender o menu principal

- `01` Instalador/configuracao de servicos: instala e gerencia proxy, VPN e tunel
- `02` Gerenciamento de usuarios: cria, remove e ajusta usuarios SSH
- `03` Ferramentas do sistema: swap, atualizacao, velocidade, comando global e utilitarios
- `04` Banco de Dados / Backend: PostgreSQL, MySQL, MariaDB, MongoDB, Redis, Spring Boot, systemd, Nginx e HTTPS

### 3. Instalar um servico

Exemplo com Squid:

1. Entre em `01`
2. Escolha `SQUID`
3. Selecione `INSTALAR`
4. Informe a porta desejada
5. Confirme com `Enter` quando a confirmacao ja vier com `S/n`

Depois da instalacao, volte ao mesmo menu do servico para:

- iniciar
- parar
- reiniciar
- desinstalar

### 4. Criar e gerenciar usuarios SSH

1. Entre em `02`
2. Escolha `NOVO USUARIO`
3. Informe:
   - nome do usuario
   - senha
   - limite de conexoes
   - data ou dias para expiracao

No mesmo menu voce tambem pode:

- apagar usuario
- alterar limite
- alterar expiracao
- alterar senha
- desconectar usuario
- gerar backup
- restaurar backup

### 5. Preparar banco de dados e backend

Fluxo recomendado para backend Java/Spring Boot:

1. Entre em `04`
2. Execute `CRIAR BANCO POSTGRESQL LOCAL`
3. Informe nome do banco, usuario, senha, bind e porta JDBC
4. Depois execute `PREPARAR BACKEND SPRING BOOT`
5. Informe pasta da app, porta, variaveis do backend e, se quiser, URL do repositorio
6. Revise os comandos gerados para subir o `.jar` ou clonar/buildar o projeto

O painel desse menu mostra de forma compacta se `PostgreSQL`, `MySQL`, `MariaDB`, `MongoDB`, `Redis`, `Nginx` e `Certbot` estao ativos ou nao.

### 6. Publicar com Nginx e HTTPS

Ordem recomendada:

1. Deixe o backend respondendo localmente em `127.0.0.1` na porta da aplicacao
2. No menu `04`, configure `NGINX REVERSE PROXY`
3. Aponte seu dominio para o IP da VPS
4. Abra `80` e `443` no firewall/Security Group
5. No menu `04`, execute `HTTPS COM CERTBOT`

Boas praticas:

- nao abra `5432` publicamente
- mantenha o banco local quando possivel
- so publique `80/443` depois que o backend estiver funcionando

### 6.1 Painel web de bancos

Se quiser uma interface web para administrar os bancos:

1. Entre em `04`
2. Escolha `11` `INSTALAR PAINEL WEB DE BANCOS`
3. Selecione quais ferramentas quer ativar
4. Informe:
   - diretorio do painel
   - porta local do painel
   - se quer `Adminer`
   - se quer `pgAdmin 4`
   - se quer `Redis Insight`
   - e-mail e senha inicial do `pgAdmin`, se ativado
5. Ao final, abra a URL local mostrada na tela

Esse modulo instala um painel opcional com:

- `Adminer` para MySQL, MariaDB e PostgreSQL
- `pgAdmin 4` para PostgreSQL
- `Redis Insight` para Redis

O painel usa Docker e fica preso a `127.0.0.1` por padrao, sem abrir acesso publico automaticamente.

Depois da instalacao, a tela mostra:

- `URL local`
- `URL remota`
- login do `pgAdmin`, quando ele estiver ativo

Exemplo de acesso local:

```text
http://127.0.0.1:18090/
```

Para gerenciar depois:

1. Entre em `04`
2. Escolha `12` `GERENCIAR PAINEL WEB DE BANCOS`

Opcoes disponiveis:

- iniciar/atualizar painel
- parar painel
- reiniciar painel
- status do painel
- desinstalar painel
- publicar painel via `Nginx + login`
- ativar `HTTPS` no painel

Se depois quiser publicar o painel com seguranca:

1. Abra `12` `GERENCIAR PAINEL WEB DE BANCOS`
2. Escolha `Publicar painel via Nginx + login`
3. Informe dominio, nome do site e credenciais de acesso
4. Depois escolha `Ativar HTTPS no painel`
5. Informe o mesmo dominio e um e-mail valido do Let's Encrypt

Esse fluxo cria um virtual host Nginx com autenticacao basica na frente do painel, e depois permite emitir certificado HTTPS para o dominio informado.

Depois disso, o acesso publicado fica assim:

```text
https://seu-dominio/
```

Dentro das ferramentas, para conectar nos bancos da propria maquina, use:

```text
host.docker.internal
```

Exemplos:

- PostgreSQL no Adminer/pgAdmin: host `host.docker.internal`, porta `5432`
- MySQL/MariaDB no Adminer: host `host.docker.internal`, porta `3306`
- Redis no Redis Insight: host `host.docker.internal`, porta `6379`

Recomendacoes de seguranca:

- nao abra a porta do painel para toda a internet
- se precisar acesso remoto, libere a porta apenas para o seu IP
- se quiser publicar com dominio, coloque o painel atras de Nginx + HTTPS
- se publicar com dominio, mantenha o login extra do Nginx ativado
- o painel nao substitui o banco principal; ele apenas ajuda a administrar

### 7. Alterar idioma

1. Entre em `03`
2. Abra `Power Tools`
3. Escolha `IDIOMA / LANGUAGE`
4. Digite o codigo do idioma disponivel, como `pt`, `en`, `es` ou outro cadastrado no arquivo de strings

### 8. Ler status e logs

Para diagnostico rapido, use:

- `Power Tools -> STATUS DASHBOARD`
- `Power Tools -> LOGS VIEWER`
- `Power Tools -> HEALTH CHECK`
- `Banco de Dados / Backend` para ver o painel de componentes ativos/inativos

### 9. Atualizar o script

Voce pode atualizar de duas formas:

- pelo menu: `Ferramentas -> Atualizar script`
- manualmente:

```bash
cd ~/VpsToolsPy
git pull
source .venv/bin/activate
pip install -r requirements.txt
python -m vps_tools.main
```

## Banco de Dados / Backend

No menu principal:

- `Banco de Dados / Backend`

O submenu concentra os fluxos de deploy e dados:

- PostgreSQL
- MySQL
- MariaDB
- MongoDB
- Redis
- Spring Boot
- systemd
- Nginx
- HTTPS com Certbot
- Painel web de bancos

Esse menu abre com um painel limpo de status dos componentes principais, mostrando apenas se cada item esta ativo ou inativo.

No caso do Redis, o foco e complementar o backend com:

- cache
- sessoes
- filas leves
- dados temporarios

Ele nao substitui o banco principal da aplicacao, como PostgreSQL ou MySQL.

## Adicionar novo idioma

1. Abra `vps_tools/i18n/strings.json`
2. Crie um novo bloco com o codigo do idioma, por exemplo `es`, `fr` ou `de`
3. Preencha as chaves normais e tambem `__pairs__`
4. Salve o arquivo
5. Abra o menu de idioma no app e selecione o novo codigo

Exemplo minimo:

```json
{
  "es": {
    "__pairs__": {
      "MENU PRINCIPAL": "MENU PRINCIPAL",
      "BANCO DE DADOS / BACKEND": "BASE DE DATOS / BACKEND"
    }
  }
}
```

## Comando global (`menu`)

No app:

- Ferramentas -> Criar comando global
- Defina o nome do comando (ex: `menu`)

Depois disso, voce pode iniciar a ferramenta apenas digitando:

```bash
menu
```

## Atualizacao

No servidor:

```bash
cd ~/VpsToolsPy
git pull
source .venv/bin/activate
pip install -r requirements.txt
python -m vps_tools.main
```

Ou use o modulo interno:

- Ferramentas -> Atualizar script

## Observacoes importantes

- Rode como `root` para instalacao/remocao de servicos e ajustes de rede.
- Para modulos com host/dominio, o DNS deve apontar para o IP da VPS.
- Em conflito de porta, o sistema permite:
  - escolher outra porta, ou
  - mover a porta do servico ocupante e reiniciar automaticamente.

## Estrutura do projeto

```text
vps_tools/
  core/
  i18n/
  services/
  ui/
  main.py
```

## Licenca

Uso conforme o repositorio oficial.
