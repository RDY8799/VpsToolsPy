import json
import os
import subprocess

from vps_tools.core.services import Service


class TrojanService(Service):
    def __init__(self):
        super().__init__("Trojan", "trojan")
        self.config_path = "/etc/trojan/config.json"

    def is_installed(self) -> bool:
        return os.path.exists(self.config_path)

    def install(self, password="password", port=443):
        try:
            # Installation logic based on common trojan scripts
            subprocess.run(['bash', '-c',
                            'curl -L https://raw.githubusercontent.com/trojan-gfw/trojan/master/scripts/install.sh | bash'],
                           check=True)

            config = {
                "run_type": "server",
                "local_addr": "0.0.0.0",
                "local_port": port,
                "remote_addr": "127.0.0.1",
                "remote_port": 80,
                "password": [password],
                "log_level": 1,
                "ssl": {
                    "cert": "/etc/trojan/cert.crt",
                    "key": "/etc/trojan/private.key",
                    "sni": "localhost"
                }
            }

            os.makedirs("/etc/trojan", exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=4)

            subprocess.run(['systemctl', 'enable', 'trojan'], check=True)
            subprocess.run(['systemctl', 'start', 'trojan'], check=True)
            return True
        except Exception as e:
            return str(e)

    def uninstall(self):
        try:
            subprocess.run(['systemctl', 'stop', 'trojan'], check=True)
            subprocess.run(['systemctl', 'disable', 'trojan'], check=True)
            if os.path.exists('/usr/bin/trojan'):
                os.remove('/usr/bin/trojan')
            if os.path.exists('/etc/trojan'):
                import shutil
                shutil.rmtree('/etc/trojan')
            return True
        except Exception as e:
            return str(e)
