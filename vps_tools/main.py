import os
import subprocess
import sys
import time

from rich.panel import Panel
from rich.table import Table

from vps_tools.core.i18n import LanguageManager
from vps_tools.core.power_tools import PowerTools
from vps_tools.core.system import SystemActions, SystemInfo
from vps_tools.core.uninstaller import CompleteUninstaller
from vps_tools.core.users import UserManager
from vps_tools.core.utils import BannerManager, HostManager
from vps_tools.services.badvpn import BadVPNService
from vps_tools.services.dropbear import DropbearService
from vps_tools.services.dnstt import DNSTTService
from vps_tools.services.hysteria import HysteriaService
from vps_tools.services.openvpn import OpenVPNService
from vps_tools.services.shadowsocks import ShadowSocksService
from vps_tools.services.squid import SquidService
from vps_tools.services.sslh import SSLHService
from vps_tools.services.stunnel import StunnelService
from vps_tools.services.trojan import TrojanService
from vps_tools.services.xray import XrayService
from vps_tools.ui.terminal import TerminalUI


class VPSToolsApp:
    def __init__(self):
        self.ui = TerminalUI()
        self.sys_info = SystemInfo()
        self.sys_actions = SystemActions()
        self.power_tools = PowerTools()
        self.lang = LanguageManager("pt")
        self.user_manager = UserManager()
        self.services = {
            "SQUID": SquidService(),
            "SSLH": SSLHService(),
            "STUNNEL": StunnelService(),
            "DROPBEAR": DropbearService(),
            "OPENVPN": OpenVPNService(),
            "SHADOWSOCKS": ShadowSocksService(),
            "XRAY": XrayService(),
            "HYSTERIA": HysteriaService(),
            "DNSTT": DNSTTService(),
            "BADVPN": BadVPNService(),
            "TROJAN": TrojanService(),
        }
        self.repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @staticmethod
    def _normalize_option(value: str) -> str:
        value = (value or "").strip()
        if not value:
            return value
        if value == "00":
            return "00"
        if value.isdigit():
            return str(int(value))
        return value.lower()

    def _confirm(self, action: str) -> bool:
        answer = self.ui.prompt(f"Confirmar {action}? (s/n): ").strip().lower()
        return answer == "s"

    def _ask_port(self, prompt: str, default_port: int):
        text = self.ui.prompt(prompt).strip()
        if not text:
            return default_port
        try:
            port = int(text)
            if 1 <= port <= 65535:
                return port
        except ValueError:
            pass
        self.ui.print_error("Porta invalida.")
        return None

    def _resolve_port_conflict(self, desired_port: int, requester_service: str):
        port = desired_port
        while True:
            if self.power_tools.is_port_available(port):
                return True, port

            owner = self.power_tools.detect_port_owner(port)
            self.ui.print_error(
                f"Porta {port} em uso por processo '{owner.get('process', 'unknown')}' "
                f"(servico: {owner.get('service', 'unknown')})."
            )
            self.ui.console.print("[yellow]1)[/yellow] Escolher outra porta")
            self.ui.console.print("[yellow]2)[/yellow] Alterar porta do servico ocupante e continuar")
            self.ui.console.print("[yellow]0)[/yellow] Cancelar instalacao")
            option = self._normalize_option(self.ui.prompt("Opcao: "))

            if option == "1":
                new_port = self._ask_port("Nova porta desejada: ", port)
                if new_port is None:
                    continue
                port = new_port
                continue

            if option == "2":
                owner_service = owner.get("service", "unknown")
                if owner_service in {"unknown", requester_service.lower()}:
                    self.ui.print_error("Nao foi possivel mapear o servico ocupante para alteracao automatica.")
                    time.sleep(1)
                    continue
                new_owner_port = self._ask_port(
                    f"Nova porta para o servico '{owner_service}': ",
                    port + 1 if port < 65535 else 1024,
                )
                if new_owner_port is None:
                    continue
                if not self.power_tools.is_port_available(new_owner_port):
                    self.ui.print_error(f"Porta {new_owner_port} tambem esta em uso.")
                    time.sleep(1)
                    continue
                ok, msg = self.power_tools.change_port(owner_service, new_owner_port)
                if ok:
                    self.ui.print_success(msg)
                    time.sleep(1)
                    # validar novamente que a porta originalmente desejada liberou
                    if self.power_tools.is_port_available(port):
                        return True, port
                    self.ui.print_error("A porta original ainda esta em uso apos alteracao do servico ocupante.")
                    time.sleep(1)
                else:
                    self.ui.print_error(msg)
                    time.sleep(1)
                continue

            if option == "0":
                return False, None

            self.ui.print_error("Opcao invalida.")
            time.sleep(1)

    def _pick_user_for_action(self, action_label: str):
        users = self.user_manager.list_users()
        username = self.ui.select_user(users, action_label=action_label)
        if username is None:
            self.ui.print_info("Acao cancelada.")
            time.sleep(1)
            return None
        if not username.strip():
            self.ui.print_error("Usuario invalido.")
            time.sleep(1)
            return None
        return username.strip()

    def main_menu(self):
        while True:
            self.ui.clear()
            self.ui.draw_header(
                self.sys_info.get_os_info(),
                self.sys_info.get_cpu_usage(),
                self.sys_info.get_ram_info(),
                self.sys_info.get_swap_info(),
                self.sys_info.get_ip(),
                self.sys_info.get_os_info(),
            )

            options = {
                "01": self.lang.t("main.install", "INSTALADOR/CONFIGURAR SERVICOS"),
                "02": self.lang.t("main.users", "GERENCIAMENTO DE USUARIOS"),
                "03": self.lang.t("main.tools", "FERRAMENTAS DO SISTEMA"),
                "04": self.lang.t("main.about", "SOBRE"),
                "00": self.lang.t("main.exit", "SAIR"),
            }
            self.ui.draw_menu(options)

            option = self._normalize_option(self.ui.prompt())

            if option == "1":
                self.installer_menu()
            elif option == "2":
                self.user_manager_menu()
            elif option == "3":
                self.tools_menu()
            elif option == "4":
                self.about()
            elif option == "00":
                sys.exit(0)
            else:
                self.ui.print_error("Opcao invalida!")
                time.sleep(2)

    def user_manager_menu(self):
        while True:
            self.ui.clear()
            users = self.user_manager.list_users()
            self.ui.draw_user_table(users)

            options = {
                "01": "NOVO USUARIO",
                "02": "APAGAR USUARIO",
                "03": "ALTERAR LIMITE",
                "04": "ALTERAR EXPIRACAO",
                "05": "ALTERAR SENHA",
                "06": "DESCONECTAR USUARIO",
                "07": "BACKUP DE USUARIOS",
                "08": "RESTAURAR BACKUP",
                "00": "VOLTAR",
            }
            self.ui.draw_menu(options, "GERENCIAMENTO DE USUARIOS")
            option = self._normalize_option(self.ui.prompt())

            if option == "1":
                if not self._confirm("criacao de usuario"):
                    continue
                username = self.ui.prompt("Nome do novo usuario: ")
                password = self.ui.prompt("Senha para o usuario: ")
                days = self.ui.prompt("Dias para expirar: ")
                limit = self.ui.prompt("Limite de conexoes: ")
                result = self.user_manager.create_user(username, password, days, limit)
                if result is True:
                    self.ui.print_success(f"Usuario {username} criado!")
                else:
                    self.ui.print_error(f"Erro: {result}")
                time.sleep(2)

            elif option == "2":
                if not self._confirm("exclusao de usuario"):
                    continue
                username = self._pick_user_for_action("deletar")
                if not username:
                    continue
                result = self.user_manager.delete_user(username)
                if result is True:
                    self.ui.print_success(f"Usuario {username} deletado!")
                else:
                    self.ui.print_error(f"Erro: {result}")
                time.sleep(2)

            elif option == "3":
                if not self._confirm("alteracao de limite"):
                    continue
                username = self._pick_user_for_action("alterar limite")
                if not username:
                    continue
                new_limit = self.ui.prompt("Novo limite de logins: ")
                result = self.user_manager.change_limit(username, new_limit)
                if result is True:
                    self.ui.print_success(f"Limite de {username} atualizado!")
                else:
                    self.ui.print_error(f"Erro: {result}")
                time.sleep(2)

            elif option == "4":
                if not self._confirm("alteracao de expiracao"):
                    continue
                username = self._pick_user_for_action("alterar expiracao")
                if not username:
                    continue
                year = self.ui.prompt("Ano (YYYY): ")
                month = self.ui.prompt("Mes (MM): ")
                day = self.ui.prompt("Dia (DD): ")
                result = self.user_manager.change_expiry(username, year, month, day)
                if result is True:
                    self.ui.print_success(f"Expiracao de {username} atualizada!")
                else:
                    self.ui.print_error(f"Erro: {result}")
                time.sleep(2)

            elif option == "5":
                if not self._confirm("alteracao de senha"):
                    continue
                username = self._pick_user_for_action("alterar senha")
                if not username:
                    continue
                new_password = self.ui.prompt("Nova senha: ")
                result = self.user_manager.change_password(username, new_password)
                if result is True:
                    self.ui.print_success(f"Senha de {username} alterada!")
                else:
                    self.ui.print_error(f"Erro: {result}")
                time.sleep(2)

            elif option == "6":
                if not self._confirm("desconexao do usuario"):
                    continue
                username = self._pick_user_for_action("desconectar")
                if not username:
                    continue
                if self.user_manager.disconnect_user(username):
                    self.ui.print_success(f"Usuario {username} desconectado!")
                else:
                    self.ui.print_error(f"Nao foi possivel desconectar {username}.")
                time.sleep(2)

            elif option == "7":
                if not self._confirm("backup de usuarios"):
                    continue
                name = self.ui.prompt("Nome para o arquivo de backup: ")
                path = self.user_manager.backup_users(name)
                if isinstance(path, str) and path.startswith("Erro"):
                    self.ui.print_error(path)
                else:
                    self.ui.print_success(f"Backup criado em: {path}")
                time.sleep(2)

            elif option == "8":
                if not self._confirm("restauracao de backup"):
                    continue
                file_path = self.ui.prompt("Caminho completo do backup: ")
                if self.user_manager.restore_backup(file_path):
                    self.ui.print_success("Backup restaurado com sucesso!")
                else:
                    self.ui.print_error("Falha ao restaurar backup.")
                time.sleep(2)

            elif option == "00":
                break
            else:
                self.ui.print_error("Opcao invalida!")
                time.sleep(2)

    def installer_menu(self):
        while True:
            self.ui.clear()
            options = {}
            for i, (name, service) in enumerate(self.services.items(), 1):
                status = (
                    "[bold green]INSTALADO[/]"
                    if service.is_installed()
                    else "[bold red]NAO INSTALADO[/]"
                )
                options[f"{i:02d}"] = f"{name} {status}"

            options["99"] = "VALIDACAO PRE-INSTALACAO"
            options["00"] = self.lang.t("menu.back", "VOLTAR")
            self.ui.draw_menu(options, "MENU DE INSTALACAO")

            option = self._normalize_option(self.ui.prompt())
            if option == "00":
                break
            if option == "99":
                self.pre_install_check_menu()
                continue

            try:
                idx = int(option) - 1
                service_name = list(self.services.keys())[idx]
                self.generic_service_menu(service_name)
            except (ValueError, IndexError):
                self.ui.print_error("Opcao invalida!")
                time.sleep(2)

    def generic_service_menu(self, service_name):
        service = self.services[service_name]
        while True:
            self.ui.clear()
            is_installed = service.is_installed()
            is_running = service.is_running()
            status = "[bold green]ATIVO[/]" if is_running else "[bold red]INATIVO[/]"

            if not is_installed:
                options = {"01": f"INSTALAR {service_name}", "00": "VOLTAR"}
            else:
                options = {
                    "01": "PARAR SERVICO" if is_running else "INICIAR SERVICO",
                    "02": "REINICIAR SERVICO",
                    "03": "DESINSTALAR",
                    "00": "VOLTAR",
                }
                if service_name == "OPENVPN":
                    options["04"] = "GERENCIAR USUARIOS OPENVPN"

            self.ui.draw_menu(options, f"{service_name} ({status})")
            option = self._normalize_option(self.ui.prompt())

            if option == "1":
                if not is_installed:
                    if not self._confirm(f"instalacao do servico {service_name}"):
                        continue
                    self.install_service_flow(service_name)
                else:
                    if is_running:
                        if not self._confirm(f"parada do servico {service_name}"):
                            continue
                        service.stop()
                        self.ui.print_success("Servico parado!")
                    else:
                        if not self._confirm(f"inicio do servico {service_name}"):
                            continue
                        service.start()
                        self.ui.print_success("Servico iniciado!")
                time.sleep(2)
            elif option == "2" and is_installed:
                if not self._confirm(f"reinicio do servico {service_name}"):
                    continue
                service.restart()
                self.ui.print_success("Servico reiniciado!")
                time.sleep(2)
            elif option == "3" and is_installed:
                if not self._confirm(f"desinstalacao do servico {service_name}"):
                    continue
                service.uninstall()
                self.ui.print_success("Servico desinstalado!")
                time.sleep(2)
                break
            elif option == "4" and is_installed and service_name == "OPENVPN":
                self.openvpn_users_menu(service)
            elif option == "00":
                break
            else:
                self.ui.print_error("Opcao invalida!")
                time.sleep(2)

    def install_service_flow(self, service_name):
        service = self.services[service_name]
        ip = self.ui.prompt("Confirme o IP: ")

        try:
            required_ports = []
            if service_name == "SQUID":
                port = self._ask_port("Porta para Squid (padrao 3128): ", 3128)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                required_ports = [port]
                compress = self.ui.prompt("Ativar compressao SSH? (s/n): ").lower() == "s"
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error("Falha na validacao pre-instalacao: " + "; ".join(issues))
                    return
                self.power_tools.save_rollback_snapshot("squid")
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(port, ip, compress)
            elif service_name == "SSLH":
                listen_port = self._ask_port("Porta para SSLH (padrao 443): ", 443)
                if listen_port is None:
                    return
                ok_port, listen_port = self._resolve_port_conflict(listen_port, service_name)
                if not ok_port:
                    return
                required_ports = [listen_port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error("Falha na validacao pre-instalacao: " + "; ".join(issues))
                    return
                self.power_tools.save_rollback_snapshot("sslh")
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(listen_port=listen_port)
            elif service_name == "STUNNEL":
                listen_port = self._ask_port("Porta para STUNNEL (padrao 4433): ", 4433)
                if listen_port is None:
                    return
                ok_port, listen_port = self._resolve_port_conflict(listen_port, service_name)
                if not ok_port:
                    return
                required_ports = [listen_port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error("Falha na validacao pre-instalacao: " + "; ".join(issues))
                    return
                self.power_tools.save_rollback_snapshot("stunnel")
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(listen_port=listen_port)
            elif service_name == "DROPBEAR":
                port = self._ask_port("Porta para DROPBEAR (padrao 2222): ", 2222)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                required_ports = [port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error("Falha na validacao pre-instalacao: " + "; ".join(issues))
                    return
                self.power_tools.save_rollback_snapshot("dropbear")
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(port=port)
            elif service_name == "OPENVPN":
                port = self._ask_port("Porta OpenVPN (padrao 1194): ", 1194)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                proto = self.ui.prompt("Protocolo udp/tcp (padrao udp): ").strip().lower() or "udp"
                client_name = self.ui.prompt("Nome do cliente inicial (padrao client): ").strip() or "client"
                with_host = self.ui.prompt("Usar host/dominio? (s/n): ").strip().lower() == "s"
                endpoint = self.ui.prompt("Host/Dominio (vazio para IP): ").strip() if with_host else ""
                required_ports = [port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error("Falha na validacao pre-instalacao: " + "; ".join(issues))
                    return
                self.power_tools.save_rollback_snapshot("openvpn")
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(
                    port=port,
                    protocol=proto,
                    endpoint=endpoint,
                    use_domain=with_host,
                    client_name=client_name,
                )
            elif service_name == "SHADOWSOCKS":
                port = self._ask_port("Porta ShadowSocks (padrao 8388): ", 8388)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                method = self.ui.prompt("Metodo (padrao chacha20-ietf-poly1305): ").strip() or "chacha20-ietf-poly1305"
                password = self.ui.prompt("Senha (vazio para auto): ").strip()
                required_ports = [port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error("Falha na validacao pre-instalacao: " + "; ".join(issues))
                    return
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(port=port, password=password, method=method)
            elif service_name == "XRAY":
                mode = self.ui.prompt("Modo (vless/vmess/trojan): ").strip().lower() or "vless"
                port = self._ask_port("Porta (padrao 443): ", 443)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                host = self.ui.prompt("Host (opcional): ").strip()
                path = self.ui.prompt("Path WS (padrao /rdy): ").strip() or "/rdy"
                required_ports = [port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error("Falha na validacao pre-instalacao: " + "; ".join(issues))
                    return
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(mode=mode, port=port, host=host, path=path)
            elif service_name == "HYSTERIA":
                port = self._ask_port("Porta Hysteria (padrao 443): ", 443)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                domain = self.ui.prompt("Host/Dominio (vazio para sem host): ").strip()
                password = self.ui.prompt("Senha (vazio para auto): ").strip()
                required_ports = [port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error("Falha na validacao pre-instalacao: " + "; ".join(issues))
                    return
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(port=port, password=password, domain=domain)
            elif service_name == "DNSTT":
                domain = self.ui.prompt("Dominio/subdominio DNSTT (ex: dns.seudominio.com): ").strip()
                udp_port = self._ask_port("Porta UDP DNSTT (padrao 5300): ", 5300)
                if udp_port is None:
                    return
                ok_port, udp_port = self._resolve_port_conflict(udp_port, service_name)
                if not ok_port:
                    return
                secret = self.ui.prompt("Secret (vazio para auto): ").strip()
                required_ports = [udp_port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error("Falha na validacao pre-instalacao: " + "; ".join(issues))
                    return
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(domain=domain, udp_port=udp_port, secret=secret)
            elif service_name == "BADVPN":
                port = self._ask_port("Porta para BADVPN (padrao 7300): ", 7300)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(port=port)
            elif service_name == "TROJAN":
                password = self.ui.prompt("Senha para Trojan: ")
                port = self._ask_port("Porta para Trojan (padrao 443): ", 443)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(password=password, port=port)
            else:
                result = f"Servico desconhecido: {service_name}"
        except ValueError:
            self.ui.print_error("Porta invalida. Digite um numero.")
            return

        if result is True:
            self.ui.print_success(f"{service_name} instalado com sucesso!")
        else:
            self.ui.print_error(f"Erro: {result}")

    def openvpn_users_menu(self, openvpn_service):
        while True:
            self.ui.clear()
            clients = openvpn_service.list_clients()
            table = Table(title="[bold yellow]USUARIOS OPENVPN[/bold yellow]", caption="[bold cyan]RDY SOFTWARE[/bold cyan]")
            table.add_column("Cliente", style="cyan")
            if clients:
                for c in clients:
                    table.add_row(c)
            else:
                table.add_row("(nenhum)")
            self.ui.console.print(table)

            options = {
                "01": "CRIAR CLIENTE",
                "02": "REVOGAR CLIENTE",
                "00": "VOLTAR",
            }
            self.ui.draw_menu(options, "OPENVPN USERS")
            option = self._normalize_option(self.ui.prompt())
            if option == "1":
                if not self._confirm("criacao de cliente openvpn"):
                    continue
                username = self.ui.prompt("Nome do cliente: ").strip()
                use_host = self.ui.prompt("Usar host/dominio no cliente? (s/n): ").strip().lower() == "s"
                endpoint = self.ui.prompt("Host/Dominio (vazio para IP): ").strip() if use_host else ""
                result = openvpn_service.add_client(username=username, endpoint=endpoint, use_domain=use_host)
                if isinstance(result, str) and result.lower().startswith("cliente criado"):
                    self.ui.print_success(result)
                else:
                    self.ui.print_error(f"Erro: {result}")
                time.sleep(2)
            elif option == "2":
                if not self._confirm("revogacao de cliente openvpn"):
                    continue
                username = self.ui.prompt("Nome do cliente a revogar: ").strip()
                result = openvpn_service.revoke_client(username)
                if result is True:
                    self.ui.print_success(f"Cliente {username} revogado.")
                else:
                    self.ui.print_error(f"Erro: {result}")
                time.sleep(2)
            elif option == "00":
                break
            else:
                self.ui.print_error("Opcao invalida!")
                time.sleep(1)

    def tools_menu(self):
        while True:
            self.ui.clear()
            options = {
                "01": "CRIAR/ALTERAR BANNER SSH",
                "02": "GERENCIAR HOSTS (PAYLOADS)",
                "03": "LIMPAR CACHE E INODES",
                "04": "ATUALIZAR SISTEMA",
                "05": "REINICIAR SERVIDOR",
                "06": "DESINSTALACAO COMPLETA",
                "07": "ATUALIZAR SCRIPT",
                "08": "CRIAR COMANDO GLOBAL",
                "09": "CRIAR SWAP",
                "10": "TESTE DE VELOCIDADE",
                "11": "POWER TOOLS",
                "00": "VOLTAR",
            }
            self.ui.draw_menu(options, "FERRAMENTAS")
            option = self._normalize_option(self.ui.prompt())

            if option == "1":
                if not self._confirm("alteracao do banner SSH"):
                    continue
                banner_text = self.ui.prompt("Texto do Banner: ")
                BannerManager.set_banner(banner_text)
                self.ui.print_success("Banner atualizado!")
                time.sleep(2)
            elif option == "2":
                self.hosts_menu()
            elif option == "3":
                if not self._confirm("limpeza de cache e inodes"):
                    continue
                self.ui.show_spinner("Limpando cache")
                result = self.sys_actions.clear_cache()
                if result is True:
                    self.ui.print_success("Cache limpo!")
                else:
                    self.ui.print_error(f"Erro ao limpar cache: {result}")
                time.sleep(2)
            elif option == "4":
                if not self._confirm("atualizacao do sistema"):
                    continue
                self.ui.print_info("Iniciando atualizacao do sistema...")
                commands = self.sys_actions.update_system()
                if not commands:
                    self.ui.print_error("Nenhum gerenciador de pacotes suportado encontrado (apt/yum).")
                    time.sleep(2)
                    continue
                for cmd in commands:
                    self.ui.print_info(f"Executando: {' '.join(cmd)}")
                    subprocess.run(cmd, check=False)
                self.ui.print_success("Sistema atualizado!")
                time.sleep(2)
            elif option == "5":
                if self._confirm("reinicio do servidor"):
                    self.sys_actions.reboot()
            elif option == "6":
                if self._confirm("DESINSTALACAO COMPLETA"):
                    self.ui.print_info("Executando desinstalacao completa...")
                    uninstaller = CompleteUninstaller()
                    results = uninstaller.run()
                    summary = CompleteUninstaller.summarize(results)
                    self.ui.print_success(summary)
                    self.ui.print_info("Verifique os logs/servicos para confirmar os itens com falha.")
                    time.sleep(3)
            elif option == "7":
                if not self._confirm("atualizacao do script"):
                    continue
                self.ui.print_info("Atualizando script pelo git...")
                ok, msg = self.sys_actions.update_script(self.repo_dir)
                if ok:
                    self.ui.print_success(msg)
                else:
                    self.ui.print_error(msg)
                time.sleep(2)
            elif option == "8":
                if not self._confirm("criacao de comando global"):
                    continue
                command_name = self.ui.prompt("Nome do comando global (ex: menu): ").strip()
                if not command_name:
                    self.ui.print_error("Nome do comando nao pode ser vazio.")
                    time.sleep(2)
                    continue
                self.ui.print_info(f"Criando comando global '{command_name}'...")
                ok, msg = self.sys_actions.create_menu_command(self.repo_dir, command_name)
                if ok:
                    self.ui.print_success(msg)
                else:
                    self.ui.print_error(msg)
                time.sleep(2)
            elif option == "9":
                if not self._confirm("criacao de swap"):
                    continue
                size_text = self.ui.prompt("Tamanho da SWAP em MB (padrao 1024): ").strip()
                try:
                    size_mb = int(size_text) if size_text else 1024
                except ValueError:
                    self.ui.print_error("Valor invalido para tamanho da swap.")
                    time.sleep(2)
                    continue
                ok, msg = self.sys_actions.create_swap(size_mb=size_mb)
                if ok:
                    self.ui.print_success(msg)
                else:
                    self.ui.print_error(msg)
                time.sleep(2)
            elif option == "10":
                if not self._confirm("teste de velocidade do servidor"):
                    continue

                def worker(update):
                    return self.sys_actions.measure_server_speed(progress_callback=update)

                ok, data = self.ui.run_animated_task("Medindo velocidade", worker)
                if ok:
                    self.ui.console.print(
                        Panel(
                            "[bold green]Resultado do teste[/bold green]\n\n"
                            f"[white]Ping:[/white] [cyan]{data['ping_ms']} ms[/cyan]\n"
                            f"[white]Download:[/white] [cyan]{data['download_mbps']} Mbps[/cyan]\n"
                            f"[white]Upload:[/white] [cyan]{data['upload_mbps']} Mbps[/cyan]\n"
                            f"[white]Amostra download:[/white] [cyan]{data['download_mb_tested']} MB[/cyan]\n"
                            f"[white]Amostra upload:[/white] [cyan]{data['upload_mb_tested']} MB[/cyan]",
                            title="VELOCIDADE",
                            border_style="green",
                        )
                    )
                else:
                    self.ui.print_error(f"Falha no teste: {data}")
                self.ui.prompt("Pressione Enter para continuar...")
            elif option == "11":
                self.power_tools_menu()
            elif option == "00":
                break
            else:
                self.ui.print_error("Opcao invalida!")
                time.sleep(2)

    def hosts_menu(self):
        while True:
            self.ui.clear()
            hosts = HostManager.list_hosts()
            self.ui.print_info("Hosts atuais:")
            for host in hosts:
                self.ui.console.print(f" - {host}")

            options = {"01": "ADICIONAR HOST", "02": "REMOVER HOST", "00": "VOLTAR"}
            self.ui.draw_menu(options, "GERENCIAR HOSTS")
            option = self._normalize_option(self.ui.prompt())

            if option == "1":
                if not self._confirm("adicao de host payload"):
                    continue
                host = self.ui.prompt("Host a adicionar: ")
                HostManager.add_host(host)
                self.ui.print_success("Host adicionado!")
                time.sleep(2)
            elif option == "2":
                if not self._confirm("remocao de host payload"):
                    continue
                host = self.ui.prompt("Host a remover: ")
                HostManager.remove_host(host)
                self.ui.print_success("Host removido!")
                time.sleep(2)
            elif option == "00":
                break
            else:
                self.ui.print_error("Opcao invalida!")
                time.sleep(2)

    def about(self):
        self.ui.clear()
        self.ui.console.print(
            Panel(
                "[bold yellow]VPS TOOLS [red]PYTHON VERSION[/bold yellow]\n\n"
                "[green]Baseado no script original da RDY SOFTWARE.\n"
                "[blue]Reescrito em Python para melhor performance e estabilidade.\n\n"
                "[cyan]Telegram: @rdysoftware",
                title="SOBRE",
                border_style="green",
            )
        )
        self.ui.prompt("Pressione qualquer tecla para voltar...")

    def pre_install_check_menu(self):
        service_name = self.ui.prompt("Servico para validar (SQUID/SSLH/STUNNEL/DROPBEAR): ").strip().lower()
        ports_raw = self.ui.prompt("Portas separadas por virgula (ex: 80,443): ").strip()
        ports = []
        for item in ports_raw.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                ports.append(int(item))
            except ValueError:
                pass
        ok, issues = self.power_tools.pre_install_validation(service_name, ports)
        if ok:
            self.ui.print_success("Validacao pre-instalacao OK.")
        else:
            self.ui.print_error("Falhas encontradas: " + "; ".join(issues))
        time.sleep(2)

    def power_tools_menu(self):
        while True:
            self.ui.clear()
            options = {
                "01": "PORT CHANGER",
                "02": "STATUS DASHBOARD",
                "03": "LOGS VIEWER",
                "04": "BACKUP/RESTORE CONFIG",
                "05": "FIREWALL MANAGER",
                "06": "HEALTH CHECK",
                "07": "ROLLBACK",
                "08": "SETUP WIZARD",
                "09": "IDIOMA / LANGUAGE",
                "00": "VOLTAR",
            }
            self.ui.draw_menu(options, "POWER TOOLS")
            option = self._normalize_option(self.ui.prompt())

            if option == "1":
                self.port_changer_menu()
            elif option == "2":
                self.dashboard_menu()
            elif option == "3":
                self.logs_viewer_menu()
            elif option == "4":
                self.config_backup_restore_menu()
            elif option == "5":
                self.firewall_menu()
            elif option == "6":
                self.health_check_menu()
            elif option == "7":
                self.rollback_menu()
            elif option == "8":
                self.setup_wizard_menu()
            elif option == "9":
                self.language_menu()
            elif option == "00":
                break
            else:
                self.ui.print_error("Opcao invalida!")
                time.sleep(1)

    def port_changer_menu(self):
        if not self._confirm("alteracao de portas"):
            return
        service = self.ui.prompt("Servico (ssh/dropbear/squid/stunnel/sslh): ").strip().lower()
        try:
            port = int(self.ui.prompt("Nova porta: ").strip())
        except ValueError:
            self.ui.print_error("Porta invalida.")
            time.sleep(1)
            return
        ok, msg = self.power_tools.change_port(service, port)
        if ok:
            self.ui.print_success(msg)
        else:
            self.ui.print_error(msg)
        time.sleep(2)

    def dashboard_menu(self):
        loops_raw = self.ui.prompt("Quantas atualizacoes? (padrao 10): ").strip()
        try:
            loops = int(loops_raw) if loops_raw else 10
        except ValueError:
            loops = 10
        for _ in range(max(1, loops)):
            self.ui.clear()
            data = self.power_tools.dashboard_snapshot()
            status = self.power_tools.service_status_map(["ssh", "dropbear", "squid", "sslh", "stunnel4", "trojan"])
            table = Table(title="[bold yellow]STATUS DASHBOARD[/bold yellow]", caption="[bold cyan]RDY SOFTWARE[/bold cyan]")
            table.add_column("Item", style="cyan")
            table.add_column("Valor", style="white")
            table.add_row("CPU", f"{data['cpu_percent']}%")
            table.add_row("RAM", f"{data['mem_percent']}%")
            table.add_row("SWAP", f"{data['swap_percent']}%")
            table.add_row("DISCO", f"{data['disk_percent']}%")
            table.add_row("NET ENVIADO", f"{data['net_sent_mb']} MB")
            table.add_row("NET RECEBIDO", f"{data['net_recv_mb']} MB")
            table.add_row("SESSOES", str(data["sessions"]))
            self.ui.console.print(table)
            st = Table(title="[bold yellow]SERVICOS[/bold yellow]", caption="[bold cyan]RDY SOFTWARE[/bold cyan]")
            st.add_column("Servico", style="cyan")
            st.add_column("Status", style="white")
            for name, value in status.items():
                st.add_row(name, value)
            self.ui.console.print(st)
            time.sleep(1)
        self.ui.prompt("Enter para voltar...")

    def logs_viewer_menu(self):
        service = self.ui.prompt("Servico para logs (ex: squid): ").strip()
        lines_raw = self.ui.prompt("Qtd linhas (padrao 80): ").strip()
        try:
            lines = int(lines_raw) if lines_raw else 80
        except ValueError:
            lines = 80
        ok, logs = self.power_tools.read_service_logs(service, lines=lines)
        if not ok:
            self.ui.print_error(logs)
            time.sleep(2)
            return
        self.ui.console.print(
            Panel(logs[-6000:], title=f"LOGS: {service}", border_style="blue")
        )
        if self._confirm("salvar logs em arquivo"):
            path = self.ui.prompt("Caminho do arquivo: ").strip()
            try:
                with open(path, "w") as f:
                    f.write(logs)
                self.ui.print_success(f"Logs salvos em {path}")
            except Exception as exc:
                self.ui.print_error(str(exc))
        self.ui.prompt("Enter para voltar...")

    def config_backup_restore_menu(self):
        option = self._normalize_option(self.ui.prompt("1 Backup / 2 Restore: "))
        if option == "1":
            if not self._confirm("backup de configuracoes"):
                return
            name = self.ui.prompt("Nome do backup: ").strip() or "backup"
            ok, msg = self.power_tools.backup_configs(name)
            if ok:
                self.ui.print_success(f"Backup criado: {msg}")
            else:
                self.ui.print_error(msg)
        elif option == "2":
            if not self._confirm("restore de configuracoes"):
                return
            path = self.ui.prompt("Caminho do backup .tar.gz: ").strip()
            ok, msg = self.power_tools.restore_configs(path)
            if ok:
                self.ui.print_success(msg)
            else:
                self.ui.print_error(msg)
        else:
            self.ui.print_error("Opcao invalida.")
        time.sleep(2)

    def firewall_menu(self):
        if not self._confirm("aplicacao de perfil de firewall"):
            return
        profile = self.ui.prompt("Perfil (basic/open): ").strip().lower()
        ok, msg = self.power_tools.firewall_apply(profile)
        if ok:
            self.ui.print_success(msg)
        else:
            self.ui.print_error(msg)
        time.sleep(2)

    def health_check_menu(self):
        report = self.power_tools.health_check()
        table = Table(title="[bold yellow]HEALTH CHECK[/bold yellow]", caption="[bold cyan]RDY SOFTWARE[/bold cyan]")
        table.add_column("Check", style="cyan")
        table.add_column("Resultado", style="white")
        for k, v in report.items():
            table.add_row(k, v)
        self.ui.console.print(table)
        self.ui.prompt("Enter para voltar...")

    def rollback_menu(self):
        option = self._normalize_option(self.ui.prompt("1 Criar snapshot / 2 Restaurar: "))
        if option == "1":
            if not self._confirm("snapshot de rollback"):
                return
            service = self.ui.prompt("Servico (ssh/dropbear/squid/sslh/stunnel): ").strip().lower()
            ok, msg = self.power_tools.save_rollback_snapshot(service)
            if ok:
                self.ui.print_success(f"Snapshot salvo: {msg}")
            else:
                self.ui.print_error(msg)
        elif option == "2":
            if not self._confirm("restaurar rollback"):
                return
            service = self.ui.prompt("Servico (ssh/dropbear/squid/sslh/stunnel): ").strip().lower()
            snaps = self.power_tools.list_rollbacks(service)
            if not snaps:
                self.ui.print_error("Nenhum snapshot encontrado.")
                time.sleep(2)
                return
            self.ui.console.print(Panel("\n".join(snaps), title="Snapshots"))
            path = self.ui.prompt("Informe o caminho exato do snapshot: ").strip()
            ok, msg = self.power_tools.restore_rollback(path)
            if ok:
                self.ui.print_success(msg)
            else:
                self.ui.print_error(msg)
        else:
            self.ui.print_error("Opcao invalida.")
        time.sleep(2)

    def setup_wizard_menu(self):
        if not self._confirm("executar setup wizard"):
            return
        self.ui.print_info("1) Atualizacao do script")
        ok, msg = self.sys_actions.update_script(self.repo_dir)
        self.ui.print_success(msg) if ok else self.ui.print_error(msg)

        self.ui.print_info("2) Validacao pre-instalacao")
        valid, issues = self.power_tools.pre_install_validation("wizard", [22, 80, 443])
        if not valid:
            self.ui.print_error("Pendencias: " + "; ".join(issues))
        else:
            self.ui.print_success("Validacao OK")

        if self._confirm("criar swap 1024 MB"):
            ok, msg = self.sys_actions.create_swap(1024)
            self.ui.print_success(msg) if ok else self.ui.print_error(msg)

        if self._confirm("criar comando global 'menu'"):
            ok, msg = self.sys_actions.create_menu_command(self.repo_dir, "menu")
            self.ui.print_success(msg) if ok else self.ui.print_error(msg)
        self.ui.prompt("Setup finalizado. Enter para voltar...")

    def language_menu(self):
        option = self.ui.prompt("Idioma (pt/en): ").strip().lower()
        if self.lang.set_language(option):
            self.ui.print_success(self.lang.t("lang.changed", "Idioma alterado com sucesso."))
        else:
            self.ui.print_error("Idioma invalido.")
        time.sleep(1)


if __name__ == "__main__":
    app = VPSToolsApp()
    app.main_menu()
