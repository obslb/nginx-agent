#!/usr/bin/env python3.8
import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import typing
from signal import SIGTERM, SIGINT

import jinja2

from core.acme_auth_dns import acme_auth_check
from version import VERSION

try:
    assert sys.version_info >= (3, 8)
except AssertionError:
    sys.exit('Sorry. This script requires python3 >= 3.8 VERSION')

from core.store import Store
from core.worker import Worker

logger = logging.getLogger('agent')


def handler(sig, loop):
    loop.stop()
    logger.info(f"Got signal {sig}, shutting down.")
    loop.remove_signal_handler(SIGTERM)
    loop.add_signal_handler(SIGINT, lambda: None)


class NginxAgent:

    def __init__(self, **kwargs):
        self.nginx_path = kwargs.get('nginx_path')
        self.letsencrypt_path = kwargs.get('letsencrypt_path')

        if not self.nginx_path:
            self.nginx_path = "/etc/nginx/"

        if not self.letsencrypt_path:
            self.letsencrypt_path = "/etc/letsencrypt/"

        self.ssl_certificate_key = os.path.join(self.nginx_path, "ssl", "nginx.key")
        self.ssl_certificate = os.path.join(self.nginx_path, "ssl", "nginx.crt")
        self.reconfigure = kwargs.get('reconfigure', False)

    @staticmethod
    def resource_path(relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, relative_path)

    def generate_ssl(self):
        subprocess.call(
            f'openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout {self.ssl_certificate_key} -out {self.ssl_certificate} -subj "/C=US/ST=Denial/L=Springfield/O=Dis/CN=www.nginx.com" ',
            shell=True)

    def check_or_generate_ssl(self):
        if not os.path.exists(self.ssl_certificate_key) or not os.path.exists(self.ssl_certificate) or self.reconfigure:
            self.generate_ssl()

    def get_template(self, name: str) -> str:
        with open(os.path.join(self.resource_path('templates'), name), 'r') as f:
            return f.read()

    def create_config(self, path: str, template_name: str, **kwargs):
        if not os.path.exists(path) or self.reconfigure:
            t = jinja2.Template(self.get_template(template_name))
            content: str = t.render(**kwargs)
            with open(path, 'w') as f:
                f.write(content)

    def setup(self, upstreams: typing.Union[None, typing.List], **kwargs):
        if upstreams is None or not upstreams:
            raise ValueError("at least one upstream is required!")

        # 1. create nginx structures
        check_structure = [
            os.path.join(self.nginx_path, "ssl"),
            os.path.join(self.nginx_path, "conf.d"),
            os.path.join(self.nginx_path, "common"),
            os.path.join(self.nginx_path, "sites-enabled"),
        ]
        for d in check_structure:
            if not os.path.exists(d):
                os.makedirs(d)

        # 2. create nginx ssl
        self.check_or_generate_ssl()

        # 3. create nginx base configs.

        # 3.1 remove default config file if its in other directory
        default_server_config = os.path.join(self.nginx_path, "conf.d", "default")
        if os.path.exists(default_server_config):
            os.remove(default_server_config)

        # 3.2 check or create new secure default config. /etc/nginx/sites-enabled/default
        default_server_config = os.path.join(self.nginx_path, "sites-enabled", "default")
        self.create_config(
            path=default_server_config,
            template_name="template.default",
            **{
                "ssl_certificate": self.ssl_certificate,
                "ssl_certificate_key": self.ssl_certificate_key
            })

        # 3.3 create main nginx conf /etc/nginx/nginx.conf
        main_nginx_config = os.path.join(self.nginx_path, "nginx.conf")
        self.create_config(
            path=main_nginx_config,
            template_name="template.nginx.conf",
            **{
                "upstreams": upstreams,
                "ssl_certificate": self.ssl_certificate,
                "ssl_certificate_key": self.ssl_certificate_key
            })

        # 3.4 create shared include directive for domains conf /etc/nginx/common/location.conf
        location_config = os.path.join(self.nginx_path, "common", "location.conf")
        self.create_config(
            path=location_config,
            template_name="template.location.conf")

    @staticmethod
    def reload_nginx():
        time.sleep(2)
        try:
            subprocess.check_output(f"/usr/sbin/nginx -s reload", stderr=subprocess.STDOUT, shell=True)
        except Exception as exc:
            print("Nginx Reload: " + str(exc))

    def create_domain_config(self, domain: str):
        # 1. get ssl certificate path

        ssl_certificate = os.path.join(self.letsencrypt_path, "live", domain, "fullchain.pem")
        if not os.path.isfile(ssl_certificate):
            raise ValueError(f"certificate:  {ssl_certificate} not exists for {domain}")

        # 2. get ssl certificate key path
        ssl_certificate_key = os.path.join(self.letsencrypt_path, "live", domain, "privkey.pem")
        if not os.path.isfile(ssl_certificate_key):
            raise ValueError(f"certificate key: {ssl_certificate_key} not exists for {domain}")

        domain_config = os.path.join(self.nginx_path, "conf.d", f"{domain}.conf")
        self.create_config(
            path=domain_config,
            template_name="template.domain.conf", **{
                "domain": domain,
                "ssl_certificate": ssl_certificate,
                "ssl_certificate_key": ssl_certificate_key,
            })
        self.reload_nginx()
        print(f"Congratulations! Your certificate and chain have been saved at {ssl_certificate}")

    @staticmethod
    def run(store: Store, **kwargs):

        loop = asyncio.get_event_loop()
        # create event loop

        worker = Worker(store)
        # load config
        print(f"nginx agent VERSION {VERSION}")

        for sig in (SIGINT, SIGTERM):
            loop.add_signal_handler(sig, handler, sig, loop)

        loop.create_task(worker.websocket_connection())
        loop.create_task(worker.task_queue())
        loop.create_task(worker.heartbeat())

        loop.run_forever()
        tasks = asyncio.all_tasks(loop=loop)
        for t in tasks:
            t.cancel()
        worker.finished = True
        group = asyncio.gather(*tasks, return_exceptions=True)
        loop.run_until_complete(group)
        loop.close()


class CommonArguments:

    def __call__(self, parser: argparse.ArgumentParser, *args, **kwargs):
        parser.add_argument(
            '--reconfigure',
            action="store_true",
            default=False,
            help='',
        )
        parser.add_argument(
            '--nginx-path',
            default=None,
            required=False,
            help="place where nginx store its configs default: /etc/nginx/",
        )
        parser.add_argument(
            '--letsencrypt-path',
            default=None,
            required=False,
            help="place where letsencrypt store its configs default: /etc/letsencrypt/",
        )
        parser.add_argument(
            '-d',
            '--debug',
            action="store_true",
            default=False,
            help='set debug, default:False, true are not recommended for production, this can leak private data.'
        )
        parser.add_argument(
            '-e',
            '--environment',
            required=False,
            default='production',
            help='default:production'
        )
        parser.add_argument(
            '--connect-urls',
            default=None,
            required=False,
            help='',
        )
        parser.add_argument(
            '--connect-token',
            default=None,
            required=False,
            help='',
        )
        parser.add_argument(
            '-u',
            '--upstreams',
            required=False,
            nargs='+',
            help='',
        )


class Bootstrap:
    usage = """
    /usr/bin/nginx-agent <command> [<args>] -h 
        The most commonly used commands are:
        - setup              setup application with all requirements.
        - run                run application.
        - acme_auth          letsencrypt acme auth hook.
        - acme_deploy        letsencrypt acme deploy hook.
        - letsencrypt        shortcut for let`s encrypt manual certificate craft.
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
            sys.exit(1)
        # use dispatch pattern to invoke method with same name
        handler = getattr(self, sub_command)
        parser = argparse.ArgumentParser(description='Base setup Sub-Command')
        try:
            handler(parser)
        except Exception as exc:
            print(exc)

    @staticmethod
    def command_setup(parser: argparse.ArgumentParser = None):
        [cls(parser) for cls in [CommonArguments()]]
        args: argparse.Namespace = parser.parse_args(sys.argv[2:])
        agent = NginxAgent(**vars(args))

        agent.setup(
            upstreams=args.upstreams,
            connect_url=args.connect_url,
            connect_token=args.connect_token,
        )

    @staticmethod
    async def reader(std):
        while True:
            buf = await std.read()
            if not buf:
                break
            print(buf.decode(), end='')

    async def async_subprocess_shell(self, command: str):
        # Create subprocess
        process = await asyncio.create_subprocess_shell(
            command,
            # stdout must a pipe to be accessible as process.stdout
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        # Wait for the subprocess to finish
        # stdout, stderr = await process.communicate()
        # Return stdout
        await asyncio.gather(
            self.reader(process.stderr),
            self.reader(process.stdout),
        )

    @staticmethod
    def command_run(parser: argparse.ArgumentParser = None):
        try:
            argument_classes = [
                CommonArguments()
            ]
            [cls(parser) for cls in argument_classes]
            args: argparse.Namespace = parser.parse_args(sys.argv[2:])
            agent = NginxAgent(**vars(args))

            upstreams: typing.List = args.upstreams
            if not upstreams:
                upstreams = json.loads(os.environ['agent_upstreams'])

            connect_urls: str = args.connect_url
            if not connect_urls:
                connect_urls = os.environ.get('agent_connect_urls')

            connect_token: str = args.connect_token
            if not connect_token:
                connect_token = os.environ.get('agent_connect_token')

            agent.setup(
                upstreams=upstreams,
                connect_urls=connect_urls,
                connect_token=connect_token,
            )
            options = {}
            options.update(vars(args))
            options["upstreams"] = upstreams
            options["connect_urls"] = connect_urls
            options["connect_token"] = connect_token
            print("agent setup: ", options)
            agent.run(Store(**options))
        except Exception as exc:
            print(exc)

    @staticmethod
    def command_acme_auth(parser: argparse.ArgumentParser = None):
        args: argparse.Namespace = parser.parse_args(sys.argv[2:])
        arguments: typing.Dict = vars(args)
        acme_auth_check()

    @staticmethod
    def command_acme_deploy(parser: argparse.ArgumentParser = None):
        argument_classes = [
            CommonArguments(),
        ]
        [cls(parser) for cls in argument_classes]
        args: argparse.Namespace = parser.parse_args(sys.argv[2:])
        domain: typing.Union[None, str] = None
        if os.environ.get("RENEWED_DOMAINS"):
            domain = os.environ["RENEWED_DOMAINS"].split(" ")[0]
        agent = NginxAgent(**vars(args))

        agent.create_domain_config(domain=domain)


if __name__ == "__main__":
    import logging.config

    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            "main_formatter": {
                "format": "%(levelname)s:%(name)s: %(message)s(%(asctime)s; %(filename)s:%(lineno)d)",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            }
        },
        'handlers': {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "main_formatter"
            },
        },
        'loggers': {
            'agent': {
                'level': 'DEBUG',
                'handlers': ['console'],
                'propagate': False
            },
        },
    }
    )
    bootstrap = Bootstrap()

    bootstrap()  # initial call
