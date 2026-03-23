import json
import os
import re
import secrets
import shlex
import shutil
import socket
import ssl
import string
import subprocess
import tarfile
import time
import calendar

import psutil
import requests

from vps_tools.core.i18n import LanguageManager


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
    _i18n = LanguageManager("pt")

    @staticmethod
    def set_language(lang: str):
        SystemActions._i18n.set_language(lang)

    @staticmethod
    def _txt(pt: str, en: str) -> str:
        return SystemActions._i18n.t_pair(pt, en)

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
            return False, SystemActions._txt(f"{label} nao pode ser vazio.", f"{label} cannot be empty.")
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
            return False, SystemActions._txt(
                f"{label} invalido. Use apenas letras, numeros e underscore, iniciando com letra ou underscore.",
                f"Invalid {label}. Use only letters, numbers, and underscores, starting with a letter or underscore.",
            )
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
            raise RuntimeError(
                SystemActions._txt(
                    "Nao foi possivel localizar runuser/su para executar comandos como postgres.",
                    "Could not find runuser/su to execute commands as postgres.",
                )
            )
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
            return False, SystemActions._txt(
                f"Arquivo de configuracao nao encontrado: {conf_path}",
                f"Configuration file not found: {conf_path}",
            )

        try:
            with open(conf_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
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
    def _replace_or_append_plain_setting(conf_path: str, key: str, value: str):
        if not os.path.exists(conf_path):
            return False, SystemActions._txt(
                f"Arquivo de configuracao nao encontrado: {conf_path}",
                f"Configuration file not found: {conf_path}",
            )
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
    def _postgresql_runtime_setting(setting_name: str):
        result = SystemActions._run_as_postgres(
            ["psql", "-At", "-d", "postgres", "-c", f"SHOW {setting_name};"]
        )
        if result.returncode != 0:
            return False, (result.stderr or result.stdout or "").strip() or SystemActions._txt(
                f"Falha ao consultar SHOW {setting_name}.",
                f"Failed to query SHOW {setting_name}.",
            )
        return True, (result.stdout or "").strip()

    @staticmethod
    def _detect_web_db_panel_network(app_dir: str = "/opt/vps-tools-db-panel", docker_network_name: str = ""):
        network_name = (docker_network_name or "").strip()
        if not network_name:
            compose_file = os.path.join(app_dir, "compose.yml")
            if os.path.exists(compose_file):
                try:
                    with open(compose_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    match = re.search(r'(?m)^name:\s*"?([^"\n]+)"?\s*$', content)
                    if match:
                        network_name = f"{match.group(1).strip()}_default"
                except Exception as exc:
                    return False, str(exc)
        if not network_name:
            return False, SystemActions._txt(
                "Nao foi possivel detectar o nome da rede Docker do painel.",
                "Could not detect the panel Docker network name.",
            )

        result = subprocess.run(
            ["docker", "network", "inspect", network_name],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False, (result.stderr or result.stdout or "").strip() or SystemActions._txt(
                f"Falha ao inspecionar a rede Docker {network_name}.",
                f"Failed to inspect Docker network {network_name}.",
            )
        try:
            payload = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            return False, str(exc)
        if not payload:
            return False, SystemActions._txt(
                "A inspecao da rede Docker nao retornou dados.",
                "Docker network inspection returned no data.",
            )

        network = payload[0] if isinstance(payload[0], dict) else {}
        ipam = network.get("IPAM") if isinstance(network, dict) else {}
        configs = ipam.get("Config") if isinstance(ipam, dict) else []
        config0 = configs[0] if configs and isinstance(configs[0], dict) else {}
        subnet = (config0.get("Subnet") or "").strip()
        gateway = (config0.get("Gateway") or "").strip()
        return True, {
            "network_name": network_name,
            "subnet": subnet,
            "gateway": gateway,
        }

    @staticmethod
    def _detect_docker_host_gateway_ip():
        daemon_json_path = "/etc/docker/daemon.json"
        if os.path.exists(daemon_json_path):
            try:
                with open(daemon_json_path, "r", encoding="utf-8") as f:
                    daemon_config = json.load(f)
                if isinstance(daemon_config, dict):
                    single_ip = (daemon_config.get("host-gateway-ip") or "").strip()
                    if single_ip:
                        return True, single_ip
                    ip_list = daemon_config.get("host-gateway-ips")
                    if isinstance(ip_list, list):
                        for item in ip_list:
                            ip_value = str(item or "").strip()
                            if ip_value and ":" not in ip_value:
                                return True, ip_value
            except Exception:
                pass

        result = subprocess.run(
            ["docker", "network", "inspect", "bridge"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False, (result.stderr or result.stdout or "").strip() or SystemActions._txt(
                "Falha ao detectar a bridge padrao do Docker.",
                "Failed to detect the default Docker bridge.",
            )
        try:
            payload = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            return False, str(exc)
        if not payload:
            return False, SystemActions._txt(
                "A inspecao da bridge padrao do Docker nao retornou dados.",
                "Inspection of the default Docker bridge returned no data.",
            )
        network = payload[0] if isinstance(payload[0], dict) else {}
        ipam = network.get("IPAM") if isinstance(network, dict) else {}
        configs = ipam.get("Config") if isinstance(ipam, dict) else []
        config0 = configs[0] if configs and isinstance(configs[0], dict) else {}
        gateway = (config0.get("Gateway") or "").strip()
        if not gateway:
            return False, SystemActions._txt(
                "Nao foi possivel detectar o host-gateway padrao do Docker.",
                "Could not detect the default Docker host gateway.",
            )
        return True, gateway

    @staticmethod
    def _upsert_pg_hba_rule(conf_path: str, database: str, db_user: str, cidr: str, auth_method: str):
        if not os.path.exists(conf_path):
            return False, SystemActions._txt(
                f"Arquivo de configuracao nao encontrado: {conf_path}",
                f"Configuration file not found: {conf_path}",
            )
        try:
            with open(conf_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as exc:
            return False, str(exc)

        rule = f"host    {database}    {db_user}    {cidr}    {auth_method}\n"
        pattern = re.compile(
            rf"^\s*host\s+{re.escape(database)}\s+{re.escape(db_user)}\s+{re.escape(cidr)}\s+\S+"
        )
        replaced = False
        output = []
        for line in lines:
            if pattern.match(line) and not replaced:
                output.append(rule)
                replaced = True
            else:
                output.append(line)
        if not replaced:
            if output and not output[-1].endswith("\n"):
                output[-1] += "\n"
            output.append("\n" if output and output[-1].strip() else "")
            output.append("# Added by VPS Tools for local Docker DB panel access\n")
            output.append(rule)
        try:
            with open(conf_path, "w", encoding="utf-8") as f:
                f.writelines(output)
            return True, conf_path
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _set_mongod_config(conf_path: str, bind_ip: str, port: int, auth_enabled: bool):
        if not os.path.exists(conf_path):
            return False, SystemActions._txt(
                f"Arquivo de configuracao nao encontrado: {conf_path}",
                f"Configuration file not found: {conf_path}",
            )
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
    def _write_json_file(path: str, payload, mode: int | None = None):
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.write("\n")
            if mode is not None:
                os.chmod(path, mode)
            return True, path
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _read_json_file(path: str, default=None):
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    @staticmethod
    def _copy_path_if_exists(src: str, dst: str):
        try:
            if not os.path.exists(src):
                return True, ""
            parent = os.path.dirname(dst)
            if parent:
                os.makedirs(parent, exist_ok=True)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            return True, dst
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _merge_json_file(path: str, updates: dict):
        data = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
                else:
                    return False, SystemActions._txt(
                        f"Arquivo JSON invalido para mesclagem: {path}",
                        f"Invalid JSON file for merge: {path}",
                    )
            except Exception as exc:
                return False, str(exc)
        data.update(updates)
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
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
            return False, SystemActions._txt("Nome do servico nao pode ser vazio.", "Service name cannot be empty.")
        if not re.match(r"^[A-Za-z0-9_.@-]+$", value):
            return False, SystemActions._txt(
                "Nome do servico invalido. Use apenas letras, numeros, ponto, underscore, @ ou -.",
                "Invalid service name. Use only letters, numbers, dot, underscore, @, or -.",
            )
        return True, ""

    @staticmethod
    def _env_file_content(env_vars: dict[str, str]) -> str:
        lines = []
        for key, value in env_vars.items():
            safe_key = re.sub(r"[^A-Za-z0-9_]", "_", key or "").upper()
            lines.append(f"{safe_key}={shlex.quote(str(value))}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _read_env_file(path: str) -> dict[str, str]:
        values: dict[str, str] = {}
        if not os.path.exists(path):
            return values
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    safe_key = re.sub(r"[^A-Za-z0-9_]", "_", key or "").upper()
                    parsed = shlex.split(value, posix=True)
                    values[safe_key] = parsed[0] if parsed else value.strip().strip("'").strip('"')
        except Exception:
            return {}
        return values

    @staticmethod
    def _dr_root_dir() -> str:
        return "/opt/vps-tools/dr"

    @staticmethod
    def _dr_profiles_dir() -> str:
        return os.path.join(SystemActions._dr_root_dir(), "profiles")

    @staticmethod
    def _dr_jobs_dir() -> str:
        return os.path.join(SystemActions._dr_root_dir(), "jobs")

    @staticmethod
    def _dr_monitoring_dir() -> str:
        return os.path.join(SystemActions._dr_root_dir(), "monitoring")

    @staticmethod
    def _dr_runbooks_dir() -> str:
        return os.path.join(SystemActions._dr_root_dir(), "runbooks")

    @staticmethod
    def _dr_operation_logs_dir() -> str:
        return os.path.join(SystemActions._dr_root_dir(), "operations")

    @staticmethod
    def _dr_exercises_dir() -> str:
        return os.path.join(SystemActions._dr_root_dir(), "exercises")

    @staticmethod
    def _dr_backup_job_paths(job_name: str):
        safe_job = re.sub(r"[^A-Za-z0-9_-]", "-", job_name or "").strip("-")
        job_dir = os.path.join(SystemActions._dr_jobs_dir(), safe_job)
        return {
            "safe_job": safe_job,
            "job_dir": job_dir,
            "config_file": os.path.join(job_dir, "job.json"),
            "status_file": os.path.join(job_dir, "last_status.json"),
            "restore_status_file": os.path.join(job_dir, "last_restore_test.json"),
            "restore_tests_dir": os.path.join(job_dir, "restore-tests"),
            "env_file": os.path.join(job_dir, "job.env"),
            "script_file": os.path.join(job_dir, "run-backup.sh"),
            "service_name": f"vps-tools-db-backup-{safe_job}",
            "timer_name": f"vps-tools-db-backup-{safe_job}.timer",
            "service_unit": f"/etc/systemd/system/vps-tools-db-backup-{safe_job}.service",
            "timer_unit": f"/etc/systemd/system/vps-tools-db-backup-{safe_job}.timer",
        }

    @staticmethod
    def _dr_monitor_paths(monitor_name: str = "default"):
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "-", monitor_name or "").strip("-") or "default"
        monitor_dir = os.path.join(SystemActions._dr_monitoring_dir(), safe_name)
        service_name = f"vps-tools-dr-monitor-{safe_name}"
        return {
            "safe_name": safe_name,
            "monitor_dir": monitor_dir,
            "config_file": os.path.join(monitor_dir, "monitor.json"),
            "report_file": os.path.join(monitor_dir, "last_report.json"),
            "script_file": os.path.join(monitor_dir, "run-monitor.sh"),
            "service_name": service_name,
            "timer_name": f"{service_name}.timer",
            "service_unit": f"/etc/systemd/system/{service_name}.service",
            "timer_unit": f"/etc/systemd/system/{service_name}.timer",
        }

    @staticmethod
    def _repo_root_dir() -> str:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    @staticmethod
    def _preferred_python_binary() -> str:
        repo_dir = SystemActions._repo_root_dir()
        candidates = [
            os.path.join(repo_dir, ".venv", "bin", "python"),
            os.path.join(repo_dir, "venv", "bin", "python"),
            shutil.which("python3") or "",
            shutil.which("python") or "",
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
        return "python3"

    @staticmethod
    def _parse_duration_to_seconds(value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip().lower()
        if not text:
            return None
        total = 0
        matched = False
        units = {
            "s": 1,
            "sec": 1,
            "secs": 1,
            "second": 1,
            "seconds": 1,
            "m": 60,
            "min": 60,
            "mins": 60,
            "minute": 60,
            "minutes": 60,
            "h": 3600,
            "hr": 3600,
            "hour": 3600,
            "hours": 3600,
            "d": 86400,
            "day": 86400,
            "days": 86400,
        }
        normalized = (
            text.replace("minutos", "minutes")
            .replace("minuto", "minute")
            .replace("horas", "hours")
            .replace("hora", "hour")
            .replace("segundos", "seconds")
            .replace("segundo", "second")
            .replace("dias", "days")
            .replace("dia", "day")
        )
        for number, unit in re.findall(r"(\d+)\s*([a-z]+)", normalized):
            factor = units.get(unit)
            if factor:
                matched = True
                total += int(number) * factor
        if matched:
            return total
        if text.isdigit():
            return int(text)
        return None

    @staticmethod
    def _format_duration_short(seconds):
        if seconds is None:
            return "-"
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            minutes, rem = divmod(seconds, 60)
            return f"{minutes}m {rem}s" if rem else f"{minutes}m"
        hours, rem = divmod(seconds, 3600)
        minutes = rem // 60
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"

    @staticmethod
    def _parse_iso_timestamp(value: str):
        text = (value or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = time.strptime(text, fmt)
                if "T" in fmt:
                    return int(calendar.timegm(parsed))
                return int(time.mktime(parsed))
            except Exception:
                continue
        return None

    @staticmethod
    def _append_jsonl_line(path: str, payload):
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
                f.write("\n")
            return True, path
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _dr_monitor_script_content(config_file: str, repo_dir: str, python_bin: str) -> str:
        return (
            "#!/usr/bin/env bash\n"
            "set -Eeuo pipefail\n"
            f"export PYTHONPATH={shlex.quote(repo_dir)}\n"
            f"exec {shlex.quote(python_bin)} - {shlex.quote(config_file)} <<'PY'\n"
            "import json\n"
            "import sys\n"
            "from vps_tools.core.system import SystemActions\n"
            "ok, data = SystemActions.run_dr_monitoring_check(config_path=sys.argv[1])\n"
            "if not ok:\n"
            "    if isinstance(data, dict):\n"
            "        print(data.get('message', 'monitoring failed'))\n"
            "    else:\n"
            "        print(data)\n"
            "    raise SystemExit(1)\n"
            "print(json.dumps(data, ensure_ascii=False))\n"
            "PY\n"
        )

    @staticmethod
    def _db_backup_script_content(job_name: str, engine: str, output_extension: str, compression_enabled: bool) -> str:
        compression_value = "1" if compression_enabled else "0"
        return (
            "#!/usr/bin/env bash\n"
            "set -Eeuo pipefail\n"
            "umask 077\n"
            "\n"
            f"JOB_NAME={shlex.quote(job_name)}\n"
            f"ENGINE={shlex.quote(engine)}\n"
            f"OUTPUT_EXTENSION={shlex.quote(output_extension)}\n"
            f"COMPRESSION_ENABLED={compression_value}\n"
            "\n"
            'STATUS_FILE="${STATUS_FILE:?STATUS_FILE is required}"\n'
            'BACKUP_DIR="${BACKUP_DIR:?BACKUP_DIR is required}"\n'
            'RETENTION_COUNT="${RETENTION_COUNT:-7}"\n'
            'VERIFY_FREE_MB="${VERIFY_FREE_MB:-512}"\n'
            'DB_HOST="${DB_HOST:-127.0.0.1}"\n'
            'DB_PORT="${DB_PORT:-0}"\n'
            'DB_NAME="${DB_NAME:-}"\n'
            'DB_USER="${DB_USER:-}"\n'
            'DB_PASSWORD="${DB_PASSWORD:-}"\n'
            'AUTH_DB="${AUTH_DB:-}"\n'
            'OFFSITE_MODE="${OFFSITE_MODE:-none}"\n'
            'OFFSITE_PATH="${OFFSITE_PATH:-}"\n'
            'OFFSITE_HOST="${OFFSITE_HOST:-}"\n'
            'OFFSITE_PORT="${OFFSITE_PORT:-22}"\n'
            'OFFSITE_USER="${OFFSITE_USER:-}"\n'
            'OFFSITE_SSH_KEY="${OFFSITE_SSH_KEY:-}"\n'
            'OFFSITE_KNOWN_HOSTS="${OFFSITE_KNOWN_HOSTS:-}"\n'
            'OFFSITE_TIMEOUT_SEC="${OFFSITE_TIMEOUT_SEC:-30}"\n'
            'ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"\n'
            'ALERT_ON_SUCCESS="${ALERT_ON_SUCCESS:-0}"\n'
            'ALERT_ON_FAILURE="${ALERT_ON_FAILURE:-1}"\n'
            'ALERT_TIMEOUT_SEC="${ALERT_TIMEOUT_SEC:-10}"\n'
            'ENCRYPTION_MODE="${ENCRYPTION_MODE:-none}"\n'
            'ENCRYPTION_PASSPHRASE="${ENCRYPTION_PASSPHRASE:-}"\n'
            'ENCRYPTION_CIPHER="${ENCRYPTION_CIPHER:-AES256}"\n'
            "\n"
            'timestamp="$(date -u +%Y%m%dT%H%M%SZ)"\n'
            'finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"\n'
            'start_epoch="$(date +%s)"\n'
            'artifact_path=""\n'
            'checksum_path=""\n'
            'status="failed"\n'
            'message=""\n'
            'tmp_dir=""\n'
            'duration_seconds="0"\n'
            'offsite_artifact_path=""\n'
            'offsite_checksum_path=""\n'
            'offsite_status="disabled"\n'
            'offsite_message=""\n'
            'alert_status="disabled"\n'
            'alert_message=""\n'
            'encryption_status="disabled"\n'
            'encryption_message=""\n'
            'preflight_status="disabled"\n'
            'preflight_message=""\n'
            'raw_backup=""\n'
            "\n"
            "write_status() {\n"
            '  python3 - "$STATUS_FILE" "$JOB_NAME" "$ENGINE" "$status" "$artifact_path" "$checksum_path" "$finished_at" "$duration_seconds" "$message" "$offsite_artifact_path" "$offsite_checksum_path" "$offsite_status" "$offsite_message" "$alert_status" "$alert_message" "$encryption_status" "$encryption_message" "$ENCRYPTION_MODE" "$ENCRYPTION_CIPHER" "$preflight_status" "$preflight_message" <<\'PY\'\n'
            "import json, sys\n"
            "(\n"
            "    path,\n"
            "    job,\n"
            "    engine,\n"
            "    status,\n"
            "    artifact,\n"
            "    checksum,\n"
            "    finished_at,\n"
            "    duration_seconds,\n"
            "    message,\n"
            "    offsite_artifact,\n"
            "    offsite_checksum,\n"
            "    offsite_status,\n"
            "    offsite_message,\n"
            "    alert_status,\n"
            "    alert_message,\n"
            "    encryption_status,\n"
            "    encryption_message,\n"
            "    encryption_mode,\n"
            "    encryption_cipher,\n"
            "    preflight_status,\n"
            "    preflight_message,\n"
            ") = sys.argv[1:]\n"
            "payload = {\n"
            '    "job_name": job,\n'
            '    "engine": engine,\n'
            '    "status": status,\n'
            '    "artifact_path": artifact,\n'
            '    "checksum_path": checksum,\n'
            '    "finished_at": finished_at,\n'
            '    "duration_seconds": int(duration_seconds or "0"),\n'
            '    "message": message,\n'
            '    "offsite_artifact_path": offsite_artifact,\n'
            '    "offsite_checksum_path": offsite_checksum,\n'
            '    "offsite_status": offsite_status,\n'
            '    "offsite_message": offsite_message,\n'
            '    "alert_status": alert_status,\n'
            '    "alert_message": alert_message,\n'
            '    "encryption_status": encryption_status,\n'
            '    "encryption_message": encryption_message,\n'
            '    "encryption_mode": encryption_mode,\n'
            '    "encryption_cipher": encryption_cipher,\n'
            '    "preflight_status": preflight_status,\n'
            '    "preflight_message": preflight_message,\n'
            "}\n"
            "with open(path, 'w', encoding='utf-8') as f:\n"
            "    json.dump(payload, f, ensure_ascii=False, indent=2)\n"
            "    f.write('\\n')\n"
            "PY\n"
            "}\n"
            "\n"
            "send_alert() {\n"
            '  if [ -z "$ALERT_WEBHOOK_URL" ]; then\n'
            '    alert_status="disabled"\n'
            '    alert_message="alert webhook not configured"\n'
            "    return 0\n"
            "  fi\n"
            '  if [ "$status" = "success" ] && [ "$ALERT_ON_SUCCESS" != "1" ]; then\n'
            '    alert_status="skipped"\n'
            '    alert_message="success alerts disabled"\n'
            "    return 0\n"
            "  fi\n"
            '  if [ "$status" != "success" ] && [ "$ALERT_ON_FAILURE" != "1" ]; then\n'
            '    alert_status="skipped"\n'
            '    alert_message="failure alerts disabled"\n'
            "    return 0\n"
            "  fi\n"
            '  if ! command -v curl >/dev/null 2>&1; then\n'
            '    alert_status="failed"\n'
            '    alert_message="curl not found"\n'
            "    return 0\n"
            "  fi\n"
            '  local payload_root="${tmp_dir:-/tmp}"\n'
            '  mkdir -p "$payload_root"\n'
            '  local payload_file="$payload_root/alert-payload.json"\n'
            '  python3 - "$payload_file" "$JOB_NAME" "$ENGINE" "$status" "$artifact_path" "$checksum_path" "$finished_at" "$duration_seconds" "$message" "$offsite_status" "$offsite_artifact_path" <<\'PY\'\n'
            "import json, sys\n"
            "path, job, engine, status, artifact, checksum, finished_at, duration_seconds, message, offsite_status, offsite_artifact = sys.argv[1:]\n"
            "payload = {\n"
            '    "job_name": job,\n'
            '    "engine": engine,\n'
            '    "status": status,\n'
            '    "artifact_path": artifact,\n'
            '    "checksum_path": checksum,\n'
            '    "finished_at": finished_at,\n'
            '    "duration_seconds": int(duration_seconds or "0"),\n'
            '    "message": message,\n'
            '    "offsite_status": offsite_status,\n'
            '    "offsite_artifact_path": offsite_artifact,\n'
            "}\n"
            "with open(path, 'w', encoding='utf-8') as f:\n"
            "    json.dump(payload, f, ensure_ascii=False)\n"
            "PY\n"
            '  if curl --silent --show-error --fail --max-time "$ALERT_TIMEOUT_SEC" -X POST -H "Content-Type: application/json" --data-binary "@$payload_file" "$ALERT_WEBHOOK_URL" >/dev/null; then\n'
            '    alert_status="sent"\n'
            '    alert_message="alert delivered"\n'
            "  else\n"
            '    alert_status="failed"\n'
            '    alert_message="alert delivery failed"\n'
            "  fi\n"
            "}\n"
            "\n"
            "apply_retention() {\n"
            '  local target_dir="$1"\n'
            '  mapfile -t old_files < <(find "$target_dir" -maxdepth 1 -type f -name "${JOB_NAME}_*${OUTPUT_EXTENSION}" | sort -r)\n'
            '  if [ "${#old_files[@]}" -gt "$RETENTION_COUNT" ]; then\n'
            '    for old_file in "${old_files[@]:$RETENTION_COUNT}"; do\n'
            '      rm -f "$old_file" "$old_file.sha256"\n'
            "    done\n"
            "  fi\n"
            "}\n"
            "\n"
            "encrypt_backup() {\n"
            '  raw_backup="$1"\n'
            '  case "$ENCRYPTION_MODE" in\n'
            "    ''|none)\n"
            '      mv "$raw_backup" "$artifact_path"\n'
            '      encryption_status="disabled"\n'
            '      encryption_message="backup encryption not configured"\n'
            "      ;;\n"
            "    gpg_symmetric)\n"
            '      if ! command -v gpg >/dev/null 2>&1; then\n'
            '        encryption_status="failed"\n'
            '        encryption_message="gpg not found"\n'
            "        return 1\n"
            "      fi\n"
            '      if [ -z "$ENCRYPTION_PASSPHRASE" ]; then\n'
            '        encryption_status="failed"\n'
            '        encryption_message="encryption passphrase is required"\n'
            "        return 1\n"
            "      fi\n"
            '      printf "%s" "$ENCRYPTION_PASSPHRASE" | gpg --batch --yes --pinentry-mode loopback --passphrase-fd 0 --cipher-algo "$ENCRYPTION_CIPHER" --symmetric --output "$artifact_path" "$raw_backup"\n'
            '      rm -f "$raw_backup"\n'
            '      encryption_status="success"\n'
            '      encryption_message="backup encrypted successfully"\n'
            "      ;;\n"
            "    *)\n"
            '      encryption_status="failed"\n'
            '      encryption_message="invalid encryption mode"\n'
            "      return 1\n"
            "      ;;\n"
            "  esac\n"
            "}\n"
            "\n"
            "copy_offsite() {\n"
            '  case "$OFFSITE_MODE" in\n'
            "    ''|none)\n"
            '      offsite_status="disabled"\n'
            '      offsite_message="offsite copy not configured"\n'
            "      return 0\n"
            "      ;;\n"
            "    local_copy)\n"
            '      if [ -z "$OFFSITE_PATH" ]; then\n'
            '        offsite_status="failed"\n'
            '        offsite_message="offsite path is required for local_copy"\n'
            "        return 1\n"
            "      fi\n"
            '      mkdir -p "$OFFSITE_PATH"\n'
            '      cp "$artifact_path" "$OFFSITE_PATH/"\n'
            '      cp "$checksum_path" "$OFFSITE_PATH/"\n'
            '      offsite_artifact_path="$OFFSITE_PATH/$(basename "$artifact_path")"\n'
            '      offsite_checksum_path="$OFFSITE_PATH/$(basename "$checksum_path")"\n'
            '      (cd "$OFFSITE_PATH" && sha256sum -c "$(basename "$offsite_checksum_path")" >/dev/null)\n'
            '      apply_retention "$OFFSITE_PATH"\n'
            '      offsite_status="success"\n'
            '      offsite_message="secondary copy completed"\n'
            "      ;;\n"
            "    scp)\n"
            '      if [ -z "$OFFSITE_PATH" ] || [ -z "$OFFSITE_HOST" ] || [ -z "$OFFSITE_USER" ]; then\n'
            '        offsite_status="failed"\n'
            '        offsite_message="scp destination is incomplete"\n'
            "        return 1\n"
            "      fi\n"
            '      ssh_opts=(-p "$OFFSITE_PORT" -o BatchMode=yes -o "ConnectTimeout=$OFFSITE_TIMEOUT_SEC")\n'
            '      scp_opts=(-P "$OFFSITE_PORT" -o BatchMode=yes -o "ConnectTimeout=$OFFSITE_TIMEOUT_SEC")\n'
            '      if [ -n "$OFFSITE_SSH_KEY" ]; then\n'
            '        ssh_opts+=(-i "$OFFSITE_SSH_KEY")\n'
            '        scp_opts+=(-i "$OFFSITE_SSH_KEY")\n'
            "      fi\n"
            '      if [ -n "$OFFSITE_KNOWN_HOSTS" ]; then\n'
            '        ssh_opts+=(-o "UserKnownHostsFile=$OFFSITE_KNOWN_HOSTS" -o StrictHostKeyChecking=yes)\n'
            '        scp_opts+=(-o "UserKnownHostsFile=$OFFSITE_KNOWN_HOSTS" -o StrictHostKeyChecking=yes)\n'
            "      else\n"
            '        ssh_opts+=(-o StrictHostKeyChecking=accept-new)\n'
            '        scp_opts+=(-o StrictHostKeyChecking=accept-new)\n'
            "      fi\n"
            '      remote_target="$OFFSITE_USER@$OFFSITE_HOST"\n'
            '      remote_dir_q="$(printf %q "$OFFSITE_PATH")"\n'
            '      remote_checksum_q="$(printf %q "$(basename "$checksum_path")")"\n'
            '      remote_pattern="${JOB_NAME}_*${OUTPUT_EXTENSION}"\n'
            '      ssh "${ssh_opts[@]}" "$remote_target" "mkdir -p $remote_dir_q"\n'
            '      scp "${scp_opts[@]}" "$artifact_path" "$checksum_path" "$remote_target:$OFFSITE_PATH/"\n'
            '      ssh "${ssh_opts[@]}" "$remote_target" "cd $remote_dir_q && sha256sum -c $remote_checksum_q >/dev/null"\n'
            '      ssh "${ssh_opts[@]}" "$remote_target" "cd $remote_dir_q && for old_file in \\$(ls -1t $remote_pattern 2>/dev/null | tail -n +$((RETENTION_COUNT + 1))); do rm -f -- \\"\\$old_file\\" \\"\\$old_file.sha256\\"; done"\n'
            '      offsite_artifact_path="$OFFSITE_USER@$OFFSITE_HOST:$OFFSITE_PATH/$(basename "$artifact_path")"\n'
            '      offsite_checksum_path="$OFFSITE_USER@$OFFSITE_HOST:$OFFSITE_PATH/$(basename "$checksum_path")"\n'
            '      offsite_status="success"\n'
            '      offsite_message="scp copy completed"\n'
            "      ;;\n"
            "    *)\n"
            '      offsite_status="failed"\n'
            '      offsite_message="invalid offsite mode"\n'
            "      return 1\n"
            "      ;;\n"
            "  esac\n"
            "}\n"
            "\n"
            "run_preflight_checks() {\n"
            '  case "$ENGINE" in\n'
            "    postgresql)\n"
            '      if ! command -v pg_isready >/dev/null 2>&1; then\n'
            '        preflight_status="failed"\n'
            '        preflight_message="pg_isready not found"\n'
            "        return 1\n"
            "      fi\n"
            '      export PGHOST="$DB_HOST"\n'
            '      export PGPORT="$DB_PORT"\n'
            '      export PGUSER="$DB_USER"\n'
            '      export PGPASSWORD="$DB_PASSWORD"\n'
            '      if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then\n'
            '        preflight_status="failed"\n'
            '        preflight_message="postgresql preflight ping failed"\n'
            "        return 1\n"
            "      fi\n"
            '      if ! psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT 1" >/dev/null 2>&1; then\n'
            '        preflight_status="failed"\n'
            '        preflight_message="postgresql preflight query failed"\n'
            "        return 1\n"
            "      fi\n"
            "      ;;\n"
            "    mysql|mariadb)\n"
            '      export MYSQL_PWD="$DB_PASSWORD"\n'
            '      if command -v mysqladmin >/dev/null 2>&1; then\n'
            '        if ! mysqladmin --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" ping >/dev/null 2>&1; then\n'
            '          preflight_status="failed"\n'
            '          preflight_message="mysql preflight ping failed"\n'
            "          return 1\n"
            "        fi\n"
            "      fi\n"
            '      if command -v mysqlcheck >/dev/null 2>&1; then\n'
            '        if ! mysqlcheck --check --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" "$DB_NAME" >/dev/null 2>&1; then\n'
            '          preflight_status="failed"\n'
            '          preflight_message="mysqlcheck validation failed"\n'
            "          return 1\n"
            "        fi\n"
            '      elif ! mysql --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" --database="$DB_NAME" -e "SELECT 1" >/dev/null 2>&1; then\n'
            '        preflight_status="failed"\n'
            '        preflight_message="mysql fallback validation failed"\n'
            "        return 1\n"
            "      fi\n"
            "      ;;\n"
            "    mongodb)\n"
            '      if command -v mongosh >/dev/null 2>&1; then\n'
            '        MONGO_PREFLIGHT=(--host "$DB_HOST" --port "$DB_PORT" --quiet)\n'
            '        if [ -n "$DB_USER" ]; then MONGO_PREFLIGHT+=(--username "$DB_USER"); fi\n'
            '        if [ -n "$DB_PASSWORD" ]; then MONGO_PREFLIGHT+=(--password "$DB_PASSWORD"); fi\n'
            '        if [ -n "$AUTH_DB" ]; then MONGO_PREFLIGHT+=(--authenticationDatabase "$AUTH_DB"); fi\n'
            '        if ! mongosh "${MONGO_PREFLIGHT[@]}" --eval "db.adminCommand({ ping: 1 }).ok" >/dev/null 2>&1; then\n'
            '          preflight_status="failed"\n'
            '          preflight_message="mongodb preflight ping failed"\n'
            "          return 1\n"
            "        fi\n"
            "      fi\n"
            "      ;;\n"
            "    *)\n"
            "      ;;\n"
            "  esac\n"
            '  preflight_status="success"\n'
            '  preflight_message="source validation completed successfully"\n'
            "}\n"
            "\n"
            "finish_failure() {\n"
            '  rc="${1:-1}"\n'
            '  duration_seconds="$(( $(date +%s) - start_epoch ))"\n'
            '  finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"\n'
            '  status="failed"\n'
            '  if [ -z "$message" ]; then\n'
            '    message="backup failed"\n'
            "  fi\n"
            "  send_alert\n"
            "  write_status\n"
            '  [ -n "$tmp_dir" ] && rm -rf "$tmp_dir"\n'
            '  exit "$rc"\n'
            "}\n"
            "\n"
            "trap 'message=\"command failed: ${BASH_COMMAND}\"; finish_failure $?' ERR\n"
            "\n"
            'mkdir -p "$BACKUP_DIR"\n'
            'available_mb="$(df -Pm "$BACKUP_DIR" | awk \'NR==2 {print $4}\')"\n'
            'if [ -n "$available_mb" ] && [ "$available_mb" -lt "$VERIFY_FREE_MB" ]; then\n'
            '  message="insufficient free space in backup directory"\n'
            "  finish_failure 1\n"
            "fi\n"
            "\n"
            "run_preflight_checks\n"
            "\n"
            'tmp_dir="$BACKUP_DIR/.tmp-${JOB_NAME}-${timestamp}"\n'
            'mkdir -p "$tmp_dir"\n'
            "\n"
            'case "$ENGINE" in\n'
            "  postgresql)\n"
            '    export PGHOST="$DB_HOST"\n'
            '    export PGPORT="$DB_PORT"\n'
            '    export PGUSER="$DB_USER"\n'
            '    export PGPASSWORD="$DB_PASSWORD"\n'
            '    raw_backup="$tmp_dir/backup.raw"\n'
            '    pg_dump --format=custom --no-owner --no-privileges --dbname="$DB_NAME" --file="$raw_backup"\n'
            "    ;;\n"
            "  mysql|mariadb)\n"
            '    if command -v mysqldump >/dev/null 2>&1; then\n'
            '      DUMP_BIN="mysqldump"\n'
            '    elif command -v mariadb-dump >/dev/null 2>&1; then\n'
            '      DUMP_BIN="mariadb-dump"\n'
            "    else\n"
            '      message="mysqldump or mariadb-dump not found"\n'
            "      finish_failure 1\n"
            "    fi\n"
            '    export MYSQL_PWD="$DB_PASSWORD"\n'
            '    if [ "$COMPRESSION_ENABLED" = "1" ]; then\n'
            '      raw_backup="$tmp_dir/backup.raw"\n'
            '      "$DUMP_BIN" --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" --single-transaction --routines --events --triggers "$DB_NAME" | gzip -c > "$raw_backup"\n'
            "    else\n"
            '      raw_backup="$tmp_dir/backup.raw"\n'
            '      "$DUMP_BIN" --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" --single-transaction --routines --events --triggers "$DB_NAME" > "$raw_backup"\n'
            "    fi\n"
            "    ;;\n"
            "  mongodb)\n"
            '    raw_backup="$tmp_dir/backup.raw"\n'
            '    MONGO_ARGS=(--host "$DB_HOST" --port "$DB_PORT" --archive="$raw_backup")\n'
            '    if [ -n "$DB_NAME" ] && [ "$DB_NAME" != "all" ]; then\n'
            '      MONGO_ARGS+=(--db "$DB_NAME")\n'
            "    fi\n"
            '    if [ "$COMPRESSION_ENABLED" = "1" ]; then\n'
            '      MONGO_ARGS+=(--gzip)\n'
            "    fi\n"
            '    if [ -n "$DB_USER" ]; then\n'
            '      MONGO_ARGS+=(--username "$DB_USER")\n'
            "    fi\n"
            '    if [ -n "$DB_PASSWORD" ]; then\n'
            '      MONGO_ARGS+=(--password "$DB_PASSWORD")\n'
            "    fi\n"
            '    if [ -n "$AUTH_DB" ]; then\n'
            '      MONGO_ARGS+=(--authenticationDatabase "$AUTH_DB")\n'
            "    fi\n"
            '    mongodump "${MONGO_ARGS[@]}"\n'
            "    ;;\n"
            "  *)\n"
            '    message="unsupported backup engine"\n'
            "    finish_failure 1\n"
            "    ;;\n"
            "esac\n"
            "\n"
            'artifact_path="$BACKUP_DIR/${JOB_NAME}_${timestamp}${OUTPUT_EXTENSION}"\n'
            'encrypt_backup "$raw_backup"\n'
            'checksum_value="$(sha256sum "$artifact_path" | awk \'{print $1}\')"\n'
            'printf "%s  %s\\n" "$checksum_value" "$(basename "$artifact_path")" > "$artifact_path.sha256"\n'
            'checksum_path="$artifact_path.sha256"\n'
            'apply_retention "$BACKUP_DIR"\n'
            'copy_offsite\n'
            'duration_seconds="$(( $(date +%s) - start_epoch ))"\n'
            'finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"\n'
            'status="success"\n'
            'message="backup completed successfully"\n'
            "send_alert\n"
            "write_status\n"
            'rm -rf "$tmp_dir"\n'
            'echo "Backup finished: $artifact_path"\n'
        )

    @staticmethod
    def _random_secret(length: int = 24) -> str:
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(length))

    @staticmethod
    def _docker_compose_command() -> list[str]:
        docker = shutil.which("docker")
        if docker:
            probe = subprocess.run([docker, "compose", "version"], capture_output=True, text=True, check=False)
            if probe.returncode == 0:
                return [docker, "compose"]
        legacy = shutil.which("docker-compose")
        if legacy:
            return [legacy]
        return []

    @staticmethod
    def _docker_compose_run(compose_file: str, args: list[str], capture_output: bool = True, text: bool = True):
        cmd = SystemActions._docker_compose_command()
        if not cmd:
            return None
        return subprocess.run([*cmd, "-f", compose_file, *args], capture_output=capture_output, text=text, check=False)

    @staticmethod
    def _web_db_panel_service_order(compose_file: str) -> list[str]:
        services = []
        try:
            with open(compose_file, "r", encoding="utf-8") as f:
                content = f.read()
            for name in ("adminer", "pgadmin", "redisinsight", "dbpanel"):
                if re.search(rf"(?m)^  {re.escape(name)}:\s*$", content):
                    services.append(name)
        except Exception:
            return []
        return services

    @staticmethod
    def _web_db_panel_disable_restart_policy(compose_file: str):
        compose_result = SystemActions._docker_compose_run(compose_file, ["ps", "-aq"], capture_output=True, text=True)
        if compose_result is None or compose_result.returncode != 0:
            return
        container_ids = [line.strip() for line in (compose_result.stdout or "").splitlines() if line.strip()]
        if not container_ids:
            return
        subprocess.run(["docker", "update", "--restart=no", *container_ids], capture_output=True, text=True, check=False)

    @staticmethod
    def _web_db_panel_compose_content(
        panel_port: int,
        app_dir: str,
        enable_adminer: bool,
        enable_pgadmin: bool,
        enable_redisinsight: bool,
        pgadmin_email: str,
        pgadmin_password: str,
    ) -> str:
        services = []

        if enable_adminer:
            services.append(
                "  adminer:\n"
                "    image: adminer:standalone\n"
                "    extra_hosts:\n"
                "      - \"host.docker.internal:host-gateway\"\n"
            )

        if enable_pgadmin:
            services.append(
                "  pgadmin:\n"
                "    image: dpage/pgadmin4:latest\n"
                "    environment:\n"
                f"      PGADMIN_DEFAULT_EMAIL: {json.dumps(pgadmin_email)}\n"
                f"      PGADMIN_DEFAULT_PASSWORD: {json.dumps(pgadmin_password)}\n"
                "      PGADMIN_CONFIG_ENHANCED_COOKIE_PROTECTION: 'True'\n"
                "      PGADMIN_CONFIG_CONSOLE_LOG_LEVEL: '20'\n"
                "    volumes:\n"
                "      - ./pgadmin:/var/lib/pgadmin\n"
                "    extra_hosts:\n"
                "      - \"host.docker.internal:host-gateway\"\n"
            )

        if enable_redisinsight:
            services.append(
                "  redisinsight:\n"
                "    image: redis/redisinsight:latest\n"
                "    environment:\n"
                "      RI_PROXY_PATH: /redis\n"
                "    volumes:\n"
                "      - ./redisinsight:/data\n"
                "    extra_hosts:\n"
                "      - \"host.docker.internal:host-gateway\"\n"
            )

        nginx_service = (
            "  dbpanel:\n"
            "    image: nginx:alpine\n"
            "    ports:\n"
            f"      - \"127.0.0.1:{panel_port}:80\"\n"
            "    volumes:\n"
            "      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro\n"
            "      - ./dashboard:/usr/share/nginx/html:ro\n"
        )

        body = "\n".join([nginx_service, *services]).rstrip() + "\n"
        return (
            'name: "vps-tools-db-panel"\n'
            "services:\n"
            f"{body}"
        )

    @staticmethod
    def _web_db_panel_nginx_conf(enable_adminer: bool, enable_pgadmin: bool, enable_redisinsight: bool) -> str:
        sections = [
            "server {",
            "    listen 80;",
            "    server_name _;",
            "",
            "    root /usr/share/nginx/html;",
            "    index index.html;",
            "",
            "    location = / {",
            "        try_files /index.html =404;",
            "    }",
            "",
        ]

        if enable_adminer:
            sections.extend(
                [
                    "    location /adminer/ {",
                    "        proxy_set_header Host $host;",
                    "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                    "        proxy_set_header X-Forwarded-Proto $scheme;",
                    "        proxy_pass http://adminer:8080/;",
                    "        proxy_redirect off;",
                    "    }",
                    "",
                ]
            )

        if enable_pgadmin:
            sections.extend(
                [
                    "    location /pgadmin4/ {",
                    "        proxy_set_header X-Script-Name /pgadmin4;",
                    "        proxy_set_header X-Scheme $scheme;",
                    "        proxy_set_header Host $host;",
                    "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                    "        proxy_set_header X-Forwarded-Proto $scheme;",
                    "        proxy_pass http://pgadmin:80/;",
                    "        proxy_redirect off;",
                    "    }",
                    "",
                ]
            )

        if enable_redisinsight:
            sections.extend(
                [
                    "    location /redis/ {",
                    "        proxy_set_header Host $host;",
                    "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                    "        proxy_set_header X-Forwarded-Proto $scheme;",
                    "        proxy_pass http://redisinsight:5540;",
                    "        proxy_redirect off;",
                    "    }",
                    "",
                ]
            )

        sections.append("}")
        return "\n".join(sections) + "\n"

    @staticmethod
    def _web_db_panel_dashboard_html(
        panel_port: int,
        enable_adminer: bool,
        enable_pgadmin: bool,
        enable_redisinsight: bool,
        pgadmin_email: str,
        pgadmin_password: str,
    ) -> str:
        cards = []
        if enable_adminer:
            cards.append(
                """
        <a class="card" href="/adminer/">
          <strong>Adminer</strong>
          <span>MySQL, MariaDB e PostgreSQL</span>
          <small>Use o host <code>host.docker.internal</code></small>
        </a>""".rstrip()
            )
        if enable_pgadmin:
            cards.append(
                f"""
        <a class="card" href="/pgadmin4/">
          <strong>pgAdmin 4</strong>
          <span>Painel PostgreSQL</span>
          <small>Login inicial: <code>{pgadmin_email}</code> / <code>{pgadmin_password}</code></small>
        </a>""".rstrip()
            )
        if enable_redisinsight:
            cards.append(
                """
        <a class="card" href="/redis/">
          <strong>Redis Insight</strong>
          <span>Painel Redis</span>
          <small>Adicione a conexao usando <code>host.docker.internal</code></small>
        </a>""".rstrip()
            )

        cards_html = "\n".join(cards)
        return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Painel Web de Bancos</title>
  <style>
    :root {{
      --bg: #f5f1e8;
      --ink: #1b1d1f;
      --muted: #5d635f;
      --line: #d8cfbf;
      --card: #fffaf1;
      --accent: #0f766e;
      --accent-2: #d97706;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background:
        radial-gradient(circle at top left, rgba(217,119,6,.12), transparent 28%),
        radial-gradient(circle at bottom right, rgba(15,118,110,.14), transparent 32%),
        var(--bg);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 48px 24px 64px;
    }}
    .hero {{
      border: 1px solid var(--line);
      background: rgba(255,250,241,.88);
      backdrop-filter: blur(8px);
      padding: 28px;
      border-radius: 24px;
      box-shadow: 0 24px 80px rgba(27,29,31,.08);
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(2rem, 4vw, 3.5rem);
      line-height: 1;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      max-width: 800px;
      font-size: 1.02rem;
    }}
    .meta {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 18px;
    }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 14px;
      font-size: .92rem;
      background: white;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 18px;
      margin-top: 26px;
    }}
    .card {{
      display: block;
      text-decoration: none;
      color: inherit;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 22px;
      transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
      box-shadow: 0 14px 44px rgba(27,29,31,.06);
    }}
    .card:hover {{
      transform: translateY(-3px);
      border-color: rgba(15,118,110,.45);
      box-shadow: 0 22px 54px rgba(27,29,31,.10);
    }}
    .card strong {{
      display: block;
      font-size: 1.15rem;
      margin-bottom: 6px;
    }}
    .card span {{
      display: block;
      color: var(--muted);
      margin-bottom: 10px;
    }}
    .card small {{
      color: var(--accent);
    }}
    .notes {{
      margin-top: 24px;
      padding: 18px 20px;
      border-left: 4px solid var(--accent-2);
      background: rgba(255,255,255,.6);
      border-radius: 16px;
      color: var(--muted);
    }}
    code {{
      font-family: Consolas, "Courier New", monospace;
      font-size: .95em;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>Painel Web de Bancos</h1>
      <p>Interface central para abrir ferramentas web de administracao dos bancos instalados nesta maquina. Por seguranca, o painel fica publicado apenas em <code>127.0.0.1:{panel_port}</code> ate voce decidir expor via firewall ou Nginx.</p>
      <div class="meta">
        <div class="pill">URL local: <code>http://127.0.0.1:{panel_port}/</code></div>
        <div class="pill">Host para conexoes internas: <code>host.docker.internal</code></div>
      </div>
      <div class="grid">
{cards_html}
      </div>
      <div class="notes">
        Nao abra este painel para a internet inteira. Se precisar acesso remoto, prefira liberar a porta apenas para seu IP ou publicar atras de HTTPS com autenticacao.
      </div>
    </section>
  </div>
</body>
</html>
"""

    @staticmethod
    def web_db_panel_status(app_dir: str = "/opt/vps-tools-db-panel"):
        compose_file = os.path.join(app_dir, "compose.yml")
        installed = os.path.exists(compose_file)
        docker_active = False
        result = subprocess.run(["systemctl", "is-active", "docker"], capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip() == "active":
            docker_active = True

        running = False
        ps_output = ""
        if installed:
            compose_result = SystemActions._docker_compose_run(compose_file, ["ps"], capture_output=True, text=True)
            if compose_result is not None:
                ps_output = (compose_result.stdout or compose_result.stderr or "").strip()
                running = compose_result.returncode == 0 and "Up" in ps_output

        panel_port = ""
        try:
            if installed:
                with open(compose_file, "r", encoding="utf-8") as f:
                    for line in f:
                        match = re.search(r'127\.0\.0\.1:(\d+):80', line)
                        if match:
                            panel_port = match.group(1)
                            break
        except Exception:
            panel_port = ""

        return {
            "installed": installed,
            "docker_active": docker_active,
            "running": running,
            "compose_file": compose_file,
            "panel_port": panel_port,
            "ps_output": ps_output,
        }

    @staticmethod
    def _openssl_apr1_hash(password: str):
        result = subprocess.run(
            ["openssl", "passwd", "-apr1", password],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False, (result.stderr or result.stdout or "").strip()
        return True, result.stdout.strip()

    @staticmethod
    def write_environment_file(path: str, env_vars: dict[str, str], owner_user: str = ""):
        ok, msg = SystemActions._write_text_file(path, SystemActions._env_file_content(env_vars), mode=0o600)
        if not ok:
            return False, msg
        if owner_user and SystemActions._linux_user_exists(owner_user):
            result = subprocess.run(["chown", f"{owner_user}:{owner_user}", path], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    f"Falha ao ajustar dono de {path}.",
                    f"Failed to change owner of {path}.",
                )
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
                return False, SystemActions._txt("systemd nao suportado no Windows.", "systemd is not supported on Windows.")
            ok, msg = SystemActions._validate_service_name(service_name)
            if not ok:
                return False, msg
            if not exec_start.strip():
                return False, SystemActions._txt("ExecStart nao pode ser vazio.", "ExecStart cannot be empty.")
            if not working_dir.startswith("/"):
                return False, SystemActions._txt("WorkingDirectory deve ser absoluto.", "WorkingDirectory must be an absolute path.")

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

            update(15, SystemActions._txt("Gravando unit file", "Writing unit file"))
            ok, msg = SystemActions._write_text_file(unit_path, "\n".join(lines))
            if not ok:
                return False, msg

            update(45, SystemActions._txt("Recarregando systemd", "Reloading systemd"))
            for cmd in (
                ["systemctl", "daemon-reload"],
                ["systemctl", "enable", service_name],
                ["systemctl", "restart", service_name],
            ):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                        f"Falha ao executar: {' '.join(cmd)}",
                        f"Failed to execute: {' '.join(cmd)}",
                    )

            update(80, SystemActions._txt("Coletando status do servico", "Collecting service status"))
            status_result = subprocess.run(
                ["systemctl", "status", service_name, "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            update(100, SystemActions._txt("Servico criado", "Service created"))
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
                return False, SystemActions._txt(f"Acao systemd invalida: {action}", f"Invalid systemd action: {action}")

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

    @staticmethod
    def save_dr_profile(
        profile_name: str,
        service_name: str,
        environment_name: str,
        rpo_target: str,
        rto_target: str,
        incident_rpo: str = "",
        max_downtime: str = "",
        recovery_priority: str = "",
        service_criticality: str = "",
        operators: str = "",
        approvers: str = "",
        notes: str = "",
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            if os.name == "nt":
                return False, SystemActions._txt(
                    "Modulo de DR nao suportado no Windows.",
                    "DR module is not supported on Windows.",
                )
            ok, msg = SystemActions._validate_service_name(profile_name)
            if not ok:
                return False, msg
            if not service_name.strip():
                return False, SystemActions._txt("Nome do servico nao pode ser vazio.", "Service name cannot be empty.")
            if not environment_name.strip():
                return False, SystemActions._txt("Ambiente nao pode ser vazio.", "Environment cannot be empty.")
            if not rpo_target.strip() or not rto_target.strip():
                return False, SystemActions._txt("RPO e RTO nao podem ser vazios.", "RPO and RTO cannot be empty.")

            update(20, SystemActions._txt("Preparando diretorio de DR", "Preparing DR directory"))
            os.makedirs(SystemActions._dr_profiles_dir(), exist_ok=True)
            payload = {
                "profile_name": profile_name,
                "service_name": service_name.strip(),
                "environment_name": environment_name.strip(),
                "rpo_target": rpo_target.strip(),
                "rto_target": rto_target.strip(),
                "incident_rpo": incident_rpo.strip(),
                "max_downtime": max_downtime.strip(),
                "recovery_priority": recovery_priority.strip(),
                "service_criticality": service_criticality.strip(),
                "operators": operators.strip(),
                "approvers": approvers.strip(),
                "notes": notes.strip(),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            update(70, SystemActions._txt("Gravando perfil de RPO/RTO", "Writing RPO/RTO profile"))
            profile_file = os.path.join(SystemActions._dr_profiles_dir(), f"{profile_name}.json")
            ok, msg = SystemActions._write_json_file(profile_file, payload, mode=0o600)
            if not ok:
                return False, msg

            update(100, SystemActions._txt("Perfil de RPO/RTO salvo", "RPO/RTO profile saved"))
            payload["profile_file"] = profile_file
            return True, payload
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def list_dr_profiles():
        profiles = []
        try:
            base_dir = SystemActions._dr_profiles_dir()
            if not os.path.isdir(base_dir):
                return profiles
            for name in sorted(os.listdir(base_dir)):
                if not name.endswith(".json"):
                    continue
                data = SystemActions._read_json_file(os.path.join(base_dir, name), default={}) or {}
                if isinstance(data, dict):
                    profiles.append(data)
            return profiles
        except Exception:
            return profiles

    @staticmethod
    def get_dr_profile(profile_name: str):
        safe_name = re.sub(r"[^A-Za-z0-9_.@-]", "-", profile_name or "").strip("-")
        if not safe_name:
            return False, SystemActions._txt("Perfil de DR invalido.", "Invalid DR profile.")
        profile_file = os.path.join(SystemActions._dr_profiles_dir(), f"{safe_name}.json")
        if not os.path.exists(profile_file):
            return False, SystemActions._txt(
                f"Perfil de DR nao encontrado: {profile_name}",
                f"DR profile not found: {profile_name}",
            )
        payload = SystemActions._read_json_file(profile_file, default={}) or {}
        if not isinstance(payload, dict) or not payload:
            return False, SystemActions._txt(
                f"Perfil de DR invalido: {profile_name}",
                f"Invalid DR profile: {profile_name}",
            )
        payload["profile_file"] = profile_file
        return True, payload

    @staticmethod
    def assess_dr_profile(profile_name: str, job_name: str = ""):
        try:
            ok, profile = SystemActions.get_dr_profile(profile_name)
            if not ok:
                return False, profile
            jobs = SystemActions.list_db_backup_jobs()
            selected_job = None
            if job_name.strip():
                safe_job = re.sub(r"[^A-Za-z0-9_-]", "-", job_name or "").strip("-")
                selected_job = next((job for job in jobs if (job.get("job_name") or "") == safe_job), None)
                if not selected_job:
                    return False, SystemActions._txt(
                        f"Job de backup nao encontrado: {job_name}",
                        f"Backup job not found: {job_name}",
                    )
            elif jobs:
                selected_job = jobs[0]

            rpo_seconds = SystemActions._parse_duration_to_seconds(profile.get("rpo_target"))
            rto_seconds = SystemActions._parse_duration_to_seconds(profile.get("rto_target"))
            max_downtime_seconds = SystemActions._parse_duration_to_seconds(profile.get("max_downtime"))
            now_epoch = int(time.time())

            assessment = {
                "profile_name": profile.get("profile_name"),
                "service_name": profile.get("service_name"),
                "environment_name": profile.get("environment_name"),
                "rpo_target": profile.get("rpo_target"),
                "rpo_target_seconds": rpo_seconds,
                "rto_target": profile.get("rto_target"),
                "rto_target_seconds": rto_seconds,
                "max_downtime": profile.get("max_downtime"),
                "max_downtime_seconds": max_downtime_seconds,
                "job_name": selected_job.get("job_name") if selected_job else "",
                "backup_adherence": "unknown",
                "restore_adherence": "unknown",
                "overall_adherence": "unknown",
                "backup_age_seconds": None,
                "backup_age_human": "-",
                "backup_duration_seconds": None,
                "restore_duration_seconds": None,
                "last_backup_finished_at": "",
                "last_restore_finished_at": "",
                "incident_rpo": profile.get("incident_rpo", ""),
                "recovery_priority": profile.get("recovery_priority", ""),
                "service_criticality": profile.get("service_criticality", ""),
                "operators": profile.get("operators", ""),
                "approvers": profile.get("approvers", ""),
            }

            if selected_job:
                last_status = selected_job.get("last_status") or {}
                last_restore = selected_job.get("last_restore_test") or {}
                backup_finished_at = (last_status.get("finished_at") or "").strip()
                backup_finished_epoch = SystemActions._parse_iso_timestamp(backup_finished_at)
                backup_duration = last_status.get("duration_seconds")
                if isinstance(backup_duration, str) and backup_duration.isdigit():
                    backup_duration = int(backup_duration)
                restore_duration = last_restore.get("duration_seconds")
                if isinstance(restore_duration, str) and restore_duration.isdigit():
                    restore_duration = int(restore_duration)

                assessment["last_backup_finished_at"] = backup_finished_at
                assessment["last_restore_finished_at"] = (last_restore.get("finished_at") or "").strip()
                assessment["backup_duration_seconds"] = backup_duration
                assessment["restore_duration_seconds"] = restore_duration

                if backup_finished_epoch:
                    backup_age = max(0, now_epoch - backup_finished_epoch)
                    assessment["backup_age_seconds"] = backup_age
                    assessment["backup_age_human"] = SystemActions._format_duration_short(backup_age)

                backup_success = (last_status.get("status") or "") == "success"
                restore_success = (last_restore.get("status") or "") == "success"
                if rpo_seconds and backup_success and assessment["backup_age_seconds"] is not None:
                    assessment["backup_adherence"] = "met" if assessment["backup_age_seconds"] <= rpo_seconds else "breached"
                elif not rpo_seconds:
                    assessment["backup_adherence"] = "not-configured"
                else:
                    assessment["backup_adherence"] = "unknown"

                if rto_seconds and restore_success and isinstance(restore_duration, int):
                    assessment["restore_adherence"] = "met" if restore_duration <= rto_seconds else "breached"
                elif not rto_seconds:
                    assessment["restore_adherence"] = "not-configured"
                else:
                    assessment["restore_adherence"] = "unknown"

                if max_downtime_seconds and isinstance(restore_duration, int):
                    assessment["downtime_adherence"] = "met" if restore_duration <= max_downtime_seconds else "breached"
                else:
                    assessment["downtime_adherence"] = "not-configured" if not max_downtime_seconds else "unknown"

            statuses = {assessment["backup_adherence"], assessment["restore_adherence"], assessment.get("downtime_adherence")}
            if "breached" in statuses:
                assessment["overall_adherence"] = "breached"
            elif {"met", "not-configured", "unknown"} & statuses:
                if assessment["backup_adherence"] == "met" and assessment["restore_adherence"] in {"met", "not-configured"}:
                    assessment["overall_adherence"] = "met"
                else:
                    assessment["overall_adherence"] = "partial"

            return True, assessment
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def configure_db_backup_job(
        job_name: str,
        engine: str,
        db_name: str,
        db_host: str,
        db_port: int,
        db_user: str,
        db_password: str,
        auth_db: str,
        backup_dir: str,
        retention_count: int,
        on_calendar: str,
        verify_free_mb: int = 512,
        compression_enabled: bool = True,
        offsite_mode: str = "none",
        offsite_path: str = "",
        offsite_host: str = "",
        offsite_port: int = 22,
        offsite_user: str = "",
        offsite_ssh_key: str = "",
        offsite_known_hosts: str = "",
        offsite_timeout_sec: int = 30,
        alert_webhook_url: str = "",
        alert_on_success: bool = False,
        alert_on_failure: bool = True,
        alert_timeout_sec: int = 10,
        encryption_mode: str = "none",
        encryption_passphrase: str = "",
        encryption_cipher: str = "AES256",
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            if os.name == "nt":
                return False, SystemActions._txt(
                    "Modulo de backup DR nao suportado no Windows.",
                    "DR backup module is not supported on Windows.",
                )
            ok, msg = SystemActions._validate_service_name(job_name)
            if not ok:
                return False, msg
            engine_value = (engine or "").strip().lower()
            if engine_value not in {"postgresql", "mysql", "mariadb", "mongodb"}:
                return False, SystemActions._txt(
                    "Engine de backup invalido. Use PostgreSQL, MySQL, MariaDB ou MongoDB.",
                    "Invalid backup engine. Use PostgreSQL, MySQL, MariaDB or MongoDB.",
                )
            if not backup_dir.startswith("/"):
                return False, SystemActions._txt("Diretorio de backup deve ser absoluto.", "Backup directory must be absolute.")
            if not db_host.strip():
                return False, SystemActions._txt("Host do banco nao pode ser vazio.", "Database host cannot be empty.")
            if not isinstance(db_port, int) or not (1 <= db_port <= 65535):
                return False, SystemActions._txt("Porta do banco invalida.", "Invalid database port.")
            if retention_count < 1:
                return False, SystemActions._txt("Retencao deve ser maior que zero.", "Retention must be greater than zero.")
            if verify_free_mb < 128:
                return False, SystemActions._txt(
                    "Espaco livre minimo deve ser de pelo menos 128 MB.",
                    "Minimum free space must be at least 128 MB.",
                )
            offsite_mode_value = (offsite_mode or "none").strip().lower()
            if offsite_mode_value not in {"none", "local_copy", "scp"}:
                return False, SystemActions._txt(
                    "Modo offsite invalido. Use none, local_copy ou scp.",
                    "Invalid offsite mode. Use none, local_copy or scp.",
                )
            if offsite_mode_value == "local_copy" and not offsite_path.startswith("/"):
                return False, SystemActions._txt(
                    "Destino local secundario deve ser um diretorio absoluto.",
                    "Secondary local destination must be an absolute directory.",
                )
            if offsite_mode_value == "scp":
                if not offsite_path.startswith("/"):
                    return False, SystemActions._txt(
                        "Destino remoto SCP deve ser um diretorio absoluto.",
                        "SCP remote destination must be an absolute directory.",
                    )
                if not offsite_host.strip() or not offsite_user.strip():
                    return False, SystemActions._txt(
                        "Host e usuario do destino SCP nao podem ser vazios.",
                        "SCP destination host and user cannot be empty.",
                    )
                if not isinstance(offsite_port, int) or not (1 <= offsite_port <= 65535):
                    return False, SystemActions._txt("Porta SCP invalida.", "Invalid SCP port.")
            if offsite_ssh_key and not offsite_ssh_key.startswith("/"):
                return False, SystemActions._txt(
                    "Caminho da chave SSH do offsite deve ser absoluto.",
                    "Offsite SSH key path must be absolute.",
                )
            if offsite_known_hosts and not offsite_known_hosts.startswith("/"):
                return False, SystemActions._txt(
                    "Caminho do known_hosts do offsite deve ser absoluto.",
                    "Offsite known_hosts path must be absolute.",
                )
            if offsite_timeout_sec < 5:
                return False, SystemActions._txt(
                    "Timeout do offsite deve ser de pelo menos 5 segundos.",
                    "Offsite timeout must be at least 5 seconds.",
                )
            if alert_timeout_sec < 3:
                return False, SystemActions._txt(
                    "Timeout do alerta deve ser de pelo menos 3 segundos.",
                    "Alert timeout must be at least 3 seconds.",
                )
            encryption_mode_value = (encryption_mode or "none").strip().lower()
            if encryption_mode_value not in {"none", "gpg_symmetric"}:
                return False, SystemActions._txt(
                    "Modo de criptografia invalido. Use none ou gpg_symmetric.",
                    "Invalid encryption mode. Use none or gpg_symmetric.",
                )
            if encryption_mode_value != "none":
                if not encryption_passphrase:
                    return False, SystemActions._txt(
                        "Senha da criptografia nao pode ser vazia.",
                        "Encryption passphrase cannot be empty.",
                    )
                if not shutil.which("gpg"):
                    return False, SystemActions._txt(
                        "gpg nao encontrado. Instale o pacote gnupg antes de ativar criptografia.",
                        "gpg not found. Install the gnupg package before enabling encryption.",
                    )
                if not encryption_cipher.strip():
                    return False, SystemActions._txt(
                        "Algoritmo da criptografia nao pode ser vazio.",
                        "Encryption cipher cannot be empty.",
                    )
            if not on_calendar.strip():
                return False, SystemActions._txt("Agenda OnCalendar nao pode ser vazia.", "OnCalendar schedule cannot be empty.")

            paths = SystemActions._dr_backup_job_paths(job_name)
            os.makedirs(paths["job_dir"], exist_ok=True)
            os.makedirs(backup_dir, exist_ok=True)

            update(20, SystemActions._txt("Preparando arquivos do job de backup", "Preparing backup job files"))
            extension_map = {
                "postgresql": ".dump",
                "mysql": ".sql.gz" if compression_enabled else ".sql",
                "mariadb": ".sql.gz" if compression_enabled else ".sql",
                "mongodb": ".archive.gz" if compression_enabled else ".archive",
            }
            output_extension = extension_map[engine_value]
            if encryption_mode_value != "none":
                output_extension = f"{output_extension}.gpg"
            env_vars = {
                "STATUS_FILE": paths["status_file"],
                "BACKUP_DIR": backup_dir,
                "RETENTION_COUNT": str(retention_count),
                "VERIFY_FREE_MB": str(verify_free_mb),
                "DB_HOST": db_host.strip(),
                "DB_PORT": str(db_port),
                "DB_NAME": db_name.strip(),
                "DB_USER": db_user.strip(),
                "DB_PASSWORD": db_password,
                "AUTH_DB": auth_db.strip(),
                "OFFSITE_MODE": offsite_mode_value,
                "OFFSITE_PATH": offsite_path.strip(),
                "OFFSITE_HOST": offsite_host.strip(),
                "OFFSITE_PORT": str(offsite_port),
                "OFFSITE_USER": offsite_user.strip(),
                "OFFSITE_SSH_KEY": offsite_ssh_key.strip(),
                "OFFSITE_KNOWN_HOSTS": offsite_known_hosts.strip(),
                "OFFSITE_TIMEOUT_SEC": str(offsite_timeout_sec),
                "ALERT_WEBHOOK_URL": alert_webhook_url.strip(),
                "ALERT_ON_SUCCESS": "1" if alert_on_success else "0",
                "ALERT_ON_FAILURE": "1" if alert_on_failure else "0",
                "ALERT_TIMEOUT_SEC": str(alert_timeout_sec),
                "ENCRYPTION_MODE": encryption_mode_value,
                "ENCRYPTION_PASSPHRASE": encryption_passphrase,
                "ENCRYPTION_CIPHER": encryption_cipher.strip(),
            }
            ok, msg = SystemActions.write_environment_file(paths["env_file"], env_vars)
            if not ok:
                return False, msg

            ok, msg = SystemActions._write_text_file(
                paths["script_file"],
                SystemActions._db_backup_script_content(paths["safe_job"], engine_value, output_extension, compression_enabled),
                mode=0o750,
            )
            if not ok:
                return False, msg

            config_payload = {
                "job_name": paths["safe_job"],
                "engine": engine_value,
                "db_name": db_name.strip(),
                "db_host": db_host.strip(),
                "db_port": db_port,
                "db_user": db_user.strip(),
                "auth_db": auth_db.strip(),
                "backup_dir": backup_dir,
                "retention_count": retention_count,
                "on_calendar": on_calendar.strip(),
                "verify_free_mb": verify_free_mb,
                "compression_enabled": compression_enabled,
                "offsite_mode": offsite_mode_value,
                "offsite_path": offsite_path.strip(),
                "offsite_host": offsite_host.strip(),
                "offsite_port": offsite_port,
                "offsite_user": offsite_user.strip(),
                "offsite_ssh_key": offsite_ssh_key.strip(),
                "offsite_known_hosts": offsite_known_hosts.strip(),
                "offsite_timeout_sec": offsite_timeout_sec,
                "alert_webhook_url": alert_webhook_url.strip(),
                "alert_on_success": alert_on_success,
                "alert_on_failure": alert_on_failure,
                "alert_timeout_sec": alert_timeout_sec,
                "encryption_mode": encryption_mode_value,
                "encryption_cipher": encryption_cipher.strip(),
                "service_name": paths["service_name"],
                "timer_name": paths["timer_name"],
                "script_file": paths["script_file"],
                "status_file": paths["status_file"],
                "config_file": paths["config_file"],
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            ok, msg = SystemActions._write_json_file(paths["config_file"], config_payload, mode=0o600)
            if not ok:
                return False, msg

            update(55, SystemActions._txt("Gravando unit files do systemd", "Writing systemd unit files"))
            service_content = (
                "[Unit]\n"
                f"Description=VPS Tools DB backup job {paths['safe_job']}\n"
                "After=network.target\n"
                "\n"
                "[Service]\n"
                "Type=oneshot\n"
                f"EnvironmentFile={paths['env_file']}\n"
                f"ExecStart={paths['script_file']}\n"
                f"WorkingDirectory={paths['job_dir']}\n"
                "User=root\n"
                "Group=root\n"
                "\n"
            )
            timer_content = (
                "[Unit]\n"
                f"Description=Schedule VPS Tools DB backup job {paths['safe_job']}\n"
                "\n"
                "[Timer]\n"
                f"OnCalendar={on_calendar.strip()}\n"
                "Persistent=true\n"
                "RandomizedDelaySec=300\n"
                f"Unit={paths['service_name']}.service\n"
                "\n"
                "[Install]\n"
                "WantedBy=timers.target\n"
                "\n"
            )
            ok, msg = SystemActions._write_text_file(paths["service_unit"], service_content)
            if not ok:
                return False, msg
            ok, msg = SystemActions._write_text_file(paths["timer_unit"], timer_content)
            if not ok:
                return False, msg

            update(80, SystemActions._txt("Recarregando e habilitando o timer", "Reloading and enabling the timer"))
            for cmd in (
                ["systemctl", "daemon-reload"],
                ["systemctl", "enable", "--now", paths["timer_name"]],
            ):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                        f"Falha ao executar: {' '.join(cmd)}",
                        f"Failed to execute: {' '.join(cmd)}",
                    )

            timer_status = subprocess.run(["systemctl", "status", paths["timer_name"], "--no-pager"], capture_output=True, text=True, check=False)
            update(100, SystemActions._txt("Job de backup configurado", "Backup job configured"))
            config_payload["timer_status"] = (timer_status.stdout or timer_status.stderr or "").strip()
            return True, config_payload
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def list_db_backup_jobs():
        jobs = []
        try:
            base_dir = SystemActions._dr_jobs_dir()
            if not os.path.isdir(base_dir):
                return jobs
            for name in sorted(os.listdir(base_dir)):
                config_file = os.path.join(base_dir, name, "job.json")
                config = SystemActions._read_json_file(config_file, default={}) or {}
                if not isinstance(config, dict) or not config:
                    continue
                service_name = config.get("service_name") or f"vps-tools-db-backup-{name}"
                timer_name = config.get("timer_name") or f"{service_name}.timer"
                timer_active = subprocess.run(["systemctl", "is-active", timer_name], capture_output=True, text=True, check=False)
                timer_enabled = subprocess.run(["systemctl", "is-enabled", timer_name], capture_output=True, text=True, check=False)
                last_status = SystemActions._read_json_file(os.path.join(base_dir, name, "last_status.json"), default={}) or {}
                last_restore_test = SystemActions._read_json_file(os.path.join(base_dir, name, "last_restore_test.json"), default={}) or {}
                config["timer_active"] = (timer_active.stdout or "").strip()
                config["timer_enabled"] = (timer_enabled.stdout or "").strip()
                config["last_status"] = last_status if isinstance(last_status, dict) else {}
                config["last_restore_test"] = last_restore_test if isinstance(last_restore_test, dict) else {}
                jobs.append(config)
            return jobs
        except Exception:
            return jobs

    @staticmethod
    def run_db_backup_job_now(job_name: str):
        try:
            paths = SystemActions._dr_backup_job_paths(job_name)
            if not os.path.exists(paths["config_file"]):
                return False, SystemActions._txt(
                    f"Job de backup nao encontrado: {job_name}",
                    f"Backup job not found: {job_name}",
                )
            result = subprocess.run(["systemctl", "start", f"{paths['service_name']}.service"], capture_output=True, text=True, check=False)
            service_status = subprocess.run(["systemctl", "status", f"{paths['service_name']}.service", "--no-pager"], capture_output=True, text=True, check=False)
            logs = subprocess.run(["journalctl", "-u", f"{paths['service_name']}.service", "-n", "80", "--no-pager"], capture_output=True, text=True, check=False)
            last_status = SystemActions._read_json_file(paths["status_file"], default={}) or {}
            ok = result.returncode == 0
            return ok, {
                "service_status": (service_status.stdout or service_status.stderr or "").strip(),
                "logs": (logs.stdout or logs.stderr or "").strip(),
                "last_status": last_status if isinstance(last_status, dict) else {},
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def db_backup_job_status(job_name: str):
        try:
            paths = SystemActions._dr_backup_job_paths(job_name)
            if not os.path.exists(paths["config_file"]):
                return False, SystemActions._txt(
                    f"Job de backup nao encontrado: {job_name}",
                    f"Backup job not found: {job_name}",
                )
            config = SystemActions._read_json_file(paths["config_file"], default={}) or {}
            timer_status = subprocess.run(["systemctl", "status", paths["timer_name"], "--no-pager"], capture_output=True, text=True, check=False)
            service_status = subprocess.run(["systemctl", "status", f"{paths['service_name']}.service", "--no-pager"], capture_output=True, text=True, check=False)
            last_status = SystemActions._read_json_file(paths["status_file"], default={}) or {}
            last_restore_test = SystemActions._read_json_file(paths["restore_status_file"], default={}) or {}
            return True, {
                "config": config if isinstance(config, dict) else {},
                "timer_status": (timer_status.stdout or timer_status.stderr or "").strip(),
                "service_status": (service_status.stdout or service_status.stderr or "").strip(),
                "last_status": last_status if isinstance(last_status, dict) else {},
                "last_restore_test": last_restore_test if isinstance(last_restore_test, dict) else {},
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def configure_dr_monitoring_job(
        monitor_name: str,
        on_calendar: str,
        service_names,
        domains,
        backup_jobs,
        profile_name: str = "",
        check_offsite_job: str = "",
        disk_path: str = "/",
        min_disk_mb: int = 1024,
        min_ram_mb: int = 256,
        max_cpu_percent: int = 90,
        ssl_warn_days: int = 14,
        alert_webhook_url: str = "",
        alert_on_success: bool = False,
        alert_on_failure: bool = True,
        alert_timeout_sec: int = 10,
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            if os.name == "nt":
                return False, SystemActions._txt(
                    "Monitoramento DR nao suportado no Windows.",
                    "DR monitoring is not supported on Windows.",
                )
            ok, msg = SystemActions._validate_service_name(monitor_name)
            if not ok:
                return False, msg
            if not on_calendar.strip():
                return False, SystemActions._txt("Agenda OnCalendar nao pode ser vazia.", "OnCalendar schedule cannot be empty.")
            if not disk_path.startswith("/"):
                return False, SystemActions._txt("Caminho de disco deve ser absoluto.", "Disk path must be absolute.")

            clean_services = [item.strip() for item in (service_names or []) if str(item).strip()]
            clean_domains = [item.strip() for item in (domains or []) if str(item).strip()]
            clean_jobs = [re.sub(r"[^A-Za-z0-9_-]", "-", item or "").strip("-") for item in (backup_jobs or []) if str(item).strip()]
            safe_profile_name = re.sub(r"[^A-Za-z0-9_.@-]", "-", profile_name or "").strip("-")
            safe_offsite_job = re.sub(r"[^A-Za-z0-9_-]", "-", check_offsite_job or "").strip("-")

            paths = SystemActions._dr_monitor_paths(monitor_name)
            os.makedirs(paths["monitor_dir"], exist_ok=True)

            config_payload = {
                "monitor_name": paths["safe_name"],
                "on_calendar": on_calendar.strip(),
                "service_names": clean_services,
                "domains": clean_domains,
                "backup_jobs": clean_jobs,
                "profile_name": safe_profile_name,
                "check_offsite_job": safe_offsite_job,
                "disk_path": disk_path,
                "min_disk_mb": int(min_disk_mb),
                "min_ram_mb": int(min_ram_mb),
                "max_cpu_percent": int(max_cpu_percent),
                "ssl_warn_days": int(ssl_warn_days),
                "alert_webhook_url": alert_webhook_url.strip(),
                "alert_on_success": bool(alert_on_success),
                "alert_on_failure": bool(alert_on_failure),
                "alert_timeout_sec": int(alert_timeout_sec),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            update(20, SystemActions._txt("Gravando configuracao do monitor DR", "Writing DR monitor configuration"))
            ok, msg = SystemActions._write_json_file(paths["config_file"], config_payload, mode=0o600)
            if not ok:
                return False, msg

            update(45, SystemActions._txt("Gravando runner do monitor DR", "Writing DR monitor runner"))
            script_content = SystemActions._dr_monitor_script_content(
                config_file=paths["config_file"],
                repo_dir=SystemActions._repo_root_dir(),
                python_bin=SystemActions._preferred_python_binary(),
            )
            ok, msg = SystemActions._write_text_file(paths["script_file"], script_content, mode=0o750)
            if not ok:
                return False, msg

            service_content = (
                "[Unit]\n"
                f"Description=VPS Tools DR monitor {paths['safe_name']}\n"
                "After=network.target\n"
                "\n"
                "[Service]\n"
                "Type=oneshot\n"
                f"ExecStart={paths['script_file']}\n"
                f"WorkingDirectory={paths['monitor_dir']}\n"
                "User=root\n"
                "Group=root\n"
                "\n"
            )
            timer_content = (
                "[Unit]\n"
                f"Description=Schedule VPS Tools DR monitor {paths['safe_name']}\n"
                "\n"
                "[Timer]\n"
                f"OnCalendar={on_calendar.strip()}\n"
                "Persistent=true\n"
                "RandomizedDelaySec=120\n"
                f"Unit={paths['service_name']}.service\n"
                "\n"
                "[Install]\n"
                "WantedBy=timers.target\n"
                "\n"
            )

            update(65, SystemActions._txt("Gravando unit files do monitor", "Writing monitor unit files"))
            ok, msg = SystemActions._write_text_file(paths["service_unit"], service_content)
            if not ok:
                return False, msg
            ok, msg = SystemActions._write_text_file(paths["timer_unit"], timer_content)
            if not ok:
                return False, msg

            update(85, SystemActions._txt("Habilitando timer do monitor", "Enabling monitor timer"))
            for cmd in (
                ["systemctl", "daemon-reload"],
                ["systemctl", "enable", "--now", paths["timer_name"]],
            ):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                        f"Falha ao executar: {' '.join(cmd)}",
                        f"Failed to execute: {' '.join(cmd)}",
                    )

            timer_status = subprocess.run(["systemctl", "status", paths["timer_name"], "--no-pager"], capture_output=True, text=True, check=False)
            update(100, SystemActions._txt("Monitor DR configurado", "DR monitor configured"))
            config_payload["timer_name"] = paths["timer_name"]
            config_payload["service_name"] = paths["service_name"]
            config_payload["timer_status"] = (timer_status.stdout or timer_status.stderr or "").strip()
            return True, config_payload
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def run_dr_monitoring_check(config_path: str = "", monitor_name: str = ""):
        try:
            if os.name == "nt":
                return False, SystemActions._txt(
                    "Monitoramento DR nao suportado no Windows.",
                    "DR monitoring is not supported on Windows.",
                )
            if config_path:
                config = SystemActions._read_json_file(config_path, default={}) or {}
                paths = SystemActions._dr_monitor_paths((config.get("monitor_name") or monitor_name or "default"))
            else:
                paths = SystemActions._dr_monitor_paths(monitor_name or "default")
                config = SystemActions._read_json_file(paths["config_file"], default={}) or {}
            if not isinstance(config, dict) or not config:
                return False, SystemActions._txt("Configuracao do monitor DR nao encontrada.", "DR monitor configuration not found.")

            service_results = []
            service_failures = []
            for name in config.get("service_names") or []:
                result = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, check=False)
                state = (result.stdout or result.stderr or "").strip() or "unknown"
                service_results.append({"service": name, "status": state})
                if state != "active":
                    service_failures.append(name)

            domain_results = []
            domain_failures = []
            for domain in config.get("domains") or []:
                try:
                    answers = socket.getaddrinfo(domain, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
                    ips = sorted({item[4][0] for item in answers if item and item[4]})
                except Exception:
                    ips = []
                domain_results.append({"domain": domain, "resolved_ips": ips})
                if not ips:
                    domain_failures.append(domain)

            ssl_results = []
            ssl_warnings = []
            warn_seconds = int(config.get("ssl_warn_days") or 14) * 86400
            for domain in config.get("domains") or []:
                cert_path = os.path.join("/etc/letsencrypt/live", domain, "fullchain.pem")
                entry = {"domain": domain, "status": "missing", "days_remaining": None, "cert_path": cert_path}
                if os.path.exists(cert_path):
                    try:
                        decoded = ssl._ssl._test_decode_cert(cert_path)
                        not_after = decoded.get("notAfter", "")
                        expires_epoch = calendar.timegm(time.strptime(not_after, "%b %d %H:%M:%S %Y %Z"))
                        remaining = max(0, int(expires_epoch - time.time()))
                        entry["days_remaining"] = remaining // 86400
                        entry["status"] = "warning" if remaining <= warn_seconds else "healthy"
                        if entry["status"] == "warning":
                            ssl_warnings.append(domain)
                    except Exception:
                        entry["status"] = "failed"
                        ssl_warnings.append(domain)
                else:
                    ssl_warnings.append(domain)
                ssl_results.append(entry)

            disk_path = config.get("disk_path") or "/"
            disk_usage = shutil.disk_usage(disk_path)
            disk_free_mb = int(disk_usage.free // (1024 * 1024))
            disk_ok = disk_free_mb >= int(config.get("min_disk_mb") or 1024)

            ram = psutil.virtual_memory()
            ram_available_mb = int(ram.available // (1024 * 1024))
            ram_ok = ram_available_mb >= int(config.get("min_ram_mb") or 256)

            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_ok = float(cpu_percent) <= float(config.get("max_cpu_percent") or 90)

            backup_results = []
            backup_failures = []
            for job_name in config.get("backup_jobs") or []:
                paths_job = SystemActions._dr_backup_job_paths(job_name)
                last_status = SystemActions._read_json_file(paths_job["status_file"], default={}) or {}
                last_restore = SystemActions._read_json_file(paths_job["restore_status_file"], default={}) or {}
                job_status = (last_status.get("status") or "not-run").strip()
                restore_status = (last_restore.get("status") or "not-tested").strip()
                backup_results.append(
                    {
                        "job_name": job_name,
                        "last_status": job_status,
                        "last_finished_at": last_status.get("finished_at", ""),
                        "last_restore_status": restore_status,
                        "offsite_status": last_status.get("offsite_status", ""),
                    }
                )
                if job_status != "success":
                    backup_failures.append(job_name)

            offsite_result = {"job_name": config.get("check_offsite_job") or "", "status": "disabled", "message": "offsite check not configured"}
            check_offsite_job = (config.get("check_offsite_job") or "").strip()
            if check_offsite_job:
                job_paths = SystemActions._dr_backup_job_paths(check_offsite_job)
                job_config = SystemActions._read_json_file(job_paths["config_file"], default={}) or {}
                mode = (job_config.get("offsite_mode") or "none").strip().lower()
                offsite_result["mode"] = mode
                if mode == "local_copy":
                    target_dir = (job_config.get("offsite_path") or "").strip()
                    probe_path = os.path.join(target_dir, f".dr-write-test-{int(time.time())}")
                    try:
                        os.makedirs(target_dir, exist_ok=True)
                        with open(probe_path, "w", encoding="utf-8") as f:
                            f.write("ok\n")
                        os.remove(probe_path)
                        offsite_result.update({"status": "success", "message": "secondary local destination is writable", "path": target_dir})
                    except Exception as exc:
                        offsite_result.update({"status": "failed", "message": str(exc), "path": target_dir})
                elif mode == "scp":
                    ssh_cmd = [
                        "ssh",
                        "-p",
                        str(job_config.get("offsite_port") or 22),
                        "-o",
                        "BatchMode=yes",
                        "-o",
                        f"ConnectTimeout={int(job_config.get('offsite_timeout_sec') or 30)}",
                    ]
                    if job_config.get("offsite_ssh_key"):
                        ssh_cmd.extend(["-i", job_config["offsite_ssh_key"]])
                    if job_config.get("offsite_known_hosts"):
                        ssh_cmd.extend(["-o", f"UserKnownHostsFile={job_config['offsite_known_hosts']}", "-o", "StrictHostKeyChecking=yes"])
                    else:
                        ssh_cmd.extend(["-o", "StrictHostKeyChecking=accept-new"])
                    ssh_cmd.append(f"{job_config.get('offsite_user')}@{job_config.get('offsite_host')}")
                    ssh_cmd.append("true")
                    result = subprocess.run(ssh_cmd, capture_output=True, text=True, check=False)
                    if result.returncode == 0:
                        offsite_result.update({"status": "success", "message": "scp destination is reachable"})
                    else:
                        offsite_result.update({"status": "failed", "message": (result.stderr or result.stdout or "").strip() or "scp connectivity failed"})
                else:
                    offsite_result.update({"status": "disabled", "message": "selected backup job has no offsite destination"})

            profile_assessment = {}
            profile_name = (config.get("profile_name") or "").strip()
            if profile_name:
                primary_job = (config.get("backup_jobs") or [""])[0]
                ok, assessment = SystemActions.assess_dr_profile(profile_name, primary_job)
                if ok:
                    profile_assessment = assessment
                else:
                    profile_assessment = {"status": "failed", "message": assessment}

            overall_status = "healthy"
            failures = []
            warnings = []
            if service_failures:
                failures.append(SystemActions._txt("servicos inativos", "inactive services"))
            if domain_failures:
                failures.append(SystemActions._txt("dominios sem resolucao DNS", "domains without DNS resolution"))
            if not disk_ok:
                failures.append(SystemActions._txt("disco abaixo do minimo", "disk below threshold"))
            if not ram_ok:
                failures.append(SystemActions._txt("RAM abaixo do minimo", "RAM below threshold"))
            if not cpu_ok:
                warnings.append(SystemActions._txt("CPU acima do limite", "CPU above threshold"))
            if backup_failures:
                failures.append(SystemActions._txt("job(s) de backup com falha", "backup job(s) failed"))
            if offsite_result.get("status") == "failed":
                failures.append(SystemActions._txt("conectividade offsite com falha", "offsite connectivity failed"))
            if ssl_warnings:
                warnings.append(SystemActions._txt("SSL ausente/proximo do vencimento", "SSL missing/near expiry"))
            if profile_assessment and profile_assessment.get("overall_adherence") == "breached":
                failures.append(SystemActions._txt("RPO/RTO violado", "RPO/RTO breached"))
            elif profile_assessment and profile_assessment.get("overall_adherence") == "partial":
                warnings.append(SystemActions._txt("aderencia parcial ao RPO/RTO", "partial RPO/RTO adherence"))

            if failures:
                overall_status = "failed"
            elif warnings:
                overall_status = "warning"

            report = {
                "monitor_name": config.get("monitor_name") or paths["safe_name"],
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "overall_status": overall_status,
                "service_results": service_results,
                "domain_results": domain_results,
                "ssl_results": ssl_results,
                "disk": {
                    "path": disk_path,
                    "free_mb": disk_free_mb,
                    "min_free_mb": int(config.get("min_disk_mb") or 1024),
                    "status": "healthy" if disk_ok else "failed",
                },
                "ram": {
                    "available_mb": ram_available_mb,
                    "min_available_mb": int(config.get("min_ram_mb") or 256),
                    "status": "healthy" if ram_ok else "failed",
                },
                "cpu": {
                    "percent": cpu_percent,
                    "max_percent": float(config.get("max_cpu_percent") or 90),
                    "status": "healthy" if cpu_ok else "warning",
                },
                "backup_results": backup_results,
                "offsite_result": offsite_result,
                "profile_assessment": profile_assessment,
                "failures": failures,
                "warnings": warnings,
            }
            SystemActions._write_json_file(paths["report_file"], report, mode=0o600)

            webhook = (config.get("alert_webhook_url") or "").strip()
            should_alert = False
            if webhook and overall_status == "failed" and config.get("alert_on_failure", True):
                should_alert = True
            if webhook and overall_status == "healthy" and config.get("alert_on_success"):
                should_alert = True
            if webhook and overall_status == "warning" and config.get("alert_on_failure", True):
                should_alert = True
            if should_alert:
                try:
                    requests.post(webhook, json=report, timeout=int(config.get("alert_timeout_sec") or 10))
                    report["alert_status"] = "sent"
                except Exception as exc:
                    report["alert_status"] = "failed"
                    report["alert_message"] = str(exc)
                    SystemActions._write_json_file(paths["report_file"], report, mode=0o600)
            else:
                report["alert_status"] = "disabled"
            return True, report
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def run_dr_monitor_job_now(monitor_name: str = "default"):
        try:
            paths = SystemActions._dr_monitor_paths(monitor_name)
            if not os.path.exists(paths["config_file"]):
                return False, SystemActions._txt(
                    f"Monitor DR nao encontrado: {monitor_name}",
                    f"DR monitor not found: {monitor_name}",
                )
            result = subprocess.run(["systemctl", "start", f"{paths['service_name']}.service"], capture_output=True, text=True, check=False)
            service_status = subprocess.run(["systemctl", "status", f"{paths['service_name']}.service", "--no-pager"], capture_output=True, text=True, check=False)
            logs = subprocess.run(["journalctl", "-u", f"{paths['service_name']}.service", "-n", "80", "--no-pager"], capture_output=True, text=True, check=False)
            report = SystemActions._read_json_file(paths["report_file"], default={}) or {}
            return result.returncode == 0, {
                "service_status": (service_status.stdout or service_status.stderr or "").strip(),
                "logs": (logs.stdout or logs.stderr or "").strip(),
                "report": report if isinstance(report, dict) else {},
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def dr_monitor_status(monitor_name: str = "default"):
        try:
            paths = SystemActions._dr_monitor_paths(monitor_name)
            if not os.path.exists(paths["config_file"]):
                return False, SystemActions._txt(
                    f"Monitor DR nao encontrado: {monitor_name}",
                    f"DR monitor not found: {monitor_name}",
                )
            config = SystemActions._read_json_file(paths["config_file"], default={}) or {}
            timer_status = subprocess.run(["systemctl", "status", paths["timer_name"], "--no-pager"], capture_output=True, text=True, check=False)
            service_status = subprocess.run(["systemctl", "status", f"{paths['service_name']}.service", "--no-pager"], capture_output=True, text=True, check=False)
            report = SystemActions._read_json_file(paths["report_file"], default={}) or {}
            return True, {
                "config": config if isinstance(config, dict) else {},
                "timer_status": (timer_status.stdout or timer_status.stderr or "").strip(),
                "service_status": (service_status.stdout or service_status.stderr or "").strip(),
                "report": report if isinstance(report, dict) else {},
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _default_dr_runbook_templates():
        return [
            {
                "runbook_name": "promover-replica",
                "category": "semi",
                "title": "Promover replica",
                "summary": "Promove uma replica para primaria com validacao previa e rollback planejado.",
                "impact": "Pode alterar o papel da base e interromper sincronizacao existente.",
                "prechecks": [
                    "Confirmar atraso da replica",
                    "Confirmar saude da replica",
                    "Confirmar aplicacao parada ou em modo manutencao",
                ],
                "rollback_plan": "Reverter trafego para a primaria anterior e reconfigurar replicacao.",
                "requires_double_confirmation": True,
                "requires_command": True,
            },
            {
                "runbook_name": "trocar-dns",
                "category": "semi",
                "title": "Trocar DNS",
                "summary": "Aplica a troca de DNS com validacao previa e plano de rollback.",
                "impact": "Pode redirecionar trafego de producao para novo destino.",
                "prechecks": [
                    "Confirmar TTL atual",
                    "Confirmar novo IP/hostname",
                    "Confirmar saude do destino",
                ],
                "rollback_plan": "Restaurar o registro DNS anterior e monitorar propagacao.",
                "requires_double_confirmation": True,
                "requires_command": True,
            },
            {
                "runbook_name": "restaurar-maquina-reserva",
                "category": "semi",
                "title": "Restaurar para maquina reserva",
                "summary": "Executa a restauracao do backup na maquina reserva com checklist guiado.",
                "impact": "Pode consumir recursos na reserva e alterar inventario de standby.",
                "prechecks": [
                    "Confirmar conectividade com a reserva",
                    "Confirmar espaco em disco",
                    "Confirmar artefato de backup validado",
                ],
                "rollback_plan": "Descartar restauracao incompleta e retornar a reserva ao estado anterior.",
                "requires_double_confirmation": False,
                "requires_command": True,
            },
            {
                "runbook_name": "recriar-vps-iac",
                "category": "semi",
                "title": "Recriar VPS a partir de template/IaC",
                "summary": "Executa o provisionamento automatizado da VPS reserva ou substituta.",
                "impact": "Pode criar recursos novos e alterar inventario de infraestrutura.",
                "prechecks": [
                    "Confirmar template/IaC atualizado",
                    "Confirmar credenciais do provedor",
                    "Confirmar custos e naming da nova VPS",
                ],
                "rollback_plan": "Destruir a VPS criada e voltar ao ambiente anterior.",
                "requires_double_confirmation": True,
                "requires_command": True,
            },
            {
                "runbook_name": "rotacionar-segredos",
                "category": "semi",
                "title": "Rotacionar segredos sensiveis",
                "summary": "Gera rota controlada de segredos, com comando unico e confirmacao.",
                "impact": "Pode invalidar credenciais em uso pelos servicos.",
                "prechecks": [
                    "Confirmar janela de manutencao",
                    "Confirmar destinos que usam o segredo",
                    "Confirmar plano de rollback e redistribuicao",
                ],
                "rollback_plan": "Restaurar o segredo anterior e reiniciar apenas os servicos afetados.",
                "requires_double_confirmation": True,
                "requires_command": True,
            },
            {
                "runbook_name": "desastre-real-failover",
                "category": "manual",
                "title": "Desastre real com decisao de failover",
                "summary": "Runbook guiado para decisao operacional de failover real.",
                "impact": "Pode mover definitivamente o trafego de producao.",
                "prechecks": [
                    "Confirmar severidade e escopo do incidente",
                    "Confirmar indisponibilidade real da primaria",
                    "Aprovar failover com responsavel",
                ],
                "rollback_plan": "Definir criterios de retorno antes de acionar o failover.",
                "requires_double_confirmation": True,
                "requires_command": False,
            },
            {
                "runbook_name": "restore-producao",
                "category": "manual",
                "title": "Restore para producao",
                "summary": "Restaura backup em producao apenas sob aprovacao explicita.",
                "impact": "Pode sobrescrever dados atuais de producao.",
                "prechecks": [
                    "Confirmar backup correto",
                    "Confirmar snapshot ou backup previo do estado atual",
                    "Confirmar aprovacao formal",
                ],
                "rollback_plan": "Restaurar o snapshot anterior ou backup do estado pre-restore.",
                "requires_double_confirmation": True,
                "requires_command": True,
            },
            {
                "runbook_name": "troca-provedor-ip",
                "category": "manual",
                "title": "Troca definitiva de provedor/IP",
                "summary": "Guia a migracao definitiva de ambiente e endereco de producao.",
                "impact": "Pode alterar todas as rotas de acesso do ambiente.",
                "prechecks": [
                    "Confirmar novos IPs e dominos",
                    "Confirmar ambiente destino pronto",
                    "Confirmar plano de comunicacao",
                ],
                "rollback_plan": "Restaurar DNS e rotas para o provedor/IP anterior.",
                "requires_double_confirmation": True,
                "requires_command": False,
            },
            {
                "runbook_name": "incidente-seguranca",
                "category": "manual",
                "title": "Incidente de seguranca/ransomware",
                "summary": "Ativa o modo de contencao e preserva evidencias antes de qualquer restore.",
                "impact": "Pode isolar servicos e suspender acesso externo.",
                "prechecks": [
                    "Preservar evidencias e logs",
                    "Confirmar escopo do comprometimento",
                    "Aprovar contencao",
                ],
                "rollback_plan": "Encerrar contencao gradualmente apos saneamento e validacao.",
                "requires_double_confirmation": True,
                "requires_command": False,
            },
        ]

    @staticmethod
    def list_dr_runbooks():
        templates = {item["runbook_name"]: dict(item, source="built-in") for item in SystemActions._default_dr_runbook_templates()}
        custom_dir = SystemActions._dr_runbooks_dir()
        if os.path.isdir(custom_dir):
            for name in sorted(os.listdir(custom_dir)):
                if not name.endswith(".json"):
                    continue
                data = SystemActions._read_json_file(os.path.join(custom_dir, name), default={}) or {}
                if isinstance(data, dict) and data.get("runbook_name"):
                    data["source"] = "custom"
                    templates[data["runbook_name"]] = data
        return list(templates.values())

    @staticmethod
    def save_dr_runbook(
        runbook_name: str,
        title: str,
        category: str,
        summary: str,
        impact: str,
        command: str,
        rollback_plan: str,
        prechecks,
        requires_double_confirmation: bool,
        responsible: str = "",
        notes: str = "",
    ):
        try:
            if os.name == "nt":
                return False, SystemActions._txt("Runbooks DR nao suportados no Windows.", "DR runbooks are not supported on Windows.")
            safe_name = re.sub(r"[^A-Za-z0-9_-]", "-", runbook_name or "").strip("-")
            if not safe_name:
                return False, SystemActions._txt("Nome de runbook invalido.", "Invalid runbook name.")
            payload = {
                "runbook_name": safe_name,
                "title": title.strip() or safe_name,
                "category": (category or "manual").strip().lower(),
                "summary": summary.strip(),
                "impact": impact.strip(),
                "command": command.strip(),
                "rollback_plan": rollback_plan.strip(),
                "prechecks": [item.strip() for item in (prechecks or []) if str(item).strip()],
                "requires_double_confirmation": bool(requires_double_confirmation),
                "responsible": responsible.strip(),
                "notes": notes.strip(),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            file_path = os.path.join(SystemActions._dr_runbooks_dir(), f"{safe_name}.json")
            ok, msg = SystemActions._write_json_file(file_path, payload, mode=0o600)
            if not ok:
                return False, msg
            payload["runbook_file"] = file_path
            return True, payload
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def execute_dr_runbook(
        runbook_name: str,
        operator_name: str,
        approver_name: str = "",
        execute_command: bool = False,
        command_override: str = "",
        capture_evidence: bool = False,
    ):
        started = time.time()
        try:
            runbooks = {item["runbook_name"]: item for item in SystemActions.list_dr_runbooks()}
            runbook = runbooks.get(runbook_name)
            if not runbook:
                return False, SystemActions._txt(
                    f"Runbook nao encontrado: {runbook_name}",
                    f"Runbook not found: {runbook_name}",
                )
            chosen_command = (command_override or runbook.get("command") or "").strip()
            evidence_bundle = {}
            if capture_evidence:
                evidence_name = f"{runbook_name}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
                ok, evidence = SystemActions.export_incident_evidence_bundle(evidence_name)
                if ok:
                    evidence_bundle = evidence
            command_result = {"status": "skipped", "command": chosen_command, "output": ""}
            if execute_command and chosen_command:
                result = subprocess.run(["bash", "-lc", chosen_command], capture_output=True, text=True, check=False)
                command_result = {
                    "status": "success" if result.returncode == 0 else "failed",
                    "command": chosen_command,
                    "returncode": result.returncode,
                    "output": ((result.stdout or "") + "\n" + (result.stderr or "")).strip()[-6000:],
                }
            payload = {
                "runbook_name": runbook_name,
                "title": runbook.get("title", runbook_name),
                "category": runbook.get("category", ""),
                "operator_name": operator_name.strip(),
                "approver_name": approver_name.strip(),
                "execute_command": execute_command,
                "command_result": command_result,
                "capture_evidence": capture_evidence,
                "evidence_bundle": evidence_bundle,
                "timeline": [
                    {"event": "started", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(started)))},
                    {"event": "finished", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                ],
                "duration_seconds": int(time.time() - started),
                "rollback_plan": runbook.get("rollback_plan", ""),
                "impact": runbook.get("impact", ""),
                "prechecks": runbook.get("prechecks", []),
                "status": command_result["status"] if execute_command else "guided",
            }
            log_path = os.path.join(
                SystemActions._dr_operation_logs_dir(),
                f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{runbook_name}.json",
            )
            SystemActions._write_json_file(log_path, payload, mode=0o600)
            payload["log_file"] = log_path
            return True, payload
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def export_incident_evidence_bundle(
        incident_name: str,
        output_dir: str = "/var/backups/vps-tools/incidents",
    ):
        try:
            if os.name == "nt":
                return False, SystemActions._txt("Coleta de evidencias nao suportada no Windows.", "Evidence capture is not supported on Windows.")
            safe_name = re.sub(r"[^A-Za-z0-9_-]", "-", incident_name or "").strip("-")
            if not safe_name:
                return False, SystemActions._txt("Nome do incidente invalido.", "Invalid incident name.")
            timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            root_dir = os.path.join(output_dir, f"{safe_name}_{timestamp}")
            staging_dir = os.path.join(root_dir, "staging")
            os.makedirs(staging_dir, exist_ok=True)
            copy_targets = [
                ("/var/log/nginx", os.path.join(staging_dir, "logs", "nginx")),
                ("/var/log/auth.log", os.path.join(staging_dir, "logs", "auth.log")),
                ("/var/log/syslog", os.path.join(staging_dir, "logs", "syslog")),
            ]
            copied = []
            for src, dst in copy_targets:
                ok, msg = SystemActions._copy_path_if_exists(src, dst)
                if not ok:
                    return False, msg
                if msg:
                    copied.append(src)
            reports_dir = os.path.join(staging_dir, "reports")
            os.makedirs(reports_dir, exist_ok=True)
            commands = {
                "journalctl-b.txt": ["journalctl", "-b", "-n", "2000", "--no-pager"],
                "journalctl-nginx.txt": ["journalctl", "-u", "nginx", "-n", "500", "--no-pager"],
                "journalctl-ssh.txt": ["journalctl", "-u", "ssh", "-n", "500", "--no-pager"],
                "ss-ltnp.txt": ["ss", "-ltnp"],
                "iptables-S.txt": ["iptables", "-S"],
            }
            for filename, cmd in commands.items():
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                ok, msg = SystemActions._write_text_file(
                    os.path.join(reports_dir, filename),
                    (result.stdout or result.stderr or "").strip() + "\n",
                    mode=0o600,
                )
                if not ok:
                    return False, msg
            manifest = {
                "incident_name": safe_name,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "copied_items": copied,
                "report_files": sorted(commands.keys()),
            }
            ok, msg = SystemActions._write_json_file(os.path.join(staging_dir, "manifest.json"), manifest, mode=0o600)
            if not ok:
                return False, msg
            os.makedirs(output_dir, exist_ok=True)
            archive_path = os.path.join(output_dir, f"{safe_name}_{timestamp}.tar.gz")
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(staging_dir, arcname=os.path.basename(staging_dir))
            checksum_result = subprocess.run(["sha256sum", archive_path], capture_output=True, text=True, check=False)
            checksum_path = f"{archive_path}.sha256"
            ok, msg = SystemActions._write_text_file(checksum_path, (checksum_result.stdout or "").strip() + "\n", mode=0o600)
            if not ok:
                return False, msg
            shutil.rmtree(root_dir, ignore_errors=True)
            return True, {"archive_path": archive_path, "checksum_path": checksum_path}
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def record_dr_exercise(
        exercise_name: str,
        scenario: str,
        mode: str,
        profile_name: str = "",
        job_name: str = "",
        notes: str = "",
        duration_seconds: int | None = None,
    ):
        try:
            safe_name = re.sub(r"[^A-Za-z0-9_-]", "-", exercise_name or "").strip("-")
            if not safe_name:
                return False, SystemActions._txt("Nome do exercicio invalido.", "Invalid exercise name.")
            assessment = {}
            if profile_name:
                ok, data = SystemActions.assess_dr_profile(profile_name, job_name)
                assessment = data if ok else {"status": "failed", "message": data}
            payload = {
                "exercise_name": safe_name,
                "scenario": scenario.strip(),
                "mode": mode.strip(),
                "profile_name": profile_name.strip(),
                "job_name": job_name.strip(),
                "notes": notes.strip(),
                "duration_seconds": duration_seconds if duration_seconds is not None else 0,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "assessment": assessment,
            }
            file_path = os.path.join(
                SystemActions._dr_exercises_dir(),
                f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{safe_name}.json",
            )
            ok, msg = SystemActions._write_json_file(file_path, payload, mode=0o600)
            if not ok:
                return False, msg
            payload["exercise_file"] = file_path
            return True, payload
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def test_db_backup_restore(
        job_name: str,
        restore_db_name: str = "",
        keep_restore_db: bool = False,
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        def finish(result_payload: dict, ok: bool):
            SystemActions._write_json_file(paths["restore_status_file"], result_payload, mode=0o600)
            return ok, result_payload

        paths = SystemActions._dr_backup_job_paths(job_name)
        started = time.time()
        temp_dir = ""
        decrypted_path = ""
        temp_db_name = ""
        try:
            if os.name == "nt":
                return False, SystemActions._txt(
                    "Teste automatico de restore nao suportado no Windows.",
                    "Automatic restore test is not supported on Windows.",
                )
            if not os.path.exists(paths["config_file"]):
                return False, SystemActions._txt(
                    f"Job de backup nao encontrado: {job_name}",
                    f"Backup job not found: {job_name}",
                )
            config = SystemActions._read_json_file(paths["config_file"], default={}) or {}
            if (config.get("engine") or "").strip().lower() != "postgresql":
                return False, SystemActions._txt(
                    "Teste automatico de restore disponivel no momento apenas para jobs PostgreSQL.",
                    "Automatic restore test is currently available only for PostgreSQL jobs.",
                )

            last_status = SystemActions._read_json_file(paths["status_file"], default={}) or {}
            artifact_path = (last_status.get("artifact_path") or "").strip()
            if not artifact_path:
                return False, SystemActions._txt(
                    "Nenhum artefato de backup encontrado para testar o restore.",
                    "No backup artifact was found to test the restore.",
                )
            if not os.path.exists(artifact_path):
                return False, SystemActions._txt(
                    f"Artefato do backup nao encontrado: {artifact_path}",
                    f"Backup artifact not found: {artifact_path}",
                )

            env_vars = SystemActions._read_env_file(paths["env_file"])
            timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            temp_dir = os.path.join(paths["restore_tests_dir"], timestamp)
            os.makedirs(temp_dir, exist_ok=True)

            base_name = re.sub(r"[^A-Za-z0-9_]", "_", restore_db_name or "").strip("_")
            if not base_name:
                base_name = re.sub(r"[^A-Za-z0-9_]", "_", f"{paths['safe_job']}_restore_{timestamp.lower()}").strip("_")
            if not re.match(r"^[A-Za-z_]", base_name):
                base_name = f"r_{base_name}"
            temp_db_name = base_name[:63]

            update(10, SystemActions._txt("Preparando artefato para restore", "Preparing artifact for restore"))
            restore_input = artifact_path
            encryption_mode = (env_vars.get("ENCRYPTION_MODE") or "none").strip().lower()
            if encryption_mode == "gpg_symmetric":
                if not shutil.which("gpg"):
                    payload = {
                        "job_name": paths["safe_job"],
                        "status": "failed",
                        "message": "gpg not found for restore test",
                        "artifact_path": artifact_path,
                        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "duration_seconds": int(time.time() - started),
                    }
                    return finish(payload, False)
                passphrase = env_vars.get("ENCRYPTION_PASSPHRASE") or ""
                if not passphrase:
                    payload = {
                        "job_name": paths["safe_job"],
                        "status": "failed",
                        "message": "missing encryption passphrase for restore test",
                        "artifact_path": artifact_path,
                        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "duration_seconds": int(time.time() - started),
                    }
                    return finish(payload, False)
                decrypted_path = os.path.join(temp_dir, "restore-input.dump")
                result = subprocess.run(
                    [
                        "gpg",
                        "--batch",
                        "--yes",
                        "--pinentry-mode",
                        "loopback",
                        "--passphrase-fd",
                        "0",
                        "--output",
                        decrypted_path,
                        "--decrypt",
                        artifact_path,
                    ],
                    input=passphrase,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    payload = {
                        "job_name": paths["safe_job"],
                        "status": "failed",
                        "message": (result.stderr or result.stdout or "").strip() or "failed to decrypt backup artifact",
                        "artifact_path": artifact_path,
                        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "duration_seconds": int(time.time() - started),
                    }
                    return finish(payload, False)
                restore_input = decrypted_path

            update(35, SystemActions._txt("Criando banco temporario de restore", "Creating temporary restore database"))
            drop_existing = SystemActions._run_as_postgres(
                ["psql", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {temp_db_name};"]
            )
            if drop_existing.returncode != 0:
                payload = {
                    "job_name": paths["safe_job"],
                    "status": "failed",
                    "message": (drop_existing.stderr or drop_existing.stdout or "").strip() or "failed to drop previous restore database",
                    "artifact_path": artifact_path,
                    "restore_db_name": temp_db_name,
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "duration_seconds": int(time.time() - started),
                }
                return finish(payload, False)
            create_db = SystemActions._run_as_postgres(
                ["psql", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c", f"CREATE DATABASE {temp_db_name};"]
            )
            if create_db.returncode != 0:
                payload = {
                    "job_name": paths["safe_job"],
                    "status": "failed",
                    "message": (create_db.stderr or create_db.stdout or "").strip() or "failed to create restore database",
                    "artifact_path": artifact_path,
                    "restore_db_name": temp_db_name,
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "duration_seconds": int(time.time() - started),
                }
                return finish(payload, False)

            update(65, SystemActions._txt("Restaurando dump no banco temporario", "Restoring dump into temporary database"))
            restore_result = SystemActions._run_as_postgres(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--dbname",
                    temp_db_name,
                    restore_input,
                ]
            )
            if restore_result.returncode != 0:
                payload = {
                    "job_name": paths["safe_job"],
                    "status": "failed",
                    "message": (restore_result.stderr or restore_result.stdout or "").strip() or "pg_restore failed",
                    "artifact_path": artifact_path,
                    "restore_db_name": temp_db_name,
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "duration_seconds": int(time.time() - started),
                }
                return finish(payload, False)

            update(85, SystemActions._txt("Executando validacoes do banco restaurado", "Running restored database validations"))
            db_name_check = SystemActions._run_as_postgres(["psql", "-d", temp_db_name, "-tAc", "SELECT current_database();"])
            table_count_check = SystemActions._run_as_postgres(
                [
                    "psql",
                    "-d",
                    temp_db_name,
                    "-tAc",
                    "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema');",
                ]
            )
            if db_name_check.returncode != 0 or table_count_check.returncode != 0:
                payload = {
                    "job_name": paths["safe_job"],
                    "status": "failed",
                    "message": (db_name_check.stderr or table_count_check.stderr or "").strip() or "restore validation queries failed",
                    "artifact_path": artifact_path,
                    "restore_db_name": temp_db_name,
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "duration_seconds": int(time.time() - started),
                }
                return finish(payload, False)

            table_count_text = (table_count_check.stdout or "").strip() or "0"
            payload = {
                "job_name": paths["safe_job"],
                "status": "success",
                "message": "automatic restore test completed successfully",
                "artifact_path": artifact_path,
                "restore_db_name": temp_db_name,
                "restore_input_path": restore_input,
                "keep_restore_db": keep_restore_db,
                "table_count": int(table_count_text),
                "validated_database_name": (db_name_check.stdout or "").strip(),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "duration_seconds": int(time.time() - started),
            }
            update(100, SystemActions._txt("Teste automatico de restore concluido", "Automatic restore test completed"))
            return finish(payload, True)
        except Exception as exc:
            payload = {
                "job_name": paths["safe_job"],
                "status": "failed",
                "message": str(exc),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "duration_seconds": int(time.time() - started),
            }
            return finish(payload, False)
        finally:
            if temp_db_name and not keep_restore_db:
                SystemActions._run_as_postgres(
                    ["psql", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {temp_db_name};"]
                )
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def export_vps_config_snapshot(
        export_name: str = "vps-config",
        output_dir: str = "/var/backups/vps-tools/config-exports",
        include_environment_files: bool = True,
        include_letsencrypt: bool = False,
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            if os.name == "nt":
                return False, SystemActions._txt(
                    "Export de configuracoes da VPS nao suportado no Windows.",
                    "VPS configuration export is not supported on Windows.",
                )
            safe_name = re.sub(r"[^A-Za-z0-9_-]", "-", export_name or "").strip("-") or "vps-config"
            if not output_dir.startswith("/"):
                return False, SystemActions._txt("Diretorio de export deve ser absoluto.", "Export directory must be absolute.")

            timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            root_dir = os.path.join(output_dir, f"{safe_name}_{timestamp}")
            staging_dir = os.path.join(root_dir, "staging")
            os.makedirs(staging_dir, exist_ok=True)

            update(10, SystemActions._txt("Copiando configuracoes principais", "Copying main configurations"))
            copy_targets = [
                ("/etc/nginx", os.path.join(staging_dir, "etc", "nginx")),
                ("/etc/systemd/system", os.path.join(staging_dir, "etc", "systemd", "system")),
                ("/etc/passwd", os.path.join(staging_dir, "etc", "passwd")),
                ("/etc/group", os.path.join(staging_dir, "etc", "group")),
                ("/etc/hosts", os.path.join(staging_dir, "etc", "hosts")),
                ("/etc/hostname", os.path.join(staging_dir, "etc", "hostname")),
            ]
            if include_letsencrypt:
                copy_targets.append(("/etc/letsencrypt", os.path.join(staging_dir, "etc", "letsencrypt")))
            copied_items = []
            for src, dst in copy_targets:
                ok, msg = SystemActions._copy_path_if_exists(src, dst)
                if not ok:
                    return False, msg
                if msg:
                    copied_items.append(src)

            update(35, SystemActions._txt("Inventariando ambiente da VPS", "Building VPS inventory"))
            reports_dir = os.path.join(staging_dir, "reports")
            os.makedirs(reports_dir, exist_ok=True)
            commands = {
                "systemctl-list-unit-files.txt": ["systemctl", "list-unit-files", "--no-pager"],
                "systemctl-list-timers.txt": ["systemctl", "list-timers", "--all", "--no-pager"],
                "ss-ltnp.txt": ["ss", "-ltnp"],
                "iptables-S.txt": ["iptables", "-S"],
                "ufw-status.txt": ["ufw", "status", "verbose"],
                "certbot-certificates.txt": ["certbot", "certificates"],
            }
            if shutil.which("nft"):
                commands["nft-list-ruleset.txt"] = ["nft", "list", "ruleset"]
            if shutil.which("nginx"):
                commands["nginx-T.txt"] = ["nginx", "-T"]
            reports = {}
            for filename, cmd in commands.items():
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                content = (result.stdout or result.stderr or "").strip()
                ok, msg = SystemActions._write_text_file(os.path.join(reports_dir, filename), content + ("\n" if content else ""))
                if not ok:
                    return False, msg
                reports[filename] = content

            server_names = sorted(set(re.findall(r"(?m)^\s*server_name\s+([^;]+);", reports.get("nginx-T.txt", ""))))
            ok, msg = SystemActions._write_text_file(
                os.path.join(reports_dir, "domains-and-server-names.txt"),
                "\n".join(server_names) + ("\n" if server_names else ""),
            )
            if not ok:
                return False, msg

            update(55, SystemActions._txt("Coletando arquivos de ambiente", "Collecting environment files"))
            env_paths = []
            if include_environment_files:
                env_discovery = subprocess.run(
                    ["bash", "-lc", "find /opt -maxdepth 4 -type f \\( -name '*.env' -o -name 'app.env' \\) 2>/dev/null | sort"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                env_paths = [line.strip() for line in (env_discovery.stdout or "").splitlines() if line.strip()]
                env_root = os.path.join(staging_dir, "opt")
                for path in env_paths:
                    relative = path.lstrip("/")
                    ok, msg = SystemActions._copy_path_if_exists(path, os.path.join(staging_dir, relative))
                    if not ok:
                        return False, msg
                ok, msg = SystemActions._write_text_file(
                    os.path.join(reports_dir, "environment-files.txt"),
                    "\n".join(env_paths) + ("\n" if env_paths else ""),
                    mode=0o600,
                )
                if not ok:
                    return False, msg

            update(75, SystemActions._txt("Gerando manifesto do export", "Generating export manifest"))
            manifest = {
                "export_name": safe_name,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "output_dir": output_dir,
                "include_environment_files": include_environment_files,
                "include_letsencrypt": include_letsencrypt,
                "copied_items": copied_items,
                "environment_files": env_paths,
                "domain_inventory_count": len(server_names),
                "report_files": sorted(reports.keys()),
            }
            ok, msg = SystemActions._write_json_file(os.path.join(staging_dir, "manifest.json"), manifest, mode=0o600)
            if not ok:
                return False, msg

            update(90, SystemActions._txt("Compactando export da VPS", "Compressing VPS export"))
            archive_path = os.path.join(output_dir, f"{safe_name}_{timestamp}.tar.gz")
            os.makedirs(output_dir, exist_ok=True)
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(staging_dir, arcname=os.path.basename(staging_dir))
            checksum_result = subprocess.run(["sha256sum", archive_path], capture_output=True, text=True, check=False)
            checksum_path = f"{archive_path}.sha256"
            ok, msg = SystemActions._write_text_file(checksum_path, (checksum_result.stdout or "").strip() + "\n", mode=0o600)
            if not ok:
                return False, msg
            shutil.rmtree(root_dir, ignore_errors=True)

            update(100, SystemActions._txt("Export de configuracoes concluido", "Configuration export completed"))
            return True, {
                "archive_path": archive_path,
                "checksum_path": checksum_path,
                "copied_items": copied_items,
                "environment_files": env_paths,
                "server_names": server_names,
                "manifest": manifest,
            }
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
                return False, SystemActions._txt(
                    "Instalacao do PostgreSQL local nao suportada no Windows.",
                    "Local PostgreSQL installation is not supported on Windows.",
                )

            manager = SystemActions._package_manager()
            if manager != "apt":
                return False, SystemActions._txt(
                    "Provisionamento automatico do PostgreSQL disponivel apenas para Debian/Ubuntu.",
                    "Automatic PostgreSQL provisioning is available only on Debian/Ubuntu.",
                )

            ok, msg = SystemActions._validate_pg_identifier(
                db_name,
                SystemActions._txt("Nome do banco", "Database name"),
            )
            if not ok:
                return False, msg
            ok, msg = SystemActions._validate_pg_identifier(
                db_user,
                SystemActions._txt("Nome do usuario", "Username"),
            )
            if not ok:
                return False, msg
            if not db_password:
                return False, SystemActions._txt(
                    "Senha do usuario do banco nao pode ser vazia.",
                    "Database user password cannot be empty.",
                )
            if not (listen_addresses or "").strip():
                return False, SystemActions._txt("listen_addresses nao pode ser vazio.", "listen_addresses cannot be empty.")
            if not (jdbc_host or "").strip():
                return False, SystemActions._txt("Host JDBC nao pode ser vazio.", "JDBC host cannot be empty.")
            if not isinstance(jdbc_port, int) or not (1 <= jdbc_port <= 65535):
                return False, SystemActions._txt("Porta JDBC invalida.", "Invalid JDBC port.")

            update(5, SystemActions._txt("Atualizando cache de pacotes", "Updating package cache"))
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha no apt-get update.",
                    "apt-get update failed.",
                )

            update(20, SystemActions._txt("Instalando PostgreSQL", "Installing PostgreSQL"))
            result = subprocess.run(
                ["apt-get", "install", "-y", "postgresql", "postgresql-contrib"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha na instalacao do PostgreSQL.",
                    "PostgreSQL installation failed.",
                )

            update(40, SystemActions._txt("Habilitando e iniciando o servico", "Enabling and starting the service"))
            for cmd in (["systemctl", "enable", "postgresql"], ["systemctl", "start", "postgresql"]):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                        f"Falha ao executar: {' '.join(cmd)}",
                        f"Failed to execute: {' '.join(cmd)}",
                    )

            update(55, SystemActions._txt("Aplicando listen_addresses do PostgreSQL", "Applying PostgreSQL listen_addresses"))
            conf_path = SystemActions._find_postgresql_conf()
            if not conf_path:
                return False, SystemActions._txt(
                    "Arquivo postgresql.conf nao encontrado em /etc/postgresql.",
                    "postgresql.conf file not found in /etc/postgresql.",
                )
            pg_listen_addresses = listen_addresses.replace("'", "''")
            ok, msg = SystemActions._replace_or_append_setting(conf_path, "listen_addresses", f"'{pg_listen_addresses}'")
            if not ok:
                return False, msg

            result = subprocess.run(["systemctl", "restart", "postgresql"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao reiniciar o PostgreSQL.",
                    "Failed to restart PostgreSQL.",
                )

            password_sql = db_password.replace("'", "''")
            role_sql = (
                "DO $$ "
                f"BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{db_user}') THEN "
                f"CREATE ROLE {db_user} LOGIN ENCRYPTED PASSWORD '{password_sql}'; "
                f"ELSE ALTER ROLE {db_user} WITH LOGIN ENCRYPTED PASSWORD '{password_sql}'; "
                "END IF; "
                "END $$;"
            )

            update(70, SystemActions._txt("Criando ou atualizando usuario do banco", "Creating or updating database user"))
            result = SystemActions._run_as_postgres(
                ["psql", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c", role_sql]
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao criar/atualizar usuario do PostgreSQL.",
                    "Failed to create/update PostgreSQL user.",
                )

            update(80, SystemActions._txt("Criando ou ajustando banco de dados", "Creating or adjusting database"))
            exists = SystemActions._run_as_postgres(
                ["psql", "-tAc", f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'"]
            )
            if exists.returncode != 0:
                return False, exists.stderr.strip() or exists.stdout.strip() or SystemActions._txt(
                    "Falha ao verificar existencia do banco.",
                    "Failed to check whether the database exists.",
                )
            if exists.stdout.strip() != "1":
                create_db = SystemActions._run_as_postgres(
                    ["psql", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c", f"CREATE DATABASE {db_name} OWNER {db_user};"]
                )
                if create_db.returncode != 0:
                    return False, create_db.stderr.strip() or create_db.stdout.strip() or SystemActions._txt(
                        "Falha ao criar banco de dados.",
                        "Failed to create database.",
                    )

            grant_sql = (
                f"ALTER DATABASE {db_name} OWNER TO {db_user}; "
                f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user};"
            )
            result = SystemActions._run_as_postgres(
                ["psql", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c", grant_sql]
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao conceder privilegios no banco.",
                    "Failed to grant database privileges.",
                )

            schema_sql = (
                f"ALTER SCHEMA public OWNER TO {db_user}; "
                f"GRANT ALL ON SCHEMA public TO {db_user};"
            )
            result = SystemActions._run_as_postgres(
                ["psql", "-v", "ON_ERROR_STOP=1", "-d", db_name, "-c", schema_sql]
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao ajustar o schema public.",
                    "Failed to adjust the public schema.",
                )

            update(90, SystemActions._txt("Coletando status final", "Collecting final status"))
            test_result = SystemActions._run_as_postgres(["psql", "-d", db_name, "-c", "\\l"])
            if test_result.returncode != 0:
                return False, test_result.stderr.strip() or test_result.stdout.strip() or SystemActions._txt(
                    "Falha no teste final do banco.",
                    "Final database test failed.",
                )

            status_result = subprocess.run(
                ["systemctl", "status", "postgresql", "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )

            os_release = SystemActions._read_os_release()
            update(100, SystemActions._txt("Provisionamento concluido", "Provisioning completed"))
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
    def allow_postgresql_for_local_panel(
        app_dir: str = "/opt/vps-tools-db-panel",
        docker_network_name: str = "",
        db_name: str = "hospital",
        db_user: str = "hospital_app",
        auth_method: str = "scram-sha-256",
        listen_host_override: str = "",
        docker_cidr_override: str = "",
        postgres_port: int = 5432,
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            if os.name == "nt":
                return False, SystemActions._txt(
                    "Configuracao do PostgreSQL local para painel Docker nao suportada no Windows.",
                    "Local PostgreSQL setup for Docker panel is not supported on Windows.",
                )

            database_value = (db_name or "").strip() or "all"
            user_value = (db_user or "").strip() or "all"
            if database_value != "all":
                ok, msg = SystemActions._validate_pg_identifier(
                    database_value,
                    SystemActions._txt("Nome do banco", "Database name"),
                )
                if not ok:
                    return False, msg
            if user_value != "all":
                ok, msg = SystemActions._validate_pg_identifier(
                    user_value,
                    SystemActions._txt("Nome do usuario", "Username"),
                )
                if not ok:
                    return False, msg

            auth_value = (auth_method or "").strip().lower()
            if auth_value not in {"scram-sha-256", "md5", "password", "trust", "reject"}:
                return False, SystemActions._txt(
                    "Metodo de autenticacao invalido. Use scram-sha-256, md5, password, trust ou reject.",
                    "Invalid authentication method. Use scram-sha-256, md5, password, trust or reject.",
                )
            if not isinstance(postgres_port, int) or not (1 <= postgres_port <= 65535):
                return False, SystemActions._txt("Porta do PostgreSQL invalida.", "Invalid PostgreSQL port.")

            update(10, SystemActions._txt("Detectando a rede Docker do painel", "Detecting the panel Docker network"))
            network_result = SystemActions._detect_web_db_panel_network(app_dir=app_dir, docker_network_name=docker_network_name)
            if not network_result[0]:
                return False, network_result[1]
            network_data = network_result[1]
            docker_network = network_data["network_name"]
            docker_cidr = (docker_cidr_override or "").strip() or (network_data.get("subnet") or "").strip()
            host_gateway_result = SystemActions._detect_docker_host_gateway_ip()
            if not host_gateway_result[0] and not (listen_host_override or "").strip():
                return False, host_gateway_result[1]
            listen_host = (listen_host_override or "").strip() or host_gateway_result[1]
            if not docker_cidr:
                return False, SystemActions._txt(
                    "Nao foi possivel detectar a sub-rede Docker. Informe o CIDR manualmente.",
                    "Could not detect the Docker subnet. Provide the CIDR manually.",
                )
            if not listen_host:
                return False, SystemActions._txt(
                    "Nao foi possivel detectar o gateway do host para o painel Docker. Informe o IP manualmente.",
                    "Could not detect the host gateway for the Docker panel. Provide the IP manually.",
                )

            update(30, SystemActions._txt("Detectando arquivos do PostgreSQL", "Detecting PostgreSQL files"))
            conf_ok, conf_path = SystemActions._postgresql_runtime_setting("config_file")
            if not conf_ok:
                conf_path = SystemActions._find_postgresql_conf()
            if not conf_path:
                return False, SystemActions._txt(
                    "Arquivo postgresql.conf nao encontrado.",
                    "postgresql.conf file not found.",
                )
            hba_ok, hba_path = SystemActions._postgresql_runtime_setting("hba_file")
            if not hba_ok:
                hba_path = os.path.join(os.path.dirname(conf_path), "pg_hba.conf")
            if not hba_path or not os.path.exists(hba_path):
                return False, SystemActions._txt(
                    "Arquivo pg_hba.conf nao encontrado.",
                    "pg_hba.conf file not found.",
                )

            update(45, SystemActions._txt("Mesclando listen_addresses do PostgreSQL", "Merging PostgreSQL listen_addresses"))
            listen_result = SystemActions._postgresql_runtime_setting("listen_addresses")
            current_listen = listen_result[1] if listen_result[0] else "localhost"
            if current_listen.strip() == "*":
                merged_listen = "*"
            else:
                merged_tokens = []
                for token in (current_listen or "localhost").split(","):
                    normalized = token.strip().strip("'").strip('"')
                    if normalized and normalized not in merged_tokens:
                        merged_tokens.append(normalized)
                for token in ("localhost", "127.0.0.1", listen_host):
                    normalized = token.strip()
                    if normalized and normalized not in merged_tokens:
                        merged_tokens.append(normalized)
                merged_listen = ",".join(merged_tokens)
            ok, msg = SystemActions._replace_or_append_setting(conf_path, "listen_addresses", f"'{merged_listen}'")
            if not ok:
                return False, msg

            update(65, SystemActions._txt("Atualizando regra do pg_hba.conf para o painel", "Updating pg_hba.conf rule for the panel"))
            ok, msg = SystemActions._upsert_pg_hba_rule(
                hba_path,
                database_value,
                user_value,
                docker_cidr,
                auth_value,
            )
            if not ok:
                return False, msg

            update(80, SystemActions._txt("Reiniciando PostgreSQL", "Restarting PostgreSQL"))
            result = subprocess.run(["systemctl", "restart", "postgresql"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao reiniciar o PostgreSQL.",
                    "Failed to restart PostgreSQL.",
                )

            update(95, SystemActions._txt("Validando escuta do PostgreSQL", "Validating PostgreSQL listening sockets"))
            service_status = subprocess.run(["systemctl", "status", "postgresql", "--no-pager"], capture_output=True, text=True, check=False)
            ss_result = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, check=False)
            port_lines = []
            if ss_result.returncode == 0:
                target = f":{postgres_port}"
                port_lines = [line for line in (ss_result.stdout or "").splitlines() if target in line]

            update(100, SystemActions._txt("Acesso local do painel ao PostgreSQL configurado", "Local panel access to PostgreSQL configured"))
            return True, {
                "docker_network_name": docker_network,
                "docker_cidr": docker_cidr,
                "listen_host": listen_host,
                "db_name": database_value,
                "db_user": user_value,
                "auth_method": auth_value,
                "listen_addresses": merged_listen,
                "config_file": conf_path,
                "pg_hba_file": hba_path,
                "service_status": (service_status.stdout or service_status.stderr or "").strip(),
                "ss_output": "\n".join(port_lines).strip(),
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
                return False, SystemActions._txt(
                    "Preparo do backend Spring Boot nao suportado no Windows.",
                    "Spring Boot backend preparation is not supported on Windows.",
                )

            manager = SystemActions._package_manager()
            if manager != "apt":
                return False, SystemActions._txt(
                    "Preparacao automatica do backend disponivel apenas para Debian/Ubuntu.",
                    "Automatic backend preparation is available only on Debian/Ubuntu.",
                )

            if not app_dir.startswith("/"):
                return False, SystemActions._txt("Diretorio da aplicacao deve ser absoluto.", "Application directory must be absolute.")
            if repo_url and not repo_dir.startswith("/"):
                return False, SystemActions._txt("Diretorio do repositorio deve ser absoluto.", "Repository directory must be absolute.")
            if not jar_name or "/" in jar_name or "\\" in jar_name:
                return False, SystemActions._txt("Nome do JAR invalido.", "Invalid JAR filename.")
            if not isinstance(app_port, int) or not (1 <= app_port <= 65535):
                return False, SystemActions._txt("Porta da aplicacao invalida.", "Invalid application port.")

            app_owner = SystemActions._resolve_linux_owner(owner_user)

            update(5, SystemActions._txt("Atualizando cache de pacotes", "Updating package cache"))
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt("Falha no apt-get update.", "apt-get update failed.")

            update(20, SystemActions._txt("Instalando Java 17", "Installing Java 17"))
            result = subprocess.run(
                ["apt-get", "install", "-y", "openjdk-17-jre-headless"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha na instalacao do Java 17.",
                    "Java 17 installation failed.",
                )

            if repo_url:
                update(35, SystemActions._txt("Instalando git", "Installing git"))
                result = subprocess.run(["apt-get", "install", "-y", "git"], capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt("Falha na instalacao do git.", "Git installation failed.")

            update(50, SystemActions._txt("Criando pasta da aplicacao", "Creating application directory"))
            result = subprocess.run(["mkdir", "-p", app_dir], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    f"Falha ao criar {app_dir}.",
                    f"Failed to create {app_dir}.",
                )

            result = subprocess.run(["chown", "-R", f"{app_owner}:{app_owner}", app_dir], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    f"Falha ao ajustar dono de {app_dir}.",
                    f"Failed to change owner of {app_dir}.",
                )

            repo_status = ""
            if repo_url:
                update(70, SystemActions._txt("Preparando repositorio do backend", "Preparing backend repository"))
                if os.path.isdir(os.path.join(repo_dir, ".git")):
                    result = subprocess.run(["git", "-C", repo_dir, "pull", "--ff-only"], capture_output=True, text=True, check=False)
                    if result.returncode != 0:
                        return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                            "Falha no git pull do backend.",
                            "Backend git pull failed.",
                        )
                    repo_status = (result.stdout or result.stderr or "").strip() or SystemActions._txt(
                        "Repositorio atualizado.",
                        "Repository updated.",
                    )
                else:
                    if os.path.exists(repo_dir) and os.listdir(repo_dir):
                        return False, SystemActions._txt(
                            f"Diretorio do repositorio ja existe e nao esta vazio: {repo_dir}",
                            f"Repository directory already exists and is not empty: {repo_dir}",
                        )
                    result = subprocess.run(["git", "clone", repo_url, repo_dir], capture_output=True, text=True, check=False)
                    if result.returncode != 0:
                        return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                            "Falha no git clone do backend.",
                            "Backend git clone failed.",
                        )
                    repo_status = (result.stdout or result.stderr or "").strip() or SystemActions._txt(
                        "Repositorio clonado.",
                        "Repository cloned.",
                    )

                result = subprocess.run(["chown", "-R", f"{app_owner}:{app_owner}", repo_dir], capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                        f"Falha ao ajustar dono de {repo_dir}.",
                        f"Failed to change owner of {repo_dir}.",
                    )

            update(85, SystemActions._txt("Coletando versoes e proximos passos", "Collecting versions and next steps"))
            java_result = subprocess.run(["java", "-version"], capture_output=True, text=True, check=False)
            java_version = (java_result.stderr or java_result.stdout or "").strip()
            if java_result.returncode != 0:
                return False, java_version or SystemActions._txt(
                    "Falha ao validar java -version.",
                    "Failed to validate java -version.",
                )

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

            update(100, SystemActions._txt("Preparacao concluida", "Preparation completed"))
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
                    SystemActions._txt("continue com 22 so para seu IP", "keep port 22 open only to your IP"),
                    SystemActions._txt(
                        f"abra {app_port} temporariamente so para seu IP, se quiser testar no navegador",
                        f"open port {app_port} temporarily only to your IP if you want to test in the browser",
                    ),
                    SystemActions._txt("nao abra 5432", "do not open port 5432"),
                    SystemActions._txt(
                        "nao abra 80/443 ate concluir a instalacao do backend",
                        "do not open 80/443 until the backend installation is complete",
                    ),
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
                return False, SystemActions._txt(
                    "Instalacao de banco nao suportada no Windows.",
                    "Database installation is not supported on Windows.",
                )
            if SystemActions._package_manager() != "apt":
                return False, SystemActions._txt(
                    "Instalacao automatica disponivel apenas para Debian/Ubuntu.",
                    "Automatic installation is available only on Debian/Ubuntu.",
                )
            if flavor not in {"mysql", "mariadb"}:
                return False, SystemActions._txt(
                    f"Sabor de banco invalido: {flavor}",
                    f"Invalid database flavor: {flavor}",
                )
            ok, msg = SystemActions._validate_pg_identifier(
                db_name,
                SystemActions._txt("Nome do banco", "Database name"),
            )
            if not ok:
                return False, msg
            ok, msg = SystemActions._validate_pg_identifier(
                db_user,
                SystemActions._txt("Nome do usuario", "Username"),
            )
            if not ok:
                return False, msg
            if not db_password:
                return False, SystemActions._txt(
                    "Senha do banco nao pode ser vazia.",
                    "Database password cannot be empty.",
                )
            if not (1 <= port <= 65535):
                return False, SystemActions._txt("Porta invalida.", "Invalid port.")

            package_name = "mysql-server" if flavor == "mysql" else "mariadb-server"
            service_name = "mysql" if flavor == "mysql" else "mariadb"
            conf_dir = "/etc/mysql/mysql.conf.d" if flavor == "mysql" else "/etc/mysql/mariadb.conf.d"
            conf_path = os.path.join(conf_dir, "zz-vps-tools.cnf")

            update(5, SystemActions._txt("Atualizando cache de pacotes", "Updating package cache"))
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha no apt-get update.",
                    "apt-get update failed.",
                )

            update(20, SystemActions._txt(f"Instalando {package_name}", f"Installing {package_name}"))
            result = subprocess.run(["apt-get", "install", "-y", package_name], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    f"Falha na instalacao do {package_name}.",
                    f"{package_name} installation failed.",
                )

            update(40, SystemActions._txt("Aplicando configuracao de bind/porta", "Applying bind/port configuration"))
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
                    return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                        f"Falha ao executar: {' '.join(cmd)}",
                        f"Failed to execute: {' '.join(cmd)}",
                    )

            password_sql = db_password.replace("'", "''")
            grant_host_sql = grant_host.replace("'", "''")
            sql = (
                f"CREATE DATABASE IF NOT EXISTS `{db_name}`;"
                f"CREATE USER IF NOT EXISTS '{db_user}'@'{grant_host_sql}' IDENTIFIED BY '{password_sql}';"
                f"ALTER USER '{db_user}'@'{grant_host_sql}' IDENTIFIED BY '{password_sql}';"
                f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'{grant_host_sql}';"
                "FLUSH PRIVILEGES;"
            )

            update(65, SystemActions._txt("Criando banco e usuario", "Creating database and user"))
            result = subprocess.run(["mysql", "-e", sql], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao criar banco/usuario.",
                    "Failed to create database/user.",
                )

            status_result = subprocess.run(
                ["systemctl", "status", service_name, "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            jdbc_scheme = "mysql" if flavor == "mysql" else "mariadb"
            update(100, SystemActions._txt("Banco configurado", "Database configured"))
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
                return False, SystemActions._txt(
                    "Instalacao do MongoDB nao suportada no Windows.",
                    "MongoDB installation is not supported on Windows.",
                )
            if SystemActions._package_manager() != "apt":
                return False, SystemActions._txt(
                    "Instalacao automatica disponivel apenas para Debian/Ubuntu.",
                    "Automatic installation is available only on Debian/Ubuntu.",
                )
            ok, msg = SystemActions._validate_pg_identifier(
                app_db,
                SystemActions._txt("Nome do banco", "Database name"),
            )
            if not ok:
                return False, msg
            ok, msg = SystemActions._validate_pg_identifier(
                app_user,
                SystemActions._txt("Nome do usuario", "Username"),
            )
            if not ok:
                return False, msg
            if not app_password:
                return False, SystemActions._txt(
                    "Senha do banco nao pode ser vazia.",
                    "Database password cannot be empty.",
                )
            codename = SystemActions._ubuntu_codename()
            if codename not in {"focal", "jammy", "noble"}:
                unknown = SystemActions._txt("desconhecido", "unknown")
                return False, SystemActions._txt(
                    f"Ubuntu sem suporte oficial configurado para MongoDB 8.0: {codename or unknown}",
                    f"Ubuntu without configured official support for MongoDB 8.0: {codename or unknown}",
                )

            update(5, SystemActions._txt("Instalando dependencias", "Installing dependencies"))
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha no apt-get update.",
                    "apt-get update failed.",
                )
            result = subprocess.run(["apt-get", "install", "-y", "gnupg", "curl"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao instalar gnupg/curl.",
                    "Failed to install gnupg/curl.",
                )

            update(25, SystemActions._txt("Configurando repositorio oficial do MongoDB", "Configuring the official MongoDB repository"))
            key_cmd = [
                "bash",
                "-lc",
                "curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor",
            ]
            result = subprocess.run(key_cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao importar chave do MongoDB.",
                    "Failed to import the MongoDB key.",
                )
            repo_line = (
                f"deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] "
                f"https://repo.mongodb.org/apt/ubuntu {codename}/mongodb-org/8.0 multiverse\n"
            )
            ok, msg = SystemActions._write_text_file("/etc/apt/sources.list.d/mongodb-org-8.0.list", repo_line)
            if not ok:
                return False, msg

            update(45, SystemActions._txt("Instalando MongoDB", "Installing MongoDB"))
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao atualizar repositorio MongoDB.",
                    "Failed to refresh the MongoDB repository.",
                )
            result = subprocess.run(["apt-get", "install", "-y", "mongodb-org"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha na instalacao do MongoDB.",
                    "MongoDB installation failed.",
                )

            update(60, SystemActions._txt("Aplicando bind/auth no mongod.conf", "Applying bind/auth in mongod.conf"))
            ok, msg = SystemActions._set_mongod_config("/etc/mongod.conf", bind_ip=bind_ip, port=port, auth_enabled=False)
            if not ok:
                return False, msg

            for cmd in (["systemctl", "enable", "mongod"], ["systemctl", "restart", "mongod"]):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                        f"Falha ao executar: {' '.join(cmd)}",
                        f"Failed to execute: {' '.join(cmd)}",
                    )

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
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao criar usuario no MongoDB.",
                    "Failed to create MongoDB user.",
                )

            if enable_auth:
                ok, msg = SystemActions._set_mongod_config("/etc/mongod.conf", bind_ip=bind_ip, port=port, auth_enabled=True)
                if not ok:
                    return False, msg
                result = subprocess.run(["systemctl", "restart", "mongod"], capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                        "Falha ao reiniciar mongod com auth.",
                        "Failed to restart mongod with auth.",
                    )

            status_result = subprocess.run(
                ["systemctl", "status", "mongod", "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            update(100, SystemActions._txt("MongoDB configurado", "MongoDB configured"))
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
                return False, SystemActions._txt(
                    "Instalacao do Redis nao suportada no Windows.",
                    "Redis installation is not supported on Windows.",
                )
            if SystemActions._package_manager() != "apt":
                return False, SystemActions._txt(
                    "Instalacao automatica disponivel apenas para Debian/Ubuntu.",
                    "Automatic installation is available only on Debian/Ubuntu.",
                )
            if not (1 <= port <= 65535):
                return False, SystemActions._txt("Porta invalida.", "Invalid port.")

            update(5, SystemActions._txt("Instalando dependencias", "Installing dependencies"))
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha no apt-get update.",
                    "apt-get update failed.",
                )
            result = subprocess.run(["apt-get", "install", "-y", "curl", "gpg"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao instalar dependencias do Redis.",
                    "Failed to install Redis dependencies.",
                )

            update(25, SystemActions._txt("Configurando repositorio oficial do Redis", "Configuring the official Redis repository"))
            key_cmd = [
                "bash",
                "-lc",
                "curl -fsSL https://packages.redis.io/gpg | gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg",
            ]
            result = subprocess.run(key_cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao importar chave do Redis.",
                    "Failed to import the Redis key.",
                )
            repo_cmd = [
                "bash",
                "-lc",
                "echo 'deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb "
                "$(lsb_release -cs) main' > /etc/apt/sources.list.d/redis.list",
            ]
            result = subprocess.run(repo_cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao criar repositorio do Redis.",
                    "Failed to create the Redis repository.",
                )

            update(45, SystemActions._txt("Instalando Redis", "Installing Redis"))
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao atualizar repositorio Redis.",
                    "Failed to refresh the Redis repository.",
                )
            result = subprocess.run(["apt-get", "install", "-y", "redis-server"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha na instalacao do Redis.",
                    "Redis installation failed.",
                )

            conf_path = "/etc/redis/redis.conf"
            update(65, SystemActions._txt("Aplicando bind/porta/senha", "Applying bind/port/password"))
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
                    return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                        f"Falha ao executar: {' '.join(cmd)}",
                        f"Failed to execute: {' '.join(cmd)}",
                    )

            status_result = subprocess.run(
                ["systemctl", "status", "redis-server", "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            update(100, SystemActions._txt("Redis configurado", "Redis configured"))
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
            if SystemActions._package_manager() != "apt":
                return False, SystemActions._txt(
                    "Publicacao automatica do painel disponivel apenas para Debian/Ubuntu.",
                    "Automatic panel publishing is available only on Debian/Ubuntu.",
                )
            ok, msg = SystemActions._validate_service_name(site_name)
            if not ok:
                return False, msg
            if not server_names:
                return False, SystemActions._txt(
                    "Informe ao menos um dominio/server_name.",
                    "Provide at least one domain/server_name.",
                )
            if not (1 <= upstream_port <= 65535):
                return False, SystemActions._txt("Porta upstream invalida.", "Invalid upstream port.")

            update(5, SystemActions._txt("Instalando Nginx", "Installing Nginx"))
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha no apt-get update.",
                    "apt-get update failed.",
                )
            result = subprocess.run(["apt-get", "install", "-y", "nginx"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha na instalacao do Nginx.",
                    "Nginx installation failed.",
                )

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
            update(35, SystemActions._txt("Gravando virtual host", "Writing virtual host"))
            ok, msg = SystemActions._write_text_file(available, conf_content)
            if not ok:
                return False, msg
            if not os.path.exists(enabled):
                os.symlink(available, enabled)

            update(60, SystemActions._txt("Validando configuracao do Nginx", "Validating Nginx configuration"))
            result = subprocess.run(["nginx", "-t"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha no nginx -t.",
                    "nginx -t failed.",
                )

            for cmd in (["systemctl", "enable", "nginx"], ["systemctl", "restart", "nginx"]):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                        f"Falha ao executar: {' '.join(cmd)}",
                        f"Failed to execute: {' '.join(cmd)}",
                    )

            status_result = subprocess.run(
                ["systemctl", "status", "nginx", "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            update(100, SystemActions._txt("Reverse proxy configurado", "Reverse proxy configured"))
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
                return False, SystemActions._txt("Informe ao menos um dominio.", "Provide at least one domain.")
            if not email.strip():
                return False, SystemActions._txt("Informe um e-mail valido.", "Provide a valid email.")

            update(10, SystemActions._txt("Instalando Certbot e plugin Nginx", "Installing Certbot and the Nginx plugin"))
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha no apt-get update.",
                    "apt-get update failed.",
                )
            result = subprocess.run(
                ["apt-get", "install", "-y", "certbot", "python3-certbot-nginx"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha na instalacao do Certbot.",
                    "Certbot installation failed.",
                )

            update(45, SystemActions._txt("Emitindo certificado", "Issuing certificate"))
            cmd = ["certbot", "--nginx", "--non-interactive", "--agree-tos", "-m", email]
            if redirect_https:
                cmd.append("--redirect")
            for domain in domains:
                cmd.extend(["-d", domain])
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao emitir certificado HTTPS.",
                    "Failed to issue the HTTPS certificate.",
                )

            update(80, SystemActions._txt("Validando renovacao", "Validating renewal"))
            renew = subprocess.run(["certbot", "renew", "--dry-run"], capture_output=True, text=True, check=False)
            if renew.returncode != 0:
                return False, renew.stderr.strip() or renew.stdout.strip() or SystemActions._txt(
                    "Falha no teste de renovacao do Certbot.",
                    "Certbot renewal test failed.",
                )

            timer = subprocess.run(["systemctl", "status", "certbot.timer", "--no-pager"], capture_output=True, text=True, check=False)
            update(100, SystemActions._txt("HTTPS configurado", "HTTPS configured"))
            return True, {
                "domains": ", ".join(domains),
                "email": email,
                "timer_status": (timer.stdout or timer.stderr or "").strip(),
                "certbot_output": (result.stdout or result.stderr or "").strip(),
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def install_web_db_panel(
        app_dir: str = "/opt/vps-tools-db-panel",
        panel_port: int = 18090,
        enable_adminer: bool = True,
        enable_pgadmin: bool = True,
        enable_redisinsight: bool = True,
        pgadmin_email: str = "admin@localhost",
        pgadmin_password: str = "",
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            if os.name == "nt":
                return False, SystemActions._txt(
                    "Painel web de bancos nao suportado no Windows.",
                    "Web database panel is not supported on Windows.",
                )
            if SystemActions._package_manager() != "apt":
                return False, SystemActions._txt(
                    "Instalacao automatica do painel disponivel apenas para Debian/Ubuntu.",
                    "Automatic panel installation is available only on Debian/Ubuntu.",
                )
            if not app_dir.startswith("/"):
                return False, SystemActions._txt(
                    "Diretorio do painel deve ser absoluto.",
                    "Panel directory must be absolute.",
                )
            if not (1 <= panel_port <= 65535):
                return False, SystemActions._txt("Porta invalida.", "Invalid port.")
            if not any([enable_adminer, enable_pgadmin, enable_redisinsight]):
                return False, SystemActions._txt(
                    "Selecione pelo menos uma ferramenta para o painel.",
                    "Select at least one tool for the panel.",
                )
            if enable_pgadmin and "@" not in pgadmin_email:
                return False, SystemActions._txt(
                    "E-mail do pgAdmin invalido.",
                    "Invalid pgAdmin email.",
                )
            if enable_pgadmin and not pgadmin_password:
                pgadmin_password = SystemActions._random_secret(18)

            os_release = SystemActions._read_os_release()
            distro_id = (os_release.get("ID") or "").lower()
            if distro_id not in {"ubuntu", "debian"}:
                return False, SystemActions._txt(
                    f"Distribuicao nao suportada para instalacao automatica do Docker: {distro_id or 'desconhecida'}",
                    f"Unsupported distribution for automatic Docker installation: {distro_id or 'unknown'}",
                )

            version_codename = (os_release.get("UBUNTU_CODENAME") or os_release.get("VERSION_CODENAME") or "").strip()
            if not version_codename:
                return False, SystemActions._txt(
                    "Nao foi possivel identificar o codename do sistema para configurar o repositorio do Docker.",
                    "Could not identify the system codename to configure the Docker repository.",
                )

            update(3, SystemActions._txt("Preparando o Docker com seguranca", "Preparing Docker safely"))
            docker_is_installed = False
            docker_state = subprocess.run(
                ["systemctl", "is-active", "docker"],
                capture_output=True,
                text=True,
                check=False,
            )
            docker_socket_state = subprocess.run(
                ["systemctl", "is-active", "docker.socket"],
                capture_output=True,
                text=True,
                check=False,
            )
            if docker_state.returncode == 0 or docker_socket_state.returncode == 0:
                docker_is_installed = True
            else:
                docker_show = subprocess.run(
                    ["systemctl", "show", "docker", "--property=LoadState", "--value"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                docker_socket_show = subprocess.run(
                    ["systemctl", "show", "docker.socket", "--property=LoadState", "--value"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if (docker_show.stdout or "").strip() == "loaded" or (docker_socket_show.stdout or "").strip() == "loaded":
                    docker_is_installed = True

            if docker_is_installed:
                for cmd in (
                    ["systemctl", "stop", "docker"],
                    ["systemctl", "stop", "docker.socket"],
                ):
                    subprocess.run(cmd, capture_output=True, text=True, check=False)
                subprocess.run(["iptables", "-P", "FORWARD", "ACCEPT"], capture_output=True, text=True, check=False)

            update(5, SystemActions._txt("Instalando dependencias do Docker", "Installing Docker dependencies"))
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha no apt-get update.",
                    "apt-get update failed.",
                )
            result = subprocess.run(
                ["apt-get", "install", "-y", "ca-certificates", "curl"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao instalar dependencias do Docker.",
                    "Failed to install Docker dependencies.",
                )

            update(20, SystemActions._txt("Configurando repositorio oficial do Docker", "Configuring the official Docker repository"))
            os.makedirs("/etc/apt/keyrings", exist_ok=True)
            key_path = "/etc/apt/keyrings/docker.asc"
            gpg_url = f"https://download.docker.com/linux/{distro_id}/gpg"
            result = subprocess.run(["curl", "-fsSL", gpg_url, "-o", key_path], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao baixar a chave do Docker.",
                    "Failed to download the Docker key.",
                )
            subprocess.run(["chmod", "a+r", key_path], capture_output=True, text=True, check=False)

            arch_result = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True, check=False)
            if arch_result.returncode != 0:
                return False, arch_result.stderr.strip() or arch_result.stdout.strip() or SystemActions._txt(
                    "Falha ao detectar a arquitetura do sistema.",
                    "Failed to detect the system architecture.",
                )
            architecture = arch_result.stdout.strip()
            repo_line = (
                f"deb [arch={architecture} signed-by={key_path}] "
                f"https://download.docker.com/linux/{distro_id} {version_codename} stable\n"
            )
            ok, msg = SystemActions._write_text_file("/etc/apt/sources.list.d/docker.list", repo_line)
            if not ok:
                return False, msg

            update(35, SystemActions._txt("Aplicando configuracao segura do Docker", "Applying safe Docker configuration"))
            os.makedirs("/etc/docker", exist_ok=True)
            ok, msg = SystemActions._merge_json_file(
                "/etc/docker/daemon.json",
                {"ip-forward-no-drop": True},
            )
            if not ok:
                return False, msg

            subprocess.run(["iptables", "-P", "FORWARD", "ACCEPT"], capture_output=True, text=True, check=False)

            update(45, SystemActions._txt("Instalando Docker Engine e Compose", "Installing Docker Engine and Compose"))
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha ao atualizar o repositorio do Docker.",
                    "Failed to refresh the Docker repository.",
                )
            policy_rc_path = "/usr/sbin/policy-rc.d"
            policy_rc_backup_path = f"{policy_rc_path}.vps-tools-panel.bak"
            policy_rc_had_original = os.path.exists(policy_rc_path)
            if policy_rc_had_original:
                try:
                    if os.path.exists(policy_rc_backup_path):
                        os.remove(policy_rc_backup_path)
                    shutil.copy2(policy_rc_path, policy_rc_backup_path)
                except Exception as exc:
                    return False, str(exc)
            ok, msg = SystemActions._write_text_file(policy_rc_path, "#!/bin/sh\nexit 101\n", mode=0o755)
            if not ok:
                return False, msg
            try:
                result = subprocess.run(
                    [
                        "apt-get", "install", "-y",
                        "docker-ce", "docker-ce-cli", "containerd.io",
                        "docker-buildx-plugin", "docker-compose-plugin",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            finally:
                try:
                    if policy_rc_had_original and os.path.exists(policy_rc_backup_path):
                        os.replace(policy_rc_backup_path, policy_rc_path)
                    elif os.path.exists(policy_rc_path):
                        os.remove(policy_rc_path)
                except Exception:
                    pass
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha na instalacao do Docker Engine.",
                    "Docker Engine installation failed.",
                )

            subprocess.run(["iptables", "-P", "FORWARD", "ACCEPT"], capture_output=True, text=True, check=False)

            update(55, SystemActions._txt("Mantendo o Docker parado ate a ativacao manual", "Keeping Docker stopped until manual activation"))
            for cmd in (
                ["systemctl", "disable", "docker"],
                ["systemctl", "disable", "docker.socket"],
                ["systemctl", "stop", "docker"],
                ["systemctl", "stop", "docker.socket"],
            ):
                subprocess.run(cmd, capture_output=True, text=True, check=False)

            subprocess.run(["iptables", "-P", "FORWARD", "ACCEPT"], capture_output=True, text=True, check=False)
            iptables_result = subprocess.run(["iptables", "-S"], capture_output=True, text=True, check=False)

            compose_file = os.path.join(app_dir, "compose.yml")
            nginx_dir = os.path.join(app_dir, "nginx")
            dashboard_dir = os.path.join(app_dir, "dashboard")
            pgadmin_dir = os.path.join(app_dir, "pgadmin")
            redis_dir = os.path.join(app_dir, "redisinsight")
            os.makedirs(nginx_dir, exist_ok=True)
            os.makedirs(dashboard_dir, exist_ok=True)
            if enable_pgadmin:
                os.makedirs(pgadmin_dir, exist_ok=True)
                subprocess.run(["chown", "-R", "5050:5050", pgadmin_dir], capture_output=True, text=True, check=False)
            if enable_redisinsight:
                os.makedirs(redis_dir, exist_ok=True)

            update(70, SystemActions._txt("Gravando arquivos do painel web", "Writing web panel files"))
            compose_content = SystemActions._web_db_panel_compose_content(
                panel_port=panel_port,
                app_dir=app_dir,
                enable_adminer=enable_adminer,
                enable_pgadmin=enable_pgadmin,
                enable_redisinsight=enable_redisinsight,
                pgadmin_email=pgadmin_email,
                pgadmin_password=pgadmin_password,
            )
            ok, msg = SystemActions._write_text_file(compose_file, compose_content)
            if not ok:
                return False, msg

            ok, msg = SystemActions._write_text_file(
                os.path.join(nginx_dir, "default.conf"),
                SystemActions._web_db_panel_nginx_conf(enable_adminer, enable_pgadmin, enable_redisinsight),
            )
            if not ok:
                return False, msg

            ok, msg = SystemActions._write_text_file(
                os.path.join(dashboard_dir, "index.html"),
                SystemActions._web_db_panel_dashboard_html(
                    panel_port=panel_port,
                    enable_adminer=enable_adminer,
                    enable_pgadmin=enable_pgadmin,
                    enable_redisinsight=enable_redisinsight,
                    pgadmin_email=pgadmin_email,
                    pgadmin_password=pgadmin_password,
                ),
            )
            if not ok:
                return False, msg

            update(85, SystemActions._txt("Deixando o painel pronto para ativacao segura", "Leaving the panel ready for safe activation"))
            docker_status = subprocess.run(["systemctl", "status", "docker", "--no-pager"], capture_output=True, text=True, check=False)
            update(100, SystemActions._txt("Painel web de bancos preparado", "Web database panel prepared"))
            return True, {
                "app_dir": app_dir,
                "compose_file": compose_file,
                "panel_port": panel_port,
                "local_url": f"http://127.0.0.1:{panel_port}/",
                "remote_url": f"http://{SystemInfo.get_ip()}:{panel_port}/",
                "pgadmin_email": pgadmin_email if enable_pgadmin else "",
                "pgadmin_password": pgadmin_password if enable_pgadmin else "",
                "enabled_tools": [
                    name
                    for name, enabled in (
                        ("Adminer", enable_adminer),
                        ("pgAdmin 4", enable_pgadmin),
                        ("Redis Insight", enable_redisinsight),
                    )
                    if enabled
                ],
                "compose_status": SystemActions._txt(
                    "Painel preparado. Use GERENCIAR PAINEL WEB DE BANCOS -> Iniciar/atualizar painel quando quiser ativar o Docker.",
                    "Panel prepared. Use MANAGE WEB DATABASE PANEL -> Start/update panel when you want to activate Docker.",
                ),
                "docker_status": (docker_status.stdout or docker_status.stderr or "").strip(),
                "iptables_status": (iptables_result.stdout or iptables_result.stderr or "").strip(),
                "notes": [
                    SystemActions._txt("painel publicado apenas em 127.0.0.1 por padrao", "panel published only on 127.0.0.1 by default"),
                    SystemActions._txt("use host.docker.internal dentro dos paineis para acessar bancos da maquina", "use host.docker.internal inside the tools to access databases on the host machine"),
                    SystemActions._txt("nao abra a porta do painel para toda a internet", "do not expose the panel port to the entire internet"),
                    SystemActions._txt("foi aplicado ip-forward-no-drop=true no Docker para evitar FORWARD DROP automatico", "ip-forward-no-drop=true was applied in Docker to avoid automatic FORWARD DROP"),
                    SystemActions._txt("o Docker foi mantido parado ao final da instalacao para reduzir risco de queda na VPS", "Docker was kept stopped at the end of the installation to reduce VPS outage risk"),
                    SystemActions._txt("ao iniciar o painel, os containers sobem em sequencia para reduzir pico de memoria", "when starting the panel, containers are started sequentially to reduce memory spikes"),
                ],
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def manage_web_db_panel(app_dir: str = "/opt/vps-tools-db-panel", action: str = "status", remove_files: bool = False):
        try:
            compose_file = os.path.join(app_dir, "compose.yml")
            if not os.path.exists(compose_file):
                return False, SystemActions._txt(
                    f"Painel web nao encontrado em {app_dir}.",
                    f"Web panel not found in {app_dir}.",
                )

            if action not in {"start", "stop", "restart", "status", "uninstall"}:
                return False, SystemActions._txt(
                    f"Acao invalida para o painel web: {action}",
                    f"Invalid action for the web panel: {action}",
                )

            if action in {"start", "restart"}:
                ok, msg = SystemActions._merge_json_file(
                    "/etc/docker/daemon.json",
                    {"ip-forward-no-drop": True},
                )
                if not ok:
                    return False, msg
                subprocess.run(["iptables", "-P", "FORWARD", "ACCEPT"], capture_output=True, text=True, check=False)
                for cmd in (
                    ["systemctl", "enable", "docker"],
                    ["systemctl", "enable", "docker.socket"],
                    ["systemctl", "start", "docker"],
                ):
                    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                    if result.returncode != 0:
                        return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                            f"Falha ao executar: {' '.join(cmd)}",
                            f"Failed to execute: {' '.join(cmd)}",
                        )
                subprocess.run(["iptables", "-P", "FORWARD", "ACCEPT"], capture_output=True, text=True, check=False)

            if action == "status":
                docker_state = subprocess.run(["systemctl", "is-active", "docker"], capture_output=True, text=True, check=False)
                if docker_state.returncode != 0 or docker_state.stdout.strip() != "active":
                    status = SystemActions.web_db_panel_status(app_dir=app_dir)
                    output = SystemActions._txt(
                        "Painel preparado, mas o Docker esta parado.\nUse a opcao 1 para iniciar o painel com seguranca.",
                        "Panel is prepared, but Docker is stopped.\nUse option 1 to start the panel safely.",
                    )
                    if status.get("panel_port"):
                        output += f"\n\nPorta local: {status['panel_port']}"
                    return True, output
                result = SystemActions._docker_compose_run(compose_file, ["ps"], capture_output=True, text=True)
            elif action == "start":
                stale_result = SystemActions._docker_compose_run(compose_file, ["down", "--remove-orphans"], capture_output=True, text=True)
                if stale_result is None:
                    return False, SystemActions._txt(
                        "Docker Compose nao encontrado.",
                        "Docker Compose not found.",
                    )
                for service in SystemActions._web_db_panel_service_order(compose_file):
                    result = SystemActions._docker_compose_run(
                        compose_file,
                        ["up", "-d", "--force-recreate", "--no-deps", service],
                        capture_output=True,
                        text=True,
                    )
                    if result is None:
                        return False, SystemActions._txt(
                            "Docker Compose nao encontrado.",
                            "Docker Compose not found.",
                        )
                    if result.returncode != 0:
                        return False, (result.stderr or result.stdout or "").strip() or SystemActions._txt(
                            f"Falha ao iniciar o servico {service} do painel.",
                            f"Failed to start panel service {service}.",
                        )
                result = SystemActions._docker_compose_run(compose_file, ["ps"], capture_output=True, text=True)
            elif action == "stop":
                SystemActions._web_db_panel_disable_restart_policy(compose_file)
                result = SystemActions._docker_compose_run(compose_file, ["stop"], capture_output=True, text=True)
            elif action == "restart":
                SystemActions._web_db_panel_disable_restart_policy(compose_file)
                stop_result = SystemActions._docker_compose_run(compose_file, ["stop"], capture_output=True, text=True)
                if stop_result is None:
                    return False, SystemActions._txt(
                        "Docker Compose nao encontrado.",
                        "Docker Compose not found.",
                    )
                if stop_result.returncode != 0:
                    return False, (stop_result.stderr or stop_result.stdout or "").strip() or SystemActions._txt(
                        "Falha ao parar o painel antes do restart.",
                        "Failed to stop the panel before restart.",
                    )
                stale_result = SystemActions._docker_compose_run(compose_file, ["down", "--remove-orphans"], capture_output=True, text=True)
                if stale_result is None:
                    return False, SystemActions._txt(
                        "Docker Compose nao encontrado.",
                        "Docker Compose not found.",
                    )
                for service in SystemActions._web_db_panel_service_order(compose_file):
                    result = SystemActions._docker_compose_run(
                        compose_file,
                        ["up", "-d", "--force-recreate", "--no-deps", service],
                        capture_output=True,
                        text=True,
                    )
                    if result is None:
                        return False, SystemActions._txt(
                            "Docker Compose nao encontrado.",
                            "Docker Compose not found.",
                        )
                    if result.returncode != 0:
                        return False, (result.stderr or result.stdout or "").strip() or SystemActions._txt(
                            f"Falha ao reiniciar o servico {service} do painel.",
                            f"Failed to restart panel service {service}.",
                        )
                result = SystemActions._docker_compose_run(compose_file, ["ps"], capture_output=True, text=True)
            else:
                SystemActions._web_db_panel_disable_restart_policy(compose_file)
                result = SystemActions._docker_compose_run(compose_file, ["down"], capture_output=True, text=True)
                if result is not None and result.returncode == 0 and remove_files and os.path.isdir(app_dir):
                    shutil.rmtree(app_dir, ignore_errors=True)

            if result is None:
                return False, SystemActions._txt(
                    "Docker Compose nao encontrado.",
                    "Docker Compose not found.",
                )

            output = (result.stdout or result.stderr or "").strip()
            ok = result.returncode == 0
            return ok, output or SystemActions._txt("Acao concluida.", "Action completed.")
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def publish_web_db_panel_via_nginx(
        app_dir: str = "/opt/vps-tools-db-panel",
        site_name: str = "db-panel",
        server_names: list[str] | None = None,
        publish_target: str = "domain",
        ip_host: str = "",
        auth_user: str = "admin",
        auth_password: str = "",
        progress_callback=None,
    ):
        def update(percent: int, text: str):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            ok, msg = SystemActions._validate_service_name(site_name)
            if not ok:
                return False, msg
            publish_target = (publish_target or "domain").strip().lower()
            server_names = [item.strip() for item in (server_names or []) if item.strip()]
            if publish_target not in {"domain", "ip"}:
                return False, SystemActions._txt(
                    "Modo de publicacao invalido para o painel.",
                    "Invalid panel publishing mode.",
                )
            if publish_target == "domain" and not server_names:
                return False, SystemActions._txt(
                    "Informe ao menos um dominio/server_name para o painel.",
                    "Provide at least one domain/server_name for the panel.",
                )
            if not auth_user.strip():
                return False, SystemActions._txt(
                    "Usuario do painel nao pode ser vazio.",
                    "Panel username cannot be empty.",
                )
            if not auth_password:
                auth_password = SystemActions._random_secret(18)

            status = SystemActions.web_db_panel_status(app_dir=app_dir)
            if not status.get("installed") or not status.get("panel_port"):
                return False, SystemActions._txt(
                    "Painel web nao instalado ou sem porta detectada.",
                    "Web panel is not installed or has no detected port.",
                )
            panel_port = int(status["panel_port"])
            if publish_target == "ip":
                publish_host = (ip_host or "").strip() or SystemInfo.get_ip()
                if not publish_host or publish_host.lower() == "unknown":
                    return False, SystemActions._txt(
                        "Nao foi possivel detectar o IP publico do painel. Informe o IP manualmente.",
                        "Could not detect the panel public IP. Provide the IP manually.",
                    )
                server_name_line = publish_host
                published_url = f"http://{publish_host}/"
            else:
                server_name_line = " ".join(server_names)
                published_url = f"http://{server_names[0]}/"

            update(10, SystemActions._txt("Instalando Nginx e OpenSSL", "Installing Nginx and OpenSSL"))
            result = subprocess.run(["apt-get", "update", "-y"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha no apt-get update.",
                    "apt-get update failed.",
                )
            result = subprocess.run(["apt-get", "install", "-y", "nginx", "openssl"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha na instalacao do Nginx/OpenSSL.",
                    "Nginx/OpenSSL installation failed.",
                )

            update(35, SystemActions._txt("Gerando arquivo de autenticacao", "Generating authentication file"))
            ok, hashed = SystemActions._openssl_apr1_hash(auth_password)
            if not ok:
                return False, hashed
            htpasswd_path = f"/etc/nginx/.htpasswd-{site_name}"
            ok, msg = SystemActions._write_text_file(htpasswd_path, f"{auth_user}:{hashed}\n", mode=0o640)
            if not ok:
                return False, msg
            nginx_group = "www-data" if shutil.which("getent") else ""
            if nginx_group:
                getent_result = subprocess.run(
                    ["getent", "group", nginx_group],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if getent_result.returncode == 0:
                    subprocess.run(["chown", f"root:{nginx_group}", htpasswd_path], capture_output=True, text=True, check=False)
                    subprocess.run(["chmod", "640", htpasswd_path], capture_output=True, text=True, check=False)
                else:
                    subprocess.run(["chmod", "644", htpasswd_path], capture_output=True, text=True, check=False)
            else:
                subprocess.run(["chmod", "644", htpasswd_path], capture_output=True, text=True, check=False)

            conf_content = (
                "server {\n"
                "    listen 80;\n"
                "    listen [::]:80;\n"
                f"    server_name {server_name_line};\n"
                "\n"
                '    auth_basic "Restricted Area";\n'
                f"    auth_basic_user_file {htpasswd_path};\n"
                "\n"
                "    location / {\n"
                f"        proxy_pass http://127.0.0.1:{panel_port}/;\n"
                "        proxy_http_version 1.1;\n"
                "        proxy_set_header Host $host;\n"
                "        proxy_set_header Upgrade $http_upgrade;\n"
                '        proxy_set_header Connection "upgrade";\n'
                "        proxy_set_header X-Real-IP $remote_addr;\n"
                "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
                "        proxy_set_header X-Forwarded-Proto $scheme;\n"
                "    }\n"
                "}\n"
            )

            update(60, SystemActions._txt("Gravando virtual host do painel", "Writing panel virtual host"))
            available = f"/etc/nginx/sites-available/{site_name}"
            enabled = f"/etc/nginx/sites-enabled/{site_name}"
            ok, msg = SystemActions._write_text_file(available, conf_content)
            if not ok:
                return False, msg
            if not os.path.exists(enabled):
                os.symlink(available, enabled)

            update(80, SystemActions._txt("Validando e reiniciando Nginx", "Validating and restarting Nginx"))
            result = subprocess.run(["nginx", "-t"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                    "Falha no nginx -t.",
                    "nginx -t failed.",
                )
            for cmd in (["systemctl", "enable", "nginx"], ["systemctl", "restart", "nginx"]):
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    return False, result.stderr.strip() or result.stdout.strip() or SystemActions._txt(
                        f"Falha ao executar: {' '.join(cmd)}",
                        f"Failed to execute: {' '.join(cmd)}",
                    )

            status_result = subprocess.run(["systemctl", "status", "nginx", "--no-pager"], capture_output=True, text=True, check=False)
            update(100, SystemActions._txt("Painel publicado via Nginx", "Panel published via Nginx"))
            return True, {
                "site_name": site_name,
                "server_names": server_name_line,
                "publish_target": publish_target,
                "config_file": available,
                "htpasswd_file": htpasswd_path,
                "auth_user": auth_user,
                "auth_password": auth_password,
                "published_url": published_url,
                "panel_port": panel_port,
                "nginx_status": (status_result.stdout or status_result.stderr or "").strip(),
            }
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def secure_web_db_panel_https(
        domains: list[str],
        email: str,
        redirect_https: bool = True,
        progress_callback=None,
    ):
        return SystemActions.setup_certbot_https(
            domains=domains,
            email=email,
            redirect_https=redirect_https,
            progress_callback=progress_callback,
        )

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
            return False, SystemActions._txt("Git nao encontrado no sistema.", "Git not found on the system.")
        if not os.path.isdir(repo_dir):
            return False, SystemActions._txt(
                f"Diretorio do repositorio nao encontrado: {repo_dir}",
                f"Repository directory not found: {repo_dir}",
            )

        result = subprocess.run(
            ['git', '-C', repo_dir, 'rev-parse', '--is-inside-work-tree'],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False, SystemActions._txt(
                "Diretorio informado nao e um repositorio git.",
                "The provided directory is not a git repository.",
            )

        fetch = subprocess.run(
            ['git', '-C', repo_dir, 'fetch', '--all'],
            capture_output=True,
            text=True,
            check=False,
        )
        if fetch.returncode != 0:
            return False, fetch.stderr.strip() or SystemActions._txt("Falha no git fetch.", "git fetch failed.")

        pull = subprocess.run(
            ['git', '-C', repo_dir, 'pull', '--ff-only'],
            capture_output=True,
            text=True,
            check=False,
        )
        if pull.returncode != 0:
            return False, pull.stderr.strip() or SystemActions._txt("Falha no git pull.", "git pull failed.")
        message = (pull.stdout or "").strip() or SystemActions._txt(
            "Script atualizado com sucesso.",
            "Script updated successfully.",
        )
        return True, message

    @staticmethod
    def create_menu_command(repo_dir: str, command_name: str = 'menu'):
        if os.name == 'nt':
            return False, SystemActions._txt(
                "Comando global automatico nao suportado no Windows.",
                "Automatic global command creation is not supported on Windows.",
            )
        if not os.path.isdir(repo_dir):
            return False, SystemActions._txt(
                f"Diretorio do repositorio nao encontrado: {repo_dir}",
                f"Repository directory not found: {repo_dir}",
            )
        if not re.match(r'^[a-zA-Z0-9._-]+$', command_name):
            return False, SystemActions._txt(
                "Nome de comando invalido. Use apenas letras, numeros, ponto, _ ou -.",
                "Invalid command name. Use only letters, numbers, dot, _ or -.",
            )

        current = shutil.which(command_name)
        target = f"/usr/local/bin/{command_name}"
        if current and current != target:
            return False, SystemActions._txt(
                f"O comando '{command_name}' ja existe em {current}.",
                f"The command '{command_name}' already exists at {current}.",
            )

        launcher = (
            "#!/usr/bin/env bash\n"
            "set -e\n"
            f'REPO_DIR="{repo_dir}"\n'
            'cd "$REPO_DIR"\n'
            'export PYTHONPATH="$REPO_DIR${PYTHONPATH:+:$PYTHONPATH}"\n'
            'if [ -x "$REPO_DIR/.venv/bin/python" ]; then\n'
            '  exec "$REPO_DIR/.venv/bin/python" -m vps_tools.main "$@"\n'
            "fi\n"
            'if [ -x "$REPO_DIR/venv/bin/python" ]; then\n'
            '  exec "$REPO_DIR/venv/bin/python" -m vps_tools.main "$@"\n'
            "fi\n"
            'exec python3 -m vps_tools.main "$@"\n'
        )
        try:
            with open(target, 'w') as f:
                f.write(launcher)
            os.chmod(target, 0o755)
            return True, SystemActions._txt(
                f"Comando '{command_name}' criado em {target}",
                f"Command '{command_name}' created at {target}",
            )
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def create_swap(size_mb: int = 1024, swap_path: str = "/swapfile"):
        if os.name == "nt":
            return False, SystemActions._txt("Criacao de swap nao suportada no Windows.", "Swap creation is not supported on Windows.")
        if size_mb < 256:
            return False, SystemActions._txt("Tamanho minimo recomendado: 256 MB.", "Recommended minimum size: 256 MB.")
        if shutil.which("mkswap") is None or shutil.which("swapon") is None:
            return False, SystemActions._txt(
                "Ferramentas de swap nao encontradas (mkswap/swapon).",
                "Swap tools not found (mkswap/swapon).",
            )

        try:
            with open("/proc/swaps", "r") as f:
                lines = [line for line in f.read().splitlines() if line.strip()]
            if len(lines) > 1:
                return False, SystemActions._txt("Ja existe swap ativo no sistema.", "There is already active swap on the system.")
        except Exception:
            pass

        if os.path.exists(swap_path):
            return False, SystemActions._txt(
                f"Arquivo de swap ja existe: {swap_path}",
                f"Swap file already exists: {swap_path}",
            )

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
                return False, SystemActions._txt("Falha ao criar arquivo de swap.", "Failed to create swap file.")

        chmod_result = subprocess.run(["chmod", "600", swap_path], check=False)
        if chmod_result.returncode != 0:
            return False, SystemActions._txt("Falha ao ajustar permissoes do swapfile.", "Failed to adjust swapfile permissions.")

        mk_result = subprocess.run(["mkswap", swap_path], check=False)
        if mk_result.returncode != 0:
            return False, SystemActions._txt("Falha ao formatar swapfile com mkswap.", "Failed to format the swapfile with mkswap.")

        on_result = subprocess.run(["swapon", swap_path], check=False)
        if on_result.returncode != 0:
            return False, SystemActions._txt("Falha ao ativar swap com swapon.", "Failed to enable swap with swapon.")

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
                return False, SystemActions._txt(
                    f"Swap criado, mas falhou ao persistir no fstab: {exc}",
                    f"Swap created, but failed to persist it in fstab: {exc}",
                )

        return True, SystemActions._txt(
            f"Swap de {size_mb} MB criado e ativado em {swap_path}.",
            f"Swap of {size_mb} MB created and enabled at {swap_path}.",
        )

    @staticmethod
    def measure_server_speed(progress_callback=None):
        def update(percent, text):
            if progress_callback:
                progress_callback(completed=percent, description=f"[cyan]{text}[/cyan]")

        try:
            # Ping (TCP connect latency approximation)
            update(5, SystemActions._txt("Medindo latencia", "Measuring latency"))
            latencies = []
            for _ in range(3):
                start = time.perf_counter()
                sock = socket.create_connection(("1.1.1.1", 443), timeout=3)
                sock.close()
                latencies.append((time.perf_counter() - start) * 1000)
            ping_ms = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

            # Download test
            update(20, SystemActions._txt("Testando download", "Testing download"))
            total_read = 0
            target_bytes = 5 * 1024 * 1024  # 5 MB for faster test
            download_urls = [
                "https://proof.ovh.net/files/10Mb.dat",
                "https://ash-speed.hetzner.com/10MB.bin",
                "https://raw.githubusercontent.com/github/gitignore/main/Python.gitignore",
            ]
            start = time.perf_counter()
            last_download_error = SystemActions._txt(
                "Falha em todas as fontes de download.",
                "All download sources failed.",
            )
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
                            update(
                                20 + int(ratio * 45),
                                SystemActions._txt(
                                    f"Testando download ({download_url})",
                                    f"Testing download ({download_url})",
                                ),
                            )
                            if total_read >= target_bytes:
                                break
                    if total_read > 0:
                        break
                except Exception as exc:
                    last_download_error = str(exc)
                    continue
            if total_read <= 0:
                return False, SystemActions._txt(
                    f"Falha no download: {last_download_error}",
                    f"Download failed: {last_download_error}",
                )
            download_seconds = max(time.perf_counter() - start, 0.001)
            download_mbps = round((total_read * 8) / (download_seconds * 1_000_000), 2)

            # Upload test
            update(70, SystemActions._txt("Testando upload", "Testing upload"))
            payload = os.urandom(2 * 1024 * 1024)  # 2 MB
            upload_urls = [
                "https://httpbin.org/post",
                "https://eu.httpbin.org/post",
                "https://postman-echo.com/post",
            ]
            start = time.perf_counter()
            last_upload_error = SystemActions._txt(
                "Falha em todas as fontes de upload.",
                "All upload sources failed.",
            )
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
                return False, SystemActions._txt(
                    f"Falha no upload: {last_upload_error}",
                    f"Upload failed: {last_upload_error}",
                )
            upload_seconds = max(time.perf_counter() - start, 0.001)
            upload_mbps = round((len(payload) * 8) / (upload_seconds * 1_000_000), 2)
            update(95, SystemActions._txt("Finalizando", "Finishing"))

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
            return False, SystemActions._txt("Gerenciador de pacotes nao suportado.", "Unsupported package manager.")

        try:
            if browser == "firefox":
                if manager == "apt":
                    subprocess.run(["apt-get", "update", "-y"], check=True)
                    subprocess.run(["apt-get", "install", "-y", "firefox"], check=True)
                else:
                    subprocess.run(["yum", "-y", "install", "firefox"], check=True)
                return True, SystemActions._txt("Firefox instalado com sucesso.", "Firefox installed successfully.")

            if browser == "chromium":
                if manager == "apt":
                    subprocess.run(["apt-get", "update", "-y"], check=True)
                    subprocess.run(["apt-get", "install", "-y", "chromium-browser"], check=False)
                    # fallback para distros que usam pacote chromium
                    if shutil.which("chromium-browser") is None:
                        subprocess.run(["apt-get", "install", "-y", "chromium"], check=True)
                else:
                    subprocess.run(["yum", "-y", "install", "chromium"], check=True)
                return True, SystemActions._txt("Chromium instalado com sucesso.", "Chromium installed successfully.")

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
                    return False, SystemActions._txt(
                        "Brave automatico suportado apenas em Debian/Ubuntu.",
                        "Automatic Brave installation is supported only on Debian/Ubuntu.",
                    )
                return True, SystemActions._txt("Brave instalado com sucesso.", "Brave installed successfully.")

            return False, SystemActions._txt(
                f"Navegador desconhecido: {browser}",
                f"Unknown browser: {browser}",
            )
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
            return False, SystemActions._txt(
                "Navegador invalido para definir padrao.",
                "Invalid browser for default selection.",
            )

        # Para servidor sem sessão desktop ativa, tentamos update-alternatives.
        if shutil.which("xdg-settings"):
            result = subprocess.run(
                ["xdg-settings", "set", "default-web-browser", desktop],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return True, SystemActions._txt(
                    f"Navegador padrao definido: {browser}",
                    f"Default browser set: {browser}",
                )

        if shutil.which("update-alternatives"):
            binary = "firefox" if browser == "firefox" else ("chromium-browser" if browser == "chromium" else "brave-browser")
            result = subprocess.run(
                ["update-alternatives", "--set", "x-www-browser", f"/usr/bin/{binary}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return True, SystemActions._txt(
                    f"Navegador padrao definido: {browser}",
                    f"Default browser set: {browser}",
                )

        return False, SystemActions._txt(
            "Nao foi possivel definir navegador padrao automaticamente.",
            "Could not set the default browser automatically.",
        )
