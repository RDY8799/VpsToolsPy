import os

from vps_tools.core.services import Service


class DomainAuditService(Service):
    def __init__(self, repo_dir: str):
        super().__init__("Domain Audit", "domain-audit")
        self.script_path = os.path.join(repo_dir, "domain_audit.py")

    def is_installed(self) -> bool:
        return os.path.exists(self.script_path)

    def is_running(self) -> bool:
        return False

    def start(self) -> bool:
        return True

    def stop(self) -> bool:
        return True

    def restart(self) -> bool:
        return True

    def uninstall(self):
        return "Domain Audit e um modulo de execucao e nao deve ser desinstalado por aqui."

    def install(self):
        return True
