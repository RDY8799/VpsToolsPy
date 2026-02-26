import os
import shutil
import subprocess
from typing import List, Tuple


class CompleteUninstaller:
    def __init__(self):
        self.results: List[Tuple[str, bool, str]] = []

    def _run(self, cmd):
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        ok = result.returncode == 0
        msg = result.stderr.strip() if result.stderr else result.stdout.strip()
        self.results.append((" ".join(cmd), ok, msg))
        return ok

    @staticmethod
    def _package_manager() -> str:
        if os.path.exists('/usr/bin/apt-get') or os.path.exists('/bin/apt-get'):
            return 'apt'
        if os.path.exists('/usr/bin/yum') or os.path.exists('/bin/yum'):
            return 'yum'
        return ''

    def _stop_and_disable_services(self):
        services = [
            'squid',
            'squid3',
            'sslh',
            'stunnel4',
            'dropbear',
            'trojan',
            'badvpn-udpgw',
            'vps-tools-vnc',
            'openclaw',
            'openclawd',
        ]
        for service in services:
            self._run(['systemctl', 'stop', service])
            self._run(['systemctl', 'disable', service])
            self._run(['service', service, 'stop'])

    def _remove_packages(self):
        manager = self._package_manager()
        if manager == 'apt':
            self._run(
                [
                    'apt-get',
                    'remove',
                    '--purge',
                    '-y',
                    'squid',
                    'squid3',
                    'sslh',
                    'stunnel4',
                    'stunnel',
                    'dropbear',
                    'trojan',
                    'x11vnc',
                ]
            )
            self._run(['apt-get', 'autoremove', '-y'])
            self._run(['apt-get', 'autoclean', '-y'])
        elif manager == 'yum':
            self._run(
                ['yum', 'remove', '-y', 'squid', 'squid3', 'sslh', 'stunnel4', 'stunnel', 'dropbear', 'trojan', 'x11vnc']
            )
            self._run(['yum', 'autoremove', '-y'])

    def _remove_files(self):
        paths = [
            '/etc/rdy',
            '/etc/default/dropbear',
            '/etc/default/sslh',
            '/etc/default/stunnel4',
            '/etc/stunnel/stunnel.conf',
            '/etc/stunnel/stunnel.pem',
            '/etc/systemd/system/badvpn-udpgw.service',
            '/etc/systemd/system/vps-tools-vnc.service',
            '/usr/bin/badvpn-udpgw',
            '/etc/vps-tools',
            '/usr/local/bin/openclaw',
            '/usr/bin/openclaw',
            '/opt/openclaw',
            '/etc/openclaw',
            '/var/lib/openclaw',
            '/var/log/openclaw',
            '/etc/trojan',
        ]
        for path in paths:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                    self.results.append((f"rm -rf {path}", True, ""))
                elif os.path.exists(path):
                    os.remove(path)
                    self.results.append((f"rm {path}", True, ""))
            except Exception as exc:
                self.results.append((f"remove {path}", False, str(exc)))

        self._run(['systemctl', 'daemon-reload'])

    def run(self):
        self._stop_and_disable_services()
        self._remove_packages()
        self._remove_files()
        return self.results

    @staticmethod
    def summarize(results: List[Tuple[str, bool, str]]) -> str:
        total = len(results)
        ok = sum(1 for _, status, _ in results if status)
        failed = total - ok
        return f"Desinstalacao completa finalizada: {ok} sucesso(s), {failed} falha(s)."
