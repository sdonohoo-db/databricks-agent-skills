# Query services

Read this reference when writing Python that invokes a Unity Gateway model service or model
provider service. Python is for inference; continue to use the Databricks CLI for service
lifecycle and permission management.

## Resolve query inputs

Before writing or running a query, resolve:

- Workspace URL and authentication method
- Exact three-part service name: `<catalog>.<schema>.<service>`
- API format required by the request
- For a model provider service, an upstream model allowed by its target configuration
- Optional request tags

Use a Databricks credential to call Unity Gateway. Never expose or request the external
provider credential; Unity Gateway supplies it for provider-service calls. Read credentials
from the environment or the runtime's supported Databricks authentication mechanism, never
hardcode them.

The caller needs `USE CATALOG`, `USE SCHEMA`, and `EXECUTE` on the selected service. See
[permissions.md](permissions.md).

## Query a model service
The unified Responses API `/ai-gateway/mlflow/v1/responses` path works across underlying providers, and is the official method to run inference on LLMs on Databricks.
It implements the [Open Responses](https://www.openresponses.org/reference) specification and works across underlying providers; Unity Gateway translates each request to the backing model's native format. Set `model` to the model service's fully qualified three-part name:

```python
import os

from openai import OpenAI

workspace_url = os.environ["DATABRICKS_HOST"].rstrip("/")
client = OpenAI(
    api_key=os.environ["DATABRICKS_TOKEN"],
    base_url=f"{workspace_url}/ai-gateway/mlflow/v1",
)

response = client.responses.create(
    model="<catalog>.<schema>.<model-service>",
    input=[{"role": "user", "content": "What is Databricks?"}],
    max_output_tokens=256,
)

print(response.output_text)
```

Open Responses on Unity Gateway is stateless. `previous_response_id` and server-side
conversation storage are unsupported; send the full conversation in `input` on each turn.
For tool calls, return every model output item unchanged, including `encrypted_content`
on reasoning and Gemini `function_call` items, then add a `function_call_output` with the
same `call_id`. Only `function` tools are portable across providers. See
[Open Responses provider behavior](https://docs.databricks.com/aws/en/machine-learning/model-serving/query-open-responses-models)
and the [Open Responses API reference](https://www.openresponses.org/reference).

### Query open source models

When querying open source models hosted by Databricks (Kimi, Deepseek, GLM, etc), use the unified Responses API via the OpenAI SDK:

```python
import os

from openai import OpenAI

workspace_url = os.environ["DATABRICKS_HOST"].rstrip("/")
client = OpenAI(
    api_key=os.environ["DATABRICKS_TOKEN"],
    base_url=f"{workspace_url}/ai-gateway/mlflow/v1",
)

response = client.responses.create(
    model="system.ai.glm-5-3-flash",
    input=[{"role": "user", "content": "What's the weather in San Francisco?"}],
    tools=[
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get the current temperature for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
                "additionalProperties": False,
            },
        }
    ],
    reasoning={"effort": "high"},
    max_output_tokens=4096,
)

for item in response.output:
    if item.type == "function_call":
        print(item.name, item.arguments)
```

While the MLflow Chat Completions on the same base url ai-gateway/mlflow/v1/chat/completions remains supported,
the unified Responses endpoint is recommended as the default for any new applications with greater tool calling and agentic support.

Use a native API only when the backing model supports that format:

| API | Python client base URL |
|---|---|
| OpenAI Responses | `<workspace-url>/ai-gateway/openai/v1` |
| Anthropic Messages | `<workspace-url>/ai-gateway/anthropic` |
| Gemini generate content | `<workspace-url>/ai-gateway/gemini` |

For OpenAI Responses, keep the fully qualified model-service name in `model`:

```python
response = OpenAI(
    api_key=os.environ["DATABRICKS_TOKEN"],
    base_url=f"{workspace_url}/ai-gateway/openai/v1",
).responses.create(
    model="<catalog>.<schema>.<model-service>",
    input="What is Databricks?",
    max_output_tokens=256,
)
```

Do not use a native API whose format does not match the backing model. Use the unified
Responses path when the backing provider is unknown or portability is preferred.

## Query a model provider service

Provider-service requests differ in two fields:

- Set `Databricks-Model-Provider-Service` to the provider service's three-part name.
- Set `model` to the upstream provider model, not the provider-service name.

For an OpenAI-compatible target whose `native_api_types` include `openai/v1/responses`:

```python
# Note example here uses optional databricks-openai package to simplify authentication
from databricks.sdk import WorkspaceClient
from databricks_openai import DatabricksOpenAI

client = DatabricksOpenAI(
    workspace_client=WorkspaceClient(),
    use_ai_gateway_native_api=True,
    default_headers={
        "Databricks-Model-Provider-Service":
            "<catalog>.<schema>.<model-provider-service>"
    },
)

response = client.responses.create(
    model="<allowed-provider-model>",
    input=[{"role": "user", "content": "What is Databricks?"}],
)

print(response.output_text)
```

Managed provider paths include:

| Provider API | Path |
|---|---|
| OpenAI chat completions | `/ai-gateway/openai/v1/chat/completions` |
| OpenAI responses | `/ai-gateway/openai/v1/responses` |
| OpenAI embeddings | `/ai-gateway/openai/v1/embeddings` |
| Anthropic messages | `/ai-gateway/anthropic/v1/messages` |
| Gemini generate content | `/ai-gateway/gemini/v1beta/models/<model>:generateContent` |

Prefer managed paths. Unmanaged passthrough must be explicitly enabled on the provider
service and bypasses usage token and cost tracking, token-based rate limits, model access
control, and service policies. Select a client and path matching the configured target's
`native_api_types`; do not assume every provider or target accepts the OpenAI format.

## Request tags

Attach string-valued request tags for cost attribution and usage analysis:

```python
import json

request_tags = {"project": "chatbot", "team": "ml-platform"}

response = client.responses.create(
    model="<catalog>.<schema>.<model-service>",
    input=[{"role": "user", "content": "What is Databricks?"}],
    extra_headers={
        "Databricks-Ai-Gateway-Request-Tags": json.dumps(request_tags)
    },
)
```

For a model service that routes to a model provider service, the model service's rate
limits, guardrails, inference table, and fallback behavior apply. The referenced provider
service's corresponding features are skipped for that routed request.
