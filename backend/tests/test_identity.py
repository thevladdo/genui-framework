"""
Tests for signed user identity (HMAC tokens) and fail-closed auth.

Covers the two failures WP-01 prevents:
(a) a client-key holder reading/deleting/poisoning ANOTHER user's profile
    by changing the user_id (authorize_user_access);
(b) a deployment with no keys configured silently serving everyone as
    admin (open_mode_context fails CLOSED unless GENUI_DEV_OPEN is set).

Runnable with `python3 -m unittest discover -s tests` from backend/.
"""

import unittest

from auth.identity import (
    AuthError,
    UserTokenVerifier,
    authorize_user_access,
    open_mode_context,
    sign_user_token,
    verify_user_token,
)
from auth.keys import AuthContext

NOW = 1_700_000_000
SECRET = "s3cret-acme"


def _client(tenant="acme"):
    return AuthContext(tenant=tenant, is_admin=False, key_fingerprint="fp")


def _admin(tenant="acme"):
    return AuthContext(tenant=tenant, is_admin=True, key_fingerprint="fp")


class TestUserToken(unittest.TestCase):
    def test_roundtrip(self):
        token = sign_user_token(SECRET, "alice", "acme", now=NOW)
        claims = verify_user_token(SECRET, token, now=NOW)
        self.assertEqual(claims["user_id"], "alice")
        self.assertEqual(claims["tenant"], "acme")

    def test_expired_rejected(self):
        token = sign_user_token(SECRET, "alice", "acme", expires_in=60, now=NOW)
        self.assertIsNone(verify_user_token(SECRET, token, now=NOW + 61))

    def test_wrong_secret_rejected(self):
        token = sign_user_token(SECRET, "alice", "acme", now=NOW)
        self.assertIsNone(verify_user_token("other-secret", token, now=NOW))

    def test_tampered_payload_rejected(self):
        token = sign_user_token(SECRET, "alice", "acme", now=NOW)
        body, sig = token.rsplit(".", 1)
        forged = sign_user_token(SECRET, "bob", "acme", now=NOW).split(".")[0]
        self.assertIsNone(verify_user_token(SECRET, f"{forged}.{sig}", now=NOW))

    def test_garbage_tokens_rejected_without_exception(self):
        for garbage in ["", "not-a-token", "a.b", "a.b.c", None]:
            self.assertIsNone(verify_user_token(SECRET, garbage, now=NOW))


class TestUserTokenVerifier(unittest.TestCase):
    def test_verifies_subject_for_tenant(self):
        verifier = UserTokenVerifier("s3cret-acme:acme")
        token = sign_user_token("s3cret-acme", "alice", "acme", now=NOW)
        self.assertEqual(verifier.verify(token, "acme", now=NOW), "alice")

    def test_token_for_other_tenant_rejected(self):
        # Same secret configured for two tenants: the token's tenant claim
        # must still match the requesting tenant (no cross-tenant replay).
        verifier = UserTokenVerifier(["shared:acme", "shared:globex"])
        token = sign_user_token("shared", "alice", "globex", now=NOW)
        self.assertIsNone(verifier.verify(token, "acme", now=NOW))

    def test_unconfigured_tenant_not_enabled(self):
        verifier = UserTokenVerifier("s3cret-acme:acme")
        self.assertTrue(verifier.enabled_for("acme"))
        self.assertFalse(verifier.enabled_for("globex"))
        token = sign_user_token(SECRET, "alice", "globex", now=NOW)
        self.assertIsNone(verifier.verify(token, "globex", now=NOW))

    def test_secret_rotation_two_secrets_same_tenant(self):
        verifier = UserTokenVerifier("old:acme,new:acme")
        old_token = sign_user_token("old", "alice", "acme", now=NOW)
        new_token = sign_user_token("new", "alice", "acme", now=NOW)
        self.assertEqual(verifier.verify(old_token, "acme", now=NOW), "alice")
        self.assertEqual(verifier.verify(new_token, "acme", now=NOW), "alice")


class TestAuthorizeUserAccess(unittest.TestCase):
    """The shared guard used by /profile, /zone/render*, /query."""

    def setUp(self):
        self.verifier = UserTokenVerifier(f"{SECRET}:acme")

    def _authorize(self, auth, user_id, token, verifier=None, dev_open=False):
        authorize_user_access(
            auth, user_id, token,
            verifier=verifier if verifier is not None else self.verifier,
            dev_open=dev_open, now=NOW,
        )

    def test_matching_subject_allowed(self):
        token = sign_user_token(SECRET, "alice", "acme", now=NOW)
        self._authorize(_client(), "alice", token)  # must not raise

    def test_subject_a_cannot_access_profile_b(self):
        token = sign_user_token(SECRET, "alice", "acme", now=NOW)
        with self.assertRaises(AuthError) as ctx:
            self._authorize(_client(), "bob", token)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_missing_token_rejected_when_secret_configured(self):
        with self.assertRaises(AuthError) as ctx:
            self._authorize(_client(), "alice", None)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_admin_allowed_without_token(self):
        self._authorize(_admin(), "alice", None)  # must not raise

    def test_unconfigured_tenant_fails_closed(self):
        with self.assertRaises(AuthError) as ctx:
            self._authorize(_client("globex"), "alice", None, dev_open=False)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_unconfigured_tenant_open_only_in_explicit_dev_mode(self):
        self._authorize(_client("globex"), "alice", None, dev_open=True)

    def test_configured_secret_enforced_even_in_dev_mode(self):
        # Once a tenant has a secret, the contract is live: dev_open does
        # not bypass a failed verification for that tenant.
        token = sign_user_token(SECRET, "alice", "acme", now=NOW)
        with self.assertRaises(AuthError):
            self._authorize(_client(), "bob", token, dev_open=True)


class TestOpenModeFailsClosed(unittest.TestCase):
    """No API keys configured: refuse unless GENUI_DEV_OPEN is explicit."""

    def test_no_keys_and_no_dev_flag_refused(self):
        with self.assertRaises(AuthError) as ctx:
            open_mode_context(dev_open=False)
        self.assertEqual(ctx.exception.status_code, 403)
        # The message must tell the operator what to configure.
        self.assertIn("CLIENT_API_KEYS", ctx.exception.detail)
        self.assertIn("GENUI_DEV_OPEN", ctx.exception.detail)

    def test_explicit_dev_mode_keeps_old_open_behavior(self):
        ctx = open_mode_context(dev_open=True)
        self.assertTrue(ctx.is_admin)
        self.assertEqual(ctx.tenant, "default")


if __name__ == "__main__":
    unittest.main()
