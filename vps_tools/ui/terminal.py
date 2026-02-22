import os
import sys
import time
try:
    import termios
    import tty
except ImportError:
    termios = None
    tty = None

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
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
            caption="[bold cyan]RDY SOFTWARE[/bold cyan]",
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

    def run_animated_task(self, title, worker):
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task_id = progress.add_task(f"[cyan]{title}[/cyan]", total=100)

            def update(completed=None, description=None):
                kwargs = {}
                if completed is not None:
                    kwargs["completed"] = max(0, min(100, completed))
                if description:
                    kwargs["description"] = description
                if kwargs:
                    progress.update(task_id, **kwargs)

            result = worker(update)
            progress.update(task_id, completed=100, description="[green]Concluido[/green]")
            return result

    def draw_user_table(self, users):
        table = Table(
            title="[bold blue]GERENCIAMENTO DE USUARIOS[/bold blue]",
            caption="[bold cyan]RDY SOFTWARE[/bold cyan]",
            box=box.HEAVY_EDGE,
        )
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

    def _read_key_posix(self):
        if termios is None or tty is None:
            return "ENTER"
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                ch3 = sys.stdin.read(1)
                if ch2 == "[" and ch3 == "A":
                    return "UP"
                if ch2 == "[" and ch3 == "B":
                    return "DOWN"
                return "ESC"
            if ch in ("\r", "\n"):
                return "ENTER"
            if ch in ("\x7f", "\b"):
                return "BACKSPACE"
            if ch == "\x03":
                return "CTRL_C"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def select_user(self, users, action_label="acao"):
        usernames = [u["username"] if isinstance(u, dict) else str(u) for u in users]
        if not usernames:
            self.print_error("Nenhum usuario disponivel.")
            return None

        if os.name == "nt" or (not sys.stdin.isatty()):
            return self.prompt(f"Usuario para {action_label}: ").strip()

        index = 0
        typed_name = ""
        while True:
            self.clear()
            table = Table(
                title=f"[bold yellow]SELECIONAR USUARIO ({action_label})[/bold yellow]",
                caption="[bold cyan]Use setas + Enter, ou digite o nome manualmente[/bold cyan]",
                show_header=False,
                box=box.ROUNDED,
                expand=True,
            )
            table.add_column("Pick", style="cyan", width=6)
            table.add_column("Usuario", style="white")

            start = max(0, index - 8)
            end = min(len(usernames), start + 16)
            for i in range(start, end):
                marker = ">>" if i == index else "  "
                table.add_row(marker, usernames[i])
            self.console.print(table)

            self.console.print(
                f"[yellow]Digitado:[/yellow] [white]{typed_name or '(vazio)'}[/white]  "
                "[blue]|[/blue] [yellow]ESC:[/yellow] cancelar"
            )

            key = self._read_key_posix()
            if key == "CTRL_C":
                raise KeyboardInterrupt
            if key == "UP":
                index = (index - 1) % len(usernames)
                continue
            if key == "DOWN":
                index = (index + 1) % len(usernames)
                continue
            if key == "BACKSPACE":
                typed_name = typed_name[:-1]
                continue
            if key == "ESC":
                return None
            if key == "ENTER":
                return typed_name.strip() or usernames[index]
            if len(key) == 1 and key.isprintable():
                typed_name += key
