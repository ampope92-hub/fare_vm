"""Verifier for the FVM-2 interpreter.

test.sh compiles the agent's Pascal and runs the binary once per image, keeping each run's
standard output and exit status root-only under /opt/runs. This module compares those captures
with the expected transcripts under /opt/golden, byte for byte. It never runs agent code.
"""
import os
import pathlib

import pytest

GOLDEN = pathlib.Path("/opt/golden")
RUNS = pathlib.Path("/opt/runs")
SAMPLE_IMAGES = pathlib.Path("/opt/sample")
HELD_IMAGES = pathlib.Path("/opt/heldback")


def _read(path):
    """Read bytes without following a final symlink."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as fh:
        return fh.read()


def _stems(folder):
    return sorted(p.stem for p in folder.glob("*.fvm"))


def _explain(got, want):
    g, w = got.split(b"\n"), want.split(b"\n")
    for i in range(max(len(g), len(w))):
        a = g[i] if i < len(g) else b"<missing>"
        b = w[i] if i < len(w) else b"<missing>"
        if a != b:
            return f"line {i + 1}: got {a[:120]!r}, expected {b[:120]!r}"
    return "transcripts differ"


def _check(suite, stem):
    want = _read(GOLDEN / suite / f"{stem}.want")
    cap = RUNS / suite / f"{stem}.out"
    assert cap.is_file() and not cap.is_symlink(), f"no transcript was captured for {stem}"
    assert _read(RUNS / suite / f"{stem}.status").strip() != b"timeout", f"{suite}/{stem}: killed at the 10 s limit"
    got = _read(cap)
    assert got == want, f"{suite}/{stem}: {_explain(got, want)}"


def test_suites_present():
    """Both suites were staged and run: every image has a captured transcript."""
    assert len(_stems(SAMPLE_IMAGES)) == 128
    assert len(_stems(HELD_IMAGES)) == 61
    for suite, folder in (("sample", SAMPLE_IMAGES), ("heldback", HELD_IMAGES)):
        for stem in _stems(folder):
            assert (RUNS / suite / f"{stem}.out").is_file(), f"{suite}/{stem} was not run"


@pytest.mark.parametrize("stem", _stems(SAMPLE_IMAGES))
def test_conformance_image(stem):
    """The transcript for this image from /app/conformance matches the machine sheet byte for byte."""
    _check("sample", stem)


@pytest.mark.parametrize("stem", _stems(HELD_IMAGES))
def test_heldback_image(stem):
    """The transcript for this held-back image, built for another validator generation, matches byte for byte."""
    _check("heldback", stem)
