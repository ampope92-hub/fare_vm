# The back-office replay tools are Free Pascal, so the interpreter is compiled with fpc.
# Canonical Python base: the harness runs on it. Nothing here needs a numerics stack.
FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# fpc is the whole toolchain; the interpreter uses the Free Pascal run-time units only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fpc \
        tmux \
        asciinema \
    && rm -rf /var/lib/apt/lists/*

# The project to finish, the machine sheet, and the conformance images.
COPY fvm /app/fvm
COPY spec /app/spec
COPY conformance /app/conformance
RUN chmod +x /app/fvm/build.sh && mkdir -p /app/fvm/obj \
    && chmod a-w /app/spec/* /app/conformance/*

WORKDIR /app
