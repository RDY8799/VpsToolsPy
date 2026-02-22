import csv
import json
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from vps_tools.core.services import Service


@dataclass
class HostResult:
    host: str
    ips: list[str]
    ssl_port: int | None = None
    ssl_ok: bool | None = None
    tls_version: str | None = None
    cert_subject: str | None = None
    cert_issuer: str | None = None
    cert_not_after: str | None = None
    suspected_stunnel: bool | None = None
    stunnel_signals: str | None = None
    error: str | None = None


class DomainAuditService(Service):
    def __init__(self):
        super().__init__("Domain Audit", "domain-audit")

    def is_installed(self) -> bool:
        return True

    def is_running(self) -> bool:
        return False

    def start(self) -> bool:
        return True

    def stop(self) -> bool:
        return True

    def restart(self) -> bool:
        return True

    def uninstall(self):
        return "Domain Audit e um modulo interno de execucao."

    def install(self):
        return True

    @staticmethod
    def normalize_domain(domain: str) -> str:
        d = domain.strip().lower()
        if d.startswith("http://") or d.startswith("https://"):
            d = d.split("://", 1)[1]
        return d.strip("/").split("/")[0]

    @staticmethod
    def parse_ports(raw: str) -> list[int]:
        ports: list[int] = []
        for part in raw.split(","):
            p = part.strip()
            if not p:
                continue
            port = int(p)
            if not (1 <= port <= 65535):
                raise ValueError(f"Porta invalida: {p}")
            ports.append(port)
        return sorted(set(ports))

    @staticmethod
    def resolve_host(host: str) -> tuple[list[str], str | None]:
        try:
            info = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
            ips = sorted({item[4][0] for item in info if item and item[4]})
            return ips, None
        except socket.gaierror as exc:
            return [], f"DNS failed: {exc}"
        except Exception as exc:
            return [], str(exc)

    @staticmethod
    def fetch_crtsh_hosts(domain: str, timeout: float = 4.0) -> set[str]:
        url = f"https://crt.sh/?q=%25.{domain}&output=json"
        req = urllib.request.Request(url, headers={"User-Agent": "vps-tools-domain-audit/1.0"}, method="GET")
        hosts: set[str] = {domain}
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
            data = json.loads(payload) if payload.strip() else []
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            return hosts
        for item in data:
            name_value = str(item.get("name_value", "")).strip().lower()
            if not name_value:
                continue
            for host in name_value.splitlines():
                host = host.strip()
                if host.startswith("*."):
                    host = host[2:]
                if host == domain or host.endswith(f".{domain}"):
                    hosts.add(host)
        return hosts

    @staticmethod
    def first_attr(value, key: str):
        if not value:
            return None
        for pair in value:
            if isinstance(pair, tuple) and len(pair) == 2 and pair[0] == key:
                return str(pair[1])
        return None

    @staticmethod
    def detect_stunnel_signals(subject: str | None, issuer: str | None, tls_version: str | None):
        if not subject:
            return False, ""
        signals = []
        s = subject.lower()
        if "localhost" in s or "localdomain" in s:
            signals.append("localhost/localdomain")
        if "stunnel" in s:
            signals.append("stunnel-cn")
        if tls_version in {"TLSv1", "TLSv1.1", "TLSv1.2"}:
            signals.append(f"older-tls:{tls_version}")
        if subject and issuer and subject == issuer:
            signals.append("self-signed")
        if signals:
            return True, ", ".join(signals)
        return False, ""

    @staticmethod
    def check_ssl(host: str, port: int, timeout: float = 3.5):
        try:
            context = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=host) as tls:
                    cert = tls.getpeercert()
                    subject = None
                    issuer = None
                    if cert:
                        subject_raw = cert.get("subject", ())
                        issuer_raw = cert.get("issuer", ())
                        subject = DomainAuditService.first_attr(subject_raw[-1] if subject_raw else (), "commonName")
                        issuer = DomainAuditService.first_attr(issuer_raw[-1] if issuer_raw else (), "commonName")
                    tls_version = tls.version()
                    suspected, signals = DomainAuditService.detect_stunnel_signals(subject, issuer, tls_version)
                    return {
                        "ssl_ok": True,
                        "tls_version": tls_version,
                        "cert_subject": subject,
                        "cert_issuer": issuer,
                        "cert_not_after": cert.get("notAfter") if cert else None,
                        "suspected_stunnel": suspected,
                        "stunnel_signals": signals,
                        "error": None,
                    }
        except Exception as exc:
            return {
                "ssl_ok": False,
                "tls_version": None,
                "cert_subject": None,
                "cert_issuer": None,
                "cert_not_after": None,
                "suspected_stunnel": None,
                "stunnel_signals": None,
                "error": f"SSL check failed on {port}: {exc}",
            }

    @staticmethod
    def _save_csv(results: Iterable[HostResult], output: Path):
        fields = [
            "host",
            "ips",
            "ssl_port",
            "ssl_ok",
            "tls_version",
            "cert_subject",
            "cert_issuer",
            "cert_not_after",
            "suspected_stunnel",
            "stunnel_signals",
            "error",
        ]
        with output.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in results:
                item = asdict(row)
                item["ips"] = ",".join(row.ips)
                writer.writerow(item)

    @staticmethod
    def _save_json(results: Iterable[HostResult], output: Path):
        data = [asdict(r) for r in results]
        with output.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def run_audit(
        self,
        domain: str,
        ports: str = "443",
        check_ssl: bool = True,
        output: str = "domain_audit.csv",
    ):
        try:
            base_domain = self.normalize_domain(domain)
            parsed_ports = self.parse_ports(ports)
            hosts = sorted(self.fetch_crtsh_hosts(base_domain))

            results: list[HostResult] = []
            for host in hosts:
                ips, err = self.resolve_host(host)
                if not check_ssl:
                    results.append(HostResult(host=host, ips=ips, error=err))
                    continue
                if err:
                    results.append(HostResult(host=host, ips=[], error=err))
                    continue
                for port in parsed_ports:
                    data = self.check_ssl(host, port)
                    results.append(
                        HostResult(
                            host=host,
                            ips=ips,
                            ssl_port=port,
                            ssl_ok=data["ssl_ok"],
                            tls_version=data["tls_version"],
                            cert_subject=data["cert_subject"],
                            cert_issuer=data["cert_issuer"],
                            cert_not_after=data["cert_not_after"],
                            suspected_stunnel=data["suspected_stunnel"],
                            stunnel_signals=data["stunnel_signals"],
                            error=data["error"],
                        )
                    )

            out = Path(output)
            if out.suffix.lower() == ".json":
                self._save_json(results, out)
            else:
                if not out.suffix:
                    out = Path(f"{output}.csv")
                self._save_csv(results, out)
            return True, f"Domain audit concluido. Saida: {out}"
        except Exception as exc:
            return False, str(exc)
