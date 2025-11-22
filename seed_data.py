import json
import uuid
from datetime import datetime, timedelta
from sqlalchemy import text
from public_detective.providers.database import DatabaseManager
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus

def seed_data():
    print("Seeding database...")
    engine = DatabaseManager.get_engine()

    # 1. Create a Procurement
    control_number = "12345678000199-1-000001/2025"
    version_1 = 1
    version_2 = 2
    
    agency_data = {
        "razaoSocial": "Prefeitura Municipal de Exemplo",
        "cnpj": "12345678000199",
        "poderId": "E",
        "esferaId": "M"
    }
    
    raw_data_v1 = json.dumps({
        "orgaoEntidade": agency_data,
        "objetoCompra": "Aquisição de medicamentos hospitalares",
        "valorTotalEstimado": 1500000.00,
        "dataAtualizacao": datetime.now().isoformat()
    })
    
    raw_data_v2 = json.dumps({
        "orgaoEntidade": agency_data,
        "objetoCompra": "Aquisição de medicamentos hospitalares (Retificado)",
        "valorTotalEstimado": 1450000.00,
        "dataAtualizacao": datetime.now().isoformat()
    })

    with engine.connect() as conn:
        # Insert Procurement Version 1
        conn.execute(text("""
            INSERT INTO procurements (
                procurement_id, pncp_control_number, object_description, total_estimated_value,
                is_srp, procurement_year, procurement_sequence, pncp_publication_date,
                last_update_date, modality_id, procurement_status_id, version_number,
                raw_data, votes_count
            ) VALUES (
                :id, :pncp, :desc, :val, :srp, :year, :seq, :pub_date, :update_date,
                :mod, :status, :ver, :raw, 0
            ) ON CONFLICT (pncp_control_number, version_number) DO NOTHING
        """), {
            "id": uuid.uuid4(),
            "pncp": control_number,
            "desc": "Aquisição de medicamentos hospitalares",
            "val": 1500000.00,
            "srp": False,
            "year": 2025,
            "seq": 1,
            "pub_date": datetime.now(),
            "update_date": datetime.now(),
            "mod": 6, # Electronic Auction
            "status": 1, # Published
            "ver": version_1,
            "raw": raw_data_v1
        })

        # Insert Procurement Version 2
        conn.execute(text("""
            INSERT INTO procurements (
                procurement_id, pncp_control_number, object_description, total_estimated_value,
                is_srp, procurement_year, procurement_sequence, pncp_publication_date,
                last_update_date, modality_id, procurement_status_id, version_number,
                raw_data, votes_count
            ) VALUES (
                :id, :pncp, :desc, :val, :srp, :year, :seq, :pub_date, :update_date,
                :mod, :status, :ver, :raw, 0
            ) ON CONFLICT (pncp_control_number, version_number) DO NOTHING
        """), {
            "id": uuid.uuid4(),
            "pncp": control_number,
            "desc": "Aquisição de medicamentos hospitalares (Retificado)",
            "val": 1450000.00,
            "srp": False,
            "year": 2025,
            "seq": 1,
            "pub_date": datetime.now(),
            "update_date": datetime.now(),
            "mod": 6,
            "status": 1,
            "ver": version_2,
            "raw": raw_data_v2
        })

        # Insert Analysis for Version 1 (High Risk)
        analysis_id_v1 = uuid.uuid4()
        conn.execute(text("""
            INSERT INTO procurement_analyses (
                analysis_id, procurement_control_number, version_number, status,
                risk_score, risk_score_rationale, procurement_summary, analysis_summary,
                red_flags, updated_at
            ) VALUES (
                :id, :pncp, :ver, :status, :score, :rationale, :summary, :analysis_summary, :flags, :date
            )
        """), {
            "id": analysis_id_v1,
            "pncp": control_number,
            "ver": version_1,
            "status": ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL.value,
            "score": 85,
            "rationale": "Alto risco de sobrepreço identificado.",
            "summary": "Compra de medicamentos com indícios de irregularidade.",
            "analysis_summary": "A análise detectou preços acima do mercado.",
            "flags": json.dumps([
                {
                    "title": "Sobrepreço Identificado",
                    "category": "SOBREPRECO",
                    "severity": "GRAVE",
                    "description": "Os itens 1, 4 e 7 apresentam preços unitários 50% acima da tabela CMED.",
                    "evidence_quote": "Item 1: R$ 150,00 (Valor Estimado) vs R$ 100,00 (Tabela CMED)",
                    "auditor_reasoning": "A comparação com o Banco de Preços em Saúde (BPS) e a tabela CMED indica um sobrepreço significativo sem justificativa técnica aparente no Estudo Técnico Preliminar.",
                    "sources": [
                        {"name": "Tabela CMED 2025", "url": "https://www.gov.br/anvisa/pt-br", "reference_price": "100,00", "price_unit": "unidade"},
                        {"name": "Painel de Preços", "url": "https://paineldeprecos.planejamento.gov.br", "reference_price": "98,50", "price_unit": "unidade"}
                    ]
                },
                {
                    "title": "Restrição de Competitividade",
                    "category": "RESTRICAO_COMPETITIVIDADE",
                    "severity": "MODERADA",
                    "description": "Exigência de atestado de capacidade técnica com quantitativos superiores a 50% do objeto.",
                    "evidence_quote": "Item 4.2 do Edital: 'Atestado comprovando fornecimento anterior de no mínimo 80% do quantitativo licitado.'",
                    "auditor_reasoning": "A jurisprudência do TCU recomenda que a exigência não ultrapasse 50% para não restringir indevidamente a competição.",
                    "sources": []
                }
            ]),
            "date": datetime.now() - timedelta(days=2)
        })

        # Insert Analysis for Version 2 (Medium Risk - after correction)
        analysis_id_v2 = uuid.uuid4()
        conn.execute(text("""
            INSERT INTO procurement_analyses (
                analysis_id, procurement_control_number, version_number, status,
                risk_score, risk_score_rationale, procurement_summary, analysis_summary,
                red_flags, updated_at
            ) VALUES (
                :id, :pncp, :ver, :status, :score, :rationale, :summary, :analysis_summary, :flags, :date
            )
        """), {
            "id": analysis_id_v2,
            "pncp": control_number,
            "ver": version_2,
            "status": ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL.value,
            "score": 45,
            "rationale": "Risco reduzido após retificação.",
            "summary": "Compra de medicamentos retificada.",
            "analysis_summary": "Preços ajustados, mas ainda requer atenção.",
            "flags": json.dumps([]),
            "date": datetime.now()
        })
        
        conn.commit()

    print("Database seeded successfully!")

if __name__ == "__main__":
    seed_data()
