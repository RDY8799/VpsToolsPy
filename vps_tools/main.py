import os
import subprocess
import sys
import time

from rich.panel import Panel

from vps_tools.core.system import SystemActions, SystemInfo
from vps_tools.core.uninstaller import CompleteUninstaller
from vps_tools.core.users import UserManager
from vps_tools.core.utils import BannerManager, HostManager
from vps_tools.services.badvpn import BadVPNService
from vps_tools.services.dropbear import DropbearService
from vps_tools.services.squid import SquidService
from vps_tools.services.sslh import SSLHService
from vps_tools.services.stunnel import StunnelService
from vps_tools.services.trojan import TrojanService
from vps_tools.ui.terminal import TerminalUI


class VPSToolsApp:
    def __init__(self):
        self.ui = TerminalUI()
        self.sys_info = SystemInfo()
        self.sys_actions = SystemActions()
        self.user_manager = UserManager()
        self.services = {
            "SQUID": SquidService(),
            "SSLH": SSLHService(),
            "STUNNEL": StunnelService(),
            "DROPBEAR": DropbearService(),
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
                "01": "INSTALADOR/CONFIGURAR SERVICOS",
                "02": "GERENCIAMENTO DE USUARIOS",
                "03": "FERRAMENTAS DO SISTEMA",
                "04": "SOBRE",
                "00": "SAIR",
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
                username = self.ui.prompt("Nome do usuario a deletar: ")
                result = self.user_manager.delete_user(username)
                if result is True:
                    self.ui.print_success(f"Usuario {username} deletado!")
                else:
                    self.ui.print_error(f"Erro: {result}")
                time.sleep(2)

            elif option == "3":
                username = self.ui.prompt("Nome do usuario: ")
                new_limit = self.ui.prompt("Novo limite de logins: ")
                result = self.user_manager.change_limit(username, new_limit)
                if result is True:
                    self.ui.print_success(f"Limite de {username} atualizado!")
                else:
                    self.ui.print_error(f"Erro: {result}")
                time.sleep(2)

            elif option == "4":
                username = self.ui.prompt("Nome do usuario: ")
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
                username = self.ui.prompt("Nome do usuario: ")
                new_password = self.ui.prompt("Nova senha: ")
                result = self.user_manager.change_password(username, new_password)
                if result is True:
                    self.ui.print_success(f"Senha de {username} alterada!")
                else:
                    self.ui.print_error(f"Erro: {result}")
                time.sleep(2)

            elif option == "6":
                username = self.ui.prompt("Nome do usuario: ")
                if self.user_manager.disconnect_user(username):
                    self.ui.print_success(f"Usuario {username} desconectado!")
                else:
                    self.ui.print_error(f"Nao foi possivel desconectar {username}.")
                time.sleep(2)

            elif option == "7":
                name = self.ui.prompt("Nome para o arquivo de backup: ")
                path = self.user_manager.backup_users(name)
                if isinstance(path, str) and path.startswith("Erro"):
                    self.ui.print_error(path)
                else:
                    self.ui.print_success(f"Backup criado em: {path}")
                time.sleep(2)

            elif option == "8":
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

            options["00"] = "VOLTAR"
            self.ui.draw_menu(options, "MENU DE INSTALACAO")

            option = self._normalize_option(self.ui.prompt())
            if option == "00":
                break

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

            self.ui.draw_menu(options, f"{service_name} ({status})")
            option = self._normalize_option(self.ui.prompt())

            if option == "1":
                if not is_installed:
                    self.install_service_flow(service_name)
                else:
                    if is_running:
                        service.stop()
                        self.ui.print_success("Servico parado!")
                    else:
                        service.start()
                        self.ui.print_success("Servico iniciado!")
                time.sleep(2)
            elif option == "2" and is_installed:
                service.restart()
                self.ui.print_success("Servico reiniciado!")
                time.sleep(2)
            elif option == "3" and is_installed:
                service.uninstall()
                self.ui.print_success("Servico desinstalado!")
                time.sleep(2)
                break
            elif option == "00":
                break
            else:
                self.ui.print_error("Opcao invalida!")
                time.sleep(2)

    def install_service_flow(self, service_name):
        service = self.services[service_name]
        ip = self.ui.prompt("Confirme o IP: ")

        try:
            if service_name == "SQUID":
                port = self.ui.prompt("Porta para Squid (padrao 3128): ")
                port = int(port) if port else 3128
                compress = self.ui.prompt("Ativar compressao SSH? (s/n): ").lower() == "s"
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(port, ip, compress)
            elif service_name == "SSLH":
                listen_port = int(self.ui.prompt("Porta para SSLH (padrao 443): ") or 443)
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(listen_port=listen_port)
            elif service_name == "STUNNEL":
                listen_port = int(self.ui.prompt("Porta para STUNNEL (padrao 4433): ") or 4433)
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(listen_port=listen_port)
            elif service_name == "DROPBEAR":
                port = int(self.ui.prompt("Porta para DROPBEAR (padrao 2222): ") or 2222)
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(port=port)
            elif service_name == "BADVPN":
                port = int(self.ui.prompt("Porta para BADVPN (padrao 7300): ") or 7300)
                self.ui.show_spinner(f"Instalando {service_name}")
                result = service.install(port=port)
            elif service_name == "TROJAN":
                password = self.ui.prompt("Senha para Trojan: ")
                port = int(self.ui.prompt("Porta para Trojan (padrao 443): ") or 443)
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
                "08": "CRIAR COMANDO 'menu'",
                "00": "VOLTAR",
            }
            self.ui.draw_menu(options, "FERRAMENTAS")
            option = self._normalize_option(self.ui.prompt())

            if option == "1":
                banner_text = self.ui.prompt("Texto do Banner: ")
                BannerManager.set_banner(banner_text)
                self.ui.print_success("Banner atualizado!")
                time.sleep(2)
            elif option == "2":
                self.hosts_menu()
            elif option == "3":
                self.ui.show_spinner("Limpando cache")
                result = self.sys_actions.clear_cache()
                if result is True:
                    self.ui.print_success("Cache limpo!")
                else:
                    self.ui.print_error(f"Erro ao limpar cache: {result}")
                time.sleep(2)
            elif option == "4":
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
                confirm = self.ui.prompt("Tem certeza que deseja reiniciar? (s/n): ").lower()
                if confirm == "s":
                    self.sys_actions.reboot()
            elif option == "6":
                confirm = self.ui.prompt("Confirma DESINSTALACAO COMPLETA? (s/n): ").lower()
                if confirm == "s":
                    self.ui.print_info("Executando desinstalacao completa...")
                    uninstaller = CompleteUninstaller()
                    results = uninstaller.run()
                    summary = CompleteUninstaller.summarize(results)
                    self.ui.print_success(summary)
                    self.ui.print_info("Verifique os logs/servicos para confirmar os itens com falha.")
                    time.sleep(3)
            elif option == "7":
                self.ui.print_info("Atualizando script pelo git...")
                ok, msg = self.sys_actions.update_script(self.repo_dir)
                if ok:
                    self.ui.print_success(msg)
                else:
                    self.ui.print_error(msg)
                time.sleep(2)
            elif option == "8":
                self.ui.print_info("Criando comando global 'menu'...")
                ok, msg = self.sys_actions.create_menu_command(self.repo_dir, "menu")
                if ok:
                    self.ui.print_success(msg)
                else:
                    self.ui.print_error(msg)
                time.sleep(2)
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
                host = self.ui.prompt("Host a adicionar: ")
                HostManager.add_host(host)
                self.ui.print_success("Host adicionado!")
                time.sleep(2)
            elif option == "2":
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


if __name__ == "__main__":
    app = VPSToolsApp()
    app.main_menu()
