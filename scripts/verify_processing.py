import sys
import os

# Add app to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.services.storage_service import storage_service
from app.services.image_processing import image_processing_service
from app.services.gemini_utils import optimize_seo

def verify():
    print("1. Checking Imports...")
    try:
        import cv2
        import numpy as np
        import requests
        from bs4 import BeautifulSoup
        import supabase
        print("   [PASS] All libraries imported.")
    except ImportError as e:
        print(f"   [FAIL] Missing library: {e}")
        return

    print("\n2. Checking Service Instantiation...")
    if storage_service:
        print("   [PASS] StorageService instantiated.")
    else:
        print("   [FAIL] StorageService failed.")

    if image_processing_service:
        print("   [PASS] ImageProcessingService instantiated.")
    else:
        print("   [FAIL] ImageProcessingService failed.")

    print("\n3. Checking GEMINI Utils Signature...")
    # Just checking if calling it without error (even if model is None) works
    try:
        res = optimize_seo("Test Product", ["tag1", "tag2"], "Detail content here")
        print(f"   [PASS] optimize_seo executed. Result keys: {res.keys()}")
    except Exception as e:
        print(f"   [FAIL] optimize_seo execution failed: {e}")

    print("\nVerification Complete.")

if __name__ == "__main__":
    verify()
