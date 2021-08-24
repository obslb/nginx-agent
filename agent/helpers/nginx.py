import logging
import argparse

logger = logging.getLogger('agent')


DEFAULT_NGINX_PATH = '/etc/nginx/'

class NginxArgs:

    def __call__(self, parser: argparse.ArgumentParser, *args, **kwargs):
        parser.add_argument(
            '--reconfigure',
            action="store_true",
            default=False,
            help='',
        )


class Nginx:
    pass
