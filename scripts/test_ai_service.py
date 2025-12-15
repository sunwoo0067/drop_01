import sys
import os
import logging

# Add app to path
sys.path.append(os.getcwd())

from app.services.ai import AIService
from app.settings import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_ai():
    logger.info("Initializing AIService...")
    service = AIService()
    
    text = "This is a lightweight camping chair made of aluminum. It weighs 2kg."
    
    # 1. Test Auto (Should default to OpenAI based on new settings)
    logger.info(f"Testing 'extract_specs' with provider='auto' (Default: {settings.default_ai_provider})")
    specs = service.extract_specs(text, provider="auto")
    logger.info(f"Result: {specs}")

    # 2. Test Gemini Explicitly
    logger.info("Testing 'analyze_pain_points' with provider='gemini'")
    points = service.analyze_pain_points(text, provider="gemini")
    logger.info(f"Result: {points}")
    
    # 3. Test Ollama Explicitly
    logger.info("Testing 'extract_specs' with provider='ollama'")
    # Note: Requires local ollama running gemma2
    specs_ollama = service.extract_specs(text, provider="ollama")
    logger.info(f"Result: {specs_ollama}")

    # 4. Test OpenAI Explicitly
    logger.info("Testing 'extract_specs' with provider='openai'")
    specs_openai = service.extract_specs(text, provider="openai")
    logger.info(f"Result: {specs_openai}")

if __name__ == "__main__":
    test_ai()
