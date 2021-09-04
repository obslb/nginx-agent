import asyncio
import json
import logging
import ssl
import sys
import traceback
import typing

# prevent issue: ModuleNotFoundError: No module named 'websockets.exceptions'
from websockets.exceptions import (
    ConnectionClosed,
    InvalidStatusCode,

)
# prevent issue: ModuleNotFoundError: No module named 'websockets.legacy'
from websockets.legacy import client

from core.models import Domain, PENDING, SUCCESS, FAILED
from core.store import Store

logger = logging.getLogger('agent')


class Connector:
    websocket = None
    receive_queue: asyncio.Queue
    producer_queue: asyncio.Queue

    def __init__(self, store):
        self.receive_queue = store.receive_queue
        self.producer_queue = store.producer_queue
        self.finished = False
        self.connect_url = store.connect_url
        self.extra_headers = {"TOKEN": store.connect_token}

    @classmethod
    async def decode_json(cls, text_data):
        return json.loads(text_data)

    @classmethod
    async def encode_json(cls, content):
        return json.dumps(content)

    async def websocket_connection(self):
        while not self.finished:
            try:
                self.websocket = await client.connect(self.connect_url,
                                                      max_size=None,
                                                      extra_headers=self.extra_headers,
                                                      ssl=ssl.SSLContext(),
                                                      )
                consumer_task = asyncio.create_task(self.receive())
                producer_task = asyncio.create_task(self.producer())
                done, pending = await asyncio.wait([consumer_task, producer_task],
                                                   return_when=asyncio.FIRST_COMPLETED, )
                for task in pending:
                    task.cancel()
            except ConnectionClosed as error:
                # disconnected from server
                logger.warning(f'{self} Error, disconnected from server: {error}')

            except BrokenPipeError as error:
                # Connect failed
                logger.warning(f'{self} Error, Connect failed: {error}')

            except IOError as error:
                # disconnected from server mis-transfer
                logger.warning(f'{self} Error, disconnected from server mis-transfer: {error}')
                await asyncio.sleep(5)

            except InvalidStatusCode as error:
                logger.warning(f'{self} Error, rejected from server: {error}')
                await asyncio.sleep(60)

            except Exception as error:
                logger.warning(f'{self} Error, unexpected exception: {error}')
                traceback.print_exc(file=sys.stdout)

    async def receive(self):
        try:
            async for message in self.websocket:
                if isinstance(message, str):
                    await self.receive_json(await self.decode_json(message))
                else:
                    raise ValueError("No text section for incoming WebSocket frame!")
        except asyncio.CancelledError:
            logger.info(f"websocket receive task shutting down.")

    async def receive_json(self, data, **kwargs):
        try:
            logger.debug(f'{self}::receive_json: {data}')
            await self.receive_queue.put(data)
        except Exception as error:
            logger.debug(f'{self}::receive_json: Exception, {error}')

    async def send_json(self, content, **kwargs):
        await self.websocket.send(await self.encode_json(content))

    async def producer(self):
        try:
            logger.debug("Websocket Producer Loop Started")
            while not self.finished:
                pong_waiter = await self.websocket.ping()
                await pong_waiter
                try:
                    event = await self.producer_queue.get()
                    # this will break Loop and return to WS setup block
                    if event is None:
                        break

                    logger.debug(f"{self}, send_json {event}")
                    await self.send_json(event)
                except asyncio.QueueEmpty as exc:
                    pass
                except Exception as exc:
                    # logger.debug(f'{self}::producer_handler: Exception, {error}')
                    pass
        except asyncio.CancelledError:
            logger.info(f"websocket producer task shutting down.")

    def __repr__(self):
        return f"<{self.__class__.__name__}>"


class Worker(Connector):

    def __init__(self, store: Store):
        super().__init__(store)

        self.finished = False
        self.store = store

    def get_or_create_domain(self, domain: str, cache_ttl=None, **kwargs) -> typing.Tuple[Domain, bool]:
        # we need create redis cache
        try:
            return self.store.get_cache(domain), False
        except ValueError as exc:
            instance = Domain(domain, cache_ttl=cache_ttl)
            self.store.set_cache(domain, instance, instance.cache_time_out)
            return instance, True

    async def dispatch(self, message: typing.Dict):
        try:
            action = message.get("action")
            if action == "add_domain":
                domain = message['content']['domain'].strip()
                cache_ttl = int(message['content']['cache_ttl'])
                if domain:
                    # we need register 2 new tasks in loop
                    instance, is_created = self.get_or_create_domain(domain, cache_ttl)
                    if is_created:
                        asyncio.create_task(self.create_letsencrypt_task(instance))
                        asyncio.create_task(self.create_dns_check_task(instance))
        except Exception as exc:
            logger.exception(exc)

    # user create tasks
    async def create_dns_check_task(self, instance: Domain):

        try:
            domain: str = instance.domain
            while instance.status in [PENDING]:
                await asyncio.sleep(5)
                # we need get fresh cache object

                instance = self.store.get_cache(domain)
                # now we need check dns propagation status
                instance.check_acme()

                if instance.continue_check:
                    acme_time = int(instance.current_time - instance.start_time)
                    if acme_time >= instance.cache_time_out:
                        instance.status = FAILED
                        instance.on_error = "Session and confirmation timeout."

                self.store.set_cache(domain, instance, instance.cache_time_out)
                await self.store.producer_queue.put(
                    {
                        "type": "client.forward.message",
                        "ftype": f"acme_{PENDING}",
                        "content": instance.serialize()
                    }
                )

            # this mean domains challenge Error or Success
            if instance.status == SUCCESS:
                await self.store.producer_queue.put(
                    {
                        "type": "client.forward.message",
                        "ftype": f"acme_{SUCCESS}",  # ftype = acme_success
                        "error": [],
                        "content": instance.serialize()

                    }
                )
                self.store.cache.delete(domain)
            else:
                await self.store.producer_queue.put(
                    {
                        "type": "client.forward.message",
                        "ftype": f"acme_{FAILED}",
                        "error": [],
                        "content": instance.serialize()
                    }
                )
                self.store.cache.delete(domain)

        except Exception as exc:
            logger.exception(exc)

    async def create_letsencrypt_task(self, instance: Domain):
        # if self.store.debug:
        #     start = time.time()
        #     current = time.time()
        #     # emulate letsencrypt process and start while loop for 40 sec
        #     while int(current - start) < 40:
        #         current = time.time()
        #         await asyncio.sleep(1)

        domain: str = instance.domain

        if self.store.environment == "production":
            auth_hook = './nginx-agent.py acme_auth'
            deploy_hook = './nginx-agent.py acme_deploy'
        else:
            # TODO: add local tests with some timeouts in development
            auth_hook = './nginx-agent.py acme_auth'
            deploy_hook = './nginx-agent.py acme_deploy'

        command = [
            'letsencrypt',
            'certonly',
            f'--cert-name "{domain}"',
            '--manual',
            f'--manual-auth-hook "{auth_hook}"',
            f'--deploy-hook "{deploy_hook}"',
            '--force-renewal',
            '--preferred-challenges=dns',
            '--register-unsafely-without-email',
            '--manual-public-ip-logging-ok',
            '--server https://acme-v02.api.letsencrypt.org/directory',
            '--agree-tos',
            '--quiet',
            f'-d "{domain}"',
            f'-d "*.{domain}"',
        ]

        shell_command = " ".join(command)

        process = await asyncio.create_subprocess_shell(shell_command,
                                                        stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.PIPE
                                                        )
        # if success process.returncode = 0
        # if error process.returncode = 1
        stdout, stderr = await process.communicate()

        instance: Domain = self.store.get_cache(domain)

        instance.on_success = stdout.decode().replace("\n", " ").strip()
        instance.on_error = stderr.decode().replace("\n", " ").strip()

        logger.debug(f"process.communicate: {process.returncode} {instance.serialize()}")
        if process.returncode == 0:
            instance.status = SUCCESS
        else:
            instance.status = FAILED
        self.store.set_cache(domain, instance, instance.cache_time_out)

    # periodical tasks
    async def task_queue(self):
        try:
            while not self.finished:
                try:
                    data = await self.store.receive_queue.get()
                    if data is None:
                        break
                    await self.dispatch(data)
                except asyncio.QueueEmpty as error:
                    pass

        except asyncio.CancelledError:
            self.finished = True
            await self.store.receive_queue.put(None)
            logger.info(f"incoming queue shutting down.")

    async def heartbeat(self):
        try:
            while True:
                await asyncio.sleep(30)
                try:
                    await self.store.producer_queue.put(
                        {
                            "type": 'heartbeat',
                            "content": {
                                "is_online": True,
                            },
                        }
                    )
                except Exception as exc:
                    logger.exception(exc)
        except asyncio.CancelledError:
            logger.info(f"cache queue shutting down.")

    def __repr__(self):
        return f"<'{self.__class__.__name__}'>"
