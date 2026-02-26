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
3. Todos os menus aceitam `1` e `01` (ou equivalente)
4. Acoes criticas pedem confirmacao
5. Selecao de usuario suporta setas + Enter ou digitacao manual

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
  services/
  ui/
  main.py
```

## Licenca

Uso conforme o repositorio oficial.
