"""Tests for Groq 429 / rate-limit handling.

Covers, against the *captured* provider behaviour (a per-DAILY-token quota of
200k that a free-tier key hits, distinct from the 8000 TPM window):

* dimension classification (TPD vs TPM vs RPM) and `retry-after` parsing,
* `_raise_groq_error` marking a daily quota as permanent (no blind retry) and a
  TPM/RPM 429 as transient with its `retry_after` + kind attached,
* `_call_with_retry` respecting the provider's `retry-after`, bounding the wait,
  adding jitter, never retrying a permanent error, and exhausting attempts,
* the shared token bucket debitting atomically under concurrency (no bypass).
"""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services import llm


class FakeRateLimitError(Exception):
    """Mimics openai.APIStatusError for a Groq 429 (status + body + headers)."""

    def __init__(self, message, *, status_code=429, body=None, headers=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.response = SimpleNamespace(headers=headers or {})


# Real captured Groq bodies (sanitised to the rate-limit clause + limit numbers).
TPD_BODY = {
    "error": {
        "message": (
            "Rate limit reached for model `openai/gpt-oss-120b` in organization "
            "`org_x` service tier `on_demand` on tokens per day (TPD): Limit "
            "200000, Used 197864, Requested 6388. Please try again in 30m36s."
        ),
        "type": "tokens",
        "code": "rate_limit_exceeded",
    }
}
TPD_HEADERS = {"retry-after": "2220", "x-ratelimit-limit-tokens": "8000"}

TPM_BODY = {
    "error": {
        "message": (
            "Rate limit reached for model `openai/gpt-oss-120b` on tokens per "
            "minute (TPM): Limit 8000, Requested 9515, please reduce your "
            "message size and try again."
        ),
        "type": "tokens",
        "code": "rate_limit_exceeded",
    }
}
TPM_HEADERS = {"retry-after": "18", "x-ratelimit-limit-tokens": "8000"}

RPM_BODY = {
    "error": {
        "message": (
            "Rate limit reached for model `openai/gpt-oss-120b` on requests per "
            "minute (RPM): Limit 30, Requested 31."
        ),
        "type": "requests",
        "code": "rate_limit_exceeded",
    }
}
RPM_HEADERS = {"retry-after": "22", "x-ratelimit-limit-requests": "30"}


def _settings(**overrides):
    base = dict(
        LLM_PROVIDER="groq",
        LLM_API_KEY="gsk_test",
        LLM_MODEL="openai/gpt-oss-120b",
        LLM_BASE_URL="https://api.groq.com/openai/v1",
        LLM_MAX_TOKENS=2000,
        LLM_MAX_RETRIES=2,
        LLM_RETRY_BACKOFF_SECONDS=1.0,
        LLM_RATE_LIMIT_BACKOFF_SECONDS=12.0,
        LLM_RATE_LIMIT_BACKOFF_MAX_SECONDS=45.0,
        LLM_RATE_LIMIT_RETRIES=2,
        LLM_TOKEN_BUDGET_PER_MINUTE=8000,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class RateLimitClassificationTests(unittest.TestCase):
    def test_daily_quota_is_classified_as_daily(self):
        err = FakeRateLimitError("rl", body=TPD_BODY, headers=TPD_HEADERS)
        kind, retry_after = llm._classify_rate_limit(err)
        self.assertEqual(kind, "daily")
        self.assertEqual(retry_after, 2220.0)

    def test_tpm_is_classified_as_tpm(self):
        err = FakeRateLimitError("rl", body=TPM_BODY, headers=TPM_HEADERS)
        kind, retry_after = llm._classify_rate_limit(err)
        self.assertEqual(kind, "tpm")
        self.assertEqual(retry_after, 18.0)

    def test_rpm_is_classified_as_rpm(self):
        err = FakeRateLimitError("rl", body=RPM_BODY, headers=RPM_HEADERS)
        kind, _ = llm._classify_rate_limit(err)
        self.assertEqual(kind, "rpm")

    def test_retry_after_ms_is_converted_to_seconds(self):
        err = FakeRateLimitError(
            "rl", body=TPM_BODY, headers={"retry-after-ms": "1500"}
        )
        _, retry_after = llm._classify_rate_limit(err)
        self.assertEqual(retry_after, 1.5)


class RaiseGroqErrorTests(unittest.TestCase):
    def setUp(self):
        self.settings = patch.object(llm, "settings", _settings())
        self.settings.start()
        self.addCleanup(self.settings.stop)

    def test_daily_429_is_permanent_with_actionable_message(self):
        err = FakeRateLimitError("rl", body=TPD_BODY, headers=TPD_HEADERS)
        with self.assertRaises(llm.LLMError) as ctx:
            llm._raise_groq_error(err)
        e = ctx.exception
        # Not transient: a per-day quota cannot recover in a 45s backoff, so it
        # must not be blind-retried.
        self.assertFalse(e.transient)
        self.assertIn("daily token quota", str(e))

    def test_tpm_429_is_transient_with_kind_and_retry_after(self):
        err = FakeRateLimitError("rl", body=TPM_BODY, headers=TPM_HEADERS)
        with self.assertRaises(llm.LLMError) as ctx:
            llm._raise_groq_error(err)
        e = ctx.exception
        self.assertTrue(e.transient)
        self.assertEqual(e.rate_limit_kind, "tpm")
        self.assertEqual(e.retry_after, 18.0)


class CallWithRetryTests(unittest.TestCase):
    def _run(self, fn, **settings_overrides):
        slept = []
        with patch.object(llm, "settings", _settings(**settings_overrides)), \
             patch.object(llm.time, "sleep", side_effect=slept.append), \
             patch.object(llm.random, "random", return_value=0.5):
            try:
                result = llm._call_with_retry(fn)
            except llm.LLMError as e:
                return ("raised", e, slept)
            return ("ok", result, slept)

    def test_transient_rate_limit_respects_provider_retry_after(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise llm.LLMError(
                    "rate limited", transient=True,
                    retry_after=20.0, rate_limit_kind="tpm",
                )
            return "ok"

        outcome, result, slept = self._run(flaky)
        self.assertEqual(outcome, "ok")
        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 2)
        # retry_after=20 (below the 45s cap) with jitter factor 1.0 -> ~20s.
        self.assertAlmostEqual(slept[0], 20.0, delta=0.5)

    def test_retry_after_is_bounded_by_cap(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                # Provider asks to wait 5 minutes; we must NOT sleep that long.
                raise llm.LLMError(
                    "rate limited", transient=True,
                    retry_after=300.0, rate_limit_kind="rpm",
                )
            return "ok"

        outcome, _, slept = self._run(flaky, LLM_RATE_LIMIT_BACKOFF_MAX_SECONDS=45.0)
        self.assertEqual(outcome, "ok")
        self.assertLessEqual(slept[0], 46.0)  # capped, plus jitter headroom

    def test_daily_quota_error_is_not_retried(self):
        calls = {"n": 0}

        def always_daily():
            calls["n"] += 1
            raise llm.LLMError(
                "daily quota exhausted", transient=False, rate_limit_kind="daily"
            )

        outcome, err, slept = self._run(always_daily)
        self.assertEqual(outcome, "raised")
        self.assertEqual(calls["n"], 1)  # exactly one attempt
        self.assertEqual(slept, [])      # no blind sleep

    def test_transient_retry_exhaustion_raises_after_attempts(self):
        calls = {"n": 0}

        def always_transient():
            calls["n"] += 1
            raise llm.LLMError("connection reset", transient=True)

        outcome, err, _ = self._run(always_transient, LLM_MAX_RETRIES=2)
        self.assertEqual(outcome, "raised")
        # initial + 2 retries = 3 attempts, then give up.
        self.assertEqual(calls["n"], 3)

    def test_permanent_error_is_not_retried(self):
        calls = {"n": 0}

        def bad_key():
            calls["n"] += 1
            raise llm.LLMError("invalid api key", transient=False)

        outcome, _, slept = self._run(bad_key)
        self.assertEqual(outcome, "raised")
        self.assertEqual(calls["n"], 1)
        self.assertEqual(slept, [])


class SharedThrottleConcurrencyTests(unittest.TestCase):
    def test_bucket_debits_are_atomic_under_concurrency(self):
        """Two racing callers must both debit the shared window (no lost update),
        proving concurrent requests cannot double-spend the same tokens."""
        bucket = llm._TokenBucket()
        t0 = 5000.0
        with patch("time.monotonic", return_value=t0):
            # Prime a full 10000-token window from "provider headers".
            bucket.sync(10000, 10000, None, 10000)
            barrier = threading.Barrier(2)

            def worker():
                barrier.wait()
                bucket.acquire(4000, 10000)

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # 10000 - 4000 - 4000 = 2000. If the debit weren't atomic, one thread
        # would read 10000 before the other debited and the total would be 6000.
        self.assertAlmostEqual(bucket._remaining, 2000.0)

    def test_acquire_blocks_when_window_is_exhausted(self):
        """An exhausted window makes acquire wait for a refill, not overshoot."""
        bucket = llm._TokenBucket()
        t0 = 1000.0
        clock = {"now": t0}

        def fake_monotonic():
            return clock["now"]

        with patch("time.monotonic", side_effect=fake_monotonic), \
             patch.object(llm.time, "sleep", side_effect=lambda s: clock.__setitem__(
                 "now", clock["now"] + s)):
            bucket.sync(100, 100, None, 6000)  # 100 tokens left, 6000/min refill
            # Needs 6000 tokens but only 100 remain -> waits ~1s of refill.
            bucket.acquire(6000, 6000)
            # After the wait, the debit succeeded and remaining reflects it.
            self.assertGreaterEqual(bucket._remaining, 0)


if __name__ == "__main__":
    unittest.main()
