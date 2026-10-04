"""
The suite runs two ways: `python -m unittest discover -s tests` puts this directory on sys.path, `python -m unittest tests.test_x` imports the modules as a package and does not.
The test modules import each other by plain name (memory_stores, test_redis_reconnect), so the directory goes on sys.path here too.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
