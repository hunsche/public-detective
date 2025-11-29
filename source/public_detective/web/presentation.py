from typing import Dict, Any, List
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.providers.database import DatabaseManager
from public_detective.models.analyses import AnalysisResult, Analysis
from public_detective.models.procurements import ProcurementModality, ProcurementStatus

class PresentationService:
    def __init__(self):
        self.repo = AnalysisRepository(DatabaseManager.get_engine())

    def get_home_stats(self) -> Dict[str, Any]:
        stats = self.repo.get_home_stats()
        stats['total_savings'] = self._format_currency(stats.get('total_savings'))
        return stats

    def get_recent_analyses(self, page: int = 1, limit: int = 9) -> Dict[str, Any]:
        results, total_count = self.repo.get_recent_analyses_summary(page, limit)
        

        
        total_pages = (total_count + limit - 1) // limit
        return {
            "results": [self._map_to_view(r) for r in results],
            "total": total_count,
            "page": page,
            "pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }

    def search_analyses(self, query_str: str, page: int = 1, limit: int = 9) -> Dict[str, Any]:
        results, total_count = self.repo.search_analyses_summary(query_str, page, limit)
        

        
        total_pages = (total_count + limit - 1) // limit
        return {
            "results": [self._map_to_view(r) for r in results],
            "total": total_count,
            "page": page,
            "pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }

    def _get_total_savings(self, analysis: AnalysisResult) -> float:
        total = 0.0
        if analysis.ai_analysis and analysis.ai_analysis.red_flags:
            for flag in analysis.ai_analysis.red_flags:
                if flag.potential_savings:
                    total += float(flag.potential_savings)
        return total

    def _format_currency(self, value: float | None) -> str:
        if value is None:
            return "N/A"
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def get_analysis_details(self, analysis_id: str) -> Dict[str, Any] | None:
        try:
            from uuid import UUID
            uuid_obj = UUID(analysis_id)
        except ValueError:
            return None

        analysis_data = self.repo.get_analysis_by_id(uuid_obj)
        if not analysis_data:
            return None
            
        # Parse nested JSONs if they are strings (depends on driver/SQLAlchemy version, but raw_data is usually dict if JSONB)
        # However, AnalysisRepository.get_analysis_by_id returns a dict from result._mapping.
        # We need to manually construct AnalysisResult for the AI part or just use the dict.
        # Let's use the dict directly but parse what we need.
        
        # Helper to parse AI analysis
        ai_analysis_data = {
            "risk_score": analysis_data.get("risk_score") or 0,
            "risk_score_rationale": analysis_data.get("risk_score_rationale") or "",
            "procurement_summary": analysis_data.get("procurement_summary") or "",
            "analysis_summary": analysis_data.get("analysis_summary") or "",
            "red_flags": analysis_data.get("red_flags") if isinstance(analysis_data.get("red_flags"), list) else json.loads(analysis_data.get("red_flags") or "[]"),
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
                ProcurementModality.IN_PERSON_AUCTION: "Leilão Presencial"
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
                    ProcurementStatus.SUSPENDED: "Suspensa"
                }
                status = status_map.get(status_enum, status_enum.name.replace("_", " ").title())
            except (ValueError, TypeError):
                status = str(status_id)


        # Format Red Flags Categories
        category_map = {
            'SOBREPRECO': 'Sobrepreço',
            'RESTRICAO_COMPETITIVIDADE': 'Restrição à Competitividade',
            'FRACIONAMENTO_DESPESA': 'Fracionamento de Despesa',
            'DIRECIONAMENTO': 'Direcionamento',
            'SUPERFATURAMENTO': 'Superfaturamento',
            'JOGO_DE_PLANILHA': 'Jogo de Planilha'
        }
        
        red_flags = []
        for flag in ai_analysis.red_flags:
            flag_dict = flag.model_dump(by_alias=True)
            flag_dict['category'] = category_map.get(flag.category, flag.category.replace("_", " ").title())
            
            if flag.potential_savings:
                flag_dict['potential_savings'] = self._format_currency(flag.potential_savings)

            # Format sources within flags
            if flag.sources:
                for source in flag_dict.get('sources', []):
                    s_type = source.get('type')
                    if s_type:
                        source_type_map = {
                            'VAREJO': 'Varejo',
                            'B2B': 'Atacado',
                            'OFICIAL': 'Site Oficial',
                            'PAINEL_PRECOS': 'Painel de Preços',
                            'BANCO_PRECOS': 'Banco de Preços',
                            'OUTRO': 'Outro'
                        }
                        source['type'] = source_type_map.get(s_type, s_type)
                    
                    if source.get('reference_price'):
                        source['reference_price'] = self._format_currency(source['reference_price'])
            
            red_flags.append(flag_dict)

        # Format currency
        val = analysis_data.get("total_estimated_value")
        estimated_value = self._format_currency(val)
        
        cnpj = raw_data.get("orgaoEntidade", {}).get("cnpj")
        agency = raw_data.get("orgaoEntidade", {}).get("razaoSocial") or "Órgão N/A"
        ano = raw_data.get("anoCompra")
        sequencial = raw_data.get("sequencialCompra")
        
        # Showcase prioritizes constructed link
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
            
            # New fields
            "location": location,
            "modality": modality,
            "publication_date": analysis_data.get("pncp_publication_date"),
            "status": status,
            "estimated_value": estimated_value,
            "official_link": official_link,
            "agency": agency
        }


    def _map_to_view(self, analysis: AnalysisResult) -> Dict[str, Any]:
        # Extract raw_data if available (it might be in the model if we updated AnalysisResult or just passed through)
        # Since AnalysisResult doesn't strictly have raw_data field defined in the model shown earlier, 
        # but the repository parses it. 
        # Wait, AnalysisResult model in models/analyses.py does NOT have raw_data.
        # But _parse_row_to_model might be attaching it or we need to handle it.
        # Let's check _parse_row_to_model in repository or just assume we need to handle it.
        # Actually, the repository returns AnalysisResult objects. If raw_data isn't in AnalysisResult, it won't be there.
        # I need to check if AnalysisResult has raw_data or if I need to add it / handle it.
        # Looking at models/analyses.py, AnalysisResult does NOT have raw_data.
        # However, the repository uses `_parse_row_to_model`. 
        # If I added `p.raw_data` to the query, `_parse_row_to_model` needs to know what to do with it.
        # Let's assume for now I need to update AnalysisResult or handle it differently.
        # BUT, `_parse_row_to_model` likely uses `AnalysisResult(**row_dict)`. 
        # If `raw_data` is passed to `AnalysisResult` and `extra='ignore'`, it gets dropped.
        # If `extra='allow'`, it stays. 
        # Let's check AnalysisResult config.
        
        # ... checking previous file view of models/analyses.py ...
        # It inherits from BaseModel. Default config is extra='ignore' usually unless specified.
        # Wait, I don't see ConfigDict(extra='allow') in AnalysisResult in the previous view.
        # So I probably need to update AnalysisResult to allow extra fields or add raw_data.
        
        # Let's update the WebService assuming the data is available, 
        # but I'll also need to update the model in the next step if it's not there.
        
        # Actually, let's look at how I can access it. 
        # If `_parse_row_to_model` returns an AnalysisResult, and that model doesn't have `raw_data`, it's gone.
        
        # Strategy: Update AnalysisResult model first to include raw_data or allow extra.
        # But I am in the middle of editing WebService. 
        # I will write the code assuming `analysis.raw_data` exists or `analysis.extra['raw_data']` exists.
        # Let's assume I will add `raw_data` to AnalysisResult.
        
        raw_data = getattr(analysis, "raw_data", {}) or {}
        if isinstance(raw_data, str):
            import json
            raw_data = json.loads(raw_data)
            
        unit = raw_data.get("unidadeOrgao", {})
        location = f"{unit.get('municipioNome', '')} - {unit.get('ufSigla', '')}" if unit.get('municipioNome') else "Localização N/A"
        agency = raw_data.get("orgaoEntidade", {}).get("razaoSocial") or "Órgão N/A"
        
        # Calculate savings
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
            "summary": analysis.ai_analysis.procurement_summary or analysis.ai_analysis.analysis_summary or "Sem resumo",
            "created_at": analysis.created_at,
            "agency": agency,
            "location": location,
            "savings": savings_text
        }
