FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libreoffice-writer-nogui \
    imagemagick \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1
ENV PATH="$POETRY_HOME/bin:$PATH"

RUN curl -sSL https://install.python-poetry.org | python3 -

WORKDIR /app

# Copy project files
COPY pyproject.toml poetry.lock ./
COPY source ./source
COPY README.md ./

# Install dependencies
RUN poetry install --without development,tests

# Set entrypoint
ENTRYPOINT ["pd"]
