import json
import os
import secrets
import string
import subprocess
import uuid

from vps_tools.core.services import Service


class XrayService(Service):
    def __init__(self):
        super().__init__("Xray (VLESS/VMESS/TROJAN)", "xray")
        self.config_path = "/usr/local/etc/xray/config.json"

    def is_installed(self) -> bool:
        return os.path.exists(self.config_path)

    @staticmethod
    def _random_password(length=16):
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(length))

    def _install_binary(self):
        if os.path.exists("/usr/local/bin/xray"):
            return
        subprocess.run(
            ["bash", "-c", "curl -Ls https://github.com/XTLS/Xray-install/raw/main/install-release.sh | bash"],
            check=True,
        )

    def _build_config(self, mode: str, port: int, host: str, path: str, user_id: str, secret: str):
        mode = mode.lower()
        if mode == "vless":
            clients = [{"id": user_id, "email": "vless@rdy"}]
            settings = {"clients": clients, "decryption": "none"}
            stream = {"network": "ws", "security": "none", "wsSettings": {"path": path, "headers": {"Host": host}}}
            protocol = "vless"
        elif mode == "vmess":
            clients = [{"id": user_id, "alterId": 0, "email": "vmess@rdy"}]
            settings = {"clients": clients}
            stream = {"network": "ws", "security": "none", "wsSettings": {"path": path, "headers": {"Host": host}}}
            protocol = "vmess"
        elif mode == "trojan":
            clients = [{"password": secret, "email": "trojan@rdy"}]
            settings = {"clients": clients}
            stream = {"network": "tcp", "security": "none"}
            protocol = "trojan"
        else:
            raise ValueError("Modo invalido. Use vless, vmess ou trojan.")

        return {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {
                    "port": int(port),
                    "listen": "0.0.0.0",
                    "protocol": protocol,
                    "settings": settings,
                    "streamSettings": stream,
                }
            ],
            "outbounds": [{"protocol": "freedom", "settings": {}}],
        }

    def install(self, mode="vless", port=443, host="", path="/rdy", user_id="", secret=""):
        try:
            self._install_binary()
            os.makedirs("/usr/local/etc/xray", exist_ok=True)
            if not user_id:
                user_id = str(uuid.uuid4())
            if not secret:
                secret = self._random_password()
            cfg = self._build_config(mode, int(port), host or "localhost", path, user_id, secret)
            with open(self.config_path, "w") as f:
                json.dump(cfg, f, indent=2)
            subprocess.run(["systemctl", "restart", "xray"], check=False)

            if mode.lower() == "trojan":
                return f"Xray/Trojan instalado na porta {port}. senha={secret}"
            return f"Xray/{mode.upper()} instalado na porta {port}. id={user_id} path={path}"
        except Exception as exc:
            return str(exc)

    def uninstall(self):
        try:
            subprocess.run(["systemctl", "stop", "xray"], check=False)
            subprocess.run(["bash", "-c", "bash <(curl -Ls https://github.com/XTLS/Xray-install/raw/main/install-release.sh) remove"], check=False)
            if os.path.exists(self.config_path):
                os.remove(self.config_path)
            return True
        except Exception as exc:
            return str(exc)

    def get_ports(self) -> list:
        if not os.path.exists(self.config_path):
            return []
        try:
            with open(self.config_path, "r") as f:
                cfg = json.load(f)
            return [str(cfg["inbounds"][0]["port"])]
        except Exception:
            return []
