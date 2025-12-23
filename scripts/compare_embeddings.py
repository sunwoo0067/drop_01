import asyncio
import httpx
import numpy as np
import logging
import json

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def get_embedding(text, model, base_url="http://localhost:11434"):
    url = f"{base_url}/api/embed"
    payload = {"model": model, "input": [text]}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        return resp.json()["embeddings"][0]

def cosine_similarity(v1, v2):
    v1 = np.array(v1)
    v2 = np.array(v2)
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

async def main():
    models = {
        "Nomic": "nomic-embed-text-v2-moe",
        "Gemma": "embeddinggemma"
    }
    
    # Test cases: (Anchor, Similar, Dissimilar)
    test_cases = [
        {
            "name": "Korean Product Match",
            "anchor": "나이키 에어 줌 페가수스 39 러닝화",
            "similar": "NIKE AIR ZOOM PEGASUS 39 조깅화",
            "dissimilar": "아디다스 울트라부스트 22 운동화"
        },
        {
            "name": "Color Abbreviation Match",
            "anchor": "블랙 패딩 점퍼",
            "similar": "검정 패딩 잠바",
            "dissimilar": "화이트 셔츠"
        }
    ]

    print("\n" + "="*50)
    print("EMBEDDING MODEL COMPARISON (Similarity Score)")
    print("="*50)

    for case in test_cases:
        print(f"\n[Case: {case['name']}]")
        print(f"Anchor: {case['anchor']}")
        
        for name, model in models.items():
            try:
                v_anchor = await get_embedding(case['anchor'], model)
                v_similar = await get_embedding(case['similar'], model)
                v_dissimilar = await get_embedding(case['dissimilar'], model)
                
                sim_pos = cosine_similarity(v_anchor, v_similar)
                sim_neg = cosine_similarity(v_anchor, v_dissimilar)
                gap = sim_pos - sim_neg
                
                print(f"  - {name:6}: Similar={sim_pos:.4f}, Dissimilar={sim_neg:.4f} (Gap: {gap:.4f})")
            except Exception as e:
                print(f"  - {name:6}: Error! {e}")

    # context window test logic (concept)
    print("\n[Rich Embedding Context Test]")
    long_text = "상품명: 나이키 신발" + " . " * 400 + " [이미지 정보: 이 신발은 빨간색 무늬가 있는 스포츠용 운동화로 보입니다. 바닥은 흰색 고무 창으로 되어 있습니다.]"
    print(f"Input Length: {len(long_text)} chars")
    
    for name, model in models.items():
        try:
            # If model truncates, embeddings of (short) and (short + long extension + end marker) will be identical if marker is truncated
            v_short = await get_embedding("상품명: 나이키 신발", model)
            v_long = await get_embedding(long_text, model)
            diff = np.linalg.norm(np.array(v_short) - np.array(v_long))
            print(f"  - {name:6}: Sensitivity to tail info = {diff:.4f}")
        except Exception as e:
             print(f"  - {name:6}: Error! {e}")

if __name__ == "__main__":
    asyncio.run(main())
