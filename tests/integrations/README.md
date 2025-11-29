# Integration Tests

## Overview

Integration tests are designed to verify the interaction and communication between different components of the application. Unlike unit tests, which test components in isolation, integration tests ensure that they work together correctly as a group.

The primary goal is to test the "glue" that holds different parts of the system together. For example, these tests confirm that a service can correctly call a repository, which in turn successfully executes a query against a real database.

## Test Architecture

Integration tests validate the interactions _within_ the application, using a mix of real services (in Docker) and mocks for external APIs to ensure stability and focus.

### Local (Emulated) Services

To test the integration with real technologies, the following services are run as local Docker containers:

1.  **PostgreSQL:** The tests connect to a real PostgreSQL database instance. Each test run is performed within a dedicated, temporary schema to ensure complete data isolation.
2.  **Google Cloud Pub/Sub Emulator:** Tests that involve messaging use the official Pub/Sub emulator to verify that messages are published and consumed correctly.
3.  **GCS (MinIO) Emulator:** Tests involving file storage interact with a MinIO server, which emulates the GCS API.

### Mocked External APIs

To ensure tests are fast, deterministic, and independent of external factors, all third-party HTTP APIs are mocked:

1.  **PNCP API:** Calls to the PNCP to fetch procurement data are intercepted and return predefined, static data from fixture files.
2.  **Google Gemini API:** Calls to the AI model are mocked to return predictable analysis results without incurring costs or relying on network connectivity.

This hybrid approach ensures we are testing our internal integrations thoroughly while keeping the tests stable and focused.

## Prerequisites

Before running the integration tests, you must have the local services running.

1.  **Start Docker Services:**
    ```bash
    docker compose up -d
    ```

## How to Run

With the Docker services running, you can execute the entire integration test suite with the following command:

```bash
poetry run pytest tests/integrations/
```
