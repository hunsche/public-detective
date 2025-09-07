# Proposal: Structured `risk_score_rationale`

This document proposes an enhancement to the `procurement_analyses` table by changing the `risk_score_rationale` column from a free-text field to a structured `JSONB` object.

## 1. Current Problem

The `risk_score_rationale` field is currently a `TEXT` column containing a human-readable explanation for the assigned `risk_score`. While informative, its unstructured nature presents several limitations:

-   **Difficult to Audit:** It's not programmatically possible to verify how the final risk score was calculated based on the identified red flags.
-   **Limited Querying:** We cannot run analytical queries to gain insights into which types of irregularities contribute most significantly to risk scores.
-   **Inconsistent Format:** The format and style of the text can vary between different AI model versions or prompt adjustments.

## 2. Proposed Solution

We propose changing the `risk_score_rationale` column to `JSONB` and enforcing a structured format that details the risk calculation. This turns the rationale from a simple explanation into a valuable, queryable data asset.

### 2.1. Proposed JSON Structure

The new structure will break down the score into its constituent parts:

```json
{
  "final_score": 7,
  "base_score": 1,
  "contributing_factors": [
    {
      "category": "DIRECIONAMENTO",
      "impact": "+3",
      "justification": "A especificação de marca ('MARCA MAXXPRINT') sem justificativa técnica é uma irregularidade grave que compromete a isonomia e direciona a contratação."
    },
    {
      "category": "RESTRICAO_COMPETITIVIDADE",
      "impact": "+2",
      "justification": "A pesquisa de preços com apenas duas cotações para um item viola a boa prática e reduz a certeza de se obter a proposta mais vantajosa."
    },
    {
      "category": "SOBREPRECO",
      "impact": "+1",
      "justification": "A grande disparidade de preços entre as propostas, combinada com as outras falhas, sugere que o valor final pode não ser competitivo ou condizente com o de mercado."
    }
  ]
}
```

-   **`final_score`**: The final calculated risk score, matching the `risk_score` column.
-   **`base_score`**: A default starting score for any analysis (e.g., 1).
-   **`contributing_factors`**: An array of objects, where each object links a `red_flag` to its impact on the score.
    -   **`category`**: The category of the red flag.
    -   **`impact`**: The numerical impact (+N) this factor had on the score.
    -   **`justification`**: A concise explanation for the impact.

## 3. Implementation Plan

1.  **Database Migration:**
    -   Create an Alembic migration to change the column type from `TEXT` to `JSONB`.
    -   Ensure the `downgrade` function safely reverts the column to `TEXT`.

2.  **AI Prompt Update:**
    -   Modify the AI prompt in `AiProvider` to instruct the model to return the `risk_score_rationale` in the new, structured JSON format.

3.  **Pydantic Model Update:**
    -   Update the Pydantic model in `source/models/analyses.py` to validate the new JSON structure, using nested models for type safety.

4.  **Application Code Adjustment:**
    -   Refactor any code that reads `risk_score_rationale` as a string to work with the new object structure.

5.  **Test Updates:**
    -   Update unit and E2E tests to assert the correctness of the new JSON structure and its values.

## 4. Sugestão de Novo Prompt para a IA (em Português)

A seção do prompt que define o formato de saída para `risk_score_rationale` seria atualizada para algo como:

> ...
>
> **risk_score_rationale**: Um objeto JSON detalhando o cálculo da pontuação de risco. A pontuação final deve ser a soma da pontuação base com o impacto de cada fator contribuinte. A estrutura DEVE ser a seguinte:
>
> ```json
> {
>   "final_score": <int>,
>   "base_score": 1,
>   "contributing_factors": [
>     {
>       "category": "<CATEGORIA_DA_RED_FLAG>",
>       "impact": "<+int>",
>       "justification": "<Explicação concisa do impacto deste fator na pontuação.>"
>     }
>   ]
> }
> ```
>
> Exemplo: Se você identificar um direcionamento (impacto +3) e uma restrição de competitividade (impacto +2), a `final_score` seria 6 (1 + 3 + 2).

## 5. Benefits

-   **Full Auditability:** Creates a clear, verifiable trail for how the risk score is calculated.
-   **Advanced Data Analysis:** Enables powerful SQL queries to analyze risk factors across all procurements.
-   **Consistency:** Enforces a standard, machine-readable format for all risk analyses.
-   **Scalability:** Simplifies the development of automated dashboards, reports, and alerting systems based on specific high-impact irregularities.
