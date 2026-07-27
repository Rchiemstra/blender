# MCP Current State Inventory

Phase 0 deliverable for the Blender MCP photorealism plan.

## Submodules

| Submodule | SHA | Remote | Branch |
|---|---|---|---|
| `tools/blender_mcp` | `476ed6afaa59da716f9b1a9a9be1d1230ee41ca7` | https://github.com/Rchiemstra/blender_mcp.git | main |
| `tools/blender_read_mode` | `c39d6e5c4a60a1a6da18a063000ef5198a1d4a6a` | https://github.com/Rchiemstra/blender_read_mode.git | main |
| `tools/blender_graph_tracker` | `d41fa1b8a1140e6424f315c2d3fddbcce7c031b4` | https://github.com/Rchiemstra/blender_graph_tracker.git | main |

All three are forks owned by `Rchiemstra`. Working tree was clean before this branch.

## blender_mcp — current architecture (P0)

Package layout under `tools/blender_mcp/`:

```
blender_mcp/
  __init__.py        # __version__ = "0.1.0"; re-exports addon entrypoints
  __main__.py        # calls server.main
  server.py          # stdio MCP server (JSON-RPC over stdin/stdout)
  addon.py           # Blender add-on: timer-driven main-thread drain
  bridge.py          # BridgeSocketServer, MainThreadCommandQueue, BridgeClient
  framing.py         # 4-byte big-endian length prefix + UTF-8 JSON
  envelope.py        # ok/error/exception uniform envelope
  blender_executor.py# execute_python implementation (runs on main thread)
  startup.py         # --python entrypoint: registers addons, serves headless
start_blender.py     # integration launcher (finds blender.exe, no MCP logic)
demo_p0.py           # in-process demo without Blender
tests/
  test_p0.py         # framing, queue, socket bridge, MCP server unit tests
  test_blender_access_mode.py  # needs bpy
  e2e/test_read_mode_e2e.py    # needs bpy
  e2e/Dockerfile     # debian:bookworm-slim + apt blender
```

### MCP protocol surface

- MCP protocol version advertised: `2025-06-18`.
- Transport: stdio JSON-RPC (one JSON object per line).
- Methods handled: `initialize`, `ping`, `tools/list`, `tools/call`, `notifications/initialized`.
- Tools exposed: **only** `execute_python`.
- `execute_python` input: `{code: str, return_render?: bool, timeout?: number}`.
- `execute_python` output envelope: `{status, payload, error, render, meta}` where `payload = {stdout, stderr, result}`.
- No resources, no prompts, no tasks, no progress notifications.

### Bridge / IPC

- `framing.py`: 4-byte unsigned big-endian length prefix + UTF-8 JSON body. `MAX_MESSAGE_BYTES = 16 MiB`. Raises `FramingError` on truncation/oversize.
- `bridge.py` `BridgeSocketServer`: localhost TCP, `SO_REUSEADDR`, accept loop on a daemon thread, one daemon thread per connection, single request/response per connection (no multiplexing, no keepalive).
- `MainThreadCommandQueue`: socket threads enqueue `QueuedCommand`; Blender main thread drains via `drain_once`/`drain_all` (called from `bpy.app.timers` every 20 ms, or `pump_until_idle` in headless mode). Executor runs on the draining thread.
- `BridgeClient`: synchronous, one connection per call, `threading.Lock` serializes calls. No reconnect, no retry, no request ID correlation at the transport layer.
- Auth: none. Handshake: none. Capability discovery: none. Deadlines: only a per-call socket timeout. Scene revision: not present.

### Blender-side execution

- `blender_executor.execute_python` compiles code with `compile()` + `exec()`, injects `bpy`, `bmesh`, `mathutils`, `gpu`, `addon_utils`, `context`, `scene`, `set_result`, `mcp_result`. Captures stdout/stderr via `contextlib.redirect_*`. Returns structured envelope with traceback on error.
- `addon.py`: `bl_info` targets Blender 4.2.0. Timer registered as persistent. `serve_forever()` is the headless entrypoint with SIGINT/SIGTERM handling.
- `startup.py`: adds `tools/blender_mcp`, `tools/`, `tools/blender_graph_tracker` to `sys.path`; registers read_mode + graph_tracker addons in GUI mode; calls `addon.serve_forever()` in background mode.

### What P0 does NOT have

- No handshake/capability discovery.
- No auth token.
- No protocol-level request IDs, deadlines, idempotency keys, or scene-revision preconditions.
- No structured error codes (errors are `{type, message, traceback}` strings).
- No reconnect/retry on the client.
- No compatibility adapter (no legacy commands to preserve yet — this is the first version).
- No path policy / filesystem root validation.
- No scene revision tracking.
- No stable object references (objects identified by name only).
- No structured scene reads (only `execute_python`).
- No viewport/camera capture.
- No vision bridge.
- No transactions, dry-run, rollback.
- No typed mutation operations.
- No PBR material builder.
- No asset provider abstraction.
- No render job manager.
- No validators.
- HTTP/downloads: none occur inside Blender today (no providers integrated yet), so the "move network out of Blender" requirement is already satisfied by absence — but must be enforced as features are added.

## blender_read_mode — current architecture

Package layout under `tools/blender_read_mode/`:

```
__init__.py     # bl_info (Blender 3.4.0+); register/unregister delegate to ui
access_mode.py  # READ_MODE/WRITE_MODE state; chmod-based file protection
read_mode.py    # clean_current_file_for_read_mode: save dirty images/catalogs before lock
ui.py           # operators, panel, save-prompt toggling
tests/
  test_read_mode.py, test_access_mode.py, test_blender_ui.py
  e2e/test_read_mode_e2e.py, e2e/Dockerfile
```

- `access_mode.set_mode(mode, filepath)`: toggles filesystem write bits via `os.chmod`. Thread-safe (`threading.RLock`). State persists in module global.
- `read_mode.clean_current_file_for_read_mode`: saves dirty external images, packs dirty generated/packed images, saves asset catalogs (with `poll()` guard), then saves mainfile, then re-locks. Returns structured status dict.
- This submodule is a **file-protection** add-on, not a scene reader. The plan's "read mode" responsibility (structured scene serializers, query engine, evaluated-geometry inspection) is **not** implemented here. The plan's `blender_read_mode` ownership slot is currently filled by a narrower feature than the plan describes.

## blender_graph_tracker — current architecture

Package layout under `tools/blender_graph_tracker/`:

```
blendgraph_tracker/
  __init__.py     # bl_info (Blender 4.2.0); register operators + ui_panel
  tracker.py      # TrackerState; depsgraph_update_handler; debounced compare
  snapshot.py     # build_snapshot_from_bpy: objects/collections/materials/textures/render
  diff.py         # diff_snapshots: emits structured change events
  changelog.py    # render_changelog (markdown)
  graph_export.py # build_scene_graph
  storage.py      # export_history/scene_graph/changelog to files
  operators.py, ui_panel.py
  tests/ (versioning, undo_revert, storage, graph_export, snapshot, events, diff, changelog, blender_ui)
  e2e/ (Dockerfile, test_blendgraph_e2e, test_undo_revert_e2e)
```

- `snapshot.build_snapshot_from_bpy`: serializes objects (name, type, location, rotation, scale, parent, collections, visibility, materials, modifiers, camera, light), collections, materials (Principled BSDF base_color/roughness/metallic/alpha), textures (images), render settings. Computes a 16-char SHA-256 hash. Skips linked/library data.
- `diff.diff_snapshots`: emits events for object created/deleted/renamed, transform changed, visibility, material slots, modifiers (add/remove/change/order), camera/light settings, collection changes, material changes, active camera, render settings. Events have `id`, `timestamp`, `blend_file`, `scene`, `type`, `source`.
- `tracker.py`: `depsgraph_update_handler` registered on `bpy.app.handlers.depsgraph_update_post`; debounced via `bpy.app.timers` (0.35 s). Tracking is opt-in (operator-driven), not always-on.
- **No persistent scene revision counter** — events have monotonic IDs but there is no `scene_revision` integer exposed to clients. **No stable UUID refs** — objects keyed by name. **No actor attribution** (mcp vs user_ui vs script). This submodule provides reusable snapshot/diff machinery the plan can build on, but does not yet satisfy the plan's `blender_graph_tracker` ownership slot (revisions, operation IDs, transaction IDs, provenance, actor attribution).

## Docker / test infrastructure today

Three independent, narrow Dockerfiles (one per submodule), all `FROM debian:bookworm-slim` with `apt-get install blender`. Each runs a single e2e test file in `blender --background --python`. There is:

- **No** top-level `docker-compose`.
- **No** unified test runner script.
- **No** artifact directory convention.
- **No** mock provider infrastructure.
- **No** Xvfb / virtual display (background mode only).
- **No** checksum verification of the Blender archive (apt-managed).
- **No** non-root user.
- **No** unit-test suite that runs outside Blender (the `test_p0.py` suite runs on CPython without bpy, but there is no orchestrator).

## Versions

- Blender target: `bl_info` declares 4.2.0 in `blender_mcp` and `blender_graph_tracker`, 3.4.0 in `blender_read_mode`. Docker uses `apt-get install blender` on Debian bookworm (typically Blender 3.x or 4.x depending on the Debian release — must be pinned in the new Dockerfile).
- Python: Blender 4.2 ships Python 3.11; Blender 4.4 ships Python 3.11/3.12. The repo's `lib/windows_x64/python/313` indicates a Python 3.13 build environment for the Blender source itself, but the add-ons run inside Blender's bundled interpreter.
- MCP SDK: **none**. The stdio server is hand-rolled JSON-RPC, not built on `mcp` or `fastmcp`. This is acceptable for P0 but means schema/resource/prompt/task support must be added by hand.

## Gap matrix (current code → plan)

| Plan section | Current state | Gap |
|---|---|---|
| §5.1 External MCP server | Partial: stdio server exists, only `execute_python` | Add handshake, capabilities, auth, deadlines, error codes, resources, prompts, tasks |
| §5.2 Blender bridge | Partial: framed IPC + main-thread queue exist | Add handshake, auth, reconnect, path policy, lifecycle cleanup |
| §5.3 Read mode | Narrow: file-protection only | Add structured serializers, query, evaluated geometry, pagination, projection |
| §5.4 Graph tracker | Partial: snapshot/diff exist | Add scene revision counter, actor attribution, operation/transaction IDs, provenance |
| §7 IPC protocol v1 | Framing done; handshake/errors/deadlines/revision absent | Full v1 envelope |
| §8 Stable refs & revisions | Absent | Persistent UUIDs, revision counter, change sets |
| §9 Resources & prompts | Absent | URI templates, prompt library |
| §10 Tool surface | Only `execute_python` | All typed read/write/visual/render/asset/validation tools |
| §11 Photorealism | Absent | PBR builder, units/scale, geometry prep, lighting, camera, color, render profiles |
| §12 Asset pipeline | Absent | Provider abstraction, Poly Haven, cache, licenses, import normalization |
| §13 Render jobs | Absent | Job manager, background workers, manifests, cancellation |
| §14 Validators | Absent | Issue registry, all check families |
| §15 Security | Absent | Auth token, path roots, archive safety, developer-mode gating |
| §17 Docker | Three narrow Dockerfiles | Unified compose, runner, mock providers, Xvfb, artifacts |

## Vision-sidecar decision

Selected mode: **`sidecar`** with a **provider-neutral** broker and a **deterministic fake provider** for Docker tests. Rationale: GLM-5.2 Max is text-only; the MCP host in this repo is not guaranteed to route image content items to a vision-capable model; a sidecar returning strict JSON `ViewAnalysis` is the most portable choice. The broker will accept a `BLENDER_MCP_VISION_PROVIDER=disabled|fake|custom` env var so the mandatory Docker suite runs without external API credentials. A real VLM adapter (e.g. GLM-5V-Turbo or OpenAI-compatible) plugs in behind the same interface.
