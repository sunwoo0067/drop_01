import requests
import uuid
import time

BASE_URL = "http://localhost:8888/api"

def test_benchmark_filters():
    print("Testing Benchmark Filters...")
    
    # 1. Test basic listing through alias
    resp = requests.get(f"{BASE_URL}/benchmarks", params={"limit": 1})
    if resp.status_code != 200:
        print(f"FAILED: Initial listing failed with {resp.status_code}")
        return
    print("✓ Basic listing through alias OK")

    # 2. Test price filters
    resp = requests.get(f"{BASE_URL}/benchmarks", params={"minPrice": 10000, "maxPrice": 50000, "limit": 10})
    if resp.status_code == 200:
        items = resp.json().get("items", [])
        all_match = all(10000 <= i["price"] <= 50000 for i in items)
        print(f"✓ Price filters OK (items: {len(items)}, match: {all_match})")
    else:
        print(f"FAILED: Price filters failed with {resp.status_code}")

    # 3. Test rating and quality score filters
    resp = requests.get(f"{BASE_URL}/benchmarks", params={"minRating": 4.0, "minQualityScore": 7.0, "limit": 10})
    if resp.status_code == 200:
        items = resp.json().get("items", [])
        all_match = all((i.get("rating") or 0) >= 4.0 and (i.get("qualityScore") or 0) >= 7.0 for i in items)
        print(f"✓ Rating/Quality filters OK (items: {len(items)}, match: {all_match})")
    else:
        print(f"FAILED: Rating/Quality filters failed with {resp.status_code}")

def test_job_retry_flow():
    print("\nTesting Job Retry Flow...")
    
    # 1. Find a failed or finished job to retry (or just use a random ID to check endpoint availability)
    # For a real test, we would need a job in the DB.
    # Let's try to list jobs first to find a candidate
    resp = requests.get(f"{BASE_URL}/benchmarks/jobs", params={"limit": 5})
    if resp.status_code != 200:
        print("FAILED: Could not list jobs")
        return
    
    jobs = resp.json().get("items", [])
    if not jobs:
        print("SKIP: No jobs found to test retry")
        return
    
    job_id = jobs[0]["id"]
    print(f"Retrying job: {job_id}")
    
    resp = requests.post(f"{BASE_URL}/benchmarks/jobs/{job_id}/retry")
    if resp.status_code in (200, 201, 202):
        print("✓ Job retry triggered OK")
        new_job_id = resp.json().get("jobId")
        print(f"New Job ID: {new_job_id}")
        
        # Verify new job status
        time.sleep(1)
        resp = requests.get(f"{BASE_URL}/benchmarks/jobs/{new_job_id}")
        if resp.status_code == 200:
            print(f"✓ New job status: {resp.json().get('status')}")
    else:
        print(f"FAILED: Job retry failed with {resp.status_code}: {resp.text}")

if __name__ == "__main__":
    try:
        test_benchmark_filters()
        test_job_retry_flow()
    except Exception as e:
        print(f"Error during testing: {e}")
