"""What the deploy workflow's smoke runs must show, as plain functions over their results (no Modal import), so
the rules are unit-tested (``tests/test_deploy.py``) and the Modal entry points only call them."""

from __future__ import annotations

from collections.abc import Mapping


def _run_problems(result: Mapping[str, object], *, unresolved: bool = True) -> list[str]:
    problems: list[str] = []
    if result.get("exit") != 0:
        problems.append(f"safecut run exited {result.get('exit')}: {result.get('tail')}")
    if unresolved and result.get("unresolved") != 0:
        problems.append(f"the audit left {result.get('unresolved')} unresolved")
    if result.get("receipt") is not True or result.get("redacted") is not True:
        problems.append("no receipt.json or redacted.mp4")
    return problems


#: What the worker smoke reports as its GPU probe when the deploy defines no GPU function (``deploy/modal_app.py``).
NO_GPU = "none (SAFECUT_DEPLOY_GPU=0)"
#: The detector the audit runs in the API container when there is no GPU (``safecut.audit``).
YUNET = "yunet-face"


def pre_deploy_problems(
    result: Mapping[str, object], *, gpu_required: bool = True, deploy_gpu: bool = True
) -> list[str]:
    """Before the deploy: the replay job ran every stage, and this image's GPU function ran EgoBlur on its render
    (the weights are on the ``safecut-models`` Volume, unaltered, and a GPU answered). With ``gpu_required`` off, a
    GPU problem is printed as a warning and doesn't block the deploy. With ``deploy_gpu`` off (``SAFECUT_DEPLOY_GPU=0``)
    there is no GPU function to probe: the smoke must say so, and nothing GPU is checked or warned about."""
    problems = _run_problems(result)
    if not deploy_gpu:
        probe = result.get("gpu_probe")
        if not isinstance(probe, Mapping) or probe.get("gpu") != NO_GPU:
            problems.append(f"the deploy defines no GPU function, but the smoke reported a GPU probe: {probe!r}")
        else:
            print(f"gpu: {NO_GPU}")
        return problems
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


def post_deploy_problems(
    result: Mapping[str, object], *, gpu_required: bool = True, deploy_gpu: bool = True
) -> list[str]:
    """After the deploy: a replay job run end to end through the deployed functions, its audit EgoBlur Gen 2 on a
    GPU, named so in its receipt (``auditor`` and ``auditor_device``). With ``gpu_required`` off, the GPU part only
    warns (the job itself must still have run). With ``deploy_gpu`` off (``SAFECUT_DEPLOY_GPU=0``) the audit must be
    YuNet in the API's own image, clear and named so: there is no GPU to check."""
    if not deploy_gpu:
        problems = _run_problems(result)
        if result.get("auditor") != YUNET:
            problems.append(f"the receipt names {result.get('auditor')!r}, not {YUNET}: the deploy has no GPU")
        if result.get("gpu_fallback"):
            problems.append(f"the audit tried a GPU the deploy doesn't define: {result.get('gpu_fallback')}")
        return problems
    problems = _run_problems(result, unresolved=False)
    # Unverifiable before a real deploy: EgoBlur on the drawn synthetic clip. An audit it couldn't clear counts with the
    # GPU's problems (so the GPU-optional switch covers it); the pre-deploy smoke's YuNet audit must always be clear.
    gpu = [f"the GPU audit left {result.get('unresolved')} unresolved"] if result.get("unresolved") != 0 else []
    gpu += _post_gpu_problems(result)
    if not gpu_required:
        for problem in gpu:
            print(f"::warning title=GPU auditor::{problem} (accepted: SAFECUT_DEPLOY_GPU_OPTIONAL=1)")
        return problems
    return problems + gpu


def _post_gpu_problems(result: Mapping[str, object]) -> list[str]:
    problems: list[str] = []
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
