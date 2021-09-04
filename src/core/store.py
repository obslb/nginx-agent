import asyncio
import pickle
import time

import redis


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class Store(metaclass=Singleton):
    def __init__(self, **kwargs):
        self.start_time = time.time()

        if v := kwargs.get("redis_host"):
            redis_host = v
        else:
            redis_host = 'redis'

        if v := kwargs.get("redis_port"):
            redis_port = v
        else:
            redis_port = 6379

        self.cache = redis.Redis(host=redis_host, port=redis_port, db=0)
        self.cache.flushall()

        self.receive_queue = asyncio.Queue()
        self.producer_queue = asyncio.Queue()

        self.connect_url = kwargs.get("connect_url", None)
        self.connect_token = kwargs.get("connect_token", None)
        self.debug = kwargs.get("debug", False)
        self.environment = kwargs.get("environment", "production")

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
