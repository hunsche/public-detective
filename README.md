[![CI](https://github.com/hunsche/public-detective/actions/workflows/ci.yml/badge.svg)](https://github.com/hunsche/public-detective/actions/workflows/ci.yml)
![Coverage](./.github/badges/coverage.svg)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# Public Detective

An AI-powered tool for enhancing transparency and accountability in Brazilian public procurement.

## About The Project

Public procurement in Brazil is a multi-billion dollar enterprise, but its complexity can make it opaque and vulnerable to inefficiencies, fraud, and corruption. **Public Detective** is an academic project designed to address this challenge by leveraging modern technology for social good.

This tool automatically fetches public tender data from Brazil's National Public Procurement Portal (PNCP) and uses Artificial Intelligence and Natural Language Processing (NLP) to analyze the full text of bid documents. The primary goal is to identify and flag potential irregularities, making it easier for journalists, civil society organizations, and citizens to scrutinize public spending.

This is a research and extension project developed at the **Pontifical Catholic University of Paraná (PUCPR)**, and it benefits from the valuable feedback and expertise of the NGO **Transparência Brasil**.

## Key Features

- **Automated Data Retrieval:** Fetches procurement data directly from the official PNCP APIs.
- **AI-Powered Irregularity Detection:** Uses a Generative AI model to flag potential red flags and provide a detailed risk score with a rationale.
- **Traceability:** Archives both original and processed documents in Google Cloud Storage for every analysis.
- **Idempotency:** Avoids re-analyzing unchanged documents by checking a content hash.

## How It Works

The analysis process is divided into two main, decoupled stages: **Pre-analysis** and **Analysis**.

### 1. Pre-analysis (Zero Cost)

This is a lightweight, zero-cost first pass that prepares procurements for the full analysis. It is designed to be run periodically to discover new and updated public tenders.

- **Fetch & Version:** It fetches new and updated procurement data from the PNCP. For each new version of a procurement, it calculates a unique hash of its contents (metadata and all associated documents) to ensure idempotency.
- **Cost Estimation:** Before committing to a full analysis, it calculates the number of tokens required and estimates the final cost based on the current price of the AI model.
- **Persist:** It saves a new, versioned record for the procurement in the database, along with a corresponding `procurement_analysis` entry marked with a `PENDING_ANALYSIS` status and the estimated cost.

### 2. Analysis (AI-Powered)

This is the second stage, where the deep, AI-powered analysis occurs. This step has a cost associated with it and is triggered on-demand for a specific analysis that is pending.

- **Trigger:** An analysis is initiated by its unique ID, which sends a message to a Google Cloud Pub/Sub topic.
- **Process:** A background worker, subscribed to the topic, picks up the message. It retrieves the specific procurement version and all associated files.
- **Analyze & Report:** The worker submits the data to the Generative AI model. It then saves the complete analysis, including the risk score, rationale, and any findings, to the database, updating the status to `ANALYSIS_SUCCESSFUL` or `ANALYSIS_FAILED`.

## Tech Stack

- **Language:** Python 3.12+
- **AI / NLP:** Google Gemini API
- **Database:** PostgreSQL with Psycopg2 (raw SQL and connection pooling)
- **Infrastructure:** Docker, GCS, Pub/Sub

## Getting Started

To get a local copy up and running, follow these simple steps.

### Prerequisites

- **Python 3.12+**
- **Poetry** for dependency management
- **Docker** and **Docker Compose** for running services

### Installation & Setup

1.  **Clone the repo:**
    ```sh
    git clone https://github.com/hunsche/public-detective.git
    cd public-detective
    ```
2.  **Install dependencies:**
    ```sh
    poetry install
    ```
3.  **Set up environment variables:**
    Create a `.env` file and add your Gemini API key.
    ```sh
    echo "GCP_GEMINI_API_KEY='YOUR_API_KEY'" > .env
    ```
4.  **Start services:**
    ```bash
    docker compose up -d
    ```
5.  **Run database migrations:**
    ```bash
    poetry run alembic upgrade head
    ```

## Usage

The application is controlled via a Command-Line Interface (CLI) with two main commands.

### `pre-analyze`
This command runs the first stage of the pipeline, fetching new procurement data and preparing it for analysis.

```bash
# Run pre-analysis for a specific date range
poetry run python -m source.cli pre-analyze --start-date 2025-01-01 --end-date 2025-01-05

# Run for a single day (default)
poetry run python -m source.cli pre-analyze
```

### `analyze`
This command triggers the full, AI-powered analysis for a single procurement that has already been pre-analyzed.

```bash
# Trigger the analysis for a specific ID
poetry run python -m source.cli analyze --analysis-id 123
```

## Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**. Please refer to the `CONTRIBUTING.md` file for details.

## License

Distributed under the Creative Commons Attribution-NonCommercial 4.0 International License. See `LICENSE` for more information.

## Contact

Matheus Hunsche - [LinkedIn](https://www.linkedin.com/in/matheus-aoki-hunsche-085446107/) - mthunsche@gmail.com

Project Link: [https://detetive-publico.com](https://detetive-publico.com)
