#!/usr/bin/env bash
sudo apt update && apt dist-upgrade -y

sudo apt install -y nginx letsencrypt python3-pip pipenv redis-server && pipenv install --deploy --system

mkdir -p /etc/nginx-agent/

cp -rf dns_acme_auth.py /etc/nginx-agent/
cp -rf dns_acme_clean.py /etc/nginx-agent/
cp -rf dns_acme_deploy.py /etc/nginx-agent/