from sqlalchemy import text
from public_detective.providers.database import DatabaseManager
import json

def check_db():
    engine = DatabaseManager.get_engine()
    analysis_id = "505c7b15-75ee-4242-8b22-885be108da67"
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT red_flags FROM procurement_analyses WHERE analysis_id = :id"), {"id": analysis_id}).fetchone()
        if result:
            print(f"Raw red_flags: {result[0]}")
            print(f"Type: {type(result[0])}")
        else:
            print("Analysis not found")

if __name__ == "__main__":
    check_db()
