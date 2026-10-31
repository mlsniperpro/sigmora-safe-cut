"""After ``modal deploy``: one replay job end to end through the deployed app, its audit on the GPU.

``uv run python -m deploy.verify_deploy`` (the deploy workflow runs it): calls the deployed ``pipeline_worker_smoke``
with ``audit_gpu=True``, so the job's audit reaches the deployed ``egoblur_detect`` exactly as the API's does, and
fails unless the receipt names EgoBlur Gen 2 on a GPU. Needs ``MODAL_TOKEN_ID``/``MODAL_TOKEN_SECRET``.
"""

from __future__ import annotations

import json
import sys

import modal

from deploy.checks import post_deploy_problems
from deploy.modal_app import APP_NAME


def main() -> int:
    smoke = modal.Function.from_name(APP_NAME, "pipeline_worker_smoke")
    result = smoke.remote(audit_gpu=True)
    print(json.dumps(result, indent=1, default=str))
    problems = post_deploy_problems(result)
    for problem in problems:
        print(f"FAIL  {problem}")
    if problems:
        return 1
    print(f"ok    replay job end to end; audited by {result['auditor']} on {result['auditor_device']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
