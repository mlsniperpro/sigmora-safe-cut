"""The prompt texts (v1, from ``docs/prompts/``) and the one way their ``{slots}`` are filled."""

from __future__ import annotations

import re
from functools import cache
from importlib import resources

VERSION = "v1"
_SLOT = re.compile(r"\{([a-z_]+)\}")


@cache
def text(name: str) -> str:
    """The prompt file ``<name>.txt``, without its trailing newline."""
    return resources.files(__package__).joinpath(f"{name}.txt").read_text(encoding="utf-8").rstrip("\n")


#: A transcript turn quoted in a prompt: one diarized turn can be a whole monologue, and a mid-turn introduction or
#: a mention of a child must survive the cut.
TURN_CHARS = 1500


def inline(text: str, limit: int = 300) -> str:
    """Model or transcript text quoted inside a later prompt: one line (so it can't forge the prompt's own lines
    or labels) and bounded (so a long sign or speech can't crowd out the instructions)."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def render(name: str, **values: str) -> str:
    """Fill ``{slot}``s with ``values``. Only the template's own slots are replaced, once each, so braces or
    slot-like text inside a value (a transcript, a label) are never interpreted. A missing value is an error."""
    template = text(name)
    needed = set(_SLOT.findall(template))
    missing = needed - values.keys()
    if missing:
        raise KeyError(f"prompt {name} needs {sorted(missing)}")
    return _SLOT.sub(lambda m: values[m.group(1)] if m.group(1) in needed else m.group(0), template)
