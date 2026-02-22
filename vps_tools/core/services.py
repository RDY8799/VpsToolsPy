import subprocess


class Service:
    def __init__(self, name: str, system_service_name: str):
        self.name = name
        self.system_service_name = system_service_name

    def is_installed(self) -> bool:
        # Generic installation check using dpkg or yum
        try:
            # Check for binary instead of package to be more robust
            return subprocess.run(['which', self.system_service_name], capture_output=True).returncode == 0
        except:
            return False

    def is_running(self) -> bool:
        try:
            result = subprocess.run(['systemctl', 'is-active', self.system_service_name], capture_output=True,
                                    text=True)
            return result.stdout.strip() == 'active'
        except Exception:
            try:
                result = subprocess.run(
                    ['service', self.system_service_name, 'status'],
                    capture_output=True,
                    text=True,
                )
                return result.returncode == 0
            except Exception:
                return False

    def _service_action(self, action: str) -> bool:
        try:
            subprocess.run(['systemctl', action, self.system_service_name], check=True)
            return True
        except Exception:
            try:
                subprocess.run(['service', self.system_service_name, action], check=True)
                return True
            except Exception:
                return False

    def start(self) -> bool:
        return self._service_action('start')

    def stop(self) -> bool:
        return self._service_action('stop')

    def restart(self) -> bool:
        return self._service_action('restart')

    def uninstall(self) -> bool:
        raise NotImplementedError("Uninstall must be implemented by subclasses")

    def install(self) -> bool:
        raise NotImplementedError("Install must be implemented by subclasses")

    def get_ports(self) -> list:
        # Should be implemented by subclasses to parse config and find ports
        return []

    def set_port(self, port: int) -> bool:
        # Should be implemented by subclasses
        return False
