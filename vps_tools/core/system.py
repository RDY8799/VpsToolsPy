import os
import re
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
