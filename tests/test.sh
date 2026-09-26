#!/bin/bash

# Verifier entrypoint, in the verifier container: it sees only `artifacts` (the Pascal under
# /app/fvm/src); everything else is baked into tests/Dockerfile and nothing is fetched here.

set -uo pipefail

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

# Fold stderr into stdout: only stdout survives into the feedback bundle.
exec 2>&1

as_runner() {
  setpriv --clear-groups --no-new-privs --reuid runner --regid runner "$@"
}

# /tests (a runtime mount) and /logs/verifier are closed to the build user before any agent code
# is compiled or run. If the unprivileged user can still reach them or the root-only images and
# transcripts under /opt, the run is abandoned with reward 0 rather than graded. A listing is tried
# as well as test -r, because access(2) can answer yes for a file inside a mode 700 directory.
chmod 700 /tests 2>/dev/null || true
chmod 700 /logs/verifier 2>/dev/null || true
if as_runner bash -c 'test -r /tests/test_outputs.py || ls /logs/verifier || ls /opt/golden || ls /opt/sample || ls /opt/heldback' >/dev/null 2>&1; then
  echo "FATAL: /tests, /logs/verifier or the expected transcripts are reachable by the unprivileged"
  echo "build user, so agent code could read them; this run cannot be graded."
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi
echo "verifier files closed to the unprivileged build user"

# A root-owned copy of the collected sources, taken before anything else touches them. cp -a
# keeps the agent's modes, so the copy is closed to everyone but root.
rm -rf /opt/src_pristine
cp -a /app/fvm/src /opt/src_pristine
chmod -R go-rwx /opt/src_pristine

# Every executable on the system paths is closed to the build user while the interpreter runs, so
# a transcript cannot come out of a python, awk or shell the binary hands its work to. Root is not
# affected. fvm_launch is held out: it is root-only, drops to the build user, installs the seccomp
# filter and runs the one binary the build user may execute. The dynamic loader is left alone; fpc links its programs statically and
# the filter refuses a second process, so there is nothing for the loader to be handed.
TOOLS="$( { find /usr/local/bin /usr/local/sbin /usr/bin /bin /usr/sbin /sbin -xdev -type f -perm /111 2>/dev/null;
             for l in $(find /usr/local/bin /usr/bin /bin -xdev -type l 2>/dev/null); do t="$(readlink -f "$l")"; [ -f "$t" ] && echo "$t"; done; } \
  | sort -u | grep -v -E 'ld-linux|/ld\.so$' | grep -v -x -F -e /usr/local/bin/fvm_launch)"
close_tools() { for f in $TOOLS; do chmod 750 "$f" 2>/dev/null || true; done; }
open_tools()  { for f in $TOOLS; do chmod 755 "$f" 2>/dev/null || true; done; }
trap open_tools EXIT

# Build from the collected sources, as the build user, with the command instruction.md states.
# The agent's build.sh is not collected and not run. fpc is run with -Cn first: it compiles and
# writes the link script but stops before linking, so the link inputs it resolved can be checked.
rm -rf /app/fvm
mkdir -p /app/fvm/obj
cp -a /opt/src_pristine /app/fvm/src
chown -R runner:runner /app/fvm
build_start=$SECONDS
setsid \
  setpriv --clear-groups --no-new-privs --reuid runner --regid runner \
  bash -c 'cd /app/fvm && exec timeout -s KILL 900 fpc -Cn -O2 -Mobjfpc -Sh -FEobj -FUobj -Fu/app/fvm/src -Fi/app/fvm/src -o/app/fvm/fvm src/fvm.pas' &
bpid=$!
wait "$bpid"
bstatus=$?
echo "compile exit status: $bstatus"
kill -TERM -- -"$bpid" 2>/dev/null || true
kill -KILL -- -"$bpid" 2>/dev/null || true
as_runner bash -c 'kill -9 -1' 2>/dev/null || true

# Every INPUT() entry of the generated link script must be an object fpc just compiled under
# obj/ or a Free Pascal run-time unit. A {$L}, {$linklib} or {$librarypath} directive naming
# anything else shows up here and the link is refused, whatever the file is called.
link_ok=1
[ "$bstatus" -eq 0 ] || link_ok=0
if [ "$link_ok" -eq 1 ]; then
  for res in /app/fvm/link*.res; do
    [ -f "$res" ] || continue
    bad="$(awk '
      { line = $0 }
      infield == 0 && line ~ /INPUT[ \t]*\(/ { infield = 1; sub(/.*INPUT[ \t]*\(/, "", line) }
      infield == 1 {
        rest = line
        if (rest ~ /\)/) { sub(/\).*/, "", rest); infield = 0 }
        n = split(rest, a, /[ \t]+/)
        for (i = 1; i <= n; i++) if (a[i] != "") print a[i]
      }
    ' "$res" | grep -vE '^/usr/lib/x86_64-linux-gnu/fpc/' | grep -vE '^obj/[A-Za-z0-9_]+\.o$' || true)"
    if [ -n "$bad" ]; then
      echo "the link script names a file that is not an fpc object or run-time unit: $(echo "$bad" | tr '\n' ' ')"
      link_ok=0
    fi
  done
fi
if [ "$link_ok" -eq 1 ]; then
  left=$(( 900 - (SECONDS - build_start) ))
  [ "$left" -lt 1 ] && left=1
  setsid \
    setpriv --clear-groups --no-new-privs --reuid runner --regid runner \
    bash -c "cd /app/fvm && exec timeout -s KILL $left sh ppas.sh" &
  lpid=$!
  wait "$lpid"
  echo "link exit status: $?"
  kill -TERM -- -"$lpid" 2>/dev/null || true
  kill -KILL -- -"$lpid" 2>/dev/null || true
  as_runner bash -c 'kill -9 -1' 2>/dev/null || true
fi
[ "$link_ok" -eq 1 ] && [ -x /app/fvm/fvm ] || echo "the collected sources did not build into /app/fvm/fvm"

# The build output now belongs to root. The build user keeps one thing it can run, the binary,
# and nothing else it can read or execute under the project.
chown -R root:root /app/fvm
find /app/fvm -type d -exec chmod 755 {} +
find /app/fvm -type f -exec chmod 600 {} +
[ -f /app/fvm/fvm ] && chmod 755 /app/fvm/fvm

# No directory the build user can write to, so nothing can be dropped and executed during a run.
chown root:root /app && chmod 755 /app
chown -R root:root /home/runner && chmod -R go-w /home/runner
chmod 0755 /tmp /var/tmp /dev/shm
for d in /app /app/fvm /tmp /var/tmp /dev/shm /home/runner; do
  if as_runner test -w "$d" 2>/dev/null; then
    echo "FATAL: $d is writable by the unprivileged build user; the run cannot be graded."
    echo 0 > /logs/verifier/reward.txt
    exit 0
  fi
done
echo "no directory is writable by the unprivileged build user"

# run_suite <image-source-dir> <capture-dir>: stage the images root-owned (0755, each 0444), run the
# binary once per image as the build user under the seccomp launcher, stdout to a root-owned file,
# stderr dropped, 10 s per image. A run ending 124 or 137 after the full 10 s is marked "timeout".
run_suite() {
  local src="$1" caps="$2" staged img stem
  staged="$(mktemp -d /app/images_XXXXXXXX)"
  cp "$src"/*.fvm "$staged"/
  chown -R root:root "$staged"
  chmod 755 "$staged"
  chmod 444 "$staged"/*.fvm
  rm -rf "$caps" && mkdir -p "$caps" && chmod 700 "$caps"
  close_tools
  for img in "$staged"/*.fvm; do
    stem="$(basename "$img" .fvm)" t0="${EPOCHREALTIME/[.,]/}"
    ( cd /app/fvm && export HOME=/home/runner && exec timeout -s KILL 10 setsid \
        /usr/local/bin/fvm_launch /app/fvm/fvm "$img" ) > "$caps/$stem.out" 2>/dev/null
    st=$?; case $st in 124|137) [ $(( ${EPOCHREALTIME/[.,]/} - t0 )) -ge 10000000 ] && st=timeout ;; esac
    echo "$st" > "$caps/$stem.status"
  done
  open_tools
  as_runner bash -c 'kill -9 -1' 2>/dev/null || true
  rm -rf "$staged"
}

echo "=== conformance images ==="
run_suite /opt/sample /opt/runs/sample
# The held-back images are staged only now, after every conformance run has ended.
echo "=== held-back images ==="
run_suite /opt/heldback /opt/runs/heldback
echo "timed out: $(grep -lx timeout /opt/runs/*/*.status 2>/dev/null | wc -l) image(s)"

# Nothing the agent started may be alive while pytest runs or while the reward is written.
as_runner bash -c 'kill -9 -1' 2>/dev/null || true

# -P keeps the working directory off sys.path; the interpreter is called by full path.
cd /tests
/usr/local/bin/python3 -P -m pytest -o cache_dir=/tmp/pytest_cache \
  --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
