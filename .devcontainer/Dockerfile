FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && install -m 0755 /root/.local/bin/uv /usr/local/bin/uv \
    && uv --version
