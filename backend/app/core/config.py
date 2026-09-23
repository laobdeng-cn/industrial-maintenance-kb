from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Industrial Maintenance KB"
    app_env: str = "development"

    database_url: str
    redis_url: str
    qdrant_url: str

    qdrant_collection: str = "maintenance_blocks_v1"
    embedding_model: str = (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    embedding_vector_size: int = 384
    embedding_cache_dir: str = "/data/models/fastembed"

    storage_root: str = "/data/storage"
    max_upload_bytes: int = 100 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
