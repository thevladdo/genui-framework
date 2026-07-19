"""
Signed user identity assertions (per-tenant HMAC) + fail-closed helpers.

Why this exists: a client key (pk_) lives in the browser and identifies
the calling APP, not the person. Any route that binds a request to a
user_id (profile read/delete/sync, personalized zone renders, /query)
needs proof that the caller IS that user, or PII leaks by editing the id.

Mechanism: the host application's backend — the only party that actually
knows who is logged in — signs {user_id, tenant, exp} with a shared
per-tenant secret (USER_TOKEN_SECRETS="<secret>:<tenant>,...") and hands
the token to the browser, which sends it in the X-User-Token header.
Shared-secret HMAC is the minimum correct mechanism for on-prem OSS:
one operator controls both sides, so asymmetric signing (JWT/JWKS) adds
key distribution without adding trust. JWT verification is the documented
upgrade path when identities come from a third-party IdP.

Fail-closed: absence of configuration must refuse, not open. The only
way to run open is the explicit GENUI_DEV_OPEN=1 dev flag.

Pure module: no FastAPI imports, testable with unittest alone.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Dict, Iterable, Optional, Union

from .keys import DEFAULT_TENANT, AuthContext, parse_key_entries

DEFAULT_TOKEN_TTL = 3600  # seconds


class AuthError(Exception):
    """Framework-free authorization failure (mapped to HTTP by the API layer)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def sign_user_token(
    secret: str,
    user_id: str,
    tenant: str,
    expires_in: int = DEFAULT_TOKEN_TTL,
    now: Optional[float] = None,
) -> str:
    """
    Mint a signed assertion binding user_id to tenant.

    Called by the HOST backend (the party that knows who is logged in),
    never by the browser. Token format: base64url(claims JSON).hexdigest.
    """
    claims = {
        "user_id": user_id,
        "tenant": tenant,
        "exp": int(now if now is not None else time.time()) + expires_in,
    }
    body = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii")
    sig = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_user_token(
    secret: str,
    token: Optional[str],
    now: Optional[float] = None,
) -> Optional[Dict]:
    """Return the claims if signature and expiry check out, else None."""
    if not token or token.count(".") != 1:
        return None
    body, sig = token.split(".", 1)
    expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        claims = json.loads(base64.urlsafe_b64decode(body.encode("ascii")))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(claims, dict):
        return None
    if claims.get("exp", 0) < (now if now is not None else time.time()):
        return None
    return claims


class UserTokenVerifier:
    """
    Resolves per-tenant signing secrets and verifies tokens against them.

    Config format mirrors the API keys: USER_TOKEN_SECRETS="secret:tenant,..."
    (entry without tenant = "default"). Multiple secrets per tenant are
    allowed, so operators can rotate without a hard cutover.
    """

    def __init__(self, entries: Union[str, Iterable[str], None] = None):
        # {secret: tenant}, same parser as the API keys
        self._secrets = parse_key_entries(entries)

    def _secrets_for(self, tenant: str) -> list:
        return [s for s, t in self._secrets.items() if t == tenant]

    def enabled_for(self, tenant: str) -> bool:
        return bool(self._secrets_for(tenant))

    def verify(self, token: Optional[str], tenant: str, now: Optional[float] = None) -> Optional[str]:
        """Return the verified user_id, or None. Tenant claim must match."""
        for secret in self._secrets_for(tenant):
            claims = verify_user_token(secret, token, now=now)
            if claims and claims.get("tenant") == tenant:
                return claims.get("user_id")
        return None


def authorize_user_access(
    auth: AuthContext,
    user_id: str,
    token: Optional[str],
    verifier: UserTokenVerifier,
    dev_open: bool,
    now: Optional[float] = None,
) -> None:
    """
    The single guard for every route that binds a request to a user_id
    (/profile/{id}, /profile/sync, /zone/render*, /query).

    Admin keys pass (server-to-server). If the tenant has a signing
    secret, the token must verify and its subject must equal user_id —
    dev_open does NOT bypass a configured secret. A tenant without a
    secret fails CLOSED unless GENUI_DEV_OPEN is explicitly set.
    """
    if auth.is_admin:
        return

    if verifier.enabled_for(auth.tenant):
        subject = verifier.verify(token, auth.tenant, now=now)
        if subject is None:
            raise AuthError(
                403,
                "A valid X-User-Token is required to access per-user data. "
                "The host backend must sign it with the tenant's USER_TOKEN_SECRETS entry.",
            )
        if subject != user_id:
            raise AuthError(403, "X-User-Token subject does not match the requested user_id")
        return

    if dev_open:
        return

    raise AuthError(
        403,
        f"Per-user routes are closed: no USER_TOKEN_SECRETS entry for tenant "
        f"'{auth.tenant}'. Configure USER_TOKEN_SECRETS=\"<secret>:{auth.tenant}\" "
        f"(production) or set GENUI_DEV_OPEN=1 (local development only).",
    )


def open_mode_context(dev_open: bool) -> AuthContext:
    """
    Identity used when NO API keys are configured.

    Historically this silently returned an admin context (fail-open).
    Now it refuses unless the operator explicitly opted into dev mode.
    """
    if not dev_open:
        raise AuthError(
            403,
            "No API keys configured and GENUI_DEV_OPEN is not set — refusing to "
            "serve (fail-closed). Configure CLIENT_API_KEYS / ADMIN_API_KEYS for "
            "production, or set GENUI_DEV_OPEN=1 for local development only.",
        )
    return AuthContext(tenant=DEFAULT_TENANT, is_admin=True, key_fingerprint="open")
