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

1.  **Fetch:** Queries the public PNCP API to find recent or open bids.
2.  **Retrieve:** Downloads all documents for a bid.
3.  **Archive:** Zips and uploads the original documents to Google Cloud Storage.
4.  **Analyze:** Submits the file contents to a Generative AI model with a specialized prompt.
5.  **Report:** Processes the AI's analysis, including a risk score and rationale, and saves it to a PostgreSQL database.

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

Example of how to run the main analysis script via the CLI:
```bash
poetry run python source/cli --start-date 2025-01-01 --end-date 2025-01-02
```

## Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**. Please refer to the `CONTRIBUTING.md` file for details.

## License

Distributed under the MIT License. See `LICENSE` for more information.

## Contact

Matheus Hunsche - [LinkedIn](https://www.linkedin.com/in/matheus-aoki-hunsche-085446107/) - mthunsche@gmail.com

Project Link: [https://detetive-publico.com](https://detetive-publico.com)
