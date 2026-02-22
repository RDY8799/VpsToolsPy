import os
import secrets
import string
import subprocess

from vps_tools.core.services import Service


class DNSTTService(Service):
    def __init__(self):
        super().__init__("DNSTT (DNS Tunnel)", "dnstt-server")
        self.bin_path = "/usr/local/bin/dnstt-server"
        self.config_path = "/etc/dnstt/server.env"
        self.service_path = "/etc/systemd/system/dnstt.service"

    def is_installed(self) -> bool:
        return os.path.exists(self.bin_path) and os.path.exists(self.service_path)

    @staticmethod
    def _random_secret(length=24):
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(length))

    def _install_binary(self):
        if os.path.exists(self.bin_path):
            return True
        url = "https://github.com/tladesignz/dnstt/releases/download/v0.20230408/dnstt-server-linux-amd64"
        result = subprocess.run(["wget", "-qO", self.bin_path, url], check=False)
        if result.returncode != 0:
            return False
        subprocess.run(["chmod", "+x", self.bin_path], check=False)
        return True

    def install(self, domain="", udp_port=5300, secret=""):
        try:
            if not domain:
                return "Informe um dominio/subdominio para DNSTT (ex: dns.seudominio.com)."
            if not secret:
                secret = self._random_secret()

            if not self._install_binary():
                return "Falha no download do binario DNSTT. Instale manualmente e tente novamente."

            os.makedirs("/etc/dnstt", exist_ok=True)
            with open(self.config_path, "w") as f:
                f.write(f'DNSTT_DOMAIN="{domain}"\n')
                f.write(f'DNSTT_SECRET="{secret}"\n')
                f.write(f"DNSTT_UDP_PORT={int(udp_port)}\n")

            unit = f"""[Unit]
Description=DNSTT Server
After=network.target

[Service]
Type=simple
EnvironmentFile={self.config_path}
ExecStart={self.bin_path} -udp :${{DNSTT_UDP_PORT}} -privkey ${{DNSTT_SECRET}}
Restart=always

[Install]
WantedBy=multi-user.target
"""
            with open(self.service_path, "w") as f:
                f.write(unit)

            subprocess.run(["systemctl", "daemon-reload"], check=False)
            subprocess.run(["systemctl", "enable", "dnstt"], check=False)
            subprocess.run(["systemctl", "restart", "dnstt"], check=False)
            return f"DNSTT configurado para {domain} (UDP {udp_port}). secret={secret}"
        except Exception as exc:
            return str(exc)

    def uninstall(self):
        try:
            subprocess.run(["systemctl", "stop", "dnstt"], check=False)
            subprocess.run(["systemctl", "disable", "dnstt"], check=False)
            if os.path.exists(self.service_path):
                os.remove(self.service_path)
            if os.path.exists(self.config_path):
                os.remove(self.config_path)
            if os.path.exists(self.bin_path):
                os.remove(self.bin_path)
            subprocess.run(["systemctl", "daemon-reload"], check=False)
            return True
        except Exception as exc:
            return str(exc)

    def get_ports(self) -> list:
        if not os.path.exists(self.config_path):
            return []
        with open(self.config_path, "r") as f:
            for line in f:
                if line.startswith("DNSTT_UDP_PORT="):
                    return [line.split("=")[1].strip()]
        return []
