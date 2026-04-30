FROM python:3.11-slim-bookworm

ARG GDAL_VERSION=3.10.3

# Install GDAL from Debian Trixie (3.10.x — bookworm only has 3.6.x).
# Trixie is pinned at low priority; only gdal-* and libgdal* come from it.
RUN apt-get update && apt-get install -y --no-install-recommends gnupg \
    && echo "deb http://deb.debian.org/debian trixie main" > /etc/apt/sources.list.d/trixie.list \
    && printf 'Package: *\nPin: release a=trixie\nPin-Priority: 50\n\nPackage: gdal-* libgdal*\nPin: release a=trixie\nPin-Priority: 500\n' \
       > /etc/apt/preferences.d/trixie-gdal \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        gdal-bin \
        libgdal-dev \
    && apt-get install -y --no-install-recommends gcc g++ \
    && apt-get purge -y gnupg && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml ./
COPY main.py map_parser.py transformer.py tiler.py database.py map_calc_tools.py ./

# Install Python dependencies (GDAL pip package must match system libgdal version)
RUN uv pip install --system --no-cache-dir gdal==${GDAL_VERSION} \
    && uv pip install --system --no-cache-dir .

ENTRYPOINT ["python", "/app/main.py"]
