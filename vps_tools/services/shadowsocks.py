import json
import os
import random
import string
import subprocess

from vps_tools.core.services import Service


class ShadowSocksService(Service):
    def __init__(self):
        super().__init__("ShadowSocks", "shadowsocks-libev")
        self.config_path = "/etc/shadowsocks-libev/config.json"
        self.alt_config_path = "/etc/shadowsocks/config.json"

    def _actual_config(self):
        if os.path.exists(self.config_path):
            return self.config_path
        if os.path.exists(self.alt_config_path):
            return self.alt_config_path
        return self.config_path

    def is_installed(self) -> bool:
        return os.path.exists(self._actual_config())

    @staticmethod
    def _random_password(length=16):
        chars = string.ascii_letters + string.digits
        return "".join(random.choice(chars) for _ in range(length))

    def install(self, port=8388, password="", method="chacha20-ietf-poly1305"):
        try:
            if not password:
                password = self._random_password()

            if os.path.exists("/etc/debian_version"):
                subprocess.run(["apt-get", "update", "-y"], check=True)
                subprocess.run(["apt-get", "install", "-y", "shadowsocks-libev"], check=True)
                service_name = "shadowsocks-libev"
            else:
                subprocess.run(["yum", "-y", "update"], check=True)
                subprocess.run(["yum", "install", "-y", "shadowsocks-libev"], check=True)
                service_name = "shadowsocks-libev"

            cfg_path = self._actual_config()
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            config = {
                "server": "0.0.0.0",
                "server_port": int(port),
                "password": password,
                "timeout": 300,
                "method": method,
                "fast_open": False,
                "mode": "tcp_and_udp",
            }
            with open(cfg_path, "w") as f:
                json.dump(config, f, indent=2)

            subprocess.run(["systemctl", "restart", service_name], check=False)
            return f"ShadowSocks instalado na porta {port} com metodo {method}."
        except Exception as exc:
            return str(exc)

    def uninstall(self):
        try:
            subprocess.run(["systemctl", "stop", "shadowsocks-libev"], check=False)
            if os.path.exists("/etc/debian_version"):
                subprocess.run(["apt-get", "remove", "--purge", "-y", "shadowsocks-libev"], check=True)
            else:
                subprocess.run(["yum", "remove", "-y", "shadowsocks-libev"], check=True)
            for p in [self.config_path, self.alt_config_path]:
                if os.path.exists(p):
                    os.remove(p)
            return True
        except Exception as exc:
            return str(exc)

    def get_ports(self) -> list:
        path = self._actual_config()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r") as f:
                cfg = json.load(f)
            return [str(cfg.get("server_port"))] if cfg.get("server_port") else []
        except Exception:
            return []
