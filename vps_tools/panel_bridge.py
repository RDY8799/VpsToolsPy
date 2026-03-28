import json
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone

from vps_tools.core.system import SystemActions, SystemInfo
from vps_tools.core.users import UserManager
from vps_tools.services.badvpn import BadVPNService
from vps_tools.services.dropbear import DropbearService
from vps_tools.services.hysteria import HysteriaService
from vps_tools.services.openclaw import OpenClawService
from vps_tools.services.openvpn import OpenVPNService
from vps_tools.services.shadowsocks import ShadowSocksService
from vps_tools.services.squid import SquidService
from vps_tools.services.sslh import SSLHService
from vps_tools.services.stunnel import StunnelService
from vps_tools.services.trojan import TrojanService
from vps_tools.services.vnc import VNCService
from vps_tools.services.xray import XrayService


SERVICE_CATALOG = {
    "SQUID": {"label": "Squid Proxy", "family": "proxy", "factory": SquidService},
    "SSLH": {"label": "SSLH", "family": "multiplexer", "factory": SSLHService},
    "STUNNEL": {"label": "Stunnel", "family": "tunnel", "factory": StunnelService},
    "DROPBEAR": {"label": "Dropbear", "family": "remote", "factory": DropbearService},
    "OPENVPN": {"label": "OpenVPN", "family": "vpn", "factory": OpenVPNService},
    "OPENCLAW": {"label": "OpenClaw", "family": "ops", "factory": OpenClawService},
    "SHADOWSOCKS": {"label": "ShadowSocks", "family": "proxy", "factory": ShadowSocksService},
    "XRAY": {"label": "Xray", "family": "vpn", "factory": XrayService},
    "HYSTERIA": {"label": "Hysteria", "family": "vpn", "factory": HysteriaService},
    "BADVPN": {"label": "BadVPN", "family": "tunnel", "factory": BadVPNService},
    "TROJAN": {"label": "Trojan", "family": "vpn", "factory": TrojanService},
    "VNC": {"label": "VNC", "family": "remote", "factory": VNCService},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(payload: dict):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _strip_rich(text: str) -> str:
    value = text or ""
    value = re.sub(r"\[[^\]]+\]", "", value)
    return value.strip()


def _progress_callback(completed=None, description=""):
    _emit(
        {
            "type": "progress",
            "percent": int(completed or 0),
            "message": _strip_rich(description),
            "timestamp": _utc_now(),
        }
    )


def _result(ok: bool, data):
    _emit(
        {
            "type": "result",
            "ok": bool(ok),
            "data": data,
            "timestamp": _utc_now(),
        }
    )


def _error(message: str, details: str = ""):
    _emit(
        {
            "type": "result",
            "ok": False,
            "data": {
                "message": message,
                "details": details,
            },
            "timestamp": _utc_now(),
        }
    )


def _git_short_head(repo_dir: str) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo_dir,
        )
        if result.returncode == 0:
            return (result.stdout or "").strip() or "unknown"
    except Exception:
        pass
    return "unknown"


def _service_state(service_name: str) -> dict:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            check=False,
        )
        status = (result.stdout or result.stderr or "").strip() or "unknown"
        return {
            "service": service_name,
            "active": result.returncode == 0 and status == "active",
            "status": status,
        }
    except Exception:
        return {
            "service": service_name,
            "active": False,
            "status": "unsupported",
        }


def _parse_open_ports() -> list[dict]:
    commands = [
        ["ss", "-lntp"],
        ["ss", "-lnup"],
    ]
    entries: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                continue
            for raw_line in (result.stdout or "").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("State") or line.startswith("Netid"):
                    continue
                parts = re.split(r"\s+", line)
                if len(parts) < 5:
                    continue
                local_address = parts[3]
                process = " ".join(parts[5:]) if len(parts) > 5 else ""
                host = local_address
                port = ""
                if ":" in local_address:
                    host, port = local_address.rsplit(":", 1)
                key = (parts[0], host, port)
                if key in seen:
                    continue
                seen.add(key)
                entries.append(
                    {
                        "protocol": parts[0],
                        "host": host,
                        "port": port,
                        "process": process,
                    }
                )
        except Exception:
            continue
    entries.sort(key=lambda item: (item.get("port", ""), item.get("protocol", "")))
    return entries


def _component_status() -> list[dict]:
    web_db = SystemActions.web_db_panel_status()
    admin_panel = (
        SystemActions.admin_web_panel_status()
        if hasattr(SystemActions, "admin_web_panel_status")
        else {"installed": False, "running": False, "service_name": "vps-tools-admin-panel"}
    )
    components = [
        ("postgresql", "PostgreSQL", _service_state("postgresql")),
        ("mysql", "MySQL", _service_state("mysql")),
        ("mariadb", "MariaDB", _service_state("mariadb")),
        ("mongod", "MongoDB", _service_state("mongod")),
        ("redis-server", "Redis", _service_state("redis-server")),
        ("nginx", "Nginx", _service_state("nginx")),
        ("docker", "Docker", _service_state("docker")),
        ("certbot.timer", "Certbot", _service_state("certbot.timer")),
    ]
    data = [
        {
            "key": key,
            "name": label,
            "installed": status["status"] != "unknown",
            "active": status["active"],
            "status": status["status"],
        }
        for key, label, status in components
    ]
    data.append(
        {
            "key": "web_db_panel",
            "name": "Painel Web de Bancos",
            "installed": bool(web_db.get("installed")),
            "active": bool(web_db.get("running")),
            "status": "active" if web_db.get("running") else "inactive",
        }
    )
    data.append(
        {
            "key": "admin_web_panel",
            "name": "Painel Web Administrativo",
            "installed": bool(admin_panel.get("installed")),
            "active": bool(admin_panel.get("running")),
            "status": "active" if admin_panel.get("running") else "inactive",
        }
    )
    return data


def _safe_call(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _normalize_ports(value):
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "", [])]
    if value in (None, "", []):
        return []
    return [str(value)]


def _service_instance(service_key: str):
    meta = SERVICE_CATALOG.get((service_key or "").upper())
    if not meta:
        return None
    return meta["factory"]()


def _service_snapshot(service_key: str) -> dict:
    catalog_key = (service_key or "").upper()
    meta = SERVICE_CATALOG[catalog_key]
    service = meta["factory"]()
    installed = bool(_safe_call(service.is_installed, False))
    running = bool(_safe_call(service.is_running, False))
    ports = _normalize_ports(_safe_call(service.get_ports, []))
    details = _safe_call(getattr(service, "get_status_info", None), {}) if hasattr(service, "get_status_info") else {}
    clients = _safe_call(service.list_clients, []) if hasattr(service, "list_clients") else []
    return {
        "key": catalog_key,
        "name": meta["label"],
        "family": meta["family"],
        "installed": installed,
        "active": running,
        "status": "active" if running else ("installed" if installed else "not_installed"),
        "ports": ports,
        "details": details or {},
        "clients": clients if isinstance(clients, list) else [],
        "system_service_name": getattr(service, "system_service_name", ""),
    }


def _managed_services() -> list[dict]:
    services = []
    for service_key in SERVICE_CATALOG:
        try:
            services.append(_service_snapshot(service_key))
        except Exception as exc:
            meta = SERVICE_CATALOG[service_key]
            services.append(
                {
                    "key": service_key,
                    "name": meta["label"],
                    "family": meta["family"],
                    "installed": False,
                    "active": False,
                    "status": "error",
                    "ports": [],
                    "details": {"message": str(exc)},
                    "clients": [],
                    "system_service_name": "",
                }
            )
    return services


def _parse_expiry(expiry_value: str):
    text = (expiry_value or "").strip()
    if not text or text.lower() in {"never", "unknown"}:
        return None
    for fmt in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _ssh_user_summary() -> dict:
    users = []
    for item in UserManager.list_users():
        users.append(
            {
                "username": item.get("username", ""),
                "uid": item.get("uid"),
                "expiry": item.get("expiry", "Unknown"),
                "limit": item.get("limit", "?"),
                "connected": int(item.get("connected", 0) or 0),
            }
        )
    users.sort(key=lambda item: item["username"])
    expiring_soon = 0
    for user in users:
        parsed = _parse_expiry(user.get("expiry", ""))
        if parsed is None:
            continue
        if (parsed - datetime.now()).days <= 7:
            expiring_soon += 1
    return {
        "count": len(users),
        "connected_count": sum(1 for user in users if user.get("connected", 0) > 0),
        "expiring_soon_count": expiring_soon,
        "items": users,
    }


def _backup_jobs_summary() -> dict:
    jobs = []
    healthy_count = 0
    attention_count = 0
    for job in SystemActions.list_db_backup_jobs():
        last_status = job.get("last_status") or {}
        restore_status = job.get("last_restore_test") or {}
        last_state = str(last_status.get("status") or last_status.get("result") or "unknown").lower()
        healthy = last_state in {"ok", "success", "completed"} and str(job.get("timer_enabled", "")).strip() == "enabled"
        if healthy:
            healthy_count += 1
        else:
            attention_count += 1
        jobs.append(
            {
                "job_name": job.get("job_name") or job.get("safe_job") or "",
                "engine": job.get("engine", ""),
                "db_name": job.get("db_name", ""),
                "backup_dir": job.get("backup_dir", ""),
                "timer_active": job.get("timer_active", ""),
                "timer_enabled": job.get("timer_enabled", ""),
                "last_status": last_status,
                "last_restore_test": restore_status,
                "health": "healthy" if healthy else "attention",
                "last_state": last_state,
                "restore_state": str(restore_status.get("status") or "not_tested").lower(),
            }
        )
    return {
        "count": len(jobs),
        "healthy_count": healthy_count,
        "attention_count": attention_count,
        "items": jobs,
    }


def _dr_summary() -> dict:
    profiles = SystemActions.list_dr_profiles()
    monitors = []
    monitor_dir = SystemActions._dr_monitoring_dir()
    try:
        if os.path.isdir(monitor_dir):
            for name in sorted(os.listdir(monitor_dir)):
                config_path = os.path.join(monitor_dir, name, "monitor.json")
                if not os.path.exists(config_path):
                    continue
                config = SystemActions._read_json_file(config_path, default={}) or {}
                if not isinstance(config, dict):
                    continue
                ok, status = SystemActions.dr_monitor_status(config.get("monitor_name", name))
                monitors.append(
                    {
                        "monitor_name": config.get("monitor_name", name),
                        "services": config.get("service_names", []),
                        "domains": config.get("domains", []),
                        "backup_jobs": config.get("backup_jobs", []),
                        "status": status if ok else {"message": status},
                    }
                )
    except Exception:
        monitors = []
    return {
        "profiles_count": len(profiles),
        "monitors_count": len(monitors),
        "profiles": profiles,
        "monitors": monitors,
    }


def collect_overview() -> dict:
    repo_dir = SystemActions._repo_root_dir()
    preferred_python = SystemActions._preferred_python_binary()
    admin_panel = (
        SystemActions.admin_web_panel_status()
        if hasattr(SystemActions, "admin_web_panel_status")
        else {"installed": False, "running": False}
    )
    managed_services = _managed_services()
    users = _ssh_user_summary()
    backups = _backup_jobs_summary()
    dr = _dr_summary()
    return {
        "script": {
            "name": "VpsToolsPy",
            "version": _git_short_head(repo_dir),
            "repo_dir": repo_dir,
            "python": preferred_python,
            "os": SystemInfo.get_os_info(),
            "public_ip": SystemInfo.get_ip(),
            "hostname": os.uname().nodename if hasattr(os, "uname") else "unknown",
        },
        "system": {
            "cpu_percent": SystemInfo.get_cpu_usage(),
            "ram": SystemInfo.get_ram_info(),
            "swap": SystemInfo.get_swap_info(),
            "timestamp": _utc_now(),
        },
        "components": _component_status(),
        "open_ports": _parse_open_ports(),
        "panels": {
            "database": SystemActions.web_db_panel_status(),
            "administrative": admin_panel,
        },
        "managed_services": managed_services,
        "users": users,
        "backups": backups,
        "dr": dr,
        "highlights": {
            "managed_services_active": sum(1 for item in managed_services if item.get("active")),
            "managed_services_installed": sum(1 for item in managed_services if item.get("installed")),
            "ssh_users": users["count"],
            "backup_jobs": backups["count"],
            "dr_profiles": dr["profiles_count"],
            "dr_monitors": dr["monitors_count"],
        },
    }


def _field(name, label, field_type="text", default="", required=True, **extra):
    payload = {
        "name": name,
        "label": label,
        "type": field_type,
        "default": default,
        "required": required,
    }
    payload.update(extra)
    return payload


def _action_catalog() -> list[dict]:
    repo_dir = SystemActions._repo_root_dir()
    return [
        {
            "id": "services.manage",
            "category": "services",
            "categoryLabel": "Servicos",
            "label": "Operar servico gerenciado",
            "description": "Executa start, stop, restart, status ou logs nos servicos expostos pelo painel.",
            "featured": True,
            "schema": [
                _field("service_key", "Servico", "select", "OPENCLAW", True, options=list(SERVICE_CATALOG.keys())),
                _field("operation", "Operacao", "select", "status", True, options=["status", "start", "stop", "restart", "logs", "uninstall"]),
                _field("lines", "Linhas de log", "number", 120, False),
            ],
        },
        {
            "id": "users.create",
            "category": "users",
            "categoryLabel": "Usuarios",
            "label": "Criar usuario SSH",
            "description": "Cria um usuario com senha, limite de conexoes e validade em dias.",
            "featured": True,
            "schema": [
                _field("username", "Usuario", "text", "operador", True),
                _field("password", "Senha", "password", "", True, secret=True),
                _field("days", "Dias ate expirar", "number", 30, True),
                _field("limit", "Limite de conexoes", "number", 2, True),
            ],
        },
        {
            "id": "users.change_password",
            "category": "users",
            "categoryLabel": "Usuarios",
            "label": "Alterar senha SSH",
            "description": "Atualiza a senha do usuario selecionado.",
            "schema": [
                _field("username", "Usuario", "text", "", True),
                _field("new_password", "Nova senha", "password", "", True, secret=True),
            ],
        },
        {
            "id": "users.change_limit",
            "category": "users",
            "categoryLabel": "Usuarios",
            "label": "Alterar limite de conexoes",
            "description": "Ajusta o limite salvo para o usuario SSH.",
            "schema": [
                _field("username", "Usuario", "text", "", True),
                _field("new_limit", "Novo limite", "number", 2, True),
            ],
        },
        {
            "id": "users.change_expiry",
            "category": "users",
            "categoryLabel": "Usuarios",
            "label": "Alterar expiracao",
            "description": "Define uma nova data de expiracao no formato ano, mes e dia.",
            "schema": [
                _field("username", "Usuario", "text", "", True),
                _field("year", "Ano", "number", datetime.now().year, True),
                _field("month", "Mes", "number", datetime.now().month, True),
                _field("day", "Dia", "number", datetime.now().day, True),
            ],
        },
        {
            "id": "users.disconnect",
            "category": "users",
            "categoryLabel": "Usuarios",
            "label": "Desconectar usuario",
            "description": "Derruba as sessoes em execucao do usuario informado.",
            "schema": [_field("username", "Usuario", "text", "", True)],
        },
        {
            "id": "users.delete",
            "category": "users",
            "categoryLabel": "Usuarios",
            "label": "Excluir usuario SSH",
            "description": "Remove o usuario e os metadados salvos pelo script.",
            "dangerous": True,
            "schema": [_field("username", "Usuario", "text", "", True)],
        },
        {
            "id": "users.backup",
            "category": "users",
            "categoryLabel": "Usuarios",
            "label": "Backup de usuarios",
            "description": "Exporta usuarios gerenciados para um arquivo de backup.",
            "schema": [_field("filename", "Nome base do backup", "text", "usuarios", True)],
        },
        {
            "id": "users.restore",
            "category": "users",
            "categoryLabel": "Usuarios",
            "label": "Restaurar backup de usuarios",
            "description": "Restaura usuarios a partir de um caminho de backup existente.",
            "dangerous": True,
            "schema": [_field("filepath", "Caminho completo do backup", "text", "", True)],
        },
        {
            "id": "database.install_postgresql",
            "category": "database",
            "categoryLabel": "Banco",
            "label": "Instalar PostgreSQL",
            "description": "Cria o banco PostgreSQL local e prepara a string JDBC para o backend.",
            "featured": True,
            "schema": [
                _field("db_name", "Nome do banco", "text", "hospital", True),
                _field("db_user", "Usuario do banco", "text", "hospital_app", True),
                _field("db_password", "Senha do usuario", "password", "", True, secret=True),
                _field("listen_addresses", "Bind do PostgreSQL", "text", "localhost", True),
                _field("jdbc_host", "Host JDBC", "text", "127.0.0.1", True),
                _field("jdbc_port", "Porta JDBC", "number", 5432, True),
            ],
        },
        {
            "id": "database.allow_postgresql_panel",
            "category": "database",
            "categoryLabel": "Banco",
            "label": "Liberar PostgreSQL para painel Docker local",
            "description": "Ajusta o PostgreSQL para o painel web de bancos sem expor a porta publicamente.",
            "schema": [
                _field("app_dir", "Diretorio do painel", "text", "/opt/vps-tools-db-panel", True),
                _field("docker_network_name", "Rede Docker (opcional)", "text", "", False),
                _field("db_name", "Banco liberado", "text", "hospital", True),
                _field("db_user", "Usuario liberado", "text", "hospital_app", True),
                _field("auth_method", "Metodo de autenticacao", "select", "scram-sha-256", True, options=["scram-sha-256", "md5", "password", "trust", "reject"]),
                _field("listen_host_override", "Host do gateway (opcional)", "text", "", False),
                _field("docker_cidr_override", "CIDR Docker (opcional)", "text", "", False),
                _field("postgres_port", "Porta PostgreSQL", "number", 5432, True),
            ],
        },
        {
            "id": "database.install_mysql",
            "category": "database",
            "categoryLabel": "Banco",
            "label": "Instalar MySQL",
            "description": "Provisiona MySQL local e cria banco e usuario.",
            "schema": [
                _field("db_name", "Nome do banco", "text", "appdb", True),
                _field("db_user", "Usuario do banco", "text", "app_user", True),
                _field("db_password", "Senha do usuario", "password", "", True, secret=True),
                _field("bind_address", "Bind", "text", "127.0.0.1", True),
                _field("port", "Porta", "number", 3306, True),
                _field("grant_host", "Host permitido", "text", "localhost", True),
            ],
        },
        {
            "id": "database.install_mariadb",
            "category": "database",
            "categoryLabel": "Banco",
            "label": "Instalar MariaDB",
            "description": "Provisiona MariaDB local e cria banco e usuario.",
            "schema": [
                _field("db_name", "Nome do banco", "text", "appdb", True),
                _field("db_user", "Usuario do banco", "text", "app_user", True),
                _field("db_password", "Senha do usuario", "password", "", True, secret=True),
                _field("bind_address", "Bind", "text", "127.0.0.1", True),
                _field("port", "Porta", "number", 3306, True),
                _field("grant_host", "Host permitido", "text", "localhost", True),
            ],
        },
        {
            "id": "database.install_mongodb",
            "category": "database",
            "categoryLabel": "Banco",
            "label": "Instalar MongoDB",
            "description": "Provisiona MongoDB local com autenticacao opcional.",
            "schema": [
                _field("app_db", "Nome do banco", "text", "appdb", True),
                _field("app_user", "Usuario", "text", "app_user", True),
                _field("app_password", "Senha", "password", "", True, secret=True),
                _field("bind_ip", "Bind IP", "text", "127.0.0.1", True),
                _field("port", "Porta", "number", 27017, True),
                _field("enable_auth", "Ativar autenticacao", "boolean", True, True),
            ],
        },
        {
            "id": "database.install_redis",
            "category": "database",
            "categoryLabel": "Banco",
            "label": "Configurar Redis",
            "description": "Instala Redis local para cache, sessao e filas.",
            "schema": [
                _field("bind_address", "Bind", "text", "127.0.0.1", True),
                _field("port", "Porta", "number", 6379, True),
                _field("password", "Senha", "password", "", False, secret=True),
            ],
        },
        {
            "id": "backend.prepare_spring_boot",
            "category": "backend",
            "categoryLabel": "Backend",
            "label": "Preparar backend Spring Boot",
            "description": "Prepara Java 17, diretorios, variaveis e comandos do backend Spring Boot.",
            "featured": True,
            "schema": [
                _field("app_dir", "Diretorio da aplicacao", "text", "/opt/celiora", True),
                _field("owner_user", "Usuario dono", "text", "ubuntu", True),
                _field("repo_url", "URL do repositorio Git", "text", "", False),
                _field("repo_dir", "Diretorio do repositorio", "text", "/opt/celiora-src", True),
                _field("jar_name", "Nome do JAR", "text", "app.jar", True),
                _field("app_port", "Porta da aplicacao", "number", 8080, True),
                _field("datasource_url", "SPRING_DATASOURCE_URL", "text", "jdbc:postgresql://127.0.0.1:5432/hospital", True),
                _field("datasource_username", "SPRING_DATASOURCE_USERNAME", "text", "hospital_app", True),
                _field("datasource_password", "SPRING_DATASOURCE_PASSWORD", "password", "", True, secret=True),
                _field("root_owner_email", "ROOT_OWNER_EMAIL", "text", "admin@example.com", True),
                _field("allowed_origin_patterns", "APP_ALLOWED_ORIGIN_PATTERNS", "text", "http://localhost:5173,http://127.0.0.1:5173", True),
                _field("jwt_secret", "APP_JWT_SECRET", "password", "", True, secret=True),
                _field("trust_forward_headers", "APP_TRUST_FORWARD_HEADERS", "boolean", False, True),
            ],
        },
        {
            "id": "infra.configure_nginx",
            "category": "infra",
            "categoryLabel": "Infra",
            "label": "Configurar Nginx Reverse Proxy",
            "description": "Publica uma aplicacao local por dominio ou server_name no Nginx.",
            "schema": [
                _field("site_name", "Nome do site", "text", "app", True),
                _field("server_names", "server_name (separados por espaco)", "text", "example.com", True),
                _field("upstream_host", "Host upstream", "text", "127.0.0.1", True),
                _field("upstream_port", "Porta upstream", "number", 8080, True),
                _field("client_max_body_size", "client_max_body_size", "text", "20m", True),
                _field("proxy_buffering", "Ativar proxy_buffering", "boolean", False, True),
            ],
        },
        {
            "id": "infra.setup_https",
            "category": "infra",
            "categoryLabel": "Infra",
            "label": "Configurar HTTPS com Certbot",
            "description": "Emite e instala certificado HTTPS com o plugin do Nginx para dominios reais; nao use IP puro.",
            "schema": [
                _field("domains", "Dominios (separados por espaco, nao use IP)", "text", "example.com", True),
                _field("email", "E-mail Let's Encrypt", "text", "admin@example.com", True),
                _field("redirect_https", "Redirecionar HTTP para HTTPS", "boolean", True, True),
            ],
        },
        {
            "id": "panels.install_web_db_panel",
            "category": "panels",
            "categoryLabel": "Paineis",
            "label": "Instalar painel web de bancos",
            "description": "Instala o painel Docker com Adminer, pgAdmin e Redis Insight.",
            "schema": [
                _field("app_dir", "Diretorio do painel", "text", "/opt/vps-tools-db-panel", True),
                _field("panel_port", "Porta local", "number", 18090, True),
                _field("enable_adminer", "Ativar Adminer", "boolean", True, True),
                _field("enable_pgadmin", "Ativar pgAdmin 4", "boolean", True, True),
                _field("enable_redisinsight", "Ativar Redis Insight", "boolean", True, True),
                _field("pgadmin_email", "Email do pgAdmin", "text", "admin@localhost", True),
                _field("pgadmin_password", "Senha do pgAdmin", "password", "", False, secret=True),
            ],
        },
        {
            "id": "panels.manage_web_db_panel",
            "category": "panels",
            "categoryLabel": "Paineis",
            "label": "Gerenciar painel web de bancos",
            "description": "Executa start, stop, restart, status ou uninstall do painel Docker.",
            "schema": [
                _field("app_dir", "Diretorio do painel", "text", "/opt/vps-tools-db-panel", True),
                _field("action", "Acao", "select", "status", True, options=["status", "start", "stop", "restart", "uninstall"]),
                _field("remove_files", "Remover arquivos ao desinstalar", "boolean", False, True),
            ],
        },
        {
            "id": "panels.install_admin_web_panel",
            "category": "panels",
            "categoryLabel": "Paineis",
            "label": "Instalar painel administrativo",
            "description": "Instala ou reconstrui o painel administrativo com validacao de startup.",
            "featured": True,
            "schema": [
                _field("app_dir", "Diretorio do painel", "text", "/opt/vps-tools-admin-panel", True),
                _field("panel_port", "Porta local", "number", 18600, True),
                _field("panel_host", "Bind do painel", "text", "127.0.0.1", True),
                _field("login_user", "Usuario inicial", "text", "admin", True),
                _field("login_password", "Senha inicial", "password", "", False, secret=True),
                _field("service_name", "Nome do servico", "text", "vps-tools-admin-panel", True),
                _field("run_user", "Usuario do servico", "text", "root", True),
            ],
        },
        {
            "id": "panels.update_admin_web_panel",
            "category": "panels",
            "categoryLabel": "Paineis",
            "label": "Atualizar painel administrativo",
            "description": "Reconstrui o painel, reinicia o servico e valida a subida com health-check.",
            "featured": True,
            "schema": [
                _field("app_dir", "Diretorio do painel", "text", "/opt/vps-tools-admin-panel", True),
                _field("service_name", "Nome do servico", "text", "vps-tools-admin-panel", True),
            ],
        },
        {
            "id": "panels.manage_admin_web_panel",
            "category": "panels",
            "categoryLabel": "Paineis",
            "label": "Gerenciar painel administrativo",
            "description": "Executa start, stop, restart, status, rebuild ou uninstall.",
            "schema": [
                _field("app_dir", "Diretorio do painel", "text", "/opt/vps-tools-admin-panel", True),
                _field("service_name", "Nome do servico", "text", "vps-tools-admin-panel", True),
                _field("action", "Acao", "select", "status", True, options=["status", "start", "stop", "restart", "rebuild", "uninstall"]),
                _field("remove_files", "Remover arquivos ao desinstalar", "boolean", False, True),
            ],
        },
        {
            "id": "services.install_openclaw",
            "category": "services",
            "categoryLabel": "Servicos",
            "label": "Instalar OpenClaw",
            "description": "Executa a instalacao oficial do OpenClaw pelo painel.",
            "schema": [],
        },
        {
            "id": "services.update_openclaw",
            "category": "services",
            "categoryLabel": "Servicos",
            "label": "Atualizar OpenClaw",
            "description": "Executa o fluxo oficial de atualizacao do OpenClaw.",
            "schema": [],
        },
        {
            "id": "services.install_vnc",
            "category": "services",
            "categoryLabel": "Servicos",
            "label": "Instalar VNC",
            "description": "Provisiona VNC com porta e senha customizaveis.",
            "schema": [
                _field("port", "Porta VNC", "number", 5901, True),
                _field("password", "Senha VNC", "password", "", False, secret=True),
            ],
        },
        {
            "id": "services.change_vnc_port",
            "category": "services",
            "categoryLabel": "Servicos",
            "label": "Alterar porta VNC",
            "description": "Regrava o servico principal do VNC com uma nova porta.",
            "schema": [_field("port", "Nova porta", "number", 5901, True)],
        },
        {
            "id": "services.change_vnc_password",
            "category": "services",
            "categoryLabel": "Servicos",
            "label": "Alterar senha VNC",
            "description": "Atualiza a senha do arquivo do VNC.",
            "schema": [_field("password", "Nova senha", "password", "", True, secret=True)],
        },
        {
            "id": "services.configure_vnc_desktop",
            "category": "services",
            "categoryLabel": "Servicos",
            "label": "Configurar desktop VNC",
            "description": "Configura a sessao grafica do VNC para uso administrativo.",
            "schema": [],
        },
        {
            "id": "services.install_openvpn",
            "category": "services",
            "categoryLabel": "Servicos",
            "label": "Instalar OpenVPN",
            "description": "Instala o servidor OpenVPN e gera um cliente inicial.",
            "schema": [
                _field("port", "Porta", "number", 1194, True),
                _field("protocol", "Protocolo", "select", "udp", True, options=["udp", "tcp"]),
                _field("vpn_network", "Rede VPN", "text", "10.8.0.0 255.255.255.0", True),
                _field("dns1", "DNS primario", "text", "1.1.1.1", True),
                _field("dns2", "DNS secundario", "text", "8.8.8.8", True),
                _field("endpoint", "Endpoint publico", "text", "", False),
                _field("use_domain", "Endpoint e dominio", "boolean", False, True),
                _field("client_name", "Cliente inicial", "text", "client", True),
            ],
        },
        {
            "id": "services.openvpn_add_client",
            "category": "services",
            "categoryLabel": "Servicos",
            "label": "Criar cliente OpenVPN",
            "description": "Gera um novo arquivo .ovpn para o cliente informado.",
            "schema": [
                _field("username", "Nome do cliente", "text", "operador", True),
                _field("endpoint", "Endpoint publico", "text", "", False),
                _field("use_domain", "Usar dominio no perfil", "boolean", False, True),
            ],
        },
        {
            "id": "services.openvpn_revoke_client",
            "category": "services",
            "categoryLabel": "Servicos",
            "label": "Revogar cliente OpenVPN",
            "description": "Revoga o certificado do cliente e remove o arquivo .ovpn.",
            "dangerous": True,
            "schema": [_field("username", "Nome do cliente", "text", "", True)],
        },
        {
            "id": "system.update_packages",
            "category": "system",
            "categoryLabel": "Sistema",
            "label": "Atualizar pacotes do sistema",
            "description": "Executa update, upgrade e limpeza do sistema operacional.",
            "featured": True,
            "schema": [],
        },
        {
            "id": "system.update_script",
            "category": "system",
            "categoryLabel": "Sistema",
            "label": "Atualizar script",
            "description": "Executa git fetch/pull no repositorio do VpsToolsPy.",
            "schema": [_field("repo_dir", "Diretorio do repositorio", "text", repo_dir, True)],
        },
        {
            "id": "system.create_menu_command",
            "category": "system",
            "categoryLabel": "Sistema",
            "label": "Criar comando global",
            "description": "Cria um launcher global como menu para abrir o script.",
            "schema": [
                _field("repo_dir", "Diretorio do repositorio", "text", repo_dir, True),
                _field("command_name", "Nome do comando", "text", "menu", True),
            ],
        },
        {
            "id": "system.create_swap",
            "category": "system",
            "categoryLabel": "Sistema",
            "label": "Criar swap",
            "description": "Provisiona um arquivo de swap na VPS.",
            "schema": [
                _field("size_mb", "Tamanho em MB", "number", 1024, True),
                _field("swap_path", "Caminho do swap", "text", "/swapfile", True),
            ],
        },
        {
            "id": "system.systemd_manage",
            "category": "system",
            "categoryLabel": "Sistema",
            "label": "Operar servico systemd",
            "description": "Executa status, logs, start, stop, restart, enable ou disable em qualquer servico systemd.",
            "schema": [
                _field("service_name", "Nome do servico", "text", "nginx", True),
                _field("action", "Acao", "select", "status", True, options=["status", "logs", "start", "stop", "restart", "enable", "disable"]),
                _field("lines", "Linhas de log", "number", 120, False),
            ],
        },
        {
            "id": "system.systemd_create",
            "category": "system",
            "categoryLabel": "Sistema",
            "label": "Criar servico systemd",
            "description": "Cria um novo servico systemd com start e restart automaticos.",
            "schema": [
                _field("service_name", "Nome do servico", "text", "minha-app", True),
                _field("description", "Descricao", "text", "Minha aplicacao", True),
                _field("exec_start", "ExecStart", "text", "/usr/bin/java -jar /opt/app/app.jar", True),
                _field("working_dir", "WorkingDirectory", "text", "/opt/app", True),
                _field("run_user", "Usuario", "text", "ubuntu", True),
                _field("environment_file", "EnvironmentFile", "text", "", False),
                _field("exec_stop", "ExecStop", "text", "", False),
                _field("restart_policy", "Restart", "select", "always", True, options=["always", "on-failure", "no"]),
                _field("restart_sec", "RestartSec", "number", 5, True),
            ],
        },
        {
            "id": "dr.run_backup",
            "category": "dr",
            "categoryLabel": "DR",
            "label": "Executar backup agora",
            "description": "Executa um job de backup ja configurado.",
            "schema": [_field("job_name", "Nome do job", "text", "postgres-prod-diario", True)],
        },
        {
            "id": "dr.backup_status",
            "category": "dr",
            "categoryLabel": "DR",
            "label": "Status do backup",
            "description": "Consulta timer, servico e ultimo resultado do job de backup.",
            "schema": [_field("job_name", "Nome do job", "text", "postgres-prod-diario", True)],
        },
        {
            "id": "dr.restore_test",
            "category": "dr",
            "categoryLabel": "DR",
            "label": "Teste automatico de restore",
            "description": "Restaura um backup PostgreSQL em banco temporario para validar recuperacao.",
            "schema": [
                _field("job_name", "Nome do job", "text", "postgres-prod-diario", True),
                _field("restore_db_name", "Banco temporario (opcional)", "text", "", False),
                _field("keep_restore_db", "Manter banco temporario", "boolean", False, True),
            ],
        },
        {
            "id": "dr.export_config",
            "category": "dr",
            "categoryLabel": "DR",
            "label": "Exportar configuracoes da VPS",
            "description": "Cria pacote com configs do host para recuperacao.",
            "schema": [_field("export_name", "Nome da exportacao", "text", "dr-config", True)],
        },
        {
            "id": "dr.run_monitor",
            "category": "dr",
            "categoryLabel": "DR",
            "label": "Executar monitor DR agora",
            "description": "Executa uma checagem DR imediata.",
            "schema": [_field("monitor_name", "Nome do monitor", "text", "default", True)],
        },
    ]


def _split_csv(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,\n]+", str(value)) if item.strip()]


def _split_words(value: str) -> list[str]:
    return [item for item in re.split(r"[\s,]+", str(value or "").strip()) if item]


def _run_command_sequence(commands: list[list[str]], label: str):
    if not commands:
        return False, {"message": "Nenhum comando disponivel para esta operacao."}
    outputs = []
    total = len(commands)
    for index, command in enumerate(commands, start=1):
        percent = int(((index - 1) / total) * 100)
        _progress_callback(percent, f"{label}: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        outputs.append(
            {
                "command": command,
                "returncode": result.returncode,
                "stdout": (result.stdout or "").strip(),
                "stderr": (result.stderr or "").strip(),
            }
        )
        if result.returncode != 0:
            return False, {
                "message": f"Falha ao executar: {' '.join(command)}",
                "outputs": outputs,
            }
    _progress_callback(100, f"{label}: concluido")
    return True, {
        "message": "Comandos concluidos com sucesso.",
        "outputs": outputs,
    }


def _service_manage(params: dict):
    service_key = str(params.get("service_key", "")).upper()
    operation = str(params.get("operation", "status")).lower()
    lines = int(params.get("lines", 120) or 120)
    service = _service_instance(service_key)
    if service is None:
        return False, {"message": f"Servico nao suportado: {service_key}"}

    if operation == "status":
        return True, _service_snapshot(service_key)

    if operation == "logs":
        if hasattr(service, "read_logs"):
            ok, data = service.read_logs(lines=lines)
            return ok, {
                "service": _service_snapshot(service_key),
                "logs": data,
            }
        service_name = getattr(service, "system_service_name", "")
        if not service_name:
            return False, {"message": "Servico sem leitor de logs disponivel."}
        ok, data = SystemActions.systemd_service_action(service_name=service_name, action="logs", lines=lines)
        return ok, {
            "service": _service_snapshot(service_key),
            "logs": data,
        }

    if operation not in {"start", "stop", "restart", "uninstall"}:
        return False, {"message": f"Operacao nao suportada: {operation}"}

    method = getattr(service, operation, None)
    if method is None:
        return False, {"message": f"Servico sem metodo: {operation}"}

    raw = method()
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[0], bool):
        ok, data = raw
    elif raw is True:
        ok, data = True, {"message": f"Operacao {operation} executada."}
    elif raw is False:
        ok, data = False, {"message": f"Operacao {operation} falhou."}
    else:
        state = _service_snapshot(service_key)
        if operation == "uninstall":
            ok = not state["installed"]
        elif operation == "start":
            ok = state["active"]
        elif operation == "stop":
            ok = not state["active"]
        else:
            ok = state["installed"]
        data = raw

    return ok, {
        "service": _service_snapshot(service_key),
        "operation": operation,
        "result": data,
    }


def _install_openclaw(_: dict):
    service = OpenClawService()
    raw = service.install()
    installed = service.is_installed()
    if raw is True or installed:
        return True, {
            "message": "OpenClaw instalado.",
            "service": _service_snapshot("OPENCLAW"),
        }
    return False, raw


def _update_openclaw(_: dict):
    service = OpenClawService()
    ok, data = service.update()
    return ok, {
        "message": data,
        "service": _service_snapshot("OPENCLAW"),
    }


def _install_vnc(params: dict):
    service = VNCService()
    raw = service.install(port=int(params.get("port", 5901)), password=str(params.get("password", "")))
    ok = service.is_installed()
    return ok, {
        "message": raw if isinstance(raw, str) else "VNC instalado.",
        "service": _service_snapshot("VNC"),
    }


def _configure_vnc_desktop(_: dict):
    service = VNCService()
    ok, data = service.configure_desktop()
    return ok, {
        "message": data,
        "service": _service_snapshot("VNC"),
    }


def _change_vnc_port(params: dict):
    service = VNCService()
    ok, data = service.set_port(int(params.get("port", 5901)))
    return ok, {
        "message": data,
        "service": _service_snapshot("VNC"),
    }


def _change_vnc_password(params: dict):
    service = VNCService()
    ok, data = service.set_password(str(params.get("password", "")))
    return ok, {
        "message": data,
        "service": _service_snapshot("VNC"),
    }


def _install_openvpn(params: dict):
    service = OpenVPNService()
    raw = service.install(
        port=int(params.get("port", 1194)),
        protocol=str(params.get("protocol", "udp")),
        vpn_network=str(params.get("vpn_network", "10.8.0.0 255.255.255.0")),
        dns1=str(params.get("dns1", "1.1.1.1")),
        dns2=str(params.get("dns2", "8.8.8.8")),
        endpoint=str(params.get("endpoint", "")),
        use_domain=bool(params.get("use_domain", False)),
        client_name=str(params.get("client_name", "client")),
    )
    ok = service.is_installed()
    return ok, {
        "message": raw,
        "service": _service_snapshot("OPENVPN"),
    }


def _openvpn_add_client(params: dict):
    service = OpenVPNService()
    username = str(params.get("username", "")).strip()
    raw = service.add_client(
        username=username,
        endpoint=str(params.get("endpoint", "")),
        use_domain=bool(params.get("use_domain", False)),
    )
    ok = username in service.list_clients()
    return ok, {
        "message": raw,
        "service": _service_snapshot("OPENVPN"),
    }


def _openvpn_revoke_client(params: dict):
    service = OpenVPNService()
    username = str(params.get("username", "")).strip()
    raw = service.revoke_client(username)
    ok = raw is True
    return ok, {
        "message": "Cliente revogado." if raw is True else raw,
        "service": _service_snapshot("OPENVPN"),
    }


def _create_user(params: dict):
    username = str(params.get("username", "")).strip()
    result = UserManager.create_user(
        username=username,
        password=str(params.get("password", "")),
        days=int(params.get("days", 30)),
        limit=int(params.get("limit", 2)),
    )
    if result is True:
        return True, {"message": f"Usuario {username} criado com sucesso.", "users": _ssh_user_summary()}
    return False, result


def _delete_user(params: dict):
    username = str(params.get("username", "")).strip()
    result = UserManager.delete_user(username)
    if result is True:
        return True, {"message": f"Usuario {username} removido.", "users": _ssh_user_summary()}
    return False, result


def _disconnect_user(params: dict):
    username = str(params.get("username", "")).strip()
    result = UserManager.disconnect_user(username)
    if result is True:
        return True, {"message": f"Usuario {username} desconectado.", "users": _ssh_user_summary()}
    return False, {"message": f"Falha ao desconectar {username}."}


def _change_user_password(params: dict):
    username = str(params.get("username", "")).strip()
    result = UserManager.change_password(username, str(params.get("new_password", "")))
    if result is True:
        return True, {"message": f"Senha de {username} atualizada.", "users": _ssh_user_summary()}
    return False, result


def _change_user_limit(params: dict):
    username = str(params.get("username", "")).strip()
    result = UserManager.change_limit(username, int(params.get("new_limit", 1)))
    if result is True:
        return True, {"message": f"Limite de {username} atualizado.", "users": _ssh_user_summary()}
    return False, result


def _change_user_expiry(params: dict):
    username = str(params.get("username", "")).strip()
    result = UserManager.change_expiry(
        username,
        int(params.get("year", datetime.now().year)),
        int(params.get("month", datetime.now().month)),
        int(params.get("day", datetime.now().day)),
    )
    if result is True:
        return True, {"message": f"Expiracao de {username} atualizada.", "users": _ssh_user_summary()}
    return False, result


def _backup_users(params: dict):
    path = UserManager.backup_users(str(params.get("filename", "usuarios")).strip() or "usuarios")
    if str(path).startswith("/"):
        return True, {"message": "Backup de usuarios criado.", "path": path}
    return False, {"message": path}


def _restore_users(params: dict):
    filepath = str(params.get("filepath", "")).strip()
    ok = UserManager.restore_backup(filepath)
    if ok:
        return True, {"message": "Backup restaurado com sucesso.", "users": _ssh_user_summary()}
    return False, {"message": "Falha ao restaurar backup de usuarios."}


def _action_handlers() -> dict:
    return {
        "services.manage": _service_manage,
        "services.install_openclaw": _install_openclaw,
        "services.update_openclaw": _update_openclaw,
        "services.install_vnc": _install_vnc,
        "services.configure_vnc_desktop": _configure_vnc_desktop,
        "services.change_vnc_port": _change_vnc_port,
        "services.change_vnc_password": _change_vnc_password,
        "services.install_openvpn": _install_openvpn,
        "services.openvpn_add_client": _openvpn_add_client,
        "services.openvpn_revoke_client": _openvpn_revoke_client,
        "users.create": _create_user,
        "users.delete": _delete_user,
        "users.disconnect": _disconnect_user,
        "users.change_password": _change_user_password,
        "users.change_limit": _change_user_limit,
        "users.change_expiry": _change_user_expiry,
        "users.backup": _backup_users,
        "users.restore": _restore_users,
        "database.install_postgresql": lambda p: SystemActions.install_local_postgresql(
            db_name=p.get("db_name", "hospital"),
            db_user=p.get("db_user", "hospital_app"),
            db_password=p.get("db_password", ""),
            listen_addresses=p.get("listen_addresses", "localhost"),
            jdbc_host=p.get("jdbc_host", "127.0.0.1"),
            jdbc_port=int(p.get("jdbc_port", 5432)),
            progress_callback=_progress_callback,
        ),
        "database.allow_postgresql_panel": lambda p: SystemActions.allow_postgresql_for_local_panel(
            app_dir=p.get("app_dir", "/opt/vps-tools-db-panel"),
            docker_network_name=p.get("docker_network_name", ""),
            db_name=p.get("db_name", "hospital"),
            db_user=p.get("db_user", "hospital_app"),
            auth_method=p.get("auth_method", "scram-sha-256"),
            listen_host_override=p.get("listen_host_override", ""),
            docker_cidr_override=p.get("docker_cidr_override", ""),
            postgres_port=int(p.get("postgres_port", 5432)),
            progress_callback=_progress_callback,
        ),
        "database.install_mysql": lambda p: SystemActions.install_mysql_like_database(
            flavor="mysql",
            db_name=p.get("db_name", "appdb"),
            db_user=p.get("db_user", "app_user"),
            db_password=p.get("db_password", ""),
            bind_address=p.get("bind_address", "127.0.0.1"),
            port=int(p.get("port", 3306)),
            grant_host=p.get("grant_host", "localhost"),
            progress_callback=_progress_callback,
        ),
        "database.install_mariadb": lambda p: SystemActions.install_mysql_like_database(
            flavor="mariadb",
            db_name=p.get("db_name", "appdb"),
            db_user=p.get("db_user", "app_user"),
            db_password=p.get("db_password", ""),
            bind_address=p.get("bind_address", "127.0.0.1"),
            port=int(p.get("port", 3306)),
            grant_host=p.get("grant_host", "localhost"),
            progress_callback=_progress_callback,
        ),
        "database.install_mongodb": lambda p: SystemActions.install_mongodb_database(
            app_db=p.get("app_db", "appdb"),
            app_user=p.get("app_user", "app_user"),
            app_password=p.get("app_password", ""),
            bind_ip=p.get("bind_ip", "127.0.0.1"),
            port=int(p.get("port", 27017)),
            enable_auth=bool(p.get("enable_auth", True)),
            progress_callback=_progress_callback,
        ),
        "database.install_redis": lambda p: SystemActions.install_redis_server(
            bind_address=p.get("bind_address", "127.0.0.1"),
            port=int(p.get("port", 6379)),
            password=p.get("password", ""),
            progress_callback=_progress_callback,
        ),
        "backend.prepare_spring_boot": lambda p: SystemActions.prepare_spring_backend_runtime(
            app_dir=p.get("app_dir", "/opt/celiora"),
            owner_user=p.get("owner_user", "ubuntu"),
            repo_url=p.get("repo_url", ""),
            repo_dir=p.get("repo_dir", "/opt/celiora-src"),
            jar_name=p.get("jar_name", "app.jar"),
            app_port=int(p.get("app_port", 8080)),
            datasource_url=p.get("datasource_url", "jdbc:postgresql://127.0.0.1:5432/hospital"),
            datasource_username=p.get("datasource_username", "hospital_app"),
            datasource_password=p.get("datasource_password", ""),
            root_owner_email=p.get("root_owner_email", "admin@example.com"),
            allowed_origin_patterns=p.get("allowed_origin_patterns", "http://localhost:5173,http://127.0.0.1:5173"),
            jwt_secret=p.get("jwt_secret", ""),
            trust_forward_headers=bool(p.get("trust_forward_headers", False)),
            progress_callback=_progress_callback,
        ),
        "infra.configure_nginx": lambda p: SystemActions.configure_nginx_reverse_proxy(
            site_name=p.get("site_name", "app"),
            server_names=_split_words(p.get("server_names", "example.com")),
            upstream_host=p.get("upstream_host", "127.0.0.1"),
            upstream_port=int(p.get("upstream_port", 8080)),
            client_max_body_size=p.get("client_max_body_size", "20m"),
            proxy_buffering=bool(p.get("proxy_buffering", False)),
            progress_callback=_progress_callback,
        ),
        "infra.setup_https": lambda p: SystemActions.setup_certbot_https(
            domains=_split_words(p.get("domains", "example.com")),
            email=p.get("email", "admin@example.com"),
            redirect_https=bool(p.get("redirect_https", True)),
            progress_callback=_progress_callback,
        ),
        "panels.install_web_db_panel": lambda p: SystemActions.install_web_db_panel(
            app_dir=p.get("app_dir", "/opt/vps-tools-db-panel"),
            panel_port=int(p.get("panel_port", 18090)),
            enable_adminer=bool(p.get("enable_adminer", True)),
            enable_pgadmin=bool(p.get("enable_pgadmin", True)),
            enable_redisinsight=bool(p.get("enable_redisinsight", True)),
            pgadmin_email=p.get("pgadmin_email", "admin@localhost"),
            pgadmin_password=p.get("pgadmin_password", ""),
            progress_callback=_progress_callback,
        ),
        "panels.manage_web_db_panel": lambda p: SystemActions.manage_web_db_panel(
            app_dir=p.get("app_dir", "/opt/vps-tools-db-panel"),
            action=p.get("action", "status"),
            remove_files=bool(p.get("remove_files", False)),
        ),
        "panels.install_admin_web_panel": lambda p: SystemActions.install_admin_web_panel(
            app_dir=p.get("app_dir", "/opt/vps-tools-admin-panel"),
            panel_port=int(p.get("panel_port", 18600)),
            panel_host=p.get("panel_host", "127.0.0.1"),
            login_user=p.get("login_user", "admin"),
            login_password=p.get("login_password", ""),
            service_name=p.get("service_name", "vps-tools-admin-panel"),
            run_user=p.get("run_user", "root"),
            progress_callback=_progress_callback,
        ),
        "panels.update_admin_web_panel": lambda p: SystemActions.update_admin_web_panel(
            app_dir=p.get("app_dir", "/opt/vps-tools-admin-panel"),
            service_name=p.get("service_name", "vps-tools-admin-panel"),
            progress_callback=_progress_callback,
        ),
        "panels.manage_admin_web_panel": lambda p: SystemActions.manage_admin_web_panel(
            app_dir=p.get("app_dir", "/opt/vps-tools-admin-panel"),
            service_name=p.get("service_name", "vps-tools-admin-panel"),
            action=p.get("action", "status"),
            remove_files=bool(p.get("remove_files", False)),
        ),
        "system.update_packages": lambda p: _run_command_sequence(SystemActions.update_system(), "Atualizando sistema"),
        "system.update_script": lambda p: SystemActions.update_script(
            repo_dir=p.get("repo_dir", SystemActions._repo_root_dir()),
        ),
        "system.create_menu_command": lambda p: SystemActions.create_menu_command(
            repo_dir=p.get("repo_dir", SystemActions._repo_root_dir()),
            command_name=p.get("command_name", "menu"),
        ),
        "system.create_swap": lambda p: SystemActions.create_swap(
            size_mb=int(p.get("size_mb", 1024)),
            swap_path=p.get("swap_path", "/swapfile"),
        ),
        "system.systemd_manage": lambda p: SystemActions.systemd_service_action(
            service_name=p.get("service_name", "nginx"),
            action=p.get("action", "status"),
            lines=int(p.get("lines", 120)),
        ),
        "system.systemd_create": lambda p: SystemActions.create_systemd_service(
            service_name=p.get("service_name", "minha-app"),
            description=p.get("description", "Minha aplicacao"),
            exec_start=p.get("exec_start", ""),
            working_dir=p.get("working_dir", "/opt/app"),
            run_user=p.get("run_user", "root"),
            environment_file=p.get("environment_file", ""),
            exec_stop=p.get("exec_stop", ""),
            restart_policy=p.get("restart_policy", "always"),
            restart_sec=int(p.get("restart_sec", 5)),
            progress_callback=_progress_callback,
        ),
        "dr.run_backup": lambda p: SystemActions.run_db_backup_job_now(
            job_name=p.get("job_name", "postgres-prod-diario"),
        ),
        "dr.backup_status": lambda p: SystemActions.db_backup_job_status(
            job_name=p.get("job_name", "postgres-prod-diario"),
        ),
        "dr.restore_test": lambda p: SystemActions.test_db_backup_restore(
            job_name=p.get("job_name", "postgres-prod-diario"),
            restore_db_name=p.get("restore_db_name", ""),
            keep_restore_db=bool(p.get("keep_restore_db", False)),
            progress_callback=_progress_callback,
        ),
        "dr.export_config": lambda p: SystemActions.export_vps_configuration_snapshot(
            export_name=p.get("export_name", "dr-config"),
        ),
        "dr.run_monitor": lambda p: SystemActions.run_dr_monitor_job_now(
            monitor_name=p.get("monitor_name", "default"),
        ),
    }


def _run_action(action_id: str, params: dict):
    handlers = _action_handlers()
    handler = handlers.get(action_id)
    if not handler:
        _error("acao_nao_suportada", action_id)
        return
    try:
        ok, data = handler(params or {})
        _result(ok, data)
    except Exception as exc:
        _error(str(exc), traceback.format_exc())


def main():
    args = sys.argv[1:]
    if not args:
        print(json.dumps({"error": "missing command"}, ensure_ascii=False))
        return 1

    command = args[0].strip().lower()
    if command == "overview":
        print(json.dumps(collect_overview(), ensure_ascii=False))
        return 0
    if command == "actions":
        print(json.dumps({"actions": _action_catalog()}, ensure_ascii=False))
        return 0
    if command == "run-action":
        if len(args) < 2:
            _error("acao_nao_informada")
            return 1
        action_id = args[1]
        params = {}
        if len(args) >= 3 and args[2].strip():
            params = json.loads(args[2])
        _emit({"type": "started", "action": action_id, "timestamp": _utc_now()})
        _run_action(action_id, params)
        return 0

    print(json.dumps({"error": f"unknown command: {command}"}, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    sys.exit(main())
