---
name: databricks-unity-gateway
description: "Create and manage Unity Gateway securables for governed AI access with the Databricks CLI. Use for Unity Gateway (formerly Unity AI Gateway) model services, MCP services, and model provider services. Not for legacy AI Gateway configuration attached to Model Serving endpoints; use databricks-model-serving for that."
compatibility: Requires databricks CLI (>= v1.11.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Unity Gateway

Use the parent `databricks-core` skill for CLI authentication and profile selection.

Unity Gateway provides Unity Catalog securables for governed access to AI services. The
current CLI command group retains the earlier product name:

```bash
databricks ai-gateway --help
```

## Choose the Correct Gateway

| Request | Use |
|---|---|
| Unity Gateway or Unity AI Gateway model service, MCP service, or model provider service | This skill and `databricks ai-gateway` |
| AI Gateway configuration on a Model Serving endpoint, including `put-ai-gateway` | `databricks-model-serving` and `databricks serving-endpoints` |
| Lakeflow Connect ingestion gateway | `databricks-lakeflow-connect` |

Treat **Unity AI Gateway** as an earlier name for **Unity Gateway** when the resource is a
Unity Catalog securable. Do not translate legacy Model Serving AI Gateway resources into
Unity Gateway resources unless the user explicitly requests a migration.

## CLI Workflow

Use only the Databricks CLI for implementation. Do not substitute direct REST calls or a
Databricks SDK.

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
| Model service | `create-model-service`, `get-model-service`, `list-model-services`, `update-model-service`, `delete-model-service` |
| MCP service | `create-mcp-service`, `get-mcp-service`, `list-mcp-services`, `update-mcp-service`, `delete-mcp-service` |
| Model provider service | `create-model-provider-service`, `get-model-provider-service`, `list-model-provider-services`, `update-model-provider-service`, `delete-model-provider-service` |

## Authoritative Documentation

- [Unity Gateway overview](https://learn.microsoft.com/en-us/azure/databricks/ai-gateway/)
- [Unity Gateway developer documentation](https://developers.databricks.com/docs/agents/ai-gateway)
- [Model service API reference](https://docs.databricks.com/api/ai-gateway/v1/model-service)
- [MCP service API reference](https://docs.databricks.com/api/ai-gateway/v1/mcp-service)
- [Model provider service API reference](https://docs.databricks.com/api/ai-gateway/v1/model-provider-service)
