import json
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone

from vps_tools.core.system import SystemActions, SystemInfo


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


def collect_overview() -> dict:
    repo_dir = SystemActions._repo_root_dir()
    preferred_python = SystemActions._preferred_python_binary()
    admin_panel = (
        SystemActions.admin_web_panel_status()
        if hasattr(SystemActions, "admin_web_panel_status")
        else {"installed": False, "running": False}
    )
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
    }


def _action_catalog() -> list[dict]:
    return [
        {
            "id": "database.install_postgresql",
            "category": "database",
            "label": "Instalar PostgreSQL",
            "description": "Cria o banco PostgreSQL local e prepara a string JDBC para o backend.",
            "schema": [
                {"name": "db_name", "label": "Nome do banco", "type": "text", "default": "hospital", "required": True},
                {"name": "db_user", "label": "Usuário do banco", "type": "text", "default": "hospital_app", "required": True},
                {"name": "db_password", "label": "Senha do usuário", "type": "password", "default": "", "required": True, "secret": True},
                {"name": "listen_addresses", "label": "Bind do PostgreSQL", "type": "text", "default": "localhost", "required": True},
                {"name": "jdbc_host", "label": "Host JDBC", "type": "text", "default": "127.0.0.1", "required": True},
                {"name": "jdbc_port", "label": "Porta JDBC", "type": "number", "default": 5432, "required": True},
            ],
        },
        {
            "id": "database.install_mysql",
            "category": "database",
            "label": "Instalar MySQL",
            "description": "Provisiona MySQL local e cria banco e usuário.",
            "schema": [
                {"name": "db_name", "label": "Nome do banco", "type": "text", "default": "appdb", "required": True},
                {"name": "db_user", "label": "Usuário do banco", "type": "text", "default": "app_user", "required": True},
                {"name": "db_password", "label": "Senha do usuário", "type": "password", "default": "", "required": True, "secret": True},
                {"name": "bind_address", "label": "Bind", "type": "text", "default": "127.0.0.1", "required": True},
                {"name": "port", "label": "Porta", "type": "number", "default": 3306, "required": True},
                {"name": "grant_host", "label": "Host permitido", "type": "text", "default": "localhost", "required": True},
            ],
        },
        {
            "id": "database.install_mariadb",
            "category": "database",
            "label": "Instalar MariaDB",
            "description": "Provisiona MariaDB local e cria banco e usuário.",
            "schema": [
                {"name": "db_name", "label": "Nome do banco", "type": "text", "default": "appdb", "required": True},
                {"name": "db_user", "label": "Usuário do banco", "type": "text", "default": "app_user", "required": True},
                {"name": "db_password", "label": "Senha do usuário", "type": "password", "default": "", "required": True, "secret": True},
                {"name": "bind_address", "label": "Bind", "type": "text", "default": "127.0.0.1", "required": True},
                {"name": "port", "label": "Porta", "type": "number", "default": 3306, "required": True},
                {"name": "grant_host", "label": "Host permitido", "type": "text", "default": "localhost", "required": True},
            ],
        },
        {
            "id": "database.install_mongodb",
            "category": "database",
            "label": "Instalar MongoDB",
            "description": "Provisiona MongoDB local com autenticação opcional.",
            "schema": [
                {"name": "app_db", "label": "Nome do banco", "type": "text", "default": "appdb", "required": True},
                {"name": "app_user", "label": "Usuário", "type": "text", "default": "app_user", "required": True},
                {"name": "app_password", "label": "Senha", "type": "password", "default": "", "required": True, "secret": True},
                {"name": "bind_ip", "label": "Bind IP", "type": "text", "default": "127.0.0.1", "required": True},
                {"name": "port", "label": "Porta", "type": "number", "default": 27017, "required": True},
                {"name": "enable_auth", "label": "Ativar autenticação", "type": "boolean", "default": True, "required": True},
            ],
        },
        {
            "id": "database.install_redis",
            "category": "database",
            "label": "Configurar Redis",
            "description": "Instala Redis local para cache, sessão e filas.",
            "schema": [
                {"name": "bind_address", "label": "Bind", "type": "text", "default": "127.0.0.1", "required": True},
                {"name": "port", "label": "Porta", "type": "number", "default": 6379, "required": True},
                {"name": "password", "label": "Senha", "type": "password", "default": "", "required": False, "secret": True},
            ],
        },
        {
            "id": "backend.prepare_spring_boot",
            "category": "backend",
            "label": "Preparar backend Spring Boot",
            "description": "Prepara Java 17, diretórios, variáveis e comandos do backend Spring Boot.",
            "schema": [
                {"name": "app_dir", "label": "Diretório da aplicação", "type": "text", "default": "/opt/celiora", "required": True},
                {"name": "owner_user", "label": "Usuário dono", "type": "text", "default": "ubuntu", "required": True},
                {"name": "repo_url", "label": "URL do repositório Git", "type": "text", "default": "", "required": False},
                {"name": "repo_dir", "label": "Diretório do repositório", "type": "text", "default": "/opt/celiora-src", "required": True},
                {"name": "jar_name", "label": "Nome do JAR", "type": "text", "default": "app.jar", "required": True},
                {"name": "app_port", "label": "Porta da aplicação", "type": "number", "default": 8080, "required": True},
                {"name": "datasource_url", "label": "SPRING_DATASOURCE_URL", "type": "text", "default": "jdbc:postgresql://127.0.0.1:5432/hospital", "required": True},
                {"name": "datasource_username", "label": "SPRING_DATASOURCE_USERNAME", "type": "text", "default": "hospital_app", "required": True},
                {"name": "datasource_password", "label": "SPRING_DATASOURCE_PASSWORD", "type": "password", "default": "", "required": True, "secret": True},
                {"name": "root_owner_email", "label": "ROOT_OWNER_EMAIL", "type": "text", "default": "admin@example.com", "required": True},
                {"name": "allowed_origin_patterns", "label": "APP_ALLOWED_ORIGIN_PATTERNS", "type": "text", "default": "http://localhost:5173,http://127.0.0.1:5173", "required": True},
                {"name": "jwt_secret", "label": "APP_JWT_SECRET", "type": "password", "default": "", "required": True, "secret": True},
                {"name": "trust_forward_headers", "label": "APP_TRUST_FORWARD_HEADERS", "type": "boolean", "default": False, "required": True},
            ],
        },
        {
            "id": "infra.configure_nginx",
            "category": "infra",
            "label": "Configurar Nginx Reverse Proxy",
            "description": "Publica uma aplicação local por domínio ou server_name no Nginx.",
            "schema": [
                {"name": "site_name", "label": "Nome do site", "type": "text", "default": "app", "required": True},
                {"name": "server_names", "label": "server_name (separados por espaço)", "type": "text", "default": "example.com", "required": True},
                {"name": "upstream_host", "label": "Host upstream", "type": "text", "default": "127.0.0.1", "required": True},
                {"name": "upstream_port", "label": "Porta upstream", "type": "number", "default": 8080, "required": True},
                {"name": "client_max_body_size", "label": "client_max_body_size", "type": "text", "default": "20m", "required": True},
                {"name": "proxy_buffering", "label": "Ativar proxy_buffering", "type": "boolean", "default": False, "required": True},
            ],
        },
        {
            "id": "infra.setup_https",
            "category": "infra",
            "label": "Configurar HTTPS com Certbot",
            "description": "Emite e instala certificado HTTPS com o plugin do Nginx.",
            "schema": [
                {"name": "domains", "label": "Domínios (separados por espaço)", "type": "text", "default": "example.com", "required": True},
                {"name": "email", "label": "E-mail Let's Encrypt", "type": "text", "default": "admin@example.com", "required": True},
                {"name": "redirect_https", "label": "Redirecionar HTTP para HTTPS", "type": "boolean", "default": True, "required": True},
            ],
        },
        {
            "id": "dr.save_profile",
            "category": "dr",
            "label": "Salvar perfil RPO/RTO",
            "description": "Define metas de perda máxima de dados e tempo máximo de recuperação.",
            "schema": [
                {"name": "profile_name", "label": "Identificador do perfil", "type": "text", "default": "backend-prod", "required": True},
                {"name": "service_name", "label": "Nome do serviço", "type": "text", "default": "backend", "required": True},
                {"name": "environment_name", "label": "Ambiente", "type": "text", "default": "producao", "required": True},
                {"name": "rpo_target", "label": "RPO alvo", "type": "text", "default": "15 minutos", "required": True},
                {"name": "rto_target", "label": "RTO alvo", "type": "text", "default": "60 minutos", "required": True},
                {"name": "incident_rpo", "label": "RPO/RTO por incidente", "type": "textarea", "default": "", "required": False},
                {"name": "max_downtime", "label": "Janela máxima de indisponibilidade", "type": "text", "default": "", "required": False},
                {"name": "recovery_priority", "label": "Prioridade de restauração", "type": "text", "default": "alta", "required": True},
                {"name": "service_criticality", "label": "Criticidade do serviço", "type": "text", "default": "critico", "required": True},
                {"name": "operators", "label": "Responsáveis pela operação", "type": "text", "default": "", "required": False},
                {"name": "approvers", "label": "Responsáveis pela aprovação", "type": "text", "default": "", "required": False},
                {"name": "notes", "label": "Observações", "type": "textarea", "default": "", "required": False},
            ],
        },
        {
            "id": "dr.configure_backup",
            "category": "dr",
            "label": "Configurar backup lógico",
            "description": "Cria job de backup com retenção, checksum, offsite, criptografia e alerta.",
            "schema": [
                {"name": "job_name", "label": "Nome do job", "type": "text", "default": "postgres-prod-diario", "required": True},
                {"name": "engine", "label": "Engine", "type": "select", "default": "postgresql", "required": True, "options": ["postgresql", "mysql", "mariadb", "mongodb"]},
                {"name": "db_name", "label": "Nome do banco", "type": "text", "default": "hospital", "required": True},
                {"name": "db_host", "label": "Host do banco", "type": "text", "default": "127.0.0.1", "required": True},
                {"name": "db_port", "label": "Porta do banco", "type": "number", "default": 5432, "required": True},
                {"name": "db_user", "label": "Usuário do banco", "type": "text", "default": "hospital_app", "required": True},
                {"name": "db_password", "label": "Senha do banco", "type": "password", "default": "", "required": False, "secret": True},
                {"name": "auth_db", "label": "Authentication DB (MongoDB)", "type": "text", "default": "", "required": False},
                {"name": "backup_dir", "label": "Diretório local de backup", "type": "text", "default": "/var/backups/vps-tools/postgres-prod-diario", "required": True},
                {"name": "retention_count", "label": "Quantidade a reter", "type": "number", "default": 7, "required": True},
                {"name": "on_calendar", "label": "Agenda systemd OnCalendar", "type": "text", "default": "*-*-* 02:00:00", "required": True},
                {"name": "verify_free_mb", "label": "Espaço livre mínimo (MB)", "type": "number", "default": 512, "required": True},
                {"name": "compression_enabled", "label": "Ativar compressão", "type": "boolean", "default": True, "required": True},
                {"name": "offsite_mode", "label": "Modo offsite", "type": "select", "default": "none", "required": True, "options": ["none", "local_copy", "scp"]},
                {"name": "offsite_path", "label": "Caminho offsite", "type": "text", "default": "", "required": False},
                {"name": "offsite_host", "label": "Host SCP", "type": "text", "default": "", "required": False},
                {"name": "offsite_port", "label": "Porta SCP", "type": "number", "default": 22, "required": False},
                {"name": "offsite_user", "label": "Usuário SCP", "type": "text", "default": "", "required": False},
                {"name": "offsite_ssh_key", "label": "Chave SSH SCP", "type": "text", "default": "", "required": False},
                {"name": "offsite_known_hosts", "label": "known_hosts SCP", "type": "text", "default": "", "required": False},
                {"name": "offsite_timeout_sec", "label": "Timeout offsite", "type": "number", "default": 30, "required": False},
                {"name": "alert_webhook_url", "label": "Webhook de alerta", "type": "text", "default": "", "required": False},
                {"name": "alert_on_success", "label": "Alerta em sucesso", "type": "boolean", "default": False, "required": True},
                {"name": "alert_on_failure", "label": "Alerta em falha", "type": "boolean", "default": True, "required": True},
                {"name": "alert_timeout_sec", "label": "Timeout do alerta", "type": "number", "default": 10, "required": True},
                {"name": "encryption_mode", "label": "Modo de criptografia", "type": "select", "default": "none", "required": True, "options": ["none", "gpg_symmetric"]},
                {"name": "encryption_passphrase", "label": "Senha da criptografia", "type": "password", "default": "", "required": False, "secret": True},
                {"name": "encryption_cipher", "label": "Cifra da criptografia", "type": "text", "default": "AES256", "required": False},
            ],
        },
        {
            "id": "dr.run_backup",
            "category": "dr",
            "label": "Executar backup agora",
            "description": "Executa um job de backup já configurado e retorna status completo.",
            "schema": [
                {"name": "job_name", "label": "Nome do job", "type": "text", "default": "postgres-prod-diario", "required": True},
            ],
        },
        {
            "id": "dr.restore_test",
            "category": "dr",
            "label": "Teste automático de restore",
            "description": "Restaura um backup PostgreSQL em banco temporário para validar recuperação.",
            "schema": [
                {"name": "job_name", "label": "Nome do job", "type": "text", "default": "postgres-prod-diario", "required": True},
            ],
        },
        {
            "id": "dr.export_config",
            "category": "dr",
            "label": "Exportar configurações da VPS",
            "description": "Cria pacote com configs do Nginx, systemd, timers, firewall e inventário do host.",
            "schema": [
                {"name": "export_name", "label": "Nome da exportação", "type": "text", "default": "dr-config", "required": True},
            ],
        },
        {
            "id": "dr.configure_monitor",
            "category": "dr",
            "label": "Configurar monitor DR",
            "description": "Cria monitor com timer systemd para checagem de saúde, backup e aderência.",
            "schema": [
                {"name": "monitor_name", "label": "Nome do monitor", "type": "text", "default": "default", "required": True},
                {"name": "services_csv", "label": "Serviços (separados por vírgula)", "type": "text", "default": "nginx,postgresql,celiora-backend", "required": False},
                {"name": "domains_csv", "label": "Domínios (separados por vírgula)", "type": "text", "default": "", "required": False},
                {"name": "backup_job_name", "label": "Job de backup relacionado", "type": "text", "default": "", "required": False},
                {"name": "profile_name", "label": "Perfil DR", "type": "text", "default": "backend-prod", "required": False},
                {"name": "offsite_job_name", "label": "Job offsite relacionado", "type": "text", "default": "", "required": False},
                {"name": "schedule_on_calendar", "label": "Agenda systemd OnCalendar", "type": "text", "default": "hourly", "required": True},
                {"name": "min_disk_free_mb", "label": "Disco livre mínimo (MB)", "type": "number", "default": 1024, "required": True},
                {"name": "min_ram_free_mb", "label": "RAM livre mínima (MB)", "type": "number", "default": 256, "required": True},
                {"name": "max_cpu_percent", "label": "CPU máxima (%)", "type": "number", "default": 95, "required": True},
                {"name": "ssl_expiry_min_days", "label": "Dias mínimos para SSL", "type": "number", "default": 15, "required": True},
                {"name": "alert_webhook_url", "label": "Webhook de alerta", "type": "text", "default": "", "required": False},
                {"name": "alert_timeout_sec", "label": "Timeout do alerta", "type": "number", "default": 10, "required": True},
            ],
        },
        {
            "id": "dr.run_monitor",
            "category": "dr",
            "label": "Executar monitor DR agora",
            "description": "Executa uma checagem DR imediata.",
            "schema": [
                {"name": "monitor_name", "label": "Nome do monitor", "type": "text", "default": "default", "required": True},
            ],
        },
    ]


def _split_csv(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _action_handlers() -> dict:
    return {
        "database.install_postgresql": lambda p: SystemActions.install_local_postgresql(
            db_name=p.get("db_name", "hospital"),
            db_user=p.get("db_user", "hospital_app"),
            db_password=p.get("db_password", ""),
            listen_addresses=p.get("listen_addresses", "localhost"),
            jdbc_host=p.get("jdbc_host", "127.0.0.1"),
            jdbc_port=int(p.get("jdbc_port", 5432)),
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
            server_names=[item for item in str(p.get("server_names", "example.com")).split() if item],
            upstream_host=p.get("upstream_host", "127.0.0.1"),
            upstream_port=int(p.get("upstream_port", 8080)),
            client_max_body_size=p.get("client_max_body_size", "20m"),
            proxy_buffering=bool(p.get("proxy_buffering", False)),
            progress_callback=_progress_callback,
        ),
        "infra.setup_https": lambda p: SystemActions.setup_certbot_https(
            domains=[item for item in str(p.get("domains", "example.com")).split() if item],
            email=p.get("email", "admin@example.com"),
            redirect_https=bool(p.get("redirect_https", True)),
            progress_callback=_progress_callback,
        ),
        "dr.save_profile": lambda p: SystemActions.save_dr_profile(
            profile_name=p.get("profile_name", "backend-prod"),
            service_name=p.get("service_name", "backend"),
            environment_name=p.get("environment_name", "producao"),
            rpo_target=p.get("rpo_target", "15 minutos"),
            rto_target=p.get("rto_target", "60 minutos"),
            incident_rpo=p.get("incident_rpo", ""),
            max_downtime=p.get("max_downtime", ""),
            recovery_priority=p.get("recovery_priority", "alta"),
            service_criticality=p.get("service_criticality", "critico"),
            operators=p.get("operators", ""),
            approvers=p.get("approvers", ""),
            notes=p.get("notes", ""),
            progress_callback=_progress_callback,
        ),
        "dr.configure_backup": lambda p: SystemActions.configure_db_backup_job(
            job_name=p.get("job_name", "postgres-prod-diario"),
            engine=p.get("engine", "postgresql"),
            db_name=p.get("db_name", "hospital"),
            db_host=p.get("db_host", "127.0.0.1"),
            db_port=int(p.get("db_port", 5432)),
            db_user=p.get("db_user", "hospital_app"),
            db_password=p.get("db_password", ""),
            auth_db=p.get("auth_db", ""),
            backup_dir=p.get("backup_dir", "/var/backups/vps-tools/postgres-prod-diario"),
            retention_count=int(p.get("retention_count", 7)),
            on_calendar=p.get("on_calendar", "*-*-* 02:00:00"),
            verify_free_mb=int(p.get("verify_free_mb", 512)),
            compression_enabled=bool(p.get("compression_enabled", True)),
            offsite_mode=p.get("offsite_mode", "none"),
            offsite_path=p.get("offsite_path", ""),
            offsite_host=p.get("offsite_host", ""),
            offsite_port=int(p.get("offsite_port", 22)),
            offsite_user=p.get("offsite_user", ""),
            offsite_ssh_key=p.get("offsite_ssh_key", ""),
            offsite_known_hosts=p.get("offsite_known_hosts", ""),
            offsite_timeout_sec=int(p.get("offsite_timeout_sec", 30)),
            alert_webhook_url=p.get("alert_webhook_url", ""),
            alert_on_success=bool(p.get("alert_on_success", False)),
            alert_on_failure=bool(p.get("alert_on_failure", True)),
            alert_timeout_sec=int(p.get("alert_timeout_sec", 10)),
            encryption_mode=p.get("encryption_mode", "none"),
            encryption_passphrase=p.get("encryption_passphrase", ""),
            encryption_cipher=p.get("encryption_cipher", "AES256"),
            progress_callback=_progress_callback,
        ),
        "dr.run_backup": lambda p: SystemActions.run_db_backup_job_now(
            job_name=p.get("job_name", "postgres-prod-diario"),
        ),
        "dr.restore_test": lambda p: SystemActions.run_automatic_restore_test(
            job_name=p.get("job_name", "postgres-prod-diario"),
        ),
        "dr.export_config": lambda p: SystemActions.export_vps_configuration_snapshot(
            export_name=p.get("export_name", "dr-config"),
        ),
        "dr.configure_monitor": lambda p: SystemActions.configure_dr_monitoring_job(
            monitor_name=p.get("monitor_name", "default"),
            service_names=_split_csv(p.get("services_csv", "")),
            domains=_split_csv(p.get("domains_csv", "")),
            backup_job_name=p.get("backup_job_name", ""),
            profile_name=p.get("profile_name", ""),
            offsite_job_name=p.get("offsite_job_name", ""),
            schedule_on_calendar=p.get("schedule_on_calendar", "hourly"),
            min_disk_free_mb=int(p.get("min_disk_free_mb", 1024)),
            min_ram_free_mb=int(p.get("min_ram_free_mb", 256)),
            max_cpu_percent=int(p.get("max_cpu_percent", 95)),
            ssl_expiry_min_days=int(p.get("ssl_expiry_min_days", 15)),
            alert_webhook_url=p.get("alert_webhook_url", ""),
            alert_timeout_sec=int(p.get("alert_timeout_sec", 10)),
            progress_callback=_progress_callback,
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
