import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") # This is anon currently
bucket = os.getenv("SUPABASE_BUCKET", "images")

print(f"URL: {url}")
print(f"Key Prefix: {key[:10]}...")
print(f"Bucket: {bucket}")

supabase = create_client(url, key)

try:
    test_data = b"hello test image"
    path = "test_upload.txt"
    res = supabase.storage.from_(bucket).upload(
        path=path,
        file=test_data,
        file_options={"content-type": "text/plain"}
    )
    print("Upload result:", res)
    public_url = supabase.storage.from_(bucket).get_public_url(path)
    print("Public URL:", public_url)
except Exception as e:
    print("Upload failed:", e)
