import unittest
from unittest.mock import patch

from ddgs.exceptions import DDGSException

from modules.discovery import search_public_sources


class DiscoveryProviderTests(unittest.TestCase):
    def test_search_uses_yahoo_backend_and_certificate_bundle(self):
        captured = {}

        class FakeDDGS:
            def __init__(self, **options):
                captured["options"] = options

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def text(self, query, max_results, backend):
                captured["call"] = (query, max_results, backend)
                return [{"title": "Example result", "href": "https://example.org", "body": "A snippet"}]

        with patch("modules.discovery.DDGS", FakeDDGS):
            results = search_public_sources("  Python search  ", 3)

        self.assertTrue(captured["options"]["verify"].endswith("cacert.pem"))
        self.assertEqual(captured["call"], ("Python search", 3, "yahoo"))
        self.assertEqual(results[0]["url"], "https://example.org")

    def test_provider_empty_result_is_not_reported_as_server_failure(self):
        class EmptyDDGS:
            def __init__(self, **options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def text(self, *args, **kwargs):
                raise DDGSException("No results found.")

        with patch("modules.discovery.DDGS", EmptyDDGS):
            self.assertEqual(search_public_sources("ordinary query", 5), [])


if __name__ == "__main__":
    unittest.main()
