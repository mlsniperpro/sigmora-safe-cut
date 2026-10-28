"""Env-driven settings and the constants every stage shares.

Every env var in ARCHITECTURE.md §4 (and the PRE-A §12 env table) is read here, typed and
validated once. Logic never hard-codes a model ID (AGENTS rule 8): it reads ``Settings``.
Efforts, output limits, retry counts, timeouts and concurrency are constants, not env vars.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Enums shared by config and contracts
# ---------------------------------------------------------------------------

Effort = Literal["minimal", "low", "medium", "high", "xhigh", "max"]
FallbackEffort = Literal["minimal", "low", "medium", "high", "omit"]
CodeKind = Literal["pilot", "recording", "judge", "public", "service", "owner", "eval", "system"]
AccessCodeKind = Literal["judge", "public", "pilot", "recording", "owner"]
WindowKind = Literal["judge", "public", "service", "recording", "pilot", "owner"]
CapKind = Literal["job", "test_line", "code", "pilot_pool", "daily", "baseten_job"]
Provider = Literal["meta", "baseten"]
OpenWeightEffort = Literal["low", "medium", "high", "xhigh", "omit"]

# Meta's documented Voice Transcribe languages (speech-to-text page, read 2026-10-25).
ASR_LANGUAGES: frozenset[str] = frozenset(
    {
        "Arabic", "Bengali", "Dutch", "English", "French", "German", "Hebrew", "Hindi",
        "Indonesian", "Italian", "Japanese", "Kannada", "Korean", "Malay", "Mandarin Chinese",
        "Marathi", "Polish", "Portuguese", "Spanish", "Tagalog", "Tamil", "Telugu", "Thai",
        "Turkish", "Vietnamese",
    }
)  # fmt: skip


class ConfigError(ValueError):
    """The environment holds a value Safe Cut refuses to start with."""


def trusted_base_url(value: str, allowed: frozenset[str]) -> str:
    """The bearer key goes to this host, so only the provider's own HTTPS host is accepted."""
    if any(ch.isspace() or not ch.isprintable() for ch in value):
        # urlsplit strips a pasted newline for parsing but the value keeps it: httpx would refuse every request
        # only after it was marked sent (and billed as estimated).
        raise ValueError("base URLs must not contain whitespace or control characters")
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or parts.hostname not in allowed
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or "?" in value  # even an empty query or fragment would move every endpoint path into it
        or "#" in value
    ):
        raise ValueError(f"base URLs must be https://{'|'.join(sorted(allowed))}/… with no credentials or port")
    return value.rstrip("/")


def ensure_standard_model(model_id: str) -> str:
    """Refuse Contributor-mode IDs (AGENTS rule 6): Safe Cut sends faces. The one place this rule lives."""
    cleaned = model_id.strip()
    if not cleaned:
        raise ValueError("model ID is empty")
    if cleaned.lower().endswith("-contributor"):
        raise ValueError(f"{cleaned!r} is a Contributor-mode model; Safe Cut uses Standard mode only")
    return cleaned


ModelId = Annotated[str, AfterValidator(ensure_standard_model)]

# ---------------------------------------------------------------------------
# Prices (dated). Read live from dev.meta.ai/docs/pricing-rate-limits on 2026-10-26.
# ---------------------------------------------------------------------------

PRICE_TABLE_DATE = "2026-10-26"


class TokenPrice(BaseModel):
    """USD per 1M tokens, Standard mode."""

    model_config = ConfigDict(frozen=True)

    input: float
    cached: float
    output: float


TOKEN_PRICES: Mapping[str, TokenPrice] = {
    "muse-spark-1.3": TokenPrice(input=1.25, cached=0.15, output=4.25),
    "muse-spark-1.2": TokenPrice(input=1.25, cached=0.15, output=4.25),
    "muse-spark-1.1": TokenPrice(input=1.25, cached=0.15, output=4.25),
    "muse-wonder-1.0": TokenPrice(input=4.00, cached=0.20, output=20.00),
}
#: WP0 probe f's fixed comparison pair (DESIGN's Spark-vs-Wonder question), named here so no probe hard-codes an ID.
#: The models the pipeline calls come from Settings (env), not from these.
COMPARE_SPARK_MODEL = "muse-spark-1.3"
COMPARE_WONDER_MODEL = "muse-wonder-1.0"
SAM_USD_PER_FRAME = 0.20 / 1000
SAM_USD_PER_IMAGE = 2.50 / 1000
SAM_MIN_FRAMES_BILLED = 50
ASR_USD_PER_SECOND = 0.18 / 3600

# ---------------------------------------------------------------------------
# Constants (PRE-A §10). Not env-configurable on purpose.
# ---------------------------------------------------------------------------

#: ``max_output_tokens`` by (model family, effort). A response cut off by it is ``MetaIncomplete``.
MAX_OUTPUT_TOKENS_DEFAULT = 16_000
MAX_OUTPUT_TOKENS: Mapping[tuple[str, str], int] = {
    ("spark", "high"): 32_000,
    ("spark", "xhigh"): 32_000,
    ("spark", "max"): 48_000,
    ("wonder", "high"): 24_000,
    ("wonder", "xhigh"): 24_000,
    ("wonder", "max"): 24_000,
}


def max_output_tokens(model: str, effort: str) -> int:
    """The output cap PRE-A §10.5 sets for a model and effort (``omit`` and ``medium`` and lower: 16k)."""
    family = "wonder" if model.startswith("muse-wonder") else "spark"
    return MAX_OUTPUT_TOKENS.get((family, effort), MAX_OUTPUT_TOKENS_DEFAULT)


# Attempts in total (first try included), PRE-A §10.2.
ATTEMPTS_DEFAULT = 4
ATTEMPTS_DEEP_EFFORT = 2  # Responses at xhigh / max
ATTEMPTS_SAM = 2  # every attempt re-bills the frames
ATTEMPTS_ASR_500 = 2  # Meta: retry an ASR 500 once
BACKOFF_BASE_S = 1.0
BACKOFF_CAP_S = 30.0
RETRY_AFTER_CAP_S = 120.0
BREAKER_FAILURES = 5
BREAKER_WINDOW_S = 60.0
BREAKER_OPEN_S = 60.0
THROTTLE_FRACTION = 0.05
THROTTLE_DELAY_S = 1.0

# Timeouts in seconds, PRE-A §10.1.
CONNECT_TIMEOUT_S = 10.0
SAM_IDLE_TIMEOUT_S = 90.0
SAM_TOTAL_TIMEOUT_S = 600.0
RESPONSES_TOTAL_TIMEOUT_S = 900.0
ASR_TOTAL_TIMEOUT_S = 180.0
FILES_DELETE_TIMEOUT_S = 15.0
FILES_UPLOAD_BASE_S = 30.0
FILES_UPLOAD_PER_MB_S = 2.0
FILES_EXPIRES_AFTER_S = 21_600  # 6 h backstop, above the 2 h segment limit
BUDGET_RESERVE_TIMEOUT_S = 10.0


def responses_idle_timeout(effort: str) -> float:
    """Read-idle timeout for a streamed Responses call: deeper effort reasons silently for longer."""
    if effort == "max":
        return 600.0
    if effort in ("high", "xhigh"):
        return 450.0
    return 300.0


# Concurrency bounds, PRE-A §10.1.
MAX_CONNECTIONS = 16
PROCESS_INFLIGHT = 8
JOB_SAM_INFLIGHT = 4
JOB_RESPONSES_INFLIGHT = 3
#: Open-weight batches of one frame set in flight at once (PRE-A §3.8), on the Baseten client's own lane.
BASETEN_INFLIGHT = 4

# Upload limits shared with WP1, WP5 and the UI.
MAX_CLIP_SECONDS = 60.05
MAX_UPLOAD_BYTES = 157_286_400
JOB_SEGMENT_TIMEOUT_S = 7_200
DATA_PURGE_HOURS = 24

# ---------------------------------------------------------------------------
# Structured env values
# ---------------------------------------------------------------------------


class OpenWeightPrice(BaseModel):
    """USD per 1M tokens on Baseten, set from probe h (``SAFECUT_OPEN_WEIGHT_PRICE={"in": …, "out": …}``)."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, populate_by_name=True)

    input: float = Field(alias="in", gt=0)
    output: float = Field(alias="out", gt=0)


class AccessCode(BaseModel):
    """One ``SAFECUT_ACCESS_CODES`` entry (PRE-A §12, PR #2 UI-SPEC request 20)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: SecretStr = Field(min_length=4)
    kind: AccessCodeKind
    cap_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None

    @model_validator(mode="after")
    def _window_order(self) -> AccessCode:
        if self.valid_from and self.valid_until and self.valid_from >= self.valid_until:
            raise ValueError(f"access code {self.kind}: valid_from must be before valid_until")
        if self.kind in ("pilot", "recording", "owner") and self.cap_usd is None:
            raise ValueError(f"access code of kind {self.kind!r} needs cap_usd")
        return self


class ServiceKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: SecretStr = Field(min_length=16)
    name: str = Field(min_length=1)


class CodeWindow(BaseModel):
    """``[from, until]`` in UTC; ``from`` may be ``None`` (no start bound)."""

    model_config = ConfigDict(frozen=True)

    start: AwareDatetime | None
    until: AwareDatetime | None


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


DEFAULT_CODE_WINDOWS: Mapping[WindowKind, CodeWindow] = {
    "judge": CodeWindow(start=_utc("2026-11-05T00:00:00Z"), until=_utc("2026-11-10T23:59:59Z")),
    "public": CodeWindow(start=_utc("2026-11-05T00:00:00Z"), until=_utc("2026-11-10T23:59:59Z")),
    "service": CodeWindow(start=_utc("2026-11-05T00:00:00Z"), until=_utc("2026-11-10T23:59:59Z")),
    "recording": CodeWindow(start=None, until=_utc("2026-11-03T23:59:59Z")),
    "pilot": CodeWindow(start=None, until=_utc("2026-11-02T23:59:59Z")),
    "owner": CodeWindow(start=None, until=_utc("2026-11-10T23:59:59Z")),
}

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

_ENV_PREFIX = "SAFECUT_"
#: Where each base URL may point (AGENTS rule 7: calls go direct, never through a proxy).
ALLOWED_HOSTS: Mapping[str, frozenset[str]] = {
    "meta_base_url": frozenset({"api.meta.ai"}),
    "open_weight_base_url": frozenset({"inference.baseten.co"}),
}
#: Secrets keep the names their providers document, without the SAFECUT_ prefix.
_SECRET_ENV: Mapping[str, str] = {"model_api_key": "MODEL_API_KEY", "baseten_api_key": "BASETEN_API_KEY"}
_JSON_FIELDS = frozenset(
    {"access_codes", "code_windows", "asr_language_bias", "service_keys", "open_weight_price", "open_weight_code_kinds"}
)
_BOOL_FIELDS = frozenset({"replay", "sam_send_store", "sam_delete_responses", "open_weight_grid_ok"})
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


class Settings(BaseModel):
    """Every runtime setting. Build it with :func:`load_settings` (env) or directly in tests."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    # Models (ARCHITECTURE §4). WP0's probe results set the scene/escalate/speech defaults.
    sam_model: ModelId = "sam-3.1"
    role_model: ModelId = "muse-spark-1.3"
    role_effort: Effort = "medium"
    scene_model: ModelId = "muse-spark-1.3"
    scene_effort: Effort = "medium"
    escalate_model: ModelId = "muse-spark-1.3"
    escalate_effort: Effort = "max"
    redteam_model: ModelId = "muse-spark-1.3"
    redteam_effort: Effort = "medium"
    asr_model: ModelId = "muse-voice-transcribe-1.0"
    speech_source: Literal["asr", "spark-1.2"] = "asr"
    speech_fallback_model: ModelId = "muse-spark-1.2"
    speech_fallback_effort: FallbackEffort = "omit"
    asr_language_bias: tuple[str, ...] = ("English",)

    # Open-weight second opinion: Muse Spark Open on Baseten (PRE-A §3.8). The hackathon ID is
    # ``meta-models/muse-spark-open-1026`` (official guide), not the docs' ``meta-models/muse-spark-open``.
    # Off until probe h passes; Baseten credits are separate from the $150 Meta ledger.
    open_weight_audit: Literal["on", "off"] = "off"
    open_weight_model: ModelId = "meta-models/muse-spark-open-1026"
    open_weight_base_url: str = "https://inference.baseten.co/v1"
    open_weight_effort: OpenWeightEffort = "medium"
    open_weight_job_usd_cap: float = Field(default=0.50, ge=0)
    open_weight_price: OpenWeightPrice | None = None  # set from probe h; with none, calls are refused
    open_weight_grid_ok: bool = False
    open_weight_code_kinds: tuple[Literal["owner", "recording"], ...] = ()
    baseten_api_key: SecretStr | None = None

    # Endpoint and key.
    meta_base_url: str = "https://api.meta.ai/v1"
    model_api_key: SecretStr | None = None
    sam_send_store: bool = True
    #: ``DELETE /v1/responses/{id}`` after each SAM call that couldn't send ``store: false``. Unset means "on
    #: exactly when ``sam_send_store`` is off" (PRE-A §12); read it through :attr:`delete_sam_responses`.
    sam_delete_responses: bool | None = None

    # Spend guards (USD).
    job_usd_cap: float = Field(default=3.00, gt=0)
    daily_usd_cap: float = Field(default=3.00, ge=0)
    pilot_code_usd: float = Field(default=6.00, ge=0)
    pilot_pool_usd: float = Field(default=20.00, ge=0)
    recording_code_usd: float = Field(default=15.00, ge=0)
    test_line_usd: float = Field(default=43.20, ge=0)

    # Pipeline knobs.
    sam_fps: int = Field(default=8, ge=1, le=10)
    miss_sam: Literal["live", "stub"] = "live"
    replay: bool = False

    # Access.
    access_codes: tuple[AccessCode, ...] = ()
    service_keys: tuple[ServiceKey, ...] = ()
    code_windows: Mapping[WindowKind, CodeWindow] = Field(default_factory=lambda: dict(DEFAULT_CODE_WINDOWS))

    # Auditor.
    egoblur_model: Literal["egoblur-gen2", "egoblur-gen1", "yunet-face"] = "egoblur-gen2"
    egoblur_weights_dir: str = "/models/egoblur"
    egoblur_face_threshold: float = Field(default=0.5, gt=0, lt=1)
    egoblur_plate_threshold: float = Field(default=0.5, gt=0, lt=1)

    # Upload storage (WP5). Secrets, all optional until WP5 needs them.
    r2_account_id: str | None = None
    r2_access_key_id: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None
    r2_bucket: str | None = None

    @property
    def delete_sam_responses(self) -> bool:
        return (not self.sam_send_store) if self.sam_delete_responses is None else self.sam_delete_responses

    @field_validator("model_api_key", "baseten_api_key")
    @classmethod
    def _clean_key(cls, value: SecretStr | None) -> SecretStr | None:
        """A key is sent in an HTTP header: surrounding whitespace (a pasted newline) is stripped, and a key with
        inner whitespace or non-ASCII characters is refused here, rather than failing every call unsent."""
        if value is None:
            return None
        key = value.get_secret_value().strip()
        if any(ch.isspace() or not ch.isascii() for ch in key):
            raise ValueError("the key holds whitespace or non-ASCII characters (never echoed)")
        return SecretStr(key)

    @model_validator(mode="after")
    def _sam_responses_handled(self) -> Settings:
        # AGENTS rule 6: if SAM can't be sent store:false, its stored responses must be deleted.
        if not self.sam_send_store and self.sam_delete_responses is False:
            raise ValueError(
                "SAFECUT_SAM_SEND_STORE=false needs SAM response deletion (leave SAFECUT_SAM_DELETE_RESPONSES unset)"
            )
        return self

    @field_validator("meta_base_url", "open_weight_base_url")
    @classmethod
    def _trusted_base(cls, value: str, info: ValidationInfo) -> str:
        return trusted_base_url(value, ALLOWED_HOSTS[info.field_name or ""])

    @field_validator("asr_language_bias")
    @classmethod
    def _known_languages(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        unknown = [lang for lang in value if lang not in ASR_LANGUAGES]
        if unknown:
            raise ValueError(f"unsupported Voice Transcribe language(s) {unknown}; use Meta's exact names")
        return value

    @field_validator("code_windows")
    @classmethod
    def _complete_windows(cls, value: Mapping[WindowKind, CodeWindow]) -> Mapping[WindowKind, CodeWindow]:
        merged = dict(DEFAULT_CODE_WINDOWS)
        merged.update(value)
        return merged

    @model_validator(mode="after")
    def _priced_models(self) -> Settings:
        """A token model without a dated price would fail mid-job; refuse it at startup instead."""
        token_models = {
            self.role_model,
            self.scene_model,
            self.escalate_model,
            self.redteam_model,
            self.speech_fallback_model,
        }
        unpriced = sorted(m for m in token_models if m not in TOKEN_PRICES)
        if unpriced:
            raise ValueError(f"no {PRICE_TABLE_DATE} price for {unpriced}; add it to TOKEN_PRICES first")
        return self

    @model_validator(mode="after")
    def _code_caps(self) -> Settings:
        seen: set[str] = set()
        for entry in self.access_codes:
            code = entry.code.get_secret_value()
            if code in seen:
                raise ValueError("SAFECUT_ACCESS_CODES has a duplicate code")
            seen.add(code)
            limit = {"pilot": self.pilot_code_usd, "owner": 6.00, "recording": self.recording_code_usd}.get(entry.kind)
            if limit is not None and entry.cap_usd is not None and entry.cap_usd > limit:
                raise ValueError(f"access code of kind {entry.kind!r} has cap_usd above {limit:.2f}")
            window = self.code_windows[entry.kind]
            if entry.valid_from and window.start and entry.valid_from < window.start:
                raise ValueError(f"access code of kind {entry.kind!r} starts before its kind's window")
            if entry.valid_until and window.until and entry.valid_until > window.until:
                raise ValueError(f"access code of kind {entry.kind!r} ends after its kind's window")
        return self

    def api_key(self) -> str:
        """The Meta key, or a typed error. Never log the return value."""
        if self.model_api_key is None or not self.model_api_key.get_secret_value():
            raise ConfigError("MODEL_API_KEY is not set")
        return self.model_api_key.get_secret_value()

    def speech_fallback_pair(self) -> tuple[str, str]:
        """The speech fallback's (model, effort): probed at startup, but its failure never stops the start."""
        return (self.speech_fallback_model, self.speech_fallback_effort)

    def open_api_key(self) -> str:
        """The Baseten key for the open-weight model. Never log the return value."""
        if self.baseten_api_key is None or not self.baseten_api_key.get_secret_value():
            raise ConfigError("BASETEN_API_KEY is not set")
        return self.baseten_api_key.get_secret_value()

    def model_effort_pairs(self) -> list[tuple[str, str]]:
        """Every configured (Responses model, effort) pair, for the startup probe (PRE-A §10.7)."""
        pairs = {
            (self.role_model, self.role_effort),
            (self.scene_model, self.scene_effort),
            (self.escalate_model, self.escalate_effort),
            (self.redteam_model, self.redteam_effort),
        }
        return sorted(pairs)


_WINDOW_PAIRS: TypeAdapter[dict[WindowKind, tuple[AwareDatetime | None, AwareDatetime | None]]] = TypeAdapter(
    dict[WindowKind, tuple[AwareDatetime | None, AwareDatetime | None]]
)


def _parse_env_value(name: str, raw: str) -> Any:
    if name in _JSON_FIELDS:
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{_ENV_PREFIX}{name.upper()} is not valid JSON: {exc.msg}") from exc
        except (RecursionError, ValueError) as exc:  # too deep, or an integer past Python's digit limit
            raise ConfigError(f"{_ENV_PREFIX}{name.upper()} is not usable JSON: {type(exc).__name__}") from exc
        if name == "code_windows":
            try:
                pairs = _WINDOW_PAIRS.validate_python(parsed)
            except ValidationError as exc:
                raise ConfigError("SAFECUT_CODE_WINDOWS must map a code kind to [from, until] (ISO UTC)") from exc
            return {kind: CodeWindow(start=start, until=until) for kind, (start, until) in pairs.items()}
        return parsed
    if name in _BOOL_FIELDS:
        word = raw.strip().lower()
        if word not in _TRUE | _FALSE:
            # A typo must never silently turn replay off (= live spend) or store on.
            raise ConfigError(f"{_ENV_PREFIX}{name.upper()} must be one of 1/0, true/false, yes/no, on/off")
        return word in _TRUE
    return raw


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build :class:`Settings` from the environment. Unset or empty variables keep their defaults."""
    source = os.environ if env is None else env
    values: dict[str, Any] = {}
    for name in Settings.model_fields:
        env_name = _SECRET_ENV.get(name, f"{_ENV_PREFIX}{name.upper()}")
        raw = source.get(env_name)
        if raw is None or raw.strip() == "":
            continue
        values[name] = _parse_env_value(name, raw)
    try:
        return Settings.model_validate(values)
    except ValidationError as exc:
        # Never echo input values: one of them may be a secret.
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors(include_input=False)
        )
        raise ConfigError(f"invalid Safe Cut configuration: {problems}") from None
