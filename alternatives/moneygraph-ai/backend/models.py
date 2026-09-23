from pydantic import BaseModel, Field

class NodeRequest(BaseModel):
    node_id: str = Field(min_length=1,max_length=64)

class CompareRequest(BaseModel):
    node_a: str = Field(min_length=1,max_length=64)
    node_b: str = Field(min_length=1,max_length=64)

class ChatRequest(NodeRequest):
    question: str = Field(min_length=1,max_length=1000)

class Signal(BaseModel):
    name: str
    evidence: str

class Explanation(BaseModel):
    summary: str
    priority_explanation: str
    signals: list[Signal]
    suggested_checks: list[str]
    limitations: str

class Narrative(BaseModel):
    answer: str
    suggested_checks: list[str]
    limitations: str

class Briefing(BaseModel):
    network_overview: str
    key_nodes: list[str]
    detected_patterns: list[str]
    important_transaction_paths: list[str]
    suggested_investigation_areas: list[str]
    limitations: str
