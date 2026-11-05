FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr ffmpeg fonts-noto-core fonts-noto-extra ca-certificates curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install '.[deployment-test]' 'azure-storage-blob>=12,<13' 'azure-identity>=1,<2'
COPY scripts ./scripts
COPY prompts ./prompts
RUN groupadd -g 10001 preppulse && useradd -u 10001 -g 10001 -m preppulse
USER preppulse
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "preppulse_api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
