import os
import shutil
import subprocess

from vps_tools.core.services import Service


class StunnelService(Service):
    def __init__(self):
        super().__init__("SSL/TLS Stunnel4", "stunnel4")
        self.config_path = "/etc/stunnel/stunnel.conf"
        self.cert_path = "/etc/stunnel/stunnel.pem"

    def is_installed(self) -> bool:
        return shutil.which("stunnel4") is not None or shutil.which("stunnel") is not None

    def install(self, listen_port=4433, connect_port=22, ip="localhost"):
        try:
            if os.path.exists("/etc/debian_version"):
                subprocess.run(["apt-get", "update", "-y"], check=True)
                subprocess.run(
                    ["apt-get", "install", "-y", "stunnel4", "openssl"], check=True
                )
            else:
                subprocess.run(["yum", "-y", "update"], check=True)
                subprocess.run(["yum", "install", "-y", "stunnel", "openssl"], check=True)

            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-nodes",
                    "-newkey",
                    "rsa:2048",
                    "-keyout",
                    "stunnel.key",
                    "-out",
                    "stunnel.crt",
                    "-days",
                    "365",
                    "-subj",
                    "/C=BR/ST=RJ/L=Rio de Janeiro/O=RDY Landia/OU=Rdy Software/CN=localhost",
                ],
                check=True,
            )

            with open(self.cert_path, "wb") as f:
                with open("stunnel.crt", "rb") as crt:
                    f.write(crt.read())
                with open("stunnel.key", "rb") as key:
                    f.write(key.read())

            os.remove("stunnel.crt")
            os.remove("stunnel.key")

            config = [
                "client = no",
                "[squid]",
                f"cert = {self.cert_path}",
                f"accept = {listen_port}",
                f"connect = 127.0.0.1:{connect_port}",
            ]

            with open(self.config_path, "w") as f:
                f.write("\n".join(config) + "\n")

            with open("/etc/default/stunnel4", "w") as f:
                f.write('ENABLED=1\nFILES="/etc/stunnel/*.conf"\nOPTIONS=""\nPPP_RESTART=0\n')

            subprocess.run(["systemctl", "restart", "stunnel4"], check=True)
            return True
        except Exception as e:
            return str(e)

    def uninstall(self):
        try:
            subprocess.run(["systemctl", "stop", "stunnel4"], check=False)
            subprocess.run(["service", "stunnel4", "stop"], check=False)
            subprocess.run(["service", "stunnel", "stop"], check=False)
            if os.path.exists("/etc/debian_version"):
                subprocess.run(
                    ["apt-get", "remove", "--purge", "stunnel", "stunnel4", "-y"], check=True
                )
            else:
                subprocess.run(["yum", "remove", "stunnel", "stunnel4", "-y"], check=True)
            for path in [self.config_path, self.cert_path, "/etc/default/stunnel4"]:
                if os.path.exists(path):
                    os.remove(path)
            return True
        except Exception as e:
            return str(e)

    def get_ports(self) -> dict:
        ports = {}
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                for line in f:
                    if line.startswith("accept"):
                        ports["accept"] = line.split("=")[1].strip()
                    elif line.startswith("connect"):
                        ports["connect"] = line.split("=")[1].strip()
        return ports
