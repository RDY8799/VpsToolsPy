import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import tarfile
from typing import Dict, List, Tuple

import psutil


class PowerTools:
    BACKUP_DIR = "/etc/rdy/system_backups"
    ROLLBACK_DIR = "/etc/rdy/rollback"

    @staticmethod
    def is_root() -> bool:
        return hasattr(os, "geteuid") and os.geteuid() == 0

    @staticmethod
    def is_port_available(port: int) -> bool:
        if port < 1 or port > 65535:
            return False
        try:
            result = subprocess.run(["ss", "-lntu"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if f":{port} " in line or line.strip().endswith(f":{port}"):
                        return False
                return True
        except Exception:
            pass
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex(("127.0.0.1", port)) != 0

    @staticmethod
    def detect_port_owner(port: int) -> Dict[str, str]:
        try:
            result = subprocess.run(
                ["ss", "-lntp"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return {"service": "unknown", "process": "unknown", "raw": ""}

            lines = result.stdout.splitlines()
            for line in lines:
                if f":{port} " not in line and not line.strip().endswith(f":{port}"):
                    continue
                proc_match = re.search(r'users:\(\("([^"]+)"', line)
                process = proc_match.group(1) if proc_match else "unknown"
                service_map = {
                    "sshd": "ssh",
                    "dropbear": "dropbear",
                    "squid": "squid",
                    "sslh": "sslh",
                    "openvpn": "openvpn",
                    "xray": "xray",
                    "trojan": "trojan",
                    "ss-server": "shadowsocks",
                    "hysteria": "hysteria",
                    "dnstt-server": "dnstt",
                }
                return {
                    "service": service_map.get(process, "unknown"),
                    "process": process,
                    "raw": line.strip(),
                }
        except Exception:
            pass
        return {"service": "unknown", "process": "unknown", "raw": ""}

    @staticmethod
    def _restart_service(*names) -> bool:
        for name in names:
            if not name:
                continue
            if subprocess.run(["systemctl", "restart", name], check=False).returncode == 0:
                return True
            if subprocess.run(["service", name, "restart"], check=False).returncode == 0:
                return True
        return False

    @staticmethod
    def _replace_line(path: str, pattern: str, new_line: str) -> bool:
        if not os.path.exists(path):
            return False
        with open(path, "r") as f:
            content = f.read()
        new_content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
        if new_content == content and pattern.startswith("^"):
            new_content += f"\n{new_line}\n"
        with open(path, "w") as f:
            f.write(new_content)
        return True

    @staticmethod
    def change_port(service: str, new_port: int) -> Tuple[bool, str]:
        if not PowerTools.is_port_available(new_port):
            return False, f"Porta {new_port} indisponivel."

        try:
            if service == "ssh":
                path = "/etc/ssh/sshd_config"
                ok = PowerTools._replace_line(path, r"^Port\s+\d+", f"Port {new_port}")
                if not ok:
                    return False, "Arquivo sshd_config nao encontrado."
                PowerTools._restart_service("sshd", "ssh")
                return True, f"Porta SSH alterada para {new_port}."

            if service == "dropbear":
                path = "/etc/default/dropbear"
                ok = PowerTools._replace_line(path, r"^DROPBEAR_PORT=\d+", f"DROPBEAR_PORT={new_port}")
                if not ok:
                    return False, "Arquivo do Dropbear nao encontrado."
                PowerTools._restart_service("dropbear")
                return True, f"Porta Dropbear alterada para {new_port}."

            if service == "squid":
                path = "/etc/squid/squid.conf" if os.path.exists("/etc/squid/squid.conf") else "/etc/squid3/squid.conf"
                ok = PowerTools._replace_line(path, r"^http_port\s+\d+", f"http_port {new_port}")
                if not ok:
                    return False, "Config do Squid nao encontrada."
                PowerTools._restart_service("squid", "squid3")
                return True, f"Porta Squid alterada para {new_port}."

            if service == "stunnel":
                path = "/etc/stunnel/stunnel.conf"
                ok = PowerTools._replace_line(path, r"^accept\s*=\s*\d+", f"accept = {new_port}")
                if not ok:
                    return False, "Config do Stunnel nao encontrada."
                PowerTools._restart_service("stunnel4", "stunnel")
                return True, f"Porta Stunnel alterada para {new_port}."

            if service == "sslh":
                path = "/etc/default/sslh"
                if not os.path.exists(path):
                    return False, "Config do SSLH nao encontrada."
                with open(path, "r") as f:
                    content = f.read()
                updated = re.sub(r"--listen 0\.0\.0\.0:\d+", f"--listen 0.0.0.0:{new_port}", content)
                with open(path, "w") as f:
                    f.write(updated)
                PowerTools._restart_service("sslh")
                return True, f"Porta SSLH alterada para {new_port}."

            if service == "openvpn":
                path = "/etc/openvpn/server/server.conf"
                ok = PowerTools._replace_line(path, r"^port\s+\d+", f"port {new_port}")
                if not ok:
                    return False, "Config do OpenVPN nao encontrada."
                PowerTools._restart_service("openvpn-server@server", "openvpn@server", "openvpn")
                return True, f"Porta OpenVPN alterada para {new_port}."

            if service == "shadowsocks":
                candidates = ["/etc/shadowsocks-libev/config.json", "/etc/shadowsocks/config.json"]
                path = next((p for p in candidates if os.path.exists(p)), "")
                if not path:
                    return False, "Config do ShadowSocks nao encontrada."
                with open(path, "r") as f:
                    cfg = json.load(f)
                cfg["server_port"] = int(new_port)
                with open(path, "w") as f:
                    json.dump(cfg, f, indent=2)
                PowerTools._restart_service("shadowsocks-libev", "shadowsocks")
                return True, f"Porta ShadowSocks alterada para {new_port}."

            if service == "xray":
                path = "/usr/local/etc/xray/config.json"
                if not os.path.exists(path):
                    return False, "Config do Xray nao encontrada."
                with open(path, "r") as f:
                    cfg = json.load(f)
                if not cfg.get("inbounds"):
                    return False, "Config do Xray sem inbounds."
                cfg["inbounds"][0]["port"] = int(new_port)
                with open(path, "w") as f:
                    json.dump(cfg, f, indent=2)
                PowerTools._restart_service("xray")
                return True, f"Porta Xray alterada para {new_port}."

            if service == "hysteria":
                path = "/etc/hysteria/config.yaml"
                ok = PowerTools._replace_line(path, r"^listen:\s*:\d+", f"listen: :{new_port}")
                if not ok:
                    return False, "Config do Hysteria nao encontrada."
                PowerTools._restart_service("hysteria-server", "hysteria")
                return True, f"Porta Hysteria alterada para {new_port}."

            if service == "dnstt":
                path = "/etc/dnstt/server.env"
                ok = PowerTools._replace_line(path, r"^DNSTT_UDP_PORT=\d+", f"DNSTT_UDP_PORT={new_port}")
                if not ok:
                    return False, "Config do DNSTT nao encontrada."
                PowerTools._restart_service("dnstt")
                return True, f"Porta DNSTT alterada para {new_port}."

            if service == "trojan":
                path = "/etc/trojan/config.json"
                if not os.path.exists(path):
                    return False, "Config do Trojan nao encontrada."
                with open(path, "r") as f:
                    cfg = json.load(f)
                cfg["local_port"] = int(new_port)
                with open(path, "w") as f:
                    json.dump(cfg, f, indent=2)
                PowerTools._restart_service("trojan")
                return True, f"Porta Trojan alterada para {new_port}."

            return False, f"Servico '{service}' nao suportado."
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def dashboard_snapshot() -> Dict:
        net = psutil.net_io_counters()
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage("/")
        users = psutil.users()
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "mem_percent": mem.percent,
            "swap_percent": swap.percent,
            "disk_percent": disk.percent,
            "net_sent_mb": round(net.bytes_sent / (1024 * 1024), 2),
            "net_recv_mb": round(net.bytes_recv / (1024 * 1024), 2),
            "sessions": len(users),
        }

    @staticmethod
    def service_status_map(services: List[str]) -> Dict[str, str]:
        output = {}
        for service in services:
            result = subprocess.run(
                ["systemctl", "is-active", service], capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                output[service] = "active"
                continue
            alt = subprocess.run(["service", service, "status"], capture_output=True, text=True, check=False)
            output[service] = "active" if alt.returncode == 0 else "inactive"
        return output

    @staticmethod
    def read_service_logs(service: str, lines: int = 80) -> Tuple[bool, str]:
        cmd = ["journalctl", "-u", service, "-n", str(lines), "--no-pager"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return True, result.stdout
        log_file = "/var/log/syslog" if os.path.exists("/var/log/syslog") else "/var/log/messages"
        if os.path.exists(log_file):
            grep = subprocess.run(["tail", "-n", str(lines), log_file], capture_output=True, text=True, check=False)
            if grep.returncode == 0:
                return True, grep.stdout
        return False, result.stderr.strip() or "Nao foi possivel ler logs."

    @staticmethod
    def backup_configs(name: str = "backup") -> Tuple[bool, str]:
        os.makedirs(PowerTools.BACKUP_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(PowerTools.BACKUP_DIR, f"{name}_{stamp}.tar.gz")
        candidates = [
            "/etc/rdy",
            "/etc/ssh/sshd_config",
            "/etc/default/dropbear",
            "/etc/default/sslh",
            "/etc/stunnel/stunnel.conf",
            "/etc/squid/squid.conf",
            "/etc/squid3/squid.conf",
        ]
        try:
            with tarfile.open(path, "w:gz") as tar:
                for item in candidates:
                    if os.path.exists(item):
                        tar.add(item)
            return True, path
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def restore_configs(backup_path: str) -> Tuple[bool, str]:
        if not os.path.exists(backup_path):
            return False, "Arquivo de backup nao encontrado."
        try:
            with tarfile.open(backup_path, "r:gz") as tar:
                tar.extractall("/")
            return True, "Backup restaurado com sucesso."
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def firewall_apply(profile: str) -> Tuple[bool, str]:
        if shutil.which("ufw"):
            if profile == "basic":
                subprocess.run(["ufw", "--force", "reset"], check=False)
                subprocess.run(["ufw", "default", "deny", "incoming"], check=False)
                subprocess.run(["ufw", "default", "allow", "outgoing"], check=False)
                for port in ["22", "80", "443"]:
                    subprocess.run(["ufw", "allow", port], check=False)
                subprocess.run(["ufw", "--force", "enable"], check=False)
                return True, "Perfil basic aplicado no UFW."
            if profile == "open":
                subprocess.run(["ufw", "default", "allow", "incoming"], check=False)
                subprocess.run(["ufw", "--force", "enable"], check=False)
                return True, "Perfil open aplicado no UFW."
            return False, "Perfil invalido."

        if shutil.which("iptables"):
            if profile == "basic":
                subprocess.run(["iptables", "-P", "INPUT", "DROP"], check=False)
                subprocess.run(["iptables", "-P", "FORWARD", "DROP"], check=False)
                subprocess.run(["iptables", "-P", "OUTPUT", "ACCEPT"], check=False)
                for port in ["22", "80", "443"]:
                    subprocess.run(["iptables", "-A", "INPUT", "-p", "tcp", "--dport", port, "-j", "ACCEPT"], check=False)
                return True, "Perfil basic aplicado no iptables."
            if profile == "open":
                subprocess.run(["iptables", "-P", "INPUT", "ACCEPT"], check=False)
                return True, "Perfil open aplicado no iptables."
            return False, "Perfil invalido."

        return False, "Nem UFW nem iptables disponiveis."

    @staticmethod
    def health_check() -> Dict[str, str]:
        report = {}
        report["root"] = "ok" if PowerTools.is_root() else "fail: execute como root"
        try:
            psutil.disk_usage("/")
            report["disk"] = "ok"
        except Exception as exc:
            report["disk"] = f"fail: {exc}"
        try:
            requests_ok = subprocess.run(["ping", "-c", "1", "1.1.1.1"], capture_output=True, check=False)
            report["internet"] = "ok" if requests_ok.returncode == 0 else "fail: sem conectividade"
        except Exception:
            report["internet"] = "fail: ping indisponivel"
        report["python"] = "ok"
        report["memory"] = "ok" if psutil.virtual_memory().percent < 95 else "warn: memoria alta"
        return report

    @staticmethod
    def pre_install_validation(service_name: str, required_ports: List[int]) -> Tuple[bool, List[str]]:
        issues = []
        if not PowerTools.is_root():
            issues.append("Usuario atual nao e root.")
        for port in required_ports:
            if not PowerTools.is_port_available(port):
                issues.append(f"Porta {port} em uso.")
        if not shutil.which("systemctl") and not shutil.which("service"):
            issues.append("Gerenciador de servicos nao encontrado.")
        return len(issues) == 0, issues

    @staticmethod
    def save_rollback_snapshot(service_name: str) -> Tuple[bool, str]:
        targets = {
            "ssh": ["/etc/ssh/sshd_config"],
            "dropbear": ["/etc/default/dropbear"],
            "squid": ["/etc/squid/squid.conf", "/etc/squid3/squid.conf"],
            "sslh": ["/etc/default/sslh"],
            "stunnel": ["/etc/stunnel/stunnel.conf"],
        }
        paths = [p for p in targets.get(service_name, []) if os.path.exists(p)]
        if not paths:
            return False, "Nenhum arquivo de configuracao encontrado para snapshot."

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_dir = os.path.join(PowerTools.ROLLBACK_DIR, service_name)
        os.makedirs(dest_dir, exist_ok=True)
        archive = os.path.join(dest_dir, f"{stamp}.tar.gz")
        try:
            with tarfile.open(archive, "w:gz") as tar:
                for item in paths:
                    tar.add(item)
            return True, archive
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def list_rollbacks(service_name: str) -> List[str]:
        dest_dir = os.path.join(PowerTools.ROLLBACK_DIR, service_name)
        if not os.path.isdir(dest_dir):
            return []
        files = [os.path.join(dest_dir, x) for x in os.listdir(dest_dir) if x.endswith(".tar.gz")]
        return sorted(files, reverse=True)

    @staticmethod
    def restore_rollback(archive_path: str) -> Tuple[bool, str]:
        if not os.path.exists(archive_path):
            return False, "Snapshot nao encontrado."
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall("/")
            return True, "Rollback restaurado."
        except Exception as exc:
            return False, str(exc)
