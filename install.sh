#!/usr/bin/env bash

# https://docs.docker.com/engine/install/ubuntu/
sudo apt update && apt dist-upgrade -y && sudo apt install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release && apt autoremove --purge -y apache2 nginx

curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

echo \
  "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose

# create shared volume data directory for containers
mkdir -p /srv/data/nginx \
      && mkdir -p /etc/letsencrypt/ \
      && touch /srv/data/nginx/nginx.conf \
      && chmod -R 1000 /srv/data/ \
      && chmod -R 1000 /etc/letsencrypt/

# example: ./install.sh '["mydomain.com"]' 'wss://mydomain.com/websocket/vps/' '123example456'

printf "UPSTREAMS=$1\nCONNECT_URL=$2\nCONNECT_TOKEN=$3" > .env

docker-compose up -d --build