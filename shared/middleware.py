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

# Some clients (Prompt Opinion included) still send the legacy camelCase
# A2A method names. The current spec — and google-adk's JSON-RPC dispatcher —
# only knows the slash-style names, so we translate at the edge.
METHOD_ALIASES: dict[str, str] = {
    "SendMessage": "message/send",
    "SendStreamingMessage": "message/stream",
    "GetTask": "tasks/get",
    "CancelTask": "tasks/cancel",
    "SetTaskPushNotificationConfig": "tasks/pushNotificationConfig/set",
    "GetTaskPushNotificationConfig": "tasks/pushNotificationConfig/get",
    "TaskResubscription": "tasks/resubscribe",
}


class RootGetServesCardMiddleware:
    """Pure-ASGI middleware: rewrite GET / to GET /.well-known/agent-card.json.

    Why: A2A's transport is JSON-RPC (POST) at the root URL, so the agent's
    root has no GET handler and returns 405. Some clients (Prompt Opinion
    included) probe the URL with GET first. Rewriting the path makes the
    agent card serve as the response, satisfying both probes and discovery.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope.get("type") == "http"
            and scope.get("method") == "GET"
            and scope.get("path") in ("/", "")
        ):
            scope = {
                **scope,
                "path": AGENT_CARD_PATH,
                "raw_path": AGENT_CARD_PATH.encode(),
            }
        await self.app(scope, receive, send)

logger = logging.getLogger(__name__)

# Override in production via env vars or a secrets manager
VALID_API_KEYS: set[str] = {
    k for k in [
        os.getenv("CRITCOM_API_KEY", "dev-key-please-change"),
        os.getenv("CRITCOM_API_KEY_SECONDARY"),
    ]
    if k
}


class ApiKeyMiddleware:
    """Pure-ASGI middleware. Validates X-API-Key, translates legacy A2A method
    names to canonical slash form, bridges message.metadata into params.metadata,
    and replays the (possibly modified) body downstream.

    Pure ASGI is required because Starlette's BaseHTTPMiddleware does not
    propagate body modifications through call_next — the downstream handler
    reads the original ASGI receive stream, not a patched request object.
    """

    def __init__(self, app, require_api_key: bool = True) -> None:
        self.app = app
        self.require_api_key = require_api_key

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        method = scope.get("method")

        if path.endswith(AGENT_CARD_PATH) or method != "POST":
            await self.app(scope, receive, send)
            return

        if self.require_api_key:
            headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
            provided = headers.get(b"x-api-key", b"").decode("latin-1") or None
            if not provided:
                logger.warning("security_rejected_missing_api_key path=%s", path)
                await _send_json(send, 401, {"error": "X-API-Key header required"})
                return
            if provided not in VALID_API_KEYS:
                logger.warning("security_rejected_invalid_api_key path=%s", path)
                await _send_json(send, 403, {"error": "Invalid API key"})
                return

        # Buffer body
        body_chunks: list[bytes] = []
        more_body = True
        while more_body:
            msg = await receive()
            if msg["type"] != "http.request":
                # disconnect or other — pass through with empty body
                more_body = False
                break
            body_chunks.append(msg.get("body") or b"")
            more_body = msg.get("more_body", False)
        body_bytes = b"".join(body_chunks)

        # Parse, log, translate method, bridge metadata
        new_body = body_bytes
        try:
            if body_bytes:
                data = json.loads(body_bytes)
                if isinstance(data, dict):
                    rpc_method = data.get("method")
                    params = data.get("params") or {}
                    rpc_msg = params.get("message") or {}
                    logger.info(
                        "incoming_a2a method=%s id=%s msg_keys=%s param_keys=%s metadata_keys=%s",
                        rpc_method,
                        data.get("id"),
                        sorted(rpc_msg.keys()) if isinstance(rpc_msg, dict) else None,
                        sorted(params.keys()) if isinstance(params, dict) else None,
                        sorted((rpc_msg.get("metadata") or {}).keys()) if isinstance(rpc_msg.get("metadata"), dict) else None,
                    )
                    if rpc_method in METHOD_ALIASES:
                        canonical = METHOD_ALIASES[rpc_method]
                        logger.info("translated_method legacy=%s canonical=%s", rpc_method, canonical)
                        data["method"] = canonical
                        # Temporary: dump full incoming body so we can diff
                        # against the validator's expectations.
                        logger.info("incoming_body_full=%s", body_bytes[:2000].decode("utf-8", errors="replace"))
                    meta = rpc_msg.get("metadata") if isinstance(rpc_msg, dict) else None
                    if meta and isinstance(params, dict) and "metadata" not in params:
                        params["metadata"] = meta
                        data["params"] = params
                    new_body = json.dumps(data).encode()
        except Exception as e:
            logger.warning("middleware_body_parse_skipped error=%s", e)

        # Replay body downstream
        sent = False

        async def new_receive():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": new_body, "more_body": False}

        await self.app(scope, new_receive, send)


async def _send_json(send, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    })
    await send({"type": "http.response.body", "body": body, "more_body": False})


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
