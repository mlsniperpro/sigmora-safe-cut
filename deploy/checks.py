"""What the deploy workflow's smoke runs must show, as plain functions over their results (no Modal import), so
the rules are unit-tested (``tests/test_deploy.py``) and the Modal entry points only call them."""

from __future__ import annotations

from collections.abc import Mapping


def _run_problems(result: Mapping[str, object]) -> list[str]:
    problems: list[str] = []
    if result.get("exit") != 0:
        problems.append(f"safecut run exited {result.get('exit')}: {result.get('tail')}")
    if result.get("unresolved") != 0:
        problems.append(f"the audit left {result.get('unresolved')} unresolved")
    if result.get("receipt") is not True or result.get("redacted") is not True:
        problems.append("no receipt.json or redacted.mp4")
    return problems


def pre_deploy_problems(result: Mapping[str, object], *, gpu_required: bool = True) -> list[str]:
    """Before the deploy: the replay job ran every stage, and this image's GPU function ran EgoBlur on its render
    (the weights are on the ``safecut-models`` Volume, unaltered, and a GPU answered). With ``gpu_required`` off, a
    GPU problem is printed as a warning and doesn't block the deploy."""
    problems = _run_problems(result)
    gpu = _gpu_problems(result)
    if not gpu_required:
        for problem in gpu:
            print(f"::warning title=GPU auditor::{problem} (deploying anyway: SAFECUT_DEPLOY_GPU_OPTIONAL=1)")
        return problems
    return problems + gpu


def _gpu_problems(result: Mapping[str, object]) -> list[str]:
    problems: list[str] = []
    probe = result.get("gpu_probe")
    if not isinstance(probe, Mapping):
        problems.append("the GPU function wasn't probed")
    elif probe.get("refused") is not None:
        problems.append(f"the GPU function refused: {probe.get('refused')} ({probe.get('detail')})")
    elif not probe.get("gpu") or not probe.get("frames"):
        problems.append(f"the GPU function answered no GPU or no frames: {dict(probe)}")
    return problems


def post_deploy_problems(result: Mapping[str, object]) -> list[str]:
    """After the deploy: a replay job run end to end through the deployed functions, its audit EgoBlur Gen 2 on a
    GPU, named so in its receipt (``auditor`` and ``auditor_device``)."""
    problems = _run_problems(result)
    if result.get("auditor") != "egoblur-gen2":
        problems.append(f"the receipt names {result.get('auditor')!r}, not egoblur-gen2: the GPU audit didn't run")
    device = result.get("auditor_device")
    if not isinstance(device, str) or not device.startswith("cuda:"):
        problems.append(f"the receipt's auditor_device is {device!r}, not a named GPU (cuda:<name>)")
    if result.get("gpu_fallback"):
        problems.append(f"the GPU auditor fell back: {result.get('gpu_fallback')}")
    return problems


def ledger_problems(result: Mapping[str, object]) -> list[str]:
    if result.get("ok") is True:
        return []
    return [f"the spend ledger or the paid-action limiter doesn't work on the jobs Volume: {dict(result)}"]
