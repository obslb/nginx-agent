#!/usr/bin/env python3
import os
import subprocess
import sys
import time

WORK_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_DIR = os.path.join(WORK_DIR, 'agent')
if not os.path.exists(BASE_DIR):
    raise Exception('Error, we could not find path with gateway: {0}!!'.format(BASE_DIR))
sys.path.append(BASE_DIR)

DOMAIN = None
if os.environ.get("RENEWED_DOMAINS"):
    DOMAIN = os.environ["RENEWED_DOMAINS"].split(" ")[0]

DEFAULT_LETSENCRYPT_WORK_DIR = "/etc/letsencrypt/"
DEFAULT_NGINX_WORK_DIR = "/etc/nginx/"


def reload_nginx():
    time.sleep(2)
    try:
        subprocess.check_output(f"sudo /usr/sbin/nginx -s reload", stderr=subprocess.STDOUT, shell=True)
    except Exception as exc:
        print("Nginx Reload: " + str(exc))


def main():
    template = """
    server {{
            listen 80;
            server_name {domain} *.{domain};
            access_log on;
            access_log  /var/log/nginx/{domain}.log main;
            error_log  /var/log/nginx/{domain}.log;
            return 301 https://$host$request_uri;
    }}
    server {{
            listen 443 ssl http2;
            server_name {domain};
            rewrite ^(.*) http://www.{domain}$1 permanent;
            ssl_certificate {ssl_certificate};
            ssl_certificate_key {ssl_certificate_key};
            include /etc/nginx/common/restricted.conf;
    }}
    server {{
            listen 443 ssl http2;
            server_name *.{domain};
            ssl_certificate {ssl_certificate};
            ssl_certificate_key {ssl_certificate_key};
            include /etc/nginx/common/restricted.conf;
    }}
    """

    # this mean we obtain ssl key pair
    ssl_certificate = os.path.join(DEFAULT_LETSENCRYPT_WORK_DIR, "live", DOMAIN, "fullchain.pem")
    if not os.path.isfile(ssl_certificate):
        raise ValueError(f"certificate:  {ssl_certificate} not exists for {DOMAIN}")

    ssl_certificate_key = os.path.join(DEFAULT_LETSENCRYPT_WORK_DIR, "live", DOMAIN, "privkey.pem")
    if not os.path.isfile(ssl_certificate_key):
        raise ValueError(f"certificate key: {ssl_certificate_key} not exists for {DOMAIN}")
    config_path = os.path.join(DEFAULT_NGINX_WORK_DIR, "conf.d", DOMAIN + '.conf')

    text = template.format(
        domain=DOMAIN,
        ssl_certificate=ssl_certificate,
        ssl_certificate_key=ssl_certificate_key,
    )
    with open(config_path, 'w') as f:
        f.write(text)
    # reload nginx for new configs
    reload_nginx()
    print("Congratulations! Your certificate and chain have been saved at")


if __name__ == "__main__":
    main()
