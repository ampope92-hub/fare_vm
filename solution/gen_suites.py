"""Writes both FVM-2 suites and their transcripts.

  python3 solution/gen_suites.py        (from the task folder)

Sample suite: one image per rule of the machine sheet, shipped to the agent under
environment/conformance/ (six of them with their transcripts) and baked, with every
transcript, into the verifier image under tests/sample/ and tests/golden/sample/.
Held-back suite: programs built by heldback.py for other validator generations (other word
widths, stack, frame, string and tick limits), seed 41, only under tests/heldback/ and
tests/golden/heldback/. Transcripts come from fvm_model.py, which fvm.pas matches byte for
byte on every image. Running this again rebuilds every file byte for byte.
"""
import os
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fvm_model import run
from heldback import heldback
from sample_cases import CASES

TASK = HERE.parent
HELD_SEED = 41
SHOWN = {"bad_magic", "int_divzero_uncaught", "str_print_escapes", "stack_overflow_fault",
         "call_argument_slots", "raise_across_frames"}


def fresh(d):
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


def main():
    conf = fresh(TASK / "environment" / "conformance")
    samp = fresh(TASK / "tests" / "sample")
    held = fresh(TASK / "tests" / "heldback")
    gold = fresh(TASK / "tests" / "golden")
    gs = fresh(gold / "sample")
    gh = fresh(gold / "heldback")
    for i, (name, build) in enumerate(CASES.items(), start=1):
        stem = f"{i:02d}_{name}"
        img = build()
        want = run(img)
        (conf / f"{stem}.fvm").write_bytes(img)
        (samp / f"{stem}.fvm").write_bytes(img)
        (gs / f"{stem}.want").write_bytes(want)
        if name in SHOWN:
            (conf / f"{stem}.expected").write_bytes(want)
    for name, img in heldback(HELD_SEED).items():
        (held / f"{name}.fvm").write_bytes(img)
        (gh / f"{name}.want").write_bytes(run(img))
    for d in (conf, samp, held, gs, gh):
        for f in d.iterdir():
            os.chmod(f, 0o644)
    print(f"{len(CASES)} sample images, {len(list(held.iterdir()))} held-back images")


if __name__ == "__main__":
    main()
