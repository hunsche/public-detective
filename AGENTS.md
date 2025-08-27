# Instructions for AI Agents

Hello! This document provides instructions on how to work on this project.

## 1. Project Overview

This project, named "Public Detective", is an AI-powered tool for analyzing public procurement documents in Brazil to find irregularities. It uses the Google Gemini API for text analysis.

Key architectural features:
- **Database Access:** All database access is managed through a singleton class, `DatabaseManager`, which provides a SQLAlchemy engine for connection pooling. It is mandatory to use this manager for all database interactions.
    - **Raw SQL and Parameter Binding:** Queries must be written as raw SQL strings and executed using SQLAlchemy's `text()` construct. To prevent SQL injection, all parameters must be passed as named bind parameters (e.g., `:param_name`), never with f-strings or `%s` formatting.
    - **No ORM:** This project uses SQLAlchemy Core for executing queries but does **not** use the high-level SQLAlchemy ORM for defining models or relationships.

    - **Example of a repository query:**
      ```python
      from sqlalchemy import text
      from providers.database import DatabaseManager

      class MyRepository:
          def __init__(self):
              self.engine = DatabaseManager.get_engine()

          def get_user(self, user_id: int):
              sql = text("SELECT * FROM users WHERE id = :user_id")
              with self.engine.connect() as conn:
                  result = conn.execute(sql, {"user_id": user_id}).first()
              return result
      ```

- **Idempotency:** Analysis of the same set of documents is skipped by checking a SHA-256 hash of the content.
- **Archiving:** Both original and processed documents are saved as zip archives to Google Cloud Storage for traceability.

### Architectural Principles

#### Layered Architecture

This project follows a Layered Architecture pattern to ensure a clean separation of concerns. This makes the codebase more modular, testable, and easier to maintain. The architecture is composed of three primary layers: Services, Providers, and Repositories.

-   **Services (`source/services/`) - The Brains**:
    -   **Responsibility**: This layer contains the core business logic of the application. It acts as an orchestrator or a "maestro".
    -   **Function**: A service is responsible for executing a specific business use case (e.g., "perform a procurement analysis"). It coordinates calls to various Repositories (to get or save domain data) and Providers (to interact with external tools) to accomplish its task.
    -   **Scope**: Services are domain-specific and represent the "how" of a business process.

-   **Repositories (`source/repositories/`) - The Database Interface**:
    -   **Responsibility**: Manage the persistence and retrieval of the application's domain models in the **database**.
    -   **Function**: They contain all the SQL queries and data mapping logic required to move data between the application and the database. They are called *by the Service layer*.
    -   **Scope**: Repositories are domain-specific. For example, `AnalysisRepository` only handles database operations for the `Analysis` model. They should **never** contain logic for interacting with other external services like GCS. A repository may store a *reference* to an external resource (like a GCS file path), but it does not handle the upload/download of that resource.

-   **Providers (`source/providers/`) - The External Tools**:
    -   **Responsibility**: Handle all low-level interactions with external services and APIs (e.g., Google Cloud Storage, Google Gemini, Pub/Sub).
    -   **Function**: They are responsible for client library setup, authentication, and exposing simple, generic methods (e.g., `gcs_provider.upload_file(...)`). They are called *by the Service layer*.
    -   **Scope**: Providers are context-agnostic. They do not know about the application's domain models. They simply perform their specific service.

#### Data and Control Flow

The flow of control is always orchestrated by the **Service** layer.

1.  A request to perform an action (e.g., from the CLI or a worker) calls a method in a **Service**.
2.  The **Service** executes the business logic.
3.  If it needs to interact with the database, it calls a method on a **Repository**.
4.  If it needs to interact with an external API (like GCS), it calls a method on a **Provider**.
5.  The Repository and Provider return data to the Service, which continues its execution until the use case is complete.

This ensures a unidirectional flow of dependencies and maintains a clear separation of responsibilities.

## 2. Environment Setup

The project is standardized on **Python 3.12**.

### A. Prerequisites
- Python 3.12
- Poetry
- Docker

### B. Installation Steps

1.  **Clone the repository.**
2.  **Install dependencies:**
    ```bash
    poetry install
    ```
3.  **Set up environment variables:**
    Create a `.env` file in the project root for the Gemini API key:
    ```
    GCP_GEMINI_API_KEY="your-gemini-api-key"
    ```

## 3. Running the Application and Services

This project uses `docker-compose` to manage dependent services (PostgreSQL, GCS emulator, etc.).

1.  **Start all services:**
    ```bash
    docker compose up -d
    ```
2.  **Apply database migrations:**
    ```bash
    poetry run alembic upgrade head
    ```
3.  **Run the main analysis script (example):**
    ```bash
    poetry run python source/cli --start-date 2025-01-01 --end-date 2025-01-02
    ```

## 4. Running Tests

### Unit Tests
These do not require any external services.
```bash
poetry run pytest tests/unit/
```

### Integration Tests
These require the Docker services to be running.
1.  Ensure services are up: `docker compose up -d`
2.  Run the integration tests:
    ```bash
    poetry run pytest tests/integrations/
    ```
**Important**: Test coverage must always be greater than the threshold defined in `pyproject.toml`.
#### Test Database Schema
Integration tests run on a separate, temporary database schema to ensure isolation from the development data. This is handled automatically by setting the `POSTGRES_DB_SCHEMA` environment variable during the test run (see `pytest.ini`). The `DatabaseManager` and Alembic migrations will use this schema if the variable is present.

## 5. Code Philosophy

- **No Inline Comments:** Code should be self-documenting through clear variable and method names. Use docstrings for classes and methods, not `#` comments.
- **Language:** All code, docstrings, and documentation are in **English**. The only exception is text that is user-facing or part of the AI prompt, which should be in **Portuguese (pt-br)**.

## 6. Database Migrations

### A. Raw SQL Only
**All database migrations MUST be written in raw SQL using `op.execute()`**. Do not use Alembic's ORM-based helpers like `op.alter_column()`, `op.create_table()`, etc.

### B. Non-Destructive Downgrades
The `downgrade` function of a migration **must never be destructive**. Instead of dropping a table or column, you must rename it with a `_dropped` suffix. This provides a safety mechanism for rollbacks.

**Example of a non-destructive downgrade:**
```python
def downgrade() -> None:
    op.execute("ALTER TABLE old_table_name RENAME TO old_table_name_dropped;")
```

## 7. Pre-commit Hooks

This project uses pre-commit hooks to enforce code quality and consistency. You **must** ensure your code passes these checks before submitting.

### A. Installation
First, install the hooks so they run automatically before each commit:
```bash
poetry run pre-commit install
```

### B. Usage and Troubleshooting
The hooks will run on changed files when you run `git commit`. However, the CI pipeline runs the checks on **all files**. This can cause the pipeline to fail even if your local commit succeeds.

To avoid this, it is **highly recommended** to occasionally run the checks on all files locally:
```bash
poetry run pre-commit run --all-files
```

This command simulates the CI environment and helps you find and fix issues in files you didn't directly modify.

Thank you for your contribution!
