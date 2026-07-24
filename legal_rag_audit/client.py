import os
import json
import logging
from typing import Dict, Any, List, Optional
import httpx
from jsonpath_ng import parse

from legal_rag_audit.config import TargetConfig

logger = logging.getLogger(__name__)

class TargetClient:
    def __init__(self, target_config: TargetConfig):
        self.config = target_config
        self.headers = self._build_auth_headers()
        self.client = httpx.AsyncClient(timeout=60.0, headers=self.headers)
        
        self.answer_parser = parse(self.config.response_format.answer_field)
        self.citations_parser = parse(self.config.response_format.citations_field)

    def _build_auth_headers(self) -> Dict[str, str]:
        headers = {}
        auth = self.config.auth
        if auth.type != "none" and auth.token_env:
            token = os.environ.get(auth.token_env)
            if not token:
                logger.warning(f"Auth token env var {auth.token_env} is not set!")
                token = "DUMMY_TOKEN" # Fallback for dummy tests
            
            if auth.type == "bearer":
                headers["Authorization"] = f"Bearer {token}"
            elif auth.type == "api_key":
                headers["x-api-key"] = token
            elif auth.type == "basic":
                # Assuming the token is already base64 encoded or formatted appropriately
                headers["Authorization"] = f"Basic {token}"
        return headers

    async def upload_document(self, filename: str, content: str, metadata: Optional[Dict] = None) -> Any:
        payload = {
            "filename": filename,
            "content": content,
        }
        if metadata:
            payload["metadata"] = metadata
            
        logger.debug(f"Uploading {filename} to {self.config.endpoints.upload}")
        response = await self.client.post(self.config.endpoints.upload, json=payload)
        response.raise_for_status()
        return response.json()

    async def chat(self, query: str) -> Dict[str, Any]:
        payload = {"query": query}
        logger.debug(f"Sending query to {self.config.endpoints.chat}: {query}")
        
        if self.config.response_format.stream:
            # Simple SSE handling: collect chunks and combine
            answer_text = ""
            citations = []
            raw_response = {}
            
            async with self.client.stream("POST", self.config.endpoints.chat, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        if data_str:
                            try:
                                chunk = json.loads(data_str)
                                # Very basic naive streaming parsing: assumes structure holds per chunk
                                match = self.answer_parser.find(chunk)
                                if match:
                                    answer_text += match[0].value
                                
                                cit_match = self.citations_parser.find(chunk)
                                if cit_match and isinstance(cit_match[0].value, list):
                                    citations.extend(cit_match[0].value)
                            except json.JSONDecodeError:
                                pass
            return {
                "answer": answer_text,
                "citations": citations,
                "raw": raw_response
            }
        else:
            response = await self.client.post(self.config.endpoints.chat, json=payload)
            response.raise_for_status()
            data = response.json()
            
            answer_match = self.answer_parser.find(data)
            answer_text = answer_match[0].value if answer_match else ""
            
            cit_match = self.citations_parser.find(data)
            citations = cit_match[0].value if cit_match else []
            
            return {
                "answer": answer_text,
                "citations": citations,
                "raw": data
            }

    async def close(self):
        await self.client.aclose()
