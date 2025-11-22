from sqlalchemy import text
from public_detective.providers.database import DatabaseManager
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus

class DashboardService:
    def __init__(self):
        self.engine = DatabaseManager.get_engine()

    def get_stats(self):
        """Fetches high-level statistics for the dashboard counters."""
        with self.engine.connect() as conn:
            # Total Analyzed
            total_analyzed = conn.execute(
                text("SELECT COUNT(*) FROM procurement_analyses WHERE status = :status"),
                {"status": ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL.value}
            ).scalar() or 0

            # Critical Risks (Risk Score > 80)
            critical_risks = conn.execute(
                text("SELECT COUNT(*) FROM procurement_analyses WHERE status = :status AND risk_score > 80"),
                {"status": ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL.value}
            ).scalar() or 0

            # Total Savings Potential (Sum of estimated value for high risk items - simplified metric)
            # For now, let's just sum the total_estimated_value of procurements with high risk
            total_savings = conn.execute(
                text("""
                    SELECT SUM(p.total_estimated_value) 
                    FROM procurement_analyses pa
                    JOIN procurements p ON pa.procurement_control_number = p.pncp_control_number 
                        AND pa.version_number = p.version_number
                    WHERE pa.status = :status AND pa.risk_score > 70
                """),
                {"status": ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL.value}
            ).scalar() or 0

        return {
            "total_analyzed": total_analyzed,
            "critical_risks": critical_risks,
            "total_savings": total_savings
        }

    def get_recent_activity(self, limit: int = 10, search: str = None, risk_level: str = None, 
                          city: str = None, state: str = None, category: str = None, 
                          start_date: str = None, end_date: str = None, modality: str = None,
                          min_value: float = None, max_value: float = None, year: int = None,
                          sphere: str = None, power: str = None):
        """Fetches the most recent successful analyses with optional filtering."""
        query = """
            SELECT 
                pa.analysis_id,
                pa.procurement_control_number,
                pa.risk_score,
                pa.risk_score_rationale,
                pa.procurement_summary,
                pa.updated_at,
                p.object_description,
                p.total_estimated_value,
                p.raw_data->'orgaoEntidade'->>'razaoSocial' as agency_name,
                p.raw_data->'unidadeOrgao'->>'municipioNome' as city_name,
                p.raw_data->'unidadeOrgao'->>'ufSigla' as state_acronym
            FROM procurement_analyses pa
            JOIN procurements p ON pa.procurement_control_number = p.pncp_control_number 
                AND pa.version_number = p.version_number
            WHERE pa.status = :status
        """
        params = {"status": ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL.value, "limit": limit}

        if search:
            query += """ AND (
                p.object_description ILIKE :search OR 
                p.raw_data->'orgaoEntidade'->>'razaoSocial' ILIKE :search OR 
                pa.procurement_control_number ILIKE :search
            )"""
            params["search"] = f"%{search}%"

        if risk_level:
            if risk_level == "high":
                query += " AND pa.risk_score >= 80"
            elif risk_level == "medium":
                query += " AND pa.risk_score >= 50 AND pa.risk_score < 80"
            elif risk_level == "low":
                query += " AND pa.risk_score < 50"

        if city:
            query += " AND p.raw_data->'unidadeOrgao'->>'municipioNome' ILIKE :city"
            params["city"] = f"%{city}%"

        if state:
            query += " AND p.raw_data->'unidadeOrgao'->>'ufSigla' = :state"
            params["state"] = state

        if category:
            # Check if any red flag in the array has the specified category
            query += """ AND EXISTS (
                SELECT 1 FROM jsonb_array_elements(pa.red_flags) as rf 
                WHERE rf->>'category' = :category
            )"""
            params["category"] = category

        if start_date:
            query += " AND pa.updated_at >= :start_date"
            params["start_date"] = start_date

        if end_date:
            query += " AND pa.updated_at <= :end_date"
            params["end_date"] = end_date
            
        if modality:
            query += " AND p.modality_id = :modality"
            params["modality"] = modality

        if min_value is not None:
            query += " AND p.total_estimated_value >= :min_value"
            params["min_value"] = min_value

        if max_value is not None:
            query += " AND p.total_estimated_value <= :max_value"
            params["max_value"] = max_value

        if year:
            query += " AND p.procurement_year = :year"
            params["year"] = year

        if sphere:
            query += " AND p.raw_data->'orgaoEntidade'->>'esferaId' = :sphere"
            params["sphere"] = sphere

        if power:
            query += " AND p.raw_data->'orgaoEntidade'->>'poderId' = :power"
            params["power"] = power

        query += " ORDER BY pa.updated_at DESC LIMIT :limit"

        with self.engine.connect() as conn:
            result = conn.execute(text(query), params).fetchall()
            rows = [dict(row._mapping) for row in result]
            
            # Normalize risk score to 0-10
            for row in rows:
                if row['risk_score'] is not None and row['risk_score'] > 10:
                    row['risk_score'] = round(row['risk_score'] / 10, 1)
                    
            return rows
