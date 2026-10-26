"""
LLM provider wrapper.

Every other service (summarizer, risk_analyzer, chatbot) calls `complete()`
and never talks to a provider SDK directly. This keeps the model swappable
through LLM_PROVIDER / LLM_MODEL / LLM_API_KEY / LLM_BASE_URL.
"""
import json
import logging
import random
import re
import threading
import time

from app.config import settings

logger = logging.getLogger(__name__)

# Actual token usage reported by the provider for the most recent call on this
# thread. Lets the throttle refund any over-reservation once we learn the real
# cost, keeping pacing both safe (reserve a ceiling upfront) and fast (refund
# the unused margin).
_call_usage = threading.local()


class LLMError(Exception):
    """Provider error with an actionable message.

    `transient=True` marks errors worth retrying (rate limits, 5xx,
    timeouts, connection hiccups); permanent errors (bad key, missing
    package) are raised with `transient=False` and never retried.

    `retry_after` carries the provider's own `retry-after` hint (seconds)
    when available, so backoff can respect the real recovery window instead
    of guessing. `rate_limit_kind` distinguishes `tpm`/`rpm`/`daily` limits;
    `daily` is raised with `transient=False` because retrying cannot recover
    a per-day quota within the relevant window.
    """

    def __init__(
        self,
        message: str,
        *,
        transient: bool = False,
        retry_after: float | None = None,
        rate_limit_kind: str | None = None,
    ):
        super().__init__(message)
        self.transient = transient
        self.retry_after = retry_after
        self.rate_limit_kind = rate_limit_kind


_TRANSIENT_MARKERS = (
    "timeout", "timed out", "rate limit", "rate_limit", "resource_exhausted",
    "quota", "unavailable", "overloaded", "connection", "temporarily",
    "internal server", "503", "502", "504", "429",
)


def _looks_transient(error: Exception) -> bool:
    """Heuristic: is this provider error worth a bounded retry?"""
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    try:
        if status is not None and int(status) >= 500:
            return True
    except (TypeError, ValueError):
        pass
    message = str(error).lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


class _TokenBucket:
    """Client-side token-bucket limiter driven by the provider's live counters.

    Groq (and most OpenAI-compatible gateways) report three headers on every
    response: ``x-ratelimit-limit-tokens``, ``x-ratelimit-remaining-tokens``,
    and ``x-ratelimit-reset-tokens``. The window refills *continuously* — the
    reset interval is a couple of seconds, not a hard 60s cliff. So the right
    response to a small budget is adaptive backpressure: before each request,
    look at the real remaining tokens and sleep only the short time needed for
    the bucket to refill enough to cover the call. This tracks reality exactly
    instead of guessing cost from prompt length or waiting out a fixed backoff.

    When live headers are unavailable (other providers, tests, mocks) we fall
    back to a local leaky-bucket estimate that refills at budget/60 tokens/sec.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._tokens = 0.0
        self._last = None
        self._limit = None  # provider's real per-minute token limit
        self._remaining = None  # last reported remaining tokens
        self._reset = None  # last reported refill interval (seconds)
        self._remaining_at = None  # monotonic time of last header

    def acquire(self, cost: float, budget_per_minute: float) -> None:
        """Block until `cost` tokens are available, then debit them.

        `cost` is a conservative upper bound on the tokens the request will
        meter (prompt tokens + output ceiling).
        """
        if budget_per_minute <= 0:
            return
        # Clamp to what the window can ever hold: a single request can't
        # meter more than the whole budget, and _live_remaining is capped at
        # the limit — without this, a conservative estimate larger than the
        # limit would wait forever for tokens that can never arrive.
        cost = min(cost, self._limit or budget_per_minute)
        while True:
            wait = 0.0
            with self._lock:
                now = time.monotonic()
                remaining = self._live_remaining(now, budget_per_minute)
                if remaining >= cost:
                    self._remaining = remaining - cost
                    self._remaining_at = now
                    self._tokens = max(0.0, remaining - cost)
                    return
                # Sleep just long enough for the window to refill the deficit.
                refill_rate = self._refill_rate(budget_per_minute)
                wait = (cost - remaining) / refill_rate
            # Sleep in bounded slices so shutdown stays responsive and other
            # threads can interleave; re-check on each pass.
            time.sleep(max(0.05, min(wait, 5.0)))

    def _live_remaining(self, now: float, budget_per_minute: float) -> float:
        """Best available view of tokens remaining right now."""
        # Prefer the provider's own counter while it's fresh (<= a few seconds
        # old), advanced forward by the refill rate since it was reported.
        if self._remaining is not None and self._remaining_at is not None:
            age = now - self._remaining_at
            advanced = min(
                self._limit or budget_per_minute,
                self._remaining + age * self._refill_rate(budget_per_minute),
            )
            if age < 15.0:
                return advanced
        # No fresh header: local leaky bucket.
        if self._last is None:
            self._last = now
            self._tokens = budget_per_minute
        self._tokens = min(
            budget_per_minute,
            self._tokens + (now - self._last) * self._refill_rate(budget_per_minute),
        )
        self._last = now
        return self._tokens

    def _refill_rate(self, budget_per_minute: float) -> float:
        """Tokens refilled per second (steady-state).

        Groq meters a per-minute budget that refills *continuously* at
        ``limit / 60`` tokens per second (8000/min -> ~133 tok/s). The
        ``x-ratelimit-reset-tokens`` header reports the time to refill the
        *deficit* incurred by the last request, NOT a full-window period — so
        deriving rate as ``limit / reset`` would wildly overestimate it (e.g.
        reset=2.87s for a 383-token deficit gives 133 tok/s, but limit/reset
        would claim 2785 tok/s). We therefore ignore reset and use the
        steady-state per-second rate from the per-minute limit.
        """
        limit = self._limit or budget_per_minute
        return limit / 60.0

    def sync(self, remaining: float, limit: float | None, reset: float | None,
             budget_per_minute: float) -> None:
        """Adopt the provider's authoritative rate-limit headers.

        These are the single source of truth for the shared window; adopting
        them corrects any drift from our cost estimate. The header already
        accounts for the just-sent request, so we store it as-is and let
        ``_live_remaining`` advance it forward by the refill rate.
        """
        if budget_per_minute <= 0 or remaining < 0:
            return
        with self._lock:
            now = time.monotonic()
            if limit and limit > 0:
                self._limit = float(limit)
            if reset and reset > 0:
                self._reset = float(reset)
            cap = self._limit or budget_per_minute
            self._remaining = min(remaining, cap)
            self._remaining_at = now


def _sync_bucket_from_headers(headers) -> None:
    """Read Groq's rate-limit headers and sync the throttle to them.

    Defensive: headers may be absent (mocks, other providers) or malformed;
    never let rate-limit bookkeeping break a successful call.
    """
    if headers is None:
        return
    try:
        budget = float(getattr(settings, "LLM_TOKEN_BUDGET_PER_MINUTE", 0) or 0)
        if budget <= 0:
            return
        get = headers.get if hasattr(headers, "get") else (lambda _k: None)
        remaining = get("x-ratelimit-remaining-tokens")
        if remaining is None:
            return
        limit = get("x-ratelimit-limit-tokens")
        reset = get("x-ratelimit-reset-tokens")
        _throttle.sync(
            _parse_number(remaining),
            _parse_number(limit),
            _parse_duration(reset),
            budget,
        )
    except Exception:  # pragma: no cover - defensive
        pass


def _parse_tpm_overshoot(error) -> tuple[int | None, int | None]:
    """Extract `(Requested, Limit)` from a Groq 413 TPM size rejection.

    Groq's body reads `... on tokens per minute (TPM): Limit 8000, Requested
    9515, please reduce your message size...`. Returns `(None, None)` when the
    message doesn't carry those numbers (so callers fall back to re-raising).
    """
    import re as _re

    text = str(error)
    match = _re.search(r"Limit\s+(\d+),\s*Requested\s+(\d+)", text, _re.IGNORECASE)
    if not match:
        return None, None
    return int(match.group(2)), int(match.group(1))  # (requested, limit)


def _mark_rate_limited() -> None:
    """On a 429, reset the bucket to exhausted so acquire paces the retry.

    Groq's 429 body reports `x-ratelimit-remaining-tokens` as the full limit
    (not the true remaining), so adopting it would falsely refill the bucket
    and cause an immediate re-send / 429 cascade. We instead set remaining=0
    while keeping the real per-minute limit, forcing _throttle.acquire to wait
    for a genuine refill before the next attempt. `sync` stores 0 as-is
    (remaining < 0 is the only rejected value), and _live_remaining then
    advances from 0 at the steady-state refill rate.
    """
    try:
        budget = float(getattr(settings, "LLM_TOKEN_BUDGET_PER_MINUTE", 0) or 0)
        if budget <= 0:
            return
        _throttle.sync(0.0, _throttle._limit, None, budget)
    except Exception:  # pragma: no cover - defensive
        pass


def _parse_number(value) -> float | None:
    """Parse a numeric header, tolerating units like ``"7727"`` or ``"7.7k"``.

    Groq rate-limit token headers are plain integers today, but parsing
    defensively means a malformed value degrades to ``None`` (ignore) instead
    of aborting the whole sync via the caller's blanket ``except``.
    """
    if value is None:
        return None
    try:
        return float(str(value).strip().rstrip("s"))
    except (TypeError, ValueError):
        return None


def _parse_duration(value) -> float | None:
    """Parse a duration header like ``"2.047s"``, ``"840ms"``, or ``"1m"``.

    Groq reports ``x-ratelimit-reset-tokens`` as a human-readable duration,
    not a bare number. ``float("2.047s")`` raises ValueError, which previously
    aborted ``_sync_bucket_from_headers`` entirely (the blanket ``except``
    swallowed it) — so the throttle never adopted the provider's real headers
    and paced off stale local estimates, causing cascading 429s. Returns
    seconds, or ``None`` when unparseable.
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    try:
        if text.endswith("ms"):
            return float(text[:-2]) / 1000.0
        if text.endswith("s"):
            return float(text[:-1])
        if text.endswith("m"):
            return float(text[:-1]) * 60.0
        if text.endswith("h"):
            return float(text[:-1]) * 3600.0
        return float(text)
    except (TypeError, ValueError):
        return None


# One bucket shared across threads (the pipeline is synchronous but chat and
# re-analysis can overlap), sized per provider budget.
_throttle = _TokenBucket()


def _estimate_tokens(text: str) -> int:
    """Conservative token estimate (~3 chars/token) used only for throttling.

    Deliberately over-estimates so the throttle paces slightly slower than the
    provider meters, keeping us safely under the limit.
    """
    return max(1, len(text) // 3)


def _throttle_cost(system_prompt: str, user_prompt: str, max_tokens: int) -> float:
    return _estimate_tokens(system_prompt) + _estimate_tokens(user_prompt) + max_tokens


def complete(system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
    """Send one turn to the configured LLM and return the text response.

    Transient provider failures (5xx, rate limits, timeouts) are retried
    with exponential backoff before surfacing the actionable error. Requests
    are also paced client-side against the provider's tokens-per-minute
    budget (LLM_TOKEN_BUDGET_PER_MINUTE) to avoid 429s in the first place.
    """
    if settings.LLM_PROVIDER not in {"groq", "ollama", "anthropic", "openai", "gemini"}:
        raise LLMError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")
    if settings.LLM_PROVIDER != "ollama" and not settings.LLM_API_KEY:
        if settings.LLM_PROVIDER == "groq":
            raise LLMError("Groq API key is missing. Set LLM_API_KEY in your .env file.")
        raise LLMError(
            "LLM_API_KEY is not set. Add it to your .env file — see .env.example. "
            "LexClarity needs an LLM to summarize documents and power the chatbot."
        )

    max_tokens = max_tokens or settings.LLM_MAX_TOKENS

    # Groq rejects (HTTP 413, code `rate_limit_exceeded`) any single request
    # where `input_tokens + max_tokens` exceeds the whole per-minute TPM
    # budget. This is a hard size check, not window state — no amount of
    # waiting can make an oversized request succeed. We can't predict the
    # provider's tokenizer from character counts (legal prose tokenizes
    # anywhere from 3 to 10 chars/token), so instead of guessing a cap we let
    # the first attempt report the exact `Requested`/`Limit` and shrink the
    # output ceiling to fit (see the size-error handling around
    # _call_with_retry below). This mutable holder is what dispatch reads.
    _max_tokens_box = [max_tokens]

    # Pace the request against the provider's tokens-per-minute budget so
    # back-to-back pipeline stages (and every retry attempt) don't burst past
    # a small free-tier limit. Budget is reserved per attempt because each
    # retry is a real metered request. We reserve a conservative ceiling
    # upfront (safe), then refund the margin once the provider reports the
    # real metered cost (fast).
    budget = float(getattr(settings, "LLM_TOKEN_BUDGET_PER_MINUTE", 0) or 0)

    def dispatch() -> str:
        # Reserve against the *current* ceiling — it shrinks if a prior
        # attempt was rejected as too large for the TPM budget.
        if budget > 0:
            _throttle.acquire(
                _throttle_cost(system_prompt, user_prompt, _max_tokens_box[0]), budget
            )
        # _complete_groq syncs the bucket from Groq's rate-limit headers on
        # every response, so the next attempt paces against real remaining
        # tokens rather than our estimate.
        if settings.LLM_PROVIDER == "groq":
            return _complete_groq(system_prompt, user_prompt, _max_tokens_box[0])
        if settings.LLM_PROVIDER == "ollama":
            return _complete_ollama(system_prompt, user_prompt, _max_tokens_box[0])
        if settings.LLM_PROVIDER == "anthropic":
            return _complete_anthropic(system_prompt, user_prompt, _max_tokens_box[0])
        if settings.LLM_PROVIDER == "openai":
            return _complete_openai(system_prompt, user_prompt, _max_tokens_box[0])
        return _complete_gemini(system_prompt, user_prompt, _max_tokens_box[0])

    # Adaptive size handling: Groq rejects (413 `rate_limit_exceeded`) any
    # request where `input_tokens + output_ceiling` exceeds the whole per-minute
    # TPM budget. On that pre-flight rejection it reports `Requested` = the input
    # token count (no output has been generated yet) and `Limit` = the budget.
    #
    # Priority is keeping a USEFUL output (so the returned JSON isn't truncated)
    # over keeping every retrieved excerpt. When the input leaves too little
    # headroom for useful output, we trim excerpts from the HEAD of the prompt —
    # the instructions live at the tail, so they survive, and the model only ever
    # cites chunk_ids still present in the prompt, so trimming never fabricates
    # evidence (it just analyses fewer excerpts).
    for _size_attempt in range(5):
        try:
            return _call_with_retry(dispatch)
        except LLMError as _size_err:
            requested, limit = _parse_tpm_overshoot(_size_err)
            if requested is None or limit is None:
                raise
            input_tokens = requested  # pre-flight: Requested == input tokens
            desired = _max_tokens_box[0]
            margin = 300
            useful = min(desired, 2500)  # never squeeze output below this if avoidable
            headroom = limit - input_tokens - margin
            if headroom >= useful:
                # Input fits with room for useful output; cap the ceiling to it.
                _max_tokens_box[0] = min(desired, headroom)
                continue
            target_input = limit - useful - margin
            if input_tokens > target_input and len(user_prompt) > 2500:
                # Trim just enough excerpts from the head to free up room for
                # `useful` output tokens, and lower the ceiling to match.
                keep = max(0.2, min(0.97, target_input / max(1, input_tokens)))
                cut = max(1, int(len(user_prompt) * (1 - keep)))
                user_prompt = user_prompt[cut:]
                _max_tokens_box[0] = useful
                continue
            if headroom >= 512:
                _max_tokens_box[0] = int(headroom)
                continue
            raise LLMError(
                "This document's analysis prompt is too large for the LLM's "
                "per-minute token budget. Reduce retrieved context (top_k) or "
                "raise LLM_TOKEN_BUDGET_PER_MINUTE.",
                transient=False,
            ) from _size_err
    raise LLMError("LLM request could not be sized to fit the token budget.")


_RATE_LIMIT_MARKERS = ("rate limit", "rate_limit", "429", "quota", "resource_exhausted")


def _is_rate_limit_error(exc: LLMError) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _RATE_LIMIT_MARKERS)


def _call_with_retry(fn):
    """Run fn, retrying transient LLMErrors with exponential backoff.

    Two classes of transient error are handled differently:

    * 5xx / timeouts / connection drops usually recover within seconds and use
      a short exponential backoff (``LLM_RETRY_BACKOFF_SECONDS``).
    * Rate limits (429 / token-per-minute quotas) only clear when the
      provider's rolling window rolls over (often ~60s), so they get a much
      longer dedicated backoff (``LLM_RATE_LIMIT_BACKOFF_SECONDS``, capped at
      ``LLM_RATE_LIMIT_BACKOFF_MAX_SECONDS``) and more attempts
      (``LLM_RATE_LIMIT_RETRIES``). Without this the pipeline's back-to-back
      stage calls exhaust a small free-tier token budget and fail immediately.

    Retry knobs are read with getattr defaults so patched settings objects
    (tests) without the attributes keep working.
    """
    max_retries = int(getattr(settings, "LLM_MAX_RETRIES", 3))
    backoff_seconds = float(getattr(settings, "LLM_RETRY_BACKOFF_SECONDS", 1.5))
    rate_limit_backoff = float(getattr(settings, "LLM_RATE_LIMIT_BACKOFF_SECONDS", 12.0))
    rate_limit_backoff_max = float(getattr(settings, "LLM_RATE_LIMIT_BACKOFF_MAX_SECONDS", 45.0))
    rate_limit_retries = int(getattr(settings, "LLM_RATE_LIMIT_RETRIES", 5))
    attempt = 0
    while True:
        try:
            return fn()
        except LLMError as exc:
            is_rate_limit = _is_rate_limit_error(exc)
            limit = rate_limit_retries if is_rate_limit else max_retries
            if not exc.transient or attempt >= limit:
                raise
            base = rate_limit_backoff if is_rate_limit else backoff_seconds
            delay = min(base * (2 ** attempt), rate_limit_backoff_max)
            # Respect the provider's own recovery hint when present (e.g. a
            # `retry-after` on a TPM/RPM 429) instead of guessing, but never
            # sleep longer than the configured cap — a multi-minute blind wait
            # on a rolling window wastes wall-clock without spending tokens.
            retry_after = getattr(exc, "retry_after", None)
            if is_rate_limit and retry_after:
                try:
                    delay = min(float(retry_after), rate_limit_backoff_max)
                except (TypeError, ValueError):
                    pass
            # Bounded jitter (~±15%) so concurrent callers don't re-sync and
            # hammer the window the instant it reopens.
            delay = delay * (0.85 + 0.3 * random.random())
            logger.warning(
                "Transient LLM error (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1, limit + 1, delay, exc,
            )
            # On a rate limit the throttle was already synced from the 429's
            # own headers; let it pace the wait for the real refill window
            # instead of relying only on a blind fixed sleep. We sleep at most
            # `delay` here, and dispatch() will additionally block in
            # _throttle.acquire if the window hasn't recovered yet.
            time.sleep(delay)
            attempt += 1


def _complete_ollama(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    try:
        from openai import OpenAI
    except ImportError as e:
        raise LLMError("The 'openai' package is not installed.") from e

    try:
        client = OpenAI(base_url=settings.LLM_BASE_URL, api_key="ollama")
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        message = str(e).lower()
        if (
            "404" in message
            or "not found" in message
            or ("model" in message and "exist" in message)
        ):
            raise LLMError(
                "Qwen2.5 7B is not available in Ollama. Run: ollama pull qwen2.5:7b"
            ) from e
        if (
            "connect" in message
            or "connection" in message
            or "localhost" in message
            or "timed out" in message
            or "timeout" in message
        ):
            raise LLMError(
                "Local Ollama server is unavailable. Please make sure Ollama is running "
                "and the qwen2.5:7b model is installed."
            ) from e
        raise LLMError(f"Ollama request failed: {e}") from e


def _record_usage(response) -> None:
    """Capture the provider's metered token count for throttle refunds.

    The response object may be a mock or lack `usage`; never let bookkeeping
    break a successful call.
    """
    try:
        usage = getattr(response, "usage", None)
        total = getattr(usage, "total_tokens", None) if usage is not None else None
        if total is not None:
            _call_usage.total_tokens = int(total)
    except Exception:  # pragma: no cover - defensive
        pass


def _groq_reasoning_effort() -> str | None:
    """Reasoning effort to request, or None when the model doesn't take one.

    Groq accepts `reasoning_effort` only per family: gpt-oss takes
    low|medium|high, and models outside a family's supported set are rejected
    with a 400 — so it is gated on the configured model rather than sent
    unconditionally.
    """
    return "low" if "gpt-oss" in (settings.LLM_MODEL or "").lower() else None


def _complete_groq(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    try:
        from openai import OpenAI
    except ImportError as e:
        raise LLMError("The 'openai' package is not installed.") from e

    try:
        client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
        kwargs = dict(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        # gpt-oss reasons before it answers, and `max_tokens` covers those
        # hidden reasoning tokens too. At the default "medium" effort the whole
        # ceiling is regularly consumed by reasoning, which is how the
        # extraction stages produced truncated JSON ("Unterminated string…") or
        # nothing at all ("Expecting value: line 1 column 1"). "low" keeps the
        # budget for the actual answer.
        effort = _groq_reasoning_effort()
        if effort:
            kwargs["reasoning_effort"] = effort

        # Prefer the raw-response API so we can read Groq's rate-limit headers
        # and pace against the provider's real remaining-token budget instead of
        # guessing from prompt length. Test doubles (MagicMock) auto-create
        # `with_raw_response`, so treat any non-openai implementation as a mock
        # and fall back to the plain call they expect.
        raw_api = getattr(client, "with_raw_response", None)
        is_openai_impl = raw_api is not None and type(raw_api).__module__.startswith("openai")

        def _invoke():
            if is_openai_impl:
                raw = client.with_raw_response.chat.completions.create(**kwargs)
                _sync_bucket_from_headers(getattr(raw, "headers", None))
                _log_provider_limits(getattr(raw, "headers", None))
                return raw.parse()
            return client.chat.completions.create(**kwargs)

        response = _invoke()
        _record_usage(response)
        content = response.choices[0].message.content
        if not content and effort:
            # A reasoning-only completion means the ceiling was eaten again.
            # One retry costs a little quota but is the difference between an
            # empty analysis section and a real one.
            response = _invoke()
            _record_usage(response)
            content = response.choices[0].message.content
        return content or ""
    except Exception as e:
        _raise_groq_error(e)


# --- Rate-limit diagnostics -------------------------------------------------
# Rate-limit headers Groq (and OpenAI-compatible gateways) may send. We read
# them to learn WHICH dimension is rejecting us (tokens/min vs requests/min vs
# per-day) and to honour provider-supplied retry hints.
_RL_HEADER_KEYS = (
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests",
    "retry-after",
    "retry-after-ms",
)

# Logged once so we know the provider's real TPM/RPM without spamming every call.
_limits_logged = {"done": False}


def _safe_rl_clause(text: str) -> str | None:
    """Extract only the rate-limit clause from a provider message.

    Groq rate-limit messages read like `on tokens per minute (TPM): Limit 8000,
    Requested 9515...` and contain only limit numbers — never prompt or document
    content. We still match narrowly so a malformed/unexpected body can't leak
    anything else into the log. Returns `None` when no rate-limit clause is found.
    """
    if not text:
        return None
    m = re.search(
        r"on\s+.+?\((?:TPM|RPM|TPD|RPD|CPM)\)\s*:\s*Limit\s+\d+\s*,\s*Requested\s+\d+",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(0)[:240]
    m = re.search(r"Limit\s+\d+\s*,\s*Requested\s+\d+", text, re.IGNORECASE)
    return m.group(0)[:240] if m else None


def _classify_rate_limit(error) -> tuple[str, float | None]:
    """Return ``(kind, retry_after_seconds)`` for a rate-limit error.

    ``kind`` is one of ``tpm`` (tokens/min), ``rpm`` (requests/min), ``daily``
    (per-day quota), or ``unknown``. ``daily`` is deliberately distinct: waiting
    45s cannot recover a per-day quota, so callers must NOT blind-retry it.
    ``retry_after_seconds`` is parsed from the provider's ``retry-after`` header
    when present (bounded by the caller), else ``None``.
    """
    try:
        body = getattr(error, "body", None)
        text = str(body) if body is not None else str(error)
    except Exception:
        text = str(error)
    low = text.lower()
    retry_after = None
    try:
        resp = getattr(error, "response", None)
        headers = getattr(resp, "headers", None)
        if headers is not None and hasattr(headers, "get"):
            ra = headers.get("retry-after")
            if ra is not None:
                retry_after = _parse_number(ra)
            if retry_after is None:
                ram = headers.get("retry-after-ms")
                if ram is not None:
                    ms = _parse_number(ram)
                    retry_after = ms / 1000.0 if ms is not None else None
    except Exception:  # pragma: no cover - defensive
        pass

    if "per day" in low or "daily" in low or "(tpd)" in low or "(rpd)" in low or "token requests per day" in low:
        return "daily", retry_after
    if "(rpm)" in low or "requests per minute" in low or "requests per second" in low:
        return "rpm", retry_after
    if "(tpm)" in low or "tokens per minute" in low:
        return "tpm", retry_after
    if "quota" in low or "resource_exhausted" in low:
        return "unknown", retry_after
    return "unknown", retry_after


def _describe_rate_limit(error) -> dict:
    """Build a safe, structured snapshot of a 429 for the log.

    Captures status, Groq's error ``code``/``type``, the narrow rate-limit
    clause, and every rate-limit / retry header. Never includes the API key,
    the Authorization header, or document/prompt text.
    """
    info: dict = {"status": getattr(error, "status_code", None)}
    try:
        body = getattr(error, "body", None)
        if isinstance(body, dict):
            err = body.get("error")
            err = err if isinstance(err, dict) else body
            info["code"] = err.get("code")
            info["type"] = err.get("type")
            info["clause"] = _safe_rl_clause(str(err.get("message") or ""))
        if info.get("clause") is None:
            info["clause"] = _safe_rl_clause(str(error))
        kind, retry_after = _classify_rate_limit(error)
        info["kind"] = kind
        if retry_after is not None:
            info["retry_after"] = round(retry_after, 3)
        resp = getattr(error, "response", None)
        headers = getattr(resp, "headers", None)
        if headers is not None and hasattr(headers, "get"):
            for k in _RL_HEADER_KEYS:
                v = headers.get(k)
                if v is not None:
                    info[k] = str(v)[:64]
    except Exception:  # pragma: no cover - defensive
        pass
    return info


def _log_provider_limits(headers) -> None:
    """Log the provider's advertised TPM/RPM once (for evidence + tuning)."""
    if _limits_logged["done"] or headers is None:
        return
    try:
        get = headers.get if hasattr(headers, "get") else (lambda _k: None)
        tok_limit = get("x-ratelimit-limit-tokens")
        req_limit = get("x-ratelimit-limit-requests")
        if tok_limit is None and req_limit is None:
            return
        _limits_logged["done"] = True
        budget = float(getattr(settings, "LLM_TOKEN_BUDGET_PER_MINUTE", 0) or 0)
        logger.warning(
            "Provider rate limits: TPM=%s RPM=%s (configured budget=%s)",
            tok_limit, req_limit, budget,
        )
    except Exception:  # pragma: no cover - defensive
        pass


def _raise_groq_error(error: Exception) -> None:
    message = str(error).lower()
    status_code = getattr(error, "status_code", None)
    error_type = type(error).__name__.lower()

    if status_code == 401 or "authentication" in message or "invalid api key" in message:
        raise LLMError("Groq API key is invalid. Check LLM_API_KEY in your .env file.") from error
    # 413 TPM *size* rejection: a single request whose input+output ceiling
    # exceeds the entire per-minute budget. Its body carries
    # `rate_limit_exceeded`, so it MUST be caught before the generic
    # rate-limit branch below — waiting can never make an oversized request
    # succeed, and treating it as transient burns the whole backoff schedule.
    # Pass the raw message through so complete() can read `Limit`/`Requested`
    # and shrink the output ceiling for a retry that fits.
    if status_code == 413 or "request too large" in message or "tokens per minute" in message:
        raise LLMError(str(error), transient=False) from error
    if status_code == 429 or "rate limit" in message or "rate_limit" in message:
        # Evidence-first: log the structured 429 (status, Groq code/type, the
        # narrow rate-limit clause, every rate-limit/retry header) so the cause
        # is known rather than guessed. Safe to log — no key, no prompt text.
        details = _describe_rate_limit(error)
        logger.warning("GROQ 429 details: %s", details)
        kind, retry_after = _classify_rate_limit(error)
        # A 429's own `x-ratelimit-remaining-tokens` reports the *limit* (not the
        # true remaining), so adopting it would falsely refill the bucket and
        # re-send instantly, cascading. Mark the window exhausted (remaining=0)
        # while keeping the real per-minute limit so _throttle.acquire blocks
        # until a genuine refill before the next attempt.
        _mark_rate_limited()
        if kind == "daily":
            # Per-day quota: 45s of retries cannot recover it. Fail fast with a
            # clear, actionable message instead of burning minutes of backoff.
            # `rate_limit_kind` lets the pipeline skip the remaining LLM stages
            # (each would only wait on the throttle and then 429 again).
            raise LLMError(
                "Groq daily token quota is exhausted for this API key. The daily "
                "window resets later — try again then, or use a different key / plan.",
                transient=False,
                rate_limit_kind="daily",
            ) from error
        raise LLMError(
            "Groq rate limit reached. Please wait and try again.",
            transient=True,
            retry_after=retry_after,
            rate_limit_kind=kind,
        ) from error
    if status_code == 404 or "model" in message and ("not found" in message or "does not exist" in message):
        raise LLMError(f"Groq model '{settings.LLM_MODEL}' is unavailable. Check LLM_MODEL.") from error
    if "timeout" in message or "timeout" in error_type:
        raise LLMError("Groq request timed out. Please try again.", transient=True) from error
    if status_code and status_code >= 500 or "connection" in message or "connect" in message:
        raise LLMError("Groq API is unavailable. Please try again later.", transient=True) from error
    raise LLMError(f"Groq request failed: {error}") from error


def _complete_anthropic(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("The 'anthropic' package is not installed.") from e

    try:
        client = anthropic.Anthropic(api_key=settings.LLM_API_KEY)
        response = client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
    except Exception as e:
        if _looks_transient(e):
            raise LLMError(f"LLM request failed: {e}", transient=True) from e
        raise LLMError(f"LLM request failed: {e}") from e


def _complete_openai(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    try:
        from openai import OpenAI
    except ImportError as e:
        raise LLMError("The 'openai' package is not installed.") from e

    try:
        client = OpenAI(api_key=settings.LLM_API_KEY)
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        if _looks_transient(e):
            raise LLMError(f"LLM request failed: {e}", transient=True) from e
        raise LLMError(f"LLM request failed: {e}") from e


def _complete_gemini(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise LLMError("The 'google-genai' package is not installed. Run `pip install google-genai`.") from e

    try:
        client = genai.Client(api_key=settings.LLM_API_KEY)
        response = client.models.generate_content(
            model=settings.LLM_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
            ),
        )
        text = response.text or ""
        if not text:
            raise LLMError("Gemini returned an empty response. Please try again.")
        return text
    except Exception as e:
        if isinstance(e, LLMError):
            raise
        message = str(e).lower()
        status_code = getattr(e, "status_code", None)
        if status_code == 401 or "api key" in message and ("invalid" in message or "not valid" in message):
            raise LLMError("Gemini API key is invalid. Check LLM_API_KEY in your .env file.") from e
        if status_code == 429 or "quota" in message or "resource_exhausted" in message:
            raise LLMError(
                "Gemini API quota or rate limit reached. Check your Google AI Studio quota and try again later.",
                transient=True,
            ) from e
        if "timeout" in message:
            raise LLMError("Gemini request timed out. Please try again.", transient=True) from e
        if _looks_transient(e):
            raise LLMError(f"Gemini request failed: {e}", transient=True) from e
        raise LLMError(f"Gemini request failed: {e}") from e


def complete_json(system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> dict | list:
    """Ask the LLM for strict JSON and parse it, tolerating markdown fences."""
    raw = complete(
        system_prompt + "\n\nRespond with ONLY valid JSON. No markdown fences, no preamble, no commentary.",
        user_prompt,
        max_tokens,
    )
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        match = re.search(r"(\[.*\]|\{.*\})", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        raise LLMError(f"LLM did not return valid JSON: {e}\nRaw response: {raw[:500]}")
