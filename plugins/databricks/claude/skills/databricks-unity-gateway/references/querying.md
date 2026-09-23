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

The unified MLflow Chat Completions path works across underlying providers. Set `model` to
the model service's fully qualified three-part name:

```python
import os

from openai import OpenAI

workspace_url = os.environ["DATABRICKS_HOST"].rstrip("/")
client = OpenAI(
    api_key=os.environ["DATABRICKS_TOKEN"],
    base_url=f"{workspace_url}/ai-gateway/mlflow/v1",
)

response = client.chat.completions.create(
    model="<catalog>.<schema>.<model-service>",
    messages=[{"role": "user", "content": "What is Databricks?"}],
    max_tokens=256,
)

print(response.choices[0].message.content)
```

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
MLflow path when the backing provider is unknown or portability is preferred.

## Query a model provider service

Provider-service requests differ in two fields:

- Set `Databricks-Model-Provider-Service` to the provider service's three-part name.
- Set `model` to the upstream provider model, not the provider-service name.

For an OpenAI-compatible provider:

```python
import os

from openai import OpenAI

workspace_url = os.environ["DATABRICKS_HOST"].rstrip("/")
client = OpenAI(
    api_key=os.environ["DATABRICKS_TOKEN"],
    base_url=f"{workspace_url}/ai-gateway/openai/v1",
    default_headers={
        "Databricks-Model-Provider-Service":
            "<catalog>.<schema>.<model-provider-service>"
    },
)

response = client.chat.completions.create(
    model="<allowed-provider-model>",
    messages=[{"role": "user", "content": "What is Databricks?"}],
)

print(response.choices[0].message.content)
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

response = client.chat.completions.create(
    model="<service-or-provider-model>",
    messages=[{"role": "user", "content": "What is Databricks?"}],
    extra_headers={
        "Databricks-Ai-Gateway-Request-Tags": json.dumps(request_tags)
    },
)
```

For a model service that routes to a model provider service, the model service's rate
limits, guardrails, inference table, and fallback behavior apply. The referenced provider
service's corresponding features are skipped for that routed request.
