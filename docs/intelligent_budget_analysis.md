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
- `--max-messages <number>`: (Optional) The maximum number of analysis tasks to trigger in a single run, regardless of the available budget.

## 5. Logging and Transparency

To ensure maximum transparency, every important decision made by the system will generate a clear log message in English.

**Log Examples:**

- **Job Start:**
  > `INFO: Starting ranked analysis job with a budget of 10.00 BRL.`
  > `INFO: Analysis run is limited to a maximum of 1 message(s).`
  > `INFO: Zero-vote budget is 10.00 BRL.`
- **Processing and Budgeting:**
  > `INFO: Found 2 pending analyses.`
  > `INFO: Processing analysis bb5346ea-31c6-450a-b6b2-025196ade101 with estimated cost of 0.01 BRL.`
  > `INFO: Running specific analysis for analysis_id: bb5346ea-31c6-450a-b6b2-025196ade101`
  > `INFO: Analysis bb5346ea-31c6-450a-b6b2-025196ade101 triggered. Remaining budget: 9.99 BRL. Zero-vote budget: 9.99 BRL.`
- **Job End (Max Messages Reached):**
  > `INFO: Reached max_messages limit of 1. Stopping job.`
  > `INFO: Ranked analysis job completed.`
- **Job End (Budget Exceeded):**
  > `INFO: Stopping ranked analysis. Next analysis cost (5.50 BRL) exceeds remaining budget (4.30 BRL).`
- **Job End (Zero-Vote Budget Exceeded):**
  > `INFO: Skipping zero-vote analysis abc-123. Cost (5.50 BRL) exceeds remaining zero-vote budget (4.30 BRL).`
