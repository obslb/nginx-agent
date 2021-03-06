#!/usr/bin/env python3
import json
import os
import pickle
import sys
import time

import redis
import requests

WORK_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_DIR = os.path.join(WORK_DIR, 'agent')
if not os.path.exists(BASE_DIR):
    raise Exception('Error, we could not find path with gateway: {0}!!'.format(BASE_DIR))
sys.path.append(BASE_DIR)

# https://www.digitalocean.com/community/tutorials/how-to-acquire-a-let-s-encrypt-certificate-using-dns-validation-with-acme-dns-certbot-on-ubuntu-18-04

# URL to acme-dns instance
ACME_DNS_URL = "https://auth.acme-dns.io"
# Path for acme-dns credential storage

ALLOW_FROM = []
# Force re-registration. Overwrites the already existing acme-dns accounts.
FORCE_REGISTER = False

DOMAIN = os.environ["CERTBOT_DOMAIN"]
if DOMAIN.startswith("*."):
    DOMAIN = DOMAIN[2:]
VALIDATION_DOMAIN = "_acme-challenge." + DOMAIN
VALIDATION_TOKEN = os.environ["CERTBOT_VALIDATION"]

# TODO CHANGE ACME_TIME_OUT FOR PRODUCTION

TEMP_FOLDER = '/tmp'
ACCOUNTS_STORAGE = '/etc/letsencrypt/'
DOMAIN_TMP_TOKENS = os.path.join(TEMP_FOLDER, DOMAIN + ".lock")


class AcmeDnsClient(object):
    """
    Handles the communication with ACME-DNS API
    """

    def __init__(self, acme_dns_url):
        self.acme_dns_url = acme_dns_url

    def register_account(self, allow_from):
        """Registers a new ACME-DNS account"""

        if allow_from:
            # Include whitelisted networks to the registration call
            reg_data = {"allowfrom": allow_from}
            res = requests.post(self.acme_dns_url + "/register",
                                data=json.dumps(reg_data))
        else:
            res = requests.post(self.acme_dns_url + "/register")
        if res.status_code == 201:
            return res.json()
        else:
            # Encountered an error
            msg = ("Encountered an error while trying to register a new acme-dns "
                   "account. HTTP status {}, Response body: {}")
            print(msg.format(res.status_code, res.text))
            sys.exit(1)

    def update_txt_record(self, account, txt):
        """Updates the TXT challenge record to ACME-DNS subdomain."""
        update = {"subdomain": account['subdomain'], "txt": txt}
        headers = {"X-Api-User": account['username'],
                   "X-Api-Key": account['password'],
                   "Content-Type": "application/json"}
        res = requests.post(self.acme_dns_url + "/update",
                            headers=headers,
                            data=json.dumps(update))
        if res.status_code == 200:
            # Successful update
            print(update)
            return
        else:
            msg = ("Encountered an error while trying to update TXT record in "
                   "acme-dns. \n"
                   "------- Request headers:\n{}\n"
                   "------- Request body:\n{}\n"
                   "------- Response HTTP status: {}\n"
                   "------- Response body: {}")
            s_headers = json.dumps(headers, indent=2, sort_keys=True)
            s_update = json.dumps(update, indent=2, sort_keys=True)
            s_body = json.dumps(res.json(), indent=2, sort_keys=True)
            print(msg.format(s_headers, s_update, res.status_code, s_body))
            sys.exit(1)


class Storage:
    def __init__(self, storage_path):
        self.cache = redis.Redis(host='localhost', port=6379, db=0)
        self.storage_path = storage_path
        self._data = self.load()

    def load(self):
        """Reads the storage content from the disk to a dict structure"""
        data = dict()
        filedata = ""
        try:
            with open(self.storage_path, 'r') as fh:
                filedata = fh.read()
        except IOError as e:
            if os.path.isfile(self.storage_path):
                # Only error out if file exists, but cannot be read
                print("ERROR: Storage file exists but cannot be read")
                sys.exit(1)
        try:
            data = json.loads(filedata)
        except ValueError:
            if len(filedata) > 0:
                # Storage file is corrupted
                print("ERROR: Storage JSON is corrupted")
                sys.exit(1)
        return data

    def save(self):
        """Saves the storage content to disk"""
        serialized = json.dumps(self._data)
        try:
            with os.fdopen(os.open(self.storage_path,
                                   os.O_WRONLY | os.O_CREAT, 0o600), 'w') as fh:
                fh.truncate()
                fh.write(serialized)
        except IOError as e:
            print("ERROR: Could not write storage file.")
            sys.exit(1)

    def put(self, key, value):
        """Puts the configuration value to storage and sanitize it"""
        # If wildcard domain, remove the wildcard part as this will use the
        # same validation record name as the base domain
        if key.startswith("*."):
            key = key[2:]
        self._data[key] = value

    def fetch(self, key):
        """Gets configuration value from storage"""
        try:
            return self._data[key]
        except KeyError:
            return None

    def get_cache(self, key: str):
        if self.cache.get(key):
            return pickle.loads(self.cache.get(key))
        raise ValueError("Object {} are not exists in cache.".format(key))

    def set_cache(self, key, value, ex=None):
        return self.cache.set(key, pickle.dumps(value), ex)


def main():
    client = AcmeDnsClient(ACME_DNS_URL)
    domain_account_path = os.path.join(ACCOUNTS_STORAGE, DOMAIN + ".json")
    storage = Storage(domain_account_path)

    # Check if an account already exists in storage
    account = storage.fetch(DOMAIN)
    if FORCE_REGISTER or not account:
        # Create and save the new account
        account = client.register_account(ALLOW_FROM)
        storage.put(DOMAIN, account)
        storage.save()
        #
        # # Display the notification for the user to update the main zone
        # msg = "Please add the following CNAME record to your main DNS zone:\n{}"
        # cname = "{} CNAME {}.".format(VALIDATION_DOMAIN, account["fulldomain"])
        # print(msg.format(cname))

    # Update the TXT record in acme-dns instance

    client.update_txt_record(account, VALIDATION_TOKEN)

    instance = storage.get_cache(DOMAIN)
    instance.set_account(account)
    instance.set_token(VALIDATION_TOKEN)
    storage.set_cache(DOMAIN, instance, instance.cache_time_out)

    # we need set accounts details and token details
    # and wait for confirm of dns or timeout
    if instance.token_one and instance.token_two:
        while not instance.continue_check:
            time.sleep(5)
            instance = storage.get_cache(DOMAIN)


if __name__ == "__main__":
    # Init
    main()
