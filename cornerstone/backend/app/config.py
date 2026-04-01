from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    project_name: str = "MyApp"
    api_prefix: str = "/api"
    database_url: str = "postgresql+asyncpg://myapp:myapp_secret@localhost:5432/myapp"
    database_url_sync: str = "postgresql+psycopg://myapp:myapp_secret@localhost:5432/myapp"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me"
    jwt_secret: str = "change-me"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    backend_cors_origins: list[str] = ["http://localhost:3000"]
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    debug: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
