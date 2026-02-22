import os
import socket
import subprocess

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
