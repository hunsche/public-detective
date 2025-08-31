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

### End-to-End (E2E) Tests

**Warning:** E2E tests are designed to run against real external services or local emulators and require a properly configured environment, including a valid `GCP_GEMINI_API_KEY`.

-   **Who Should Run This?** Agents working on the full application flow or making changes that could impact multiple components.
-   **Purpose:** The E2E test (`tests/e2e/test_full_e2e.py`) validates the entire application flow, from the command-line interface to the database, simulating a real-world scenario. It is crucial for verifying that all components are integrated correctly.

#### How to Run the E2E Test for Analysis

To properly execute the E2E test and view all the necessary output for critical analysis, you must run `pytest` with the `-s` flag. This flag disables output capturing, allowing you to see the real-time logs from the CLI commands and, most importantly, the final JSON data dump.

```bash
poetry run pytest -s tests/e2e/test_full_e2e.py
```

Without the `-s` flag, the test might appear to pass, but you will not see the critical data required for your audit.

#### E2E Test Workflow

The test script automates the following application workflow:
1.  **`pre-analyze`**: The CLI is called to find new procurements for a specific date and create initial `procurement_analysis` records in the database with a `PENDING_ANALYSIS` status.
2.  **Fetch IDs**: The test queries the database to get the `analysis_id`s of the records created in the previous step.
3.  **`analyze`**: The CLI is called in a loop for each `analysis_id`, which publishes a message to the Pub/Sub queue, triggering the full analysis for that item.
4.  **`worker`**: The worker process is started. It listens to the Pub/Sub queue, consumes the messages, and executes the core analysis logic for each one.
5.  **Validation**: The test asserts that the status of the processed records in the `procurement_analysis` table is now `ANALYSIS_SUCCESSFUL`.
6.  **Data Dump**: At the end of a successful run, the test prints a complete dump of all data from all tables in the test schema, formatted as JSON.

#### Agent's Task - Critical Analysis

When running this test, your primary role is to act as a critical auditor of the output. A passing test is not enough.
1.  **Scrutinize the Logs:** The test is designed to stream logs from each CLI command in real-time. Pay close attention to these logs for warnings, errors, or unexpected behavior during the run.
2.  **Examine the Final Data Dump:** This is the most critical part. The JSON dump at the end of the test shows the final state of the database. You must:
    -   **Verify Correctness:** Do not assume the data is correct. Does the `procurement` data match the `procurement_analysis` data? Are timestamps (`created_at`, `updated_at`) logical? Is the `risk_score` plausible?
    -   **Identify Inconsistencies:** Look for any anomalies, missing data, or unexpected values. For example, if the worker log shows it processed 3 messages, does the data dump show exactly 3 updated records?
    -   **Be Demanding:** Question every field. Your goal is to catch subtle bugs in business logic, data integrity, or component interaction that a simple pass/fail status might miss.

#### E2E Best Practices & Learnings
- **Real-time Logging is Crucial**: The test uses a helper function (`run_command`) to execute CLI commands as subprocesses while streaming their `stdout` and `stderr`. This is essential for debugging complex, multi-step interactions, as it shows exactly what each component is doing in real-time.
- **Timeouts Prevent Deadlocks**: The worker can hang indefinitely if it's waiting for messages that never arrive. The E2E test invokes the worker with a `--timeout` parameter. This ensures the test will fail fast rather than getting stuck, which is critical for CI/CD environments.

**Important**: Test coverage must always be greater than the threshold defined in `pyproject.toml`.
#### Test Database Schema
Integration and E2E tests run on a separate, temporary database schema to ensure isolation from development data. This is handled automatically by setting the `POSTGRES_DB_SCHEMA` environment variable during the test run (see `pytest.ini`). The `DatabaseManager` and Alembic migrations will use this schema if the variable is present.

## 5. Code Philosophy

- **No Inline Comments:** Code should be self-documenting through clear variable and method names. Use docstrings for classes and methods, not `#` comments.
- **Class Property Typing:** All instance properties (i.e., attributes assigned to `self`) must be explicitly typed at the class level. This improves readability and allows for better static analysis.

    ```python
    # Correct: Property is typed at the class level
    class MyService:
        my_repository: MyRepository

        def __init__(self, repo: MyRepository):
            self.my_repository = repo
    ```

    ```python
    # Incorrect: Property is not declared at the class level
    class MyService:
        def __init__(self, repo: MyRepository):
            self.my_repository = repo
    ```
- **Language:** All code, docstrings, and documentation are in **English**. The only exception is text that is user-facing or part of the AI prompt, which should be in **Portuguese (pt-br)**.
- **Logging:** Do not use `print()` for logging or debugging in the application code. Always use the `LoggingProvider` to get a logger instance. This ensures that all output is structured, contextual, and can be controlled centrally. `print()` is only acceptable in scripts meant for direct command-line interaction, such as `source/worker/test_analysis_from_db.py`.

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
