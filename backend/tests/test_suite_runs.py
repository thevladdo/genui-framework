"""
The suite gives one answer however it is launched.

`discover -s tests` and `python -m unittest tests.test_x` import the modules differently, and a module that imports a sibling can be loaded twice under two names.
A test that silently skips or shares state across the two copies passes one way and not the other.
"""

import os
import re
import subprocess
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = ("test_chat_session", "test_redis_reconnect")


def _summary(args):
    result = subprocess.run([sys.executable, "-m", "unittest", *args], cwd=BACKEND, capture_output=True, text=True, timeout=300)
    ran = re.search(r"^Ran (\d+) test", result.stderr, re.M)
    skipped = re.search(r"skipped=(\d+)", result.stderr)
    return result.returncode, int(ran.group(1)) if ran else 0, int(skipped.group(1)) if skipped else 0, result.stderr[-1500:]


class TestLaunchModes(unittest.TestCase):
    def test_package_run_matches_discover(self):
        code, ran, skipped, tail = _summary([f"tests.{m}" for m in MODULES])
        self.assertEqual(code, 0, tail)
        expected = [_summary(["discover", "-s", "tests", "-p", f"{m}.py"]) for m in MODULES]
        self.assertEqual(ran, sum(e[1] for e in expected))
        self.assertEqual(skipped, sum(e[2] for e in expected))


if __name__ == "__main__":
    unittest.main()
