import cv2
import numpy as np
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.getcwd())

from app.services.image_processing import image_processing_service

def test_image_resize():
    print("이미지 리사이징 테스트 시작...")
    
    # 1. 작은 이미지 테스트 (100x100)
    print("- 작은 이미지(100x100) 테스트 중...")
    small_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", small_img)
    
    # 실제 서비스의 hash_breaking 호출
    processed_bytes = image_processing_service.hash_breaking(encoded.tobytes())
    assert processed_bytes is not None, "이미지 가공 실패"
    
    nparr = np.frombuffer(processed_bytes, np.uint8)
    processed_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w = processed_img.shape[:2]
    print(f"  원본: 100x100 -> 가공 후: {w}x{h}")
    assert w >= 500 and h >= 500, "최소 규격(500x500) 미달"

    # 2. 큰 이미지 테스트 (6000x4000)
    print("- 큰 이미지(6000x4000) 테스트 중...")
    large_img = np.zeros((4000, 6000, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", large_img)
    
    processed_bytes = image_processing_service.hash_breaking(encoded.tobytes())
    assert processed_bytes is not None, "이미지 가공 실패"
    
    nparr = np.frombuffer(processed_bytes, np.uint8)
    processed_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w = processed_img.shape[:2]
    print(f"  원본: 6000x4000 -> 가공 후: {w}x{h}")
    assert w <= 5000 and h <= 5000, "최대 규격(5000x5000) 초과"

    print("이미지 리사이징 테스트 완료!")

if __name__ == "__main__":
    try:
        test_image_resize()
    except Exception as e:
        print(f"테스트 실패: {e}")
        sys.exit(1)
