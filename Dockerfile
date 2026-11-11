# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: builder
# Compilers and -dev headers (gcc, linux-libc-dev, libsqlcipher-dev, ...) are
# only needed to build pysqlcipher3. They stay in this stage and never reach
# the final image, which removes thousands of kernel-header CVEs.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev \
        libsqlcipher-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir \
        "flask>=3.0,<4.0" \
        "flask-cors>=4.0" \
        "gunicorn>=23.0" \
        "pysaml2>=7.0" \
        "cryptography>=41.0" \
        "pysqlcipher3>=1.2" \
        "pyotp>=2.9" \
        "flask-limiter>=3.5" \
        "certifi>=2026.10.18" \
    && pip uninstall -y setuptools wheel \
    && python -m pip uninstall -y pip

# ---------------------------------------------------------------------------
# Stage 2: runtime
# Only the runtime libraries: xmlsec1 (CLI used by pysaml2) and sqlcipher
# (pulls in the shared libsqlcipher library that pysqlcipher3 links against).
# apt-get upgrade applies Debian security fixes newer than the base image
# (openssl, perl-base, zlib, ...).
# pip is removed from the final image: it is not needed at runtime and its
# vendored packages (setuptools, ...) are a recurring source of CVEs.
# ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        xmlsec1 \
        sqlcipher \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.12/ensurepip/_bundled

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY app/ .

# Create data dir and non-root user
RUN mkdir -p /data \
    && useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app /data

VOLUME ["/data"]

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/ping')" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "120", "server:app"]
