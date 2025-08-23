# Public Detective

An AI-powered tool for enhancing transparency and accountability in Brazilian public procurement.

## About The Project

Public procurement in Brazil is a multi-billion dollar enterprise, but its complexity can make it opaque and vulnerable to inefficiencies, fraud, and corruption. **Public Detective** is an academic project designed to address this challenge by leveraging modern technology for social good.

This tool automatically fetches public tender data from Brazil's National Public Procurement Portal (PNCP) and uses Artificial Intelligence and Natural Language Processing (NLP) to analyze the full text of bid documents (PDFs). The primary goal is to identify and flag potential irregularities, making it easier for journalists, civil society organizations, and citizens to scrutinize public spending.

This is a research and extension project developed at the **Pontifical Catholic University of Paraná (PUCPR)**, and it benefits from the valuable feedback and expertise of the NGO **Transparência Brasil**.

## Key Features

- **Automated Data Retrieval:** Fetches procurement data directly from the official PNCP APIs.
- **In-depth Document Analysis:** Goes beyond metadata to analyze the full text of bid documents.
- **AI-Powered Irregularity Detection:** Uses a Generative AI model to flag potential red flags, such as:
  - Technical specifications that appear tailored to a single supplier.
  - Unusually short or restrictive deadlines.
  - Overly demanding qualification requirements designed to limit competition.
  - Other textual patterns that may indicate bid rigging.
- **Simplified Risk Reporting:** Translates complex findings into a simple, easy-to-understand risk score or "traffic light" system to guide human analysis.

## How It Works

The system follows a clear pipeline:

1.  **Fetch:** Queries the public PNCP API (`/api/consulta`) to find recent or open bids.
2.  **Retrieve:** Identifies the unique identifiers for a bid (`cnpj`, `ano`, `sequencial`) and uses the appropriate PNCP API (`/api/pncp`) to retrieve the list of associated documents.
3.  **Download:** Downloads the primary bid document (PDF) using the endpoint provided by the API.
4.  **Analyze:** Submits the PDF content to a Generative AI model with a specialized prompt engineered to detect dozens of potential red flags for irregularities.
5.  **Report:** Processes the AI's analysis, assigns a risk score, and presents a summary of the findings for review.

## Tech Stack

- **Language:** Python 3.13+
- **AI / NLP:** Google Gemini API
- **File Conversion:** LibreOffice

## Getting Started

To get a local copy up and running, follow these simple steps.

### Prerequisites

- Python 3.13+
- Poetry
- Docker
- LibreOffice

### Installation

1.  Clone the repo
    ```sh
    git clone https://github.com/hunsche/public-detective.git
    ```
2.  Navigate to the project directory
    ```sh
    cd public-detective
    ```
3.  Install Python packages
    ```sh
    poetry install
    ```
4.  Set up your environment variables
    ```sh
    # Create a .env file and add your Gemini API key
    echo "GCP_GEMINI_API_KEY='YOUR_API_KEY'" > .env
    ```

### Running Migrations

Use Alembic to manage database migrations.

```bash
poetry run alembic upgrade head
```

## Usage

[Add examples here of how to run your script]
```python
# Example of how to run the main analysis script
python source/cli --start-date 2025-01-01 --end-date 2025-01-02
````

## Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**. Please refer to the `CONTRIBUTING.md` file for details.

## License

Distributed under the MIT License. See `LICENSE` for more information.

## Contact

Matheus Hunsche - [LinkedIn](https://www.linkedin.com/in/matheus-aoki-hunsche-085446107/) - mthunsche@gmail.com

Project Link: [https://detetive-publico.com](https://detetive-publico.com)

## Acknowledgments

  - **Pontifícia Universidade Católica do Paraná (PUCPR)** for the academic support.
  - **Transparência Brasil** for their invaluable feedback and domain expertise.
  - The **Portal Nacional de Contratações Públicas (PNCP)** for providing the open data essential for this project.
