import asyncio
import logging
from signal import SIGTERM, SIGINT

from store import Store
from worker import Worker

logger = logging.getLogger('agent')


def handler(sig, loop):
    loop.stop()
    logger.info(f"Got signal {sig}, shutting down.")
    loop.remove_signal_handler(SIGTERM)
    loop.add_signal_handler(SIGINT, lambda: None)


def main(store: Store):
    loop = asyncio.get_event_loop()
    # create event loop

    worker = Worker(store)
    # load config
    print(f"main call")

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
