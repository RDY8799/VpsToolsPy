import os
import re
import secrets
import string
import subprocess

from vps_tools.core.services import Service


class VNCService(Service):
    def __init__(self):
        super().__init__("VNC", "vps-tools-vnc")
        self.service_name = "vps-tools-vnc"
        self.service_path = f"/etc/systemd/system/{self.service_name}.service"
        self.pass_file = "/etc/vps-tools/vnc.pass"
        self.session_script = "/usr/local/bin/vps-vnc-session.sh"

    @staticmethod
    def _random_password(length: int = 10) -> str:
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(length))

    def is_installed(self) -> bool:
        has_bin = subprocess.run(["which", "x11vnc"], capture_output=True, check=False).returncode == 0
        return has_bin and os.path.exists(self.service_path) and os.path.exists(self.pass_file) and os.path.exists(self.session_script)

    def _install_packages(self):
        if os.path.exists("/etc/debian_version"):
            subprocess.run(["apt-get", "update", "-y"], check=True)
            subprocess.run(
                [
                    "apt-get",
                    "install",
                    "-y",
                    "x11vnc",
                    "xfce4",
                    "xfce4-goodies",
                    "xorg",
                    "dbus-x11",
                    "xterm",
                ],
                check=True,
            )
        else:
            subprocess.run(["yum", "-y", "install", "epel-release"], check=False)
            # Tenta perfil XFCE completo; se falhar, tenta pacotes comuns.
            group_try = subprocess.run(["yum", "-y", "groupinstall", "Xfce"], check=False)
            if group_try.returncode != 0:
                subprocess.run(
                    [
                        "yum",
                        "-y",
                        "install",
                        "x11vnc",
                        "xfce4-session",
                        "xfce4-panel",
                        "thunar",
                        "xorg-x11-server-Xorg",
                        "xorg-x11-xinit",
                        "dbus-x11",
                        "xterm",
                    ],
                    check=True,
                )
            else:
                subprocess.run(["yum", "-y", "install", "x11vnc", "xorg-x11-server-Xorg", "dbus-x11", "xterm"], check=True)

    def _write_session_script(self):
        content = """#!/usr/bin/env bash
set -e
if command -v startxfce4 >/dev/null 2>&1; then
  exec dbus-launch --exit-with-session startxfce4
fi
if command -v startlxde >/dev/null 2>&1; then
  exec dbus-launch --exit-with-session startlxde
fi
exec xterm
"""
        with open(self.session_script, "w") as f:
            f.write(content)
        subprocess.run(["chmod", "+x", self.session_script], check=False)

    def _write_service(self, port: int):
        content = f"""[Unit]
Description=VPS Tools VNC (x11vnc)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/x11vnc -create -forever -shared -noxdamage -rfbauth {self.pass_file} -rfbport {port}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
"""
        # usa script de sessao para garantir desktop pronto (XFCE/LXDE fallback)
        content = content.replace(
            "ExecStart=/usr/bin/x11vnc -create -forever -shared -noxdamage -rfbauth "
            f"{self.pass_file} -rfbport {port}",
            "ExecStart=/usr/bin/x11vnc -create -forever -shared -noxdamage "
            f"-rfbauth {self.pass_file} -rfbport {port} -xstartup {self.session_script}",
        )
        with open(self.service_path, "w") as f:
            f.write(content)

    def get_port(self) -> int:
        if not os.path.exists(self.service_path):
            return 5901
        try:
            with open(self.service_path, "r") as f:
                content = f.read()
            m = re.search(r"-rfbport\s+(\d+)", content)
            if m:
                return int(m.group(1))
        except Exception:
            pass
        return 5901

    def set_password(self, password: str):
        password = (password or "").strip()
        if not password:
            return False, "Senha invalida."
        os.makedirs("/etc/vps-tools", exist_ok=True)
        cmd = ["x11vnc", "-storepasswd", password, self.pass_file]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return False, (result.stderr or result.stdout or "Falha ao definir senha VNC.").strip()
        subprocess.run(["chmod", "600", self.pass_file], check=False)
        return True, "Senha VNC atualizada."

    def set_port(self, port: int):
        if not (1 <= int(port) <= 65535):
            return False, "Porta invalida."
        self._write_service(int(port))
        subprocess.run(["systemctl", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "restart", self.service_name], check=False)
        return True, f"Porta VNC alterada para {port}."

    def install(self, port: int = 5901, password: str = ""):
        try:
            if not password:
                password = self._random_password()
            self._install_packages()
            self._write_session_script()
            ok, msg = self.set_password(password)
            if not ok:
                return msg
            self._write_service(port)
            subprocess.run(["systemctl", "daemon-reload"], check=False)
            subprocess.run(["systemctl", "enable", "--now", self.service_name], check=False)
            subprocess.run(["systemctl", "restart", self.service_name], check=False)
            return f"VNC instalado. Porta: {port} Senha: {password}"
        except Exception as exc:
            return str(exc)

    def uninstall(self):
        try:
            subprocess.run(["systemctl", "disable", "--now", self.service_name], check=False)
            if os.path.exists(self.service_path):
                os.remove(self.service_path)
            if os.path.exists(self.pass_file):
                os.remove(self.pass_file)
            if os.path.exists(self.session_script):
                os.remove(self.session_script)
            subprocess.run(["systemctl", "daemon-reload"], check=False)

            if os.path.exists("/etc/debian_version"):
                subprocess.run(["apt-get", "remove", "-y", "x11vnc"], check=False)
                subprocess.run(["apt-get", "autoremove", "-y"], check=False)
            else:
                subprocess.run(["yum", "remove", "-y", "x11vnc"], check=False)
            return True
        except Exception as exc:
            return str(exc)

    def read_logs(self, lines: int = 120):
        out = subprocess.run(
            ["journalctl", "-u", self.service_name, "-n", str(lines), "--no-pager"],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return True, out.stdout
        return False, "Nenhum log encontrado para VNC."

    def get_status_info(self):
        return {
            "installed": self.is_installed(),
            "running": self.is_running(),
            "port": self.get_port(),
        }
