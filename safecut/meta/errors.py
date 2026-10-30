"""Typed errors for every Meta Model API failure (PRE-A §10.3) and the HTTP-status classifier."""

from __future__ import annotations

from typing import Any, cast

from safecut.config import CapKind


class MetaError(Exception):
    """Base class. ``retryable`` says whether the transport may try the same request again."""

    default_retryable = False

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        request_id: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.request_id = request_id
        self.retryable = self.default_retryable if retryable is None else retryable
        #: Set by the transport: some attempt may have reached the server and been processed.
        self.maybe_processed = False


class MetaAuthError(MetaError):
    """401 or 403: the key is wrong or lacks access. Stop the job; never retried."""


class MetaBillingError(MetaError):
    """402: insufficient balance or a lapsed payment method."""


class MetaConfigError(MetaError):
    """A model, effort, schema or path the API doesn't accept: a deploy-time mistake."""


class MetaFileGone(MetaError):
    """404 ``file_not_found``: re-upload the file once and repeat the call."""


class MetaBadRequest(MetaError):
    """Any other 4xx the request itself caused."""


class MetaRateLimited(MetaError):
    """429. Retryable within the attempt budget; raised as final after the last attempt."""

    default_retryable = True


class MetaUnavailable(MetaError):
    """5xx, timeouts, connection errors, or an open circuit breaker."""

    default_retryable = True


class BreakerOpen(MetaUnavailable):
    """The circuit breaker refused the call: nothing was sent."""


class ReplayRefused(MetaConfigError):
    """``SAFECUT_REPLAY`` is on: the live call was refused before any reservation, so nothing was sent."""


class MetaRefusal(MetaError):
    """The model refused (a refusal part or event).

    The refusal text may quote what the model saw (private text), so the message carries only its length;
    the text itself is on :attr:`refusal_text`, which is never logged.
    """

    refusal_text: str = ""

    @classmethod
    def of(cls, text: str) -> MetaRefusal:
        error = cls(f"the model refused ({len(text)} characters)")
        error.refusal_text = text
        return error


class MetaIncomplete(MetaError):
    """The response ended early. ``eof`` (no terminal event) is transient; the rest is deterministic."""

    def __init__(self, message: str, *, eof: bool, status: int | None = None, request_id: str | None = None) -> None:
        super().__init__(message, status=status, request_id=request_id, retryable=eof)
        self.eof = eof


class BudgetExceeded(MetaError):
    """The pre-call estimate doesn't fit a cap. No request was made."""

    def __init__(self, message: str, *, cap: CapKind, limit_usd: float, needed_usd: float) -> None:
        super().__init__(message)
        self.cap: CapKind = cap
        self.limit_usd = limit_usd
        self.needed_usd = needed_usd


_CONFIG_PARAMS = ("model", "reasoning", "text.format", "text", "max_output_tokens", "metadata")
_RETRYABLE_5XX = frozenset({500, 502, 503})


def _error_fields(body: Any) -> tuple[str, str | None, str | None]:
    """``(message, code, param)`` from Meta's ``{"error": {...}}`` envelope, tolerating anything else."""
    if not isinstance(body, dict):
        return "", None, None
    err = cast(dict[str, Any], body).get("error")
    if isinstance(err, str):
        return err, None, None
    if not isinstance(err, dict):
        return "", None, None
    fields = cast(dict[str, Any], err)
    code, param = fields.get("code"), fields.get("param")
    return (
        str(fields.get("message") or ""),
        code if isinstance(code, str) else None,
        param if isinstance(param, str) else None,
    )


def classify(status: int, body: Any, *, request_id: str | None = None) -> MetaError:
    """Map a non-2xx response to its typed error. ``body`` is the decoded JSON, or ``None``.

    Retryable statuses come back as retryable types; the transport decides when attempts run out.
    """
    message, code, param = _error_fields(body)
    detail = f"HTTP {status}" + (f" {code}" if code else "") + (f": {message}" if message else "")
    kwargs: dict[str, Any] = {"status": status, "request_id": request_id}
    if status in (401, 403):
        return MetaAuthError(detail, **kwargs)
    if status == 402:
        return MetaBillingError(detail, **kwargs)
    if status == 404:
        if body is None or body in ({}, ""):
            return MetaConfigError(
                f"HTTP 404 with an empty body (wrong path?){': ' + message if message else ''}", **kwargs
            )
        if code == "file_not_found":
            return MetaFileGone(detail, **kwargs)
        if code == "model_not_found":
            return MetaConfigError(detail, **kwargs)
        return MetaBadRequest(detail, **kwargs)
    if status == 400:
        lowered = message.lower()
        root = param.split("[")[0].split(".")[0] if param else None  # "reasoning.effort" -> "reasoning"
        if (root and root in _CONFIG_PARAMS) or "unsupported param" in lowered:
            return MetaConfigError(detail, **kwargs)
        return MetaBadRequest(detail, **kwargs)
    if status == 429:
        return MetaRateLimited(detail, **kwargs)
    if status == 504:
        # Meta: "do not simply retry, the same request will usually time out again".
        return MetaUnavailable(detail, retryable=False, **kwargs)
    if status >= 500:
        # PRE-A §10.2 retries 500/502/503 only: 501, 505, 507, 511 … fail the same way every time.
        return MetaUnavailable(detail, retryable=status in _RETRYABLE_5XX, **kwargs)
    return MetaBadRequest(detail, **kwargs)
