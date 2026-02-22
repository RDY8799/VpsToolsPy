#!/bin/bash

# VPS Tools Python Version Installer
# Detect OS
if [[ -e /etc/debian_version ]]; then
    OS=debian
    apt-get update -y
    apt-get install -y python3 python3-pip python3-venv git
elif [[ -e /etc/centos-release || -e /etc/redhat-release ]]; then
    OS=centos
    yum -y update
    yum install -y python3 python3-pip git
else
    echo "OS not supported"
    exit 1
fi

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Create a symlink to run the tool easily
echo "#!/bin/bash
source $(pwd)/venv/bin/activate
export PYTHONPATH=$(pwd)
python3 $(pwd)/vps_tools/main.py "\$@"" > vps-tools
chmod +x vps-tools
mv vps-tools /usr/local/bin/

echo "Installation complete! Type 'vps-tools' to start the script."
