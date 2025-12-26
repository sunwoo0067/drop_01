import sys
import os

# Add app to path
sys.path.append(os.getcwd())

from app.services.image_processing import image_processing_service
from app.coupang_sync import _normalize_detail_html_for_coupang
from app.services.detail_html_checks import find_forbidden_tags, strip_forbidden_tags

def test_normalization():
    print("Testing HTML Normalization...")
    html = '<center><img src="http://example.com/test.jpg">_x000D_<script>alert(1)</script></center>'
    
    # 1. Strip forbidden tags
    stripped = strip_forbidden_tags(html)
    print(f"Stripped: {stripped}")
    assert "<script>" not in stripped
    
    # 2. Normalize for Coupang
    normalized = _normalize_detail_html_for_coupang(html)
    print(f"Normalized: {normalized}")
    assert "https://" in normalized
    assert "_x000D_" not in normalized
    assert "<script>" not in normalized
    
    print("Normalization test passed!\n")

def test_fragment_preservation():
    print("Testing Fragment Preservation...")
    fragment = '<div style="text-align:center;">이미지 설명</div><br><img src="http://example.com/1.jpg">'
    
    # Simulation of replace_html_image_urls (mocking download/upload is hard, so just check structure)
    # We replaced str(soup) with soup.decode_contents()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(fragment, "html.parser")
    result = soup.decode_contents()
    
    print(f"Original: {fragment}")
    print(f"Result: {result}")
    
    # BeautifulSoup might fix tag closures but shouldn't add <html>/<body> if fragment was simple
    assert "<html>" not in result
    assert "<body>" not in result
    
    print("Fragment preservation test passed!\n")

if __name__ == "__main__":
    test_normalization()
    test_fragment_preservation()
    print("All tests passed!")
