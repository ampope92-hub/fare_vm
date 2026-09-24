#!/usr/bin/env bash
# Build the interpreter. Run it as: /app/fvm/fvm IMAGE
set -euo pipefail
cd /app/fvm
fpc -O2 -Mobjfpc -Sh -FEobj -FUobj -o/app/fvm/fvm src/fvm.pas
