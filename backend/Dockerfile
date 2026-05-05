# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_NO_INPUT=1 \
    PIP_VERSION=26.1 \
    SETUPTOOLS_VERSION=82.0.1 \
    WHEEL_VERSION=0.47.0

WORKDIR /app

COPY requirements-runtime.txt ./
RUN --mount=type=cache,id=rag-backend-pip-cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install --upgrade \
      "pip==${PIP_VERSION}" \
      "setuptools==${SETUPTOOLS_VERSION}" \
      "wheel==${WHEEL_VERSION}" && \
    python -m pip install --retries 10 -r requirements-runtime.txt

COPY . .
RUN --mount=type=cache,id=rag-backend-pip-cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install --no-deps -e "."

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
