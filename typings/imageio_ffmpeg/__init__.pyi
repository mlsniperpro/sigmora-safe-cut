# Minimal stubs for the parts of imageio-ffmpeg Safe Cut uses (the package ships no type hints).
from collections.abc import Generator
from typing import Any

def get_ffmpeg_exe() -> str: ...
def get_ffmpeg_version() -> str: ...
def read_frames(
    path: str,
    pix_fmt: str = ...,
    bpp: int | None = ...,
    input_params: list[str] | None = ...,
    output_params: list[str] | None = ...,
    bits_per_pixel: int | None = ...,
) -> Generator[Any]: ...
