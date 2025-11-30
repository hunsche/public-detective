# End-to-End (E2E) Tests

## Overview

End-to-End (E2E) tests are designed to simulate the application's complete workflow in an environment that closely mirrors production. The primary goal is to validate the integration and interaction between all system components, ensuring that the application functions as expected from start to finish.

We have two distinct categories of E2E tests in this project:

1.  **Workflow E2E (`tests/e2e/workflows/`)**: Tests the backend data processing pipeline (CLI -> Worker -> DB).
2.  **Web E2E (`tests/e2e/web/`)**: Tests the frontend user interface (Browser -> Web App -> DB).

---

## 1. Workflow E2E Tests (`tests/e2e/workflows/`)

These tests execute a real-world use case: they start from the command-line interface (`CLI`), trigger procurement analyses, process the data through the `worker`, and finally, verify that the results have been correctly persisted in the database.

### Architecture

To balance realism, cost, and isolation, these tests employ a hybrid architecture:

#### Real Services Used

To ensure that the core business logic is correct and our integrations with external APIs are robust, the following services are consumed from their actual versions on GCP and PNCP:

1.  **PNCP (National Public Procurement Portal):** Fetches real procurement data.
2.  **Google Vertex AI (Gemini API):** Processes document analyses using the actual Gemini API.
3.  **Google Cloud Storage (GCS):** Stores original documents and analysis results in a real GCS bucket.

#### Local (Emulated) Services

1.  **PostgreSQL:** Runs in a local Docker container on a temporary schema.
2.  **Google Cloud Pub/Sub Emulator:** Handles messaging between CLI and Worker locally.

### Prerequisites & Running

These tests require **mandatory** environment variables (`GCP_SERVICE_ACCOUNT_CREDENTIALS`, `GCP_GCS_BUCKET_PROCUREMENTS`, `GCP_PROJECT`) and access to real GCP resources.

**Run command:**

```bash
poetry run pytest -s -n auto tests/e2e/workflows/
```

---

## 2. Web E2E Tests (`tests/e2e/web/`)

These tests validate the user interface and user experience using **Playwright**. They simulate a real user interacting with the web application in a browser.

### Philosophy & Architecture

Unlike the Workflow E2E tests, the Web E2E tests are designed to be **fast, deterministic, and always runnable**.

1.  **Always Run:** These tests are part of the default test suite and should run on every CI pipeline and local development cycle.
2.  **No Real External Services:** They do **NOT** access the real PNCP, Google Cloud, or Vertex AI. They are completely isolated from external network dependencies (except for the local browser).
3.  **Seeded Database:** Instead of fetching fresh data, these tests rely on a **pre-populated database seed**. This ensures that the test data is consistent and predictable. The application connects to the local PostgreSQL container, but uses existing data to render the pages.

### How to Run

Since these tests do not require external credentials, you can run them simply with:

```bash
poetry run pytest tests/e2e/web/
```

Or run the entire suite (which includes Unit, Integration, and Web E2E, but excludes Workflow E2E):

```bash
poetry run pytest
```
