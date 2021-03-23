import argparse
import logging.handlers
import os
import subprocess
import sys

logger = logging.getLogger('agent')

DEFAULT_NGINX_PATH = '/etc/nginx/'


class CommonArguments:

    def __call__(self, parser: argparse.ArgumentParser, *args, **kwargs):
        parser.add_argument(
            '--nginx-path',
            default=DEFAULT_NGINX_PATH,
            help='',
        )
        parser.add_argument(
            '--letsencrypt-path',
            help='',
        )
        parser.add_argument(
            '--config-path',
            help='',
        )
        parser.add_argument(
            '-d',
            '--debug',
            action="store_true",
            default=False,
            help='set debug, default:False, true are not recommended for production, this can leak private data.'
        )
        parser.add_argument(
            '--connect_url',
            required=False,
            help='',
        )
        parser.add_argument(
            '--connect_token',
            required=False,
            help='',
        )
        parser.add_argument(
            '-u',
            '--upstream',
            required=False,
            help='',
        )


class InstallArguments:
    def __call__(self, parser: argparse.ArgumentParser, *args, **kwargs):
        parser.add_argument(
            '--reconfigure',
            action="store_true",
            default=False,
            help='',
        )


class BaseService:
    @staticmethod
    def _write(path: str, text: str):
        with open(path, 'w') as f:
            f.write(text)


class SystemService(BaseService):
    service_name = "nginx-agent.service"

    def __init__(self,
                 systemd_path='/etc/systemd/system/', reconfigure=False):
        self.systemd_path = systemd_path
        self.reconfigure = reconfigure

    def check(self, **kwargs):
        path = os.path.join(self.systemd_path, self.service_name)
        if not os.path.exists(path) or self.reconfigure:
            template = f"""
[Unit]
Description=Nginx Remote Agent
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
Restart=always
RestartSec=5
User=root
Group=root
WorkingDirectory=/srv/
ExecStart=/usr/bin/python3 ./src/manage.py runserver 0.0.0.0:8000

[Install]
WantedBy=multi-user.target
        """
            self._write(path, template)


class NginxService(BaseService):
    """ need generate ssl key, crt"
    /etc/nginx/
            ├── common
                   └── restricted.conf
            ├── conf.d
            ├── sites-enabled
                    ├── default
            ├── ssl
                   ├── nginx.crt
                    ── nginx.key
            ├── nginx.conf

    """
    nginx_key = "nginx.key"
    nginx_crt = "nginx.crt"
    default_nginx_config = "nginx.conf"
    default_server_config = "default"
    default_restricted_config = "restricted.conf"

    nginx_key_path: str
    nginx_cert_path: str

    def __init__(self, config_dir="/etc/nginx", upstream=None, reconfigure=False):
        self.config_dir: str = config_dir
        self.reconfigure: bool = reconfigure
        self.upstream = upstream
        ssl_path, confd_path, common_path = os.path.join(self.config_dir, "ssl"), \
                                            os.path.join(self.config_dir, "conf.d"), \
                                            os.path.join(self.config_dir, "common")
        sites_enabled = os.path.join(self.config_dir, "sites-enabled")
        for item in [ssl_path, common_path, confd_path, sites_enabled]:
            if not os.path.exists(item):
                os.makedirs(item)
        self.nginx_key_path, self.nginx_cert_path = os.path.join(ssl_path, self.nginx_key), os.path.join(ssl_path,
                                                                                                         self.nginx_crt)

    def _gen_ssl_certificate(self):
        if not os.path.exists(self.nginx_key_path) or not os.path.exists(self.nginx_cert_path) or self.reconfigure:
            subprocess.call(
                f'openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout {self.nginx_key_path} -out {self.nginx_cert_path} -subj "/C=US/ST=Denial/L=Springfield/O=Dis/CN=www.nginx.com" ',
                shell=True)

    def _gen_default_server_config(self):
        default_server_config_path = os.path.join(self.config_dir, "sites-enabled", self.default_server_config)
        if not os.path.exists(default_server_config_path) or self.reconfigure:
            template = """
# cat /etc/nginx/config/sites-enabled/default
server {{
        listen 80 default_server;
        listen 443 ssl default_server;
        access_log on;

        access_log  /var/log/nginx/default_access.log main;
        error_log  /var/log/nginx/default_error.log;

        server_name _;
        ssl_certificate {ssl_certificate};
        ssl_certificate_key {ssl_certificate_key};
        return 444;
}}
            """.format(ssl_certificate=self.nginx_cert_path, ssl_certificate_key=self.nginx_key_path)
            self._write(default_server_config_path, template)

    def _gen_common_restricted(self):
        default_gen_common_restricted_path = os.path.join(self.config_dir, "common", self.default_restricted_config)
        if not os.path.exists(default_gen_common_restricted_path) or self.reconfigure:
            template = """
location / {
    proxy_redirect off;
    proxy_pass https://backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto  $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Host $server_name;
    proxy_ssl_session_reuse on;
    proxy_ssl_verify off;
}
            """
            self._write(default_gen_common_restricted_path, template)

    def _gen_main_nginx_conf(self):
        default_main_nginx_config_path = os.path.join(self.config_dir, self.default_nginx_config)
        if not os.path.exists(default_main_nginx_config_path) or self.reconfigure:
            if not self.upstream:
                raise ValueError(f"Upstream {self.upstream} required for main nginx config file.")
            template = """
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {{
    worker_connections 768;
    # multi_accept on;
}}

http {{
    resolver 8.8.8.8 8.8.4.4 valid=300s; # Cache resolver

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    server_names_hash_bucket_size 256;
    large_client_header_buffers 4 32k;



    client_max_body_size    100m;
    client_body_buffer_size 128k;
    proxy_connect_timeout   90;
    proxy_send_timeout      90;
    proxy_read_timeout      90;
    proxy_buffering         on;
    proxy_buffer_size       256k;
    proxy_buffers           4 256k;
    proxy_busy_buffers_size 256k;


    log_format main '$http_x_forwarded_for - $remote_user [$time_local] '
                    '"$request_method $scheme://$host$request_uri $server_protocol" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" $request_time';

    map $http_upgrade $connection_upgrade {{
        default upgrade;
        '' close;
    }}

    upstream backend {{
        server www.{upstream}:443;
    }}

    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    # enable session resumption to improve https performance
    # http://vincent.bernat.im/en/blog/2011-ssl-session-reuse-rfc5077.html
    ssl_session_cache shared:SSL:50m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    
    # disable SSLv3(enabled by default since nginx 0.8.19) since it's less secure then TLS http://en.wikipedia.org/wiki/Secure_Sockets_Layer#SSL_3.0
    ssl_protocols TLSv1.2 TLSv1.3;
    
    
    # enables server-side protection from BEAST attacks
    # http://blog.ivanristic.com/2013/09/is-beast-still-a-threat.html
    ssl_prefer_server_ciphers on;
    
    # ciphers chosen for forward secrecy and compatibility
    # http://blog.ivanristic.com/2013/08/configuring-apache-nginx-and-openssl-for-forward-secrecy.html
    ssl_ciphers 'ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA:ECDHE-ECDSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA:ECDHE-RSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:DHE-RSA-AES256-SHA256:DHE-RSA-AES256-SHA:ECDHE-ECDSA-DES-CBC3-SHA:ECDHE-RSA-DES-CBC3-SHA:EDH-RSA-DES-CBC3-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA256:AES128-SHA:AES256-SHA:DES-CBC3-SHA:!DSS';
  
    ##
    # Logging Settings
    ##

    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log;

    ##
    # Gzip Settings
    ##

    gzip on;

    # gzip_vary on;
    # gzip_proxied any;
    # gzip_comp_level 6;
    # gzip_buffers 16 8k;
    # gzip_http_version 1.1;
    # gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    ##
    # Virtual Host Configs
    ##

    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}}
            """.format(upstream=self.upstream)
            self._write(default_main_nginx_config_path, template)

    def check(self):
        self._gen_ssl_certificate()
        self._gen_default_server_config()
        self._gen_common_restricted()
        self._gen_main_nginx_conf()


class Bootstrap:
    usage = """
    ./nginx-remote-agent.py <command> [<args>] -h 
        The most commonly used commands are:
        - default              create standalone system setup.
        - letsencrypt          Shortcut for let`s encrypt service.
    """
    epilog = ""
    description = ""

    def __init__(self):
        self.parser = argparse.ArgumentParser(
            usage=self.usage,
            epilog=self.epilog,
            description=self.description,
        )

    def __call__(self, *args, **kwargs):
        self.parser.add_argument('command', help='Sub-Command to run')
        # parse_args defaults to [1:] for args, but you need to
        # exclude the rest of the args too, or validation will fail
        args = self.parser.parse_args(sys.argv[1:2])

        sub_command = "command_" + args.command
        if not hasattr(self, sub_command):
            print('Unrecognized command')
            self.parser.print_help()
            exit(1)
        # use dispatch pattern to invoke method with same name
        handler = getattr(self, sub_command)
        parser = argparse.ArgumentParser(description='Base setup Sub-Command')
        try:
            handler(parser)
        except Exception as exc:
            print(exc)

    def _install(self, args: argparse.Namespace):
        if not args.upstream:
            raise ValueError(f"Upstream {args.upstream} required for main nginx config file.")
        _nginx = NginxService(config_dir=args.nginx_path, upstream=args.upstream, reconfigure=args.reconfigure)
        _nginx.check()

        # TODO ADD SYSTEM START SERVICE CONFIG WITH CONNECT_URL AND CONNECT_TOKEN
        # _systemd = SystemService()
        return

    def command_install(self, parser: argparse.ArgumentParser = None):
        # install required tools.
        # create required structure`s.
        # create systemctl service.

        argument_classes = [
            CommonArguments(),
            InstallArguments()
        ]
        [cls(parser) for cls in argument_classes]
        args: argparse.Namespace = parser.parse_args(sys.argv[2:])
        self._install(args)

    def command_run(self, parser: argparse.ArgumentParser = None):
        from main import main
        from store import Store
        argument_classes = [
            CommonArguments()
        ]
        [cls(parser) for cls in argument_classes]
        args: argparse.Namespace = parser.parse_args(sys.argv[2:])
        store = Store(**vars(args))
        main(store)
