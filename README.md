# VpsToolsPy

Suite de gerenciamento de VPS em Python para automação de serviços, usuários e ferramentas operacionais.

## Recursos

- Instalador e gerenciador de serviços:
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
- Gerenciamento de usuários SSH
- Backup/restore de usuários
- Power Tools:
  - Port changer
  - Dashboard de status
  - Logs viewer
  - Backup/restore de configurações
  - Firewall manager
  - Health check
  - Rollback de configuração
  - Setup wizard
  - Idioma PT/EN
- Ferramentas do sistema:
  - Atualização do sistema
  - Criação de swap
  - Teste de velocidade
  - Criação de comando global (ex: `menu`)
  - Desinstalação completa

## Requisitos

- Linux (Debian/Ubuntu/CentOS/RHEL)
- Acesso root
- Python 3.10+
- Git

## Instalação (Debian/Ubuntu)

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

## Instalação (CentOS/RHEL)

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

## Uso rápido

1. Execute `python -m vps_tools.main`
2. Menu principal:
   - `01` Instalador/configuração de serviços
   - `02` Gerenciamento de usuários
   - `03` Ferramentas do sistema
3. Todos os menus aceitam `1` e `01` (ou equivalente)
4. Ações críticas pedem confirmação
5. Seleção de usuário suporta setas + Enter ou digitação manual

## Comando global (`menu`)

No app:

- Ferramentas -> Criar comando global
- Defina o nome do comando (ex: `menu`)

Depois disso, você poderá iniciar a ferramenta apenas digitando:

```bash
menu
```

## Atualização

No servidor:

```bash
cd ~/VpsToolsPy
git pull
source .venv/bin/activate
pip install -r requirements.txt
python -m vps_tools.main
```

Ou use o módulo interno:

- Ferramentas -> Atualizar script

## Observações importantes

- Rode como `root` para instalação/remoção de serviços e ajustes de rede.
- Para módulos com host/domínio, o DNS deve apontar para o IP da VPS.
- Em caso de conflito de porta, o sistema oferece:
  - escolher outra porta, ou
  - mover a porta do serviço ocupante e reiniciar automaticamente.

## Estrutura do projeto

```text
vps_tools/
  core/
  services/
  ui/
  main.py
```

## Licença

Uso conforme o repositório oficial.
