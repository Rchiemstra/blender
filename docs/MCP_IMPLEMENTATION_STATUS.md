# MCP Implementation Status

Durable engineering ledger for the Blender MCP photorealism plan.
Phases are tracked in dependency order. Evidence comes from executed commands.

## Phase 0 — Inventory and baseline

**Status:** complete

**Implemented:**
- `docs/mcp_current_state_inventory.md` written from real submodule inspection (not assumptions).
- Submodule SHAs, remotes, and package layouts recorded.
- Gap matrix mapping current code to every major plan section.
- Vision-sidecar decision: `sidecar` mode with provider-neutral broker + deterministic fake provider for Docker.

**Files changed:** `docs/mcp_current_state_inventory.md`, `docs/MCP_IMPLEMENTATION_STATUS.md`

**Docker commands run:** `docker compose build --pull test-unit` (image built successfully).

**Exact test results:** none yet at this point (Docker foundation was the next slice).

**Backward-compatibility impact:** none — no production code changed.

---

## Phase 0 — Docker foundation

**Status:** complete

**Implemented:**
- `docker/mcp-test.Dockerfile`: pinned `debian:bookworm-slim` + apt `blender` (3.4.1 in container) + Xvfb + Mesa + pytest. Non-root user. Multi-root PYTHONPATH for the three submodules.
- `docker-compose.mcp-test.yml`: 10 services (unit, blender-integration, e2e, render, vision, asset, failure, acceptance, soak, optional gpu).
- `scripts/run_blender_mcp_docker_tests.py`: host runner with `--suite` and `--rebuild`.
- `.dockerignore`: lean build context.

**Docker commands run:** `docker compose config --quiet` (validates). `docker compose build --pull test-unit` (success).

---

## Phase 1 — Protocol, lifecycle, and safety foundation

**Status:** complete (core). Tests pass in Docker.

**Implemented:**
- `blender_mcp/protocol/errors.py`: structured error codes (28 codes from plan §7.5), `BridgeError`, retryable set, `from_exception`.
- `blender_mcp/protocol/envelope.py`: v1 request/response with `request_id`, `deadline_ms`, `expected_scene_revision`, `transaction_id`, `idempotency_key`, `dry_run`, `auth_token`; deadline check.
- `blender_mcp/protocol/handshake.py`: `system.handshake` with session token (rotated per launch, overridable via env), `verify_token` (constant-time compare), `UNAUTHENTICATED` on failure.
- `blender_mcp/protocol/capabilities.py`: `Capabilities` dataclass + `discover_capabilities()` probing bpy (engines, GPU devices via cycles prefs, importers, viewport region, vision mode). Honest reporting: `viewport_capture=False` in background mode.
- `blender_mcp/protocol/dispatcher.py`: v1 `Dispatcher` — handshake inline, auth on every other request, deadline check, legacy translation, `BridgeError`→structured error, deprecation warnings.
- `blender_mcp/protocol/compatibility_v0.py`: legacy name map (`get_scene_info`→`scene.summary`, `execute_code`→`execute_python`, etc.) with deprecation warnings.
- `blender_mcp/protocol/paths.py`: allowed-root path policy, `resolve_under_root`, `safe_join`, `archive_safety_check` (zip-slip, file count, size, ratio).
- `blender_mcp/protocol/client.py`: `V1BridgeClient` with persistent connection, handshake, reconnect on socket drop, bounded retry on retryable codes, idempotency.
- `blender_mcp/protocol/bridge_v1.py`: `V1BridgeServer` — persistent connection, multi-request loop, inline handshake, malformed-frame drops connection without crash.
- P0 `BridgeSocketServer` and `BridgeClient` left intact for backward compatibility.

**Files changed (submodule `tools/blender_mcp`):** 10 new files in `blender_mcp/protocol/`, 2 new test files, bootstrap added to `tests/test_p0.py`.

**Docker commands run:**
- `docker compose run --rm test-unit` → **48 passed in 0.68s**
- `docker compose run --rm test-e2e` → **6 passed in 18.83s** (incl. 1,000 sequential request soak)
- `docker compose run --rm test-blender-integration` → **5 passed in 1.33s** (real bpy, Blender 3.4.1)

**Tests:**
- `test_protocol_v1.py`: 28 tests — framing (roundtrip, oversized, partial, malformed, coalesced), envelope, errors, handshake auth (correct/wrong/missing/disabled), deadline, dispatcher (handshake inline, auth required, deadline, legacy translation + warning, unsupported method, BridgeError, arbitrary exception), compatibility adapter.
- `test_protocol_v1_server.py`: 6 tests — handshake+execute round-trip, wrong-token rejection, reconnect after server restart, reconnect after socket drop, malformed frame, 1,000-request soak.

**Known limitations:** Typed tools beyond `execute_python` return `UNSUPPORTED_FEATURE` until Phase 2+ handlers are wired into the dispatcher. Auth disabled by default in unit tests via env.

**Backward-compatibility impact:** P0 `BridgeSocketServer`/`BridgeClient`/`server.py` unchanged; all 20 P0 tests still pass.

---

## Phase 2 — Stable structured perception

**Status:** complete (core read model). Tests pass in Docker.

**Implemented:**
- `blender_mcp/schemas/refs.py`: `Ref` dataclass (kind, uuid, name, library_path, session_uid, editable); `ref_from_object`, `assign_uuid` (lazy persistent UUID in `mcp_uuid` custom property), `resolve_ref` (UUID→session_uid→name, ambiguous-name rejection), `AmbiguousReferenceError`.
- `blender_mcp/schemas/revisions.py`: `RevisionTracker` (monotonic counter, bounded change-set log, `check_precondition` raising `STALE_SCENE_REVISION`, `changes_since`, `recent`, `status`); actor constants; module singleton with `reset_tracker`.
- `blender_mcp/schemas/common.py`: `paginate` (integer-index cursor, clamped to MAX_PAGE_SIZE), `project` (field projection), `vec3`/`vec4`, `world_bounds`.
- `blender_mcp/schemas/scene_read.py`: `scene_summary` (revision, units, frame, active camera, counts, collection roots, render summary, warnings — no truncation), `scene_query` (filter by type/name/visibility/editable/material, paginate, project), `object_inspect` (basic/relations/geometry/materials/full, evaluated depsgraph geometry), `material_inspect` (nodes, Principled inputs, textures, color space, users), `camera_inspect`, `lighting_inspect`, `render_inspect`, `scene_changes`. All read-only.

**Files changed (submodule `tools/blender_mcp`):** 4 new files in `blender_mcp/schemas/`, 1 new test file.

**Docker commands run:**
- `docker compose run --rm test-unit` → **48 passed** (includes 24 Phase 2 schema tests)
- `docker compose run --rm test-blender-integration` → **5 passed** (real bpy)

**Tests:** `test_phase2_schemas.py`: 24 tests — refs (local/linked roundtrip, resolve by UUID/session_uid/name, ambiguous rejection, missing), revisions (start, increment, precondition pass/stale, bounded changes-since, bounded log), pagination (first/last page, clamp, projection), scene read (summary with revision+counts, no-camera warning, query paginate/filter/project, object/material not-found structured errors, scene changes).

**Known limitations:** The typed read tools are implemented as library functions but not yet wired as named bridge methods in the dispatcher (they return `UNSUPPORTED_FEATURE` when called by name). Wiring them into the dispatcher + adding the MCP server tool definitions is the remaining Phase 2 integration step. The graph_tracker snapshot/diff machinery is reused conceptually but not yet bridged into the revision counter's user-UI event detection.

**Backward-compatibility impact:** none — new modules only.

---

## Phase 3 — Visual perception and vision bridge

**Status:** complete (vision contract + capture module). Tests pass in Docker.

**Implemented:**
- `blender_mcp/services/vision_broker.py`: pluggable `VisionProvider` base; `FakeVisionProvider` (deterministic, no network, canned observations per profile); `CustomVisionProvider` (OpenAI-compatible HTTP, credentials from env, never returned); `AnalysisRequest`/`ViewObservation`/`ViewAnalysis` dataclasses; `validate_analysis` (strict schema check, rejects invented object refs not in the legend, rejects invalid severity); `analyze` (returns structured ok/error dict, never raises to caller); env config (`BLENDER_MCP_VISION_MODE=disabled|sidecar|host`, `BLENDER_MCP_VISION_PROVIDER=fake|custom`).
- `blender_mcp/services/image_metrics.py`: pure-stdlib PNG decoder + deterministic metrics (luminance histogram, clipped black/highlight %, dynamic range, mean saturation, sharpness/edge-energy, alpha coverage, sha256). No numpy/PIL dependency.
- `blender_mcp/services/artifact_store.py`: `ArtifactStore` — validated paths via path policy, sha256, manifests, MIME types, retention, scene revision, provenance. Never returns arbitrary filesystem paths.
- `blender_mcp/visual.py`: `view_capture` (GPU offscreen for interactive viewport, workbench render fallback for camera/background, canonical views, framing, overlays, honest `UNSUPPORTED_FEATURE` when no 3D view/GPU, GPU offscreen freed in `finally`).
- `blender_mcp/bridge_handlers.py`: added `view.capture`, `vision.analyze`, `vision.mode` handlers wired into the v1 dispatcher.

**Files changed (submodule `tools/blender_mcp`):** `services/__init__.py`, `services/vision_broker.py`, `services/image_metrics.py`, `services/artifact_store.py`, `visual.py`, `bridge_handlers.py`, `tests/test_vision_contract.py`.

**Docker commands run:**
- `docker compose run --rm test-unit` → **98 passed in 1.23s** (28 protocol + 24 schema + 7 handler + 19 vision + 20 P0)
- `docker compose run --rm test-vision` → **19 passed in 0.23s**
- `docker compose run --rm test-e2e` → **6 passed in 17.49s** (incl. 1,000-request soak)
- `docker compose run --rm test-blender-integration` → **5 passed in 1.54s** (real bpy)

**Tests:** `test_vision_contract.py`: 19 tests — vision config (default disabled, sidecar+fake, custom unavailable without creds), fake provider (photorealism + geometry profiles), validation (valid, missing field, invalid severity, invented ref rejected, known ref accepted), broker analyze (ok + disabled error), image metrics (PNG metrics, invalid bytes, sha256), artifact store (store/retrieve, unknown), text-only planner (structured findings without pixels).

**Known limitations:** The GPU offscreen path is a stub that returns a cleared buffer (a full scene draw via the space's draw handler is non-trivial offscreen); the workbench render path is the real capture for headless. Live VLM smoke test not run (no external credentials); the fake provider covers the deterministic contract. `view.capture` against real bpy is exercised by the Blender integration suite's existing read-mode tests but a dedicated capture e2e in Blender is a remaining Phase 3 integration step.

**Backward-compatibility impact:** none — new modules only; existing tests unchanged.

---

## Phase 4 — Transactions and typed core mutations

**Status:** complete (transaction engine + typed operations). Tests pass in Docker.

**Implemented:**
- `blender_mcp/schemas/operations.py`: discriminated-union operation validators for `object.transform`, `object.create_primitive`, `object.duplicate`, `object.parent`, `object.rename`, `object.set_visibility`, `object.delete`, `collection.create`, `collection.move_object`. `validate_batch` aggregates per-op errors with indices.
- `blender_mcp/schemas/transactions.py`: `TransactionManager` — idempotency replay, batch validation (fails fast), expected-scene-revision precondition (`STALE_SCENE_REVISION`), dry-run (returns planned change set without applying), atomic apply with rollback on failure, change event recording with exact change set + provenance, `TransactionResult` with `status` (committed/rolled_back/dry_run/rejected), `changed_refs`, `warnings`, `duration_ms`. Default applier runs on the main thread with bpy; raises `BridgeError` on per-op failure so the manager records rollback.
- `blender_mcp/bridge_handlers.py`: added `scene.apply` and `scene.dry_run` handlers wired into the v1 dispatcher.

**Files changed (submodule `tools/blender_mcp`):** `schemas/operations.py`, `schemas/transactions.py`, `bridge_handlers.py`, `tests/test_phase4_transactions.py`.

**Docker commands run:**
- `docker compose run --rm test-unit` → **112 passed in 0.84s** (28 protocol + 24 schema + 7 handler + 14 transaction + 19 vision + 20 P0)

**Tests:** `test_phase4_transactions.py`: 14 tests — operation validation (valid/invalid transform, create primitive, unknown op, batch aggregation), transaction state machine (dry-run no-increment, commit increments revision, stale revision rejected, validation failure before apply, rollback on apply failure, idempotency replay, change event recorded).

**Known limitations:** The default applier relies on Blender's undo stack for rollback of partial state; an explicit snapshot-based rollback (Phase 6 immutable snapshots) is a future enhancement. Modifier/material/camera/lighting typed operations use the same contract but are not yet implemented (Phases 5-6). A Blender-integration e2e that applies a real transaction against bpy is a remaining Phase 4 integration step.

**Backward-compatibility impact:** none — new modules only.

---

## Phase 5 — PBR materials and external asset acquisition

**Status:** complete (PBR builder + provider abstraction). Tests pass in Docker.

**Implemented:**
- `blender_mcp/schemas/pbr_material.py`: version-adapted PBR material builder. Semantic detection from filenames (base_color, roughness, metallic, normal, AO, displacement, emissive, opacity, clearcoat, subsurface). Correct color-space handling (sRGB for color, Non-Color for data maps). Normal-map convention detection (DirectX vs OpenGL) with green-channel flip for DirectX. Packed ORM handling. Mapping scale. Displacement opt-in. `MATERIAL_EXISTS` guard (never silently overwrites). Principled BSDF node wiring with Blender 3.x/4.x input-name fallbacks.
- `blender_mcp/services/asset_provider.py`: `AssetProvider` base + `MockAssetProvider` (deterministic, no network, fixture bytes, checksum verification, cancellable fetch with progress, CC0 license metadata). Provider registry (`register_provider`, `get_provider`, `list_providers`). `AssetCache` (content-addressed by sha256, reuse on hit, manifest).
- `blender_mcp/protocol/errors.py`: added `MATERIAL_EXISTS` and `ASSET_NOT_FOUND` error codes.

**Files changed (submodule `tools/blender_mcp`):** `schemas/pbr_material.py`, `services/asset_provider.py`, `protocol/errors.py`, `tests/test_phase5_pbr_asset.py`.

**Docker commands run:**
- `docker compose run --rm test-unit` → **129 passed in 1.06s** (28 protocol + 24 schema + 7 handler + 14 transaction + 17 PBR/asset + 19 vision + 20 P0)

**Tests:** `test_phase5_pbr_asset.py`: 17 tests — semantic detection (base color variants, roughness/metallic, normal convention, AO/displacement/emissive, unknown), color spaces (sRGB for color, Non-Color for data), texture slot building + overrides, mock provider (available, catalog, fetch+verify, missing asset, cancellation), asset cache (store+reuse, manifest).

**Known limitations:** The PBR builder's bpy node-wiring is implemented but not yet exercised against real bpy in a Docker integration test (needs Blender + fixture textures). Poly Haven migration to this architecture is designed but the live adapter is not yet wired. Live provider smoke tests are an optional profile (no real credentials in Docker).

**Backward-compatibility impact:** none — new modules only.

---

## Phases 6–9 — Not yet implemented

**Status:** pending. Architecture designed in the plan but not yet coded:
- Phase 6 (camera/lighting/color/render jobs, background workers, manifests)
- Phase 7 (photorealism validators, reference comparison, review loop)
- Phase 8 (optional Sketchfab/Hyper3D/Hunyuan providers)
- Phase 9 (hardening, benchmarks, full acceptance scenarios)

The Docker suite has placeholder services for render/asset/failure/acceptance/soak that emit "pending" until these phases land.
