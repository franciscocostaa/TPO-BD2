FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# Consolas de los motores: redis-cli (Debian) y mongosh (repositorio oficial de MongoDB).
# La imagen base trae el repositorio de Yarn con una clave vencida; no se usa y rompe apt-get update.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && curl -fsSL https://pgp.mongodb.com/server-8.0.asc \
        | gpg --dearmor -o /usr/share/keyrings/mongodb-server-8.0.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg] https://repo.mongodb.org/apt/debian bookworm/mongodb-org/8.0 main" \
        > /etc/apt/sources.list.d/mongodb-org-8.0.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends redis-tools mongodb-mongosh \
    && rm -rf /var/lib/apt/lists/*
