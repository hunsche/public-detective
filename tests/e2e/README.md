# End-to-End (E2E) Tests

## Overview

End-to-End (E2E) tests are designed to simulate the application's complete workflow in an environment that closely mirrors production. The primary goal is to validate the integration and interaction between all system components, ensuring that the application functions as expected from start to finish.

These tests execute a real-world use case: they start from the command-line interface (`CLI`), trigger procurement analyses, process the data through the `worker`, and finally, verify that the results have been correctly persisted in the database.

## Test Architecture

To balance realism, cost, and isolation, the E2E tests employ a hybrid architecture, combining real cloud services with local services running in Docker containers.

### Real Services Used

To ensure that the core business logic is correct and our integrations with external APIs are robust, the following services are consumed from their actual versions on the Google Cloud Platform (GCP) and the National Public Procurement Portal (PNCP):

1.  **PNCP (National Public Procurement Portal):** The tests fetch real procurement data directly from the PNCP. This ensures our code can handle the structure and format of the data it will encounter in production.
2.  **Google Vertex AI (Gemini API):** Document analyses are processed by the actual Gemini API. This validates that our prompts are correct, communication with the AI service is working, and we can correctly interpret the responses.
3.  **Google Cloud Storage (GCS):** Original documents and analysis results are stored in a real GCS bucket. This confirms that our access permissions, upload logic, and file organization are correct.

### Local (Emulated) Services

To ensure the tests are independent, repeatable, and do not interfere with development or production environments, the following services are run locally using Docker Compose:

1.  **PostgreSQL:** The database runs in a local Docker container. The tests operate on a separate, temporary schema, ensuring complete isolation and the ability to start from a clean state with each run.
2.  **Google Cloud Pub/Sub Emulator:** Communication between the `CLI` and the `worker` is handled by an official Pub/Sub emulator. This allows us to test the message publishing and consumption logic quickly and without cost, isolating the test from the production messaging system.

## Prerequisites

To run the E2E tests, the environment must be configured with credentials and resources that allow access to the real GCP services. The following environment variables are **mandatory**:

1.  `GCP_SERVICE_ACCOUNT_CREDENTIALS`:
    *   **Description:** The JSON content of a GCP service account key.
    *   **Minimum Permissions:** The service account must have permissions to read and write to Google Cloud Storage (`Storage Object Admin`) and to invoke the Vertex AI API (`Vertex AI User`).
    *   **How to configure:** Export the content of the JSON file to this environment variable.

2.  `GCP_GCS_BUCKET_PROCUREMENTS`:
    *   **Description:** The name of a real, existing bucket in Google Cloud Storage.
    *   **Purpose:** This bucket will be used by the tests to store files and artifacts generated during the procurement analysis.

3. `GCP_PROJECT`:
    *   **Description:** The GCP project ID where the above resources (service account and bucket) are located.
    *   **Purpose:** This is required for the GCP SDK to know which project to operate in.

## How to Run

With the local services running (`docker compose up -d`) and the environment variables properly configured, you can run the E2E tests with the following command:

```bash
poetry run pytest -s -n auto tests/e2e/
```

*   The `-s` flag is important to disable `pytest`'s output capturing, allowing you to see the application's logs in real-time, which is crucial for debugging and understanding the execution flow.
*   The `-n auto` flag (provided by `pytest-xdist`) runs the tests in parallel, which can significantly speed up the execution time by utilizing multiple CPU cores.
