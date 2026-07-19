"""
API authentication for the GenUI backend.

Pure logic lives in auth.keys (API keys) and auth.identity (signed user
tokens, fail-closed helpers) — both testable without FastAPI.
FastAPI dependencies live in auth.dependencies.
"""

from .identity import AuthError, UserTokenVerifier, sign_user_token, verify_user_token
from .keys import AuthContext, KeyRegistry, parse_key_entries

__all__ = [
    "AuthContext",
    "AuthError",
    "KeyRegistry",
    "UserTokenVerifier",
    "parse_key_entries",
    "sign_user_token",
    "verify_user_token",
]
