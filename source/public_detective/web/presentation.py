"""Presentation service for the web interface."""

import json
from typing import Any

from public_detective.models.analyses import Analysis, AnalysisResult
from public_detective.models.procurements import ProcurementModality, ProcurementStatus
from public_detective.providers.database import DatabaseManager
from public_detective.repositories.analyses import AnalysisRepository


class PresentationService:
    """Service for preparing data for presentation in the web interface."""

    def __init__(self) -> None:
        """Initialize the service."""
        self.repo = AnalysisRepository(DatabaseManager.get_engine())

    def get_home_stats(self) -> dict[str, Any]:
        """Get statistics for the home page.

        Returns:
            A dictionary containing home page statistics.
        """
        stats = self.repo.get_home_stats()
        stats["total_savings"] = self._format_currency(stats.get("total_savings"))
        return dict(stats)

    def get_recent_analyses(self, page: int = 1, limit: int = 9) -> dict[str, Any]:
        """Get recent analyses for the list page.

        Args:
            page: The page number.
            limit: The number of items per page.

        Returns:
            A dictionary containing the list of analyses and pagination info.
        """
        results, total_count = self.repo.get_recent_analyses_summary(page, limit)

        total_pages = (total_count + limit - 1) // limit
        return {
            "results": [self._map_to_view(r) for r in results],
            "total": total_count,
            "page": page,
            "pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

    def search_analyses(self, query_str: str, page: int = 1, limit: int = 9) -> dict[str, Any]:
        """Search analyses by query string.

        Args:
            query_str: The search query.
            page: The page number.
            limit: The number of items per page.

        Returns:
            A dictionary containing the search results and pagination info.
        """
        results, total_count = self.repo.search_analyses_summary(query_str, page, limit)

        total_pages = (total_count + limit - 1) // limit
        return {
            "results": [self._map_to_view(r) for r in results],
            "total": total_count,
            "page": page,
            "pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

    def _format_currency(self, value: float | None) -> str:
        if value is None:
            return "N/A"
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def get_analysis_details(self, analysis_id: str) -> dict[str, Any] | None:
        """Get detailed analysis data by ID.

        Args:
            analysis_id: The analysis ID.

        Returns:
            A dictionary containing the analysis details, or None if not found.
        """
        try:
            from uuid import UUID

            uuid_obj = UUID(analysis_id)
        except ValueError:
            return None

        analysis_data = self.repo.get_analysis_details(uuid_obj)
        if not analysis_data:
            return None
        ai_analysis_data = {
            "risk_score": analysis_data.get("risk_score") or 0,
            "risk_score_rationale": analysis_data.get("risk_score_rationale") or "",
            "procurement_summary": analysis_data.get("procurement_summary") or "",
            "analysis_summary": analysis_data.get("analysis_summary") or "",
            "red_flags": (
                analysis_data.get("red_flags")
                if isinstance(analysis_data.get("red_flags"), list)
                else json.loads(analysis_data.get("red_flags") or "[]")
            ),
            "seo_keywords": analysis_data.get("seo_keywords") or [],
        }
        ai_analysis = Analysis.model_validate(ai_analysis_data)

        raw_data = analysis_data.get("raw_data") or {}
        if isinstance(raw_data, str):
            raw_data = json.loads(raw_data)

        unit = raw_data.get("unidadeOrgao", {})
        location = f"{unit.get('municipioNome', '')} - {unit.get('ufSigla', '')}"

        modality_id = analysis_data.get("modality_id")
        try:
            modality_enum = ProcurementModality(modality_id)
            modality_map = {
                ProcurementModality.ELECTRONIC_AUCTION: "Pregão Eletrônico",
                ProcurementModality.COMPETITIVE_DIALOGUE: "Diálogo Competitivo",
                ProcurementModality.CONTEST: "Concurso",
                ProcurementModality.ELECTRONIC_COMPETITION: "Concorrência Eletrônica",
                ProcurementModality.IN_PERSON_COMPETITION: "Concorrência Presencial",
                ProcurementModality.ELECTRONIC_REVERSE_AUCTION: "Pregão Eletrônico",
                ProcurementModality.IN_PERSON_REVERSE_AUCTION: "Pregão Presencial",
                ProcurementModality.BIDDING_WAIVER: "Dispensa de Licitação",
                ProcurementModality.BIDDING_UNENFORCEABILITY: "Inexigibilidade de Licitação",
                ProcurementModality.EXPRESSION_OF_INTEREST: "Manifestação de Interesse",
                ProcurementModality.PRE_QUALIFICATION: "Pré-Qualificação",
                ProcurementModality.ACCREDITATION: "Credenciamento",
                ProcurementModality.IN_PERSON_AUCTION: "Leilão Presencial",
            }
            modality = modality_map.get(modality_enum, modality_enum.name.replace("_", " ").title())
        except (ValueError, TypeError):
            modality = str(modality_id)

        status_id = analysis_data.get("procurement_status_id")
        status_name = raw_data.get("situacaoCompraNome")

        if status_name:
            status = status_name
        else:
            try:
                status_enum = ProcurementStatus(status_id)
                status_map = {
                    ProcurementStatus.PUBLISHED: "Publicada",
                    ProcurementStatus.REVOKED: "Revogada",
                    ProcurementStatus.ANNULLED: "Anulada",
                    ProcurementStatus.SUSPENDED: "Suspensa",
                }
                status = status_map.get(status_enum, status_enum.name.replace("_", " ").title())
            except (ValueError, TypeError):
                status = str(status_id)

        category_map = {
            "SOBREPRECO": "Sobrepreço",
            "RESTRICAO_COMPETITIVIDADE": "Restrição à Competitividade",
            "FRACIONAMENTO_DESPESA": "Fracionamento de Despesa",
            "DIRECIONAMENTO": "Direcionamento",
            "SUPERFATURAMENTO": "Superfaturamento",
            "JOGO_DE_PLANILHA": "Jogo de Planilha",
        }

        red_flags = []
        for flag in ai_analysis.red_flags:
            flag_dict = flag.model_dump(by_alias=True)
            flag_dict["category"] = category_map.get(flag.category, flag.category.replace("_", " ").title())

            if flag.potential_savings:
                flag_dict["potential_savings"] = self._format_currency(flag.potential_savings)

            if flag.sources:
                for source in flag_dict.get("sources", []):
                    s_type = source.get("type")
                    if s_type:
                        source_type_map = {
                            "VAREJO": "Varejo",
                            "B2B": "Atacado",
                            "OFICIAL": "Site Oficial",
                            "PAINEL_PRECOS": "Painel de Preços",
                            "BANCO_PRECOS": "Banco de Preços",
                            "OUTRO": "Outro",
                        }
                        source["type"] = source_type_map.get(s_type, s_type)

                    if source.get("reference_price"):
                        source["reference_price"] = self._format_currency(source["reference_price"])

            red_flags.append(flag_dict)

        total_value = analysis_data.get("total_estimated_value")
        estimated_value = self._format_currency(total_value)

        cnpj = raw_data.get("orgaoEntidade", {}).get("cnpj")
        agency = raw_data.get("orgaoEntidade", {}).get("razaoSocial") or "Órgão N/A"
        ano = raw_data.get("anoCompra")
        sequencial = raw_data.get("sequencialCompra")

        official_link = None
        if cnpj and ano and sequencial:
            official_link = f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{sequencial}"

        if not official_link:
            official_link = raw_data.get("linkSistemaOrigem")
        return {
            "id": analysis_data["analysis_id"],
            "control_number": analysis_data["procurement_control_number"],
            "score": ai_analysis.risk_score or 0,
            "summary": ai_analysis.procurement_summary,
            "analysis_summary": ai_analysis.analysis_summary,
            "rationale": ai_analysis.risk_score_rationale,
            "red_flags": red_flags,
            "created_at": analysis_data.get("created_at"),
            "grounding_metadata": analysis_data.get("grounding_metadata"),
            "location": location,
            "modality": modality,
            "publication_date": analysis_data.get("pncp_publication_date"),
            "status": status,
            "estimated_value": estimated_value,
            "official_link": official_link,
            "agency": agency,
        }

    def _map_to_view(self, analysis: AnalysisResult) -> dict[str, Any]:

        raw_data = getattr(analysis, "raw_data", {}) or {}
        if isinstance(raw_data, str):
            raw_data = json.loads(raw_data)

        unit = raw_data.get("unidadeOrgao", {})
        location = (
            f"{unit.get('municipioNome', '')} - {unit.get('ufSigla', '')}"
            if unit.get("municipioNome")
            else "Localização N/A"
        )
        agency = raw_data.get("orgaoEntidade", {}).get("razaoSocial") or "Órgão N/A"

        total_savings = 0
        if analysis.ai_analysis and analysis.ai_analysis.red_flags:
            for flag in analysis.ai_analysis.red_flags:
                if flag.potential_savings:
                    total_savings += flag.potential_savings

        savings_text = self._format_currency(total_savings) if total_savings > 0 else None

        return {
            "id": analysis.analysis_id,
            "control_number": analysis.procurement_control_number,
            "score": analysis.ai_analysis.risk_score or 0,
            "summary": analysis.ai_analysis.procurement_summary
            or analysis.ai_analysis.analysis_summary
            or "Sem resumo",
            "created_at": analysis.created_at,
            "agency": agency,
            "location": location,
            "savings": savings_text,
        }
