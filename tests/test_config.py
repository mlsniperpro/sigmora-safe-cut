"""Settings from the environment: defaults, parsing, validation and secret hygiene."""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from safecut import config
from safecut.config import ConfigError, load_settings


def test_defaults_match_architecture() -> None:
    s = load_settings({})
    assert (s.sam_model, s.role_model, s.scene_model, s.escalate_model) == (
        "sam-3.1",
        "muse-spark-1.3",
        "muse-spark-1.3",
        "muse-spark-1.3",
    )
    assert s.escalate_effort == "max"
    assert s.asr_model == "muse-voice-transcribe-1.0"
    assert (s.speech_source, s.speech_fallback_model, s.speech_fallback_effort) == ("asr", "muse-spark-1.2", "omit")
    assert (s.job_usd_cap, s.daily_usd_cap, s.sam_fps) == (3.0, 3.0, 8)
    assert s.meta_base_url == "https://api.meta.ai/v1"
    assert s.asr_language_bias == ("English",)
    assert s.replay is False
    assert s.sam_send_store is True
    assert s.model_api_key is None
    assert set(s.code_windows) == {"judge", "public", "service", "recording", "pilot", "owner"}


def test_env_values_are_parsed() -> None:
    env = {
        "MODEL_API_KEY": "secret-value",
        "SAFECUT_SCENE_MODEL": "muse-wonder-1.0",
        "SAFECUT_JOB_USD_CAP": "2.5",
        "SAFECUT_SAM_FPS": "6",
        "SAFECUT_REPLAY": "1",
        "SAFECUT_SAM_SEND_STORE": "false",
        "SAFECUT_ASR_LANGUAGE_BIAS": "[]",
        "SAFECUT_META_BASE_URL": "https://api.meta.ai/v1/",
        "SAFECUT_ACCESS_CODES": json.dumps([{"code": "pilot-abc", "kind": "pilot", "cap_usd": 6.0}]),
        "SAFECUT_CODE_WINDOWS": json.dumps({"judge": ["2026-11-05T00:00:00Z", "2026-11-09T00:00:00Z"]}),
        "SAFECUT_SPEECH_FALLBACK_EFFORT": "",
    }
    s = load_settings(env)
    assert s.api_key() == "secret-value"
    assert s.scene_model == "muse-wonder-1.0"
    assert (s.job_usd_cap, s.sam_fps, s.replay, s.sam_send_store) == (2.5, 6, True, False)
    assert s.asr_language_bias == ()
    assert s.meta_base_url == "https://api.meta.ai/v1"
    assert s.access_codes[0].kind == "pilot"
    assert s.code_windows["judge"].until is not None
    assert s.code_windows["judge"].until.day == 9
    assert s.code_windows["pilot"] == config.DEFAULT_CODE_WINDOWS["pilot"]
    assert s.speech_fallback_effort == "omit"
    assert ("muse-wonder-1.0", "medium") in s.model_effort_pairs()


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"SAFECUT_ROLE_MODEL": "muse-spark-1.3-contributor"}, "Contributor"),
        ({"SAFECUT_SAM_FPS": "11"}, "sam_fps"),
        ({"SAFECUT_ESCALATE_EFFORT": "none"}, "escalate_effort"),
        ({"SAFECUT_SPEECH_FALLBACK_EFFORT": "max"}, "speech_fallback_effort"),
        ({"SAFECUT_ASR_LANGUAGE_BIAS": '["Swahili"]'}, "unsupported"),
        ({"SAFECUT_ASR_LANGUAGE_BIAS": "[English"}, "not valid JSON"),
        ({"SAFECUT_META_BASE_URL": "http://api.meta.ai/v1"}, "https"),
        ({"SAFECUT_META_BASE_URL": "https://api.meta.ai@evil.example/v1"}, "https"),
        ({"SAFECUT_META_BASE_URL": "https://api.meta.ai.evil.test/v1"}, "https"),
        ({"SAFECUT_META_BASE_URL": "https://169.254.169.254/v1"}, "https"),
        ({"SAFECUT_META_BASE_URL": "https://api.meta.ai:8443/v1"}, "https"),
        ({"SAFECUT_OPEN_BASE_URL": "https://api.meta.ai/v1"}, "https"),
        ({"SAFECUT_ACCESS_CODES": '[{"code": "pilot-1", "kind": "pilot"}]'}, "cap_usd"),
        ({"SAFECUT_ACCESS_CODES": '[{"code": "pilot-1", "kind": "pilot", "cap_usd": 7}]'}, "above"),
        ({"SAFECUT_ACCESS_CODES": '[{"code": "rec-1", "kind": "recording", "cap_usd": 15.01}]'}, "above"),
        ({"SAFECUT_ACCESS_CODES": '[{"code": "own-1", "kind": "owner", "cap_usd": 6.5}]'}, "above"),
        (
            {"SAFECUT_ACCESS_CODES": '[{"code": "x-123", "kind": "judge"}, {"code": "x-123", "kind": "public"}]'},
            "duplicate",
        ),
        (
            {"SAFECUT_ACCESS_CODES": '[{"code": "judge-1", "kind": "judge", "valid_until": "2026-12-01T00:00:00Z"}]'},
            "ends after",
        ),
        (
            {"SAFECUT_ACCESS_CODES": '[{"code": "judge-1", "kind": "judge", "valid_from": "2026-11-01T00:00:00Z"}]'},
            "starts before",
        ),
        ({"SAFECUT_CODE_WINDOWS": '{"judge": ["2026-11-05T00:00:00Z"]}'}, "SAFECUT_CODE_WINDOWS"),
        ({"SAFECUT_CODE_WINDOWS": "[]"}, "SAFECUT_CODE_WINDOWS"),
        ({"SAFECUT_JOB_USD_CAP": "0"}, "job_usd_cap"),
    ],
)
def test_bad_env_is_refused(env: dict[str, str], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_settings(env)


def test_errors_never_echo_values() -> None:
    secret = "sk-live-do-not-print"
    with pytest.raises(ConfigError) as info:
        load_settings({"MODEL_API_KEY": secret, "SAFECUT_SAM_FPS": secret})
    assert secret not in str(info.value)
    assert secret not in repr(load_settings({"MODEL_API_KEY": secret}))


def test_missing_key_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="MODEL_API_KEY"):
        load_settings({}).api_key()


@given(st.sampled_from(["muse-spark-1.3", "sam-3.1", "x"]), st.booleans())
def test_contributor_suffix_always_refused(model: str, contributor: bool) -> None:
    env = {"SAFECUT_ROLE_MODEL": model + ("-contributor" if contributor else "")}
    if contributor:
        with pytest.raises(ConfigError):
            load_settings(env)
    else:
        assert load_settings(env).role_model == model


def test_price_table_covers_every_default_model() -> None:
    s = load_settings({})
    for model in {s.role_model, s.scene_model, s.escalate_model, s.redteam_model, s.speech_fallback_model}:
        assert model in config.TOKEN_PRICES
    assert config.PRICE_TABLE_DATE == "2026-10-26"


def test_idle_timeouts_grow_with_effort() -> None:
    assert config.responses_idle_timeout("medium") < config.responses_idle_timeout("high")
    assert config.responses_idle_timeout("high") < config.responses_idle_timeout("max")
