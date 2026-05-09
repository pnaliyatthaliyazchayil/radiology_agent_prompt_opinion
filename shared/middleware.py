"""
ApiKeyMiddleware — validates X-API-Key on every POST and bridges A2A message
metadata into params.metadata so the FHIR hook can read it.

Mirrors the pattern from po-adk-python/shared/middleware.py.
"""

from __future__ import annotations

import json
import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

AGENT_CARD_PATH = "/.well-known/agent-card.json"

logger = logging.getLogger(__name__)

# Override in production via env vars or a secrets manager
VALID_API_KEYS: set[str] = {
    k for k in [
        os.getenv("CRITCOM_API_KEY", "dev-key-please-change"),
        os.getenv("CRITCOM_API_KEY_SECONDARY"),
    ]
    if k
}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, require_api_key: bool = True) -> None:
        super().__init__(app)
        self.require_api_key = require_api_key

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Always allow agent-card.json
        if request.url.path.endswith(AGENT_CARD_PATH):
            return await call_next(request)

        if request.method != "POST":
            return await call_next(request)

        if self.require_api_key:
            provided = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
            if not provided:
                logger.warning("security_rejected_missing_api_key path=%s", request.url.path)
                return JSONResponse({"error": "X-API-Key header required"}, status_code=401)
            if provided not in VALID_API_KEYS:
                logger.warning("security_rejected_invalid_api_key path=%s", request.url.path)
                return JSONResponse({"error": "Invalid API key"}, status_code=403)

        # Bridge metadata: copy params.message.metadata → params.metadata so the
        # ADK before_model_callback can find it via session/invocation context.
        try:
            body_bytes = await request.body()
            if body_bytes:
                body = json.loads(body_bytes)
                params = body.get("params") or {}
                msg = params.get("message") or {}
                meta = msg.get("metadata")
                if meta and "metadata" not in params:
                    params["metadata"] = meta
                    body["params"] = params
                    new_bytes = json.dumps(body).encode()
                    # Replace the body in the receive callable
                    async def receive():
                        return {"type": "http.request", "body": new_bytes, "more_body": False}
                    request._receive = receive  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug("middleware_metadata_bridge_skipped error=%s", e)

        return await call_next(request)


class AgentCardPatchMiddleware(BaseHTTPMiddleware):
    """Inject `supportedInterfaces` and `extensions` into the agent card.

    Why: Prompt Opinion's A2A parser requires `supportedInterfaces`, and PO
    only injects FHIR context for agents that declare the FHIR extension URI.
    google-adk's AgentCard builder doesn't emit either, so we patch them in.
    """

    def __init__(self, app, fhir_extension_uri: str | None = None) -> None:
        super().__init__(app)
        self.fhir_extension_uri = fhir_extension_uri

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if not (request.method == "GET" and request.url.path.endswith(AGENT_CARD_PATH)):
            return await call_next(request)

        response = await call_next(request)
        if response.status_code != 200:
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            card = json.loads(body)
        except json.JSONDecodeError:
            return Response(
                content=body,
                status_code=response.status_code,
                headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
                media_type=response.media_type,
            )

        protocol_version = card.get("protocolVersion") or "0.3.0"

        def _enrich(iface: dict[str, str]) -> dict[str, str]:
            transport = iface.get("transport") or "JSONRPC"
            return {
                "url": iface["url"],
                "transport": transport,
                "protocolBinding": iface.get("protocolBinding") or transport,
                "protocolVersion": iface.get("protocolVersion") or protocol_version,
            }

        if "supportedInterfaces" not in card:
            interfaces: list[dict[str, str]] = []
            primary_url = card.get("url")
            primary_transport = card.get("preferredTransport") or "JSONRPC"
            if primary_url:
                interfaces.append({"url": primary_url, "transport": primary_transport})
            for extra in card.get("additionalInterfaces") or []:
                interfaces.append(extra)
            card["supportedInterfaces"] = [_enrich(i) for i in interfaces]
        else:
            card["supportedInterfaces"] = [_enrich(i) for i in card["supportedInterfaces"]]

        if self.fhir_extension_uri:
            capabilities = card.get("capabilities") or {}
            existing = capabilities.get("extensions") or []
            if not any(e.get("uri") == self.fhir_extension_uri for e in existing):
                existing.append({
                    "uri": self.fhir_extension_uri,
                    "required": True,
                    "description": "Prompt Opinion FHIR context: receives patient FHIR base URL + bearer token at runtime.",
                })
                capabilities["extensions"] = existing
                card["capabilities"] = capabilities
            # Drop the (incorrect) top-level extensions array if any prior version wrote one
            card.pop("extensions", None)

        new_body = json.dumps(card).encode()
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(
            content=new_body,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )
