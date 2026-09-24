# Verifier image. Runs in its own container and sees only the paths declared in `artifacts`.
# It compiles the agent's Pascal and runs the interpreter once per image, so it needs fpc, and
# it compares transcripts with the standard library, so it needs nothing else.

# The interpreter runs under a small launcher that installs a seccomp filter (no anonymous
# executables, no second process). It is compiled in a throwaway stage and linked statically,
# so the final image carries the binary and no C compiler.
FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb AS launcher
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY launch.c /tmp/launch.c
RUN gcc -O2 -static -Wall -o /fvm_launch /tmp/launch.c

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update \
    && apt-get install -y --no-install-recommends fpc \
    && rm -rf /var/lib/apt/lists/*

# Verifier tooling, hash-pinned. Nothing is installed at trial time.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

COPY --from=launcher /fvm_launch /usr/local/bin/fvm_launch
RUN chmod 755 /usr/local/bin/fvm_launch

# Agent-authored code is compiled and run in this image, which also holds every expected
# transcript, so that code runs as `runner`, never as root.
RUN useradd --create-home --uid 10001 --shell /bin/bash runner

# Landing directory for the declared artifact.
RUN mkdir -p /app/fvm/src

# The conformance images (the same bytes the agent was given), the held-back images and every
# expected transcript, root-only. /tests is a runtime mount, so nothing is protected there.
COPY sample /opt/sample
COPY heldback /opt/heldback
COPY golden /opt/golden
RUN chmod -R go-rwx /opt/sample /opt/heldback /opt/golden

COPY . /tests/

WORKDIR /app
