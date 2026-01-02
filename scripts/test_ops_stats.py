from app.db import SessionLocal
from app.services.analytics.reporting import CoupangOperationalReportService
from app.services.analytics.guardrails import CoupangGuardrailService
import json

def test_reporting():
    session = SessionLocal()
    try:
        stats = CoupangOperationalReportService.get_daily_operational_stats(session, days=7)
        print("--- Operational Stats ---")
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        
        is_critical, msg, rec = CoupangGuardrailService.check_system_integrity(session)
        print("\n--- Guardrail Check ---")
        print(f"Is Critical: {is_critical}")
        print(f"Message: {msg}")
        print(f"Recommended Mode: {rec}")
        
    finally:
        session.close()

if __name__ == "__main__":
    test_reporting()
