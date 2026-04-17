# LADA Integration Examples

This document provides examples for integrating with LADA's new OpenClaw-parity modules.

## Table of Contents

1. [Gateway Protocol](#gateway-protocol)
2. [Agent Runtime](#agent-runtime)
3. [Task Registry](#task-registry)
4. [Approval Engine](#approval-engine)
5. [Doctor Module](#doctor-module)
6. [Plugin Governance](#plugin-governance)
7. [Subagents](#subagents)
8. [ACP Bridge](#acp-bridge)

---

## Gateway Protocol

The Gateway Protocol provides structured WebSocket communication with role-based scopes.

### Python Client Example

```python
import asyncio
import websockets
import json

async def connect_to_lada():
    uri = "ws://localhost:5000/ws"
    
    async with websockets.connect(uri) as ws:
        # Protocol handshake
        handshake = {
            "type": "protocol_handshake",
            "data": {
                "version": "1.0",
                "role": "operator",  # or "node"
                "scopes": ["chat", "system", "tasks"],
                "capabilities": ["streaming", "tools"]
            }
        }
        await ws.send(json.dumps(handshake))
        
        # Wait for handshake response
        response = await ws.recv()
        print(f"Handshake: {response}")
        
        # Send a chat message
        message = {
            "type": "chat",
            "id": "msg-001",
            "data": {
                "content": "Hello LADA!",
                "stream": True
            }
        }
        await ws.send(json.dumps(message))
        
        # Receive streaming response
        async for chunk in ws:
            data = json.loads(chunk)
            if data["type"] == "stream_end":
                break
            print(data["data"].get("content", ""), end="")

asyncio.run(connect_to_lada())
```

### Available Scopes

| Scope | Description |
|-------|-------------|
| `chat` | Send/receive chat messages |
| `system` | System commands (volume, brightness, etc.) |
| `tasks` | Task registry operations |
| `approve` | Approval queue management |
| `config` | Configuration changes |
| `plugins` | Plugin management |
| `agents` | Agent registry |
| `admin` | Administrative operations |
| `audit` | Audit log access |

---

## Agent Runtime

Register and manage isolated agent contexts.

### Register a Custom Agent

```python
from modules.agent_runtime import get_agent_registry, AgentCapabilities

registry = get_agent_registry()

# Register a research agent with limited capabilities
capabilities = AgentCapabilities(
    allowed_skills={"web_search", "summarize", "read_file"},
    denied_skills={"delete_file", "execute_code"},
    max_tokens=8000,
)

agent = registry.register(
    agent_id="research-agent",
    name="Research Assistant",
    capabilities=capabilities,
)

print(f"Registered: {agent.agent_id}")
```

### Check Agent Permissions

```python
from modules.agent_runtime import get_agent_registry

registry = get_agent_registry()

# Check if an agent can use a skill
can_search = registry.can_use_skill("research-agent", "web_search")
print(f"Can search: {can_search}")  # True

can_delete = registry.can_use_skill("research-agent", "delete_file")
print(f"Can delete: {can_delete}")  # False (denied)
```

---

## Task Registry

Create, track, and manage long-running tasks.

### Create and Track a Task

```python
from modules.tasks import get_task_registry, TaskState

registry = get_task_registry()

# Create a new task
task = registry.create(
    task_type="research",
    params={"topic": "quantum computing", "depth": "comprehensive"},
    agent_id="research-agent",
)

print(f"Task created: {task.task_id}, State: {task.state}")

# Update task state
registry.update_state(task.task_id, TaskState.RUNNING)

# Complete with result
registry.complete(
    task.task_id,
    result={"summary": "...", "sources": [...]}
)
```

### Resume an Interrupted Task

```python
from modules.tasks import get_task_registry

registry = get_task_registry()

# Get resume token for a paused task
token_info = registry.create_resume_token(task_id)
print(f"Resume token: {token_info['token']}")

# Later, resume the task
result = registry.resume(token_info['token'])
if result['success']:
    print("Task resumed!")
```

---

## Approval Engine

Request and process approvals for sensitive actions.

### Check Action Approval

```python
from modules.approval import check_and_request_approval, ActionSeverity

# Check if an action needs approval
result = check_and_request_approval(
    action="delete_files",
    command="rm -rf /tmp/cache/*",
    params={"path": "/tmp/cache"},
    agent_id="cleanup-agent",
)

if result["allowed"]:
    print("Action approved, proceeding...")
elif result["pending"]:
    print(f"Waiting for approval: {result['request_id']}")
else:
    print(f"Action denied: {result['reason']}")
```

### Approve a Pending Request

```python
from modules.approval import get_approval_queue

queue = get_approval_queue()

# List pending approvals
pending = queue.list_pending()
for req in pending:
    print(f"{req.request_id}: {req.action} by {req.agent_id}")

# Approve a request
queue.approve(
    request_id="apr_abc123",
    approver_id="admin",
    note="Verified safe to proceed"
)
```

### Using the Decorator

```python
from modules.approval import require_approval

@require_approval(action="critical_operation", severity="dangerous")
async def delete_user_data(user_id: str):
    """This function requires approval before executing."""
    # ... deletion logic ...
    return {"deleted": user_id}

# When called, will check approval before executing
result = await delete_user_data("user-123")
```

---

## Doctor Module

Run diagnostics and auto-fix issues.

### Run Diagnostics

```python
from modules.doctor import DiagnosticsRunner

runner = DiagnosticsRunner()
report = runner.run_all()

print(f"Status: {'HEALTHY' if report.failed == 0 else 'UNHEALTHY'}")
print(f"Passed: {report.passed}/{report.total_checks}")

for result in report.results:
    if not result.passed:
        print(f"❌ {result.name}: {result.message}")
        if result.fixable:
            print(f"   Fix available: {result.fix_id}")
```

### Apply Auto-Fixes

```python
from modules.doctor import AutoFixEngine

engine = AutoFixEngine()

# List available fixes
fixes = engine.list_fixes()
for fix in fixes:
    print(f"{fix.fix_id}: {fix.description}")

# Execute a specific fix
result = engine.execute("fix_missing_config")
if result.success:
    print("Fix applied successfully!")
else:
    print(f"Fix failed: {result.error}")
```

### Register Custom Health Check

```python
from modules.doctor import get_health_registry, Diagnostic

def check_custom_service():
    """Check if our custom service is running."""
    try:
        # Check service health
        import requests
        resp = requests.get("http://localhost:8080/health", timeout=5)
        return resp.status_code == 200, "Service healthy", {}
    except Exception as e:
        return False, f"Service unhealthy: {e}", {"error": str(e)}

registry = get_health_registry()
registry.register(Diagnostic(
    id="custom_service",
    name="Custom Service Health",
    category="services",
    check_fn=check_custom_service,
    fix_id="restart_custom_service",  # Optional
))
```

---

## Plugin Governance

Manage plugin trust, security scanning, and policies.

### Scan a Plugin

```python
from modules.plugins.scanner import get_plugin_scanner

scanner = get_plugin_scanner()

# Scan a plugin directory
result = scanner.scan("plugins/my_plugin")

print(f"Passed: {result.passed}")
print(f"Risk Level: {result.risk_level}")
print(f"Findings: {len(result.findings)}")

for finding in result.findings:
    print(f"  [{finding.severity}] {finding.message}")
```

### Manage Plugin Trust

```python
from modules.plugins.trust import get_trust_registry, TrustLevel

registry = get_trust_registry()

# Set trust level for a plugin
registry.set_trust_level("my-plugin", TrustLevel.VERIFIED)

# Get plugin trust info
entry = registry.get("my-plugin")
print(f"Trust: {entry.trust_level}, Source: {entry.source}")
```

### Configure Plugin Policy

```python
from modules.plugins.policy import get_policy_engine, PolicyMode

engine = get_policy_engine()

# Block all untrusted plugins
engine.set_global_settings(block_untrusted=True)

# Set default policy mode
engine.set_mode(PolicyMode.DENY_ALL)

# Allow specific plugin
engine.add_to_allowlist("trusted-plugin-id")

# Check permission
decision = engine.evaluate(
    plugin_id="some-plugin",
    trust_level=TrustLevel.COMMUNITY,
)
print(f"Allowed: {decision.allowed}, Reason: {decision.reason}")
```

---

## Subagents

Spawn and manage child agents for parallel work.

### Spawn a Subagent

```python
from modules.subagents import get_subagent_runtime, SubagentConfig

runtime = get_subagent_runtime()

# Spawn a research subagent
config = SubagentConfig(
    agent_type="research",
    task_description="Research climate change impacts on agriculture",
    timeout_seconds=300,
    max_tokens=4096,
)

subagent_id = runtime.spawn(config)
print(f"Spawned: {subagent_id}")

# Wait for completion
result = runtime.wait(subagent_id, timeout=60)
if result and result.success:
    print(f"Result: {result.output}")
```

### Manage Subagent Hierarchy

```python
from modules.subagents import get_subagent_runtime

runtime = get_subagent_runtime()

# Spawn parent agent
parent_id = runtime.spawn(SubagentConfig(
    agent_type="coordinator",
    task_description="Coordinate research team",
))

# Spawn child agents under parent
child1_id = runtime.spawn(SubagentConfig(
    agent_type="researcher",
    task_description="Research topic A",
    parent_id=parent_id,
))

child2_id = runtime.spawn(SubagentConfig(
    agent_type="researcher",
    task_description="Research topic B",
    parent_id=parent_id,
))

# Get hierarchy tree
tree = runtime.get_tree(parent_id)
print(f"Tree: {tree}")

# Cancel parent (cancels children too)
runtime.cancel(parent_id)
```

---

## ACP Bridge

Connect IDEs and external tools via the Agent Communication Protocol.

### WebSocket Client (IDE Integration)

```python
import asyncio
import websockets
import json

async def acp_client():
    uri = "ws://localhost:5000/acp"
    
    async with websockets.connect(uri) as ws:
        # Initialize session
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session/init",
            "params": {
                "client_name": "MyIDE",
                "client_version": "1.0.0"
            }
        }
        await ws.send(json.dumps(request))
        response = json.loads(await ws.recv())
        session_id = response["result"]["session_id"]
        print(f"Session: {session_id}")
        
        # Set context (current file, project info)
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "context/set",
            "params": {
                "current_file": "src/main.py",
                "project_root": "/home/user/myproject",
                "language": "python"
            }
        }))
        await ws.recv()
        
        # Chat completion
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "chat/complete",
            "params": {
                "messages": [
                    {"role": "user", "content": "Explain this code"}
                ]
            }
        }))
        
        response = json.loads(await ws.recv())
        print(f"Response: {response['result']['content']}")
        
        # List available tools
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tool/list",
            "params": {}
        }))
        
        tools = json.loads(await ws.recv())
        print(f"Available tools: {[t['name'] for t in tools['result']['tools']]}")

asyncio.run(acp_client())
```

### Available ACP Methods

| Method | Description |
|--------|-------------|
| `session/init` | Initialize ACP session |
| `session/status` | Get session status |
| `context/set` | Set context (file, project) |
| `context/get` | Get current context |
| `context/clear` | Clear context |
| `chat/complete` | Send chat completion request |
| `tool/list` | List available tools |
| `tool/invoke` | Invoke a tool |

---

## API Endpoints Summary

### Plugin Governance

```bash
# List trust entries
GET /plugins/trust

# Get specific plugin trust
GET /plugins/trust/{plugin_id}

# Update plugin trust
POST /plugins/trust/{plugin_id}
{"trust_level": "verified"}

# Scan plugin
POST /plugins/scan/{plugin_id}

# Get scan history
GET /plugins/scan/findings

# Get policy
GET /plugins/policy

# Check policy
POST /plugins/policy/check
{"plugin_id": "...", "action": "..."}

# Add to allowlist/denylist
POST /plugins/policy/allow
POST /plugins/policy/deny
```

### Subagents

```bash
# List subagents
GET /subagents

# Spawn subagent
POST /subagents
{"name": "researcher", "context": {...}}

# Get subagent
GET /subagents/{agent_id}

# Cancel subagent
DELETE /subagents/{agent_id}

# Send message to subagent
POST /subagents/{agent_id}/message
{"message": "..."}

# Get limits
GET /subagents/limits
```

---

## CLI Commands

```bash
# Run doctor diagnostics
python main.py doctor run

# List available health checks
python main.py doctor list

# Run specific health check
python main.py doctor health <check_id>

# Apply auto-fix
python main.py doctor fix <fix_id>

# Scan plugins for security issues
python main.py scan [plugin_id]
```

---

## Environment Variables

```bash
# Gateway Protocol
LADA_WS_PROTOCOL_ENABLED=1
LADA_WS_HANDSHAKE_TIMEOUT=10
LADA_WS_REQUIRE_IDEMPOTENCY=0

# Agent Runtime
LADA_AGENTS_DIR=config/agents
LADA_AGENT_BINDINGS_FILE=config/agent_bindings.json

# Task Registry
LADA_TASKS_DIR=data/tasks
LADA_FLOWS_DIR=config/flows

# Approval Engine
LADA_POLICIES_DIR=config/policies
LADA_APPROVALS_DIR=data/approvals

# Doctor Module
LADA_DOCTOR_REPORTS_DIR=data/doctor
LADA_FIX_HISTORY_DIR=data/fixes

# Plugin Governance
LADA_PLUGIN_TRUST_DIR=config/plugin_trust
LADA_PLUGIN_POLICY_FILE=config/plugin_policy.json

# Subagents
LADA_SUBAGENT_MAX_DEPTH=5
LADA_SUBAGENT_MAX_CONCURRENT=10
LADA_SUBAGENT_MAX_TOTAL=50

# ACP Bridge
LADA_ACP_SESSION_TTL=3600
LADA_ACP_MAX_SESSIONS=100
```

---

## Testing

Run all new module tests:

```bash
# All new modules
python -m pytest tests/test_gateway_protocol.py tests/test_agent_runtime.py \
  tests/test_task_registry.py tests/test_approval.py tests/test_doctor.py \
  tests/test_plugin_governance.py tests/test_subagents_acp.py -v -o "addopts="

# Specific module
python -m pytest tests/test_approval.py -v -o "addopts="
```
