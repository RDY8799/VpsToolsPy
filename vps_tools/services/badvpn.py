import os
import subprocess

from vps_tools.core.services import Service


class BadVPNService(Service):
    def __init__(self):
        super().__init__("BadVPN UDPGW", "badvpn-udpgw")

    def install(self, port=7300):
        try:
            if os.path.exists('/etc/debian_version'):
                subprocess.run(['apt-get', 'update', '-y'], check=True)
                subprocess.run(['apt-get', 'install', '-y', 'cmake', 'make', 'gcc'], check=True)

            # Download and compile (Simplified for this example, usually a binary is better)
            # In many VPS scripts, they download a pre-compiled binary
            binary_url = "https://raw.githubusercontent.com/RDY8799/VPS-tools/main/badvpn-udpgw"  # Hypothetical URL
            subprocess.run(['wget', '-O', '/usr/bin/badvpn-udpgw', binary_url], check=False)
            subprocess.run(['chmod', '+x', '/usr/bin/badvpn-udpgw'], check=True)

            # Create systemd service
            unit_file = f"""[Unit]
Description=BadVPN UDP Gateway
After=network.target

[Service]
ExecStart=/usr/bin/badvpn-udpgw --listen-addr 127.0.0.1:{port} --max-clients 1000 --max-connections-for-client 10
Restart=always

[Install]
WantedBy=multi-user.target
"""
            with open('/etc/systemd/system/badvpn-udpgw.service', 'w') as f:
                f.write(unit_file)

            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            subprocess.run(['systemctl', 'enable', 'badvpn-udpgw'], check=True)
            subprocess.run(['systemctl', 'start', 'badvpn-udpgw'], check=True)
            return True
        except Exception as e:
            return str(e)

    def uninstall(self):
        try:
            subprocess.run(['systemctl', 'stop', 'badvpn-udpgw'], check=True)
            subprocess.run(['systemctl', 'disable', 'badvpn-udpgw'], check=True)
            if os.path.exists('/etc/systemd/system/badvpn-udpgw.service'):
                os.remove('/etc/systemd/system/badvpn-udpgw.service')
            return True
        except Exception as e:
            return str(e)
