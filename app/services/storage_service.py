import logging
import uuid
from typing import Optional
from supabase import create_client, Client
from app.settings import settings

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self):
        self.url = settings.supabase_url
        self.key = settings.supabase_service_role_key
        self.bucket = settings.supabase_bucket
        
        if not self.url or not self.key:
            logger.warning("Supabase credentials not set. Storage service disabled.")
            self.client: Optional[Client] = None
        else:
            try:
                self.client = create_client(self.url, self.key)
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                self.client = None

    def upload_image(self, file_content: bytes, file_ext: str = "jpg", path_prefix: str = "processed") -> Optional[str]:
        """
        Uploads bytes to Supabase Storage and returns the public URL.
        Path format: {path_prefix}/{uuid}.{file_ext}
        """
        if not self.client:
            logger.error("Supabase client is not initialized.")
            return None

        file_name = f"{uuid.uuid4()}.{file_ext}"
        file_path = f"{path_prefix}/{file_name}"

        content_type = f"image/{file_ext}"
        if file_ext == "jpg":
            content_type = "image/jpeg"

        try:
            self.client.storage.from_(self.bucket).upload(
                path=file_path,
                file=file_content,
                file_options={"content-type": content_type}
            )
            
            # Get Public URL
            public_url = self.client.storage.from_(self.bucket).get_public_url(file_path)
            return public_url

        except Exception as e:
            logger.error(f"Failed to upload image to Supabase: {e}")
            return None

# Singleton instance
storage_service = StorageService()
