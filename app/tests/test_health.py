"""The readiness endpoint the reverse proxy and the container healthcheck use."""

from unittest import mock

from django.test import TestCase

from troopconnect import health

HEALTHZ_URL = "/healthz"


class HealthzTest(TestCase):
    def test_ready_when_every_dependency_answers(self):
        response = self.client.get(HEALTHZ_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"database": "ok", "cache": "ok"})

    def test_not_ready_when_the_database_is_unreachable(self):
        with mock.patch.object(health, "connection") as connection:
            connection.cursor.side_effect = OSError("database is down")

            response = self.client.get(HEALTHZ_URL)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["database"], "error")
        # The cache is still fine, and saying so is what makes the endpoint
        # worth reading when something is wrong.
        self.assertEqual(response.json()["cache"], "ok")

    def test_not_ready_when_the_cache_is_unreachable(self):
        with mock.patch.object(health, "cache") as cache:
            cache.set.side_effect = OSError("redis is down")

            response = self.client.get(HEALTHZ_URL)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["cache"], "error")

    def test_a_failing_cache_probe_is_not_mistaken_for_a_working_one(self):
        with mock.patch.object(health, "cache") as cache:
            cache.get.return_value = None

            response = self.client.get(HEALTHZ_URL)

        self.assertEqual(response.status_code, 503)

    def test_it_never_reports_the_error_itself(self):
        """This endpoint is public, so it answers only whether each is up."""
        with mock.patch.object(health, "connection") as connection:
            connection.cursor.side_effect = OSError("relation \"members\" does not exist")

            response = self.client.get(HEALTHZ_URL)

        self.assertEqual(
            sorted(response.json()), ["cache", "database"]
        )
        self.assertNotIn("members", response.content.decode())

    def test_it_is_reachable_without_logging_in(self):
        self.assertEqual(self.client.get(HEALTHZ_URL).status_code, 200)

    def test_it_is_not_cached(self):
        response = self.client.get(HEALTHZ_URL)

        self.assertIn("no-cache", response.headers.get("Cache-Control", ""))

    def test_it_only_answers_get(self):
        self.assertEqual(self.client.post(HEALTHZ_URL).status_code, 405)
