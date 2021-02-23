#!/usr/bin/env python3
import logging.config
import sys

from store import LOGGING_CONFIG

try:
    assert sys.version_info >= (3, 8)
except AssertionError:
    sys.exit('Sorry. This script requires python3 >= 3.8 version')

if __name__ == "__main__":
    from cli import Bootstrap

    logging.config.dictConfig(LOGGING_CONFIG)
    bootstrap = Bootstrap()

    bootstrap()  # initial call
