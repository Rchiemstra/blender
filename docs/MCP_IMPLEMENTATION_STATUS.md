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

**Files changed:**
- `docs/mcp_current_state_inventory.md` (new)
- `docs/MCP_IMPLEMENTATION_STATUS.md` (new, this file)

**Architecture decisions:**
- Keep the existing framed IPC and main-thread queue — they already satisfy the plan's framing requirement. Extend, do not rewrite.
- `blender_read_mode` is currently a file-protection add-on; the plan's "read mode" responsibility (structured serializers) will be added as new modules rather than by repurposing the file-protection code.
- `blender_graph_tracker` snapshot/diff machinery is reusable; the plan's revision counter and actor attribution will be layered on top.
- No MCP SDK is used today; the hand-rolled JSON-RPC server is kept and extended with resources/prompts/tasks by hand.

**Docker commands run:** none yet (Docker foundation is the next slice).

**Exact test results:** existing `test_p0.py` is runnable on CPython without bpy; not yet executed in this session (will run inside the new Docker unit suite).

**Known limitations:** baseline Blender version inside the legacy Dockerfiles is unpinned (`apt-get install blender`); the new Dockerfile must pin a version.

**Backward-compatibility impact:** none — no production code changed.

**Next phase entry conditions:** met. Proceed to Docker foundation, then Phase 1.
