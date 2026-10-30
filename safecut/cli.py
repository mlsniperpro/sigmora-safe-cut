"""``safecut``: the command line. One subcommand per stage (from :data:`safecut.stages.STAGES`), plus ``run``.

    safecut run <clip> --out <job_dir> [--replay] [--auto-approve-policy]   the whole job, locally
    safecut <stage> --job <job_dir> [--replay]                              one stage (prepare, track, …, receipt)
    safecut approve --job <job_dir>                                         approve the reviewed plan
    safecut publish --job <job_dir> [--replay]                              render → audit → receipt
    safecut validate --job <job_dir>                                        cross-check every contract file

Exit codes: 0 ok · 1 the job can't continue · 2 usage · 3 a stage isn't in this build yet · 4 a contract file is
invalid · 5 replay tried to reach the network · 6 the audit blocked publishing (the render must not be
published).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from safecut import netguard, pipeline
from safecut.config import load_settings
from safecut.contracts import Audit, ContractError, load, validate_job_dir
from safecut.stages import INTAKE, RECEIPT_HTML, REDACTED, STAGES, Stage, StageError, StageUnavailable

app = typer.Typer(
    name="safecut",
    help="Sigmora Safe Cut: hide everyone who shouldn't be published, and prove it.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)

JobOpt = Annotated[Path, typer.Option("--job", help="The job directory.", file_okay=False)]
ReplayOpt = Annotated[
    bool | None,
    typer.Option(
        "--replay/--live", help="Read saved responses from raw/ and never touch the network (default: SAFECUT_REPLAY)."
    ),
]


def _fail(code: int, message: str) -> NoReturn:
    typer.echo(f"safecut: {message}", err=True)
    raise typer.Exit(code)


def _replay(flag: bool | None) -> bool:
    replay = load_settings().replay if flag is None else flag
    if replay:
        netguard.block()
    return replay


def _guarded(action: Callable[[], None]) -> None:
    """Map the pipeline's typed errors to exit codes and one readable line."""
    try:
        action()
    except StageUnavailable as exc:
        _fail(3, str(exc))
    except (pipeline.StageOutputInvalid, ContractError) as exc:
        _fail(4, str(exc))
    except netguard.NetworkBlocked as exc:
        _fail(5, str(exc))
    except (pipeline.PipelineError, StageError) as exc:
        _fail(1, str(exc))


def _stage_command(stage: Stage) -> Callable[..., None]:
    def command(job: JobOpt, replay: ReplayOpt = None) -> None:
        def go() -> None:
            if stage.phase == "publish":
                pipeline.check_approval(job)  # render, audit and receipt run only on an approved plan
            result = pipeline.run_stage(job, stage, replay=_replay(replay), force=True)
            typer.echo(f"{stage.name}: wrote {result.output} ({result.elapsed_s:.2f} s)")

        _guarded(go)

    command.__doc__ = f"Run the {stage.name} stage: writes {stage.output} (lane {stage.lane})."
    return command


def _prepare_command(stage: Stage) -> Callable[..., None]:
    def command(
        job: JobOpt,
        clip: Annotated[
            Path | None, typer.Argument(help="Create the job from this clip first.", dir_okay=False)
        ] = None,
        replay: ReplayOpt = None,
    ) -> None:
        def go() -> None:
            mode = _replay(replay)
            if clip is not None:
                pipeline.create_job(clip, job, mode="replay" if mode else "live")
            elif not (job / INTAKE).is_file():
                raise pipeline.PipelineError(f"{job}: no {INTAKE}; pass the clip: safecut prepare <clip> --job …")
            result = pipeline.run_stage(job, stage, replay=mode, force=True)
            typer.echo(f"{stage.name}: wrote {result.output} ({result.elapsed_s:.2f} s)")

        _guarded(go)

    command.__doc__ = f"Run the {stage.name} stage: writes {stage.output} (lane {stage.lane})."
    return command


for _stage in STAGES:
    app.command(_stage.name)((_prepare_command if _stage.name == "prepare" else _stage_command)(_stage))


def _report(results: list[pipeline.StageResult]) -> None:
    for result in results:
        typer.echo(f"  {result.stage:<10} {result.event:<7} {result.elapsed_s:7.2f} s  {result.output.name}")


@app.command()
def run(
    clip: Annotated[Path, typer.Argument(help="The source clip (≤ 60 s, ≤ 150 MB).", dir_okay=False)],
    out: Annotated[Path, typer.Option("--out", help="A new job directory; its name is the job ID.", file_okay=False)],
    replay: ReplayOpt = None,
    auto_approve_policy: Annotated[
        bool, typer.Option("--auto-approve-policy", help="Accept the policy's decisions without review, then render.")
    ] = False,
    replay_from: Annotated[
        Path | None,
        typer.Option(
            "--replay-from",
            help="A recorded job (with raw/) to replay; default: looked up by the clip's sha256 in fixtures/jobs/.",
            file_okay=False,
        ),
    ] = None,
) -> None:
    """Run the whole job locally: analyse, stop for review (or auto-approve), then render, audit and receipt."""

    def go() -> None:
        mode = _replay(replay)
        recording: Path | None = None
        if mode:
            recording = replay_from or pipeline.find_recording(pipeline.sha256_file(clip))
            if recording is None:
                raise pipeline.PipelineError(
                    f"no recorded responses for {clip.name} (sha256 not in fixtures/jobs/*/raw/manifest.json); "
                    "pass --replay-from <job dir>, or record them with scripts/go-live.sh"
                )
        pipeline.create_job(clip, out, mode="replay" if mode else "live")
        if recording is not None:
            pipeline.attach_recording(out, recording)
        typer.echo(f"job {out.name}: analysing ({'replay' if mode else 'live'})")
        _report(pipeline.analyse(out, replay=mode))
        if not auto_approve_policy:
            typer.echo(
                f"job {out.name}: waiting for review. Edit decisions in the web app, or approve as is with:\n"
                f"  safecut approve --job {out} && safecut publish --job {out}"
            )
            return
        pipeline.approve(out, how="auto_policy")
        typer.echo(f"job {out.name}: policy decisions approved; publishing")
        _report(pipeline.publish(out, replay=mode))
        _refuse_if_blocked(out)
        typer.echo(f"job {out.name}: done: {out / REDACTED}, {out / 'receipt.json'}, {out / RECEIPT_HTML}")

    _guarded(go)


@app.command()
def approve(job: JobOpt) -> None:
    """Approve the job's current decisions as reviewed (writes approval.json)."""
    _guarded(lambda: typer.echo(f"approved at {pipeline.approve(job, how='review').approved_at.isoformat()}"))


@app.command()
def publish(job: JobOpt, replay: ReplayOpt = None) -> None:
    """Render, audit and seal the receipt for an approved job."""

    def go() -> None:
        _report(pipeline.publish(job, replay=_replay(replay)))
        _refuse_if_blocked(job)

    _guarded(go)


def _refuse_if_blocked(job: Path) -> None:
    """The audit's verdict decides: a blocked audit is never reported as done (exit 6, the reason and the count)."""
    audit = load(job / "audit.json", Audit)
    if audit.blocked_reason is not None:
        _fail(
            6,
            f"the audit blocked publishing ({audit.blocked_reason}, {audit.unresolved} unresolved): "
            f"don't publish {job / REDACTED}; review the job and run the audit again",
        )


@app.command()
def validate(job: JobOpt) -> None:
    """Validate every contract file in the job directory and cross-check them."""

    def go() -> None:
        loaded = validate_job_dir(job)
        typer.echo(f"{job.name}: valid ({', '.join(sorted(loaded))})")

    _guarded(go)


def main() -> None:
    app(prog_name="safecut")


if __name__ == "__main__":
    sys.exit(main())
