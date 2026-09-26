---
name: databricks-unity-gateway
description: "Create, manage, query, and grant access to Unity Gateway resources. Use whenever a request requires inference on a model like claude, openai, gemini or open source or names Unity Gateway or Unity AI Gateway, including model services, MCP services, model provider services. Not for legacy workspace scoped AI Gateway configuration attached to Model Serving endpoints; use databricks-model-serving for that. Use also for migration from legacy AI Gateway to Unity Gateway"
compatibility: Requires databricks CLI (>= v1.17.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Unity Gateway

Use the parent `databricks-core` skill for CLI authentication and profile selection.

Unity Gateway provides Unity Catalog securables for governed access to AI services. The CLI
command group keeps the earlier product name: `databricks ai-gateway --help`.

## Choose the Correct Gateway

| Request | Use |
|---|---|
| Unity Gateway or Unity AI Gateway model service, MCP service, or model provider service | This skill and `databricks ai-gateway` |
| AI Gateway configuration on a Model Serving endpoint, including `put-ai-gateway` | `databricks-model-serving` and `databricks serving-endpoints` |
| Lakeflow Connect ingestion gateway | `databricks-lakeflow-connect` |

Treat **Unity AI Gateway** as an earlier name for **Unity Gateway** when the resource is a
Unity Catalog securable. Do not translate legacy Model Serving AI Gateway resources into
Unity Gateway resources unless the user explicitly requests a migration.

## Query a model

Databricks-hosted models already exist as model services in `system.ai`, e.g.
`system.ai.claude-opus-5-5` and `system.ai.gpt-6-sol`. Query them directly; do not create a
model service to call one. Create a model service only for custom routing, fallback, rate
limits, inference tables, or an external or provisioned-throughput destination. Default to
the unified Responses API with `databricks-openai`:

```python
from databricks.sdk import WorkspaceClient
from databricks_openai import DatabricksOpenAI
client = DatabricksOpenAI(workspace_client=WorkspaceClient(), use_ai_gateway=True)
response = client.responses.create(model="system.ai.claude-opus-5-5", input="What is Databricks?")
print(response.output_text)
```

Do not use `/serving-endpoints` or `databricks-<model>` endpoint names. For examples, tools,
native APIs, and provider services, read [references/querying.md](references/querying.md).

## CLI Workflow

Use the Databricks CLI for resource lifecycle and permission management. Do not substitute
direct REST calls or a Databricks SDK for those operations. Python clients are supported
for querying model and model provider services; read [Query services](references/querying.md).

An explicit request for **Unity Gateway**, **Unity AI Gateway**, or
`databricks ai-gateway` belongs to this skill. Do not switch to
`databricks-model-serving` merely because the request involves a model service or a
workspace. Use that skill only for a legacy per-endpoint AI Gateway operation or when a
provisioned-throughput destination requires Model Serving endpoint details.

1. Verify the CLI meets the minimum version:

   ```bash
   databricks --version
   ```

2. Inspect the command and the relevant operation before constructing a payload:

   ```bash
   databricks ai-gateway --help
   databricks ai-gateway <operation> --help
   ```

3. Pass create and update configuration through `--json`. Use an explicit profile when
   profile-based authentication is required:

   ```bash
   databricks ai-gateway <operation> --json @payload.json --profile <PROFILE>
   ```

Do not invent JSON fields from similarly named legacy APIs. Build the payload from the
installed CLI help and the Unity Gateway documentation for the selected service type.

## Service Types

| Service type | CLI operations |
|---|---|
| Model service | `create-model-service`, `get-model-service`, `list-model-services`, `update-model-service`, `delete-model-service`; read [Model services](references/model-services.md) |
| MCP service | `create-mcp-service`, `get-mcp-service`, `list-mcp-services`, `update-mcp-service`, `delete-mcp-service`; read [MCP services](references/mcp-services.md) |
| Model provider service | `create-model-provider-service`, `get-model-provider-service`, `list-model-provider-services`, `update-model-provider-service`, `delete-model-provider-service`; read [Model provider services](references/model-provider-services.md) |

## Querying and permissions

- Before writing Python that invokes a model or model provider service, read
  [references/querying.md](references/querying.md).
- Before checking, granting, or revoking Unity Gateway access, read
  [references/permissions.md](references/permissions.md).

Before any model-service operation, read
[references/model-services.md](references/model-services.md). It contains the current
resource-name conventions, JSON payload fields, required-input gate, and lifecycle
commands. Before any MCP-service operation, read
[references/mcp-services.md](references/mcp-services.md) for the equivalent MCP-specific
contract. Before any model-provider-service operation, read
[references/model-provider-services.md](references/model-provider-services.md). Do not
fetch public documentation for fields already covered by these references. Consult the
authoritative documentation only when a required field is absent from the reference or the
user explicitly asks for the latest documentation. Do not assign a Beta or preview status
unless the installed CLI help or current documentation explicitly does so.

## Migration from Model Serving to Unity Gateway

When migrating from workspace-scoped Model Serving endpoints to Unity Catalog-scoped Unity Gateway services, read [references/model-serving-migration.md](references/model-serving-migration.md).

## Common questions

**Can `ai_query` use a custom model service?** No. It supports Databricks-provided `system.ai` model services. Only usage tracking applies; rate limits, policies, inference tables, and fallbacks do not.

**Can I use the Anthropic SDK?** The Anthropic SDK has no Responses API, and `databricks-ai-bridge` has no Anthropic client. For [unified Responses](references/querying.md#query-a-model-service), use `DatabricksOpenAI` as in [Query a model](#query-a-model). If the Anthropic SDK is required, use the native Messages API at `<workspace-url>/ai-gateway/anthropic` with a Databricks token. This is the native Messages API, not unified Responses.

**How do I use OpenAI embeddings or image APIs?** Use an OpenAI model provider service and its native managed path for embeddings. For an unmanaged path e.g. `openai/v1/images/generations`, enable passthrough via [Model provider services](references/model-provider-services.md) and accept the reduced governance coverage.

**How do I return a tool result with unified Open Responses?** Preserve every model output item. Add the `function_call_output` with the same `call_id`, then send the complete input again. Preserve provider fields such as Gemini `encrypted_content`.

**How do I connect a coding agent?** Install the Unity Gateway CLI with `uv tool install git+https://github.com/databricks/unity-gateway`, then run `ug claude`, `ug codex`, `ug gemini`, or another supported agent. Use `ug configure`, `ug mcp add`, and `ug usage`. The old `ucode` commands remain compatible.

**How do I let Unity Gateway pick the model for each request?** Launch with `ug codex --enable-smart-routing` (or `ug claude --enable-smart-routing`) to turn on Smart Routing for sessions and subagents. This differs from weighted traffic splitting on a model service. See [Unity Gateway CLI Smart Routing](https://github.com/databricks/unity-gateway/tree/main/src/ucode/smart_routing).

**Why does a configured service fail at inference?** A model can be visible in Unity Catalog but unavailable from the workspace region. Confirm a matching service in the Unity Gateway UI and check the public model-serving availability matrix.

## Authoritative Documentation

- [Unity Gateway overview](https://docs.databricks.com/aws/en/ai-gateway/)
- [Unity Gateway release notes](https://docs.databricks.com/aws/en/release-notes/unity-gateway/)
- [Unity Gateway developer documentation](https://developers.databricks.com/docs/agents/ai-gateway)
- [Model service API reference](https://docs.databricks.com/api/ai-gateway/v1/model-service)
- [MCP service API reference](https://docs.databricks.com/api/ai-gateway/v1/mcp-service)
- [Model provider service API reference](https://docs.databricks.com/api/ai-gateway/v1/model-provider-service)
- [Query model services](https://docs.databricks.com/aws/en/ai-gateway/query-model-services)
- [Open Responses specification](https://www.openresponses.org/specification)
- [Open Responses provider behavior on Databricks](https://docs.databricks.com/aws/en/machine-learning/model-serving/query-open-responses-models)
- [Query model provider services](https://docs.databricks.com/aws/en/ai-gateway/query-model-provider-services)
- [Model service requirements and grants](https://docs.databricks.com/aws/en/ai-gateway/create-model-services)
- [Model provider service governance](https://docs.databricks.com/aws/en/ai-gateway/govern-model-provider-services)
- [Routing and fallbacks](https://docs.databricks.com/aws/en/ai-gateway/configure-traffic-splitting)
- [Rate limits](https://docs.databricks.com/aws/en/ai-gateway/rate-limits)
- [Register an external MCP server](https://docs.databricks.com/aws/en/ai-gateway/register-mcp-service)
