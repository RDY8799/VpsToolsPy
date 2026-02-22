#!/usr/bin/env python3
"""
Authorized domain audit helper with stunnel-like detection.

Usage examples:
  python domain_audit.py --domain example.com --check-ssl --ports 443,8443 --output results.csv
  python domain_audit.py --domain example.com --wordlist subdomains.txt --output results.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import socket
import ssl
import sys
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse


DEFAULT_TIMEOUT = 3.5
DEFAULT_THREADS = 40
DEFAULT_MAX_CRAWL_PAGES = 60


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


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, val in attrs:
            if not val:
                continue
            if key.lower() in {"href", "src", "action"}:
                self.links.append(val.strip())


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def default_output_name() -> str:
    return f"domain_audit_{datetime.now().strftime('%M%S')}.csv"


def normalize_domain(domain: str) -> str:
    d = domain.strip().lower()
    if d.startswith("http://") or d.startswith("https://"):
        d = d.split("://", 1)[1]
    return d.strip("/").split("/")[0]


def normalize_host(raw_host: str | None) -> str | None:
    if not raw_host:
        return None
    host = raw_host.strip().strip(".").lower()
    if not host:
        return None
    return host


def in_scope(host: str | None, domain: str) -> bool:
    h = normalize_host(host)
    if not h:
        return False
    return h == domain or h.endswith(f".{domain}")


def fetch_crtsh_hosts(domain: str, timeout: float) -> set[str]:
    url = f"https://crt.sh/?q=%25.{domain}&output=json"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "authorized-domain-audit/1.0"},
        method="GET",
    )
    hosts: set[str] = set()

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
        if not raw.strip():
            return hosts
        data = json.loads(raw)
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


def load_wordlist(wordlist_path: Path, domain: str) -> set[str]:
    hosts: set[str] = set()
    with wordlist_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            sub = line.strip().lower()
            if not sub or sub.startswith("#"):
                continue
            sub = sub.strip(".")
            if "." in sub and sub.endswith(domain):
                hosts.add(sub)
            elif "." not in sub:
                hosts.add(f"{sub}.{domain}")
    return hosts


def fetch_text(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "authorized-domain-audit/1.0"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        ctype = response.headers.get("Content-Type", "").lower()
        if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
            return ""
        payload = response.read(1_200_000)
    return payload.decode("utf-8", errors="replace")


def discover_hosts_via_crawl(domain: str, timeout: float, max_pages: int) -> set[str]:
    seeds = [f"https://{domain}", f"http://{domain}"]
    queue = deque(seeds)
    visited: set[str] = set()
    found: set[str] = {domain}

    while queue and len(visited) < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        try:
            html = fetch_text(url, timeout)
        except Exception:  # noqa: BLE001
            continue
        if not html:
            continue

        extractor = LinkExtractor()
        try:
            extractor.feed(html)
        except Exception:  # noqa: BLE001
            pass

        # Extract domains that appear in plain text/JS too.
        for match in re.findall(r"\b([a-z0-9][a-z0-9.-]*\.[a-z]{2,})\b", html.lower()):
            if in_scope(match, domain):
                found.add(match)

        for raw_link in extractor.links:
            absolute = urljoin(url, raw_link)
            parsed = urlparse(absolute)
            host = normalize_host(parsed.hostname)
            if not in_scope(host, domain):
                continue
            if host:
                found.add(host)

            # Continue crawling only internal HTTP(S) pages.
            if parsed.scheme in {"http", "https"}:
                clean_url = f"{parsed.scheme}://{host}{parsed.path or '/'}"
                if parsed.query:
                    clean_url = f"{clean_url}?{parsed.query}"
                if clean_url not in visited:
                    queue.append(clean_url)

    return found


def resolve_host(host: str) -> tuple[list[str], str | None]:
    try:
        info = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        return [], f"DNS resolution failed: {exc}"
    except Exception as exc:  # noqa: BLE001
        return [], f"DNS error: {exc}"

    ips = sorted({item[4][0] for item in info if item and item[4]})
    return ips, None


def first_attr(value: tuple[tuple[str, str], ...] | tuple | None, key: str) -> str | None:
    if not value:
        return None
    for pair in value:
        if isinstance(pair, tuple) and len(pair) == 2 and pair[0] == key:
            return str(pair[1])
    return None


def detect_stunnel_signals(cert_subject: str | None, tls_version: str | None) -> tuple[bool, str]:
    if not cert_subject:
        return False, ""

    cn_lower = cert_subject.lower()
    signals = []

    # Common stunnel default/generic patterns
    if "localhost" in cn_lower or "localdomain" in cn_lower:
        signals.append("localhost/localdomain in CN")
    if "stunnel" in cn_lower:
        signals.append("stunnel in CN")
    if "server" in cn_lower and len(cn_lower.split(".")) <= 2:
        signals.append("generic server CN")
    if cn_lower.startswith("*.") and ("local" in cn_lower or len(cn_lower.split(".")) <= 3):
        signals.append("wildcard generic/local")
    if cn_lower in {"example.com", "test.com", "invalid", "selfsigned"}:
        signals.append("placeholder CN")

    # Older stunnel often sticks to TLS 1.2 or lower
    if tls_version and tls_version in {"TLSv1", "TLSv1.1", "TLSv1.2"}:
        signals.append(f"older TLS: {tls_version}")

    # Self-signed or same subject/issuer
    # Note: issuer check is in check_ssl, but we can add more if needed

    if signals:
        return True, ", ".join(signals)
    return False, ""


def check_ssl(host: str, port: int, timeout: float) -> dict[str, str | bool | None]:
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
                    subject = first_attr(subject_raw[-1] if subject_raw else (), "commonName")  # Last tuple is usually CN
                    issuer = first_attr(issuer_raw[-1] if issuer_raw else (), "commonName")
                tls_version = tls.version()

                suspected, signals = detect_stunnel_signals(subject, tls_version)
                is_self_signed = subject == issuer if subject and issuer else False
                if is_self_signed:
                    signals = signals + ", self-signed" if signals else "self-signed"

                return {
                    "ssl_ok": True,
                    "tls_version": tls_version,
                    "cert_subject": subject,
                    "cert_issuer": issuer,
                    "cert_not_after": cert.get("notAfter") if cert else None,
                    "suspected_stunnel": suspected or is_self_signed,
                    "stunnel_signals": signals,
                    "error": None,
                }
    except Exception as exc:  # noqa: BLE001
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


def scan_host(host: str, ports: list[int], timeout: float, ssl_enabled: bool) -> list[HostResult]:
    ips, dns_error = resolve_host(host)
    if not ssl_enabled:
        return [HostResult(host=host, ips=ips, error=dns_error)]

    # If DNS fails, still return one line for visibility.
    if dns_error:
        return [HostResult(host=host, ips=[], error=dns_error)]

    rows: list[HostResult] = []
    for port in ports:
        ssl_data = check_ssl(host, port, timeout)
        rows.append(
            HostResult(
                host=host,
                ips=ips,
                ssl_port=port,
                ssl_ok=bool(ssl_data["ssl_ok"]),
                tls_version=ssl_data["tls_version"],  # type: ignore[arg-type]
                cert_subject=ssl_data["cert_subject"],  # type: ignore[arg-type]
                cert_issuer=ssl_data["cert_issuer"],  # type: ignore[arg-type]
                cert_not_after=ssl_data["cert_not_after"],  # type: ignore[arg-type]
                suspected_stunnel=ssl_data["suspected_stunnel"],  # type: ignore[arg-type]
                stunnel_signals=ssl_data["stunnel_signals"],  # type: ignore[arg-type]
                error=ssl_data["error"],  # type: ignore[arg-type]
            )
        )
    return rows


def parse_ports(raw: str) -> list[int]:
    ports: list[int] = []
    for part in raw.split(","):
        piece = part.strip()
        if not piece:
            continue
        p = int(piece)
        if p < 1 or p > 65535:
            raise ValueError(f"Invalid port: {piece}")
        ports.append(p)
    return sorted(set(ports))


def save_csv(results: Iterable[HostResult], output: Path) -> None:
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
            item["suspected_stunnel"] = "Yes" if row.suspected_stunnel else "No" if row.suspected_stunnel is False else ""
            writer.writerow(item)


def save_json(results: Iterable[HostResult], output: Path) -> None:
    data = [asdict(r) for r in results]
    with output.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def print_summary(domain: str, hosts: set[str], results: list[HostResult]) -> None:
    resolved = {r.host for r in results if r.ips}
    ssl_ok = [r for r in results if r.ssl_ok]
    suspected = [r for r in results if r.suspected_stunnel]
    print(f"[{now_utc()}] Domain: {domain}")
    print(f"Hosts discovered: {len(hosts)}")
    print(f"Hosts resolved: {len(resolved)}")
    if ssl_ok:
        print(f"TLS checks OK: {len(ssl_ok)}")
    if suspected:
        print(f"Suspected stunnel-like: {len(suspected)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authorized domain/subdomain audit (passive + DNS + optional TLS checks with stunnel heuristics)."
    )
    parser.add_argument("--domain", help="Target root domain you own/control (e.g. example.com).")
    parser.add_argument("--wordlist", help="Optional path to subdomain wordlist.")
    parser.add_argument(
        "--ports",
        help="Comma-separated ports for TLS check (used with --check-ssl). Example: 443,8443",
    )
    parser.add_argument("--check-ssl", action="store_true", help="Run TLS handshake checks on discovered hosts.")
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS, help=f"Worker threads (default: {DEFAULT_THREADS}).")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"Socket timeout in seconds (default: {DEFAULT_TIMEOUT}).")
    parser.add_argument(
        "--max-crawl-pages",
        type=int,
        default=DEFAULT_MAX_CRAWL_PAGES,
        help=f"Maximum internal pages to crawl for discovering in-scope domains (default: {DEFAULT_MAX_CRAWL_PAGES}).",
    )
    parser.add_argument("--output", help="Output file (.csv or .json).")
    args = parser.parse_args()

    domain_input = args.domain
    if not domain_input:
        domain_input = input("Dominio (ex: example.com): ").strip()
    if not domain_input:
        print("Dominio invalido.", file=sys.stderr)
        return 2

    ports_input = args.ports
    if not ports_input:
        ports_input = input("Portas TLS separadas por virgula [443]: ").strip() or "443"

    try:
        domain = normalize_domain(domain_input)
        ports = parse_ports(ports_input)
    except ValueError as exc:
        print(f"Entrada invalida: {exc}", file=sys.stderr)
        return 2

    hosts: set[str] = {domain}
    hosts.update(fetch_crtsh_hosts(domain, args.timeout))
    hosts.update(discover_hosts_via_crawl(domain, args.timeout, max(1, args.max_crawl_pages)))

    if args.wordlist:
        wpath = Path(args.wordlist)
        if not wpath.exists():
            print(f"Wordlist not found: {wpath}", file=sys.stderr)
            return 2
        hosts.update(load_wordlist(wpath, domain))

    results: list[HostResult] = []
    with ThreadPoolExecutor(max_workers=max(1, args.threads)) as executor:
        futures = [executor.submit(scan_host, h, ports, args.timeout, args.check_ssl) for h in sorted(hosts)]
        for future in as_completed(futures):
            results.extend(future.result())

    output_input = args.output
    if not output_input:
        suggested = default_output_name()
        output_input = input(f"Nome do arquivo de saida (Enter para {suggested}): ").strip() or suggested

    if "." not in Path(output_input).name:
        output_input = f"{output_input}.csv"

    results.sort(key=lambda r: (r.host, r.ssl_port or 0))
    output = Path(output_input)
    if output.suffix.lower() == ".json":
        save_json(results, output)
    else:
        save_csv(results, output)

    print_summary(domain, hosts, results)
    print(f"Saved: {output.resolve()}")
    print("Use only on assets you own or have explicit written authorization to test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
