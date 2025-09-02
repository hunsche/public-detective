# Intelligent Analysis with Dynamic Budgeting

This document details the operation of the intelligent analysis job, designed to optimize the use of financial resources (donations) in a transparent and strategic manner.

---

## 1. Main Goal

The intelligent analysis system aims to automate the decision of which procurements to analyze, prioritizing those that the community deems most important (via votes) while ensuring a constant flow of new analyses of recent content. All of this is done while respecting a budget that can be set manually or calculated automatically based on received donations, with a controlled spending pace (daily, weekly, or monthly).

## 2. Key Concepts

- **Total Execution Budget (`--budget`):** The maximum amount that can be spent in a single job execution. It can be set manually or calculated automatically.
- **Budget Period (`--budget-period`):** Defines the spending pace for the automatic budget. Options are `daily`, `weekly`, `monthly`.
- **Period Capital:** The calculation base for the automatic budget. It is the sum of the **current cash balance** and **everything already spent within the current period**. This ensures that new donations are immediately incorporated into the planning.
- **Daily Target:** The "ideal" amount the system should spend per day to consume the "Period Capital" in a balanced way. It is recalculated at each execution to adapt to new donations.
- **Budget for Zero-Vote Items (`--zero-vote-budget-percent`):** A safeguard to prevent the entire budget from being spent on low-priority procurements. It is a percentage of the Total Execution Budget.

## 3. The Decision Flow

The system follows a series of logical steps to determine which procurements to analyze and how much to spend.

```mermaid
graph TD
    A[Start Job Execution] --> B{Budget Mode?};
    B -- Manual (`--budget`) --> C[Use Provided Budget];
    B -- Automatic (`--use-auto-budget`) --> D{Calculate Auto Budget};
    D --> E[1. Get Current Balance];
    E --> F[2. Get Expenses in Period];
    F --> G[3. Calculate Period Capital];
    G --> H[4. Calculate Daily Target];
    H --> I[5. Calculate Cumulative Target for Today];
    I --> J[6. Calculate Budget for Current Run];
    J --> C;

    C --> K[Define Zero-Vote Budget];
    K --> L[Fetch Pending Analyses (Sorted)];
    L --> M{Loop: For each Analysis};
    M --> N[Calculate Estimated Cost];
    N --> O{Total Budget Sufficient?};
    O -- No --> P[End Job];
    O -- Yes --> Q{Is it a zero-vote item?};
    Q -- Yes --> R{Zero-Vote Budget Sufficient?};
    Q -- No --> S[Process Analysis];
    R -- No --> T[Skip to next analysis];
    R -- Yes --> S;
    S --> U[Deduct Cost from Budgets];
    U --> V[Record Expense in Ledger];
    V --> M;
    P --> W[End];
    T --> M;
```

## 4. Command-Line Interface (CLI) Parameters

- `--budget <value>`: (Required, unless `--use-auto-budget` is used) Sets a manual, fixed budget for the execution. Accepts decimal values (e.g., `150.75`).
- `--use-auto-budget`: (Optional) Activates the automatic budget mode. If used, the `--budget` parameter is ignored.
- `--budget-period <daily|weekly|monthly>`: (Required if `--use-auto-budget` is used) Defines the period for the spending pace calculation.
- `--zero-vote-budget-percent <0-100>`: (Optional, Default: 100) The percentage of the execution budget that can be spent on procurements with zero votes.

## 5. Logging and Transparency

To ensure maximum transparency, every important decision made by the system will generate a clear and friendly log message in **Portuguese**.

**Log Examples:**

- **Job Start (Manual Mode):**
  > `INFO: Iniciando job de análise com orçamento manual de R$ 150,75.`
- **Job Start (Automatic Mode):**
  > `INFO: Iniciando job com orçamento automático. Período definido: 'monthly'.`
  > `DEBUG: Saldo atual: R$ 3000,00. Despesas no período: R$ 250,00. Capital total do período: R$ 3250,00.`
  > `DEBUG: Meta diária calculada: R$ 108,33.`
  > `DEBUG: Meta acumulada para o dia 10: R$ 1083,30. Gasto real no período: R$ 250,00.`
  > `INFO: Orçamento calculado para esta execução: R$ 833,30.`
- **Skip Decision (Budget Exceeded):**
  > `INFO: Análise 123 ignorada. Custo estimado (R$ 15,50) excede o orçamento restante (R$ 10,20).`
- **Skip Decision (Zero-Vote Budget Exceeded):**
  > `INFO: Análise 456 (0 votos) ignorada. Custo estimado (R$ 5,00) excede o orçamento restante para itens sem votos (R$ 3,50).`
- **Processing Success:**
  > `INFO: Análise 789 processada com sucesso. Custo: R$ 8,75. Orçamento restante: R$ 1,45.`
