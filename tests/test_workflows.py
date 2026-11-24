"""Offline API checks using only Python's standard library and an in-memory DB."""
import json
import unittest
from urllib.parse import urlencode
from unittest.mock import patch

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import main
import modules.evidence as evidence
from database import Base
from modules.evidence import ResearchCaseCreate, create_research_case


class AtlasWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.session_factory = sessionmaker(bind=cls.engine, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.original_session_factory = evidence.SessionLocal
        self.original_create_database = main.create_database
        self.original_search = main.search_public_sources
        evidence.SessionLocal = self.session_factory
        main.create_database = lambda: Base.metadata.create_all(bind=self.engine)

        def fake_search(query, limit, backend=None):
            if query.startswith("site:"):
                domain = query.split()[0].removeprefix("site:")
                snippet = "Contact alice@example.org or call +1 (555) 123-4567"
                url = f"https://{domain}/org/repo/issues/private-record"
            else:
                snippet = f"Public result for {query}"
                url = "https://example.org/research"
            return [{
                "title": "Example public source",
                "url": url,
                "snippet": snippet,
                "verification_status": "unverified",
            }][:limit]

        main.search_public_sources = fake_search
        main.startup()
        self.case = create_research_case(ResearchCaseCreate(
            title="Authorized sample review",
            question="What public sources support this sample research question?",
            scope="Review only public web sources for the sample topic provided in tests.",
            authorization_basis="self_audit",
            authorized=True,
        ))
        self.case_id = self.case["id"]

    def tearDown(self):
        evidence.SessionLocal = self.original_session_factory
        main.create_database = self.original_create_database
        main.search_public_sources = self.original_search

    def request(self, method, path, payload=None):
        """Make a small ASGI request without installing an HTTP test package."""
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        path_only, _, query = path.partition("?")
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path_only,
            "raw_path": path_only.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": [(b"content-type", b"application/json")],
            "client": ("test", 1234),
            "server": ("test", 80),
        }
        events = [{"type": "http.request", "body": body, "more_body": False}]
        sent = []

        async def receive():
            if events:
                return events.pop(0)
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        import asyncio

        asyncio.run(main.app(scope, receive, send))
        start = next(item for item in sent if item["type"] == "http.response.start")
        content = b"".join(
            item.get("body", b"") for item in sent if item["type"] == "http.response.body"
        )
        return start["status"], content

    def test_home_and_health(self):
        status, content = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"ATLAS", content)
        self.assertIn(b"Removal tracker", content)
        self.assertIn(b"case-create-form", content)
        self.assertIn(b"case-activity-list", content)
        self.assertIn(b"All saved records", content)
        self.assertIn(b"username is sent to GitHub", content)
        self.assertIn(b"Amazon India", content)
        self.assertIn(b"Flipkart", content)
        self.assertIn(b"cannot inspect an account or its orders/messages", content)
        self.assertIn(b"Not checked yet", content)
        status, content = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(content)["status"], "healthy")
        status, content = self.request("GET", "/static/style.css")
        self.assertEqual(status, 200)
        self.assertIn(b"--green", content)
        status, content = self.request("GET", "/static/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"/research?", content)

    def test_research_cases_record_scope_and_closed_cases_block_collection(self):
        status, content = self.request("GET", "/cases")
        self.assertEqual(status, 200)
        cases = json.loads(content)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["id"], self.case_id)
        self.assertEqual(cases[0]["authorization_basis"], "self_audit")
        status, content = self.request("GET", f"/cases/{self.case_id}/activity")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(content)[0]["event_type"], "case_created")

        status, content = self.request("POST", "/cases", {
            "title": "  Public report review  ",
            "question": "Which public sources support the report's date?",
            "scope": "Review the report and public government publications only.",
            "authorization_basis": "official_duties",
            "authorized": True,
        })
        self.assertEqual(status, 201)
        created = json.loads(content)
        self.assertEqual(created["title"], "Public report review")
        self.assertEqual(created["status"], "open")
        self.assertTrue(created["authorized_at"])

        status, _ = self.request("POST", "/cases", {
            "title": "bad", "question": "Too short", "scope": "Too short",
            "authorization_basis": "public_interest", "authorized": False,
        })
        self.assertEqual(status, 422)

        status, content = self.request("PATCH", f"/cases/{self.case_id}", {"status": "closed"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(content)["status"], "closed")
        status, content = self.request("GET", f"/cases/{self.case_id}/activity")
        activity = json.loads(content)
        self.assertEqual(status, 200)
        self.assertIn("case_closed", [item["event_type"] for item in activity])
        status, content = self.request("GET", f"/research?q=public+research&case_id={self.case_id}")
        self.assertEqual(status, 409)
        self.assertIn("closed", json.loads(content)["detail"])
        status, _ = self.request("POST", "/evidence", {
            "case_id": self.case_id,
            "title": "Late source",
            "source_url": "https://example.org/late-source",
            "description": "This should be blocked after closure.",
            "source_type": "manual",
        })
        self.assertEqual(status, 409)

    def test_manual_evidence_can_be_added_and_filtered(self):
        status, content = self.request(
            "POST",
            "/evidence",
            {
                "case_id": self.case_id,
                "title": "Official public report",
                "source_url": "https://example.org/report",
                "description": "A note for later review.",
                "source_type": "manual",
            },
        )
        self.assertEqual(status, 200)
        created = json.loads(content)
        self.assertEqual(created["verification_status"], "unverified")
        self.assertEqual(created["case_id"], self.case_id)
        status, content = self.request("GET", f"/cases/{self.case_id}/activity")
        self.assertIn("source_added", [item["event_type"] for item in json.loads(content)])
        status, content = self.request("GET", "/evidence?search=Official")
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(content)), 1)

    def test_search_saves_source_and_review_status(self):
        status, content = self.request("GET", "/search?" + urlencode({"q": "public research", "case_id": self.case_id}))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(content)["saved_to_database"], 1)

        status, content = self.request("GET", "/evidence")
        records = json.loads(content)
        self.assertEqual(status, 200)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["verification_status"], "unverified")

        status, content = self.request(
            "PATCH",
            f"/evidence/{records[0]['id']}/verification",
            {"status": "reviewed", "note": "Opened the page and checked its publisher."},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(content)["verification_status"], "reviewed")
        status, content = self.request("GET", f"/cases/{self.case_id}/activity")
        self.assertIn("source_reviewed", [item["event_type"] for item in json.loads(content)])
        self.assertNotIn("publisher", json.dumps(json.loads(content)))

    def test_multi_source_research_shows_separate_coverage(self):
        wiki = [{
            "title": "Example encyclopedia page",
            "url": "https://en.wikipedia.org/wiki/Example",
            "snippet": "An encyclopedia entry.",
        }]
        wikidata = [{
            "title": "Example item",
            "url": "https://www.wikidata.org/wiki/Q123",
            "snippet": "A structured knowledge item.",
        }]
        with patch("main.search_wikipedia", return_value=wiki), patch(
            "main.search_wikidata", return_value=wikidata
        ):
            status, content = self.request("GET", f"/research?q=public+research&case_id={self.case_id}")
        self.assertEqual(status, 200)
        body = json.loads(content)
        self.assertEqual(body["results_count"], 3)
        self.assertEqual([item["status"] for item in body["coverage"]], ["results"] * 3)
        self.assertEqual(body["saved_to_database"], 3)
        self.assertEqual({item["source"] for item in body["results"]}, {
            "Yahoo web index", "Wikipedia", "Wikidata"
        })

    def test_multi_source_research_reports_one_provider_failure(self):
        with patch("main.search_wikipedia", side_effect=TimeoutError()), patch(
            "main.search_wikidata", return_value=[]
        ):
            status, content = self.request("GET", f"/research?q=public+research&case_id={self.case_id}&save=false")
        self.assertEqual(status, 200)
        body = json.loads(content)
        self.assertEqual([item["status"] for item in body["coverage"]], [
            "results", "unavailable", "no_results"
        ])
        self.assertEqual(body["saved_to_database"], 0)

    def test_search_can_check_provider_without_saving_results(self):
        status, content = self.request(
            "GET", "/search?" + urlencode({"q": "public research", "save": "false", "case_id": self.case_id})
        )
        self.assertEqual(status, 200)
        body = json.loads(content)
        self.assertEqual(body["results_count"], 1)
        self.assertEqual(body["saved_to_database"], 0)
        self.assertEqual(body["provider"], "Yahoo via DDGS")
        status, content = self.request("GET", "/evidence")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(content), [])

    def test_long_provider_title_is_kept_as_usable_evidence(self):
        provider_result = [{
            "title": "A" * 400,
            "url": "https://example.org/source",
            "snippet": "A public page result",
        }]
        with patch("main.search_public_sources", return_value=provider_result):
            status, content = self.request("GET", f"/search?q=long+title+example&case_id={self.case_id}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(content)["saved_to_database"], 1)
        status, content = self.request("GET", "/evidence")
        record = json.loads(content)[0]
        self.assertEqual(status, 200)
        self.assertEqual(len(record["title"]), 300)
        self.assertTrue(record["title"].endswith("..."))
        status, content = self.request("GET", f"/cases/{self.case_id}/activity")
        serialized_activity = json.dumps(json.loads(content))
        self.assertIn("public_search", serialized_activity)
        self.assertNotIn("long title example", serialized_activity)

    def test_exposure_check_requires_authorisation_and_username_only(self):
        status, _ = self.request(
            "POST", "/exposure-check", {"platform": "GitHub", "username": "sample_user", "case_id": self.case_id}
        )
        self.assertEqual(status, 422)
        status, _ = self.request(
            "POST",
            "/exposure-check",
            {"platform": "GitHub", "username": "person@example.org", "case_id": self.case_id, "authorized": True},
        )
        self.assertEqual(status, 422)

        with patch("main.check_github_profile", return_value={
            "status": "found", "message": "GitHub returned a public profile.",
            "profile_url": "https://github.com/sample_user",
        }):
            status, content = self.request(
                "POST",
                "/exposure-check",
                {"platform": "GitHub", "username": "sample_user", "case_id": self.case_id, "authorized": True},
            )
        self.assertEqual(status, 200)
        result = json.loads(content)
        self.assertEqual(result["provider"], "Multiple web indexes via DDGS")
        self.assertEqual(result["direct_check"]["status"], "found")
        self.assertEqual(result["index_check"]["status"], "results")
        self.assertEqual([item["provider"] for item in result["index_check"]["providers"]], [
            "Yahoo", "Bing", "Brave", "Google"
        ])
        self.assertEqual(result["alerts_detected"], 2)
        self.assertEqual(result["alerts_saved"], 2)
        self.assertNotIn("username", result)
        serialized = json.dumps(result)
        self.assertNotIn("alice@example.org", serialized)
        self.assertNotIn("555", serialized)
        self.assertNotIn("private-record", serialized)
        self.assertTrue(all("page_url" not in alert and "snippet" not in alert for alert in result["alerts"]))
        self.assertIn("github.com", result["alerts"][0]["report_url"])
        self.assertNotIn("private-record", result["alerts"][0]["report_url"])

        status, content = self.request("GET", f"/exposure-alerts?case_id={self.case_id}")
        self.assertEqual(status, 200)
        alerts = json.loads(content)
        self.assertEqual(len(alerts), 2)
        self.assertTrue(all(alert["source_domain"] == "github.com" for alert in alerts))
        self.assertNotIn("sample_user", json.dumps(alerts))

        status, content = self.request(
            "PATCH", f"/exposure-alerts/{alerts[0]['id']}", {"status": "reported"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(content)["status"], "reported")
        status, content = self.request("GET", f"/cases/{self.case_id}/activity")
        activity = json.loads(content)
        self.assertIn("alert_status_changed", [item["event_type"] for item in activity])
        self.assertNotIn("sample_user", json.dumps(activity))

    def test_exposure_check_can_run_without_saving_alerts(self):
        status, content = self.request(
            "POST",
            "/exposure-check?save=false",
            {"platform": "Instagram", "username": "sample_user", "case_id": self.case_id, "authorized": True},
        )
        self.assertEqual(status, 200)
        body = json.loads(content)
        self.assertEqual(body["direct_check"]["status"], "not_available")
        self.assertEqual(body["index_check"]["status"], "results")
        self.assertEqual(body["results_count"], 1)
        self.assertEqual(body["alerts_detected"], 2)
        self.assertEqual(body["alerts_saved"], 0)
        status, content = self.request("GET", f"/cases/{self.case_id}/activity")
        activity = json.loads(content)
        check = next(item for item in activity if item["event_type"] == "exposure_check")
        self.assertEqual(check["details"]["platform"], "Instagram")
        self.assertNotIn("sample_user", json.dumps(activity))
        status, content = self.request("GET", f"/exposure-alerts?case_id={self.case_id}")
        self.assertEqual(json.loads(content), [])

    def test_exposure_check_supports_indian_shopping_platforms(self):
        status, content = self.request(
            "POST",
            "/exposure-check?save=false",
            {"platform": "Flipkart", "username": "sample_user", "case_id": self.case_id, "authorized": True},
        )
        self.assertEqual(status, 200)
        body = json.loads(content)
        self.assertEqual(body["platform"], "Flipkart")
        self.assertEqual(body["index_check"]["status"], "results")
        self.assertEqual(body["alerts_detected"], 2)
        self.assertNotIn("sample_user", json.dumps(body))

    def test_exposure_check_rejects_unknown_platform(self):
        status, content = self.request(
            "POST",
            "/exposure-check",
            {"platform": "Unknown Marketplace", "username": "sample_user", "case_id": self.case_id, "authorized": True},
        )
        self.assertEqual(status, 422)

    def test_exposure_check_accepts_at_prefix_and_reports_empty_index(self):
        main.search_public_sources = lambda query, limit, backend=None: []
        with patch("main.check_github_profile", return_value={
            "status": "not_found", "message": "No public profile.", "profile_url": None,
        }) as direct_check:
            status, content = self.request(
                "POST", "/exposure-check?save=false",
                {"platform": "GitHub", "username": "@missing_account", "case_id": self.case_id, "authorized": True},
            )
        self.assertEqual(status, 200)
        direct_check.assert_called_once_with("missing_account")
        body = json.loads(content)
        self.assertEqual(body["results_count"], 0)
        self.assertEqual(body["index_check"]["status"], "no_results")
        self.assertIn("not proof", body["index_check"]["note"])

    def test_old_database_upgrade_keeps_existing_evidence(self):
        legacy_engine = create_engine("sqlite://")
        original_engine = database.engine
        try:
            with legacy_engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE TABLE evidence ("
                    "id INTEGER PRIMARY KEY, title VARCHAR(300) NOT NULL, "
                    "source_url TEXT NOT NULL, description TEXT NOT NULL, "
                    "source_type VARCHAR(100) NOT NULL, "
                    "verification_status VARCHAR(30) NOT NULL, recorded_at DATETIME NOT NULL)"
                )
                connection.exec_driver_sql(
                    "INSERT INTO evidence VALUES "
                    "(1, 'Saved source', 'https://example.org', 'Old note', "
                    "'public_website', 'unverified', '2026-01-01 00:00:00')"
                )
            database.engine = legacy_engine
            database.create_database()
            with legacy_engine.connect() as connection:
                row = connection.exec_driver_sql(
                    "SELECT id, title, description, case_id FROM evidence"
                ).one()
                columns = {
                    column["name"]
                    for column in inspect(legacy_engine).get_columns("evidence")
                }
            self.assertEqual(tuple(row), (1, "Saved source", "Old note", None))
            self.assertTrue({"verification_note", "reviewed_at", "search_query", "case_id"}.issubset(columns))
            self.assertIn("exposure_alerts", inspect(legacy_engine).get_table_names())
            self.assertIn("research_cases", inspect(legacy_engine).get_table_names())
            self.assertIn("case_activity", inspect(legacy_engine).get_table_names())
            self.assertIn("case_id", {column["name"] for column in inspect(legacy_engine).get_columns("exposure_alerts")})
        finally:
            database.engine = original_engine
            legacy_engine.dispose()


if __name__ == "__main__":
    unittest.main()
