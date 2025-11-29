# Unit Tests

## Overview

Unit tests are designed to test the smallest pieces of the application in complete isolation. The primary goal is to verify that individual functions, methods, and classes behave as expected without any external dependencies.

These tests focus on the internal logic of a component. They use mocks and stubs to simulate interactions with other parts of the system, such as the database, external APIs, or the file system.

## Test Architecture

Unit tests are entirely self-contained and do not require any external services or infrastructure.

- **No Docker Required:** You do not need to run `docker compose up`.
- **No Network Access:** Tests do not make calls to live APIs (like PNCP or Google Cloud). All external interactions are replaced with mock objects.
- **In-Memory Behavior:** Dependencies are mocked to return predefined data, ensuring that tests are fast, predictable, and can run in any environment, including CI/CD pipelines, without any setup.

## How to Run

To run all unit tests, use the following command:

```bash
poetry run pytest tests/units/
```
