# CritCom — Prompt Opinion Challenge Build

Critical results communication agent for radiology, built for the **Prompt Opinion Agent Assemble Challenge**.

This is a **FHIR-only** build — the DICOM worklist path from the full repo has been removed for this deployment.

---

## What it does

When a radiologist signs a report with a critical finding, CritCom:

1. Fetches the `DiagnosticReport` from FHIR (injected by Prompt Opinion)
2. Classifies the ACR category (Cat1 / Cat2 / Cat3) — using the FHIR tag if present, or LLM inference if not
3. Resolves the ordering physician's contact details from the `ServiceRequest`
4. Creates a FHIR `Communication` recording the notification
5. Opens a FHIR `Task` to track acknowledgment (60 min for Cat1, 24 h for Cat2)
6. Escalates to on-call coverage if the acknowledgment window expires

---

## Setup

### 1. Deploy the agent

**Option A — Render (recommended for Prompt Opinion)**

1. Push this repo to GitHub
2. Create a new **Web Service** on [render.com](https://render.com)
3. Set runtime to **Docker** (uses the `Dockerfile`)
4. Add the environment variables below

**Option B — Local**

```bash
pip install -r requirements.txt
pip install -e .          # installs src/critcom as a package
cp .env.example .env      # fill in GOOGLE_API_KEY and CRITCOM_API_KEY
uvicorn critcom_agent.app:a2a_app --host 0.0.0.0 --port 8001
```

### 2. Environment variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | ✅ | Google AI Studio key (gemini-2.0-flash) |
| `CRITCOM_API_KEY` | ✅ | API key Prompt Opinion will send in `X-API-Key` |
| `CRITCOM_AGENT_URL` | ✅ | Public URL of this deployment |
| `CRITCOM_LLM_MODEL` | optional | Default: `gemini-2.0-flash` |
| `CRITCOM_REQUIRE_API_KEY` | optional | Default: `true` |
| `CRITCOM_FHIR_BASE_URL` | local only | Default: `http://localhost:8080/fhir` |

For local FHIR testing, set `CRITCOM_FHIR_BASE_URL` and optionally `CRITCOM_FHIR_BEARER_TOKEN`.
In Prompt Opinion, FHIR credentials are injected automatically at runtime.

### 3. Register on Prompt Opinion

1. Go to **app.promptopinion.ai** → **Agents** → **Build your own**
2. Create a new agent, set type to **A2A**
3. Paste your public URL (e.g. `https://critcom.onrender.com`)
4. Enter `CRITCOM_API_KEY` value as the API key
5. **Enable FHIR context** so the agent receives patient FHIR credentials
6. Set the skill to `process_critical_finding`

---

## Agent card

After deployment, verify the agent card is reachable:

```
GET https://your-app.onrender.com/.well-known/agent-card.json
```

---

## Tools (FHIR-only)

| Tool | Description |
|---|---|
| `fetch_report_fhir_tool` | Fetch a signed DiagnosticReport; falls back to LLM classification if no ACR tag |
| `resolve_provider_tool` | Walk ServiceRequest → Practitioner to get contact details |
| `dispatch_communication_tool` | Create a FHIR Communication resource for the notification |
| `track_acknowledgment_tool` | Create / check / mark a FHIR Task tracking provider ack |
| `escalate_tool` | Mark overdue Task failed, notify on-call, open new Task |
| `query_audit_tool` | Return full audit trail of Communications + Tasks |

---

## Testing locally with ADK

```bash
adk web .
```

Opens the ADK developer UI at `http://localhost:8000`. You can chat with the agent
and inspect tool calls without needing Prompt Opinion.
