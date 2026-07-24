import os
from typing import Optional, Dict, Union, Any
from pydantic import BaseModel, Field
import yaml

class EndpointConfig(BaseModel):
    url: str
    method: str = "POST"
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Any = None
    file_field: Optional[str] = None

class EndpointsConfig(BaseModel):
    chat: Union[str, EndpointConfig]
    receive: Optional[Union[str, EndpointConfig]] = None
    upload: Union[str, EndpointConfig]
    retrieval: Optional[Union[str, EndpointConfig]] = None

class AuthConfig(BaseModel):
    type: str = "none" # bearer | api_key | basic | none
    token_env: Optional[str] = None

class ResponseFormatConfig(BaseModel):
    answer_field: str = "response.text"
    citations_field: str = "response.sources"
    stream: bool = False

class TargetConfig(BaseModel):
    name: str
    endpoints: EndpointsConfig
    auth: AuthConfig = AuthConfig()
    response_format: ResponseFormatConfig = ResponseFormatConfig()

class CorpusConfig(BaseModel):
    path: Optional[str] = None
    use_bundled: bool = False

class TestsConfig(BaseModel):
    hallucination_rate: bool = False
    citation_integrity: bool = False
    retrieval_relevance: bool = False
    injection_resistance: bool = False
    cross_tenant_leakage: bool = False
    confidence_threshold: bool = False
    contradiction_surfacing: bool = False
    latency_penalty: bool = False
    retrieval_disambiguation: bool = False
    structural_integrity: bool = False
    entity_masking_rehydration: bool = False
    cross_document_attribution: bool = False
    parametric_knowledge_bleed: bool = False

class TenantConfig(BaseModel):
    token_env: str

class ThresholdsConfig(BaseModel):
    max_hallucination_rate: float = 0.02
    min_retrieval_relevance: float = 0.85
    max_injection_success_rate: float = 0.0
    max_cross_tenant_leaks: int = 0

class AuditConfig(BaseModel):
    target: TargetConfig
    corpus: CorpusConfig
    tests: TestsConfig
    multi_tenant: Optional[Dict[str, TenantConfig]] = None
    thresholds: ThresholdsConfig = ThresholdsConfig()

    @classmethod
    def load_from_yaml(cls, path: str) -> "AuditConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)
