# Given a VERSION number MAJOR.MINOR.PATCH, increment the: MAJOR VERSION when you make incompatible API changes,
# MINOR VERSION when you add functionality in a backwards-compatible manner, and BUILD must get updated whenever a
# release candidate is built from the current trunk (at least weekly for Dev channel release candidates). The BUILD
# number is an ever-increasing number representing a point in time of the Chromium trunk. PATCH VERSION when you make
# backwards-compatible bug fixes. Additional labels for pre-release and build metadata are available as extensions to
# the MAJOR.MINOR.PATCH format. MAJOR.MINOR.BUILD.PATCH.
MAJOR, MINOR, BUILD, PATCH = 1, 0, 0, 1
VERSION = f'{MAJOR}.{MINOR}.{BUILD}.{PATCH}'
