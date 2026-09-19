# control_plane/gateway.py
import re
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

app = FastAPI(title="Enterprise AI Gateway")
security = HTTPBearer()

class ChatRequest(BaseModel):
    user_id: str
    tenant_id: str
    message: str

def sanitize_input(text: str) -> str:
    # 1. Block common prompt injection patterns
    injection_patterns = [r"ignore previous instructions", r"system prompt", r"override rules"]
    for pattern in injection_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            raise HTTPException(status_code=400, detail="Security policy violation: Prompt injection detected.")
    
    # 2. Simple PII Masking (e.g., SSN / Credit Card patterns)
    masked_text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]", text)
    return masked_text

@app.post("/v1/chat/completions")
async def process_chat_request(request: ChatRequest, auth: HTTPAuthorizationCredentials = Depends(security)):
    # Authenticate token (stubbed)
    if not auth.credentials:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Enforce Pre-Execution Guardrail
    clean_message = sanitize_input(request.message)
    
    # Hand off to Layer 2 (Agent Runtime)
    # ... runtime.execute(user_id=request.user_id, prompt=clean_message) ...
    return {"status": "success", "sanitized_prompt": clean_message}