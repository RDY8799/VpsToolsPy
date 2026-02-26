import os
import shutil
import subprocess

from vps_tools.core.services import Service


class OpenClawService(Service):
    def __init__(self):
        super().__init__("OpenClaw", "openclaw")
        self.installer_cmd = "curl -fsSL https://openclaw.ai/install.sh | bash"
        self.unit_candidates = [
            "openclaw",
            "openclawd",
            "openclaw-ai",
        ]
        self.binary_candidates = [
            "/usr/local/bin/openclaw",
            "/usr/bin/openclaw",
            "/opt/openclaw/openclaw",
        ]

    def _unit_exists(self, unit_name: str) -> bool:
        result = subprocess.run(
            ["systemctl", "show", "-p", "LoadState", "--value", unit_name],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False
        return result.stdout.strip() not in {"", "not-found"}

    def _existing_units(self):
        return [u for u in self.unit_candidates if self._unit_exists(u)]

    def is_installed(self) -> bool:
        if shutil.which("openclaw"):
            return True
        for path in self.binary_candidates:
            if os.path.exists(path):
                return True
        return len(self._existing_units()) > 0

    def is_running(self) -> bool:
        for unit in self._existing_units():
            result = subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip() == "active":
                return True

        p = subprocess.run(["pgrep", "-f", "openclaw"], capture_output=True, check=False)
        return p.returncode == 0

    def _service_action(self, action: str) -> bool:
        ok = False
        for unit in self._existing_units():
            if subprocess.run(["systemctl", action, unit], check=False).returncode == 0:
                ok = True
        if ok:
            return True

        # fallback
        for unit in self.unit_candidates:
            if subprocess.run(["service", unit, action], check=False).returncode == 0:
                return True
        return False

    def install(self):
        result = subprocess.run(
            ["bash", "-lc", self.installer_cmd],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and self.is_installed():
            return True
        return (result.stderr or result.stdout or "Falha ao instalar OpenClaw.").strip()

    def update(self):
        result = subprocess.run(
            ["bash", "-lc", self.installer_cmd],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return True, (result.stdout.strip() or "OpenClaw atualizado.")
        return False, (result.stderr.strip() or result.stdout.strip() or "Falha ao atualizar OpenClaw.")

    def uninstall(self):
        # Tentativas suportadas por diferentes builds/scripts
        attempts = [
            ["openclaw", "uninstall", "-y"],
            ["openclaw", "remove", "-y"],
            ["bash", "-lc", "curl -fsSL https://openclaw.ai/install.sh | bash -s -- --uninstall"],
        ]
        for cmd in attempts:
            subprocess.run(cmd, check=False, capture_output=True, text=True)

        self.stop()

        # Limpeza de restos comuns
        for path in [
            "/usr/local/bin/openclaw",
            "/usr/bin/openclaw",
            "/opt/openclaw",
            "/etc/openclaw",
            "/var/lib/openclaw",
            "/var/log/openclaw",
        ]:
            if os.path.isdir(path):
                subprocess.run(["rm", "-rf", path], check=False)
            elif os.path.isfile(path):
                subprocess.run(["rm", "-f", path], check=False)

        for unit in self.unit_candidates:
            subprocess.run(["systemctl", "disable", "--now", unit], check=False)
            unit_file = f"/etc/systemd/system/{unit}.service"
            if os.path.exists(unit_file):
                subprocess.run(["rm", "-f", unit_file], check=False)
        subprocess.run(["systemctl", "daemon-reload"], check=False)

        return not self.is_installed()

    def get_version(self) -> str:
        if not shutil.which("openclaw"):
            return "not installed"
        try:
            result = subprocess.run(
                ["openclaw", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return "not installed"
        if result.returncode == 0:
            return (result.stdout or result.stderr).strip() or "unknown"
        return "unknown"

    def get_status_info(self):
        units = self._existing_units()
        return {
            "installed": self.is_installed(),
            "running": self.is_running(),
            "version": self.get_version(),
            "units": ", ".join(units) if units else "-",
        }

    def read_logs(self, lines: int = 120):
        for unit in self._existing_units():
            out = subprocess.run(
                ["journalctl", "-u", unit, "-n", str(lines), "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            if out.returncode == 0 and out.stdout.strip():
                return True, out.stdout
        return False, "Nenhum log encontrado para OpenClaw."
