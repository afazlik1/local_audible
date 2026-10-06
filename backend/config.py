from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.8:27b-mtp-q8_0"
    ocr_timeout: float = 1800
    book_images_dir: Path = Path("book images")
    data_dir: Path = Path("data")
    tts_provider: str = "kokoro"
    kokoro_voice: str = "af_heart"
    kokoro_lang_code: str = "a"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
