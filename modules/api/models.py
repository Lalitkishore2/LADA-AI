"""
LADA API — Pydantic request/response models.
"""

from typing import Optional, List, Dict, Any

try:
    from pydantic import BaseModel, Field
    PYDANTIC_OK = True
except ImportError:
    PYDANTIC_OK = False

if PYDANTIC_OK:
    class ChatRequest(BaseModel):
        """Chat request model."""
        message: str = Field(..., description="User message")
        conversation_id: Optional[str] = Field(None, description="Existing conversation ID")
        stream: bool = Field(False, description="Enable streaming response")
        model: Optional[str] = Field(None, description="AI model to use")
        use_web_search: bool = Field(False, description="Enable web search")

    class ChatResponse(BaseModel):
        """Chat response model."""
        success: bool
        response: str
        conversation_id: str
        model: str
        sources: List[Dict] = Field(default_factory=list)
        timestamp: str

    class AgentRequest(BaseModel):
        """Agent request model."""
        agent: str = Field(..., description="Agent type: flight, hotel, restaurant, email, calendar")
        action: str = Field(..., description="Action to perform")
        params: Dict = Field(default_factory=dict, description="Action parameters")

    class AgentResponse(BaseModel):
        """Agent response model."""
        success: bool
        agent: str
        action: str
        result: Any
        timestamp: str

    class ConversationInfo(BaseModel):
        """Conversation info model."""
        id: str
        title: str
        message_count: int
        created_at: str
        updated_at: str

    class HealthResponse(BaseModel):
        """Health check response."""
        status: str
        version: str
        uptime: float
        agents: List[str]
        models: List[str]

    class OpenAIChatMessage(BaseModel):
        """OpenAI-compatible chat message."""
        role: str
        content: str

    class OpenAIChatRequest(BaseModel):
        """OpenAI-compatible chat completions request."""
        model: str = Field("auto", description="Model ID or 'auto' for LADA tier routing")
        messages: List[OpenAIChatMessage] = Field(default_factory=list)
        stream: bool = Field(False)
        temperature: Optional[float] = Field(0.7)
        max_tokens: Optional[int] = Field(2048)
