# Dockerfile

# ---- Builder Stage ----
# This stage installs dependencies and builds the application.
FROM python:3.12-slim-bookworm as builder

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.2 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

# Install system dependencies required for the application and poetry
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-headless \
    imagemagick \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python -

# Add Poetry to PATH
ENV PATH="$POETRY_HOME/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy dependency definition files
COPY pyproject.toml poetry.lock poetry.toml ./

# Install dependencies
RUN poetry install --no-dev --no-root

# ---- Final Stage ----
# This stage creates the final, lean production image.
FROM python:3.12-slim-bookworm as final

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    POETRY_HOME="/opt/poetry"

# Create a non-root user for security
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Install system dependencies required at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-headless \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy the installed dependencies and poetry from the builder stage
COPY --from=builder /opt/poetry /opt/poetry
COPY --from=builder /app /app

# Copy the application source code
COPY source/ ./source/

# Give ownership to the non-root user
RUN chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Set the entrypoint for the application
# The final command (e.g., "api", "worker") will be provided by Cloud Run.
ENTRYPOINT ["/opt/poetry/bin/poetry", "run", "python", "-m", "public_detective.cli"]
