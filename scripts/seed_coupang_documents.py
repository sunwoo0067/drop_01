import json
import sys
from typing import Any, Iterable, Tuple

from sqlalchemy import func

from app.db import SessionLocal
from app.models import CoupangDocumentLibrary


def _iter_entries(payload: Any) -> Iterable[Tuple[str, str, str]]:
    if isinstance(payload, dict):
        payload = [payload]

    if not isinstance(payload, list):
        return []

    for entry in payload:
        if not isinstance(entry, dict):
            continue
        brand = entry.get("brand") or entry.get("Brand")
        documents = entry.get("documents")
        if brand and isinstance(documents, list):
            for doc in documents:
                if not isinstance(doc, dict):
                    continue
                template = doc.get("templateName") or doc.get("template_name")
                path = doc.get("vendorDocumentPath") or doc.get("vendor_document_path")
                if template and path:
                    yield str(brand).strip(), str(template).strip(), str(path).strip()
            continue

        template = entry.get("templateName") or entry.get("template_name")
        path = entry.get("vendorDocumentPath") or entry.get("vendor_document_path")
        if brand and template and path:
            yield str(brand).strip(), str(template).strip(), str(path).strip()


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/seed_coupang_documents.py <json_path>")
        return 1

    json_path = sys.argv[1]
    with open(json_path, "r", encoding="utf-8") as fp:
        payload = json.load(fp)

    added = 0
    updated = 0
    with SessionLocal() as session:
        for brand, template, path in _iter_entries(payload):
            row = (
                session.query(CoupangDocumentLibrary)
                .filter(func.lower(CoupangDocumentLibrary.brand) == brand.lower())
                .filter(func.lower(CoupangDocumentLibrary.template_name) == template.lower())
                .first()
            )
            if row:
                row.vendor_document_path = path
                row.is_active = True
                updated += 1
            else:
                session.add(
                    CoupangDocumentLibrary(
                        brand=brand,
                        template_name=template,
                        vendor_document_path=path,
                        is_active=True,
                    )
                )
                added += 1
        session.commit()

    print(f"Seed complete. added={added}, updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
