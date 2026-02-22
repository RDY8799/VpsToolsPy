import os
import shutil
import socket
import subprocess
from pathlib import Path

from vps_tools.core.services import Service


class OpenVPNService(Service):
    def __init__(self):
        super().__init__("OpenVPN", "openvpn")
        self.server_conf = "/etc/openvpn/server/server.conf"
        self.client_dir = "/etc/openvpn/client"
        self.easyrsa_dir = "/etc/openvpn/easy-rsa"

    def _service_candidates(self):
        return ["openvpn-server@server", "openvpn@server", "openvpn"]

    def is_installed(self) -> bool:
        return shutil.which("openvpn") is not None and os.path.exists(self.server_conf)

    def is_running(self) -> bool:
        for name in self._service_candidates():
            result = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, check=False)
            if result.returncode == 0 and result.stdout.strip() == "active":
                return True
        return False

    def start(self) -> bool:
        for name in self._service_candidates():
            if subprocess.run(["systemctl", "start", name], check=False).returncode == 0:
                return True
            if subprocess.run(["service", name, "start"], check=False).returncode == 0:
                return True
        return False

    def stop(self) -> bool:
        ok = False
        for name in self._service_candidates():
            if subprocess.run(["systemctl", "stop", name], check=False).returncode == 0:
                ok = True
            if subprocess.run(["service", name, "stop"], check=False).returncode == 0:
                ok = True
        return ok

    def restart(self) -> bool:
        ok = False
        for name in self._service_candidates():
            if subprocess.run(["systemctl", "restart", name], check=False).returncode == 0:
                ok = True
            if subprocess.run(["service", name, "restart"], check=False).returncode == 0:
                ok = True
        return ok

    @staticmethod
    def _public_ip() -> str:
        try:
            out = subprocess.check_output(["hostname", "-I"], text=True).strip().split()
            if out:
                return out[0]
        except Exception:
            pass
        return "127.0.0.1"

    @staticmethod
    def _enable_ip_forward():
        path = "/etc/sysctl.conf"
        if os.path.exists(path):
            with open(path, "r") as f:
                content = f.read()
        else:
            content = ""
        if "net.ipv4.ip_forward=1" not in content:
            with open(path, "a") as f:
                f.write("\nnet.ipv4.ip_forward=1\n")
        subprocess.run(["sysctl", "-p"], check=False)

    @staticmethod
    def _default_iface() -> str:
        try:
            route = subprocess.check_output(["ip", "route", "show", "default"], text=True).strip()
            parts = route.split()
            if "dev" in parts:
                return parts[parts.index("dev") + 1]
        except Exception:
            pass
        return "eth0"

    def _setup_nat(self):
        iface = self._default_iface()
        subprocess.run(
            ["iptables", "-t", "nat", "-C", "POSTROUTING", "-s", "10.8.0.0/24", "-o", iface, "-j", "MASQUERADE"],
            check=False,
        )
        subprocess.run(
            ["iptables", "-t", "nat", "-A", "POSTROUTING", "-s", "10.8.0.0/24", "-o", iface, "-j", "MASQUERADE"],
            check=False,
        )

    def _install_packages(self):
        if os.path.exists("/etc/debian_version"):
            subprocess.run(["apt-get", "update", "-y"], check=True)
            subprocess.run(["apt-get", "install", "-y", "openvpn", "easy-rsa", "iptables"], check=True)
        else:
            subprocess.run(["yum", "-y", "update"], check=True)
            subprocess.run(["yum", "install", "-y", "openvpn", "easy-rsa", "iptables"], check=True)

    def _build_pki(self, client_name: str):
        os.makedirs(self.easyrsa_dir, exist_ok=True)
        if os.path.exists("/usr/share/easy-rsa"):
            subprocess.run(["cp", "-r", "/usr/share/easy-rsa/.", self.easyrsa_dir], check=False)
        elif os.path.exists("/usr/share/easy-rsa/3"):
            subprocess.run(["cp", "-r", "/usr/share/easy-rsa/3/.", self.easyrsa_dir], check=False)

        pki = Path(self.easyrsa_dir)
        env = os.environ.copy()
        env["EASYRSA_BATCH"] = "1"

        subprocess.run([str(pki / "easyrsa"), "init-pki"], cwd=self.easyrsa_dir, env=env, check=True)
        subprocess.run([str(pki / "easyrsa"), "build-ca", "nopass"], cwd=self.easyrsa_dir, env=env, check=True)
        subprocess.run([str(pki / "easyrsa"), "gen-dh"], cwd=self.easyrsa_dir, env=env, check=True)
        subprocess.run([str(pki / "easyrsa"), "build-server-full", "server", "nopass"], cwd=self.easyrsa_dir, env=env, check=True)
        subprocess.run([str(pki / "easyrsa"), "build-client-full", client_name, "nopass"], cwd=self.easyrsa_dir, env=env, check=True)
        subprocess.run(["openvpn", "--genkey", "secret", "/etc/openvpn/server/tls-crypt.key"], check=True)

        os.makedirs("/etc/openvpn/server", exist_ok=True)
        subprocess.run(["cp", f"{self.easyrsa_dir}/pki/ca.crt", "/etc/openvpn/server/ca.crt"], check=True)
        subprocess.run(["cp", f"{self.easyrsa_dir}/pki/private/server.key", "/etc/openvpn/server/server.key"], check=True)
        subprocess.run(["cp", f"{self.easyrsa_dir}/pki/issued/server.crt", "/etc/openvpn/server/server.crt"], check=True)
        subprocess.run(["cp", f"{self.easyrsa_dir}/pki/dh.pem", "/etc/openvpn/server/dh.pem"], check=True)

    def _write_server_conf(self, port: int, protocol: str, vpn_network: str, dns1: str, dns2: str):
        conf = f"""port {port}
proto {protocol}
dev tun
user nobody
group nogroup
persist-key
persist-tun
topology subnet
server {vpn_network}
ifconfig-pool-persist /etc/openvpn/server/ipp.txt
push "redirect-gateway def1 bypass-dhcp"
push "dhcp-option DNS {dns1}"
push "dhcp-option DNS {dns2}"
keepalive 10 120
tls-crypt /etc/openvpn/server/tls-crypt.key
crl-verify /etc/openvpn/server/crl.pem
ca /etc/openvpn/server/ca.crt
cert /etc/openvpn/server/server.crt
key /etc/openvpn/server/server.key
dh /etc/openvpn/server/dh.pem
cipher AES-256-GCM
auth SHA256
data-ciphers AES-256-GCM:AES-128-GCM
status /var/log/openvpn-status.log
verb 3
explicit-exit-notify 1
"""
        with open(self.server_conf, "w") as f:
            f.write(conf)

    def _current_port_proto(self):
        port = "1194"
        proto = "udp"
        if os.path.exists(self.server_conf):
            with open(self.server_conf, "r") as f:
                for line in f:
                    if line.startswith("port "):
                        port = line.split()[1].strip()
                    elif line.startswith("proto "):
                        proto = line.split()[1].strip()
        return int(port), proto

    def _write_client_ovpn(
        self, client_name: str, endpoint: str, port: int, protocol: str, use_domain: bool
    ) -> str:
        os.makedirs(self.client_dir, exist_ok=True)
        ca = Path(f"{self.easyrsa_dir}/pki/ca.crt").read_text()
        cert_raw = Path(f"{self.easyrsa_dir}/pki/issued/{client_name}.crt").read_text()
        key = Path(f"{self.easyrsa_dir}/pki/private/{client_name}.key").read_text()
        tls = Path("/etc/openvpn/server/tls-crypt.key").read_text()

        cert = cert_raw
        begin = "-----BEGIN CERTIFICATE-----"
        if begin in cert_raw:
            cert = cert_raw[cert_raw.index(begin):]

        verify_line = "remote-cert-tls server\n" if use_domain else ""
        profile = f"""client
dev tun
proto {protocol}
remote {endpoint} {port}
resolv-retry infinite
nobind
persist-key
persist-tun
cipher AES-256-GCM
auth SHA256
verb 3
{verify_line}<ca>
{ca}
</ca>
<cert>
{cert}
</cert>
<key>
{key}
</key>
<tls-crypt>
{tls}
</tls-crypt>
"""
        path = f"{self.client_dir}/{client_name}.ovpn"
        with open(path, "w") as f:
            f.write(profile)
        return path

    def install(
        self,
        port: int = 1194,
        protocol: str = "udp",
        vpn_network: str = "10.8.0.0 255.255.255.0",
        dns1: str = "1.1.1.1",
        dns2: str = "8.8.8.8",
        endpoint: str = "",
        use_domain: bool = False,
        client_name: str = "client",
    ):
        try:
            protocol = protocol.lower().strip()
            if protocol not in {"udp", "tcp"}:
                return "Protocolo invalido. Use udp ou tcp."

            self._install_packages()
            self._build_pki(client_name=client_name)
            self._write_server_conf(port, protocol, vpn_network, dns1, dns2)
            self._enable_ip_forward()
            self._setup_nat()

            endpoint_final = endpoint.strip() or self._public_ip()
            client_path = self._write_client_ovpn(
                client_name=client_name,
                endpoint=endpoint_final,
                port=port,
                protocol=protocol,
                use_domain=use_domain,
            )

            if not self.restart():
                self.start()
            return f"OpenVPN instalado. Cliente gerado em: {client_path}"
        except Exception as exc:
            return str(exc)

    def list_clients(self):
        if not os.path.isdir(self.client_dir):
            return []
        clients = []
        for name in os.listdir(self.client_dir):
            if name.endswith(".ovpn"):
                clients.append(name[:-5])
        return sorted(clients)

    def add_client(self, username: str, endpoint: str = "", use_domain: bool = False):
        try:
            username = username.strip()
            if not username:
                return "Nome de usuario invalido."
            env = os.environ.copy()
            env["EASYRSA_BATCH"] = "1"
            subprocess.run(
                [f"{self.easyrsa_dir}/easyrsa", "build-client-full", username, "nopass"],
                cwd=self.easyrsa_dir,
                env=env,
                check=True,
            )

            port, proto = self._current_port_proto()
            endpoint_final = endpoint.strip() or self._public_ip()
            profile = self._write_client_ovpn(
                client_name=username,
                endpoint=endpoint_final,
                port=port,
                protocol=proto,
                use_domain=use_domain,
            )
            return f"Cliente criado com sucesso: {profile}"
        except Exception as exc:
            return str(exc)

    def revoke_client(self, username: str):
        try:
            username = username.strip()
            if not username:
                return "Nome de usuario invalido."
            env = os.environ.copy()
            env["EASYRSA_BATCH"] = "1"
            subprocess.run(
                [f"{self.easyrsa_dir}/easyrsa", "revoke", username],
                cwd=self.easyrsa_dir,
                env=env,
                check=True,
            )
            subprocess.run(
                [f"{self.easyrsa_dir}/easyrsa", "gen-crl"],
                cwd=self.easyrsa_dir,
                env=env,
                check=True,
            )
            subprocess.run(["cp", f"{self.easyrsa_dir}/pki/crl.pem", "/etc/openvpn/server/crl.pem"], check=True)
            ovpn = f"{self.client_dir}/{username}.ovpn"
            if os.path.exists(ovpn):
                os.remove(ovpn)
            self.restart()
            return True
        except Exception as exc:
            return str(exc)

    def uninstall(self):
        try:
            self.stop()
            if os.path.exists("/etc/debian_version"):
                subprocess.run(["apt-get", "remove", "--purge", "-y", "openvpn", "easy-rsa"], check=True)
            else:
                subprocess.run(["yum", "remove", "-y", "openvpn", "easy-rsa"], check=True)

            for path in ["/etc/openvpn/server", self.client_dir, self.easyrsa_dir]:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
            if os.path.exists("/etc/openvpn"):
                subprocess.run(["find", "/etc/openvpn", "-type", "f", "-delete"], check=False)
            return True
        except Exception as exc:
            return str(exc)

    def get_ports(self) -> list:
        if not os.path.exists(self.server_conf):
            return []
        with open(self.server_conf, "r") as f:
            for line in f:
                if line.startswith("port "):
                    return [line.split()[1].strip()]
        return []
