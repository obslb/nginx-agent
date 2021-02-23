import asyncio
import logging
import os
from typing import Dict, Tuple

from models import Domain, PENDING, SUCCESS, FAILED
from store import Store

logger = logging.getLogger('agent')


class Worker:
    consumer_name = 'agent.worker'

    def __init__(self, loop, store: Store):

        self.loop = loop
        self.finished = False
        self.config_path = store.config_path
        self.letsencrypt_path: str = store.letsencrypt_path
        self.store = store

        self.dns_acme_auth = os.path.join(self.config_path, "dns_acme_auth.py")
        self.dns_acme_clean = os.path.join(self.config_path, "dns_acme_clean.py")
        self.dns_acme_deploy = os.path.join(self.config_path, "dns_acme_deploy.py")

    def get_or_create_domain(self, domain: str) -> Tuple[Domain, bool]:
        # we need create redis cache
        try:
            return self.store.get_cache(domain), False
        except ValueError as exc:
            instance = Domain(domain)
            self.store.set_cache(domain, instance, instance.cache_time_out)
            return instance, True

    async def periodical_check(self, instance: Domain):
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
                    if acme_time >= 60 * 11:
                        instance.status = FAILED
                        instance.on_error = "Session and confirmation timeout."

                self.store.set_cache(domain, instance, instance.cache_time_out)
                await self.store.producer_queue.put(
                    {
                        "consumer": "remote.vps.agent",
                        "type": "receive.json",
                        "action": f"acme_{PENDING}",
                        "message": instance.serialize()
                    }
                )

            # this mean domains challenge Error or Success
            # TODO add logic for this challenge
            if instance.status == SUCCESS:
                await self.store.producer_queue.put(
                    {
                        "consumer": "remote.vps.agent",
                        "type": "receive.json",
                        "action": f"acme_{SUCCESS}",
                        "error": [],
                        "message": instance.serialize()
                    }
                )
                self.store.cache.delete(domain)
            else:
                await self.store.producer_queue.put(
                    {
                        "consumer": "remote.vps.agent",
                        "type": "receive.json",
                        "action": f"acme_{FAILED}",
                        "error": [],
                        "message": instance.serialize()
                    }
                )
                self.store.cache.delete(domain)

        except Exception as exc:
            logger.exception(exc)

    async def letsencrypt_fork(self, instance: Domain):
        domain: str = instance.domain

        command = [
            'letsencrypt',
            'certonly',
            f'--cert-name "{domain}"',
            '--manual',
            # f'--manual-auth-hook {self.dns_acme_auth}',
            f'--manual-auth-hook ./dns_acme_auth.py',
            # f'--deploy-hook {self.dns_acme_deploy}',
            f'--deploy-hook ./dns_acme_deploy.py',
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

    async def dispatch(self, message: Dict):
        try:
            payload = message["content"]["payload"]
            action = message["content"]["action"]
            if action == "add_domain":
                domain = payload.get("domain").strip()
                instance, is_created = self.get_or_create_domain(domain)
                if is_created:
                    asyncio.create_task(self.letsencrypt_fork(instance))
                    asyncio.create_task(self.periodical_check(instance))
            logger.debug(f"{self}, dispatch {message}")

        except Exception as exc:
            logger.exception(exc)

    def __repr__(self):
        return f"<{self.__class__.__name__}>"

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

    async def cache(self):
        try:
            while True:
                await asyncio.sleep(30)
                try:
                    await self.store.producer_queue.put(
                        {
                            "action": 'heartbeat',
                            "data": {
                                "is_active": True
                            },
                        }
                    )
                except Exception as exc:
                    logger.exception(exc)
        except asyncio.CancelledError:
            logger.info(f"cache queue shutting down.")
