# Instructions for AI Agents

Hello! This document provides instructions on how to work on this project.

## 1. Project Overview

This project, named "Public Detective", is an AI-powered tool for analyzing public procurement documents in Brazil to find irregularities. It uses the Google Gemini API for text analysis.

Key architectural features:
- **Database Access:** All database access is managed through a singleton class, `DatabaseManager`, which provides a SQLAlchemy engine for connection pooling. It is mandatory to use this manager for all database interactions.
    - **Raw SQL and Parameter Binding:** Queries must be written as raw SQL strings and executed using SQLAlchemy's `text()` construct. To prevent SQL injection, all parameters must be passed as named bind parameters (e.g., `:param_name`), never with f-strings or `%s` formatting.
    - **No ORM:** This project uses SQLAlchemy Core for executing queries but does **not** use the high-level SQLAlchemy ORM for defining models or relationships.
- **UUIDs for Primary Keys:** All primary keys in the database must be of type `UUID` and use `uuid_generate_v4()` as the default value. This ensures that primary keys are unique across the entire system, not just within a single table.

    - **Example of a repository query:**
      ```python
      from sqlalchemy import text
      from providers.database import DatabaseManager

      class MyRepository:
          def __init__(self):
              self.engine = DatabaseManager.get_engine()

          def get_user(self, user_id: int):
              sql = text("SELECT id, name, email FROM users WHERE id = :user_id")
              with self.engine.connect() as conn:
                  result = conn.execute(sql, {"user_id": user_id}).first()
              return result
      ```

- **Avoid `SELECT *`:** Always specify the exact columns you need in your `SELECT` statements. This makes queries more readable, prevents pulling unnecessary data, and makes the code more resilient to changes in the database schema. The only exception for this rule is for E-to-E tests.

- **No Abbreviations in SQL:** All table names, column names, and aliases in SQL queries must be fully spelled out and descriptive. Avoid abbreviations (e.g., use `users` instead of `u`, `user_id` instead of `uid`) to maximize readability and maintainability.

- **Idempotency:** Analysis of the same set of documents is skipped by checking a SHA-256 hash of the content.
- **Archiving:** Both original and processed documents are saved as zip archives to Google Cloud Storage for traceability.
- **Status Auditing:** Every change to an analysis's status is recorded in a dedicated `procurement_analysis_status_history` table, providing a full audit trail for debugging and observability.
- **Orphan Task Handling:** A dedicated CLI command, `reap-stale-tasks`, is provided to find and reset tasks that have been stuck in the `IN_PROGRESS` state for too long.

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

#### Dependency Injection Pattern

The glue that holds these layers together is a form of Dependency Injection (DI).

- **Concept**: Instead of a class creating its own dependencies (e.g., a Service creating its own Repository instance), the dependencies are "injected" from the outside, typically during the class's initialization.
- **Our Pattern: Constructor Injection**: Dependencies are passed in as arguments to the `__init__` method of a class. The main application entry points (e.g., the CLI command handlers) act as the "composition root" where the application's object graph is constructed.
- **Rule**: All dependencies (Repositories, Providers, etc.) **must** be passed into a Service's constructor. Do not instantiate dependencies inside a Service. This is critical for testability, as it allows mock dependencies to be injected during unit tests.

## 2. Environment Setup

The project is standardized on **Python 3.12**.

### A. Prerequisites
- Python 3.12
- Poetry
- Docker
- LibreOffice Headless
- ImageMagick

### B. Installation Steps

1.  **Clone the repository.**
2.  **Install dependencies:**
    ```bash
    poetry install
    ```
3.  **Set up environment variables:**
    This project relies on environment variables for configuration. For full functionality, especially E2E tests that interact with live GCP services, the environment **must** be configured with valid `GCP_SERVICE_ACCOUNT_CREDENTIALS`. The agent should assume these credentials are provided and valid.

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

### 4.1. Test Writing Style (`pytest` only)

To maintain consistency and leverage the best features available, all tests in this project **must** be written using the modern `pytest` style. The use of the legacy `unittest` framework is prohibited for any new or modified tests.

-   **Use Plain `assert`**: All assertions should use Python's built-in `assert` statement. Do not use `unittest.TestCase` methods like `self.assertEqual()` or `self.assertTrue()`.
-   **Use `pytest` Fixtures**: For test setup and teardown, use `@pytest.fixture` decorators. Do not use `unittest`'s class-based `setUp()` and `tearDown()` methods.
-   **Write Functional Tests**: Tests should be simple functions (e.g., `def test_something():`). Do not use `class TestSomething(unittest.TestCase):` inheritance.

This rule is enforced to ensure all tests are clean, readable, and consistent with modern Python best practices.

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

**Warning:** E2E tests are designed to run against real external services or local emulators and require a properly configured environment.

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
1.  **`pre-analyze`**: The CLI is called to find new procurements for a specific date and create initial `procurement_analyses` records in the database with a `PENDING_ANALYSIS` status.
2.  **Fetch IDs**: The test queries the database to get the `analysis_id`s of the records created in the previous step.
3.  **`analyze`**: The CLI is called in a loop for each `analysis_id`, which publishes a message to the Pub/Sub queue, triggering the full analysis for that item.
4.  **`worker`**: The worker process is started. It listens to the Pub/Sub queue, consumes the messages, and executes the core analysis logic for each one.
5.  **Validation**: The test asserts that the status of the processed records in the `procurement_analyses` table is now `ANALYSIS_SUCCESSFUL`.
6.  **Data Dump**: At the end of a successful run, the test prints a complete dump of all data from all tables in the test schema, formatted as JSON.

#### Agent's Task - Critical Analysis

When running this test, your primary role is to act as a critical auditor of the output. A passing test is not enough.
1.  **Scrutinize the Logs:** The test is designed to stream logs from each CLI command in real-time. Pay close attention to these logs for warnings, errors, or unexpected behavior during the run.
2.  **Examine the Final Data Dump:** This is the most critical part. The JSON dump at the end of the test shows the final state of the database. You must:
    -   **Verify Correctness:** Do not assume the data is correct. Does the `procurement` data match the `procurement_analyses` data? Are timestamps (`created_at`, `updated_at`) logical? Is the `risk_score` plausible?
    -   **Identify Inconsistencies:** Look for any anomalies, missing data, or unexpected values. For example, if the worker log shows it processed 3 messages, does the data dump show exactly 3 updated records?
    -   **Be Demanding:** Question every field. Your goal is to catch subtle bugs in business logic, data integrity, or component interaction that a simple pass/fail status might miss.

#### E2E Best Practices & Learnings
- **Real-time Logging is Crucial**: The test uses a helper function (`run_command`) to execute CLI commands as subprocesses while streaming their `stdout` and `stderr`. This is essential for debugging complex, multi-step interactions, as it shows exactly what each component is doing in real-time.
- **Timeouts Prevent Deadlocks**: The worker can hang indefinitely if it's waiting for messages that never arrive. The E2E test invokes the worker with a `--timeout` parameter. This ensures the test will fail fast rather than getting stuck, which is critical for CI/CD environments.

**Important**: Test coverage must always be greater than the threshold defined in `pyproject.toml`.
#### Test Database Schema
Integration and E2E tests run on a separate, temporary database schema to ensure isolation from development data. This is handled automatically by setting the `POSTGRES_DB_SCHEMA` environment variable during the test run (see `pytest.ini`). The `DatabaseManager` and Alembic migrations will use this schema if the variable is present.

## 5. Code Philosophy

- **No Abbreviations:** Variable names must be fully spelled out and descriptive. Avoid abbreviations (e.g., use `procurement` instead of `proc`, `candidate` instead of `c`) to maximize readability and create self-documenting code.
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
- **Exception Handling:** Service layer methods (`source/services/`) must catch generic exceptions and re-raise them as specific, custom exceptions from the `source/exceptions/` package (e.g., `AnalysisError`). The presentation layers (`cli`, `worker`) are responsible for catching these specific exceptions and handling user-facing feedback (e.g., logging, raising `click.Abort()`).

- **File Naming Conventions:**
    - **Models (`source/models/`):** Filenames must be **plural** (e.g., `analyses.py`, `procurements.py`), as they define data structures that are often handled as collections.
    - **Repositories (`source/repositories/`):** Filenames must be **plural** (e.g., `analyses.py`, `procurements.py`), as they manage collections of data entities.
    - **Services (`source/services/`):** Filenames must be **singular** (e.g., `analysis.py`, `converter.py`), as they provide specific business capabilities. The `_service` suffix in filenames is not allowed.

### C. Google Gemini API Imports
**This is a critical project-specific rule. Violation of this rule will lead to incorrect behavior and pipeline failures.**

The official Google Generative AI SDK has two namespaces: `google.genai` and the legacy `google.generativeai`. The `google.generativeai` namespace is **deprecated** and its usage is strictly **prohibited** in this project.

-   **All imports** related to the Gemini API **must** come from the `google.genai` package.
-   Do **not** use any imports from `google.generativeai`. This includes submodules like `google.generativeai.client`.

**Correct Usage:**
```python
from google.genai import types
from google.genai import GenerativeModel

# Correct: All types and classes come from the `google.genai` root.
contents: types.ContentsType = [...]
```

**Incorrect Usage (Prohibited):**
```python
# Incorrect: This will be rejected by the linter and CI.
from google.generativeai.client import content_types

# Incorrect: This namespace is deprecated and must not be used.
from google.generativeai import types
```

This rule is enforced to maintain consistency and avoid issues caused by mixing legacy and modern APIs.

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

### C. Table Naming Conventions
All database tables must be named using the plural form of the entity they represent. For example, the table for users is named `users`, not `user`.

### D. Indexing Strategy
**To ensure optimal query performance, every column that is used in a `WHERE` clause, `JOIN` condition, or `ORDER BY` clause must have an index.**

-   **Single-Column Indexes:** Create a standard index for columns used in simple filters.
-   **Composite Indexes:** Create composite (multi-column) indexes for columns that are frequently queried together in the same `WHERE` clause. The order of columns in the index should match the query's selectivity (most selective column first).
-   **Index Naming:** Use the convention `idx_table_name_column_names`.

Before adding a new query to a repository, verify that all columns in the filter and sort clauses are properly indexed in the database migrations.

## 7. Code Style and Quality Enforcement

This project enforces a strict set of code style and quality rules to ensure consistency, readability, and maintainability. All code is automatically checked and formatted using pre-commit hooks. You **must** ensure your code passes these checks before submitting.

### A. How to Use
1.  **Install the hooks:** This command sets up the hooks to run automatically before each commit.
    ```bash
    poetry run pre-commit install
    ```

2.  **Run checks manually (Recommended):** The CI pipeline runs checks on **all files**, while a local commit only checks the files you've changed. This can cause the CI to fail even if your local commit succeeds. To avoid this, run the checks on all files locally before pushing:
    ```bash
    poetry run pre-commit run --all-files
    ```

    **CRITICAL:** You MUST run `poetry run pre-commit run -a` before finalizing any task to ensure all checks pass.

### B. Key Tools and Standards

The pre-commit pipeline enforces the following standards:

-   **Formatting (Black):** All code is automatically formatted by the [Black](https://github.com/psf/black) code formatter.
-   **Import Sorting (isort):** All imports are automatically sorted and grouped by [isort](https://pycqa.github.io/isort/), ensuring a consistent and readable module structure.
-   **Linting (Flake8):** We use [Flake8](https://flake8.pycqa.org/en/latest/) for linting, enhanced with several plugins to enforce a higher standard of code quality:
    -   `flake8-bugbear`: Finds likely bugs and design problems.
    -   `flake8-comprehensions`: Helps write better and more idiomatic comprehensions.
    -   `flake8-todos`: Ensures that temporary code markers like `TODO` are addressed.
    -   The configuration also explicitly enables `E266` to enforce the **No Inline Comments** rule.
-   **Security (Bandit):** The [Bandit](https://github.com/PyCQA/bandit) tool is used to find common security issues in Python code.
-   **Static Typing (MyPy):** All code must pass strict static type analysis using [MyPy](http://mypy-lang.org/). Our configuration enforces:
    -   **Full Annotation Coverage:** All function definitions must have type annotations (`disallow_untyped_defs`).
    -   **Explicit Optionals:** Values that can be `None` must be explicitly typed with `Optional` (`no_implicit_optional`).
    -   **No `Any` Returns:** Functions are not allowed to implicitly return the `Any` type (`warn_return_any`).
-   **Docstring Standards (Interrogate, pydocstyle, darglint):** We enforce comprehensive and consistent docstrings.
    -   **Coverage:** At least 95% of the codebase must be documented (`interrogate`).
    -   **Style:** All docstrings must follow the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings) (`pydocstyle`).
    -   **Correctness:** Docstrings must be synchronized with function signatures (`darglint`).
-   **Test Coverage:** All contributions must maintain or increase the project's test coverage. The test suite will fail if the coverage drops below the threshold defined in `pyproject.toml`.

### C. Guiding Principles

In addition to the automated checks, we follow these principles:

-   **Zero-Warning Policy:** Warnings are treated as errors. Code that produces warnings during linting, static analysis, or testing is considered incomplete. All warnings must be resolved before a contribution is considered finished.
-   **Self-Documenting Code:** We prioritize clear, descriptive variable and method names over inline comments. Use docstrings for public classes and methods to explain the *why*, not the *what*. Avoid `#` comments unless absolutely necessary for complex logic.
-   **English Language:** All code, docstrings, and documentation must be in **English**. The only exception is text that is user-facing or part of an AI prompt, which should be in **Portuguese (pt-br)**.
-   **Structured Logging:** Do not use `print()` in the application code. Always use the `LoggingProvider` to ensure all output is structured and controllable.

Thank you for your contribution!

## 8. Import and Packaging Philosophy

This project uses a specific package structure where each component in the `source` directory (e.g., `cli`, `services`) is treated as a distinct top-level package. This has important implications for imports and testing.

### A. The "No `source` Prefix" Rule

**All internal imports must be absolute from the component's root.** The `source` directory is **not** a package and must never be used as a prefix.

-   **Correct:** `from public_detective.commands import analyze`
-   **Incorrect:** `from source.public_detective.commands import analyze`

This structure is defined in `pyproject.toml`. If you encounter import-related errors with tooling, do not add the `source.` prefix. The solution will likely involve adjusting the tool's configuration.

### B. Mocking and Patching in Tests

This rule is critical for tests. The path provided to a patch decorator must exactly match the import path used by the module under test.

-   **Code:** `from cli.commands import DatabaseManager`
-   **Test Patch:** `@patch("cli.commands.DatabaseManager")`

Using an incorrect path (e.g., with a `source.` prefix) will cause mocks to fail silently and tests to hit real resources.

## 9. Exception Handling and Linter Configuration

This project follows a specific philosophy for handling exceptions to ensure robustness and clarity, which also impacts our linter configuration.

### A. Exception Handling Philosophy

1.  **Custom Service Exceptions:** The Service layer (`source/services/`) is the core of the business logic. When a method in a service encounters an error (e.g., a database error, an API failure, or unexpected data), it **must** catch the generic exception and re-raise it as a specific, custom exception from the `source/exceptions/` package (e.g., `AnalysisError`). This encapsulates the implementation detail of the error and provides a clear, domain-specific error to the calling layer.

2.  **Presentation Layer Handles Custom Exceptions:** The presentation layers (e.g., the `cli` or the `worker`) are responsible for calling the services. They should **never** handle generic `Exception` types. Instead, they must catch the specific custom exceptions raised by the service (e.g., `except AnalysisError as e:`).

3.  **User-Facing Feedback:** After catching a custom exception, the presentation layer is responsible for providing appropriate user feedback. For the CLI, this means printing a user-friendly error message and exiting with a non-zero status code, typically by raising `click.Abort()`. For the worker, this means logging the error and NACK-ing the Pub/Sub message so it can be retried or sent to a dead-letter queue.

This pattern creates a clean separation of concerns: the service layer signals *what* went wrong in business terms, and the presentation layer decides *how* to report that failure to the user or the infrastructure.

### B. Darglint Configuration (`DAR401`/`DAR402`)

The docstring linter `darglint` has a known issue where it cannot correctly parse the common pattern used in `click` applications: catching a custom exception and then raising `click.Abort()`. This leads to a conflicting pair of errors: `DAR401` (Missing exception) and `DAR402` (Excess exception).

After extensive testing, it was confirmed that this is a limitation of the linter when faced with this specific, idiomatic code pattern. Refactoring the code to satisfy the linter would result in a less clear, non-standard implementation.

Therefore, the project has made the pragmatic decision to **globally disable these two specific darglint rules** in the `.flake8` configuration file.

**Trade-off:** By disabling these rules, we lose the automated check that ensures `Raises` sections in docstrings are perfectly synchronized with the code. This means all developers and agents **must be extra diligent** to manually update the `Raises` section of a function's docstring whenever they add or remove a `raise` statement.
