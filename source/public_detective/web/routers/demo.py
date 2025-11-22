from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime


# Simple mock object classes
class MockEntity:
    def __init__(self, name):
        self.name = name


class MockModality:
    def __init__(self, name):
        self.name = name


class MockProcurement:
    def __init__(self, control_number, description, value, date, entity, modality):
        self.pncp_control_number = control_number
        self.object_description = description
        self.total_estimated_value = value
        self.pncp_publication_date = date
        self.government_entity = MockEntity(entity)
        self.modality = MockModality(modality)


class MockRedFlag:
    def __init__(self, category, description, evidence, severity, recommendation):
        self.category = category
        self.description = description
        self.evidence = evidence
        self.severity = severity
        self.recommendation = recommendation


class MockAnalysis:
    def __init__(self):
        self.risk_score = 75
        self.summary = "Análise identificou irregularidades significativas no processo licitatório, incluindo prazo excessivamente curto para apresentação de propostas e especificações técnicas que favorecem fornecedor específico."
        self.red_flags = [
            MockRedFlag(
                "Prazo Inadequado",
                "Prazo de apenas 3 dias úteis para apresentação de propostas, prejudicando a competitividade",
                "Edital publicado em 15/03/2024 com prazo final em 18/03/2024",
                "high",
                "Prorrogar prazo para mínimo de 8 dias úteis conforme Lei 14.133/2021"
            ),
            MockRedFlag(
                "Especificação Restritiva",
                "Requisitos técnicos excessivamente específicos que limitam competição",
                "Item 4.2 do edital exige marca específica sem justificativa técnica adequada",
                "high",
                "Reformular especificações para permitir equivalência técnica"
            ),
            MockRedFlag(
                "Orçamento Incompatível",
                "Valor estimado 35% acima da média de mercado para itens similares",
                "Pesquisa de preços em apenas 2 fornecedores, insuficiente para média confiável",
                "medium",
                "Realizar nova pesquisa de preços com mínimo de 5 fornecedores"
            )
        ]
        self.recommendations = [
            "Prorrogar prazo do edital para garantir ampla participação",
            "Reformular especificações técnicas eliminando restrições desnecessárias",
            "Realizar nova pesquisa de preços fundamentada",
            "Publicar justificativa técnica detalhada para requisitos específicos"
        ]
        self.legal_compliance = "Processo apresenta não conformidades com artigos 54 e 40 da Lei 14.133/2021 (Nova Lei de Licitações) quanto a prazos mínimos e competitividade. Recomenda-se adequação antes da abertura das propostas."
        self.cost_analysis = "Valor estimado de R$ 450.000,00 está superavaliado em aproximadamente 35% quando comparado com licitações similares dos últimos 6 meses. Preço de referência sugerido: R$ 292.500,00 a R$ 337.500,00."
        self.procedural_compliance = "Procedimento segue parcialmente o rito da Lei 14.133/2021, porém com falhas no quesito publicidade (prazo) e na fase preparatória (pesquisa de preços). Necessária republicação do edital com correções."
        self.contract_analysis = "Minuta contratual prevê cláusulas equilibradas, mas necessita ajustes nas penalidades (muito brandas) e na forma de medição/pagamento (sem critérios objetivos claros)."
        self.created_at = datetime(2024, 3, 16, 14, 30)
        self.input_tokens_used = 15420
        self.output_tokens_used = 3850
        self.total_cost = 0.2847
        self.version_number = 1


router = APIRouter()

# Define base path for templates
BASE_PATH = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))

# Mock procurements
MOCK_PROCUREMENTS = [
    MockProcurement(
        "00038.000001/2024-11",
        "Aquisição de equipamentos de informática para modernização da gestão pública",
        450000.00,
        datetime(2024, 3, 15),
        "Prefeitura Municipal de São Paulo",
        "Pregão Eletrônico"
    ),
    MockProcurement(
        "00123.000045/2024-05",
        "Contratação de serviços de limpeza e conservação para prédios públicos",
        850000.00,
        datetime(2024, 5, 20),
        "Governo do Estado de Minas Gerais",
        "Concorrência Pública"
    ),
    MockProcurement(
        "00067.000032/2024-08",
        "Aquisição de medicamentos e insumos hospitalares",
        1250000.00,
        datetime(2024, 8, 10),
        "Secretaria de Saúde do Rio de Janeiro",
        "Dispensa de Licitação"
    ),
]


@router.get("/demo/search", name="demo_search")
async def demo_search(request: Request):
    """Retorna resultados de busca mockados."""
    return templates.TemplateResponse(
        "partials/search_results.html",
        {
            "request": request,
            "results": MOCK_PROCUREMENTS,
            "query": "demo"
        }
    )


@router.get("/demo/analysis/{control_number}", name="demo_analysis")
async def demo_analysis(control_number: str, request: Request):
    """Retorna análise mockada."""
    # Encontra o procurement correspondente
    procurement = next(
        (p for p in MOCK_PROCUREMENTS if p.pncp_control_number == control_number),
        MOCK_PROCUREMENTS[0]  # Fallback para o primeiro
    )
    
    return templates.TemplateResponse(
        "analysis_detail.html",
        {
            "request": request,
            "title": f"Análise: {procurement.government_entity.name}",
            "analysis": MockAnalysis(),
            "procurement": procurement
        }
    )
