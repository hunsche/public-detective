# Instructions for AI Agents

Hello! This document provides instructions on how to work on this project.

## 1. Project Overview

This project, named "Public Detective", is an AI-powered tool for analyzing public procurement documents in Brazil to find irregularities. It uses the Google Gemini API for text analysis.

File conversion from office formats (e.g., DOCX, XLSX) to plain text formats (PDF, CSV) is handled by the **LibreOffice** command-line tool.

The database access layer uses `psycopg2` with a connection pool, executing raw SQL queries for performance and control. It does not use a high-level ORM.

## 2. Environment Setup

This project uses `asdf` to manage tool versions. The required versions are specified in the `.tool-versions` file. It is highly recommended to follow these steps to ensure a consistent development environment.

### A. Install `asdf` and Dependencies

1.  **Install `asdf`:**
    Follow the [official asdf installation guide](https://asdf-vm.com/guide/getting-started.html). The recommended method is to clone the repository:
    ```bash
    git clone https://github.com/asdf-vm/asdf.git ~/.asdf --branch v0.14.0
    ```
    Then, add `asdf` to your shell's startup file (e.g., `~/.bashrc`, `~/.zshrc`):
    ```bash
    . "$HOME/.asdf/asdf.sh"
    ```
    **Important:** Restart your shell after making this change.

2.  **Install Build Dependencies:**
    `asdf` compiles Python from source, which requires build dependencies. For Debian/Ubuntu-based systems, run:
    ```bash
    sudo apt-get update
    sudo apt-get install -y build-essential libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm \
    libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
    ```

3.  **Install LibreOffice:**
    The execution environment **must have LibreOffice installed**. On Debian/Ubuntu, you can install it with:
    ```bash
    sudo apt-get install -y libreoffice
    ```

### B. Install Project Tools and Dependencies

1.  **Add `asdf` Plugins:**
    ```bash
    asdf plugin-add python
    asdf plugin-add poetry
    ```

2.  **Install Tool Versions:**
    Navigate to the project root directory and run `asdf install`. This will install the correct versions of Python and Poetry as defined in `.tool-versions`.
    ```bash
    asdf install
    ```

3.  **Configure Poetry's Environment:**
    This is a crucial step to link Poetry with the `asdf`-managed Python version.
    ```bash
    poetry env use python
    ```

4.  **Install Project Dependencies:**
    This creates a `.venv` and installs all packages from `pyproject.toml`.
    ```bash
    poetry install
    ```

## 3. Running Tests

### Unit Tests
To run the unit tests, use Pytest via Poetry. These do not require any external services.
```bash
poetry run pytest tests/
```

### Integration Tests
Integration tests require the Docker services to be running.
1.  Start the services:
    ```bash
    docker-compose up -d
    ```
2.  Run the integration tests:
    ```bash
    poetry run pytest tests/integration/
    ```
3.  Shut down the services when you're done:
    ```bash
    docker-compose down
    ```

## 4. Database Migrations

The project uses Alembic to manage database schema migrations.
- To apply all migrations: `poetry run alembic upgrade head`
- To create a new migration (after changing a model): `poetry run alembic revision --autogenerate -m "Your migration message"`
  (Note: This requires a running database connection).

Thank you for your contribution!
