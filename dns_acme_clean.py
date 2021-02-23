#!/usr/bin/env python3
import json
import os
# CERTBOT_DOMAIN
import subprocess

domain = os.environ["CERTBOT_DOMAIN"]
# CERTBOT_VALIDATION
TEMP_FOLDER = '/tmp'
DOMAIN_TMP_TOKENS = os.path.join(TEMP_FOLDER, domain + ".lock")
if os.path.exists(DOMAIN_TMP_TOKENS):
    os.remove(DOMAIN_TMP_TOKENS)
