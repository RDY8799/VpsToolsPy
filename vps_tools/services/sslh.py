import os
import re
import subprocess

from vps_tools.core.services import Service


class SSLHService(Service):
    def __init__(self):
        super().__init__("SSLH Multiplexer", "sslh")
        self.config_path = "/etc/default/sslh"

    def is_installed(self) -> bool:
        return os.path.exists(self.config_path)

    def install(
            self, listen_port=443, ssh_port=22, http_port=80, ssl_port=4433, openvpn_port=1194
    ):
        try:
            if os.path.exists("/etc/debian_version"):
                subprocess.run(["apt-get", "update", "-y"], check=True)
                subprocess.run(["apt-get", "install", "-y", "sslh"], check=True)
            else:
                subprocess.run(["yum", "-y", "update"], check=True)
                subprocess.run(["yum", "install", "-y", "sslh"], check=True)

            config = [
                "RUN=yes",
                "DAEMON=/usr/sbin/sslh",
                (
                    f'DAEMON_OPTS="--user sslh --listen 0.0.0.0:{listen_port} '
                    f"--ssh 127.0.0.1:{ssh_port} --http 127.0.0.1:{http_port} "
                    f"--ssl 127.0.0.1:{ssl_port} --openvpn 127.0.0.1:{openvpn_port} "
                    '--pidfile /var/run/sslh/sslh.pid --timeout 5"'
                ),
            ]

            with open(self.config_path, "w") as f:
                f.write("\n".join(config) + "\n")

            subprocess.run(["systemctl", "restart", "sslh"], check=True)
            return True
        except Exception as e:
            return str(e)

    def uninstall(self):
        try:
            subprocess.run(["systemctl", "stop", "sslh"], check=True)
            if os.path.exists("/etc/debian_version"):
                subprocess.run(["apt-get", "remove", "--purge", "sslh", "-y"], check=True)
            else:
                subprocess.run(["yum", "remove", "sslh", "-y"], check=True)
            return True
        except Exception as e:
            return str(e)

    def get_ports(self) -> dict:
        ports = {}
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                content = f.read()
                ports["listen"] = (
                    re.search(r"--listen 0\.0\.0\.0:(\d+)", content).group(1)
                    if "--listen" in content
                    else "Unknown"
                )
                ports["ssh"] = (
                    re.search(r"--ssh 127\.0\.0\.1:(\d+)", content).group(1)
                    if "--ssh" in content
                    else "Unknown"
                )
                ports["http"] = (
                    re.search(r"--http 127\.0\.0\.1:(\d+)", content).group(1)
                    if "--http" in content
                    else "Unknown"
                )
                ports["ssl"] = (
                    re.search(r"--ssl 127\.0\.0\.1:(\d+)", content).group(1)
                    if "--ssl" in content
                    else "Unknown"
                )
                ports["openvpn"] = (
                    re.search(r"--openvpn 127\.0\.0\.1:(\d+)", content).group(1)
                    if "--openvpn" in content
                    else "Unknown"
                )
        return ports

    def set_port(self, protocol: str, new_port: int) -> bool:
        if not os.path.exists(self.config_path):
            return False

        with open(self.config_path, "r") as f:
            content = f.read()

        if protocol == "listen":
            new_content = re.sub(
                r"--listen 0\.0\.0\.0:\d+", f"--listen 0.0.0.0:{new_port}", content
            )
        else:
            new_content = re.sub(
                rf"--{protocol} 127\.0\.0\.1:\d+",
                f"--{protocol} 127.0.0.1:{new_port}",
                content,
            )

        with open(self.config_path, "w") as f:
            f.write(new_content)

        return self.restart()
