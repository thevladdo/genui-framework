"""
API authentication for the GenUI backend.

Pure key logic lives in auth.keys (testable without FastAPI);
FastAPI dependencies live in auth.dependencies.
"""

from .keys import AuthContext, KeyRegistry, parse_key_entries

__all__ = ["AuthContext", "KeyRegistry", "parse_key_entries"]
