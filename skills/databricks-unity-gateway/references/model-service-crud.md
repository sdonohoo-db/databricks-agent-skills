# Model service CRUD — detailed reference

Per-verb detail for `databricks ai-gateway *-model-service*`, scoped to
**pay-per-token (Paygo) Databricks-hosted foundation model** destinations. The
[SKILL.md](../SKILL.md#model-services) overview is the place to start; this file is the
lookup table for exact arguments and payloads.

The `ai-gateway` group is **Beta** — every signature here should be confirmed against
`databricks ai-gateway <SUBCOMMAND> -h` on the installed CLI before use. Advanced
configuration (traffic splitting, fallbacks, rate limits, inference tables, external and
provisioned-throughput destinations) is covered in a later phase.

> **Provenance.** Command signatures, argument formats, privilege requirements, and payload
> field semantics below were taken from the CLI's own help text and the SDK's request/response
> types, not from a live workspace. Anything *not* stated by those sources is marked as
> needing confirmation. The `/api/2.1/unity-catalog/` API reference is the authoritative
> schema; where this file and the API reference disagree, believe the API reference.

## Name forms

| Where | Form |
|---|---|
| `PARENT` positional (create), `--parent` (list) | `schemas/{catalog}.{schema}` |
| `NAME` positional (get / update / delete) | `model-services/{catalog}.{schema}.{model_service}` |
| `pay_per_token_config.model` | `models/{catalog}.{schema}.{model}` |
| `grants` securable name | bare `{catalog}.{schema}.{model_service}` |
| REST path segment | bare, after the literal prefix: `/model-services/{catalog}.{schema}.{model_service}` |

`name` is server-derived on create from `parent` + `model_service_id`, and is **immutable**
afterwards. The CLI help states each `{...}` component is capped at 255 characters
individually; standard Unity Catalog identifier rules otherwise apply, so confirm exact limits
in the API reference if you are near them.

## create-model-service

```
databricks ai-gateway create-model-service PARENT MODEL_SERVICE_ID [flags]
```

Two required positionals, both sent as **query params** (not body fields):

| Positional | Value |
|---|---|
| `PARENT` | `schemas/<CATALOG>.<SCHEMA>` |
| `MODEL_SERVICE_ID` | leaf name only, e.g. `my_model_service` |

Flags: `--json`, `--comment`, `--name`, `--owner`. **There is no `--config` flag** — `config`
is required on create, so `--json` is mandatory in practice. `--json` accepts an inline
string or `@path/to/file.json`, and unmarshals **directly into the `ModelService` body** —
do *not* wrap it in `{"model_service": …}`.

Body fields that matter on create:

| Field | Notes |
|---|---|
| `config` | **Required.** Destinations / routing (and later: rate limits, inference table). |
| `comment` | Optional description. Also `--comment`. |
| `owner` | Optional; write-only. Defaults to the caller. Read it back as `effective_owner`. |

Minimal valid Paygo body:

```json
{
  "config": {
    "routing": {
      "destinations": [
        {
          "name": "primary",
          "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
          "pay_per_token_config": {
            "model": "models/system.ai.databricks-meta-llama-3-3-70b-instruct"
          }
        }
      ]
    }
  }
}
```

- `config.routing.destinations` requires at least one entry on create, and the SDK documents
  an upper bound of 10. Treat the bound as indicative and confirm it in the API reference
  before designing around it.
- Per destination, `name` (the routing label) and `destination_type` are required. The
  `destination_type` selects which config variant is read — `DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL`
  reads `pay_per_token_config`. The other two variants,
  `DESTINATION_TYPE_PROVISIONED_THROUGHPUT_FOUNDATION_MODEL` and
  `DESTINATION_TYPE_EXTERNAL_FOUNDATION_MODEL`, are a later phase.
- `pay_per_token_config.model` is the typed UC model name `models/{catalog}.{schema}.{model}`.
  Databricks-hosted foundation models live under `system.ai.*`. **Discover the available
  models at runtime rather than hard-coding** — the id above is only an example and the
  catalog changes as new models ship.
- `traffic_percentage` exists on a destination but governs multi-destination routing, which is
  a later phase. Leave it unset for the single-destination case above; check the API reference
  for how it is interpreted before relying on a particular default.

Full command:

```bash
databricks ai-gateway create-model-service \
  schemas/<CATALOG>.<SCHEMA> my_model_service \
  --json @body.json \
  --comment 'Governed Llama endpoint for the search team' \
  --profile <PROFILE>
```

Response is the created `ModelService`. The two fields worth capturing are the server-derived
`name` and the `etag` (needed for a later conditional update or delete). The representation
typically also carries read-only metadata such as `effective_owner`, `metastore_id`,
`create_time` / `created_by`, and a `supported_api_types` list derived from the backing models
— treat that as an indicative rather than exhaustive list, and see the API reference for the
authoritative response schema.

## get-model-service

```bash
databricks ai-gateway get-model-service \
  model-services/<CATALOG>.<SCHEMA>.<SERVICE> --profile <PROFILE>
```

`NAME` must be the typed `model-services/…` form. Use this before any update or delete to
capture the current `etag`:

```bash
ETAG=$(databricks ai-gateway get-model-service \
  model-services/<CATALOG>.<SCHEMA>.<SERVICE> --output json --profile <PROFILE> | jq -r .etag)
```

## list-model-services

```bash
databricks ai-gateway list-model-services \
  --parent schemas/<CATALOG>.<SCHEMA> --profile <PROFILE>
```

Takes **no positionals**; the schema comes from `--parent`, which is semantically required by
the API even though the CLI does not enforce it.

| Flag | Notes |
|---|---|
| `--parent` | `schemas/<CATALOG>.<SCHEMA>`. Effectively required. |
| `--view` | `BASIC` or `FULL` only — the CLI rejects any other token. `FULL` requests the fuller representation of each row and `BASIC` a more compact one, defaulting to `BASIC`; inspect the output (or the API reference) for exactly which fields each view returns rather than assuming a specific field is present. |
| `--page-size` | Services per page. Documented default and maximum are both 100. |
| `--limit` | Client-side cap on total results returned. |
| `--page-token` | Hidden pagination flag taking an opaque token from a previous response. Whether the CLI follows pages for you is not something to assume — check `-h` on your CLI, and page explicitly if you need a guarantee. |

Per the CLI help, listing requires `USE_CATALOG` on the parent catalog and `USE_SCHEMA` on the
parent schema, and returns only the model services the caller can access — as owner or through
`EXECUTE`, `READ_METADATA`, or `MANAGE`. So an empty list may mean missing grants rather than
an empty schema.

```bash
# Service names, plus supported API types when the view returns them.
databricks ai-gateway list-model-services \
  --parent schemas/<CATALOG>.<SCHEMA> --view FULL --output json --profile <PROFILE> \
  | jq -r '.[] | "\(.name)\t\(.supported_api_types // [] | join(","))"'
```

## update-model-service

```
databricks ai-gateway update-model-service NAME UPDATE_MASK [flags]
```

**Both arguments are positional** — there is no `--update-mask` flag. `UPDATE_MASK` is a
comma-separated list of field paths, and only those fields are applied.

| Mask path | Supported |
|---|---|
| `comment` | yes |
| `config` | yes (replaces the whole config) |
| `config.routing.destinations` | yes |
| `config.routing.fallback.destinations` | yes |
| `config.rate_limits` | yes |
| `config.inference_table` | yes |
| `config.routing`, `config.routing.fallback` | **no** — intermediate paths are rejected |
| `*` | **no** — wildcards are unsupported; list each path explicitly |

Rules:

- The resource `name` is immutable — omit `--name`.
- When the mask names `config` or any `config.*` subpath, `config` is **required** in the body.
- Flags `--comment` / `--owner` set those fields without `--json`; `--json` supplies a partial
  `ModelService` body (again, unwrapped). A field changes only if its path is in the mask.

```bash
# Comment only — no config needed in the body.
databricks ai-gateway update-model-service \
  model-services/<CATALOG>.<SCHEMA>.<SERVICE> comment \
  --comment 'Deprecated; migrate to the v2 service' \
  --etag "$ETAG" --profile <PROFILE>

# Repoint the Paygo destination at a different system.ai model.
databricks ai-gateway update-model-service \
  model-services/<CATALOG>.<SCHEMA>.<SERVICE> config.routing.destinations \
  --json '{
    "config": {
      "routing": {
        "destinations": [{
          "name": "primary",
          "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
          "pay_per_token_config": {"model": "models/system.ai.<MODEL>"}
        }]
      }
    }
  }' --etag "$ETAG" --profile <PROFILE>

# Two paths at once (comma-separated, no spaces).
databricks ai-gateway update-model-service \
  model-services/<CATALOG>.<SCHEMA>.<SERVICE> comment,config.routing.destinations \
  --json @patch.json --etag "$ETAG" --profile <PROFILE>
```

### Optimistic concurrency (etag)

Every read returns an `etag` derived from the entity's state. Passing it via `--etag` makes
the mutation an if-match precondition: the server rejects it if the stored etag has changed
since your read. Omitting `--etag` makes the update unconditional, which can silently clobber
a concurrent edit. The safe loop is **read → modify → write with the etag you read**, and on
rejection re-read and retry rather than dropping the flag.

## delete-model-service

```bash
databricks ai-gateway delete-model-service \
  model-services/<CATALOG>.<SCHEMA>.<SERVICE> --etag "$ETAG" --profile <PROFILE>
```

No request body; `--etag` is the same if-match precondition as on update. Per the CLI help,
requires ownership or `MANAGE` on the service, plus `USE_CATALOG` on the parent catalog and
`USE_SCHEMA` on the parent schema.

Deleting a UC **model** that a destination references is documented as *not* removing the
destination row: the dangling destination is surfaced rather than silently dropped so callers
can see the broken routing, and inference through it fails closed. The SDK models this as an
`is_deleted` boolean on the destination — confirm the field name and the exact behavior against
the API reference before building on it, since this was read from the type definition rather
than observed on a live service:

```bash
databricks ai-gateway get-model-service model-services/<CATALOG>.<SCHEMA>.<SERVICE> \
  --output json --profile <PROFILE> \
  | jq '.config.routing.destinations[] | select(.is_deleted) | .name'
```

## Grants

Least privilege only — **never `ALL PRIVILEGES`**. The `grants` commands take the securable
type `model_service` and the **bare** three-level name, unlike the typed `model-services/…`
form used by `ai-gateway`.

| Goal | Privileges |
|---|---|
| Create a model service | Parent schema owner, **or** `CREATE_SERVICE` + `USE_SCHEMA` on the schema + `USE_CATALOG` on the catalog. Plus `USE_CATALOG` + `USE_SCHEMA` + `EXECUTE` on every referenced UC model. |
| Invoke the service | `USE_CATALOG` + `USE_SCHEMA` + `EXECUTE` on the service |
| `get` / `list` | Owner, or `EXECUTE` / `READ_METADATA` / `MANAGE` on the service, plus `USE_CATALOG` + `USE_SCHEMA` |
| `update` / `delete` | Owner, or `MANAGE` on the service, plus `USE_CATALOG` + `USE_SCHEMA` |

The `get` / `list` / `update` / `delete` rows restate the per-subcommand CLI help. The parent
`USE_CATALOG` + `USE_SCHEMA` requirement is consistent across all four; the service-level
privilege names are the ones the Beta help lists, so re-check them with
`databricks ai-gateway <SUBCOMMAND> -h` and the API reference before encoding them in a
provisioning script.

```bash
# Current grants on the service.
databricks grants get model_service <CATALOG>.<SCHEMA>.<SERVICE> --profile <PROFILE>

# Grant invoke rights to a consuming group.
databricks grants update model_service <CATALOG>.<SCHEMA>.<SERVICE> \
  --json '{"changes":[{"principal":"<GROUP>","add":["EXECUTE"]}]}' --profile <PROFILE>

# Revoke them again.
databricks grants update model_service <CATALOG>.<SCHEMA>.<SERVICE> \
  --json '{"changes":[{"principal":"<GROUP>","remove":["EXECUTE"]}]}' --profile <PROFILE>
```

`CREATE_SERVICE` is the privilege the Beta CLI help names for schema-level creation. If a
workspace rejects that spelling, confirm the accepted value against
`databricks grants get schema <CATALOG>.<SCHEMA>` and the API reference rather than
substituting a broader privilege. General `GRANT`/`REVOKE` mechanics, inheritance, and
ownership transfer belong to the
[databricks-unity-catalog](../../databricks-unity-catalog/SKILL.md) skill.

## REST fallback

For a CLI without the `ai-gateway` group. `databricks api <verb>` reuses the profile's auth,
so no token handling is needed. Quote any URL containing `?` or `&`.

| Op | Call |
|---|---|
| create | `POST /api/2.1/unity-catalog/model-services?parent=schemas/<C>.<S>&model_service_id=<NAME>` |
| get | `GET /api/2.1/unity-catalog/model-services/<C>.<S>.<NAME>` |
| list | `GET /api/2.1/unity-catalog/model-services?parent=schemas/<C>.<S>` |
| update | `PATCH /api/2.1/unity-catalog/model-services/<C>.<S>.<NAME>?update_mask=<PATHS>` |
| delete | `DELETE /api/2.1/unity-catalog/model-services/<C>.<S>.<NAME>` |

`update_mask` and `etag` are **query params** on update (and `etag` on delete), not body
fields. The request body for create and update is the bare `ModelService` object — the same
payload the CLI's `--json` takes.

```bash
# Create.
databricks api post \
  '/api/2.1/unity-catalog/model-services?parent=schemas/<CATALOG>.<SCHEMA>&model_service_id=my_model_service' \
  --json @body.json --profile <PROFILE>

# Get.
databricks api get \
  /api/2.1/unity-catalog/model-services/<CATALOG>.<SCHEMA>.<SERVICE> --profile <PROFILE>

# List.
databricks api get \
  '/api/2.1/unity-catalog/model-services?parent=schemas/<CATALOG>.<SCHEMA>' --profile <PROFILE>

# Update, conditional on the etag.
databricks api patch \
  '/api/2.1/unity-catalog/model-services/<CATALOG>.<SCHEMA>.<SERVICE>?update_mask=comment&etag=<ETAG>' \
  --json '{"comment":"Governed Llama endpoint"}' --profile <PROFILE>

# Delete.
databricks api delete \
  /api/2.1/unity-catalog/model-services/<CATALOG>.<SCHEMA>.<SERVICE> --profile <PROFILE>
```

Additional list query params (`page_size`, `page_token`, `view`) mirror the CLI flags. Raw REST
calls give you no client-side paging, so plan to follow the response's pagination token
yourself until it is absent rather than assuming one call returns everything. Confirm the
token's field name and any query-param spelling you have not used before against the
`/api/2.1/unity-catalog/` API reference.
