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

## Phases 3–9 — Not yet implemented

**Status:** pending. The architecture (vision broker interface, transaction model, PBR builder, render job manager, validators, provider abstraction) is designed in the plan but not yet coded. The Docker suite has placeholder services for render/vision/asset/failure/acceptance/soak that emit "pending" until the corresponding phases land.
