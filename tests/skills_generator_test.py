#!/usr/bin/env python3
"""Unit tests for the plugin.meta.json -> plugin manifests generator.

P1 made plugin.meta.json the single source of truth and generates every
target's plugin.json + marketplace.json from it, with a CI drift guard. These
tests pin that machinery (byte-reproducible generation, drift detection, skill
coverage) so a future refactor of a build_* renderer can't silently change a
target's output. Stdlib-only; run with:
  python3 -m unittest discover -s tests -p "*_test.py"
"""
import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("skills", _REPO / "scripts" / "skills.py")
assert _spec is not None
assert _spec.loader is not None
skills = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skills)


class GeneratedPluginsTest(unittest.TestCase):
    def setUp(self):
        self.meta = skills.load_meta(_REPO)

    def test_repo_is_canonical(self):
        # The committed plugin manifests must equal what the generator produces
        # from plugin.meta.json, and every skill must be covered. This pins the
        # committed state even if the validate wiring changes.
        self.assertEqual(skills.check_generated_plugins(_REPO, self.meta), [])
        self.assertEqual(skills.check_meta_skill_coverage(_REPO, self.meta), [])

    def test_generate_roundtrips_clean(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            written = skills.generate_plugins(root, self.meta)
            self.assertEqual(written, len(skills.generated_plugin_files(self.meta)))
            self.assertEqual(skills.check_generated_plugins(root, self.meta), [])

    def test_each_dir_has_generated_marker(self):
        # Every generated-manifest directory ships a README marker so a reader
        # browsing the folder sees it is generated.
        files = skills.generated_plugin_files(self.meta)
        for directory in skills._GENERATED_MANIFEST_DIRS:
            self.assertIn(f"{directory}/README.md", files)

    def test_content_drift_detected(self):
        # The root generated set is now the marketplace catalogs (the four
        # plugin.json moved into the bundle). Edit a catalog and expect drift.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skills.generate_plugins(root, self.meta)
            target = root / ".claude-plugin" / "marketplace.json"
            data = json.loads(target.read_text())
            data["description"] = "drifted"
            target.write_text(json.dumps(data, indent=2) + "\n")
            errors = skills.check_generated_plugins(root, self.meta)
            self.assertTrue(
                any("out of date" in e and ".claude-plugin/marketplace.json" in e for e in errors),
                errors,
            )

    def test_formatting_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skills.generate_plugins(root, self.meta)
            target = root / ".agents" / "plugins" / "marketplace.json"
            # Same content, non-canonical formatting (4-space + sorted keys).
            data = json.loads(target.read_text())
            target.write_text(json.dumps(data, indent=4, sort_keys=True) + "\n")
            errors = skills.check_generated_plugins(root, self.meta)
            self.assertTrue(
                any("canonical generated form" in e for e in errors), errors
            )

    def test_missing_file_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skills.generate_plugins(root, self.meta)
            (root / ".cursor-plugin" / "marketplace.json").unlink()
            errors = skills.check_generated_plugins(root, self.meta)
            self.assertTrue(
                any("Missing generated file .cursor-plugin/marketplace.json" in e for e in errors),
                errors,
            )

    def test_keyword_composition(self):
        kw = skills.build_keywords(self.meta)
        skill_kws = [s["keyword"] for s in self.meta["skills"].values()]
        expected = [
            *self.meta["keywords_lead"],
            *skill_kws,
            *self.meta["keywords_tail"],
        ]
        self.assertEqual(kw, expected)
        # No duplicate keywords (lead/tail must not collide with a skill keyword).
        self.assertEqual(len(kw), len(set(kw)))

    def test_all_targets_share_one_version(self):
        versions = {
            build(self.meta)["version"]
            for build in (
                skills.build_claude_plugin,
                skills.build_codex_plugin,
                skills.build_copilot_plugin,
                skills.build_cursor_plugin,
            )
        }
        self.assertEqual(versions, {self.meta["version"]})

    def test_name_is_databricks_everywhere(self):
        # The plugin name keys Cursor/Claude installs; the generator must never
        # emit anything but "databricks".
        for build in (
            skills.build_claude_plugin,
            skills.build_codex_plugin,
            skills.build_copilot_plugin,
            skills.build_cursor_plugin,
        ):
            self.assertEqual(build(self.meta)["name"], "databricks")

    def test_claude_plugin_has_no_hooks_key(self):
        # hooks/hooks.json is auto-loaded by Claude Code; declaring it double-loads.
        self.assertNotIn("hooks", skills.build_claude_plugin(self.meta))


class UnityGatewaySkillWiringTest(unittest.TestCase):
    """The databricks-unity-gateway skill ships wired up, not half-added.

    check_meta_skill_coverage catches a skill that is on disk but absent from
    meta (and vice versa) generically; this pins the specific wiring for the
    UC AI Gateway skill so a bad merge cannot quietly drop it or its keyword.
    """

    _NAME = "databricks-unity-gateway"

    def setUp(self):
        self.meta = skills.load_meta(_REPO)

    def test_in_meta_skills_map_with_keyword(self):
        self.assertEqual(
            self.meta["skills"].get(self._NAME), {"keyword": "unity-gateway"}
        )
        self.assertIn("unity-gateway", skills.build_keywords(self.meta))

    def test_skill_md_frontmatter(self):
        frontmatter = skills._read_frontmatter(
            _REPO / "skills" / self._NAME / "SKILL.md"
        )
        self.assertIsNotNone(frontmatter, "SKILL.md has no frontmatter block")
        self.assertIn(f"name: {self._NAME}", frontmatter)
        self.assertIn("description:", frontmatter)
        # Phase A shipped the first real content (model service CRUD) at 0.2.0;
        # 0.2.1 applied the doc-accuracy corrections found by auditing it against
        # the published guide, and 0.2.2 finalized the grants content. The
        # version stays pinned here so a bump is always a deliberate edit
        # landing alongside the content it describes.
        self.assertIn('version: "0.2.2"', frontmatter)
        # parent: databricks-core is what makes the routing row mandatory --
        # see RoutingCoverageTest.test_unity_gateway_has_routing_row.
        self.assertEqual(
            skills._skill_parent(_REPO / "skills" / self._NAME), "databricks-core"
        )

    def test_compatibility_marks_beta_and_rest_fallback(self):
        # Two load-bearing scaffold properties. The ai-gateway group is Beta, so
        # the skill must not read as stable, and it must offer the REST fallback
        # for a CLI that predates the group -- without those the scaffold implies
        # a settled CLI surface it has not verified. Asserted against the
        # compatibility value itself, not the whole frontmatter, so a stray
        # "Beta" in the description cannot satisfy this.
        frontmatter = skills._read_frontmatter(
            _REPO / "skills" / self._NAME / "SKILL.md"
        )
        compatibility = next(
            (
                line
                for line in frontmatter.splitlines()
                if line.startswith("compatibility:")
            ),
            None,
        )
        self.assertIsNotNone(compatibility, "SKILL.md has no compatibility line")
        self.assertIn("Beta", compatibility)
        self.assertIn("databricks api", compatibility)
        self.assertIn("/api/2.1/unity-catalog/", compatibility)


class UnityGatewayModelServiceCrudTest(unittest.TestCase):
    """Phase A content invariants: model service CRUD.

    These commands and name formats were verified against pinned upstream
    sources (databricks CLI cmd/workspace/ai-gateway/ai-gateway.go and
    databricks-sdk-go service/catalog), NOT against a live CLI -- the shipped
    v1.7.0 has no `ai-gateway` group. That makes them exactly the kind of fact a
    later edit can garble without anyone noticing, so each load-bearing one gets
    an assertion here. Content is read from the skill files rather than
    regenerated, so these fail on a bad hand-edit even when generation is clean.
    """

    _NAME = "databricks-unity-gateway"

    # The `<verb>-model-service(s)` CLI surface. Splitting create/get/delete
    # (singular) from list (plural) keeps a typo'd suffix from passing.
    _VERBS = (
        "create-model-service",
        "get-model-service",
        "list-model-services",
        "update-model-service",
        "delete-model-service",
    )

    @classmethod
    def setUpClass(cls):
        skill_dir = _REPO / "skills" / cls._NAME
        cls.skill_md = (skill_dir / "SKILL.md").read_text()
        # The detailed payloads may live either inline in SKILL.md or in the
        # references file; assert against the concatenation so a future split or
        # re-merge does not break these tests for the wrong reason.
        reference = skill_dir / "references" / "model-service-crud.md"
        cls.reference_md = reference.read_text() if reference.exists() else ""
        cls.combined = cls.skill_md + "\n" + cls.reference_md

    def test_crud_section_exists(self):
        self.assertIn("## Model services", self.skill_md)

    def test_all_five_verbs_documented(self):
        # Every CRUD verb must appear in SKILL.md itself, not only in the
        # reference file -- the overview is what an agent reads first.
        for verb in self._VERBS:
            with self.subTest(verb=verb):
                self.assertIn(verb, self.skill_md)

    def test_parent_uses_schemas_prefix(self):
        # PARENT / --parent take the typed `schemas/{catalog}.{schema}` form.
        self.assertIn("schemas/<CATALOG>.<SCHEMA>", self.skill_md)
        self.assertIn("--parent schemas/<CATALOG>.<SCHEMA>", self.skill_md)

    def test_get_update_delete_use_model_services_prefix(self):
        # NAME is `model-services/{catalog}.{schema}.{name}`, NOT the bare
        # three-level name. Assert the typed form is the one shown for each of
        # the three name-taking verbs.
        typed = "model-services/<CATALOG>.<SCHEMA>.<SERVICE>"
        self.assertIn(typed, self.skill_md)
        for verb in ("get-model-service", "update-model-service", "delete-model-service"):
            with self.subTest(verb=verb):
                # The typed NAME must appear in the same command invocation as
                # the verb (allowing a line continuation between them).
                self.assertRegex(
                    self.skill_md,
                    rf"{re.escape(verb)}\s*(?:\\\s*)?\n?\s*{re.escape(typed)}",
                    f"{verb} does not show the typed model-services/ NAME form",
                )

    def test_bare_vs_typed_name_gotcha_called_out(self):
        # The grants securable name is the BARE three-level name while
        # ai-gateway wants the typed form; conflating them is the documented
        # top gotcha, so the contrast must survive edits.
        self.assertIn("grants get model_service <CATALOG>.<SCHEMA>.<SERVICE>", self.skill_md)
        self.assertNotIn(
            "grants get model_service model-services/",
            self.combined,
            "grants must take the BARE name, never the typed model-services/ form",
        )

    # --- doc-accuracy corrections (audited against the published guide) -----

    def test_create_example_sets_traffic_percentage_100(self):
        # The guide's create examples all carry "traffic_percentage": 100 on a
        # single destination, and percentages must sum to 100. An earlier draft
        # omitted it and told readers to leave it unset -- exactly the kind of
        # wrong-but-plausible advice a copy-paste reader would ship.
        self.assertRegex(self.skill_md, r'"traffic_percentage":\s*100')
        # Every fenced snippet that defines a paygo destination must set it.
        for block in self._code_blocks(self.combined):
            if "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL" not in block:
                continue
            with self.subTest(block=block.strip()[:60]):
                self.assertRegex(
                    block,
                    r'"traffic_percentage":\s*\d+',
                    "a paygo destination snippet omits traffic_percentage",
                )

    def test_no_advice_to_leave_traffic_percentage_unset(self):
        # Guard the specific reversed claim that was corrected, so it cannot
        # creep back in via a copy-paste of the old wording.
        self.assertNotRegex(
            self.combined,
            r"[Ll]eave (?:it|`?traffic_percentage`?) unset",
            "traffic_percentage is required per destination; do not advise unsetting it",
        )
        self.assertRegex(self.combined, r"sum to 100")

    def test_create_needs_only_execute_on_routed_model(self):
        # The guide requires USE_CATALOG + USE_SCHEMA + CREATE_SERVICE on the
        # catalog/schema, plus EXECUTE on each routed MODEL -- not
        # USE_CATALOG/USE_SCHEMA on each model's parents too. Over-granting is a
        # least-privilege violation, so pin the corrected wording.
        self.assertIn("CREATE_SERVICE", self.skill_md)
        for doc in (self.skill_md, self.reference_md):
            if not doc:
                continue
            with self.subTest():
                self.assertNotRegex(
                    doc,
                    r"USE_CATALOG`? \+ `?USE_SCHEMA`? \+ `?EXECUTE`? on \*\*each referenced UC model",
                    "create must need only EXECUTE on a routed model",
                )
        # The corrected requirement is stated affirmatively somewhere.
        self.assertRegex(
            self.skill_md, r"EXECUTE`? on \*\*each model the service routes to"
        )

    def test_create_service_privilege_stated_plainly(self):
        # The privilege is confirmed by the guide, so the old "if your workspace
        # rejects it as an unknown privilege" hedge must be gone, replaced by the
        # SQL-vs-enum spelling note.
        self.assertNotIn("rejects it as an unknown privilege", self.combined)
        self.assertIn("CREATE SERVICE", self.combined)

    def test_ownership_and_namespace_facts_documented(self):
        # Two doc-confirmed gotchas: creator is owner and initially the only
        # principal who can query; model + model provider services share one
        # namespace per schema.
        self.assertRegex(self.skill_md, r"(?i)you become the owner")
        self.assertRegex(
            self.skill_md, r"(?i)only principal who\s+can query"
        )
        self.assertRegex(
            self.skill_md, r"(?i)share one name namespace|share a single name namespace"
        )

    # --- grants specifics (audited against the grant-access docs) -----------

    def test_rest_permissions_endpoint_documented(self):
        # Grants go through the UC permissions API, NOT the model-services CRUD
        # path. Both files must show it, and every fenced example of it must use
        # the securable type plus the BARE three-level name.
        path = "/api/2.1/unity-catalog/permissions/model_service/"
        self.assertIn(path, self.skill_md)
        self.assertIn(path, self.reference_md)
        found = False
        for block in self._code_blocks(self.combined):
            for match in re.finditer(
                r"/api/2\.1/unity-catalog/permissions/(\S+)", block
            ):
                found = True
                tail = match.group(1)
                with self.subTest(tail=tail):
                    self.assertTrue(
                        tail.startswith("model_service/"),
                        "permissions path needs the model_service securable type",
                    )
                    name = tail[len("model_service/"):]
                    self.assertFalse(
                        name.startswith("model-services/"),
                        "permissions path takes the BARE name, not the typed form",
                    )
        self.assertTrue(found, "no fenced permissions-API example to check")

    def test_system_ai_default_execute_exception(self):
        # Counterpart to owner-only-by-default: system.ai services grant EXECUTE
        # to all account users up front, so they are restricted, not granted.
        self.assertRegex(
            self.skill_md, r"(?i)all account users can query"
        )
        self.assertRegex(self.combined, r"(?i)system\.ai")

    def test_grants_update_authority_documented(self):
        # Running grants update is not open to any caller.
        self.assertRegex(
            self.skill_md, r"(?i)\*\*Changing\*\* grants|Changing grants"
        )
        for token in ("MANAGE", "admin"):
            with self.subTest(token=token):
                self.assertIn(token, self.skill_md)

    def test_grants_get_all_vs_own_documented(self):
        # The all-grants-vs-own-grants split is a silent-wrong-answer trap: a
        # partial list looks like a complete one.
        self.assertRegex(self.skill_md, r"(?i)only their own")
        self.assertIn("READ_METADATA", self.skill_md)

    def test_viewing_grants_not_conflated_with_reading_metadata(self):
        # `databricks grants get` (permissions) and `ai-gateway
        # get-model-service` / `list-model-services` (the resource) are
        # different authorizations. Asserted PER FILE: checking the combined
        # text let either file drop the distinction while the other's wording
        # kept the assertion green.
        self.assertRegex(
            self.skill_md,
            r"(?i)distinct from `?get-model-service",
            "SKILL.md must separate viewing grants from reading the resource",
        )
        self.assertRegex(
            self.reference_md,
            r"(?i)distinct question from reading the \*?service metadata",
            "the reference must separate viewing grants from reading metadata",
        )

    def test_no_sql_grant_form_invented(self):
        # The docs offer no SQL GRANT for model services; inventing one would
        # send readers to a statement that does not parse.
        for doc in (self.skill_md, self.reference_md):
            if not doc:
                continue
            with self.subTest():
                self.assertNotRegex(
                    doc, r"(?i)GRANT\s+\w+\s+ON\s+(?:MODEL\s+)?SERVICE\b"
                )
        self.assertRegex(self.combined, r"(?i)no SQL `?GRANT`? form")

    def test_inference_table_select_and_propagation_noted(self):
        # Per file, for the same reason as above: SKILL.md states propagation in
        # its own words and the reference in its own, so assert each rather than
        # letting one cover for the other.
        # SKILL.md states propagation twice (a grants bullet and a
        # troubleshooting row). Require BOTH: with a bare substring check,
        # deleting the bullet still passed because the row matched.
        self.assertRegex(
            self.skill_md,
            r"- Privilege changes can take \*\*a few minutes to propagate\*\*",
            "the grants section must carry the propagation caveat",
        )
        self.assertRegex(
            self.skill_md,
            r"\| Privilege changes take a few minutes to propagate",
            "the troubleshooting table must carry the propagation row",
        )
        self.assertRegex(
            self.reference_md, r"(?i)[Pp]ropagation is not instant|minutes to take effect"
        )
        # Inference-table payload reads need SELECT on the table, in both files.
        for doc, label in ((self.skill_md, "SKILL.md"), (self.reference_md, "reference")):
            with self.subTest(doc=label):
                self.assertRegex(
                    doc,
                    r"(?i)`?SELECT`? on (?:that|the) table",
                    f"{label} must note SELECT on the inference table",
                )

    def test_create_documents_paygo_destination_type(self):
        # The anchor example's destination_type enum value, verbatim.
        self.assertIn(
            "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL", self.skill_md
        )
        # ...paired with the pay_per_token_config variant it selects and the
        # typed `models/` UC model name.
        self.assertIn("pay_per_token_config", self.skill_md)
        self.assertIn("models/system.ai.", self.skill_md)

    def test_create_config_is_required_and_has_no_flag(self):
        # `config` is required on create and there is NO --config flag; it must
        # go through --json. Documenting a --config flag would be wrong.
        self.assertNotIn("--config ", self.combined)
        self.assertRegex(self.skill_md, r"no `--config` flag")

    def test_update_mask_is_positional(self):
        # UPDATE_MASK is the second POSITIONAL arg; there is no --update-mask
        # flag. The prose must say so, and -- the half that actually catches a
        # bad example -- no runnable snippet may pass it as a flag. Checked
        # against the fenced code blocks rather than the raw text, since the
        # prose necessarily mentions `--update-mask` to deny it exists.
        self.assertIn("update-model-service NAME UPDATE_MASK", self.combined)
        self.assertIn("no `--update-mask` flag", self.combined)
        for block in self._code_blocks(self.combined):
            self.assertNotIn(
                "--update-mask",
                block,
                "a snippet passes --update-mask; UPDATE_MASK is positional",
            )

    @staticmethod
    def _code_blocks(text: str) -> list[str]:
        # Fenced blocks only -- the runnable commands, as distinct from prose
        # that may name a flag in order to say it does not exist.
        return re.findall(r"^```[^\n]*\n(.*?)^```", text, re.MULTILINE | re.DOTALL)

    def test_code_blocks_use_correct_name_forms(self):
        # No runnable snippet may pass a bare three-level name to a verb that
        # requires the typed model-services/ form. This is the invariant a
        # copy-paste reader actually depends on.
        for block in self._code_blocks(self.combined):
            for verb in ("get-model-service", "update-model-service", "delete-model-service"):
                for match in re.finditer(
                    rf"{re.escape(verb)}\s*(?:\\\s*\n\s*)?(\S+)", block
                ):
                    arg = match.group(1)
                    # Skip the usage-synopsis form (`... NAME UPDATE_MASK`) and
                    # shell-substitution contexts.
                    if arg in ("NAME", "\\") or arg.startswith("$"):
                        continue
                    with self.subTest(verb=verb, arg=arg):
                        self.assertTrue(
                            arg.startswith("model-services/"),
                            f"{verb} snippet passes {arg!r}, not a model-services/ name",
                        )

    def test_unsupported_update_mask_paths_flagged(self):
        # Wildcard and intermediate paths are rejected by the API; a reader who
        # tries `*` gets an INVALID_ARGUMENT, so the caveat is load-bearing.
        self.assertIn("config.routing.destinations", self.skill_md)
        self.assertRegex(self.skill_md, r"[Ww]ildcard `\*` is \*\*not\*\* supported")

    def test_etag_concurrency_documented(self):
        self.assertIn("--etag", self.skill_md)
        self.assertIn("etag", self.skill_md.lower())

    def test_rest_fallback_path_documented(self):
        # The REST base path, plus the fact that update is PATCH with
        # update_mask as a query param (verified against the pinned SDK).
        self.assertIn("/api/2.1/unity-catalog/model-services", self.skill_md)
        self.assertIn("databricks api patch", self.skill_md)
        self.assertRegex(self.skill_md, r"update_mask=")

    # --- copy-paste hazards -------------------------------------------------
    # Each of the five below is a shape that LOOKS plausible but fails against
    # the real API. Prose is free to discuss them; a fenced snippet must not
    # contain one, because fenced snippets get copy-pasted verbatim.

    def test_no_snippet_wraps_body_in_model_service_key(self):
        # --json unmarshals DIRECTLY into the ModelService body. Wrapping it as
        # {"model_service": ...} is the natural guess from the REST field name
        # and it silently produces a body with no config.
        for block in self._code_blocks(self.combined):
            self.assertNotIn(
                '"model_service"',
                block,
                'a snippet wraps the body as {"model_service": ...}; --json takes '
                "the ModelService fields directly",
            )

    def test_rest_paths_use_bare_name_segment(self):
        # The REST path is /model-services/<C>.<S>.<NAME> -- the typed prefix IS
        # the path segment, so re-adding it (or a schemas/ segment) 404s.
        for block in self._code_blocks(self.combined):
            for line in block.splitlines():
                if "databricks api" not in line and "/model-services" not in line:
                    continue
                with self.subTest(line=line.strip()[:70]):
                    self.assertNotIn("model-services/model-services/", line)
                    # A resource path must not carry a schemas/ segment; that
                    # form only belongs in the ?parent= query param.
                    self.assertNotRegex(
                        line,
                        r"/model-services/schemas/",
                        "REST resource path must not contain a schemas/ segment",
                    )

    def test_grants_snippets_use_bare_name(self):
        # The grants securable name is the BARE three-level name.
        for block in self._code_blocks(self.combined):
            for line in block.splitlines():
                if "grants" not in line or "model_service" not in line:
                    continue
                with self.subTest(line=line.strip()[:70]):
                    self.assertNotIn(
                        "model-services/",
                        line,
                        "grants takes the BARE name, not the typed form",
                    )

    def test_create_model_service_id_is_a_leaf(self):
        # MODEL_SERVICE_ID is the leaf name only. Passing a dotted three-level
        # name or a typed path there is the most likely create-time mistake.
        found = False
        for block in self._code_blocks(self.combined):
            for match in re.finditer(
                r"create-model-service\s*\\?\s*\n?\s*(schemas/\S+)\s+(\S+)", block
            ):
                found = True
                leaf = match.group(2)
                with self.subTest(leaf=leaf):
                    self.assertNotIn("/", leaf, "MODEL_SERVICE_ID must be a leaf name")
                    self.assertNotIn(".", leaf, "MODEL_SERVICE_ID must be a leaf name")
        self.assertTrue(found, "no fenced create-model-service example to check")

    def test_view_flag_only_takes_basic_or_full(self):
        # The CLI enum is exactly [BASIC, FULL]; anything else is rejected.
        for block in self._code_blocks(self.combined):
            for match in re.finditer(r"--view[ =]+(\S+)", block):
                value = match.group(1)
                with self.subTest(value=value):
                    self.assertIn(
                        value,
                        ("BASIC", "FULL", "BASIC|FULL"),
                        "--view accepts only BASIC or FULL",
                    )

    def test_least_privilege_grants_documented(self):
        # Create-side and invoke-side privileges, and never a blanket grant.
        for privilege in ("CREATE_SERVICE", "USE_SCHEMA", "USE_CATALOG", "EXECUTE"):
            with self.subTest(privilege=privilege):
                self.assertIn(privilege, self.skill_md)
        self.assertIn("never `ALL PRIVILEGES`", self.skill_md)
        # ALL_PRIVILEGES may only ever appear as the thing NOT to grant.
        self.assertNotRegex(self.combined, r'add":\s*\[\s*"ALL_PRIVILEGES')

    def test_reference_link_resolves(self):
        # If SKILL.md links the detailed reference, the target must exist --
        # a dead relative link is invisible until a reader follows it.
        skill_dir = _REPO / "skills" / self._NAME
        for target in re.findall(r"\]\((references/[^)#]+)\)", self.skill_md):
            with self.subTest(target=target):
                self.assertTrue(
                    (skill_dir / target).is_file(), f"dead link: {target}"
                )

    def test_later_phases_still_marked_pending(self):
        # Phase A is CRUD only. MCP services, model provider services, and the
        # advanced config must stay on the roadmap, not read as shipped.
        self.assertIn("## Coming in stages", self.skill_md)
        for pending in ("MCP services", "Model provider services"):
            with self.subTest(pending=pending):
                self.assertIn(pending, self.skill_md)

    def test_documentation_safety_placeholders(self):
        # Repo-wide doc-safety rule: placeholder host and workspace id only.
        self.assertIn("company-workspace.cloud.databricks.com", self.skill_md)
        self.assertIn("1111111111111111", self.skill_md)
        # No real-looking bearer token literals anywhere in the skill.
        self.assertNotRegex(self.combined, r"\bdap[ip][0-9a-f]{16,}")


class MetaSkillCoverageTest(unittest.TestCase):
    def _make_skill(self, root: Path, name: str) -> None:
        skill_dir = root / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\n---\n")

    def test_clean(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(root, "databricks-core")
            meta = {"skills": {"databricks-core": {"keyword": "cli"}}}
            self.assertEqual(skills.check_meta_skill_coverage(root, meta), [])

    def test_disk_skill_missing_from_meta(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(root, "databricks-core")
            self._make_skill(root, "databricks-newthing")
            meta = {"skills": {"databricks-core": {"keyword": "cli"}}}
            errors = skills.check_meta_skill_coverage(root, meta)
            self.assertTrue(any("databricks-newthing" in e for e in errors), errors)

    def test_meta_entry_without_disk_skill(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(root, "databricks-core")
            meta = {
                "skills": {
                    "databricks-core": {"keyword": "cli"},
                    "databricks-ghost": {"keyword": "ghost"},
                }
            }
            errors = skills.check_meta_skill_coverage(root, meta)
            self.assertTrue(any("databricks-ghost" in e for e in errors), errors)

    def test_missing_keyword(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(root, "databricks-core")
            meta = {"skills": {"databricks-core": {}}}
            errors = skills.check_meta_skill_coverage(root, meta)
            self.assertTrue(any("keyword" in e for e in errors), errors)


class ManifestFileReferenceTest(unittest.TestCase):
    def _make_skill(
        self,
        root: Path,
        name: str,
        repo_dir: str = "skills",
        files: tuple[str, ...] = (),
    ) -> None:
        skill_dir = root / repo_dir / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
        for file_rel in files:
            target = skill_dir / file_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"{file_rel}\n")

    def _write_manifest(self, root: Path, manifest_skills: dict) -> None:
        manifest = {"version": "2", "skills": manifest_skills}
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    def test_absent_manifest_is_ok_for_source_only_mirror(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(skills.check_manifest_file_references(Path(d)), [])

    def test_existing_skill_files_are_clean(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(root, "databricks-core", files=("references/setup.md",))
            self._write_manifest(
                root,
                {
                    "databricks-core": {
                        "repo_dir": "skills",
                        "files": ["SKILL.md", "references/setup.md"],
                    }
                },
            )
            self.assertEqual(skills.check_manifest_file_references(root), [])

    def test_missing_skill_directory_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_manifest(
                root,
                {
                    "databricks-ai-runtime": {
                        "repo_dir": "skills",
                        "files": ["SKILL.md"],
                    }
                },
            )
            errors = skills.check_manifest_file_references(root)
            self.assertTrue(
                any(
                    "databricks-ai-runtime" in e
                    and "skills/databricks-ai-runtime" in e
                    for e in errors
                ),
                errors,
            )

    def test_missing_skill_file_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(root, "databricks-core")
            self._write_manifest(
                root,
                {
                    "databricks-core": {
                        "repo_dir": "skills",
                        "files": ["SKILL.md", "references/missing.md"],
                    }
                },
            )
            errors = skills.check_manifest_file_references(root)
            self.assertTrue(
                any(
                    "references/missing.md" in e and "does not exist" in e
                    for e in errors
                ),
                errors,
            )

    def test_unsafe_manifest_file_path_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(root, "databricks-core")
            self._write_manifest(
                root,
                {
                    "databricks-core": {
                        "repo_dir": "skills",
                        "files": ["SKILL.md", "../outside.md"],
                    }
                },
            )
            errors = skills.check_manifest_file_references(root)
            self.assertTrue(any("unsafe file path" in e for e in errors), errors)


class SkillFrontmatterTest(unittest.TestCase):
    def _make_skill(self, root: Path, name: str, description: str) -> None:
        skill_dir = root / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n"
        )

    def test_repo_skills_are_clean(self):
        # Pins the databricks-app-design fix and guards every shipped skill: no
        # SKILL.md may carry a description a strict YAML parser would reject.
        self.assertEqual(skills.check_skill_frontmatter(_REPO), [])

    def test_unquoted_colon_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(
                root, "databricks-bad", "Use when answering questions: pick a chart."
            )
            errors = skills.check_skill_frontmatter(root)
            self.assertTrue(
                any("databricks-bad" in e and "unquoted ':'" in e for e in errors),
                errors,
            )

    def test_quoted_colon_ok(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(
                root, "databricks-good", '"Use when answering questions: pick a chart."'
            )
            self.assertEqual(skills.check_skill_frontmatter(root), [])

    def test_unquoted_no_colon_ok(self):
        # The common, valid shape: a plain bare scalar with no colon. Guards
        # against the regex over-matching and flagging legitimate descriptions.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(
                root, "databricks-plain", "Use when building dashboards and charts."
            )
            self.assertEqual(skills.check_skill_frontmatter(root), [])

    def _make_skill_raw(self, root: Path, dirname: str, frontmatter: str) -> None:
        # For shapes _make_skill can't express (block scalars, absent fields).
        skill_dir = root / "skills" / dirname
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n")

    def test_long_name_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            name = "databricks-" + "x" * skills.MAX_SKILL_NAME_LEN
            self._make_skill(root, name, "Use when building dashboards.")
            errors = skills.check_skill_frontmatter(root)
            self.assertTrue(
                any("character name" in e for e in errors), errors
            )

    def test_name_at_limit_ok(self):
        # Boundary: exactly at the cap must pass, so the check is > and not >=.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            name = "d" * skills.MAX_SKILL_NAME_LEN
            self._make_skill(root, name, "Use when building dashboards.")
            self.assertEqual(skills.check_skill_frontmatter(root), [])

    def test_missing_name_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill_raw(
                root, "databricks-nameless", "description: Use when charting."
            )
            errors = skills.check_skill_frontmatter(root)
            self.assertTrue(
                any("missing a 'name'" in e for e in errors), errors
            )

    def test_long_description_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            desc = "word " * (skills.MAX_SKILL_DESCRIPTION_LEN // 4)
            self._make_skill(root, "databricks-verbose", desc)
            errors = skills.check_skill_frontmatter(root)
            self.assertTrue(
                any("character description" in e for e in errors), errors
            )

    def test_description_at_limit_ok(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            desc = "d" * skills.MAX_SKILL_DESCRIPTION_LEN
            self._make_skill(root, "databricks-atlimit", desc)
            self.assertEqual(skills.check_skill_frontmatter(root), [])

    def test_block_scalar_description_over_limit_flagged(self):
        # The regression a first-line-only regex misses: a folded scalar's
        # `description:` line holds just the two-character '>-' indicator, so
        # the cap has to be applied to the RESOLVED value. databricks-dbsql
        # ships this shape, which is why it matters.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            line = "filler " * 30
            body = "name: databricks-folded\ndescription: >-\n" + "".join(
                f"  {line.strip()}\n" for _ in range(8)
            )
            self._make_skill_raw(root, "databricks-folded", body.rstrip("\n"))
            errors = skills.check_skill_frontmatter(root)
            self.assertTrue(
                any("character description" in e for e in errors), errors
            )

    def test_block_scalar_description_under_limit_ok(self):
        # Control for the above: the same folded shape, short, must not flag.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            body = (
                "name: databricks-folded-ok\ndescription: >-\n"
                "  Use when building dashboards\n  and charts.\n"
            )
            self._make_skill_raw(root, "databricks-folded-ok", body.rstrip("\n"))
            self.assertEqual(skills.check_skill_frontmatter(root), [])

    # The three holes review found in measuring a description by delegating to
    # discovery.extract_description_from_skill. Each let an over-limit
    # description pass silently, which is the exact failure the check exists to
    # stop, so each gets a flagging test and a short control.

    def test_literal_triple_dash_in_description_still_measured(self):
        # extract_description_from_skill ends the frontmatter at the first '---'
        # ANYWHERE, so a description containing one was truncated to a few
        # characters and sailed past the limit. Measured from the frontmatter
        # block instead, which only closes on a delimiter line.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            tail = "z" * (skills.MAX_SKILL_DESCRIPTION_LEN + 100)
            self._make_skill_raw(
                root,
                "databricks-dashes",
                f'name: databricks-dashes\ndescription: "start --- {tail}"',
            )
            errors = skills.check_skill_frontmatter(root)
            self.assertTrue(
                any("character description" in e for e in errors), errors
            )

    def test_short_description_containing_triple_dash_ok(self):
        # Control for the above: the '---' must not itself trip anything.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill_raw(
                root,
                "databricks-dashes-ok",
                'name: databricks-dashes-ok\ndescription: "before --- after"',
            )
            self.assertEqual(skills.check_skill_frontmatter(root), [])

    def test_block_scalar_header_with_trailing_comment_measured(self):
        # `>- # note` is a valid header but was not one of the six bare forms,
        # so it fell through as a plain scalar and measured as the header token.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            body = "\n".join("  " + "w" * 100 for _ in range(15))
            self._make_skill_raw(
                root,
                "databricks-hdrcomment",
                f"name: databricks-hdrcomment\ndescription: >- # note\n{body}",
            )
            errors = skills.check_skill_frontmatter(root)
            self.assertTrue(
                any("character description" in e for e in errors), errors
            )

    def test_block_scalar_indentation_indicator_measured(self):
        # Same class of gap for an explicit indentation indicator such as `>2`.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            body = "\n".join("  " + "w" * 100 for _ in range(15))
            self._make_skill_raw(
                root,
                "databricks-indent",
                f"name: databricks-indent\ndescription: >2\n{body}",
            )
            errors = skills.check_skill_frontmatter(root)
            self.assertTrue(
                any("character description" in e for e in errors), errors
            )

    def test_short_block_scalar_with_trailing_comment_ok(self):
        # Control: the header forms above must not flag when the body is short.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill_raw(
                root,
                "databricks-hdr-ok",
                "name: databricks-hdr-ok\ndescription: >- # note\n"
                "  Use when building dashboards\n  and charts.",
            )
            self.assertEqual(skills.check_skill_frontmatter(root), [])

    def test_plain_multiline_description_measured(self):
        # A plain (unquoted) scalar can run onto indented continuation lines.
        # Measuring only the `description:` line let a short opening line hide
        # an over-limit folded body - the exact violation this check exists for.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            body = "\n".join("  " + "w" * 100 for _ in range(15))
            self._make_skill_raw(
                root,
                "databricks-plainmulti",
                f"name: databricks-plainmulti\ndescription: Short first line\n{body}",
            )
            errors = skills.check_skill_frontmatter(root)
            self.assertTrue(
                any("character description" in e for e in errors), errors
            )

    def test_short_plain_multiline_description_ok(self):
        # Control: folding continuation lines must not flag a short value, and a
        # sibling key at column 0 must end the run rather than be folded in.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill_raw(
                root,
                "databricks-plainmulti-ok",
                "name: databricks-plainmulti-ok\n"
                "description: Use when building\n  dashboards and charts.\n"
                "parent: databricks-core",
            )
            self.assertEqual(skills.check_skill_frontmatter(root), [])


class BundleTest(unittest.TestCase):
    """The per-provider bundles under plugins/databricks/<provider>/."""

    # Source dirs the per-provider build copies/renders from.
    _SRC_DIRS = ("skills", "hooks", "commands", "rules", "assets")

    def setUp(self):
        self.meta = skills.load_meta(_REPO)

    def test_repo_bundle_is_canonical(self):
        # The committed bundle equals a fresh build (copies + generated
        # plugin.json + rendered commands), with no missing or extra files.
        self.assertEqual(skills.check_generated_bundle(_REPO, self.meta), [])

    def _seed(self, root: Path) -> Path:
        # Copy the real source tree (skills/, the generated wiring+routing in
        # hooks/ and rules/, the command templates, assets/) so a per-provider
        # build can run, then build the bundle.
        for d in self._SRC_DIRS:
            shutil.copytree(_REPO / d, root / d)
        skills.generate_bundle(root, self.meta)
        return root

    def test_generate_bundle_roundtrips_clean(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            self.assertEqual(skills.check_generated_bundle(root, self.meta), [])

    def test_copied_file_drift_detected(self):
        # Hand-editing a copied file inside a provider folder must fail the check.
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            (root / "plugins/databricks/claude/skills/databricks-core/SKILL.md").write_text("tampered")
            errors = skills.check_generated_bundle(root, self.meta)
            self.assertTrue(any("out of date" in e for e in errors), errors)

    def test_extra_file_detected(self):
        # A hand-added file in a provider folder (no source) must be flagged.
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            (root / "plugins/databricks/codex/skills/STRAY.md").write_text("hand-added")
            errors = skills.check_generated_bundle(root, self.meta)
            self.assertTrue(
                any("STRAY.md" in e and "not produced by the generator" in e for e in errors),
                errors,
            )

    def test_generated_plugin_json_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            target = root / "plugins/databricks/claude/.claude-plugin/plugin.json"
            data = json.loads(target.read_text())
            data["version"] = "9.9.9"
            target.write_text(json.dumps(data, indent=2) + "\n")
            errors = skills.check_generated_bundle(root, self.meta)
            self.assertTrue(
                any("claude/.claude-plugin/plugin.json" in e and "out of date" in e for e in errors),
                errors,
            )

    def test_copilot_has_no_router(self):
        # Each provider folder ships only what it uses: Copilot's wiring does not
        # reference the router, so no router script or routing data is copied.
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            cph = root / "plugins/databricks/copilot/hooks"
            self.assertFalse((cph / "databricks-router.py").exists())
            self.assertFalse((cph / "_routing_data.json").exists())
            self.assertTrue((cph / "databricks-context.py").exists())

    def test_copilot_bundle_uses_root_hooks_file(self):
        # VS Code treats .github/plugin/plugin.json as a Copilot-format plugin;
        # its hook auto-discovery looks for hooks.json at the plugin root, not
        # hooks/hooks.json (the Claude-format location).
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            cph = root / "plugins/databricks/copilot"
            self.assertTrue((cph / "hooks.json").exists())
            self.assertFalse((cph / "hooks" / "hooks.json").exists())

    def test_bundle_skips_unpublished_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for dd in self._SRC_DIRS:
                shutil.copytree(_REPO / dd, root / dd)
            noise = root / "skills" / "databricks-core" / "__pycache__"
            noise.mkdir(parents=True, exist_ok=True)
            (noise / "x.pyc").write_text("x")
            (root / "skills" / "databricks-core" / ".DS_Store").write_text("x")
            for filename in skills.UNPUBLISHED_FILENAMES:
                (root / "skills" / "databricks-core" / filename).write_text("x")
            skills.generate_bundle(root, self.meta)
            seeded = root / "plugins/databricks/claude/skills/databricks-core"
            self.assertFalse((seeded / ".DS_Store").exists())
            self.assertFalse((seeded / "__pycache__").exists())
            for filename in skills.UNPUBLISHED_FILENAMES:
                self.assertFalse((seeded / filename).exists())


class ScopedSourcesTest(unittest.TestCase):
    """Every marketplace catalog points a scoped source at its provider subfolder."""

    def setUp(self):
        self.meta = skills.load_meta(_REPO)
        self.subdir = self.meta["marketplace"]["source"]["subdir"]

    def test_repo_catalogs_are_scoped(self):
        self.assertEqual(skills.check_scoped_sources(self.meta), [])

    def test_each_catalog_points_at_its_provider_subfolder(self):
        # Currently ref "main" (the bundle is committed there); the tag-pinning
        # follow-up flips marketplace.source.ref_template to "v{version}".
        self.assertEqual(skills.marketplace_ref(self.meta), "main")
        claude = skills.build_claude_marketplace(self.meta)["plugins"][0]["source"]
        self.assertEqual(claude["path"], f"{self.subdir}/claude")
        self.assertEqual(claude["ref"], "main")
        codex = skills.build_codex_marketplace(self.meta)["plugins"][0]["source"]
        self.assertEqual(codex["path"], f"{self.subdir}/codex")

    def test_cursor_source_is_bare_provider_subfolder_no_ref(self):
        # Cursor cannot pin a ref; its source is the bare relative subfolder.
        cursor = skills.build_cursor_marketplace(self.meta)["plugins"][0]["source"]
        self.assertEqual(cursor, f"{self.subdir}/cursor")

    def test_wrong_subfolder_rejected(self):
        # check_scoped_sources requires each catalog's path to be its own provider
        # subfolder; a source pointing elsewhere (here the whole repo) must fail.
        bad = json.loads(json.dumps(self.meta))
        bad["marketplace"]["source"]["subdir"] = "."
        self.assertTrue(skills.check_scoped_sources(bad))


class GenerateAllTest(unittest.TestCase):
    """The one generate sequence shared by the CLI and the release bump.

    The release bump (bump_version.py) and `skills.py generate` once held two
    hand-maintained copies of the step list; the release copy dropped the
    per-skill asset sync, so a release regenerated everything except the bundled
    icons and then failed its own validate on "Stale 'assets/databricks.png'".
    Both now call generate_all, and these tests pin that it (a) re-syncs stale
    assets and (b) leaves a self-consistent tree.
    """

    # Source dirs generate_all reads from. rules/ is intentionally omitted: it is
    # produced by generate_routing (rules/databricks-routing.mdc + README), so it
    # need not -- and in a source-only checkout cannot -- be seeded. Keeping it out
    # lets this test run on the bare mirror too, not just the published tree.
    _SRC_DIRS = ("skills", "hooks", "commands", "assets", "metaplugin")

    def setUp(self):
        self.meta = skills.load_meta(_REPO)

    def _seed(self, root: Path) -> Path:
        for d in self._SRC_DIRS:
            shutil.copytree(_REPO / d, root / d)
        return root

    def _meta_at(self, version: str) -> dict:
        # The committed-version source (version.meta.json) is excluded from the
        # source-only mirror, so build a version-matched meta explicitly rather
        # than relying on load_meta to resolve one.
        meta = dict(self.meta)
        meta["version"] = version
        return meta

    def test_generate_all_roundtrips_clean(self):
        # A full generate from source must satisfy EVERY drift check, so a
        # regression that drops or mis-orders any sub-step is caught here. The
        # bundle check alone is not enough: it validates the bundle against the
        # root wiring it copied, not the root wiring against meta, and it never
        # sees the root marketplace catalogs or manifest.json (neither ships in
        # the bundle). So assert each generated surface independently.
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            skills.generate_all(root, version_override="9.9.9")
            meta = self._meta_at("9.9.9")
            self.assertEqual(skills.check_codex_metadata(root), [])
            self.assertEqual(skills.check_generated_plugins(root, meta), [])
            self.assertEqual(skills.check_generated_routing(root, meta), [])
            self.assertEqual(skills.check_generated_hooks(root, meta), [])
            self.assertTrue(skills.validate_manifest(root))
            self.assertEqual(skills.check_manifest_file_references(root), [])
            self.assertEqual(skills.check_generated_bundle(root, meta), [])

    def test_generate_all_resyncs_stale_skill_asset(self):
        # The exact regression: a stale per-skill icon must be re-synced by the
        # generate sequence, not survive it.
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            stale = root / "skills/databricks-core/assets/databricks.png"
            stale.write_bytes(b"STALE")
            self.assertTrue(
                any(
                    "Stale 'assets/databricks.png'" in e and "databricks-core" in e
                    for e in skills.check_codex_metadata(root)
                ),
                "expected the corrupted icon to be flagged before generate_all",
            )
            skills.generate_all(root, version_override="9.9.9")
            self.assertEqual(skills.check_codex_metadata(root), [])

    def test_generate_all_excludes_unpublished_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            core = root / "skills/databricks-core"
            for filename in skills.UNPUBLISHED_FILENAMES:
                (core / filename).write_text("universe-only")

            result = skills.generate_all(root, version_override="9.9.9")

            core_manifest = result["manifest"]["skills"]["databricks-core"]
            manifest_files = set(core_manifest["files"])
            self.assertTrue(manifest_files.isdisjoint(skills.UNPUBLISHED_FILENAMES))
            bundled_core = root / "plugins/databricks/claude/skills/databricks-core"
            for filename in skills.UNPUBLISHED_FILENAMES:
                self.assertFalse((bundled_core / filename).exists())


if __name__ == "__main__":
    unittest.main()
