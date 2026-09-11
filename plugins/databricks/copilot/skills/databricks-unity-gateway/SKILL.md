---
name: databricks-unity-gateway
description: "Unity Catalog AI Gateway services, managed through the `databricks ai-gateway` CLI command group. Use when asked to work with model services, MCP services, or model provider services — Unity Catalog securables named catalog.schema.name and backed by /api/2.1/unity-catalog/ — including creating, listing, inspecting, updating, and deleting them. NOT for: legacy per-endpoint AI Gateway configuration on a serving endpoint (serving-endpoints put-ai-gateway) or serving-endpoint lifecycle, traffic routing, and querying — use databricks-model-serving. NOT for: generic Unity Catalog privilege mechanics such as GRANT/REVOKE, ownership, external locations, or system tables — use databricks-unity-catalog."
compatibility: "Requires a databricks CLI that ships the `ai-gateway` command group (Beta; the group and its flags may change). Confirm with `databricks ai-gateway -h`; when the installed CLI lacks the group, use the `databricks api` REST fallback against /api/2.1/unity-catalog/."
metadata:
  version: "0.2.0"
parent: databricks-core
---

# Unity Catalog AI Gateway

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

> **Status**: model service CRUD (below) is verified against the CLI and API surface.
> Advanced configuration and the other two service types arrive in later phases — see
> [Coming in stages](#coming-in-stages).

## Scope

Unity Catalog AI Gateway ("Unity Gateway") exposes governed model APIs as **Unity Catalog
securables**: a **model service**, **MCP service**, or **model provider service** is created
in a catalog and schema, addressed by its three-level name `<CATALOG>.<SCHEMA>.<NAME>`, and
managed through the `databricks ai-gateway` command group over
`/api/2.1/unity-catalog/`. Because these objects live in Unity Catalog, they are governed
the same way other securables are — grant the narrowest privilege that satisfies the use
case, and never a blanket `ALL PRIVILEGES`.

This is a **different thing** from the legacy, per-endpoint *AI Gateway configuration* on a
Model Serving endpoint (rate limits, usage tracking, guardrails, inference tables applied to
one serving endpoint via `databricks serving-endpoints put-ai-gateway`). That endpoint-level
config, and serving-endpoint lifecycle in general (create, update traffic, poll readiness,
query), belongs to **[databricks-model-serving](../databricks-model-serving/SKILL.md)**. For
generic Unity Catalog privilege mechanics — `GRANT`/`REVOKE`, ownership, external locations,
system tables — use **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)**.

| You want to… | Skill |
|---|---|
| CRUD a UC model / MCP / model provider service (`databricks ai-gateway …`) | this skill |
| Configure rate limits or usage tracking on one serving endpoint (`serving-endpoints put-ai-gateway`) | `databricks-model-serving` |
| Create, update, query, or delete a serving endpoint | `databricks-model-serving` |
| Grant privileges, set ownership, query system tables | `databricks-unity-catalog` |

## CLI Discovery — ALWAYS Do This First

The `ai-gateway` command group is **Beta**: subcommands, flags, and JSON payload fields can
change between CLI releases, so **do not guess syntax and do not copy flags from memory**.
The syntax documented below is the current verified shape — still confirm it against the
installed CLI before constructing a command.

```bash
# 1. Confirm the group exists in the installed CLI and list its subcommands.
databricks ai-gateway -h

# 2. Discover the exact flags, positional args, and JSON fields for one subcommand.
databricks ai-gateway <SUBCOMMAND> -h
```

Run both before constructing any command. If step 1 reports an unknown command, the
installed CLI predates the group — either upgrade the CLI or use the
[REST fallback](#rest-fallback).

Names in examples are placeholders — substitute your own catalog and schema
(`<CATALOG>.<SCHEMA>.<NAME>`), workspace host
(`company-workspace.cloud.databricks.com`), and workspace ID (`1111111111111111`). Never
paste a real token, password, or credential into a command or a file.

## Model services

A **model service** is a governed AI Gateway endpoint that routes inference requests to one
or more model **destinations**. This section covers the pay-per-token (Paygo) case: a
destination backed by a Databricks-hosted foundation model in `system.ai`.

### Two name forms — the #1 gotcha

The same service is addressed **two different ways** depending on the command:

| Context | Form | Example |
|---|---|---|
| `ai-gateway` `NAME` arg (get / update / delete) | typed, `model-services/` prefix | `model-services/<CATALOG>.<SCHEMA>.<SERVICE>` |
| `ai-gateway` `PARENT` arg / `--parent` (create / list) | typed, `schemas/` prefix | `schemas/<CATALOG>.<SCHEMA>` |
| `grants` securable name | **bare** three-level name | `<CATALOG>.<SCHEMA>.<SERVICE>` |

Passing a bare `<CATALOG>.<SCHEMA>.<SERVICE>` to `get-model-service`, or the typed
`model-services/…` form to `grants`, is the most common error. There is a third typed form
for models: `pay_per_token_config.model` is `models/{catalog}.{schema}.{model}`.

### The five CRUD commands

| Op | Command | Key details |
|---|---|---|
| Create | `create-model-service PARENT MODEL_SERVICE_ID` | Both positional. `PARENT` = `schemas/<CATALOG>.<SCHEMA>`; `MODEL_SERVICE_ID` = leaf name only. `config` is **required**; there is no `--config` flag — pass it via `--json`. |
| Read | `get-model-service NAME` | `NAME` = `model-services/<CATALOG>.<SCHEMA>.<SERVICE>`. |
| List | `list-model-services --parent schemas/<CATALOG>.<SCHEMA>` | `--parent` is a flag, and semantically required by the API. Also `--view BASIC\|FULL` (no other value), `--page-size` (≤100), `--limit`. |
| Update | `update-model-service NAME UPDATE_MASK` | `UPDATE_MASK` is **positional** (no `--update-mask` flag), comma-separated. Name is immutable. |
| Delete | `delete-model-service NAME [--etag]` | No request body. |

All inherit the global `--profile` / `--output` / `--debug` / `--target` flags.

### Create a pay-per-token model service

The minimal valid body — one Paygo destination pointing at a `system.ai` foundation model:

```bash
databricks ai-gateway create-model-service \
  schemas/<CATALOG>.<SCHEMA> my_model_service \
  --json '{
    "config": {
      "routing": {
        "destinations": [{
          "name": "primary",
          "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
          "pay_per_token_config": {
            "model": "models/system.ai.databricks-meta-llama-3-3-70b-instruct"
          }
        }]
      }
    }
  }' --profile <PROFILE>
```

- **`--json` is the `ModelService` body directly** — *not* wrapped in `{"model_service": …}`.
  `parent` and `model_service_id` are query params supplied as the two positionals, so they
  do **not** appear in the body. Optional body fields: `comment`, `owner` (also available as
  `--comment` / `--owner` flags).
- The model id above is an **example**. New foundation models land regularly — discover
  what's available in `system.ai` rather than hard-coding a name (see
  `databricks-model-serving`'s Foundation Model API section for the runtime-list snippet).
- On success the server derives `name` as `model-services/<CATALOG>.<SCHEMA>.my_model_service`
  and returns an `etag`.

### Read, list, update, delete

```bash
# Read one service (typed NAME).
databricks ai-gateway get-model-service \
  model-services/<CATALOG>.<SCHEMA>.<SERVICE> --profile <PROFILE>

# List services in a schema. --view FULL asks for the fuller per-row representation.
databricks ai-gateway list-model-services \
  --parent schemas/<CATALOG>.<SCHEMA> --view FULL --profile <PROFILE>

# Update the comment only. UPDATE_MASK is the second POSITIONAL arg.
databricks ai-gateway update-model-service \
  model-services/<CATALOG>.<SCHEMA>.<SERVICE> comment \
  --comment 'Governed Llama endpoint for the search team' --profile <PROFILE>

# Delete, guarded by the etag from a prior read.
databricks ai-gateway delete-model-service \
  model-services/<CATALOG>.<SCHEMA>.<SERVICE> --etag '<ETAG>' --profile <PROFILE>
```

**Update rules.** Only fields named in `UPDATE_MASK` change, and the resource name is
immutable (omit `--name`). Valid mask paths include `comment`, `config`,
`config.routing.destinations`, `config.routing.fallback.destinations`, `config.rate_limits`,
and `config.inference_table`. Wildcard `*` is **not** supported, and neither are the
intermediate paths `config.routing` or `config.routing.fallback` — name a concrete leaf.
When the mask names `config` or any `config.*` subpath, `config` becomes required in the body.

**Concurrency.** Every read returns an `etag`. For a safe read-modify-write, pass that value
back via `--etag`; the server rejects the mutation if the stored etag has changed since your
read. Without `--etag` the update is unconditional and can clobber a concurrent edit.

For fuller per-verb payloads, the update-mask matrix, and the REST equivalents, see
[references/model-service-crud.md](references/model-service-crud.md).

### Grants — create and invoke

Grant the narrowest privilege that works; **never `ALL PRIVILEGES`**.

| To… | Needs |
|---|---|
| **Create** a model service | Own the parent schema, **or** `CREATE_SERVICE` + `USE_SCHEMA` on the schema plus `USE_CATALOG` on the catalog. Additionally `USE_CATALOG` + `USE_SCHEMA` + `EXECUTE` on **each referenced UC model** destination. |
| **Invoke** the finished service | `USE_CATALOG` + `USE_SCHEMA` + `EXECUTE` on the model service. |
| **Read** metadata (`get` / `list`) | `USE_CATALOG` + `USE_SCHEMA`, plus ownership or a read-capable privilege on the service — the Beta help lists `EXECUTE` / `READ_METADATA` / `MANAGE`. |
| **Update** / **delete** | `USE_CATALOG` + `USE_SCHEMA`, plus ownership or `MANAGE` on the service. |

The create and invoke rows are the two to get right. For the read/update/delete rows, the
parent `USE_CATALOG` + `USE_SCHEMA` requirement is stable, but confirm the exact service-level
privilege names with `databricks ai-gateway <SUBCOMMAND> -h` and the API reference before
baking them into automation — this is a Beta surface.

Grant `EXECUTE` to a consuming group — note the **bare** securable name here, contrasted
with the typed `model-services/…` form the `ai-gateway` commands take:

```bash
# Inspect current grants (securable type model_service, BARE three-level name).
databricks grants get model_service <CATALOG>.<SCHEMA>.<SERVICE> --profile <PROFILE>

# Let a group invoke the service.
databricks grants update model_service <CATALOG>.<SCHEMA>.<SERVICE> \
  --json '{"changes":[{"principal":"<GROUP>","add":["EXECUTE"]}]}' --profile <PROFILE>
```

`CREATE_SERVICE` is what the Beta CLI help documents for schema-level creation; if your
workspace rejects it as an unknown privilege, confirm the accepted spelling with
`databricks grants get schema <CATALOG>.<SCHEMA>` and the API reference. For `GRANT`/`REVOKE`
mechanics, inheritance, and ownership transfer in general, use
**[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)**.

### REST fallback

When the installed CLI predates the `ai-gateway` group, drive the same API through
`databricks api <verb>`, which reuses your profile's auth:

```bash
# Create (parent + model_service_id are QUERY params; body is the ModelService).
databricks api post \
  '/api/2.1/unity-catalog/model-services?parent=schemas/<CATALOG>.<SCHEMA>&model_service_id=my_model_service' \
  --json @body.json --profile <PROFILE>

# Read / list / delete.
databricks api get    /api/2.1/unity-catalog/model-services/<CATALOG>.<SCHEMA>.<SERVICE> --profile <PROFILE>
databricks api get    '/api/2.1/unity-catalog/model-services?parent=schemas/<CATALOG>.<SCHEMA>' --profile <PROFILE>
databricks api delete /api/2.1/unity-catalog/model-services/<CATALOG>.<SCHEMA>.<SERVICE> --profile <PROFILE>

# Update: PATCH, with update_mask (and optional etag) as QUERY params.
databricks api patch \
  '/api/2.1/unity-catalog/model-services/<CATALOG>.<SCHEMA>.<SERVICE>?update_mask=comment' \
  --json '{"comment":"Governed Llama endpoint"}' --profile <PROFILE>
```

The path segment after `/model-services/` is the **bare** `<CATALOG>.<SCHEMA>.<SERVICE>` —
the `model-services/` prefix the CLI `NAME` arg wants is the path segment itself. Quote any
URL containing `?` or `&` so the shell does not split it.

## Coming in stages

Later phases add verified commands and payloads, discovered from the CLI, for:

1. **MCP services** — create / list / get / update / delete a UC MCP service.
2. **Model provider services** — create / list / get / update / delete a UC model provider
   service, including how provider credentials are supplied.
3. **Advanced model service config** — routing and traffic splitting across destinations,
   fallbacks, rate limits, inference tables, and external / provisioned-throughput
   destinations.

Until a section lands, use [CLI Discovery](#cli-discovery--always-do-this-first) and the
`/api/2.1/unity-catalog/` API reference as the source of truth.

## Troubleshooting

| Error | Solution |
|-------|----------|
| `unknown command "ai-gateway" for "databricks"` | Installed CLI predates the group. Upgrade, or use the [REST fallback](#rest-fallback). |
| `INVALID_ARGUMENT` on `get`/`update`/`delete` | `NAME` must be the typed `model-services/<CATALOG>.<SCHEMA>.<SERVICE>`, not the bare three-level name. |
| `INVALID_ARGUMENT` naming the update mask | Wildcard `*` and intermediate paths (`config.routing`) are unsupported — name a concrete leaf such as `config.routing.destinations`. |
| Create rejected for a missing `config` | `config` is required on create and there is no `--config` flag; supply it via `--json`. |
| Etag mismatch on update or delete | Someone else modified the service since your read. Re-run `get-model-service`, re-apply your change, and pass the fresh `--etag`. |
| `PERMISSION_DENIED` on create | Check schema-level create rights **and** `EXECUTE` on each referenced `system.ai` model — the model grant is the one usually missed. |
| `PERMISSION_DENIED` invoking the service | Caller needs `USE_CATALOG` + `USE_SCHEMA` + `EXECUTE` on the service; grant with the **bare** name via `databricks grants update model_service`. |
| Empty `list-model-services` output | `--parent` is effectively required, and results are filtered to services you can access. Verify the schema and your grants. |
