import asyncio
import json
import logging
import sys
import traceback
import ssl
import websockets
from websockets import WebSocketClientProtocol, InvalidStatusCode

logger = logging.getLogger('agent')




class GateWayAgent:
    websocket: WebSocketClientProtocol = None
    receive_queue: asyncio.Queue
    producer_queue: asyncio.Queue

    @classmethod
    async def decode_json(cls, text_data):
        return json.loads(text_data)

    @classmethod
    async def encode_json(cls, content):
        return json.dumps(content)

    def __init__(self, store):
        self.receive_queue = store.receive_queue
        self.producer_queue = store.producer_queue
        self.finished = False
        self.connect_url = store.connect_url
        self.extra_headers = {"TOKEN": store.connect_token}

    async def websocket_connection(self):
        while not self.finished:
            try:
                self.websocket = await websockets.connect(self.connect_url,
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
            except websockets.ConnectionClosed as error:
                # disconnected from server
                logger.warning(f'{self} Error, disconnected from server: {error}')

            except BrokenPipeError as error:
                # Connect failed
                logger.warning(f'{self} Error, Connect failed: {error}')

            except IOError as error:
                # disconnected from server mis-transfer
                logger.warning(f'{self} Error, disconnected from server mis-transfer: {error}')

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
                except asyncio.QueueEmpty as error:
                    pass
                except Exception as error:
                    # logger.debug(f'{self}::producer_handler: Exception, {error}')
                    pass
        except asyncio.CancelledError:
            logger.info(f"websocket producer task shutting down.")

    def __repr__(self):
        return f"<{self.__class__.__name__}>"
