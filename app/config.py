from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='COGNITRAIL_', env_file='.env', extra='ignore', hide_input_in_errors=True)
    database_url: str = 'sqlite:///.runtime/cognitrail.db'
    deployment: Literal['local', 'private'] = 'local'
    public_url: str = ''
    gateway_secret: str = ''
    provider: Literal['extractive', 'gemini'] = 'extractive'
    model: str = 'extractive-v1'
    gemini_api_key: str = ''
    brave_api_key: str = ''
    api_token: str = ''
    data_dir: Path = Path('.runtime')
    max_sources: int = Field(30, ge=1, le=100)
    max_file_bytes: int = Field(5 * 1024 * 1024, ge=1024, le=5 * 1024 * 1024)
    max_source_chars: int = Field(100000, ge=1000, le=100000)
    max_workspace_chars: int = Field(2000000, ge=1000, le=5000000)
    timeout: int = Field(20, ge=1, le=30)
    daily_model_calls: int = Field(100, ge=1, le=1000)
    daily_search_calls: int = Field(100, ge=1, le=1000)
    retention_days: int = Field(30, ge=1, le=90)

    @model_validator(mode='after')
    def provider_config(self):
        import re
        from urllib.parse import urlparse
        if self.deployment == 'private':
            origin = urlparse(self.public_url)
            if origin.scheme != 'https' or not origin.hostname or origin.path not in ('', '/') or origin.query or origin.fragment or origin.username is not None or origin.password is not None:
                raise ValueError('Private hosting requires an HTTPS public origin')
            if len(self.gateway_secret) < 32:
                raise ValueError('Private hosting requires a gateway secret of at least 32 characters')
            if self.api_token:
                raise ValueError('Private hosting authenticates through the HTTPS gateway, not a browser API token')
        if self.provider == 'gemini':
            if not self.gemini_api_key or self.model == 'extractive-v1' or not re.fullmatch(r'[A-Za-z0-9._-]+', self.model):
                raise ValueError('Configure a Gemini key and valid available model ID')
        return self
