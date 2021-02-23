# Given a version number MAJOR.MINOR.PATCH, increment the: MAJOR version when you make incompatible API changes,
# MINOR version when you add functionality in a backwards-compatible manner, and BUILD must get updated whenever a
# release candidate is built from the current trunk (at least weekly for Dev channel release candidates). The BUILD
# number is an ever-increasing number representing a point in time of the Chromium trunk. PATCH version when you make
# backwards-compatible bug fixes. Additional labels for pre-release and build metadata are available as extensions to
# the MAJOR.MINOR.PATCH format. MAJOR.MINOR.BUILD.PATCH.
MAJOR, MINOR, BUILD, PATCH = 0, 0, 0, 1
version = f'{MAJOR}.{MINOR}.{BUILD}.{PATCH}'
