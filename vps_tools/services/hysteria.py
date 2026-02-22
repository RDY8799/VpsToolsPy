import os
import secrets
import string
import subprocess

from vps_tools.core.services import Service


class HysteriaService(Service):
    def __init__(self):
        super().__init__("Hysteria2", "hysteria-server")
        self.config_path = "/etc/hysteria/config.yaml"

    def is_installed(self) -> bool:
        return os.path.exists(self.config_path)

    @staticmethod
    def _random_password(length=16):
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(length))

    def _install_binary(self):
        if os.path.exists("/usr/local/bin/hysteria") or os.path.exists("/usr/bin/hysteria"):
            return
        subprocess.run(["bash", "-c", "curl -fsSL https://get.hy2.sh/ | bash"], check=True)

    def install(self, port=443, password="", domain="", email="admin@example.com"):
        try:
            self._install_binary()
            if not password:
                password = self._random_password()
            os.makedirs("/etc/hysteria", exist_ok=True)

            if domain:
                tls_block = f"""tls:
  cert: /etc/letsencrypt/live/{domain}/fullchain.pem
  key: /etc/letsencrypt/live/{domain}/privkey.pem
"""
            else:
                subprocess.run(
                    [
                        "openssl",
                        "req",
                        "-x509",
                        "-nodes",
                        "-newkey",
                        "rsa:2048",
                        "-keyout",
                        "/etc/hysteria/server.key",
                        "-out",
                        "/etc/hysteria/server.crt",
                        "-days",
                        "365",
                        "-subj",
                        "/CN=localhost",
                    ],
                    check=False,
                )
                tls_block = """tls:
  cert: /etc/hysteria/server.crt
  key: /etc/hysteria/server.key
"""

            config = f"""listen: :{int(port)}
{tls_block}
auth:
  type: password
  password: {password}

masquerade:
  type: proxy
  proxy:
    url: https://www.cloudflare.com
    rewriteHost: true
"""
            with open(self.config_path, "w") as f:
                f.write(config)

            subprocess.run(["systemctl", "restart", "hysteria-server"], check=False)
            return f"Hysteria2 instalado na porta {port}. senha={password}"
        except Exception as exc:
            return str(exc)

    def uninstall(self):
        try:
            subprocess.run(["systemctl", "stop", "hysteria-server"], check=False)
            subprocess.run(["bash", "-c", "bash <(curl -fsSL https://get.hy2.sh/) --remove"], check=False)
            if os.path.exists(self.config_path):
                os.remove(self.config_path)
            return True
        except Exception as exc:
            return str(exc)

    def get_ports(self) -> list:
        if not os.path.exists(self.config_path):
            return []
        with open(self.config_path, "r") as f:
            for line in f:
                if line.startswith("listen:"):
                    token = line.split(":")[-1].strip()
                    return [token]
        return []
