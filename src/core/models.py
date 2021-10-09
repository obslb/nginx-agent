import time
from typing import Dict, List

import dns.resolver

PENDING = "pending"
SUCCESS = "success"
FAILED = 'failed'


class Domain:
    token_one = None
    token_two = None
    on_error = None
    on_success = None
    continue_time_out = 60 * 5
    continue_check = False
    cache_time_out = 60 * 11

    def __init__(self, domain: str, **kwargs):
        self.domain = domain
        self.status = PENDING
        self.account = {}
        if cache_ttl := kwargs.get("cache_ttl"):
            self.continue_time_out = cache_ttl
            self.cache_time_out = cache_ttl + 30
        self.resolver = dns.resolver.Resolver()
        self.resolver.nameservers = ['8.8.8.8', '8.8.8.4']
        self.start_time = time.time()
        self.current_time = time.time()

    def set_token(self, token: str):
        if self.token_one is None:
            self.token_one = token
        else:
            self.token_two = token

    def set_account(self, account: Dict):
        self.account = account

    def serialize(self):
        auto_check_in = (self.continue_time_out - int(self.current_time - self.start_time))
        return {
            "domain": self.domain,
            "status": self.status,
            "account": self.account,
            "token_one": self.token_one,
            "token_two": self.token_two,
            "on_error": self.on_error,
            "on_success": self.on_success,
            "start_time": self.start_time,  # deprecated field in v2
            "current_time": self.current_time,  # deprecated field in v2
            "continue_time_out": self.continue_time_out,
            "continue_check": self.continue_check,
            # new field form v2
            "auto_check_in": auto_check_in,
        }

    def get_acme_challenge(self) -> List:
        try:
            results = []
            answers = self.resolver.resolve(f'_acme-challenge.{self.domain}', 'TXT')
            for rdata in answers:
                txt = rdata.to_text()[1:-1]  # remove " " from dns query
                results.append(txt)
            return results
        except Exception as exc:
            pass

    def check_acme(self):
        self.current_time = time.time()
        acme_time = int(self.current_time - self.start_time)
        if acme_time >= self.continue_time_out:
            self.continue_check = True
        results = self.get_acme_challenge()
        match = []
        if results:
            for token in [self.token_one, self.token_two]:
                if token in results:
                    match.append(True)
                else:
                    match.append(False)
            if all(match):
                self.continue_check = True
