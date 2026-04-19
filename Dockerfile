FROM python:3.12-slim

WORKDIR /app

# System deps for pysaml2 (lxml needs libxml2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev \
    libxslt-dev \
    xmlsec1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "flask>=3.0,<4.0" \
    "flask-cors>=4.0" \
    "gunicorn>=21.0" \
    "pysaml2>=7.0" \
    "cryptography>=41.0"

COPY app/ .

# Create data dir and non-root user
RUN mkdir -p /data \
    && useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app /data

VOLUME ["/data"]

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "120", "server:app"]
