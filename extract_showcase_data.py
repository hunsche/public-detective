import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

# Database connection parameters
DB_HOST = "localhost"
DB_NAME = "public_detective"
DB_USER = "postgres"
DB_PASS = os.environ.get("PGPASSWORD", "postgres")

OUTPUT_DIR = "showcase"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "data.js")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

from decimal import Decimal

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def extract_data():
    print("Connecting to database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("Fetching successful analyses with procurement details...")
        query = """
            SELECT 
                pa.analysis_id,
                pa.procurement_control_number,
                pa.procurement_summary,
                pa.analysis_summary,
                pa.risk_score,
                pa.risk_score_rationale,
                pa.red_flags,
                pa.total_cost,
                pa.analysis_date,
                pa.grounding_metadata,
                p.raw_data -> 'unidadeOrgao' ->> 'municipioNome' as municipio,
                p.raw_data -> 'unidadeOrgao' ->> 'ufSigla' as uf,
                p.raw_data -> 'orgaoEntidade' ->> 'razaoSocial' as orgao,
                p.raw_data ->> 'valorTotalEstimado' as valor_estimado,
                p.raw_data ->> 'dataPublicacaoPncp' as data_publicacao,
                p.raw_data ->> 'situacaoCompraNome' as status_compra,
                p.raw_data ->> 'modalidadeNome' as modalidade,
                p.raw_data -> 'orgaoEntidade' ->> 'cnpj' as cnpj,
                p.raw_data ->> 'anoCompra' as ano_compra,
                p.raw_data ->> 'sequencialCompra' as sequencial_compra
            FROM procurement_analyses pa
            JOIN procurements p ON pa.procurement_control_number = p.pncp_control_number
            WHERE pa.status = 'ANALYSIS_SUCCESSFUL'
            ORDER BY pa.risk_score DESC NULLS LAST, pa.analysis_date DESC
            LIMIT 50;
        """
        cur.execute(query)
        rows = cur.fetchall()
        
        analyses = []
        for row in rows:
            data = dict(row)
            # Construct PNCP link manually: https://pncp.gov.br/app/editais/{cnpj}/{ano}/{sequencial}
            if data.get('cnpj') and data.get('ano_compra') and data.get('sequencial_compra'):
                data['link_oficial'] = f"https://pncp.gov.br/app/editais/{data['cnpj']}/{data['ano_compra']}/{data['sequencial_compra']}"
            else:
                data['link_oficial'] = None
            
            # Ensure numeric value for valor_estimado
            if data.get('valor_estimado'):
                data['valor_estimado'] = float(data['valor_estimado'])
                
            analyses.append(data)
            
        print(f"Found {len(analyses)} analyses.")
        
        # Create output directory if it doesn't exist
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
            
        # Format as JavaScript variable
        json_data = json.dumps(analyses, default=json_serial, indent=2)
        js_content = f"window.SHOWCASE_DATA = {json_data};"
        
        with open(OUTPUT_FILE, "w") as f:
            f.write(js_content)
            
        print(f"Data successfully written to {OUTPUT_FILE}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    extract_data()
