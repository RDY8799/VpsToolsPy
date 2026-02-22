import time

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class TerminalUI:
    def __init__(self):
        self.console = Console()

    def clear(self):
        self.console.clear()

    def draw_header(self, system_info, cpu, ram, swap, ip, os_info, user="root"):
        header = Table.grid(expand=True)
        header.add_column(justify="center", ratio=1)
        header.add_row(
            Panel(
                Text.from_markup(
                    f"[yellow]CPU USADA: [cyan]{cpu}% [blue]| [yellow]RAM USADA: [cyan]{ram['used']}MB "
                    f"[yellow]LIVRE: [cyan]{ram['free']}MB [blue]| [yellow]SWAP: [cyan]{swap['used']}MB\n"
                    f"[green]##### [white]IP: [cyan]{ip} [blue]| [white]SISTEMA: [cyan]{os_info} "
                    f"[blue]| [white]USUARIO: [cyan]{user}"
                ),
                title="[bold blue]VPS TOOLS [red]v2.0[/bold blue]",
                border_style="blue",
                box=box.DOUBLE,
            )
        )
        self.console.print(header)

    def draw_menu(self, options, title="MENU PRINCIPAL"):
        table = Table(
            title=f"[bold yellow]{title}[/bold yellow]",
            show_header=False,
            box=box.ROUNDED,
            expand=True,
        )
        table.add_column("Option", style="cyan", justify="right", width=5)
        table.add_column("Description", style="white")

        for key, description in options.items():
            table.add_row(f"[{key}]", description)

        self.console.print(table)

    def prompt(self, message="Escolha uma opcao: "):
        return self.console.input(f"[bold yellow]{message}[/bold yellow]")

    def print_success(self, message):
        self.console.print(f"[bold green][OK] {message}[/bold green]")

    def print_error(self, message):
        self.console.print(f"[bold red][ERRO] {message}[/bold red]")

    def print_info(self, message):
        self.console.print(f"[bold blue][INFO] {message}[/bold blue]")

    def show_spinner(self, message, duration=2):
        with self.console.status(f"[bold magenta]{message}...[/bold magenta]", spinner="dots"):
            time.sleep(duration)

    def draw_user_table(self, users):
        table = Table(title="[bold blue]GERENCIAMENTO DE USUARIOS[/bold blue]", box=box.HEAVY_EDGE)
        table.add_column("USUARIO", style="green")
        table.add_column("SENHA", style="magenta")
        table.add_column("EXPIRA EM", style="blue")
        table.add_column("LOGINS", style="yellow")
        table.add_column("CONECTADO", style="cyan")

        for user in users:
            table.add_row(
                user["username"],
                user["password"],
                user["expiry"],
                str(user["limit"]),
                str(user["connected"]),
            )
        self.console.print(table)
