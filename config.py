from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "doc-intel-copilot-docs-608040300344"
    s3_presigned_url_expiry: int = 3600
    dynamodb_documents_table: str = "doc-intel-documents"
    dynamodb_extractions_table: str = "doc-intel-extractions"
    dynamodb_insights_table: str = "doc-intel-insights"
    dynamodb_reviews_table: str = "doc-intel-reviews"
    bedrock_model_id: str = "us.anthropic.claude-sonnet-4-6"
    max_file_size_mb: int = 20
    allowed_formats: list[str] = ["pdf", "png", "jpg", "jpeg"]
    classification_timeout: int = 30
    extraction_timeout: int = 30
    insights_timeout: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
