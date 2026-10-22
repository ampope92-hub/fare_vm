# Fare VM: A Clean-Room Bytecode Interpreter in Free Pascal

Transit fare readers run their fare rules as FVM-2 bytecode images. The back office needs its own interpreter so it can replay a disputed journey away from the device. The agent gets the machine specification (`/app/spec/FVM2.txt`), a 133-image vendor conformance suite (images only, no expected transcripts) and a Free Pascal project stub. It must implement an interpreter that runs `fvm IMAGE` and writes the exact transcript the spec defines to standard output. The task is offline, with only fpc and its run-time units available.

## What makes it hard

Nothing has to be discovered: the spec states every rule. The difficulty is that several dozen exact rules interact within a single run, and there are no reference transcripts to compare against. An interpreter that takes the obvious reading of one boundary rule fails a whole class of images. Examples from the spec:

- **Arithmetic.** Integers are two's complement at a width set by the image header, anywhere from 8 to 48 bits, so every result must be reduced. `LEN` and `BYTE` wrap too, so on an 8-bit reader a 200-byte string has length -56.
- **Division and shifts.** Division floors rather than truncates, and MIN / -1 wraps. Shift counts are unsigned, so a negative count is huge, and `USHR` reinterprets its result as signed.
- **Comparisons.** `EQ` across types yields 0, while `LT` across types raises.
- **Exceptions.** A raising instruction has already consumed its operands (except `CALL`). Errors unwind through frames and cut the operand stack back to the size the handler recorded only when the stack is larger. Unwinding can itself fault when the stack is full, and `RET` drops the handlers its frame installed.
- **Tick accounting.** Every instruction is charged before it takes effect. `CALL` costs the callee's slot count, and string instructions cost one tick per 8 bytes produced. For `PRINT` that means the escaped text, so where a budget runs out depends on the escaping rule.
- **Check order.** The spec fixes the order in which an instruction's faults and raises are checked.

The held-back images are fare-rule-style programs: tap histories folded into zones and capped fares, receipts built up to the string limit, recursive digit sums that run out of frames, byte-string sorts, check digits over card numbers, and field parsing. They are mixed with boundary-operand blocks for each instruction.

## How it's graded

The verifier compiles the collected `.pas`/`.pp`/`.inc` files with `fpc -O2 -Mobjfpc -Sh` as an unprivileged user (`build.sh` is not used). It checks that the generated link script names only fpc's own objects and run-time units. It then runs the binary once per image under a seccomp launcher (`tests/launch.c`) that refuses a second process and anonymous executables. Every other program on the box is closed, no directory is writable, and each image has a 10-second limit.

- **133 conformance images**, one per rule of the spec, each built as that rule's hard case.
- **61 held-back images**, staged only after the conformance runs. They use other word widths (8, 9, 10, 13, 20, 24, 27, 40 and 48 bits), other stack, frame, string and tick limits, programs on exactly their tick budget or a few ticks short, and redundant varint encodings.

Each transcript is compared byte for byte against an expected transcript held root-only in the verifier image, one test per image. The reward is 1 only if all 194 match and no run hit the time limit. Expected transcripts come from a Python model of the spec (`solution/fvm_model.py`). The Pascal reference matches it on all 194 graded images and on 488 further held-back images from eight other seeds. Eighty-five single-rule mutants of the reference (for example truncating division, signed `ULT`, shift count modulo W, handlers kept across `RET`) all score 0, and each fails its own conformance image.

## Repository layout

- `instruction.md` - the task prompt given to the agent
- `task.toml` - metadata, limits, and the difficulty, solution and verification write-ups
- `environment/` - agent container: `Dockerfile`, `spec/FVM2.txt`, `conformance/` (133 images), `fvm/` (stub `src/fvm.pas` and `build.sh`)
- `solution/` - `solve.sh`, reference `fvm.pas`, Python model `fvm_model.py`, assembler `fvm_asm.py`, and image generators (`gen_suites.py`, `sample_cases.py`, `heldback.py`)
- `tests/` - verifier `Dockerfile`, `test.sh`, `test_outputs.py`, seccomp `launch.c`, named copies of the conformance images (`sample/`), held-back images (`heldback/`), and expected transcripts (`golden/`)

## Running it

Requires Docker and Harbor (`uv tool install harbor` or `pip install harbor`). From the repo root:

```
harbor run -p . -a oracle
```

runs the reference solution through the verifier (should score reward 1). To try an agent:

```
harbor run -p . -a <agent> -m <model>
```

for example `-a claude-code`.

---

Task design, data generators, reference solution and verifier by Audrey Pope.
