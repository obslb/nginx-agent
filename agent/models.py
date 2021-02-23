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

    def __init__(self, domain: str):
        self.domain = domain
        self.status = PENDING
        self.account = {}
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
        return {
            "domain": self.domain,
            "status": self.status,
            "account": self.account,
            "token_one": self.token_one,
            "token_two": self.token_two,
            "on_error": self.on_error,
            "on_success": self.on_success,
            "start_time": self.start_time,
            "current_time": self.current_time,
            "continue_time_out": self.continue_time_out,
            "continue_check": self.continue_check,
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
