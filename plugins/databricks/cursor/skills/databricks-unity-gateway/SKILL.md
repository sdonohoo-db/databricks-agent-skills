---
name: databricks-unity-gateway
description: "Unity Catalog AI Gateway services, managed through the `databricks ai-gateway` CLI command group. Use when asked to work with model services, MCP services, or model provider services — Unity Catalog securables named catalog.schema.name and backed by /api/2.1/unity-catalog/ — including creating, listing, inspecting, updating, and deleting them. NOT for: legacy per-endpoint AI Gateway configuration on a serving endpoint (serving-endpoints put-ai-gateway) or serving-endpoint lifecycle, traffic routing, and querying — use databricks-model-serving. NOT for: generic Unity Catalog privilege mechanics such as GRANT/REVOKE, ownership, external locations, or system tables — use databricks-unity-catalog."
compatibility: "Requires a databricks CLI that ships the `ai-gateway` command group (Beta; the group and its flags may change). Confirm with `databricks ai-gateway -h`; when the installed CLI lacks the group, use the `databricks api` REST fallback against /api/2.1/unity-catalog/."
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Unity Catalog AI Gateway

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

> **Status**: this skill is a scaffold. Only the scoping and discovery guidance below is
> final; the per-command how-to arrives in later phases (see
> [Coming in stages](#coming-in-stages)). Until then, discover exact syntax from the CLI
> itself rather than from this file.

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

```bash
# 1. Confirm the group exists in the installed CLI and list its subcommands.
databricks ai-gateway -h

# 2. Discover the exact flags, positional args, and JSON fields for one subcommand.
databricks ai-gateway <SUBCOMMAND> -h
```

Run both before constructing any command. If step 1 reports an unknown command, the
installed CLI predates the group — either upgrade the CLI or use the REST fallback:

```bash
# REST fallback when the CLI lacks the ai-gateway group. Discover the exact path and
# payload from the API reference for /api/2.1/unity-catalog/ first.
databricks api get /api/2.1/unity-catalog/<PATH> --profile <PROFILE>
```

Names in examples are placeholders — substitute your own catalog and schema
(`<CATALOG>.<SCHEMA>.<NAME>`), workspace host
(`company-workspace.cloud.databricks.com`), and workspace ID (`1111111111111111`). Never
paste a real token, password, or credential into a command or a file.

## Coming in stages

Later phases add verified commands and payloads, discovered from the CLI, for:

1. **Model services** — create / list / get / update / delete a UC model service.
2. **MCP services** — create / list / get / update / delete a UC MCP service.
3. **Model provider services** — create / list / get / update / delete a UC model provider
   service, including how provider credentials are supplied.
4. **Advanced** — routing and traffic across models, rate limits, inference tables, and
   external destinations.

Until a section lands, use [CLI Discovery](#cli-discovery--always-do-this-first) and the
`/api/2.1/unity-catalog/` API reference as the source of truth.
