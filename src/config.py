from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "hackathon2026"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "chunks"

    llm_base_url: str = "https://api.ollama.com"
    llm_api_key: str = ""
    llm_model: str = "gemma3:12b"
    llm_provider: str = ""  # "" = автодетект; openai | ollama

    embed_model: str = "intfloat/multilingual-e5-small"

    api_url: str = "http://localhost:8000"
    data_real_dir: str = "data/real"  # корпус для вкладки «Библиотека» и раздачи /files


settings = Settings()
