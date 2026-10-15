ARG PYTHON_IMAGE=python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# glibc is required by the operator-provisioned Ubuntu llama.cpp release.
# Keep this image compatible with actual local CPU inference, not just its CLI.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca PIP_CERT=/run/secrets/proxy_ca NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --shell /usr/sbin/nologin appuser \
    && install -d -o appuser -g appuser -m 0750 /app/data

# Dependencies come from the same canonical metadata as host installation.
# Resolve them before source so a code-only rebuild retains this cache layer.
COPY pyproject.toml README.md ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca PIP_CERT=/run/secrets/proxy_ca NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    python -c "import pathlib,tomllib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); p=d['project']; r=p['dependencies']+p['optional-dependencies']['local-inference']+p['optional-dependencies']['hosted-inference']+d['build-system']['requires']; pathlib.Path('/tmp/skeleton-runtime-requirements.txt').write_text('\n'.join(r)+'\n')" \
    && pip install --no-cache-dir -r /tmp/skeleton-runtime-requirements.txt \
    && rm /tmp/skeleton-runtime-requirements.txt

# Dockerfile.dockerignore admits only canonical runtime source and contracts.
# One source layer avoids repeated full source snapshots on VFS builders.
COPY --chown=appuser:appuser . .

# The installer toolchain is build-time only. pip 26.2+ also carries vendored
# packages plus an embedded CycloneDX SBOM under pip/_vendor; leaving that
# tree in a production image makes those vendored copies part of the runtime
# attack surface and causes image scanners to report them independently of
# the application's installed packages. Install first, then remove the full
# installer/toolchain surface from the final runtime.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca PIP_CERT=/run/secrets/proxy_ca NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir --no-deps --no-build-isolation -e . \
    && pip uninstall -y msgpack setuptools \
    && rm -rf /usr/local/lib/python3.14/site-packages/msgpack* \
              /usr/local/lib/python3.14/site-packages/setuptools* \
              /usr/local/lib/python3.14/site-packages/pkg_resources* \
              /usr/local/lib/python3.14/site-packages/pip \
              /usr/local/lib/python3.14/site-packages/pip-*.dist-info \
              /usr/local/bin/pip*

USER appuser

EXPOSE 8001

# Probe only the public liveness contract and use Python's standard library so
# the runtime image does not gain curl/apt packages solely for health checks.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/v1/health/live', timeout=5).read()" || exit 1

CMD ["uvicorn", "skeleton.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
