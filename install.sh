#!/usr/bin/env bash
export LANG=en_US.UTF-8

sudo apt update && apt install -y git python3.8 python3.8-dev python3.8-venv && apt autoremove --purge -y apache2 && apt dist-upgrade -y

sudo locale-gen en_US.UTF-8
#sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 2
#sudo python3.8 -m easy_install pip
sudo apt install -y nginx letsencrypt redis-server && pipenv install --deploy --system

mkdir -p /etc/nginx-agent/

cp -rf dns_acme_auth.py /etc/nginx-agent/
cp -rf dns_acme_clean.py /etc/nginx-agent/
cp -rf dns_acme_deploy.py /etc/nginx-agent/