from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FabricSettings(BaseSettings):
    environment: str = Field(default="development")
    fabric_wallet_path: Path
    fabric_connection_profile: Path
    fabric_channel: str
    fabric_chaincode: str
    fabric_tls_enabled: bool
    fabric_grpc_timeout: int
    redis_url: str
    secret_key: str

    vault_addr: str = Field(default="http://10.10.10.150:8200")
    vault_token: str = Field(...)

    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="llama-3.3-70b-versatile")

    fabric_retry_max_attempts: int
    fabric_retry_base_delay: float
    fabric_retry_factor: float
    fabric_retry_jitter: float
    fabric_retry_circuit_breaker_threshold: int
    fabric_retry_circuit_breaker_timeout: float

    fabric_events_rate_limit: float
    fabric_events_redis_channel: str
    fabric_events_targets: str
    fabric_events_required_payload_fields: str
    fabric_events_grpc_reconnect_delay: float
    fabric_events_grpc_simulation_delay: float

    fabric_required_msps: str
    fabric_ledger_not_found_error_string: str
    fabric_endorsement_error_string: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters.")
        return v


class Settings(FabricSettings):
    database_url: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    allowed_origins: str
    log_level: str = "INFO"

    # gRPC server
    grpc_port: int = Field(default=50051)
    grpc_server_cert: str = Field(default="")   # path to PEM cert (production)
    grpc_server_key: str = Field(default="")    # path to PEM private key
    grpc_ca_cert: str = Field(default="")       # path to CA cert for mTLS

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.environment == "production":
            if not self.fabric_tls_enabled:
                raise ValueError("TLS must be enabled in production.")
            if "localhost" in self.database_url:
                raise ValueError("localhost database URL is not allowed in production.")
        return self


settings = Settings()
