import os
import json
import logging
from typing import Dict, Any, List, Optional
import httpx
from jsonpath_ng.ext import parse

from ..config import TargetConfig

logger = logging.getLogger(__name__)

class TargetClient:
    def __init__(self, target_config: TargetConfig):
        self.config = target_config
        self.headers = self._build_auth_headers()
        self.client = httpx.AsyncClient(timeout=60.0, headers=self.headers)
        
        self.answer_parser = parse(self.config.response_format.answer_field)
        self.citations_parser = parse(self.config.response_format.citations_field)
        self.stop_parser = parse(self.config.response_format.stop_field) if getattr(self.config.response_format, 'stop_field', None) else None

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

    def _inject_variables(self, template: Any, variables: Dict[str, str]) -> Any:
        if template is None:
            return None
        if isinstance(template, str):
            res = template
            for k, v in variables.items():
                res = res.replace(f"{{{{{k}}}}}", v)
            return res
        elif isinstance(template, dict):
            return {k: self._inject_variables(v, variables) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._inject_variables(item, variables) for item in template]
        else:
            return template

    def _prepare_request(self, endpoint_config, default_payload, variables):
        if isinstance(endpoint_config, str):
            return endpoint_config, "POST", self.headers, {"json": default_payload}
        
        url = self._inject_variables(endpoint_config.url, variables)
        method = endpoint_config.method
        headers = {**self.headers, **endpoint_config.headers}
        
        if endpoint_config.body is not None:
            payload = self._inject_variables(endpoint_config.body, variables)
            if isinstance(payload, (dict, list)):
                return url, method, headers, {"json": payload}
            else:
                return url, method, headers, {"content": payload}
        else:
            if method.upper() == "GET":
                return url, method, headers, {}
            return url, method, headers, {"json": default_payload}

    async def upload_document(self, filename: str, content: str, metadata: Optional[Dict] = None) -> Any:
        endpoint_config = self.config.endpoints.upload
        
        file_field = getattr(endpoint_config, "file_field", None) if not isinstance(endpoint_config, str) else None
        
        default_payload = {
            "filename": filename,
            "content": content,
        }
        if metadata:
            default_payload["metadata"] = metadata
            
        url, method, headers, kwargs = self._prepare_request(
            endpoint_config,
            default_payload=default_payload,
            variables={"FILENAME": filename, "CONTENT": content}
        )
            
        if file_field:
            # Native multipart form upload using httpx
            # Remove content-type from headers so httpx computes the boundary correctly
            headers = {k: v for k, v in headers.items() if k.lower() != 'content-type'}
            
            # Since we are sending files, we remove json/content from kwargs
            kwargs.pop("json", None)
            kwargs.pop("content", None)
            
            files = {file_field: (filename, content, "text/plain")}
            kwargs["files"] = files
            
            logger.debug(f"Uploading {filename} to {url} using native multipart on field '{file_field}'")
            response = await self.client.request(method, url, headers=headers, **kwargs)
        else:
            logger.debug(f"Uploading {filename} to {url}")
            response = await self.client.request(method, url, headers=headers, **kwargs)
            
        response.raise_for_status()
        return response.json()

    def _extract_json_from_string(self, text: str) -> Optional[str]:
        if not isinstance(text, str):
            return None
        start_brace = text.find('{')
        start_bracket = text.find('[')
        
        start = -1
        if start_brace != -1 and start_bracket != -1:
            start = min(start_brace, start_bracket)
        else:
            start = max(start_brace, start_bracket)
            
        if start != -1:
            return text[start:]
        return None

    async def chat(self, query: str) -> Dict[str, Any]:
        import uuid
        req_uuid = str(uuid.uuid4())
        
        # `chat` may be a bare URL string or a full endpoint object (§6.1 allows both,
        # and the README example uses the string form). A string has no `.headers`, so
        # reading it directly made every chat request fail with an AttributeError while
        # uploads — which take the same union — worked fine.
        endpoint_headers = getattr(self.config.endpoints.chat, "headers", None) or {}
        chat_headers = {**self.headers, **endpoint_headers}
        variables = {"QUERY": query, "UUID": req_uuid}
        for k, v in chat_headers.items():
            variables[k] = str(v)
            variables[k.replace("-", "_")] = str(v)
        
        url, method, headers, kwargs = self._prepare_request(
            self.config.endpoints.chat,
            default_payload={"query": query},
            variables=variables
        )
        
        receive_endpoint = getattr(self.config.endpoints, "receive", None)
        if receive_endpoint:
            rec_url, rec_method, rec_headers, rec_kwargs = self._prepare_request(
                receive_endpoint,
                default_payload={},
                variables=variables
            )
            if rec_url.startswith("ws://") or rec_url.startswith("wss://"):
                import websockets
                import asyncio
                import json
                
                safe_headers = {k: v for k, v in rec_headers.items() if k.lower() not in ["connection", "upgrade", "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions"]}
                
                # Forward cookies from httpx client to websocket
                if self.client.cookies:
                    cookie_str = "; ".join([f"{k}={v}" for k, v in self.client.cookies.items()])
                    safe_headers["Cookie"] = cookie_str
                
                async with websockets.connect(rec_url, additional_headers=safe_headers, open_timeout=60.0) as websocket:
                    init_message = getattr(receive_endpoint, "init_message", None) if not isinstance(receive_endpoint, str) else None
                    if init_message:
                        init_msg_resolved = self._inject_variables(init_message, variables)
                        if isinstance(init_msg_resolved, dict):
                            init_msg_resolved = json.dumps(init_msg_resolved)
                        elif not isinstance(init_msg_resolved, str):
                            init_msg_resolved = str(init_msg_resolved)
                        await websocket.send(init_msg_resolved)
                    elif "socket.io" in rec_url:
                        # Send socket.io namespace connect packet
                        # Flexible: pull from receive.body if configured
                        connect_packet = rec_kwargs.get("content") or rec_kwargs.get("json")
                        if connect_packet:
                            if isinstance(connect_packet, dict):
                                connect_packet = json.dumps(connect_packet)
                            await websocket.send(connect_packet)
                        else:
                            await websocket.send("40")
                        
                    logger.debug(f"Sending query to {url}: {query}")
                    response = await self.client.request(method, url, headers=headers, **kwargs)
                    response.raise_for_status()

                    answer_text = ""
                    citations = []
                    raw_response = {}
                    
                    import time
                    start_time = time.time()
                    
                    while True:
                        if time.time() - start_time > 120.0:
                            logger.error("Websocket receive overall timeout (120s) reached.")
                            break
                        
                        try:
                            current_timeout = 5.0 if answer_text else 45.0
                            message = await asyncio.wait_for(websocket.recv(), timeout=current_timeout)
                            logger.debug(f"Raw WS message: {message}")
                            
                            # Handle Socket.IO Ping
                            if isinstance(message, str) and message == "2":
                                await websocket.send("3")
                                continue
                                
                            if isinstance(message, str) and getattr(self.config.response_format, 'stop_payload_match', None) and self.config.response_format.stop_payload_match in message:
                                logger.debug("Websocket receive stopped by lazy stop_payload_match.")
                                break

                            json_str = self._extract_json_from_string(message)
                            if json_str:
                                chunk = json.loads(json_str)
                                
                                if getattr(self, 'stop_parser', None):
                                    stop_match = self.stop_parser.find(chunk)
                                    if stop_match and str(stop_match[0].value) == getattr(self.config.response_format, 'stop_value', None):
                                        logger.debug("Websocket receive stopped by strict stop_field match.")
                                        break

                                match = self.answer_parser.find(chunk)
                                if match:
                                    if not self.config.response_format.stream:
                                        answer_text = match[0].value
                                        cit_match = self.citations_parser.find(chunk)
                                        if cit_match and isinstance(cit_match[0].value, list):
                                            citations.extend(cit_match[0].value)
                                        raw_response = chunk
                                        break
                                    else:
                                        answer_text += match[0].value
                                        cit_match = self.citations_parser.find(chunk)
                                        if cit_match and isinstance(cit_match[0].value, list):
                                            citations.extend(cit_match[0].value)
                                        if not isinstance(raw_response, list):
                                            raw_response = []
                                        raw_response.append(chunk)
                        except asyncio.TimeoutError:
                            break
                        except websockets.exceptions.ConnectionClosed:
                            logger.debug("Websocket connection closed by server")
                            break
                        except Exception as e:
                            logger.error(f"Error processing websocket message: {e}")
                            break # Break on unexpected errors to prevent infinite loops
                    
                    # Wait at most 30 seconds for the answer to fully stream if streaming
                    # Wait wait, the timeout inside wait_for handles the idle time.
                    # But if we receive a constant stream of garbage, it could loop forever.
                    # We will rely on ConnectionClosed to break the loop naturally if the server finishes.
                    return {
                        "answer": answer_text,
                        "citations": citations,
                        "raw": raw_response
                    }
            elif rec_method.upper() == "GET":
                import asyncio
                logger.debug(f"Sending query to {url}: {query}")
                response = await self.client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                
                for _ in range(30):
                    await asyncio.sleep(1.0)
                    resp = await self.client.request(rec_method, rec_url, headers=rec_headers, **rec_kwargs)
                    if resp.status_code == 200:
                        data = resp.json()
                        match = self.answer_parser.find(data)
                        if match:
                            answer_text = match[0].value
                            citations = []
                            cit_match = self.citations_parser.find(data)
                            if cit_match and isinstance(cit_match[0].value, list):
                                citations.extend(cit_match[0].value)
                            return {
                                "answer": answer_text,
                                "citations": citations,
                                "raw": data
                            }
                return {"answer": "", "citations": [], "raw": {}}
                
        # Fallback to normal synchronous / SSE processing if receive is not configured
        logger.debug(f"Sending query to {url}: {query}")
        
        if self.config.response_format.stream:
            answer_text = ""
            citations = []
            raw_response = {}
            
            async with self.client.stream(method, url, headers=headers, **kwargs) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                        
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                    elif line.startswith("data "):
                        data_str = line[5:].strip()
                    elif line.startswith("id:") or line.startswith("event:") or line.startswith("retry:"):
                        continue
                    else:
                        data_str = line

                    if data_str == "[DONE]":
                        break
                        
                    if getattr(self.config.response_format, 'stop_payload_match', None) and self.config.response_format.stop_payload_match in data_str:
                        logger.debug("HTTP stream stopped by lazy stop_payload_match.")
                        break
                    
                    if data_str:
                        try:
                            import json
                            json_str = self._extract_json_from_string(data_str)
                            if json_str:
                                chunk = json.loads(json_str)
                            else:
                                chunk = json.loads(data_str)
                                
                            if getattr(self, 'stop_parser', None):
                                stop_match = self.stop_parser.find(chunk)
                                if stop_match and str(stop_match[0].value) == getattr(self.config.response_format, 'stop_value', None):
                                    logger.debug("HTTP stream stopped by strict stop_field match.")
                                    break
                                
                            match = self.answer_parser.find(chunk)
                            if match:
                                answer_text += match[0].value
                            
                            cit_match = self.citations_parser.find(chunk)
                            if cit_match and isinstance(cit_match[0].value, list):
                                citations.extend(cit_match[0].value)
                            if not isinstance(raw_response, list):
                                raw_response = []
                            raw_response.append(chunk)
                        except Exception:
                            pass
            return {
                "answer": answer_text,
                "citations": citations,
                "raw": raw_response
            }
        else:
            response = await self.client.request(method, url, headers=headers, **kwargs)
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
