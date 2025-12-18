import cv2
import numpy as np
import sys
import os
import random

# Mocking ImageProcessingService logic
def mock_hash_breaking(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    
    height, width = img.shape[:2]
    scale = random.uniform(1.01, 1.02)
    new_height, new_width = int(height * scale), int(width * scale)
    
    MIN_DIM = 500
    MAX_DIM = 5000
    
    if new_width < MIN_DIM or new_height < MIN_DIM:
        ratio = max(MIN_DIM / new_width, MIN_DIM / new_height)
        new_width = int(new_width * ratio)
        new_height = int(new_height * ratio)
    
    if new_width > MAX_DIM or new_height > MAX_DIM:
        ratio = min(MAX_DIM / new_width, MAX_DIM / new_height)
        new_width = int(new_width * ratio)
        new_height = int(new_height * ratio)

    img_resized = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
    return img_resized

def test_image_resize():
    # 1. Create a small image (100x100)
    small_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", small_img)
    
    processed = mock_hash_breaking(encoded.tobytes())
    h, w = processed.shape[:2]
    print(f"Original: 100x100 -> Processed: {w}x{h}")
    assert w >= 500 and h >= 500, "Should be at least 500x500"

    # 2. Create a large image (6000x4000)
    # Actually 6000x4000 might consume much memory, let's try something large but safe
    large_img = np.zeros((4000, 6000, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", large_img)
    processed = mock_hash_breaking(encoded.tobytes())
    h, w = processed.shape[:2]
    print(f"Original: 6000x4000 -> Processed: {w}x{h}")
    assert w <= 5000 and h <= 5000, "Should be at most 5000x5000"

    print("Image resize test passed!")

if __name__ == "__main__":
    test_image_resize()
