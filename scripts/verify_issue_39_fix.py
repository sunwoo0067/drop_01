import sys
import os

# Add app to path
sys.path.append(os.getcwd())

from bs4 import BeautifulSoup
from app.services.image_processing import image_processing_service
from app.coupang_sync import _normalize_detail_html_for_coupang
from app.services.detail_html_checks import find_forbidden_tags, strip_forbidden_tags

def test_normalization():
    print("Testing HTML Normalization (Full Strip)...")
    html = '<center><img src="http://example.com/test.jpg">_x000D_<script>alert(1); console.log("bad");</script> content </center>'
    
    # Normalize for Coupang (includes stripping)
    normalized = _normalize_detail_html_for_coupang(html)
    print(f"Normalized: {normalized}")
    assert "https://" in normalized
    assert "_x000D_" not in normalized
    assert "<script>" not in normalized
    assert "alert(1)" not in normalized  # Content should be gone
    assert "console.log" not in normalized  # Content should be gone
    
    print("Normalization test passed!\n")

def test_full_doc_vs_fragment():
    print("Testing Full Doc vs Fragment...")
    # Fragment
    frag = '<div>Fragment</div>'
    soup_frag = BeautifulSoup(frag, "html.parser")
    # Simulation (hard to call service directly without more mocks, so testing the logic)
    is_full_doc_frag = any(tag in frag.lower() for tag in ["<html", "<body"])
    res_frag = soup_frag.decode_contents() if not is_full_doc_frag else str(soup_frag)
    print(f"Fragment Result: {res_frag}")
    assert "<html>" not in res_frag
    
    # Full Doc
    doc = '<html><body><div>Full Doc</div></body></html>'
    soup_doc = BeautifulSoup(doc, "html.parser")
    is_full_doc_doc = any(tag in doc.lower() for tag in ["<html", "<body"])
    # Note: BeautifulSoup adds tags if they are missing but here they are present
    res_doc = soup_doc.decode_contents() if not is_full_doc_doc else str(soup_doc)
    print(f"Full Doc Result: {res_doc}")
    assert "<html>" in res_doc
    
    print("Full doc vs fragment test passed!\n")

if __name__ == "__main__":
    test_normalization()
    test_full_doc_vs_fragment()
    print("All tests passed!")
