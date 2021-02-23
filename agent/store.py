import asyncio
import pickle
import redis


class Store:
    connect_url = ""
    connect_token = ""
    tmp = '/tmp/'
    nginx_path = '/etc/nginx/'
    letsencrypt_path = '/etc/letsencrypt/'
    config_path = '/etc/nginx-agent/'

    def __init__(self, **kwargs):
        self.cache = redis.Redis(host='localhost', port=6379, db=0)
        self.cache.flushall()

        self.receive_queue = asyncio.Queue()
        self.producer_queue = asyncio.Queue()
        for k, v in kwargs.items():
            if hasattr(self, k) and v:
                setattr(self, k, v)

        if not self.connect_url or not self.connect_token:
            raise ValueError(f"connect_url {self.connect_url} and connect_token {self.connect_token} required!")

    def update(self, **kwargs):
        for k, v in kwargs:
            if hasattr(self, k) and v:
                setattr(self, k, v)

    def get_cache(self, key: str):
        if value := self.cache.get(key):
            return pickle.loads(value)
        raise ValueError(f"Object {key} are not exists in cache.")

    def set_cache(self, key, value, ex=None):
        return self.cache.set(key, pickle.dumps(value), ex)


LOGGING_CONFIG = {
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
