import os
import subprocess
import sys
import time

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from vps_tools.core.i18n import LanguageManager
from vps_tools.core.power_tools import PowerTools
from vps_tools.core.system import SystemActions, SystemInfo
from vps_tools.core.uninstaller import CompleteUninstaller
from vps_tools.core.users import UserManager
from vps_tools.core.utils import BannerManager, HostManager
from vps_tools.services.badvpn import BadVPNService
from vps_tools.services.domain_audit import DomainAuditService
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
        self.ui.set_language(self.lang.current_lang)
        self.user_manager = UserManager()
        self.repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
            "DOMAIN_AUDIT": DomainAuditService(),
        }

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

    def _txt(self, pt: str, en: str) -> str:
        return en if self.lang.current_lang == "en" else pt

    def _confirm(self, action: str) -> bool:
        if self.lang.current_lang == "en":
            action_map = {
                "criacao de usuario": "user creation",
                "exclusao de usuario": "user deletion",
                "alteracao de limite": "limit change",
                "alteracao de expiracao": "expiry change",
                "alteracao de senha": "password change",
                "desconexao do usuario": "user disconnection",
                "backup de usuarios": "user backup",
                "restauracao de backup": "backup restore",
                "instalacao do servico": "service installation",
                "parada do servico": "service stop",
                "inicio do servico": "service start",
                "reinicio do servico": "service restart",
                "desinstalacao do servico": "service uninstall",
                "criacao de cliente openvpn": "OpenVPN client creation",
                "revogacao de cliente openvpn": "OpenVPN client revoke",
                "alteracao do banner SSH": "SSH banner change",
                "limpeza de cache e inodes": "cache/inodes cleanup",
                "atualizacao do sistema": "system update",
                "reinicio do servidor": "server reboot",
                "DESINSTALACAO COMPLETA": "full uninstall",
                "atualizacao do script": "script update",
                "criacao de comando global": "global command creation",
                "criacao de swap": "swap creation",
                "teste de velocidade do servidor": "server speed test",
                "adicao de host payload": "payload host add",
                "remocao de host payload": "payload host removal",
                "alteracao de portas": "port change",
                "backup de configuracoes": "config backup",
                "restore de configuracoes": "config restore",
                "aplicacao de perfil de firewall": "firewall profile apply",
                "snapshot de rollback": "rollback snapshot",
                "restaurar rollback": "rollback restore",
                "executar setup wizard": "setup wizard",
                "criar swap 1024 MB": "create 1024 MB swap",
                "criar comando global 'menu'": "create global command 'menu'",
                "execucao de domain audit": "domain audit execution",
            }
            for k, v in action_map.items():
                if action == k or action.startswith(k + " "):
                    action = action.replace(k, v, 1)
                    break
        answer = self.ui.prompt(
            f"{self.lang.t('confirm.prefix', 'Confirm')} {action}? {self.lang.t('confirm.suffix', '(s/n):')}"
        ).strip().lower()
        return answer in {"s", "y", "yes", "sim"}

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
        self.ui.print_error(self.lang.t("common.invalid_port", "Porta invalida."))
        return None

    def _resolve_port_conflict(self, desired_port: int, requester_service: str):
        port = desired_port
        while True:
            if self.power_tools.is_port_available(port):
                return True, port

            owner = self.power_tools.detect_port_owner(port)
            self.ui.print_error(
                self.lang.t("conflict.in_use", "Porta {port} em uso por processo '{process}' (servico: {service}).").format(
                    port=port,
                    process=owner.get("process", "unknown"),
                    service=owner.get("service", "unknown"),
                )
            )
            self.ui.console.print(f"[yellow]1)[/yellow] {self.lang.t('conflict.choose_other', 'Escolher outra porta')}")
            self.ui.console.print(f"[yellow]2)[/yellow] {self.lang.t('conflict.change_owner', 'Alterar porta do servico ocupante e continuar')}")
            self.ui.console.print(f"[yellow]0)[/yellow] {self.lang.t('conflict.cancel_install', 'Cancelar instalacao')}")
            option = self._normalize_option(self.ui.prompt(self.lang.t("conflict.option", "Opcao: ")))

            if option == "1":
                new_port = self._ask_port(self.lang.t("conflict.new_desired_port", "Nova porta desejada: "), port)
                if new_port is None:
                    continue
                port = new_port
                continue

            if option == "2":
                owner_service = owner.get("service", "unknown")
                if owner_service in {"unknown", requester_service.lower()}:
                    self.ui.print_error(self.lang.t("conflict.owner_unmapped", "Nao foi possivel mapear o servico ocupante para alteracao automatica."))
                    time.sleep(1)
                    continue
                new_owner_port = self._ask_port(
                    self.lang.t("conflict.new_owner_port", "Nova porta para o servico '{service}': ").format(service=owner_service),
                    port + 1 if port < 65535 else 1024,
                )
                if new_owner_port is None:
                    continue
                if not self.power_tools.is_port_available(new_owner_port):
                    self.ui.print_error(self.lang.t("conflict.new_owner_in_use", "Porta {port} tambem esta em uso.").format(port=new_owner_port))
                    time.sleep(1)
                    continue
                ok, msg = self.power_tools.change_port(owner_service, new_owner_port)
                if ok:
                    self.ui.print_success(msg)
                    time.sleep(1)
                    # validar novamente que a porta originalmente desejada liberou
                    if self.power_tools.is_port_available(port):
                        return True, port
                    self.ui.print_error(self.lang.t("conflict.original_still_used", "A porta original ainda esta em uso apos alteracao do servico ocupante."))
                    time.sleep(1)
                else:
                    self.ui.print_error(msg)
                    time.sleep(1)
                continue

            if option == "0":
                return False, None

            self.ui.print_error(self.lang.t("menu.invalid", "Opcao invalida!"))
            time.sleep(1)

    def _pick_user_for_action(self, action_label: str):
        users = self.user_manager.list_users()
        username = self.ui.select_user(users, action_label=action_label)
        if username is None:
            self.ui.print_info(self.lang.t("common.cancelled", "Acao cancelada."))
            time.sleep(1)
            return None
        if not username.strip():
            self.ui.print_error(self.lang.t("common.invalid_user", "Usuario invalido."))
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
                self.ui.print_error(self.lang.t("menu.invalid", "Opcao invalida!"))
                time.sleep(2)

    def user_manager_menu(self):
        while True:
            self.ui.clear()
            users = self.user_manager.list_users()
            self.ui.draw_user_table(users)

            options = {
                "01": self.lang.t("users.new", "NOVO USUARIO"),
                "02": self.lang.t("users.delete", "APAGAR USUARIO"),
                "03": self.lang.t("users.limit", "ALTERAR LIMITE"),
                "04": self.lang.t("users.expiry", "ALTERAR EXPIRACAO"),
                "05": self.lang.t("users.password", "ALTERAR SENHA"),
                "06": self.lang.t("users.disconnect", "DESCONECTAR USUARIO"),
                "07": self.lang.t("users.backup", "BACKUP DE USUARIOS"),
                "08": self.lang.t("users.restore", "RESTAURAR BACKUP"),
                "00": self.lang.t("menu.back", "VOLTAR"),
            }
            self.ui.draw_menu(options, self.lang.t("users.title", "GERENCIAMENTO DE USUARIOS"))
            option = self._normalize_option(self.ui.prompt())

            if option == "1":
                if not self._confirm("criacao de usuario"):
                    continue
                username = self.ui.prompt("Nome do novo usuario: " if self.lang.current_lang == "pt" else "New username: ")
                password = self.ui.prompt("Senha para o usuario: " if self.lang.current_lang == "pt" else "Password for user: ")
                days = self.ui.prompt("Dias para expirar: " if self.lang.current_lang == "pt" else "Days to expire: ")
                limit = self.ui.prompt("Limite de conexoes: " if self.lang.current_lang == "pt" else "Connection limit: ")
                result = self.user_manager.create_user(username, password, days, limit)
                if result is True:
                    self.ui.print_success(
                        f"Usuario {username} criado!" if self.lang.current_lang == "pt" else f"User {username} created!"
                    )
                else:
                    self.ui.print_error(f"{self.lang.t('common.error_prefix', 'Erro:')} {result}")
                time.sleep(2)

            elif option == "2":
                if not self._confirm("exclusao de usuario"):
                    continue
                username = self._pick_user_for_action("deletar")
                if not username:
                    continue
                result = self.user_manager.delete_user(username)
                if result is True:
                    self.ui.print_success(
                        f"Usuario {username} deletado!" if self.lang.current_lang == "pt" else f"User {username} deleted!"
                    )
                else:
                    self.ui.print_error(f"{self.lang.t('common.error_prefix', 'Erro:')} {result}")
                time.sleep(2)

            elif option == "3":
                if not self._confirm("alteracao de limite"):
                    continue
                username = self._pick_user_for_action("alterar limite")
                if not username:
                    continue
                new_limit = self.ui.prompt("Novo limite de logins: " if self.lang.current_lang == "pt" else "New login limit: ")
                result = self.user_manager.change_limit(username, new_limit)
                if result is True:
                    self.ui.print_success(
                        f"Limite de {username} atualizado!" if self.lang.current_lang == "pt" else f"{username} limit updated!"
                    )
                else:
                    self.ui.print_error(f"{self.lang.t('common.error_prefix', 'Erro:')} {result}")
                time.sleep(2)

            elif option == "4":
                if not self._confirm("alteracao de expiracao"):
                    continue
                username = self._pick_user_for_action("alterar expiracao")
                if not username:
                    continue
                year = self.ui.prompt("Ano (YYYY): " if self.lang.current_lang == "pt" else "Year (YYYY): ")
                month = self.ui.prompt("Mes (MM): " if self.lang.current_lang == "pt" else "Month (MM): ")
                day = self.ui.prompt("Dia (DD): " if self.lang.current_lang == "pt" else "Day (DD): ")
                result = self.user_manager.change_expiry(username, year, month, day)
                if result is True:
                    self.ui.print_success(
                        f"Expiracao de {username} atualizada!" if self.lang.current_lang == "pt" else f"{username} expiry updated!"
                    )
                else:
                    self.ui.print_error(f"{self.lang.t('common.error_prefix', 'Erro:')} {result}")
                time.sleep(2)

            elif option == "5":
                if not self._confirm("alteracao de senha"):
                    continue
                username = self._pick_user_for_action("alterar senha")
                if not username:
                    continue
                new_password = self.ui.prompt("Nova senha: " if self.lang.current_lang == "pt" else "New password: ")
                result = self.user_manager.change_password(username, new_password)
                if result is True:
                    self.ui.print_success(
                        f"Senha de {username} alterada!" if self.lang.current_lang == "pt" else f"{username} password changed!"
                    )
                else:
                    self.ui.print_error(f"{self.lang.t('common.error_prefix', 'Erro:')} {result}")
                time.sleep(2)

            elif option == "6":
                if not self._confirm("desconexao do usuario"):
                    continue
                username = self._pick_user_for_action("desconectar")
                if not username:
                    continue
                if self.user_manager.disconnect_user(username):
                    self.ui.print_success(
                        f"Usuario {username} desconectado!" if self.lang.current_lang == "pt" else f"User {username} disconnected!"
                    )
                else:
                    self.ui.print_error(
                        f"Nao foi possivel desconectar {username}." if self.lang.current_lang == "pt" else f"Could not disconnect {username}."
                    )
                time.sleep(2)

            elif option == "7":
                if not self._confirm("backup de usuarios"):
                    continue
                name = self.ui.prompt("Nome para o arquivo de backup: " if self.lang.current_lang == "pt" else "Backup filename: ")
                path = self.user_manager.backup_users(name)
                if isinstance(path, str) and path.startswith("Erro"):
                    self.ui.print_error(path)
                else:
                    self.ui.print_success(
                        f"Backup criado em: {path}" if self.lang.current_lang == "pt" else f"Backup created at: {path}"
                    )
                time.sleep(2)

            elif option == "8":
                if not self._confirm("restauracao de backup"):
                    continue
                file_path = self.ui.prompt("Caminho completo do backup: " if self.lang.current_lang == "pt" else "Full backup path: ")
                if self.user_manager.restore_backup(file_path):
                    self.ui.print_success(
                        "Backup restaurado com sucesso!" if self.lang.current_lang == "pt" else "Backup restored successfully!"
                    )
                else:
                    self.ui.print_error(
                        "Falha ao restaurar backup." if self.lang.current_lang == "pt" else "Failed to restore backup."
                    )
                time.sleep(2)

            elif option == "00":
                break
            else:
                self.ui.print_error(self.lang.t("menu.invalid", "Opcao invalida!"))
                time.sleep(2)

    def installer_menu(self):
        while True:
            self.ui.clear()
            options = {}
            for i, (name, service) in enumerate(self.services.items(), 1):
                status = (
                    f"[bold green]{self.lang.t('service.installed', 'INSTALADO')}[/]"
                    if service.is_installed()
                    else f"[bold red]{self.lang.t('service.not_installed', 'NAO INSTALADO')}[/]"
                )
                options[f"{i:02d}"] = f"{name} {status}"

            options["99"] = self.lang.t("installer.precheck", "VALIDACAO PRE-INSTALACAO")
            options["00"] = self.lang.t("menu.back", "VOLTAR")
            self.ui.draw_menu(options, self.lang.t("installer.title", "MENU DE INSTALACAO"))

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
                self.ui.print_error(self.lang.t("menu.invalid", "Opcao invalida!"))
                time.sleep(2)

    def generic_service_menu(self, service_name):
        if service_name == "DOMAIN_AUDIT":
            self.domain_audit_service_menu()
            return

        service = self.services[service_name]
        while True:
            self.ui.clear()
            is_installed = service.is_installed()
            is_running = service.is_running()
            status = (
                f"[bold green]{self.lang.t('service.active', 'ATIVO')}[/]"
                if is_running
                else f"[bold red]{self.lang.t('service.inactive', 'INATIVO')}[/]"
            )

            if not is_installed:
                options = {
                    "01": f"{self.lang.t('service.install', 'INSTALAR')} {service_name}",
                    "00": self.lang.t("menu.back", "VOLTAR"),
                }
            else:
                options = {
                    "01": self.lang.t("service.stop", "PARAR SERVICO")
                    if is_running
                    else self.lang.t("service.start", "INICIAR SERVICO"),
                    "02": self.lang.t("service.restart", "REINICIAR SERVICO"),
                    "03": self.lang.t("service.uninstall", "DESINSTALAR"),
                    "00": self.lang.t("menu.back", "VOLTAR"),
                }
                if service_name == "OPENVPN":
                    options["04"] = self._txt("GERENCIAR USUARIOS OPENVPN", "MANAGE OPENVPN USERS")

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
                        self.ui.print_success(self.lang.t("service.stop_ok", "Servico parado!"))
                    else:
                        if not self._confirm(f"inicio do servico {service_name}"):
                            continue
                        service.start()
                        self.ui.print_success(self.lang.t("service.start_ok", "Servico iniciado!"))
                time.sleep(2)
            elif option == "2" and is_installed:
                if not self._confirm(f"reinicio do servico {service_name}"):
                    continue
                service.restart()
                self.ui.print_success(self.lang.t("service.restart_ok", "Servico reiniciado!"))
                time.sleep(2)
            elif option == "3" and is_installed:
                if not self._confirm(f"desinstalacao do servico {service_name}"):
                    continue
                service.uninstall()
                self.ui.print_success(self.lang.t("service.uninstall_ok", "Servico desinstalado!"))
                time.sleep(2)
                break
            elif option == "4" and is_installed and service_name == "OPENVPN":
                self.openvpn_users_menu(service)
            elif option == "00":
                break
            else:
                self.ui.print_error(self.lang.t("menu.invalid", "Opcao invalida!"))
                time.sleep(2)

    def install_service_flow(self, service_name):
        service = self.services[service_name]
        ip = self.ui.prompt(self._txt("Confirme o IP: ", "Confirm IP: "))

        try:
            required_ports = []
            if service_name == "SQUID":
                port = self._ask_port(self._txt("Porta para Squid (padrao 3128): ", "Squid port (default 3128): "), 3128)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                required_ports = [port]
                compress = self.ui.prompt(self._txt("Ativar compressao SSH? (s/n): ", "Enable SSH compression? (y/n): ")).lower() in {"s", "y", "yes", "sim"}
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error(self._txt("Falha na validacao pre-instalacao: ", "Pre-install validation failed: ") + "; ".join(issues))
                    return
                self.power_tools.save_rollback_snapshot("squid")
                self.ui.show_spinner(self._txt(f"Instalando {service_name}", f"Installing {service_name}"))
                result = service.install(port, ip, compress)
            elif service_name == "SSLH":
                listen_port = self._ask_port(self._txt("Porta para SSLH (padrao 443): ", "SSLH port (default 443): "), 443)
                if listen_port is None:
                    return
                ok_port, listen_port = self._resolve_port_conflict(listen_port, service_name)
                if not ok_port:
                    return
                required_ports = [listen_port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error(self._txt("Falha na validacao pre-instalacao: ", "Pre-install validation failed: ") + "; ".join(issues))
                    return
                self.power_tools.save_rollback_snapshot("sslh")
                self.ui.show_spinner(self._txt(f"Instalando {service_name}", f"Installing {service_name}"))
                result = service.install(listen_port=listen_port)
            elif service_name == "STUNNEL":
                listen_port = self._ask_port(self._txt("Porta para STUNNEL (padrao 4433): ", "STUNNEL port (default 4433): "), 4433)
                if listen_port is None:
                    return
                ok_port, listen_port = self._resolve_port_conflict(listen_port, service_name)
                if not ok_port:
                    return
                required_ports = [listen_port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error(self._txt("Falha na validacao pre-instalacao: ", "Pre-install validation failed: ") + "; ".join(issues))
                    return
                self.power_tools.save_rollback_snapshot("stunnel")
                self.ui.show_spinner(self._txt(f"Instalando {service_name}", f"Installing {service_name}"))
                result = service.install(listen_port=listen_port)
            elif service_name == "DROPBEAR":
                port = self._ask_port(self._txt("Porta para DROPBEAR (padrao 2222): ", "DROPBEAR port (default 2222): "), 2222)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                required_ports = [port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error(self._txt("Falha na validacao pre-instalacao: ", "Pre-install validation failed: ") + "; ".join(issues))
                    return
                self.power_tools.save_rollback_snapshot("dropbear")
                self.ui.show_spinner(self._txt(f"Instalando {service_name}", f"Installing {service_name}"))
                result = service.install(port=port)
            elif service_name == "OPENVPN":
                port = self._ask_port(self._txt("Porta OpenVPN (padrao 1194): ", "OpenVPN port (default 1194): "), 1194)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                proto = self.ui.prompt(self._txt("Protocolo udp/tcp (padrao udp): ", "Protocol udp/tcp (default udp): ")).strip().lower() or "udp"
                client_name = self.ui.prompt(self._txt("Nome do cliente inicial (padrao client): ", "Initial client name (default client): ")).strip() or "client"
                with_host = self.ui.prompt(self._txt("Usar host/dominio? (s/n): ", "Use host/domain? (y/n): ")).strip().lower() in {"s", "y", "yes", "sim"}
                endpoint = self.ui.prompt(self._txt("Host/Dominio (vazio para IP): ", "Host/Domain (empty for IP): ")).strip() if with_host else ""
                required_ports = [port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error(self._txt("Falha na validacao pre-instalacao: ", "Pre-install validation failed: ") + "; ".join(issues))
                    return
                self.power_tools.save_rollback_snapshot("openvpn")
                self.ui.show_spinner(self._txt(f"Instalando {service_name}", f"Installing {service_name}"))
                result = service.install(
                    port=port,
                    protocol=proto,
                    endpoint=endpoint,
                    use_domain=with_host,
                    client_name=client_name,
                )
            elif service_name == "SHADOWSOCKS":
                port = self._ask_port(self._txt("Porta ShadowSocks (padrao 8388): ", "ShadowSocks port (default 8388): "), 8388)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                method = self.ui.prompt(self._txt("Metodo (padrao chacha20-ietf-poly1305): ", "Method (default chacha20-ietf-poly1305): ")).strip() or "chacha20-ietf-poly1305"
                password = self.ui.prompt(self._txt("Senha (vazio para auto): ", "Password (empty for auto): ")).strip()
                required_ports = [port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error(self._txt("Falha na validacao pre-instalacao: ", "Pre-install validation failed: ") + "; ".join(issues))
                    return
                self.ui.show_spinner(self._txt(f"Instalando {service_name}", f"Installing {service_name}"))
                result = service.install(port=port, password=password, method=method)
            elif service_name == "XRAY":
                mode = self.ui.prompt(self._txt("Modo (vless/vmess/trojan): ", "Mode (vless/vmess/trojan): ")).strip().lower() or "vless"
                port = self._ask_port(self._txt("Porta (padrao 443): ", "Port (default 443): "), 443)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                host = self.ui.prompt(self._txt("Host (opcional): ", "Host (optional): ")).strip()
                path = self.ui.prompt(self._txt("Path WS (padrao /rdy): ", "WS Path (default /rdy): ")).strip() or "/rdy"
                required_ports = [port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error(self._txt("Falha na validacao pre-instalacao: ", "Pre-install validation failed: ") + "; ".join(issues))
                    return
                self.ui.show_spinner(self._txt(f"Instalando {service_name}", f"Installing {service_name}"))
                result = service.install(mode=mode, port=port, host=host, path=path)
            elif service_name == "HYSTERIA":
                port = self._ask_port(self._txt("Porta Hysteria (padrao 443): ", "Hysteria port (default 443): "), 443)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                domain = self.ui.prompt(self._txt("Host/Dominio (vazio para sem host): ", "Host/Domain (empty for none): ")).strip()
                password = self.ui.prompt(self._txt("Senha (vazio para auto): ", "Password (empty for auto): ")).strip()
                required_ports = [port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error(self._txt("Falha na validacao pre-instalacao: ", "Pre-install validation failed: ") + "; ".join(issues))
                    return
                self.ui.show_spinner(self._txt(f"Instalando {service_name}", f"Installing {service_name}"))
                result = service.install(port=port, password=password, domain=domain)
            elif service_name == "DNSTT":
                domain = self.ui.prompt(self._txt("Dominio/subdominio DNSTT (ex: dns.seudominio.com): ", "DNSTT domain/subdomain (e.g., dns.example.com): ")).strip()
                udp_port = self._ask_port(self._txt("Porta UDP DNSTT (padrao 5300): ", "DNSTT UDP port (default 5300): "), 5300)
                if udp_port is None:
                    return
                ok_port, udp_port = self._resolve_port_conflict(udp_port, service_name)
                if not ok_port:
                    return
                secret = self.ui.prompt(self._txt("Secret (vazio para auto): ", "Secret (empty for auto): ")).strip()
                required_ports = [udp_port]
                ok, issues = self.power_tools.pre_install_validation(service_name, required_ports)
                if not ok:
                    self.ui.print_error(self._txt("Falha na validacao pre-instalacao: ", "Pre-install validation failed: ") + "; ".join(issues))
                    return
                self.ui.show_spinner(self._txt(f"Instalando {service_name}", f"Installing {service_name}"))
                result = service.install(domain=domain, udp_port=udp_port, secret=secret)
            elif service_name == "BADVPN":
                port = self._ask_port(self._txt("Porta para BADVPN (padrao 7300): ", "BADVPN port (default 7300): "), 7300)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                self.ui.show_spinner(self._txt(f"Instalando {service_name}", f"Installing {service_name}"))
                result = service.install(port=port)
            elif service_name == "TROJAN":
                password = self.ui.prompt(self._txt("Senha para Trojan: ", "Trojan password: "))
                port = self._ask_port(self._txt("Porta para Trojan (padrao 443): ", "Trojan port (default 443): "), 443)
                if port is None:
                    return
                ok_port, port = self._resolve_port_conflict(port, service_name)
                if not ok_port:
                    return
                self.ui.show_spinner(self._txt(f"Instalando {service_name}", f"Installing {service_name}"))
                result = service.install(password=password, port=port)
            else:
                result = f"{self.lang.t('service.unknown', 'Servico desconhecido')}: {service_name}"
        except ValueError:
            self.ui.print_error(self.lang.t("common.invalid_port_number", "Porta invalida. Digite um numero."))
            return

        if result is True:
            self.ui.print_success(f"{service_name} {self.lang.t('service.install_ok', 'instalado com sucesso!')}")
        else:
            self.ui.print_error(f"{self.lang.t('common.error_prefix', 'Erro:')} {result}")

    def openvpn_users_menu(self, openvpn_service):
        while True:
            self.ui.clear()
            clients = openvpn_service.list_clients()
            table = Table(
                title=f"[bold yellow]{self.lang.t('openvpn.users_title', 'USUARIOS OPENVPN')}[/bold yellow]",
                caption="[bold cyan]RDY SOFTWARE[/bold cyan]",
            )
            table.add_column(self.lang.t("openvpn.client_label", "Cliente"), style="cyan")
            if clients:
                for c in clients:
                    table.add_row(c)
            else:
                table.add_row(self.lang.t("openvpn.no_client", "(nenhum)"))
            self.ui.console.print(table)

            options = {
                "01": self.lang.t("openvpn.create_client", "CRIAR CLIENTE"),
                "02": self.lang.t("openvpn.revoke_client", "REVOGAR CLIENTE"),
                "00": self.lang.t("menu.back", "VOLTAR"),
            }
            self.ui.draw_menu(options, self.lang.t("openvpn.users_menu_title", "OPENVPN USERS"))
            option = self._normalize_option(self.ui.prompt())
            if option == "1":
                if not self._confirm("criacao de cliente openvpn"):
                    continue
                username = self.ui.prompt(self.lang.t("openvpn.client_name", "Nome do cliente: ")).strip()
                use_host = self.ui.prompt(self._txt("Usar host/dominio no cliente? (s/n): ", "Use host/domain in client? (y/n): ")).strip().lower() in {"s", "y", "yes", "sim"}
                endpoint = self.ui.prompt(self._txt("Host/Dominio (vazio para IP): ", "Host/Domain (empty for IP): ")).strip() if use_host else ""
                result = openvpn_service.add_client(username=username, endpoint=endpoint, use_domain=use_host)
                if isinstance(result, str) and ("criado" in result.lower() or "created" in result.lower()):
                    self.ui.print_success(result)
                else:
                    self.ui.print_error(f"{self.lang.t('common.error_prefix', 'Erro:')} {result}")
                time.sleep(2)
            elif option == "2":
                if not self._confirm("revogacao de cliente openvpn"):
                    continue
                username = self.ui.prompt(self.lang.t("openvpn.client_name_revoke", "Nome do cliente a revogar: ")).strip()
                result = openvpn_service.revoke_client(username)
                if result is True:
                    self.ui.print_success(self.lang.t("openvpn.client_revoked", "Cliente {username} revogado.").format(username=username))
                else:
                    self.ui.print_error(f"{self.lang.t('common.error_prefix', 'Erro:')} {result}")
                time.sleep(2)
            elif option == "00":
                break
            else:
                self.ui.print_error(self.lang.t("menu.invalid", "Opcao invalida!"))
                time.sleep(1)

    def tools_menu(self):
        while True:
            self.ui.clear()
            options = {
                "01": self.lang.t("tools.banner", "CRIAR/ALTERAR BANNER SSH"),
                "02": self.lang.t("tools.hosts", "GERENCIAR HOSTS (PAYLOADS)"),
                "03": self.lang.t("tools.cache", "LIMPAR CACHE E INODES"),
                "04": self.lang.t("tools.update_system", "ATUALIZAR SISTEMA"),
                "05": self.lang.t("tools.reboot", "REINICIAR SERVIDOR"),
                "06": self.lang.t("tools.full_uninstall", "DESINSTALACAO COMPLETA"),
                "07": self.lang.t("tools.update_script", "ATUALIZAR SCRIPT"),
                "08": self.lang.t("tools.global_cmd", "CRIAR COMANDO GLOBAL"),
                "09": self.lang.t("tools.swap", "CRIAR SWAP"),
                "10": self.lang.t("tools.speed", "TESTE DE VELOCIDADE"),
                "11": self.lang.t("tools.power", "POWER TOOLS"),
                "12": self.lang.t("tools.domain_audit", "DOMAIN AUDIT"),
                "00": self.lang.t("menu.back", "VOLTAR"),
            }
            self.ui.draw_menu(options, self.lang.t("tools.title", "FERRAMENTAS"))
            option = self._normalize_option(self.ui.prompt())

            if option == "1":
                if not self._confirm("alteracao do banner SSH"):
                    continue
                banner_text = self.ui.prompt(self._txt("Texto do Banner: ", "Banner text: "))
                BannerManager.set_banner(banner_text)
                self.ui.print_success(self.lang.t("tools.banner_updated", "Banner atualizado!"))
                time.sleep(2)
            elif option == "2":
                self.hosts_menu()
            elif option == "3":
                if not self._confirm("limpeza de cache e inodes"):
                    continue
                self.ui.show_spinner("Limpando cache")
                result = self.sys_actions.clear_cache()
                if result is True:
                    self.ui.print_success(self.lang.t("tools.cache_cleaned", "Cache limpo!"))
                else:
                    self.ui.print_error(self.lang.t("tools.cache_error", "Erro ao limpar cache: {error}").format(error=result))
                time.sleep(2)
            elif option == "4":
                if not self._confirm("atualizacao do sistema"):
                    continue
                self.ui.print_info(self.lang.t("tools.system_updating", "Iniciando atualizacao do sistema..."))
                commands = self.sys_actions.update_system()
                if not commands:
                    self.ui.print_error(self.lang.t("tools.pkg_not_found", "Nenhum gerenciador de pacotes suportado encontrado (apt/yum)."))
                    time.sleep(2)
                    continue
                for cmd in commands:
                    self.ui.print_info(self.lang.t("tools.running", "Executando: {cmd}").format(cmd=" ".join(cmd)))
                    subprocess.run(cmd, check=False)
                self.ui.print_success(self.lang.t("tools.system_updated", "Sistema atualizado!"))
                time.sleep(2)
            elif option == "5":
                if self._confirm("reinicio do servidor"):
                    self.sys_actions.reboot()
            elif option == "6":
                if self._confirm("DESINSTALACAO COMPLETA"):
                    self.ui.print_info(self.lang.t("tools.uninstall_running", "Executando desinstalacao completa..."))
                    uninstaller = CompleteUninstaller()
                    results = uninstaller.run()
                    summary = CompleteUninstaller.summarize(results)
                    self.ui.print_success(summary)
                    self.ui.print_info(self.lang.t("tools.check_logs", "Verifique os logs/servicos para confirmar os itens com falha."))
                    time.sleep(3)
            elif option == "7":
                if not self._confirm("atualizacao do script"):
                    continue
                self.ui.print_info(self.lang.t("tools.updating_git", "Atualizando script pelo git..."))
                ok, msg = self.sys_actions.update_script(self.repo_dir)
                if ok:
                    self.ui.print_success(msg)
                else:
                    self.ui.print_error(msg)
                time.sleep(2)
            elif option == "8":
                if not self._confirm("criacao de comando global"):
                    continue
                command_name = self.ui.prompt(self.lang.t("tools.command_name_prompt", "Nome do comando global (ex: menu): ")).strip()
                if not command_name:
                    self.ui.print_error(self.lang.t("tools.command_name_empty", "Nome do comando nao pode ser vazio."))
                    time.sleep(2)
                    continue
                self.ui.print_info(self.lang.t("tools.command_creating", "Criando comando global '{name}'...").format(name=command_name))
                ok, msg = self.sys_actions.create_menu_command(self.repo_dir, command_name)
                if ok:
                    self.ui.print_success(msg)
                else:
                    self.ui.print_error(msg)
                time.sleep(2)
            elif option == "9":
                if not self._confirm("criacao de swap"):
                    continue
                size_text = self.ui.prompt(self.lang.t("tools.swap_size_prompt", "Tamanho da SWAP em MB (padrao 1024): ")).strip()
                try:
                    size_mb = int(size_text) if size_text else 1024
                except ValueError:
                    self.ui.print_error(self.lang.t("tools.swap_size_invalid", "Valor invalido para tamanho da swap."))
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
                            f"[bold green]{self.lang.t('tools.speed_result_title', 'Resultado do teste')}[/bold green]\n\n"
                            f"[white]{self.lang.t('tools.speed_ping', 'Ping')}:[/white] [cyan]{data['ping_ms']} ms[/cyan]\n"
                            f"[white]{self.lang.t('tools.speed_download', 'Download')}:[/white] [cyan]{data['download_mbps']} Mbps[/cyan]\n"
                            f"[white]{self.lang.t('tools.speed_upload', 'Upload')}:[/white] [cyan]{data['upload_mbps']} Mbps[/cyan]\n"
                            f"[white]{self.lang.t('tools.speed_sample_dl', 'Amostra download')}:[/white] [cyan]{data['download_mb_tested']} MB[/cyan]\n"
                            f"[white]{self.lang.t('tools.speed_sample_ul', 'Amostra upload')}:[/white] [cyan]{data['upload_mb_tested']} MB[/cyan]",
                            title=self.lang.t("tools.speed_title", "VELOCIDADE"),
                            border_style="green",
                        )
                    )
                else:
                    self.ui.print_error(self.lang.t("tools.speed_failed", "Falha no teste: {error}").format(error=data))
                self.ui.prompt(self.lang.t("common.press_enter", "Pressione Enter para continuar..."))
            elif option == "11":
                self.power_tools_menu()
            elif option == "12":
                self.domain_audit_service_menu()
            elif option == "00":
                break
            else:
                self.ui.print_error(self.lang.t("menu.invalid", "Opcao invalida!"))
                time.sleep(2)

    def hosts_menu(self):
        while True:
            self.ui.clear()
            hosts = HostManager.list_hosts()
            self.ui.print_info(self.lang.t("tools.current_hosts", "Hosts atuais:"))
            for host in hosts:
                self.ui.console.print(f" - {host}")

            options = {
                "01": self.lang.t("hosts.add", "ADICIONAR HOST"),
                "02": self.lang.t("hosts.remove", "REMOVER HOST"),
                "00": self.lang.t("menu.back", "VOLTAR"),
            }
            self.ui.draw_menu(options, self.lang.t("hosts.title", "GERENCIAR HOSTS"))
            option = self._normalize_option(self.ui.prompt())

            if option == "1":
                if not self._confirm("adicao de host payload"):
                    continue
                host = self.ui.prompt(self._txt("Host a adicionar: ", "Host to add: "))
                HostManager.add_host(host)
                self.ui.print_success(self.lang.t("tools.host_added", "Host adicionado!"))
                time.sleep(2)
            elif option == "2":
                if not self._confirm("remocao de host payload"):
                    continue
                host = self.ui.prompt(self._txt("Host a remover: ", "Host to remove: "))
                HostManager.remove_host(host)
                self.ui.print_success(self.lang.t("tools.host_removed", "Host removido!"))
                time.sleep(2)
            elif option == "00":
                break
            else:
                self.ui.print_error(self.lang.t("menu.invalid", "Opcao invalida!"))
                time.sleep(2)

    def about(self):
        self.ui.clear()
        self.ui.console.print(
            Panel(
                "[bold yellow]VPS TOOLS [red]PYTHON VERSION[/bold yellow]\n\n"
                f"[green]{self._txt('Baseado no script original da RDY SOFTWARE.', 'Based on the original RDY SOFTWARE script.')}\n"
                f"[blue]{self._txt('Reescrito em Python para melhor performance e estabilidade.', 'Rewritten in Python for better performance and stability.')}\n\n"
                "[cyan]Telegram: @rdysoftware",
                title=self.lang.t("about.title", "SOBRE"),
                border_style="green",
            )
        )
        self.ui.prompt(self.lang.t("common.press_any_back", "Pressione qualquer tecla para voltar..."))

    def pre_install_check_menu(self):
        service_name = self.ui.prompt(self.lang.t("precheck.service_prompt", "Servico para validar (SQUID/SSLH/STUNNEL/DROPBEAR): ")).strip().lower()
        ports_raw = self.ui.prompt(self.lang.t("precheck.ports_prompt", "Portas separadas por virgula (ex: 80,443): ")).strip()
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
            self.ui.print_success(self.lang.t("precheck.ok", "Validacao pre-instalacao OK."))
        else:
            self.ui.print_error(self.lang.t("precheck.fail", "Falhas encontradas: {issues}").format(issues="; ".join(issues)))
        time.sleep(2)

    def power_tools_menu(self):
        while True:
            self.ui.clear()
            options = {
                "01": self.lang.t("power.port_changer", "PORT CHANGER"),
                "02": self.lang.t("power.dashboard", "STATUS DASHBOARD"),
                "03": self.lang.t("power.logs", "LOGS VIEWER"),
                "04": self.lang.t("power.backup_restore", "BACKUP/RESTORE CONFIG"),
                "05": self.lang.t("power.firewall", "FIREWALL MANAGER"),
                "06": self.lang.t("power.health", "HEALTH CHECK"),
                "07": self.lang.t("power.rollback", "ROLLBACK"),
                "08": self.lang.t("power.wizard", "SETUP WIZARD"),
                "09": self.lang.t("power.language", "IDIOMA / LANGUAGE"),
                "00": self.lang.t("menu.back", "VOLTAR"),
            }
            self.ui.draw_menu(options, self.lang.t("power.title", "POWER TOOLS"))
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
                self.ui.print_error(self.lang.t("menu.invalid", "Opcao invalida!"))
                time.sleep(1)

    def port_changer_menu(self):
        if not self._confirm("alteracao de portas"):
            return
        service = self.ui.prompt(self.lang.t("port_changer.service_prompt", "Servico (ssh/dropbear/squid/stunnel/sslh): ")).strip().lower()
        try:
            port = int(self.ui.prompt(self.lang.t("port_changer.new_port", "Nova porta: ")).strip())
        except ValueError:
            self.ui.print_error(self.lang.t("common.invalid_port", "Porta invalida."))
            time.sleep(1)
            return
        ok, msg = self.power_tools.change_port(service, port)
        if ok:
            self.ui.print_success(msg)
        else:
            self.ui.print_error(msg)
        time.sleep(2)

    def dashboard_menu(self):
        duration_raw = self.ui.prompt(self._txt("Duracao do dashboard em segundos (padrao 20): ", "Dashboard duration in seconds (default 20): ")).strip()
        interval_raw = self.ui.prompt(self._txt("Intervalo de atualizacao em segundos (padrao 1.5): ", "Refresh interval in seconds (default 1.5): ")).strip()
        try:
            duration = int(duration_raw) if duration_raw else 20
        except ValueError:
            duration = 20
        try:
            interval = float(interval_raw) if interval_raw else 1.5
        except ValueError:
            interval = 1.5
        duration = max(5, duration)
        interval = max(0.5, interval)

        def render_frame():
            data = self.power_tools.dashboard_snapshot()
            status = self.power_tools.service_status_map(
                ["ssh", "dropbear", "squid", "sslh", "stunnel4", "trojan", "openvpn", "xray"]
            )

            table = Table(
                title=f"[bold yellow]{self.lang.t('dashboard.title', 'STATUS DASHBOARD')}[/bold yellow]",
                caption="[bold cyan]RDY SOFTWARE[/bold cyan]",
            )
            table.add_column(self.lang.t("dashboard.item", "Item"), style="cyan")
            table.add_column(self.lang.t("dashboard.value", "Valor"), style="white")
            table.add_row(self.lang.t("dashboard.cpu", "CPU"), f"{data['cpu_percent']}%")
            table.add_row(self.lang.t("dashboard.ram", "RAM"), f"{data['mem_percent']}%")
            table.add_row(self.lang.t("dashboard.swap", "SWAP"), f"{data['swap_percent']}%")
            table.add_row(self.lang.t("dashboard.disk", "DISCO"), f"{data['disk_percent']}%")
            table.add_row(self.lang.t("dashboard.net_sent", "NET ENVIADO"), f"{data['net_sent_mb']} MB")
            table.add_row(self.lang.t("dashboard.net_recv", "NET RECEBIDO"), f"{data['net_recv_mb']} MB")
            table.add_row(self.lang.t("dashboard.sessions", "SESSOES"), str(data["sessions"]))

            st = Table(
                title=f"[bold yellow]{self.lang.t('dashboard.services', 'SERVICOS')}[/bold yellow]",
                caption="[bold cyan]RDY SOFTWARE[/bold cyan]",
            )
            st.add_column(self.lang.t("dashboard.service_col", "Servico"), style="cyan")
            st.add_column("Status", style="white")
            for name, value in status.items():
                st.add_row(name, value)
            return Group(table, st)

        started = time.time()
        with Live(render_frame(), console=self.ui.console, refresh_per_second=4, screen=False) as live:
            while (time.time() - started) < duration:
                time.sleep(interval)
                live.update(render_frame())
        self.ui.prompt(self.lang.t("common.enter_back", "Enter para voltar..."))

    def logs_viewer_menu(self):
        service = self.ui.prompt(self.lang.t("logs.service_prompt", "Servico para logs (ex: squid): ")).strip()
        lines_raw = self.ui.prompt(self.lang.t("logs.lines_prompt", "Qtd linhas (padrao 80): ")).strip()
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
            Panel(logs[-6000:], title=self.lang.t("logs.title", "LOGS: {service}").format(service=service), border_style="blue")
        )
        if self._confirm(self.lang.t("logs.save_confirm", "salvar logs em arquivo")):
            path = self.ui.prompt(self.lang.t("logs.path_prompt", "Caminho do arquivo: ")).strip()
            try:
                with open(path, "w") as f:
                    f.write(logs)
                self.ui.print_success(self.lang.t("logs.saved", "Logs salvos em {path}").format(path=path))
            except Exception as exc:
                self.ui.print_error(str(exc))
        self.ui.prompt(self.lang.t("common.enter_back", "Enter para voltar..."))

    def config_backup_restore_menu(self):
        option = self._normalize_option(self.ui.prompt(self.lang.t("backup.menu_prompt", "1 Backup / 2 Restore: ")))
        if option == "1":
            if not self._confirm("backup de configuracoes"):
                return
            name = self.ui.prompt(self.lang.t("backup.name_prompt", "Nome do backup: ")).strip() or "backup"
            ok, msg = self.power_tools.backup_configs(name)
            if ok:
                self.ui.print_success(self.lang.t("backup.created", "Backup criado: {msg}").format(msg=msg))
            else:
                self.ui.print_error(msg)
        elif option == "2":
            if not self._confirm("restore de configuracoes"):
                return
            path = self.ui.prompt(self.lang.t("backup.path_prompt", "Caminho do backup .tar.gz: ")).strip()
            ok, msg = self.power_tools.restore_configs(path)
            if ok:
                self.ui.print_success(msg)
            else:
                self.ui.print_error(msg)
        else:
            self.ui.print_error(self.lang.t("menu.invalid", "Opcao invalida!"))
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
        table.add_column(self._txt("Check", "Check"), style="cyan")
        table.add_column(self._txt("Resultado", "Result"), style="white")
        for k, v in report.items():
            table.add_row(k, v)
        self.ui.console.print(table)
        self.ui.prompt(self.lang.t("common.enter_back", "Enter para voltar..."))

    def rollback_menu(self):
        option = self._normalize_option(self.ui.prompt(self.lang.t("rollback.menu_prompt", "1 Criar snapshot / 2 Restaurar: ")))
        if option == "1":
            if not self._confirm("snapshot de rollback"):
                return
            service = self.ui.prompt(self.lang.t("rollback.service_prompt", "Servico (ssh/dropbear/squid/sslh/stunnel): ")).strip().lower()
            ok, msg = self.power_tools.save_rollback_snapshot(service)
            if ok:
                self.ui.print_success(self.lang.t("rollback.saved", "Snapshot salvo: {msg}").format(msg=msg))
            else:
                self.ui.print_error(msg)
        elif option == "2":
            if not self._confirm("restaurar rollback"):
                return
            service = self.ui.prompt(self.lang.t("rollback.service_prompt", "Servico (ssh/dropbear/squid/sslh/stunnel): ")).strip().lower()
            snaps = self.power_tools.list_rollbacks(service)
            if not snaps:
                self.ui.print_error(self.lang.t("rollback.none", "Nenhum snapshot encontrado."))
                time.sleep(2)
                return
            self.ui.console.print(Panel("\n".join(snaps), title=self.lang.t("rollback.snapshots", "Snapshots")))
            path = self.ui.prompt(self.lang.t("rollback.path_prompt", "Informe o caminho exato do snapshot: ")).strip()
            ok, msg = self.power_tools.restore_rollback(path)
            if ok:
                self.ui.print_success(msg)
            else:
                self.ui.print_error(msg)
        else:
            self.ui.print_error(self.lang.t("menu.invalid", "Opcao invalida!"))
        time.sleep(2)

    def setup_wizard_menu(self):
        if not self._confirm("executar setup wizard"):
            return
        self.ui.print_info(self.lang.t("wizard.step1", "1) Atualizacao do script"))
        ok, msg = self.sys_actions.update_script(self.repo_dir)
        self.ui.print_success(msg) if ok else self.ui.print_error(msg)

        self.ui.print_info(self.lang.t("wizard.step2", "2) Validacao pre-instalacao"))
        valid, issues = self.power_tools.pre_install_validation("wizard", [22, 80, 443])
        if not valid:
            self.ui.print_error(self.lang.t("wizard.pending", "Pendencias: {issues}").format(issues="; ".join(issues)))
        else:
            self.ui.print_success(self.lang.t("wizard.ok", "Validacao OK"))

        if self._confirm("criar swap 1024 MB"):
            ok, msg = self.sys_actions.create_swap(1024)
            self.ui.print_success(msg) if ok else self.ui.print_error(msg)

        if self._confirm("criar comando global 'menu'"):
            ok, msg = self.sys_actions.create_menu_command(self.repo_dir, "menu")
            self.ui.print_success(msg) if ok else self.ui.print_error(msg)
        self.ui.prompt(self.lang.t("wizard.done", "Setup finalizado. Enter para voltar..."))

    def language_menu(self):
        option = self.ui.prompt(self.lang.t("language.prompt", "Idioma (pt/en): ")).strip().lower()
        if self.lang.set_language(option):
            self.ui.set_language(option)
            self.ui.print_success(self.lang.t("lang.changed", "Idioma alterado com sucesso."))
        else:
            self.ui.print_error(self.lang.t("lang.invalid", "Idioma invalido."))
        time.sleep(1)

    def domain_audit_service_menu(self):
        if not self._confirm("execucao de domain audit"):
            return
        service = self.services["DOMAIN_AUDIT"]
        domain = self.ui.prompt(self.lang.t("domain.target_prompt", "Dominio alvo (ex: exemplo.com): ")).strip()
        if not domain:
            self.ui.print_error(self.lang.t("common.invalid_domain", "Dominio invalido."))
            time.sleep(1)
            return

        ports = self.ui.prompt(self.lang.t("domain.ports_prompt", "Portas TLS (padrao 443): ")).strip() or "443"
        check_ssl = self.ui.prompt(self.lang.t("domain.ssl_prompt", "Checar SSL/TLS? (s/n): ")).strip().lower() in {"s", "y", "yes", "sim"}
        output = self.ui.prompt(self.lang.t("domain.output_prompt", "Arquivo de saida (ex: audit.csv|audit.json): ")).strip() or "domain_audit.csv"

        self.ui.print_info(self.lang.t("domain.run", "Executando domain audit..."))
        ok, msg = service.run_audit(
            domain=domain,
            ports=ports,
            check_ssl=check_ssl,
            output=output,
        )
        if ok:
            self.ui.print_success(msg)
        else:
            self.ui.print_error(self.lang.t("domain.failed", "Domain audit falhou: {msg}").format(msg=msg))
        self.ui.prompt(self.lang.t("common.press_enter_back", "Pressione Enter para voltar..."))


if __name__ == "__main__":
    app = VPSToolsApp()
    app.main_menu()
