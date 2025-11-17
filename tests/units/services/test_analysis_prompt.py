"""This module contains tests for the analysis prompt generation."""

import json
import textwrap
from datetime import datetime
from unittest.mock import MagicMock

from public_detective.models.procurements import Procurement
from public_detective.services.analysis import AnalysisService


def test_build_analysis_prompt_contains_new_instructions() -> None:
    """Tests if the generated prompt matches the calibrated template."""
    mock_procurement_repo = MagicMock()
    mock_analysis_repo = MagicMock()
    mock_source_document_repo = MagicMock()
    mock_file_record_repo = MagicMock()
    mock_status_history_repo = MagicMock()
    mock_budget_ledger_repo = MagicMock()
    mock_ai_provider = MagicMock()
    mock_gcs_provider = MagicMock()

    service = AnalysisService(
        procurement_repo=mock_procurement_repo,
        analysis_repo=mock_analysis_repo,
        source_document_repo=mock_source_document_repo,
        file_record_repo=mock_file_record_repo,
        status_history_repo=mock_status_history_repo,
        budget_ledger_repo=mock_budget_ledger_repo,
        ai_provider=mock_ai_provider,
        gcs_provider=mock_gcs_provider,
    )

    procurement_data = {
        "processo": "123/2023",
        "objetoCompra": "Test Procurement",
        "amparoLegal": {"codigo": 1, "nome": "Lei 14.133/2021", "descricao": "Nova Lei de Licitações"},
        "srp": False,
        "orgaoEntidade": {
            "cnpj": "00000000000191",
            "razaoSocial": "Test Entity",
            "poderId": "E",
            "esferaId": "M",
        },
        "anoCompra": 2023,
        "sequencialCompra": 1,
        "dataPublicacaoPncp": datetime(2023, 5, 1, 15, 30).isoformat(),
        "dataAtualizacao": datetime(2023, 5, 2, 10, 45).isoformat(),
        "numeroCompra": "001/2023",
        "unidadeOrgao": {
            "ufNome": "Test State",
            "codigoUnidade": "123",
            "nomeUnidade": "Test Unit",
            "ufSigla": "TS",
            "municipioNome": "Test City",
            "codigoIbge": "1234567",
        },
        "modalidadeId": 1,
        "numeroControlePNCP": "12345678901234567890-1-0001/2023",
        "dataAtualizacaoGlobal": datetime(2023, 5, 3, 9, 15).isoformat(),
        "modoDisputaId": 1,
        "situacaoCompraId": 1,
        "usuarioNome": "Test User",
        "valorTotalEstimado": 1000.0,
        "dataAberturaProposta": datetime(2023, 5, 10, 9, 0).isoformat(),
        "dataEncerramentoProposta": datetime(2023, 5, 20, 17, 0).isoformat(),
    }
    procurement = Procurement.model_validate(procurement_data)

    prompt = service._build_analysis_prompt(procurement, [])

    expected_summary = json.dumps(
        {
            "Objeto": "Test Procurement",
            "Modalidade": 1,
            "Órgão": "Test Entity",
            "Unidade": "Test Unit",
            "Valor Estimado": "R$ 1.000,00",
            "Abertura das Propostas": "10/05/2023 09:00",
            "Encerramento das Propostas": "20/05/2023 17:00",
        },
        indent=2,
        ensure_ascii=False,
    )

    expected_prompt = textwrap.dedent(
        f"""
        Você é um auditor sênior especializado em licitações públicas no Brasil.
        Sua tarefa é analisar os documentos em anexo para identificar possíveis
        irregularidades no processo de contratação.

        Primeiro, revise os metadados da licitação em formato JSON para obter o
        contexto geral. Em seguida, use a lista de documentos e arquivos para
        entender a origem de cada anexo.

        --- SUMÁRIO DA LICITAÇÃO ---
        {expected_summary}
        --- FIM DO SUMÁRIO ---

        --- CONTEXTO DOS DOCUMENTOS ANEXADOS ---

        --- FIM DO CONTEXTO ---

        Com base em todas as informações disponíveis, analise a licitação em
        busca de irregularidades nas seguintes categorias. Para cada achado,
        extraia a citação exata de um dos documentos que embase sua análise e
        preencha um objeto `red_flag` com os campos definidos no esquema.

        **Categorias de Irregularidades:**
        1. **Direcionamento (DIRECIONAMENTO):** Cláusulas que favorecem um fornecedor específico, como exigência de marca sem justificativa técnica, qualificações irrelevantes ou prazos inexequíveis.
        2. **Restrição de Competitividade (RESTRICAO_COMPETITIVIDADE):** Requisitos que limitam a participação, como amostras excessivas ou critérios de habilitação desproporcionais.
        3. **Sobrepreço (SOBREPRECO):** Preços orçados ou contratados significativamente acima da média de mercado. Ao analisar, considere o momento da cotação, a quantidade e a logística. Para esta categoria, você **deve** buscar ativamente preços de referência em fontes confiáveis (Painel de Preços, SINAPI, atas de pregões, sites de e-commerce etc.) usando as ferramentas de pesquisa disponíveis (por exemplo, Google Search). Identifique o preço unitário contratado (`contracted_unit_price`), encontre um preço de referência (`reference_price` e `price_unit`), calcule mentalmente a diferença percentual (`price_difference_percentage = ((contracted_unit_price - reference_price) / reference_price) * 100`) e classifique a severidade conforme abaixo. Cada fonte consultada deve ser registrada na lista `sources`.
        4. **Superfaturamento (SUPERFATURAMENTO):** Dano efetivo ao erário, comprovado por pagamento de serviço não executado, medições falsas ou aditivos que desequilibram o valor inicial. Só utilize esta categoria se houver evidência clara de dano consumado. Se houver comparação de preços, siga as mesmas instruções de sobrepreço para compor as fontes.
        5. **Fraude (FRAUDE):** Indícios de conluio entre licitantes, documentos falsificados ou outras práticas fraudulentas.
        6. **Documentação Irregular (DOCUMENTACAO_IRREGULAR):** Falhas formais graves, como ausência de justificativa de preço, parecer jurídico ou publicação obrigatória.
        7. **Outros (OUTROS):** Irregularidades que não se encaixam nas categorias anteriores.

        **Estrutura do `red_flag`:**
        - `category`: uma das categorias acima.
        - `severity`: `LEVE`, `MODERADA` ou `GRAVE` (veja critérios abaixo).
        - `description`: descrição objetiva (em pt-br) da irregularidade.
        - `evidence_quote`: citação literal (em pt-br) de um documento da licitação que comprova a irregularidade.
        - `auditor_reasoning`: justificativa técnica (em pt-br) explicando por que a evidência representa um risco.
        - `sources` (opcional): lista de fontes externas utilizadas para justificar o red flag. Preencha apenas para categorias que exijam evidências adicionais (sobrepreço e superfaturamento). Cada item deve conter:
        - `name`: nome ou título da fonte.
        - `url`: URL pública da fonte (quando houver).
        - `reference_price`: preço de referência por unidade (quando disponível).
        - `price_unit`: unidade do valor (ex.: “unidade”, “metro”).
        - `reference_date`: data em que o preço foi válido ou coletado.
        - `evidence`: trecho literal (em pt-br) da fonte que apoia a comparação.
        - `rationale`: explicação de como a fonte foi utilizada; inclua o cálculo mental do preço contratado versus o de referência e a diferença percentual.

        **Classificação de Severidade (calibrada):**
        - **Leve:** falhas formais, ou sobrepreço com diferença < 20 % em itens de baixo valor.
        - **Moderada:** restrição de competitividade, sobrepreço com diferença entre 20 % e 50 %, ou ausência parcial de pesquisa de preços.
        - **Grave:** direcionamento claro, ausência total de pesquisa de preços, sobrepreço com diferença > 50 %, ou qualquer indício de fraude ou dano consumado.

        **Critérios para a Nota de Risco (0 a 10 – calibrada):**
        A nota deve ponderar a quantidade, a severidade das irregularidades e o impacto financeiro. Utilize os seguintes exemplos como referência:
        - **0–1 (Risco Mínimo):** apenas falhas burocráticas menores (ex.: atestado técnico vencido poucos dias).
        - **2–3 (Risco Baixo):** irregularidades leves sem indício de má-fé (ex.: sobrepreço de 15 % em item de baixo valor).
        - **4–5 (Risco Moderado):** evidências de restrição de competitividade ou sobrepreço relevante (ex.: exigência de certificação específica; sobrepreço de 40 % no item principal).
        - **6–7 (Risco Alto):** direcionamento claro, múltiplas irregularidades ou sobrepreço elevado (ex.: especificação de marca sem justificativa; pesquisa de preços com apenas uma cotação).
        - **8–9 (Risco Crítico):** forte suspeita de fraude, conluio ou dano ao erário (ex.: concorrentes com mesmo sócio; preços 100 % acima do mercado).
        - **10 (Risco Máximo):** prova documental de fraude ou superfaturamento, ou conjunto de irregularidades graves que demonstram má-fé e dano iminente ou consumado.

        Sua resposta deve ser um objeto JSON que siga estritamente o esquema fornecido, incluindo os campos `procurement_summary`, `analysis_summary`, `risk_score_rationale`, e a lista de `red_flags` (cada um com seus `sources` quando houver). Não retorne nenhum campo extra.

        Forneça um resumo conciso (em pt-br, máximo 3 sentenças) do escopo da licitação no campo `procurement_summary`.

        Forneça um resumo conciso (em pt-br, máximo 3 sentenças) da análise geral no campo `analysis_summary`.

        **Palavras-chave para SEO:**
        Por fim, gere uma lista de 5 a 10 palavras-chave estratégicas (em pt-br) que um usuário interessado nesta licitação digitaria no Google. Pense em termos relacionados ao objeto da licitação, ao órgão público, à cidade/estado e a sinônimos que maximizem a encontrabilidade da análise.
    """  # noqa: E501
    ).strip()

    normalized_prompt = textwrap.dedent(prompt).strip()

    assert normalized_prompt == expected_prompt
