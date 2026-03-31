from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://testapp:testapp@localhost:5432/testapp"
    secret_key: str = "test-secret-key-for-scaffold"
    redis_url: str = "redis://localhost:6379"


settings = Settings()
