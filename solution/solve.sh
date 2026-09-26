#!/usr/bin/env bash
set -euo pipefail

# The interpreter, written straight from /app/spec/FVM2.txt: integers kept sign-extended in an
# Int64 and reduced to the header's width after every operation, floor division, shift counts
# read unsigned, each instruction checked in the order the sheet gives (decode, indexes, operands,
# raises, room, ticks) before it takes effect, and handlers that unwind frames and cut the stack.
install -m 644 "$(dirname "$0")/fvm.pas" /app/fvm/src/fvm.pas
bash /app/fvm/build.sh

# A look at how each conformance image ends.
for img in /app/conformance/*.fvm; do
  printf '%s  %s\n' "$(basename "$img")" "$(/app/fvm/fvm "$img" | tail -n 1)"
done
