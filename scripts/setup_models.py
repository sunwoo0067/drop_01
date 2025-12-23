import os
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODELS_DIR = "app/services/ai/models"

def setup_custom_models():
    if not os.path.exists(MODELS_DIR):
        logger.error(f"Models directory not found: {MODELS_DIR}")
        return

    modelfiles = [f for f in os.listdir(MODELS_DIR) if f.endswith(".modelfile")]

    for mf in modelfiles:
        model_name = mf.replace(".modelfile", "")
        file_path = os.path.join(MODELS_DIR, mf)
        
        logger.info(f"Creating/Updating custom model: {model_name} from {file_path}")
        
        try:
            # Check if base model exists first (optional but good)
            # We'll just run ollama create
            cmd = ["ollama", "create", model_name, "-f", file_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Successfully created model: {model_name}")
            else:
                logger.error(f"Failed to create model {model_name}: {result.stderr}")
                
        except Exception as e:
            logger.error(f"Error executing ollama command: {e}")

if __name__ == "__main__":
    setup_custom_models()
