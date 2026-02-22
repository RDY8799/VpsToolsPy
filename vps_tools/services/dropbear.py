import os
import subprocess

from vps_tools.core.services import Service


class DropbearService(Service):
    def __init__(self):
        super().__init__("Dropbear SSH", "dropbear")
        self.config_path = "/etc/default/dropbear"

    def is_installed(self) -> bool:
        return os.path.exists(self.config_path)

    def install(self, port=2222):
        try:
            if os.path.exists("/etc/debian_version"):
                subprocess.run(["apt-get", "update", "-y"], check=True)
                subprocess.run(["apt-get", "install", "-y", "dropbear"], check=True)
            else:
                subprocess.run(["yum", "-y", "update"], check=True)
                subprocess.run(["yum", "install", "-y", "dropbear"], check=True)

            config = [
                "NO_START=0",
                f"DROPBEAR_PORT={port}",
                'DROPBEAR_EXTRA_ARGS=""',
                'DROPBEAR_BANNER=""',
                "DROPBEAR_RECEIVE_WINDOW=65536",
            ]

            with open(self.config_path, "w") as f:
                f.write("\n".join(config) + "\n")

            subprocess.run(["systemctl", "restart", "dropbear"], check=True)
            return True
        except Exception as e:
            return str(e)

    def uninstall(self):
        try:
            subprocess.run(["systemctl", "stop", "dropbear"], check=True)
            if os.path.exists("/etc/debian_version"):
                subprocess.run(
                    ["apt-get", "remove", "--purge", "dropbear", "-y"], check=True
                )
            else:
                subprocess.run(["yum", "remove", "dropbear", "-y"], check=True)
            return True
        except Exception as e:
            return str(e)

    def get_ports(self) -> list:
        ports = []
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                for line in f:
                    if line.startswith("DROPBEAR_PORT"):
                        ports.append(line.split("=")[1].strip())
        return ports
