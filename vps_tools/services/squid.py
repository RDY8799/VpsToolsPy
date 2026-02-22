import os
import subprocess

from vps_tools.core.system import SystemActions
from vps_tools.core.services import Service


class SquidService(Service):
    def __init__(self):
        super().__init__("Squid Proxy", "squid")

    def is_installed(self) -> bool:
        return os.path.exists("/etc/squid/squid.conf") or os.path.exists(
            "/etc/squid3/squid.conf"
        )

    def get_config_path(self):
        if os.path.exists("/etc/squid/squid.conf"):
            return "/etc/squid/squid.conf"
        if os.path.exists("/etc/squid3/squid.conf"):
            return "/etc/squid3/squid.conf"
        return None

    def install(self, port=3128, ip="localhost", compress=True):
        try:
            if os.path.exists("/etc/debian_version"):
                subprocess.run(["apt-get", "update", "-y"], check=True)
                subprocess.run(
                    ["apt-get", "install", "-y", "squid", "figlet"], check=True
                )
                service_name = "squid"
            else:
                subprocess.run(["yum", "-y", "update"], check=True)
                subprocess.run(["yum", "install", "-y", "squid"], check=True)
                service_name = "squid"

            config_path = self.get_config_path()
            if not config_path:
                return "Failed to find squid configuration file path"

            payloads_path = "/etc/rdy/payloads"
            os.makedirs("/etc/rdy", exist_ok=True)
            with open(payloads_path, "w") as f:
                f.write("www.speedtest.net\n.speedtest.\ntelegram.me/rdysoftware\n")

            config = [
                f"http_port {port}",
                "http_port 3128" if port != 3128 else "",
                "visible_hostname RDYSOFTWARE",
                f"acl ip dstdomain {ip}",
                "acl GET method GET",
                "#rdyacl",
                "http_access allow ip",
                'acl accept dstdomain -i "/etc/rdy/payloads"',
                "http_access allow accept",
                "acl local dstdomain localhost",
                "#rdyallow",
                "http_access allow local",
                "acl iplocal dstdomain 127.0.0.1",
                "http_access allow iplocal",
                "http_access deny all",
            ]

            with open(config_path, "w") as f:
                f.write("\n".join([line for line in config if line]) + "\n")

            if compress:
                with open("/etc/ssh/sshd_config", "r") as f:
                    lines = f.readlines()
                with open("/etc/ssh/sshd_config", "w") as f:
                    for line in lines:
                        if not line.startswith("Compression"):
                            f.write(line)
                    f.write("\nCompression yes\n")
                if not SystemActions.restart_service_with_fallback("sshd", "ssh"):
                    return "Falha ao reiniciar servico SSH (sshd/ssh)"

            subprocess.run(["systemctl", "restart", service_name], check=True)
            return True
        except Exception as e:
            return str(e)

    def uninstall(self):
        try:
            if os.path.exists("/etc/debian_version"):
                subprocess.run(
                    ["apt-get", "remove", "--purge", "squid", "squid3", "-y"],
                    check=True,
                )
            else:
                subprocess.run(["yum", "remove", "squid", "squid3", "-y"], check=True)
            return True
        except Exception as e:
            return str(e)

    def get_ports(self) -> list:
        ports = []
        path = self.get_config_path()
        if path:
            with open(path, "r") as f:
                for line in f:
                    if line.startswith("http_port"):
                        ports.append(line.split()[1])
        return ports
