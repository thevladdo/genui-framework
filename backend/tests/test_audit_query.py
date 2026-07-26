"""
Tests for the audit read path.

The invariants:
- an audit event that was written is findable by tenant, user and date
  (the DPO question: "what did user X see on day Z?");
- tenants never read each other's trail (the query is tenant-scoped by
  the key, the filter is not optional);
- newest first, paginated, rotated files included;
- the production default (logger sink, external log pipeline) answers
  "not queryable here" explicitly instead of a silent empty result;
- the zone_render audit line records what the guarantee chain removed.

Runnable with `python3 -m unittest discover -s tests` from backend/.
The endpoint tests need fastapi (backend venv); they skip in the
pure-stdlib shell interpreter.
"""

import json
import logging
import os
import tempfile
import time
import unittest

from utils.audit import AuditLogger, AuditReader, FileAuditReader

try: 
    import api.audit_router as audit_router
    import api.zone_router as zone_router
    import auth.dependencies as auth_deps
    from auth.keys import AuthContext
    from config import settings

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


class TestFileAuditReader(unittest.TestCase):
    """Round-trip: what AuditLogger writes, FileAuditReader finds."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "audit.jsonl")
        self.logger = AuditLogger(path=self.path)

    def tearDown(self):
        for handler in (self.logger._file_logger or logging.Logger("x")).handlers:
            handler.close()
        self.tmp.cleanup()

    def query(self, tenant="acme", **kw):
        return FileAuditReader(self.path).query(tenant, **kw)

    def test_written_event_findable_by_tenant_user_and_date(self):
        """The DPO question: what did user X see on day Z."""
        self.logger.log("zone_render", tenant="acme", user_id="u1", zone_id="hero")
        today = time.strftime("%Y-%m-%d")

        result = self.query(user_id="u1", date_from=today, date_to=today)

        self.assertEqual(len(result["entries"]), 1)
        entry = result["entries"][0]
        self.assertEqual(entry["tenant"], "acme")
        self.assertEqual(entry["user_id"], "u1")
        self.assertEqual(entry["zone_id"], "hero")
        self.assertFalse(result["has_more"])

    def test_cross_tenant_isolation(self):
        """Same user_id in two tenants: each tenant sees only its rows."""
        self.logger.log("zone_render", tenant="acme", user_id="shared-id")
        self.logger.log("zone_render", tenant="globex", user_id="shared-id")

        result = self.query(tenant="acme", user_id="shared-id")
        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(result["entries"][0]["tenant"], "acme")

        self.assertEqual(self.query(tenant="initech")["entries"], [])

    def test_zone_event_and_date_filters(self):
        self.logger.log("zone_render", tenant="acme", zone_id="hero")
        self.logger.log("zone_render", tenant="acme", zone_id="sidebar")
        self.logger.log("profile_delete", tenant="acme", user_id="u1")

        by_zone = self.query(zone_id="hero")
        self.assertEqual([e["zone_id"] for e in by_zone["entries"]], ["hero"])

        by_event = self.query(event="profile_delete")
        self.assertEqual(len(by_event["entries"]), 1)
        self.assertEqual(by_event["entries"][0]["event"], "profile_delete")

        self.assertEqual(self.query(date_from="9999-12-31")["entries"], [])
        self.assertEqual(self.query(date_to="2000-01-01")["entries"], [])

    def test_newest_first_and_pagination(self):
        for i in range(5):
            self.logger.log("zone_render", tenant="acme", user_id=f"u{i}")

        page = self.query(limit=2)
        self.assertEqual([e["user_id"] for e in page["entries"]], ["u4", "u3"])
        self.assertTrue(page["has_more"])

        page2 = self.query(limit=2, offset=2)
        self.assertEqual([e["user_id"] for e in page2["entries"]], ["u2", "u1"])
        self.assertTrue(page2["has_more"])

        page3 = self.query(limit=2, offset=4)
        self.assertEqual([e["user_id"] for e in page3["entries"]], ["u0"])
        self.assertFalse(page3["has_more"])

    def test_rotated_files_are_scanned_after_the_live_one(self):
        """RotatingFileHandler moves older lines to audit.jsonl.1: they
        must still be findable, after the newer live-file rows."""
        with open(f"{self.path}.1", "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": "2026-01-01T00:00:00+0000",
                "event": "zone_render", "tenant": "acme", "user_id": "old",
            }) + "\n")
        self.logger.log("zone_render", tenant="acme", user_id="new")

        result = self.query()
        self.assertEqual([e["user_id"] for e in result["entries"]], ["new", "old"])

    def test_corrupted_line_is_skipped(self):
        """A truncated write (crash mid-line) must not break the query."""
        self.logger.log("zone_render", tenant="acme", user_id="ok")
        with open(self.path, "a", encoding="utf-8") as f:
            f.write('{"truncated": \n')
            f.write("not json at all\n")

        result = self.query()
        self.assertEqual([e["user_id"] for e in result["entries"]], ["ok"])

    def test_missing_file_is_an_empty_result(self):
        reader = FileAuditReader(os.path.join(self.tmp.name, "nope.jsonl"))
        self.assertEqual(reader.query("acme"), {"entries": [], "has_more": False})


class TestLoggerSinkReader(unittest.TestCase):
    """The production default is honest about not being queryable."""

    def test_not_queryable_and_says_so(self):
        reader = AuditReader()
        self.assertFalse(reader.queryable)
        self.assertTrue(reader.note)
        self.assertEqual(reader.query("acme"), {"entries": [], "has_more": False})


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class TestAuditEndpoint(unittest.TestCase):
    ADMIN = None

    @classmethod
    def setUpClass(cls):
        cls.ADMIN = AuthContext(tenant="acme", is_admin=True, key_fingerprint="afp")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "audit.jsonl")
        self._saved_path = settings.audit_log_path
        settings.audit_log_path = self.path

    def tearDown(self):
        settings.audit_log_path = self._saved_path
        self.tmp.cleanup()

    def _query(self, **kw):
        params = dict(
            user_id=None, zone_id=None, event=None,
            date_from=None, date_to=None, limit=50, offset=0,
        )
        params.update(kw)
        return audit_router.query_audit(auth=self.ADMIN, **params)

    def test_endpoint_is_scoped_to_the_key_tenant(self):
        writer = AuditLogger(path=self.path)
        writer.log("zone_render", tenant="acme", user_id="u1")
        writer.log("zone_render", tenant="globex", user_id="u1")
        for handler in writer._file_logger.handlers:
            handler.close()

        body = self._query(user_id="u1")
        self.assertTrue(body["queryable"])
        self.assertEqual(body["source"], "file")
        self.assertEqual([e["tenant"] for e in body["entries"]], ["acme"])

    def test_logger_sink_default_reports_unqueryable(self):
        settings.audit_log_path = None
        body = self._query()
        self.assertFalse(body["queryable"])
        self.assertEqual(body["source"], "log-pipeline")
        self.assertIn("pipeline", body["note"])
        self.assertEqual(body["entries"], [])


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class TestRenderAuditSanitization(unittest.TestCase):
    """The audit line must record what the guarantee chain removed."""

    def test_audit_render_includes_sanitization(self):
        recorded = []

        class _RecordingAudit:
            def log(self, event, tenant, user_id=None, **payload):
                recorded.append({"event": event, "tenant": tenant, **payload})

        saved = auth_deps._audit_logger
        auth_deps._audit_logger = _RecordingAudit()
        try:
            auth = AuthContext(tenant="acme", is_admin=False, key_fingerprint="cfp")
            request = zone_router.ZoneRenderRequest(zone_id="hero", base_prompt="x")
            sanitization = {
                "removed_urls": ["https://invented.example"],
                "dropped_components": [],
                "removed_numbers": [],
                "policy_violations": [],
            }
            payload = {
                "render_id": "r1",
                "components": [],
                "personalization_applied": False,
                "meta": {"sanitization": sanitization},
            }
            zone_router._audit_render(auth, request, payload, {"status": "miss"})
        finally:
            auth_deps._audit_logger = saved

        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["sanitization"], sanitization)


if __name__ == "__main__":
    unittest.main()
