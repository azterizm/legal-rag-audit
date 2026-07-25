# Legal RAG Audit

An open-source, deterministic, endpoint-based evaluation tool that tests legal RAG systems for retrieval integrity, hallucination rates, and compliance readiness against enterprise procurement standards (TPRM).

It is **NOT** an agentic browser crawler. It consumes API endpoints, runs a fixed suite of tests against them, and outputs a structured JSON report with pass/fail verdicts and a hallucination rate percentage.

## Why This Exists

Enterprise legal buyers don't just want "good" AI; they need provable compliance and measured risk. 
This tool helps you quantify retrieval integrity and identify exact failure modes in retrieval pipelines (not just "it hallucinates sometimes").

It tests for:
- Hallucination Rates (Mapping factual claims to sources)
- Citation Integrity (No phantom sources)
- Prompt Injection Resistance
- Cross-Tenant Data Leakage (For multi-tenant setups)
- Retrieval Relevance
- Latency Penalties, Disambiguation, and more.

## Installation

```bash
pip install -e .
```

Or run via Docker (recommended for CI/CD and DevOps teams).

## Configuration & Setup Guide

To get accurate, deterministic results and avoid false positives, you must correctly map the audit tool to your RAG system's exact API shape using `config.yaml`.

### 1. The Configuration File (`config.yaml`)

Create a `config.yaml` in your project root. Here is a robust example:

```yaml
target:
  name: "lexcorp-staging" # Give your test run a descriptive name
  endpoints:
    chat: "https://staging.lexcorp.example.com/api/v1/chat"
    upload: "https://staging.lexcorp.example.com/api/v1/documents"
    retrieval: "https://staging.lexcorp.example.com/api/v1/search" # Optional
  auth:
    type: "bearer" # Options: bearer | api_key | basic | none
    token_env: "TARGET_API_KEY" # Tool reads the actual token securely from this env var
  response_format:
    # CRITICAL: Define the exact JSONPath to the answer string and citation array in your API's response.
    # Incorrect JSONPaths are the #1 cause of false positives (e.g., evaluating an empty string as a hallucination).
    answer_field: "response.text" 
    citations_field: "response.sources"
    stream: false # Set to true if your chat endpoint uses Server-Sent Events (SSE)

corpus:
  # The test documents used for the evaluation.
  use_bundled: true # True to use our curated 13-document suite of adversarial legal texts
  # OR provide a path to your own custom directory of texts
  # path: "./my_test_documents/"

tests:
  hallucination_rate: true
  citation_integrity: true
  retrieval_relevance: true
  injection_resistance: true
  cross_tenant_leakage: false # Set to true only if multi_tenant config is provided
  confidence_threshold: true

thresholds:
  max_hallucination_rate: 0.02 # Maximum acceptable hallucination rate (2%)
  min_retrieval_relevance: 0.85 # Minimum cosine similarity for retrieved chunks
  max_injection_success_rate: 0.0 
  max_cross_tenant_leaks: 0
```

#### API Endpoints Explained

To ensure the audit tool interfaces correctly with your RAG system, you must configure the following endpoints in your `config.yaml`. The tool expects your API to accept standard `POST` requests with JSON payloads.

1. **`chat` (Required)**: 
   - **What it is**: The primary endpoint for sending user queries to your RAG system and receiving generated answers.
   - **Expected Request**: A `POST` request with a JSON body containing the query.
   - **Expected Response**: A JSON object containing the final answer string and an array of citations. The tool uses `response_format.answer_field` and `response_format.citations_field` from your config to extract these.

2. **`upload` (Required if uploading a corpus)**: 
   - **What it is**: The endpoint used to ingest raw text or documents into your RAG system's knowledge base prior to testing.
   - **Expected Request**: A `POST` request containing the document content and metadata. The tool currently sends `{"filename": "...", "content": "..."}`.
   - **Expected Response**: A JSON object acknowledging the upload. The tool captures the `id` from the response (if available) to verify citations later.

3. **`retrieval` (Optional)**: 
   - **What it is**: A direct endpoint to your vector database or search index. If provided, the tool tests the raw retrieval relevance before generation.
   - **Expected Request**: A `POST` request with the search query.
   - **Expected Response**: A JSON object containing an array of retrieved text chunks. The tool computes cosine similarity against these raw chunks to grade retrieval performance independently of the LLM.

#### Advanced Endpoint Configuration

If your API requires specific HTTP methods, custom headers, or a deeply nested JSON body structure (or stringified JSON), you can configure endpoints as objects rather than simple strings. 

You can also configure a **`receive`** endpoint if your RAG system uses decoupled asynchronous responses (e.g., polling GET endpoints or WebSockets). When configured, the tool will trigger the generation on the `chat` endpoint and automatically listen for the response on the `receive` endpoint.

Use the `{{QUERY}}` variable in the `body` field. The tool will inject the query at runtime. (For upload endpoints, use `{{FILENAME}}` and `{{CONTENT}}`).

```yaml
target:
  endpoints:
    chat:
      url: "https://app.lexcorp.example.com/v1/api_core/widget/send_message/?language=en"
      method: "POST"
      headers:
        accept: "application/json, text/plain, */*"
        conv-id: "bd208096-772e-40a7-bcde-702ad8bdebfc"
        scenario-id: "hhh0h4uuiy"
        x-api-key: "hhh0h4uuiy"
      # If your body must be a JSON string, you can provide it as a string:
      body: '{"content":"{{QUERY}}","is_voice":false,"client_message_id":"f9517177-f80c","client_metadata":{"chat_page_access_token":"eyJhbGciOiJIUzI1NiIsIn...","language":"en"}}'
      
    receive:
      # Automatically detected as a WebSocket connection
      url: "wss://app.lexcorp.example.com/socket.io/?EIO=4&transport=websocket"
      headers:
        accept-language: "en-GB,en-US;q=0.9,en;q=0.8"
        cache-control: "no-cache"
      # (Optional) Send a specific connection initiation packet upon connecting to the WebSocket.
      # You can provide a string (e.g., "40" for Socket.IO) or a JSON object. Variables like {{UUID}} are supported.
      init_message: "40"
  
  response_format:
    # Use jsonpath-ng syntax to filter specific WS events for the AI's final answer
    answer_field: "$[?(@.event_type=='message' & @.data.author.type=='ai_assistant')].data.content"
    stream: true # Keep the connection open to aggregate chunks if the WS streams chunks
    # (Optional) Stop stream immediately if payload contains this substring (Lazy match)
    stop_payload_match: "MESSAGE_END"
    # (Optional) Stop stream if JSONPath strictly matches this value
    # stop_field: "message.type"
    # stop_value: "finish"
```

### 2. Setting up the Corpus

**Bundled Corpus (Recommended):**
Set `use_bundled: true` in your `config.yaml`. The tool ships with a highly curated suite of 13 synthetic legal documents explicitly designed to trigger failure modes (e.g., highly contradictory SaaS agreements, overlapping statutes, and prompt injection traps).

**Custom Corpus:**
If you set `use_bundled: false`, you must provide a `path:` to a directory of text/markdown files.
- The tool will upload these documents and use their raw text as the source of truth.
- **Tip to avoid false positives:** Ensure the documents in your custom directory are clean and accurately reflect the expected facts you are testing for, as the Hallucination Evaluator computes semantic similarity directly against these files.

### 3. Execution

Set your environment variables and run the tool:
```bash
export TARGET_API_KEY="your-api-token"
legal-rag-audit -c config.yaml -o output_report
```
3. Check `output_report.json` or `output_report.md` for the detailed results.

## Zero Data Exfiltration

**Zero data exfiltration.** The tool sends test documents to the target and reads responses. It does not phone home, collect telemetry, or transmit any data externally. It operates locally or within your containerised environment.

## Deterministic Evaluation

The evaluation suite uses deterministic checks (exact string matching, semantic similarity via bundled embedding models), rather than relying on an LLM-in-the-loop to ask "is this a hallucination?", which itself can be flawed.

## Output Example

The tool outputs a structured JSON report and a markdown summary.

# Roadmap

- [ ] Add support for third party LLMs (e.g., OpenAI, Gemini)
