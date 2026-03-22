import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import time

import psutil
import requests


class SystemInfo:
    @staticmethod
    def get_ip():
        try:
            return requests.get('https://icanhazip.com', timeout=5).text.strip()
        except:
            try:
                # Fallback to local IP discovery if external service fails
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            except:
                return "Unknown"

    @staticmethod
    def get_os_info():
        if os.path.exists('/etc/issue'):
            with open('/etc/issue', 'r') as f:
                return f.read().splitlines()[0].strip()
        return "Unknown OS"

    @staticmethod
    def get_cpu_usage():
        return psutil.cpu_percent(interval=1)

    @staticmethod
    def get_ram_info():
        mem = psutil.virtual_memory()
        return {
            'total': mem.total // (1024 * 1024),
            'used': mem.used // (1024 * 1024),
            'free': mem.available // (1024 * 1024),
            'percent': mem.percent
        }

    @staticmethod
    def get_swap_info():
        swap = psutil.swap_memory()
        return {
            'total': swap.total // (1024 * 1024),
            'used': swap.used // (1024 * 1024),
            'free': swap.free // (1024 * 1024),
            'percent': swap.percent
        }


class SystemActions:
    @staticmethod
    def _package_manager() -> str:
        if os.path.exists('/usr/bin/apt-get') or os.path.exists('/bin/apt-get'):
            return 'apt'
        if os.path.exists('/usr/bin/yum') or os.path.exists('/bin/yum'):
            return 'yum'
        return ''

    @staticmethod
    def _read_os_release() -> dict:
        data = {}
        path = "/etc/os-release"
        if not os.path.exists(path):
            return data
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    data[key] = value.strip().strip('"')
        except Exception:
            return {}
        return data

    @staticmethod
    def _validate_pg_identifier(value: str, label: str):
        if not value:
            return False, f"{label} nao pode ser vazio."
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
            return False, f"{label} invalido. Use apenas letras, numeros e underscore, iniciando com letra ou underscore."
        return True, ""

    @staticmethod
    def _linux_user_exists(username: str) -> bool:
        if not username:
            return False
        result = subprocess.run(["id", "-u", username], capture_output=True, text=True, check=False)
        return result.returncode == 0

    @staticmethod
    def _resolve_linux_owner(preferred: str = "ubuntu") -> str:
        candidates = [
            preferred,
            os.environ.get("SUDO_USER"),
            os.environ.get("USER"),
        ]
        current = subprocess.run(["id", "-un"], capture_output=True, text=True, check=False)
        if current.returncode == 0:
            candidates.append((current.stdout or "").strip())
        for candidate in candidates:
            if SystemActions._linux_user_exists(candidate):
                return candidate
        return "root"

    @staticmethod
    def _run_as_postgres(command: list[str], capture_output: bool = True, text: bool = True):
        if shutil.which("runuser"):
            cmd = ["runuser", "-u", "postgres", "--", *command]
        elif shutil.which("su"):
            joined = " ".join(shlex.quote(part) for part in command)
            cmd = ["su", "-", "postgres", "-c", joined]
        else:
            raise RuntimeError("Nao foi possivel localizar runuser/su para executar comandos como postgres.")
        return subprocess.run(cmd, capture_output=capture_output, text=text, check=False)

    @staticmethod
    def _find_postgresql_conf():
        base_dir = "/etc/postgresql"
        if not os.path.isdir(base_dir):
            return None

        def version_key(value: str):
            parts = []
            for item in value.split("."):
                try:
                    parts.append(int(item))
                except ValueError:
                    parts.append(item)
            return tuple(parts)

        versions = sorted(os.listdir(base_dir), key=version_key, reverse=True)
        for version in versions:
            conf_path = os.path.join(base_dir, version, "main", "postgresql.conf")
            if os.path.exists(conf_path):
                return conf_path
        return None

    @staticmethod
    def _replace_or_append_setting(conf_path: str, key: str, value: str):
        if not os.path.exists(conf_path):
            return False, f"Arquivo de configuracao nao encontrado: {conf_path}"

        try:
            with open(conf_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _replace_or_append_plain_setting(conf_path: str, key: str, value: str):
        if not os.path.exists(conf_path):
            return False, f"Arquivo de configuracao nao encontrado: {conf_path}"
        try:
            with open(conf_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as exc:
            return False, str(exc)

        pattern = re.compile(rf"^\s*#?\s*{re.escape(key)}\b")
        new_line = f"{key} {value}\n"
        replaced = False
        output = []
        for line in lines:
            if pattern.match(line) and not replaced:
                output.append(new_line)
                replaced = True
            else:
                output.append(line)
        if not replaced:
            if output and not output[-1].endswith("\n"):
                output[-1] += "\n"
            output.append(new_line)
        try:
            with open(conf_path, "w", encoding="utf-8") as f:
                f.writelines(output)
            return True, conf_path
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _set_mongod_config(conf_path: str, bind_ip: str, port: int, auth_enabled: bool):
        if not os.path.exists(conf_path):
            return False, f"Arquivo de configuracao nao encontrado: {conf_path}"
        try:
            with open(conf_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as exc:
            return False, str(exc)

        if re.search(r"(?m)^\s*bindIp:\s*", content):
            content = re.sub(r"(?m)^\s*bindIp:\s*.*$", f"  bindIp: {bind_ip}", content, count=1)
        elif re.search(r"(?m)^net:\s*$", content):
            content = re.sub(r"(?m)^net:\s*$", f"net:\n  port: {port}\n  bindIp: {bind_ip}", content, count=1)
        else:
            content += f"\nnet:\n  port: {port}\n  bindIp: {bind_ip}\n"

        if re.search(r"(?m)^\s*port:\s*", content):
            content = re.sub(r"(?m)^\s*port:\s*.*$", f"  port: {port}", content, count=1)

        auth_value = "enabled" if auth_enabled else "disabled"
        if re.search(r"(?m)^security:\s*$", content):
            if re.search(r"(?m)^\s*authorization:\s*", content):
                content = re.sub(r"(?m)^\s*authorization:\s*.*$", f"  authorization: {auth_value}", content, count=1)
            else:
                content = re.sub(r"(?m)^security:\s*$", f"security:\n  authorization: {auth_value}", content, count=1)
        elif re.search(r"(?m)^#\s*security:\s*$", content):
            content = re.sub(r"(?m)^#\s*security:\s*$", f"security:\n  authorization: {auth_value}", content, count=1)
        else:
            content += f"\nsecurity:\n  authorization: {auth_value}\n"

        return SystemActions._write_text_file(conf_path, content)

    @staticmethod
    def _write_text_file(path: str, content: str, mode: int | None = None):
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            if mode is not None:
                os.chmod(path, mode)
            return True, path
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _ubuntu_codename() -> str:
        os_release = SystemActions._read_os_release()
        for key in ("VERSION_CODENAME", "UBUNTU_CODENAME"):
            value = (os_release.get(key) or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _validate_service_name(value: str):
        if not value:
            return False, "Nome do servico nao pode ser vazio."
        if not re.match(r"^[A-Za-z0-9_.@-]+$", value):
            return False, "Nome do servico invalido. Use apenas letras, numeros, ponto, underscore, @ ou -."
        return True, ""

    @staticmethod
    def _env_file_content(env_vars: dict[str, str]) -> str:
        lines = []
        for key, value in env_vars.items():
            safe_key = re.sub(r"[^A-Za-z0-9_]", "_", key or "").upper()
            lines.append(f"{safe_key}={shlex.quote(str(value))}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def write_environment_file(path: str, env_vars: dict[str, str], owner_user: str = ""):
        ok, msg = SystemActions._write_text_file(path, SystemActions._env_file_content(env_vars), mode=0o600)
        if not ok:
            return False, msg
        if owner_user and SystemActions._linux_user_exists(owner_user):
            result = subprocess.run(["chown", f"{owner_user}:{owner_user}", path], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or f"Falha ao ajustar dono de {path}."
        return True, path

    @staticmethod
    def create_systemd_service(
        service_name: str,
        description: str,
        exec_start: str,
        working_dir: str,
        run_user: str,
        environment_file: str = "",
        exec_stop: str = "",
        restart_policy: str = "always",
        restart_sec: int = 5,
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            if os.name == "nt":
                return False, "systemd nao suportado no Windows."
            ok, msg = SystemActions._validate_service_name(service_name)
            if not ok:
                return False, msg
            if not exec_start.strip():
                return False, "ExecStart nao pode ser vazio."
            if not working_dir.startswith("/"):
                return False, "WorkingDirectory deve ser absoluto."

            run_user = SystemActions._resolve_linux_owner(run_user or "root")
            unit_path = f"/etc/systemd/system/{service_name}.service"
            lines = [
                "[Unit]",
                f"Description={description or service_name}",
                "After=network.target",
                "",
                "[Service]",
                "Type=simple",
                f"User={run_user}",
                f"Group={run_user}",
                f"WorkingDirectory={working_dir}",
            ]
            if environment_file:
                lines.append(f"EnvironmentFile={environment_file}")
            lines.extend(
                [
                    f"ExecStart={exec_start}",
                ]
            )
            if exec_stop.strip():
                lines.append(f"ExecStop={exec_stop}")
            lines.extend(
                [
                    f"Restart={restart_policy}",
                    f"RestartSec={restart_sec}",
                    "",
                    "[Install]",
                    "WantedBy=multi-user.target",
                    "",
                ]
            )

            update(15, "Gravando unit file")
            ok, msg = SystemActions._write_text_file(unit_path, "\n".join(lines))
            if not ok:
                return False, msg

            update(45, "Recarregando systemd")
            for cmd in (
                ["systemctl", "daemon-reload"],
                ["systemctl", "enable", service_name],
                ["systemctl", "restart", service_name],
            ):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or f"Falha ao executar: {' '.join(cmd)}"

            update(80, "Coletando status do servico")
            status_result = subprocess.run(
                ["systemctl", "status", service_name, "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            update(100, "Servico criado")
            return True, {
                "service_name": service_name,
                "unit_path": unit_path,
                "run_user": run_user,
                "working_dir": working_dir,
                "environment_file": environment_file,
                "exec_start": exec_start,
                "status": (status_result.stdout or status_result.stderr or "").strip(),
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def systemd_service_action(service_name: str, action: str, lines: int = 120):
        try:
            ok, msg = SystemActions._validate_service_name(service_name)
            if not ok:
                return False, msg
            if action not in {"start", "stop", "restart", "status", "enable", "disable", "logs"}:
                return False, f"Acao systemd invalida: {action}"

            if action == "logs":
                result = subprocess.run(
                    ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            elif action == "status":
                result = subprocess.run(
                    ["systemctl", "status", service_name, "--no-pager"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            else:
                result = subprocess.run(["systemctl", action, service_name], capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    status = subprocess.run(
                        ["systemctl", "status", service_name, "--no-pager"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    result = status
            text_out = (result.stdout or result.stderr or "").strip()
            return result.returncode == 0, text_out
        except Exception as exc:
            return False, str(exc)

        pattern = re.compile(rf"^\s*#?\s*{re.escape(key)}\s*=")
        new_line = f"{key} = {value}\n"
        replaced = False
        output = []

        for line in lines:
            if pattern.match(line) and not replaced:
                output.append(new_line)
                replaced = True
            else:
                output.append(line)

        if not replaced:
            if output and not output[-1].endswith("\n"):
                output[-1] += "\n"
            output.append(new_line)

        try:
            with open(conf_path, "w", encoding="utf-8") as f:
                f.writelines(output)
            return True, conf_path
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def install_local_postgresql(
        db_name: str = "hospital",
        db_user: str = "hospital_app",
        db_password: str = "TroquePorUmaSenhaForte123!",
        listen_addresses: str = "localhost",
        jdbc_host: str = "127.0.0.1",
        jdbc_port: int = 5432,
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")
        try:
            if os.name == "nt":
                return False, "Instalacao do PostgreSQL local nao suportada no Windows."

            manager = SystemActions._package_manager()
            if manager != "apt":
                return False, "Provisionamento automatico do PostgreSQL disponivel apenas para Debian/Ubuntu."

            ok, msg = SystemActions._validate_pg_identifier(db_name, "Nome do banco")
            if not ok:
                return False, msg
            ok, msg = SystemActions._validate_pg_identifier(db_user, "Nome do usuario")
            if not ok:
                return False, msg
            if not db_password:
                return False, "Senha do usuario do banco nao pode ser vazia."
            if not (listen_addresses or "").strip():
                return False, "listen_addresses nao pode ser vazio."
            if not (jdbc_host or "").strip():
                return False, "Host JDBC nao pode ser vazio."
            if not isinstance(jdbc_port, int) or not (1 <= jdbc_port <= 65535):
                return False, "Porta JDBC invalida."

            update(5, "Atualizando cache de pacotes")
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha no apt-get update."

            update(20, "Instalando PostgreSQL")
            result = subprocess.run(
                ["apt-get", "install", "-y", "postgresql", "postgresql-contrib"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha na instalacao do PostgreSQL."

            update(40, "Habilitando e iniciando o servico")
            for cmd in (["systemctl", "enable", "postgresql"], ["systemctl", "start", "postgresql"]):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or f"Falha ao executar: {' '.join(cmd)}"

            update(55, "Aplicando listen_addresses do PostgreSQL")
            conf_path = SystemActions._find_postgresql_conf()
            if not conf_path:
                return False, "Arquivo postgresql.conf nao encontrado em /etc/postgresql."
            pg_listen_addresses = listen_addresses.replace("'", "''")
            ok, msg = SystemActions._replace_or_append_setting(conf_path, "listen_addresses", f"'{pg_listen_addresses}'")
            if not ok:
                return False, msg

            result = subprocess.run(["systemctl", "restart", "postgresql"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao reiniciar o PostgreSQL."

            password_sql = db_password.replace("'", "''")
            role_sql = (
                "DO $$ "
                f"BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{db_user}') THEN "
                f"CREATE ROLE {db_user} LOGIN ENCRYPTED PASSWORD '{password_sql}'; "
                f"ELSE ALTER ROLE {db_user} WITH LOGIN ENCRYPTED PASSWORD '{password_sql}'; "
                "END IF; "
                "END $$;"
            )

            update(70, "Criando ou atualizando usuario do banco")
            result = SystemActions._run_as_postgres(
                ["psql", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c", role_sql]
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao criar/atualizar usuario do PostgreSQL."

            update(80, "Criando ou ajustando banco de dados")
            exists = SystemActions._run_as_postgres(
                ["psql", "-tAc", f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'"]
            )
            if exists.returncode != 0:
                return False, exists.stderr.strip() or exists.stdout.strip() or "Falha ao verificar existencia do banco."
            if exists.stdout.strip() != "1":
                create_db = SystemActions._run_as_postgres(
                    ["psql", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c", f"CREATE DATABASE {db_name} OWNER {db_user};"]
                )
                if create_db.returncode != 0:
                    return False, create_db.stderr.strip() or create_db.stdout.strip() or "Falha ao criar banco de dados."

            grant_sql = (
                f"ALTER DATABASE {db_name} OWNER TO {db_user}; "
                f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user};"
            )
            result = SystemActions._run_as_postgres(
                ["psql", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c", grant_sql]
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao conceder privilegios no banco."

            schema_sql = (
                f"ALTER SCHEMA public OWNER TO {db_user}; "
                f"GRANT ALL ON SCHEMA public TO {db_user};"
            )
            result = SystemActions._run_as_postgres(
                ["psql", "-v", "ON_ERROR_STOP=1", "-d", db_name, "-c", schema_sql]
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao ajustar o schema public."

            update(90, "Coletando status final")
            test_result = SystemActions._run_as_postgres(["psql", "-d", db_name, "-c", "\\l"])
            if test_result.returncode != 0:
                return False, test_result.stderr.strip() or test_result.stdout.strip() or "Falha no teste final do banco."

            status_result = subprocess.run(
                ["systemctl", "status", "postgresql", "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )

            os_release = SystemActions._read_os_release()
            update(100, "Provisionamento concluido")
            return True, {
                "db_name": db_name,
                "db_user": db_user,
                "db_password": db_password,
                "listen_addresses": listen_addresses,
                "jdbc_host": jdbc_host,
                "jdbc_port": jdbc_port,
                "jdbc_url": f"jdbc:postgresql://{jdbc_host}:{jdbc_port}/{db_name}",
                "os_info": SystemInfo.get_os_info(),
                "is_ubuntu": os_release.get("ID", "").lower() == "ubuntu",
                "service_status": (status_result.stdout or status_result.stderr or "").strip(),
                "psql_test_output": (test_result.stdout or test_result.stderr or "").strip(),
                "config_file": conf_path,
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def prepare_spring_backend_runtime(
        app_dir: str = "/opt/celiora",
        owner_user: str = "ubuntu",
        repo_url: str = "",
        repo_dir: str = "/opt/celiora-src",
        jar_name: str = "app.jar",
        app_port: int = 8080,
        datasource_url: str = "jdbc:postgresql://127.0.0.1:5432/hospital",
        datasource_username: str = "hospital_app",
        datasource_password: str = "@123@Rdy",
        root_owner_email: str = "rdysoftware@gmail.com",
        allowed_origin_patterns: str = "http://localhost:5173,http://127.0.0.1:5173",
        jwt_secret: str = "troque-por-uma-chave-bem-forte-com-32-ou-mais-caracteres",
        trust_forward_headers: bool = False,
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            if os.name == "nt":
                return False, "Preparo do backend Spring Boot nao suportado no Windows."

            manager = SystemActions._package_manager()
            if manager != "apt":
                return False, "Preparacao automatica do backend disponivel apenas para Debian/Ubuntu."

            if not app_dir.startswith("/"):
                return False, "Diretorio da aplicacao deve ser absoluto."
            if repo_url and not repo_dir.startswith("/"):
                return False, "Diretorio do repositorio deve ser absoluto."
            if not jar_name or "/" in jar_name or "\\" in jar_name:
                return False, "Nome do JAR invalido."
            if not isinstance(app_port, int) or not (1 <= app_port <= 65535):
                return False, "Porta da aplicacao invalida."

            app_owner = SystemActions._resolve_linux_owner(owner_user)

            update(5, "Atualizando cache de pacotes")
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha no apt-get update."

            update(20, "Instalando Java 17")
            result = subprocess.run(
                ["apt-get", "install", "-y", "openjdk-17-jre-headless"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha na instalacao do Java 17."

            if repo_url:
                update(35, "Instalando git")
                result = subprocess.run(["apt-get", "install", "-y", "git"], capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or "Falha na instalacao do git."

            update(50, "Criando pasta da aplicacao")
            result = subprocess.run(["mkdir", "-p", app_dir], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or f"Falha ao criar {app_dir}."

            result = subprocess.run(["chown", "-R", f"{app_owner}:{app_owner}", app_dir], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or f"Falha ao ajustar dono de {app_dir}."

            repo_status = ""
            if repo_url:
                update(70, "Preparando repositorio do backend")
                if os.path.isdir(os.path.join(repo_dir, ".git")):
                    result = subprocess.run(["git", "-C", repo_dir, "pull", "--ff-only"], capture_output=True, text=True, check=False)
                    if result.returncode != 0:
                        return False, result.stderr.strip() or result.stdout.strip() or "Falha no git pull do backend."
                    repo_status = (result.stdout or result.stderr or "").strip() or "Repositorio atualizado."
                else:
                    if os.path.exists(repo_dir) and os.listdir(repo_dir):
                        return False, f"Diretorio do repositorio ja existe e nao esta vazio: {repo_dir}"
                    result = subprocess.run(["git", "clone", repo_url, repo_dir], capture_output=True, text=True, check=False)
                    if result.returncode != 0:
                        return False, result.stderr.strip() or result.stdout.strip() or "Falha no git clone do backend."
                    repo_status = (result.stdout or result.stderr or "").strip() or "Repositorio clonado."

                result = subprocess.run(["chown", "-R", f"{app_owner}:{app_owner}", repo_dir], capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or f"Falha ao ajustar dono de {repo_dir}."

            update(85, "Coletando versoes e proximos passos")
            java_result = subprocess.run(["java", "-version"], capture_output=True, text=True, check=False)
            java_version = (java_result.stderr or java_result.stdout or "").strip()
            if java_result.returncode != 0:
                return False, java_version or "Falha ao validar java -version."

            jar_target = os.path.join(app_dir, jar_name).replace("\\", "/")
            env_exports = "\n".join(
                [
                    f"export PORT={app_port}",
                    f"export APP_JWT_SECRET='{jwt_secret}'",
                    f"export ROOT_OWNER_EMAIL='{root_owner_email}'",
                    f"export SPRING_DATASOURCE_URL='{datasource_url}'",
                    f"export SPRING_DATASOURCE_USERNAME='{datasource_username}'",
                    f"export SPRING_DATASOURCE_PASSWORD='{datasource_password}'",
                    f"export APP_TRUST_FORWARD_HEADERS='{'true' if trust_forward_headers else 'false'}'",
                    f"export APP_ALLOWED_ORIGIN_PATTERNS='{allowed_origin_patterns}'",
                ]
            )
            jar_run_command = f"{env_exports}\n\njava -jar {jar_target}"
            health_check_command = f"curl http://127.0.0.1:{app_port}/actuator/health"
            build_commands = (
                f"cd {repo_dir}\n"
                "./gradlew bootJar\n"
                f"cp build/libs/*.jar {jar_target}\n\n"
                f"{jar_run_command}"
            ) if repo_url else ""

            update(100, "Preparacao concluida")
            return True, {
                "os_info": SystemInfo.get_os_info(),
                "is_ubuntu": SystemActions._read_os_release().get("ID", "").lower() == "ubuntu",
                "app_dir": app_dir,
                "app_owner": app_owner,
                "repo_url": repo_url,
                "repo_dir": repo_dir,
                "repo_status": repo_status,
                "jar_name": jar_name,
                "jar_target": jar_target,
                "app_port": app_port,
                "java_version": java_version,
                "env_exports": env_exports,
                "jar_run_command": jar_run_command,
                "build_commands": build_commands,
                "health_check_command": health_check_command,
                "security_group_notes": [
                    "continue com 22 so para seu IP",
                    f"abra {app_port} temporariamente so para seu IP, se quiser testar no navegador",
                    "nao abra 5432",
                    "nao abra 80/443 ate concluir a instalacao do backend",
                ],
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def install_mysql_like_database(
        flavor: str,
        db_name: str,
        db_user: str,
        db_password: str,
        bind_address: str = "127.0.0.1",
        port: int = 3306,
        grant_host: str = "localhost",
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            if os.name == "nt":
                return False, "Instalacao de banco nao suportada no Windows."
            if SystemActions._package_manager() != "apt":
                return False, "Instalacao automatica disponivel apenas para Debian/Ubuntu."
            if flavor not in {"mysql", "mariadb"}:
                return False, f"Sabor de banco invalido: {flavor}"
            ok, msg = SystemActions._validate_pg_identifier(db_name, "Nome do banco")
            if not ok:
                return False, msg
            ok, msg = SystemActions._validate_pg_identifier(db_user, "Nome do usuario")
            if not ok:
                return False, msg
            if not db_password:
                return False, "Senha do banco nao pode ser vazia."
            if not (1 <= port <= 65535):
                return False, "Porta invalida."

            package_name = "mysql-server" if flavor == "mysql" else "mariadb-server"
            service_name = "mysql" if flavor == "mysql" else "mariadb"
            conf_dir = "/etc/mysql/mysql.conf.d" if flavor == "mysql" else "/etc/mysql/mariadb.conf.d"
            conf_path = os.path.join(conf_dir, "zz-vps-tools.cnf")

            update(5, "Atualizando cache de pacotes")
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha no apt-get update."

            update(20, f"Instalando {package_name}")
            result = subprocess.run(["apt-get", "install", "-y", package_name], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or f"Falha na instalacao do {package_name}."

            update(40, "Aplicando configuracao de bind/porta")
            conf_content = (
                "[mysqld]\n"
                f"bind-address = {bind_address}\n"
                f"port = {port}\n"
            )
            ok, msg = SystemActions._write_text_file(conf_path, conf_content)
            if not ok:
                return False, msg

            for cmd in (["systemctl", "enable", service_name], ["systemctl", "restart", service_name]):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or f"Falha ao executar: {' '.join(cmd)}"

            password_sql = db_password.replace("'", "''")
            grant_host_sql = grant_host.replace("'", "''")
            sql = (
                f"CREATE DATABASE IF NOT EXISTS `{db_name}`;"
                f"CREATE USER IF NOT EXISTS '{db_user}'@'{grant_host_sql}' IDENTIFIED BY '{password_sql}';"
                f"ALTER USER '{db_user}'@'{grant_host_sql}' IDENTIFIED BY '{password_sql}';"
                f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'{grant_host_sql}';"
                "FLUSH PRIVILEGES;"
            )

            update(65, "Criando banco e usuario")
            result = subprocess.run(["mysql", "-e", sql], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao criar banco/usuario."

            status_result = subprocess.run(
                ["systemctl", "status", service_name, "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            jdbc_scheme = "mysql" if flavor == "mysql" else "mariadb"
            update(100, "Banco configurado")
            return True, {
                "flavor": flavor,
                "service_name": service_name,
                "db_name": db_name,
                "db_user": db_user,
                "db_password": db_password,
                "bind_address": bind_address,
                "port": port,
                "grant_host": grant_host,
                "config_file": conf_path,
                "jdbc_url": f"jdbc:{jdbc_scheme}://{bind_address}:{port}/{db_name}",
                "service_status": (status_result.stdout or status_result.stderr or "").strip(),
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def install_mongodb_database(
        app_db: str,
        app_user: str,
        app_password: str,
        bind_ip: str = "127.0.0.1",
        port: int = 27017,
        enable_auth: bool = True,
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            if os.name == "nt":
                return False, "Instalacao do MongoDB nao suportada no Windows."
            if SystemActions._package_manager() != "apt":
                return False, "Instalacao automatica disponivel apenas para Debian/Ubuntu."
            ok, msg = SystemActions._validate_pg_identifier(app_db, "Nome do banco")
            if not ok:
                return False, msg
            ok, msg = SystemActions._validate_pg_identifier(app_user, "Nome do usuario")
            if not ok:
                return False, msg
            if not app_password:
                return False, "Senha do banco nao pode ser vazia."
            codename = SystemActions._ubuntu_codename()
            if codename not in {"focal", "jammy", "noble"}:
                return False, f"Ubuntu sem suporte oficial configurado para MongoDB 8.0: {codename or 'desconhecido'}"

            update(5, "Instalando dependencias")
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha no apt-get update."
            result = subprocess.run(["apt-get", "install", "-y", "gnupg", "curl"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao instalar gnupg/curl."

            update(25, "Configurando repositorio oficial do MongoDB")
            key_cmd = [
                "bash",
                "-lc",
                "curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor",
            ]
            result = subprocess.run(key_cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao importar chave do MongoDB."
            repo_line = (
                f"deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] "
                f"https://repo.mongodb.org/apt/ubuntu {codename}/mongodb-org/8.0 multiverse\n"
            )
            ok, msg = SystemActions._write_text_file("/etc/apt/sources.list.d/mongodb-org-8.0.list", repo_line)
            if not ok:
                return False, msg

            update(45, "Instalando MongoDB")
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao atualizar repositorio MongoDB."
            result = subprocess.run(["apt-get", "install", "-y", "mongodb-org"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha na instalacao do MongoDB."

            update(60, "Aplicando bind/auth no mongod.conf")
            ok, msg = SystemActions._set_mongod_config("/etc/mongod.conf", bind_ip=bind_ip, port=port, auth_enabled=False)
            if not ok:
                return False, msg

            for cmd in (["systemctl", "enable", "mongod"], ["systemctl", "restart", "mongod"]):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or f"Falha ao executar: {' '.join(cmd)}"

            script = (
                f"const dbName = {json.dumps(app_db)};"
                f"const userName = {json.dumps(app_user)};"
                f"const pwd = {json.dumps(app_password)};"
                "const dbRef = db.getSiblingDB(dbName);"
                "if (dbRef.getUser(userName)) { dbRef.updateUser(userName, {pwd: pwd, roles:[{role:'readWrite', db: dbName}]}); }"
                " else { dbRef.createUser({user: userName, pwd: pwd, roles:[{role:'readWrite', db: dbName}]}); }"
            )
            result = subprocess.run(["mongosh", "--quiet", "--eval", script], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao criar usuario no MongoDB."

            if enable_auth:
                ok, msg = SystemActions._set_mongod_config("/etc/mongod.conf", bind_ip=bind_ip, port=port, auth_enabled=True)
                if not ok:
                    return False, msg
                result = subprocess.run(["systemctl", "restart", "mongod"], capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or "Falha ao reiniciar mongod com auth."

            status_result = subprocess.run(
                ["systemctl", "status", "mongod", "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            update(100, "MongoDB configurado")
            return True, {
                "db_name": app_db,
                "db_user": app_user,
                "db_password": app_password,
                "bind_ip": bind_ip,
                "port": port,
                "auth_enabled": enable_auth,
                "config_file": "/etc/mongod.conf",
                "connection_string": f"mongodb://{app_user}:{app_password}@{bind_ip}:{port}/{app_db}?authSource={app_db}",
                "service_status": (status_result.stdout or status_result.stderr or "").strip(),
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def install_redis_server(
        bind_address: str = "127.0.0.1",
        port: int = 6379,
        password: str = "",
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            if os.name == "nt":
                return False, "Instalacao do Redis nao suportada no Windows."
            if SystemActions._package_manager() != "apt":
                return False, "Instalacao automatica disponivel apenas para Debian/Ubuntu."
            if not (1 <= port <= 65535):
                return False, "Porta invalida."

            update(5, "Instalando dependencias")
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha no apt-get update."
            result = subprocess.run(["apt-get", "install", "-y", "curl", "gpg"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao instalar dependencias do Redis."

            update(25, "Configurando repositorio oficial do Redis")
            key_cmd = [
                "bash",
                "-lc",
                "curl -fsSL https://packages.redis.io/gpg | gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg",
            ]
            result = subprocess.run(key_cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao importar chave do Redis."
            repo_cmd = [
                "bash",
                "-lc",
                "echo 'deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb "
                "$(lsb_release -cs) main' > /etc/apt/sources.list.d/redis.list",
            ]
            result = subprocess.run(repo_cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao criar repositorio do Redis."

            update(45, "Instalando Redis")
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao atualizar repositorio Redis."
            result = subprocess.run(["apt-get", "install", "-y", "redis-server"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha na instalacao do Redis."

            conf_path = "/etc/redis/redis.conf"
            update(65, "Aplicando bind/porta/senha")
            ok, msg = SystemActions._replace_or_append_plain_setting(conf_path, "bind", bind_address)
            if not ok:
                return False, msg
            ok, msg = SystemActions._replace_or_append_plain_setting(conf_path, "port", str(port))
            if not ok:
                return False, msg
            if password:
                ok, msg = SystemActions._replace_or_append_plain_setting(conf_path, "requirepass", password)
                if not ok:
                    return False, msg

            for cmd in (["systemctl", "enable", "redis-server"], ["systemctl", "restart", "redis-server"]):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or f"Falha ao executar: {' '.join(cmd)}"

            status_result = subprocess.run(
                ["systemctl", "status", "redis-server", "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            update(100, "Redis configurado")
            return True, {
                "bind_address": bind_address,
                "port": port,
                "password": password,
                "config_file": conf_path,
                "connection_string": f"redis://:{password}@{bind_address}:{port}/0" if password else f"redis://{bind_address}:{port}/0",
                "service_status": (status_result.stdout or status_result.stderr or "").strip(),
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def configure_nginx_reverse_proxy(
        site_name: str,
        server_names: list[str],
        upstream_host: str,
        upstream_port: int,
        client_max_body_size: str = "20m",
        proxy_buffering: bool = False,
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            ok, msg = SystemActions._validate_service_name(site_name)
            if not ok:
                return False, msg
            if not server_names:
                return False, "Informe ao menos um dominio/server_name."
            if not (1 <= upstream_port <= 65535):
                return False, "Porta upstream invalida."

            update(5, "Instalando Nginx")
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha no apt-get update."
            result = subprocess.run(["apt-get", "install", "-y", "nginx"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha na instalacao do Nginx."

            server_name_line = " ".join(server_names)
            conf_content = (
                "server {\n"
                "    listen 80;\n"
                "    listen [::]:80;\n"
                f"    server_name {server_name_line};\n"
                f"    client_max_body_size {client_max_body_size};\n\n"
                "    location / {\n"
                f"        proxy_pass http://{upstream_host}:{upstream_port};\n"
                "        proxy_http_version 1.1;\n"
                "        proxy_set_header Host $host;\n"
                "        proxy_set_header Upgrade $http_upgrade;\n"
                "        proxy_set_header Connection \"upgrade\";\n"
                "        proxy_set_header X-Real-IP $remote_addr;\n"
                "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
                f"        proxy_buffering {'on' if proxy_buffering else 'off'};\n"
                "    }\n"
                "}\n"
            )

            available = f"/etc/nginx/sites-available/{site_name}"
            enabled = f"/etc/nginx/sites-enabled/{site_name}"
            update(35, "Gravando virtual host")
            ok, msg = SystemActions._write_text_file(available, conf_content)
            if not ok:
                return False, msg
            if not os.path.exists(enabled):
                os.symlink(available, enabled)

            update(60, "Validando configuracao do Nginx")
            result = subprocess.run(["nginx", "-t"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha no nginx -t."

            for cmd in (["systemctl", "enable", "nginx"], ["systemctl", "restart", "nginx"]):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or f"Falha ao executar: {' '.join(cmd)}"

            status_result = subprocess.run(
                ["systemctl", "status", "nginx", "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            update(100, "Reverse proxy configurado")
            return True, {
                "site_name": site_name,
                "server_names": server_name_line,
                "config_file": available,
                "upstream": f"http://{upstream_host}:{upstream_port}",
                "service_status": (status_result.stdout or status_result.stderr or "").strip(),
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def setup_certbot_https(
        domains: list[str],
        email: str,
        redirect_https: bool = True,
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            if not domains:
                return False, "Informe ao menos um dominio."
            if not email.strip():
                return False, "Informe um e-mail valido."

            update(10, "Instalando Certbot e plugin Nginx")
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha no apt-get update."
            result = subprocess.run(
                ["apt-get", "install", "-y", "certbot", "python3-certbot-nginx"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha na instalacao do Certbot."

            update(45, "Emitindo certificado")
            cmd = ["certbot", "--nginx", "--non-interactive", "--agree-tos", "-m", email]
            if redirect_https:
                cmd.append("--redirect")
            for domain in domains:
                cmd.extend(["-d", domain])
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or "Falha ao emitir certificado HTTPS."

            update(80, "Validando renovacao")
            renew = subprocess.run(["certbot", "renew", "--dry-run"], capture_output=True, text=True, check=False)
            if renew.returncode != 0:
                return False, renew.stderr.strip() or renew.stdout.strip() or "Falha no teste de renovacao do Certbot."

            timer = subprocess.run(["systemctl", "status", "certbot.timer", "--no-pager"], capture_output=True, text=True, check=False)
            update(100, "HTTPS configurado")
            return True, {
                "domains": ", ".join(domains),
                "email": email,
                "timer_status": (timer.stdout or timer.stderr or "").strip(),
                "certbot_output": (result.stdout or result.stderr or "").strip(),
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def restart_service_with_fallback(*service_names):
        for name in service_names:
            if not name:
                continue
            if subprocess.run(['systemctl', 'restart', name], check=False).returncode == 0:
                return True
            if subprocess.run(['service', name, 'restart'], check=False).returncode == 0:
                return True
        return False

    @staticmethod
    def clear_cache():
        try:
            subprocess.run(['sync'], check=True)
            with open('/proc/sys/vm/drop_caches', 'w') as f:
                f.write('3')
            return True
        except Exception as e:
            return str(e)

    @staticmethod
    def reboot():
        os.system('reboot')

    @staticmethod
    def update_system():
        manager = SystemActions._package_manager()
        if manager == 'apt':
            return [
                ['apt-get', 'update', '-y'],
                ['apt-get', 'upgrade', '-y'],
                ['apt-get', 'dist-upgrade', '-y'],
                ['apt-get', 'autoremove', '-y'],
                ['apt-get', 'autoclean', '-y'],
            ]
        if manager == 'yum':
            return [
                ['yum', '-y', 'update'],
                ['yum', '-y', 'upgrade'],
                ['yum', '-y', 'autoremove'],
                ['yum', 'clean', 'all'],
            ]
        return []

    @staticmethod
    def update_script(repo_dir: str):
        if shutil.which('git') is None:
            return False, "Git nao encontrado no sistema."
        if not os.path.isdir(repo_dir):
            return False, f"Diretorio do repositorio nao encontrado: {repo_dir}"

        result = subprocess.run(
            ['git', '-C', repo_dir, 'rev-parse', '--is-inside-work-tree'],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False, "Diretorio informado nao e um repositorio git."

        fetch = subprocess.run(
            ['git', '-C', repo_dir, 'fetch', '--all'],
            capture_output=True,
            text=True,
            check=False,
        )
        if fetch.returncode != 0:
            return False, fetch.stderr.strip() or "Falha no git fetch."

        pull = subprocess.run(
            ['git', '-C', repo_dir, 'pull', '--ff-only'],
            capture_output=True,
            text=True,
            check=False,
        )
        if pull.returncode != 0:
            return False, pull.stderr.strip() or "Falha no git pull."
        message = (pull.stdout or "").strip() or "Script atualizado com sucesso."
        return True, message

    @staticmethod
    def create_menu_command(repo_dir: str, command_name: str = 'menu'):
        if os.name == 'nt':
            return False, "Comando global automatico nao suportado no Windows."
        if not os.path.isdir(repo_dir):
            return False, f"Diretorio do repositorio nao encontrado: {repo_dir}"
        if not re.match(r'^[a-zA-Z0-9._-]+$', command_name):
            return False, "Nome de comando invalido. Use apenas letras, numeros, ponto, _ ou -."

        current = shutil.which(command_name)
        target = f"/usr/local/bin/{command_name}"
        if current and current != target:
            return False, f"O comando '{command_name}' ja existe em {current}."

        launcher = (
            "#!/usr/bin/env bash\n"
            "set -e\n"
            f'REPO_DIR="{repo_dir}"\n'
            'cd "$REPO_DIR"\n'
            'if [ -x "$REPO_DIR/.venv/bin/python" ]; then\n'
            '  exec "$REPO_DIR/.venv/bin/python" -m vps_tools.main "$@"\n'
            "fi\n"
            'exec python3 -m vps_tools.main "$@"\n'
        )
        try:
            with open(target, 'w') as f:
                f.write(launcher)
            os.chmod(target, 0o755)
            return True, f"Comando '{command_name}' criado em {target}"
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def create_swap(size_mb: int = 1024, swap_path: str = "/swapfile"):
        if os.name == "nt":
            return False, "Criacao de swap nao suportada no Windows."
        if size_mb < 256:
            return False, "Tamanho minimo recomendado: 256 MB."
        if shutil.which("mkswap") is None or shutil.which("swapon") is None:
            return False, "Ferramentas de swap nao encontradas (mkswap/swapon)."

        try:
            with open("/proc/swaps", "r") as f:
                lines = [line for line in f.read().splitlines() if line.strip()]
            if len(lines) > 1:
                return False, "Ja existe swap ativo no sistema."
        except Exception:
            pass

        if os.path.exists(swap_path):
            return False, f"Arquivo de swap ja existe: {swap_path}"

        fallocate_ok = False
        if shutil.which("fallocate") is not None:
            fallocate_ok = (
                subprocess.run(
                    ["fallocate", "-l", f"{size_mb}M", swap_path], check=False
                ).returncode
                == 0
            )
        if not fallocate_ok:
            dd_cmd = [
                "dd",
                "if=/dev/zero",
                f"of={swap_path}",
                "bs=1M",
                f"count={size_mb}",
                "status=progress",
            ]
            dd_result = subprocess.run(dd_cmd, check=False)
            if dd_result.returncode != 0:
                return False, "Falha ao criar arquivo de swap."

        chmod_result = subprocess.run(["chmod", "600", swap_path], check=False)
        if chmod_result.returncode != 0:
            return False, "Falha ao ajustar permissoes do swapfile."

        mk_result = subprocess.run(["mkswap", swap_path], check=False)
        if mk_result.returncode != 0:
            return False, "Falha ao formatar swapfile com mkswap."

        on_result = subprocess.run(["swapon", swap_path], check=False)
        if on_result.returncode != 0:
            return False, "Falha ao ativar swap com swapon."

        try:
            with open("/etc/fstab", "r") as f:
                fstab = f.read()
        except Exception:
            fstab = ""

        entry = f"{swap_path} none swap sw 0 0"
        if entry not in fstab:
            try:
                with open("/etc/fstab", "a") as f:
                    f.write(f"\n{entry}\n")
            except Exception as exc:
                return False, f"Swap criado, mas falhou ao persistir no fstab: {exc}"

        return True, f"Swap de {size_mb} MB criado e ativado em {swap_path}."

    @staticmethod
    def measure_server_speed(progress_callback=None):
        def update(percent, text):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            # Ping (TCP connect latency approximation)
            update(5, "Medindo latencia")
            latencies = []
            for _ in range(3):
                start = time.perf_counter()
                sock = socket.create_connection(("1.1.1.1", 443), timeout=3)
                sock.close()
                latencies.append((time.perf_counter() - start) * 1000)
            ping_ms = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

            # Download test
            update(20, "Testando download")
            total_read = 0
            target_bytes = 5 * 1024 * 1024  # 5 MB for faster test
            download_urls = [
                "https://proof.ovh.net/files/10Mb.dat",
                "https://ash-speed.hetzner.com/10MB.bin",
                "https://raw.githubusercontent.com/github/gitignore/main/Python.gitignore",
            ]
            start = time.perf_counter()
            last_download_error = "Falha em todas as fontes de download."
            for download_url in download_urls:
                try:
                    total_read = 0
                    with requests.get(download_url, stream=True, timeout=20) as response:
                        response.raise_for_status()
                        for chunk in response.iter_content(chunk_size=64 * 1024):
                            if not chunk:
                                continue
                            total_read += len(chunk)
                            ratio = min(1.0, total_read / target_bytes)
                            update(20 + int(ratio * 45), f"Testando download ({download_url})")
                            if total_read >= target_bytes:
                                break
                    if total_read > 0:
                        break
                except Exception as exc:
                    last_download_error = str(exc)
                    continue
            if total_read <= 0:
                return False, f"Falha no download: {last_download_error}"
            download_seconds = max(time.perf_counter() - start, 0.001)
            download_mbps = round((total_read * 8) / (download_seconds * 1_000_000), 2)

            # Upload test
            update(70, "Testando upload")
            payload = os.urandom(2 * 1024 * 1024)  # 2 MB
            upload_urls = [
                "https://httpbin.org/post",
                "https://eu.httpbin.org/post",
                "https://postman-echo.com/post",
            ]
            start = time.perf_counter()
            last_upload_error = "Falha em todas as fontes de upload."
            upload_ok = False
            for upload_url in upload_urls:
                try:
                    response = requests.post(upload_url, data=payload, timeout=25)
                    response.raise_for_status()
                    upload_ok = True
                    break
                except Exception as exc:
                    last_upload_error = str(exc)
                    continue
            if not upload_ok:
                return False, f"Falha no upload: {last_upload_error}"
            upload_seconds = max(time.perf_counter() - start, 0.001)
            upload_mbps = round((len(payload) * 8) / (upload_seconds * 1_000_000), 2)
            update(95, "Finalizando")

            return True, {
                "ping_ms": ping_ms,
                "download_mbps": download_mbps,
                "upload_mbps": upload_mbps,
                "download_mb_tested": round(total_read / (1024 * 1024), 2),
                "upload_mb_tested": round(len(payload) / (1024 * 1024), 2),
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def install_browser(browser: str):
        browser = (browser or "").strip().lower()
        manager = SystemActions._package_manager()
        if manager not in {"apt", "yum"}:
            return False, "Gerenciador de pacotes nao suportado."

        try:
            if browser == "firefox":
                if manager == "apt":
                    subprocess.run(["apt-get", "update", "-y"], check=True)
                    subprocess.run(["apt-get", "install", "-y", "firefox"], check=True)
                else:
                    subprocess.run(["yum", "-y", "install", "firefox"], check=True)
                return True, "Firefox instalado com sucesso."

            if browser == "chromium":
                if manager == "apt":
                    subprocess.run(["apt-get", "update", "-y"], check=True)
                    subprocess.run(["apt-get", "install", "-y", "chromium-browser"], check=False)
                    # fallback para distros que usam pacote chromium
                    if shutil.which("chromium-browser") is None:
                        subprocess.run(["apt-get", "install", "-y", "chromium"], check=True)
                else:
                    subprocess.run(["yum", "-y", "install", "chromium"], check=True)
                return True, "Chromium instalado com sucesso."

            if browser == "brave":
                if manager == "apt":
                    subprocess.run(["apt-get", "update", "-y"], check=True)
                    subprocess.run(["apt-get", "install", "-y", "curl", "gnupg"], check=True)
                    subprocess.run(
                        ["bash", "-lc", "curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg"],
                        check=True,
                    )
                    subprocess.run(
                        [
                            "bash",
                            "-lc",
                            "echo 'deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] https://brave-browser-apt-release.s3.brave.com/ stable main' > /etc/apt/sources.list.d/brave-browser-release.list",
                        ],
                        check=True,
                    )
                    subprocess.run(["apt-get", "update", "-y"], check=True)
                    subprocess.run(["apt-get", "install", "-y", "brave-browser"], check=True)
                else:
                    return False, "Brave automatico suportado apenas em Debian/Ubuntu."
                return True, "Brave instalado com sucesso."

            return False, f"Navegador desconhecido: {browser}"
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def set_default_browser(browser: str):
        browser = (browser or "").strip().lower()
        candidates = {
            "firefox": "firefox.desktop",
            "chromium": "chromium-browser.desktop",
            "brave": "brave-browser.desktop",
        }
        desktop = candidates.get(browser)
        if not desktop:
            return False, "Navegador invalido para definir padrao."

        # Para servidor sem sessão desktop ativa, tentamos update-alternatives.
        if shutil.which("xdg-settings"):
            result = subprocess.run(
                ["xdg-settings", "set", "default-web-browser", desktop],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return True, f"Navegador padrao definido: {browser}"

        if shutil.which("update-alternatives"):
            binary = "firefox" if browser == "firefox" else ("chromium-browser" if browser == "chromium" else "brave-browser")
            result = subprocess.run(
                ["update-alternatives", "--set", "x-www-browser", f"/usr/bin/{binary}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return True, f"Navegador padrao definido: {browser}"

        return False, "Nao foi possivel definir navegador padrao automaticamente."
