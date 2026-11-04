"""After ``modal deploy``: one replay job end to end through the deployed app, its audit on the GPU.

``uv run python -m deploy.verify_deploy`` (the deploy workflow runs it): calls the deployed ``pipeline_worker_smoke``
with ``audit_gpu=True``, so the job's audit reaches the deployed ``egoblur_detect`` exactly as the API's does, and
fails unless the receipt names EgoBlur Gen 2 on a GPU. With ``SAFECUT_DEPLOY_GPU=0`` (no GPU function deployed) it
calls it with ``audit_gpu=False`` and fails unless the receipt names YuNet, the audit clear. Needs
``MODAL_TOKEN_ID``/``MODAL_TOKEN_SECRET``.
"""

from __future__ import annotations

import json
import os
import sys

import modal

from deploy.checks import post_deploy_problems
from deploy.modal_app import APP_NAME, DEPLOY_GPU


def main() -> int:
    smoke = modal.Function.from_name(APP_NAME, "pipeline_worker_smoke")
    # SAFECUT_DEPLOY_GPU=0: the deployed app has no GPU function, so the job audits with YuNet, as the API's does.
    result = smoke.remote(audit_gpu=DEPLOY_GPU)
    print(json.dumps(result, indent=1, default=str))
    # SAFECUT_DEPLOY_GPU_OPTIONAL=1 (a repository variable, for a hotfix during a GPU outage): the GPU part warns.
    problems = post_deploy_problems(
        result, gpu_required=os.environ.get("SAFECUT_DEPLOY_GPU_OPTIONAL") != "1", deploy_gpu=DEPLOY_GPU
    )
    for problem in problems:
        print(f"FAIL  {problem}")
    if problems:
        return 1
    print(f"ok    replay job end to end; audited by {result['auditor']} on {result.get('auditor_device')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
