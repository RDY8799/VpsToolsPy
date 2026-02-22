import os
import subprocess

from vps_tools.core.system import SystemActions


class BannerManager:
    @staticmethod
    def set_banner(text, append=False):
        banner_path = "/etc/rdy/banner"
        os.makedirs("/etc/rdy", exist_ok=True)

        mode = "a" if append else "w"
        with open(banner_path, mode) as f:
            f.write(f"\n{text}\n")

        # Configure SSH to use this banner
        sshd_config = "/etc/ssh/sshd_config"
        with open(sshd_config, "r") as f:
            lines = f.readlines()

        with open(sshd_config, "w") as f:
            for line in lines:
                if not line.strip().startswith("Banner"):
                    f.write(line)
            f.write(f"\nBanner {banner_path}\n")

        SystemActions.restart_service_with_fallback("sshd", "ssh")
        return True

    @staticmethod
    def get_banner():
        banner_path = "/etc/rdy/banner"
        if os.path.exists(banner_path):
            with open(banner_path, "r") as f:
                return f.read()
        return "Nenhum banner configurado."


class HostManager:
    @staticmethod
    def add_host(host):
        path = "/etc/rdy/payloads"
        os.makedirs("/etc/rdy", exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write("")

        with open(path, "a") as f:
            f.write(f"{host}\n")

        # Reload Squid if installed
        subprocess.run(["squid", "-k", "reconfigure"], check=False)
        return True

    @staticmethod
    def remove_host(host):
        path = "/etc/rdy/payloads"
        if not os.path.exists(path):
            return False

        with open(path, "r") as f:
            lines = f.readlines()

        with open(path, "w") as f:
            for line in lines:
                if line.strip() != host:
                    f.write(line)

        subprocess.run(["squid", "-k", "reconfigure"], check=False)
        return True

    @staticmethod
    def list_hosts():
        path = "/etc/rdy/payloads"
        if os.path.exists(path):
            with open(path, "r") as f:
                return [line.strip() for line in f.readlines() if line.strip()]
        return []
