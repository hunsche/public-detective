from sqlalchemy import text
from public_detective.providers.database import DatabaseManager
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus

class AnalysisService:
    def __init__(self):
        self.engine = DatabaseManager.get_engine()

    def get_analysis_details(self, analysis_id: str):
        """Fetches detailed information for a specific analysis."""
        sql = text("""
            SELECT 
                pa.analysis_id,
                pa.procurement_control_number,
                pa.version_number,
                pa.risk_score,
                pa.risk_score_rationale,
                pa.procurement_summary,
                pa.analysis_summary,
                pa.red_flags,
                pa.updated_at,
                p.object_description,
                p.total_estimated_value,
                p.raw_data->'orgaoEntidade'->>'razaoSocial' as agency_name,
                p.raw_data->'unidadeOrgao'->>'municipioNome' as city_name,
                p.raw_data->'unidadeOrgao'->>'ufSigla' as state_acronym
            FROM procurement_analyses pa
            JOIN procurements p ON pa.procurement_control_number = p.pncp_control_number 
                AND pa.version_number = p.version_number
            WHERE pa.analysis_id = :analysis_id
        """)

        with self.engine.connect() as conn:
            result = conn.execute(sql, {"analysis_id": analysis_id}).fetchone()
            if not result:
                return None
            
            data = dict(result._mapping)
            
            # Normalize risk score
            if data['risk_score'] is not None and data['risk_score'] > 10:
                data['risk_score'] = round(data['risk_score'] / 10, 1)
                
            # Parse red_flags if it's a string (should be list/dict from JSONB but just in case)
            if isinstance(data['red_flags'], str):
                import json
                data['red_flags'] = json.loads(data['red_flags'])
                
            return data

    def get_version_history(self, procurement_control_number: str):
        """Fetches all analyzed versions for a given procurement."""
        sql = text("""
            SELECT 
                pa.analysis_id,
                pa.version_number,
                pa.risk_score,
                pa.updated_at,
                pa.status
            FROM procurement_analyses pa
            WHERE pa.procurement_control_number = :control_number
            ORDER BY pa.version_number DESC
        """)

        with self.engine.connect() as conn:
            result = conn.execute(sql, {"control_number": procurement_control_number}).fetchall()
            return [dict(row._mapping) for row in result]
