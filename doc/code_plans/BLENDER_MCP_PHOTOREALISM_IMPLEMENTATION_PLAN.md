# Blender MCP for Photorealistic Rendering

**Repository target:** `Rchiemstra/blender`, branch `blender-rchiemstra`  
**Primary implementation agent:** GLM-5.2 Max  
**Document purpose:** implementation specification, sequencing plan, tool contract, and acceptance criteria  
**Recommended repository path:** `docs/BLENDER_MCP_PHOTOREALISM_IMPLEMENTATION_PLAN.md`

---

## 1. Executive decision

The MCP should not be designed as a thin wrapper around `execute_python`. It should be a controlled perception and action system that lets an agent:

1. inspect Blender semantically;
2. inspect the rendered result visually;
3. make typed, reversible scene changes;
4. validate those changes;
5. launch and monitor render jobs;
6. compare results and iterate;
7. preserve provenance, licenses, settings, and output artifacts.

The target architecture is:

```text
GLM-5.2 Max
  - planning, coding, tool selection, interpretation of structured data
  - text input/output
          |
          | MCP: tools, resources, prompts, progress, tasks
          v
External Blender MCP server
  - schemas and typed tool contracts
  - scene/resource facade
  - job manager
  - asset-provider adapters
  - artifact store
  - deterministic image analysis
  - optional vision-model adapter
          |
          | framed, authenticated localhost IPC
          v
Blender bridge/add-on
  - non-blocking main-thread dispatcher
  - scene readers
  - typed mutation handlers
  - viewport capture
  - scene revisions and change events
  - snapshot/save integration
          |
          +--------------------+
          |                    |
          v                    v
Interactive Blender       Background Blender workers
                          - Cycles preview/final renders
                          - import conversion where useful
                          - isolated, cancellable jobs

Optional vision sidecar, such as GLM-5V-Turbo
  - receives screenshots/renders
  - returns strict structured visual observations
  - never mutates the Blender scene directly
```

### 1.1 Critical model constraint

GLM-5.2 Max must be treated as a text-only planning and coding model. A screenshot tool alone does not give it useful visual perception unless the MCP host explicitly routes images through a vision-capable model. Therefore the implementation must support one of these modes:

- **Host vision mode:** the MCP client sends image tool results to a vision-capable model.
- **Vision sidecar mode:** the Blender MCP server calls a configured vision model and returns a structured text/JSON report to GLM-5.2 Max.
- **No-vision mode:** the server returns deterministic image metrics and render passes, but must clearly report that semantic visual judgement is unavailable.

For GLM-5.2 Max, vision sidecar mode is the recommended default.

### 1.2 What matters most

The priorities are not the four originally proposed features in isolation. The actual order is:

1. **Reliable structured perception.** The agent cannot improve what it cannot identify.
2. **Reliable visual feedback for a text-only agent.** Capturing pixels is not the same as interpreting pixels.
3. **Typed, reversible scene operations.** Generic Python is an escape hatch, not a normal workflow.
4. **Asynchronous rendering and asset work.** Blender's main thread must not be held hostage by downloads or long jobs.
5. **Photorealism-specific validation.** Units, scale, bevels, UVs, map color spaces, lighting, camera, exposure, and output settings all need inspection.
6. **Asset libraries.** Poly Haven and other providers are useful only after the import, caching, licensing, and normalization pipeline is dependable.
7. **Generated 3D assets.** This belongs late in the roadmap. Generated geometry often needs more cleanup than scanned or deliberately modeled assets.

### 1.3 Non-goals

This plan does not promise that an MCP can produce the "most realistic render in existence." That is not a measurable engineering requirement. The implementable goal is:

> Produce repeatable, inspectable, reference-driven photorealistic Blender renders through an agent loop, with evidence for every important scene decision and with human review remaining possible.

Do not make these first-release goals:

- one-shot text-to-complete-scene generation;
- continuous video streaming from Blender;
- modifying Blender core for functionality available through the Python API;
- training a new vision or 3D model;
- forcing 8K assets everywhere;
- removing all artistic judgement from the workflow;
- using a single synthetic "realism score" as proof of quality.

---

## 2. Repository-specific assessment

The visible top-level branch is an orchestration repository. `start_blender.py` launches Blender with a startup script from `tools/blender_mcp`, and the repository declares three relevant submodules:

- `tools/blender_mcp`
- `tools/blender_read_mode`
- `tools/blender_graph_tracker`

Use those boundaries deliberately:

| Component | Ownership |
|---|---|
| `blender_mcp` | MCP server, IPC client, Blender bridge/add-on, typed tools, jobs, assets, vision adapter, artifact storage |
| `blender_read_mode` | Read-only scene serializers, query engine, evaluated-geometry inspection, resource views, scene snapshots and diffs |
| `blender_graph_tracker` | Revisions, change events, operation history, provenance, user-vs-agent changes, transaction metadata |
| top-level `blender` fork | Launcher, pinned submodule revisions, integration documentation, end-to-end test entry points |

Do not put scene logic into `start_blender.py`. Its responsibilities should remain:

- locate or build Blender;
- initialize/check submodules;
- establish a session token and artifact root;
- pass host, port, profile, and session settings;
- start Blender in the correct mode;
- wait for a readiness signal when requested;
- log startup diagnostics;
- fail clearly when interactive-only features are requested in background mode.

### 2.1 Mandatory phase-zero inspection

The three submodules were not visible during preparation of this plan. Before coding, GLM-5.2 Max must inspect their checked-out contents and record:

- current commit SHA and upstream remote;
- package layout;
- MCP SDK and protocol version;
- current tool names and schemas;
- current Blender command handlers;
- whether the code derives from `ahujasid/blender-mcp` and at which revision;
- existing scene-read, graph-tracking, screenshot, asset, and render features;
- existing tests and launch methods;
- supported Blender versions;
- existing use of sockets, threads, timers, handlers, and operators.

Create `docs/mcp_current_state_inventory.md` before changing code. Do not blindly recreate modules that already exist.

### 2.2 Known weaknesses in the public reference implementation

The public reference implementation already contains viewport capture and integrations for Poly Haven, Sketchfab, Hyper3D, and Hunyuan3D. Therefore "add these four features" is not an adequate plan.

The important weaknesses to verify in the local fork are:

- scene summaries truncated to a small number of objects;
- scene state returned as formatted strings rather than strict structured output;
- object names used as identity;
- little or no evaluated dependency-graph inspection;
- no explicit scene revision or stale-write protection;
- ad hoc JSON-over-TCP framing;
- long-lived Python threads in the Blender process;
- HTTP downloads and decompression occurring in Blender;
- arbitrary Python execution exposed as a normal tool;
- errors encoded as successful strings beginning with `Error:`;
- no general transaction, dry-run, rollback, or operation provenance contract;
- no render job/task abstraction with progress and cancellation;
- no image-analysis bridge for a text-only planning model;
- no comprehensive photorealism validation gate;
- no final render manifest tying outputs to scene/settings/assets.

---

## 3. How an agent sees Blender

An agent does not automatically see Blender's window, outliner, node editor, materials, or rendered image. It sees only the context supplied by the MCP host.

### 3.1 The four perception channels

| Channel | What the agent receives | What it is good for | What it cannot replace |
|---|---|---|---|
| Tool descriptions and schemas | Names, descriptions, argument/output types | Discovering what actions are possible | Current scene state |
| Structured scene results | JSON for objects, materials, camera, lights, settings, revisions | Identity, dimensions, relationships, exact values, deterministic reasoning | Whether the result looks convincing |
| Images and render passes | PNG/JPEG/EXR or image references | Composition, visible artifacts, material appearance, lighting | Exact object identity and node settings unless annotated |
| History and diagnostics | Changes, warnings, errors, render/job metadata | Recovery, iteration, auditability | Fresh scene and image state |

A strong system always combines structured and visual perception.

### 3.2 Required agent loop

```text
Observe structured state
  -> Observe current visual state
  -> Form a bounded plan
  -> Start transaction/checkpoint
  -> Apply one coherent batch of changes
  -> Read scene diff
  -> Capture or render preview
  -> Analyze preview
  -> Validate scene and render settings
  -> Keep, adjust, or roll back
  -> Render final
  -> Inspect final and write manifest
```

A screenshot should not be returned without:

- scene revision;
- camera/view identity;
- view and projection matrices when applicable;
- shading mode;
- resolution;
- selected/visible object context;
- artifact ID and SHA-256;
- optional object-label overlay and ID legend.

### 3.3 Vision path for GLM-5.2 Max

Implement a vision broker with this contract:

```text
GLM-5.2 Max calls blender.vision.analyze
  -> MCP loads image artifact and compact scene context
  -> MCP sends image plus constrained prompt to configured VLM
  -> VLM returns JSON matching ViewAnalysis schema
  -> MCP validates and normalizes JSON
  -> GLM-5.2 Max receives structured observations and suggested tool actions
```

The vision model must not receive direct mutation tools. It is an observer. GLM-5.2 Max remains responsible for deciding whether to act.

Provide these configuration values:

```text
BLENDER_MCP_VISION_MODE=sidecar|host|disabled
BLENDER_MCP_VISION_PROVIDER=zai|openai|local|custom
BLENDER_MCP_VISION_MODEL=<model-id>
BLENDER_MCP_VISION_ENDPOINT=<optional endpoint>
BLENDER_MCP_VISION_API_KEY=<secret reference, never returned by tools>
```

At startup, report the configured mode and whether a calibration analysis succeeds. Do not pretend an image was understood when only capture succeeded.

---

## 4. Success criteria

The completed system should satisfy all of the following.

### 4.1 Perception

- Query scenes with at least 10,000 objects without dumping the entire scene into model context.
- Paginate and filter object/material results.
- Identify local objects across renames using persistent MCP IDs.
- Inspect evaluated geometry, not only original mesh data.
- Return material node topology, image paths, color spaces, mapping scale, and missing-file status.
- Return camera, lighting, world, render, output, and color-management settings.
- Return a bounded change set since a known scene revision.
- Capture a viewport or camera image with metadata.
- Produce a structured visual analysis usable by GLM-5.2 Max.

### 4.2 Action

- Complete the common photorealistic workflow without arbitrary Python.
- Validate every input before mutating Blender.
- Support dry-run for destructive or broad changes.
- Reject stale operations when the scene changed unexpectedly.
- Batch coherent changes to reduce round trips.
- Record changed object/material IDs and warnings.
- Roll back a failed batch when Blender's undo/snapshot constraints allow it.
- Require explicit confirmation or developer mode for arbitrary Python.

### 4.3 Rendering

- Detect available render engines and devices at runtime.
- Launch preview and final renders as cancellable jobs.
- Report progress, state, warnings, and outputs.
- Avoid blocking the interactive Blender bridge for final renders.
- Produce display output such as PNG and scene-linear output such as multilayer OpenEXR when requested.
- Produce a manifest containing scene revision, camera, render settings, Blender build, assets, hashes, timing, and output paths.

### 4.4 Reliability

- Reconnect after the Blender process or socket restarts.
- Reject malformed, partial, oversized, unauthenticated, or stale requests.
- Avoid persistent Blender Python threads for networking and downloads.
- Avoid unbounded memory growth across repeated captures and queries.
- Keep provider failures isolated from scene-control tools.
- Preserve a useful audit trail without logging secrets.

---

## 5. Architecture in detail

## 5.1 External MCP server

The MCP server runs outside Blender and owns:

- MCP protocol integration;
- strict input/output schemas;
- tools, resources, prompts, progress, and task support;
- connection management to Blender;
- job orchestration;
- asset-provider HTTP calls;
- downloads, retries, checksums, archives, and cache;
- vision-provider calls;
- deterministic image analysis;
- artifact storage;
- log aggregation and redaction;
- compatibility adapters for old command names.

It must not import `bpy`.

## 5.2 Blender bridge/add-on

The Blender-side bridge owns only operations requiring `bpy`, `gpu`, the dependency graph, UI context, or Blender data blocks.

Use a non-blocking, timer-driven main-thread poller rather than a permanent Python networking thread:

```python
# Illustrative structure, not final code.
def poll_bridge() -> float:
    for request in transport.poll_nonblocking(max_requests=8):
        response = dispatcher.execute_on_main_thread(request)
        transport.queue_response(response)
    transport.flush_nonblocking()
    return 0.02
```

Rules:

- never call `bpy` from a worker thread;
- never perform HTTP requests in Blender;
- never unpack archives in Blender;
- never wait synchronously for a remote generation job in Blender;
- bound work per timer tick so normal UI interaction remains responsive;
- use Blender handlers only for lifecycle/change/render notifications, with lightweight callbacks;
- remove handlers, timers, sockets, and temporary data cleanly on unregister or file change.

If a non-blocking socket poller proves unreliable on a supported platform, use a small external bridge process and Blender timer polling through files/shared memory/local pipe. Do not solve thread-safety warnings by hoping the problem is theoretical.

## 5.3 Read mode

`blender_read_mode` should provide reusable, side-effect-free readers:

- scene summary serializer;
- object/material/camera/light/world/render serializers;
- evaluated-geometry reader;
- collection tree reader;
- dependency/relationship reader;
- query filters and pagination;
- scene snapshot fingerprint;
- diff computation;
- resource URI generation;
- size/token budgeting.

Readers should prefer direct data API access over context-sensitive operators.

## 5.4 Graph tracker

`blender_graph_tracker` should own:

- monotonically increasing scene revision;
- operation IDs and transaction IDs;
- MCP-generated change sets;
- debounced detection of user/UI changes;
- object/material provenance;
- before/after fingerprints;
- recent history resources;
- change subscriptions where supported;
- rollback metadata and snapshot links.

It should distinguish:

```text
actor = mcp | user_ui | script | import | render_worker | unknown
```

Do not serialize the whole scene after every dependency-graph callback. Track affected IDs, debounce bursts, and compute detail lazily.

## 5.5 Worker processes

Use external workers for:

- Poly Haven and other provider calls;
- file downloads and hash validation;
- archive extraction with zip-slip protection;
- model conversion/preflight when possible;
- background Blender renders;
- image metrics;
- optional vision inference;
- optional generated-asset polling.

A final render worker should receive:

- immutable job JSON;
- a saved scene snapshot path;
- camera reference;
- overrides;
- output directory;
- cancellation token path or IPC channel;
- result manifest path.

It should not edit the user's working `.blend` file.

## 5.6 Artifact store

Recommended structure:

```text
<artifact-root>/
  sessions/<session-id>/
    captures/
    render-jobs/<job-id>/
    snapshots/
    vision/
    logs/
  cache/
    polyhaven/
    sketchfab/
    generated/
    converted/
  manifests/
```

Every artifact receives:

- opaque artifact ID;
- normalized path under allowed root;
- MIME type;
- size;
- SHA-256;
- creation time;
- scene revision if relevant;
- producing tool/job;
- retention policy;
- license/provenance metadata where relevant.

Do not return arbitrary filesystem paths as trusted artifacts. Validate that every returned path resolves under an allowed root.

---

## 6. Proposed repository layout

Adapt this to the existing submodule layout instead of creating duplicate packages.

```text
tools/blender_mcp/
  pyproject.toml
  README.md
  blender_mcp/
    __init__.py
    server.py
    startup.py

    protocol/
      framing.py
      envelope.py
      errors.py
      capabilities.py
      compatibility_v0.py

    schemas/
      common.py
      refs.py
      system.py
      scene.py
      geometry.py
      materials.py
      camera.py
      lighting.py
      render.py
      assets.py
      vision.py
      jobs.py
      operations.py

    tools/
      system.py
      scene_read.py
      visual.py
      scene_write.py
      geometry.py
      materials.py
      camera.py
      lighting.py
      render.py
      assets.py
      validation.py
      jobs.py
      developer.py

    resources/
      scene.py
      objects.py
      materials.py
      history.py
      jobs.py
      artifacts.py

    bridge_client/
      connection.py
      transport.py
      retry.py

    services/
      artifact_store.py
      job_manager.py
      render_jobs.py
      image_metrics.py
      vision_broker.py
      secret_store.py
      license_store.py
      logging.py

    providers/
      base.py
      polyhaven.py
      sketchfab.py
      hyper3d.py
      hunyuan.py
      local_library.py

    blender_addon/
      __init__.py
      preferences.py
      transport.py
      dispatcher.py
      timer_poller.py
      lifecycle.py
      revisions.py
      transactions.py
      refs.py
      handlers/
        system.py
        scene_read.py
        visual.py
        scene_write.py
        geometry.py
        materials.py
        camera.py
        lighting.py
        render.py
        importers.py
        validation.py

    workers/
      render_worker.py
      import_worker.py

  tests/
    unit/
    integration/
    blender/
    fixtures/
    golden/

tools/blender_read_mode/
  blender_read_mode/
    serializer.py
    query.py
    evaluated_geometry.py
    material_graph.py
    collection_graph.py
    snapshots.py
    diff.py
    resources.py

tools/blender_graph_tracker/
  blender_graph_tracker/
    revisions.py
    events.py
    provenance.py
    operation_log.py
    subscriptions.py
    fingerprints.py

docs/
  BLENDER_MCP_PHOTOREALISM_IMPLEMENTATION_PLAN.md
  mcp_current_state_inventory.md
  mcp_protocol_v1.md
  mcp_tool_reference.md
  mcp_compatibility_matrix.md
  mcp_security_model.md
  mcp_benchmark_report.md
```

---

## 7. IPC protocol v1

The current bridge must be upgraded from "send JSON and keep reading until `json.loads` happens to succeed" to an explicit framed protocol.

## 7.1 Framing

Use a four-byte unsigned big-endian payload length followed by UTF-8 JSON.

```text
[4-byte length][JSON bytes]
```

Requirements:

- maximum request and response size;
- incremental reads and writes;
- multiple requests per connection;
- request IDs;
- response correlation;
- reconnect support;
- deadline and cancellation metadata;
- protocol version negotiation;
- authentication token;
- no image base64 over this channel unless a small diagnostic requires it.

Large images and renders travel through the artifact store.

## 7.2 Handshake

First request after connect:

```json
{
  "protocol_version": "1.0",
  "request_id": "01J...",
  "method": "system.handshake",
  "params": {
    "session_id": "01J...",
    "auth_token": "<redacted>",
    "client": {
      "name": "blender-mcp-server",
      "version": "1.0.0"
    }
  }
}
```

Response:

```json
{
  "protocol_version": "1.0",
  "request_id": "01J...",
  "ok": true,
  "result": {
    "blender_version": "5.x.y",
    "build_hash": "...",
    "python_version": "...",
    "interactive": true,
    "active_file": "...",
    "scene_revision": 17,
    "capabilities": {
      "viewport_capture": true,
      "camera_capture": true,
      "background_render_worker": true,
      "cycles": true,
      "eevee": true,
      "workbench": true,
      "gpu_devices": [],
      "supported_importers": [],
      "max_frame_bytes": 4194304
    }
  },
  "warnings": [],
  "timing_ms": 4.2
}
```

Capabilities must be discovered, not assumed from GPU brand or Blender version.

## 7.3 Request envelope

```json
{
  "protocol_version": "1.0",
  "request_id": "01J...",
  "method": "scene.apply_operations",
  "params": {},
  "deadline_ms": 30000,
  "expected_scene_revision": 17,
  "transaction_id": "01J...",
  "idempotency_key": "...",
  "dry_run": false
}
```

## 7.4 Response envelope

```json
{
  "protocol_version": "1.0",
  "request_id": "01J...",
  "ok": true,
  "result": {},
  "scene_revision_before": 17,
  "scene_revision_after": 18,
  "changed_refs": [],
  "warnings": [],
  "timing_ms": 12.4
}
```

## 7.5 Error model

Do not return a successful text string containing `Error:`. Return a failed tool result with a structured error.

```json
{
  "ok": false,
  "error": {
    "code": "STALE_SCENE_REVISION",
    "message": "Expected scene revision 17 but current revision is 19.",
    "retryable": true,
    "details": {
      "expected": 17,
      "actual": 19
    },
    "suggested_action": "Call blender.scene.changes or blender.scene.summary, then retry."
  }
}
```

Minimum error codes:

```text
INVALID_ARGUMENT
UNAUTHENTICATED
PERMISSION_DENIED
UNSUPPORTED_FEATURE
NO_ACTIVE_SCENE
NO_3D_VIEW
OBJECT_NOT_FOUND
MATERIAL_NOT_FOUND
AMBIGUOUS_REFERENCE
STALE_SCENE_REVISION
CONTEXT_UNAVAILABLE
MODE_CONFLICT
VALIDATION_FAILED
TRANSACTION_FAILED
ROLLBACK_FAILED
FILE_ACCESS_DENIED
ASSET_PROVIDER_DISABLED
ASSET_LICENSE_REQUIRED
DOWNLOAD_FAILED
CHECKSUM_MISMATCH
IMPORT_FAILED
RENDER_FAILED
VISION_UNAVAILABLE
VISION_INVALID_RESPONSE
TIMEOUT
CANCELLED
BLENDER_DISCONNECTED
INTERNAL_ERROR
```

## 7.6 Compatibility

Maintain a temporary translation layer from old command names such as `get_scene_info`, `get_object_info`, and `execute_code`. Log deprecation warnings. Remove it only after tests and client configuration migrate.

---

## 8. Stable references and scene revisions

Names are human labels, not stable identities.

## 8.1 Object and data-block references

Use this model:

```json
{
  "kind": "OBJECT",
  "uuid": "f1690ce1-...",
  "session_uid": 193842,
  "name": "Chair.003",
  "library_path": null,
  "editable": true
}
```

Identity policy:

1. For editable local data blocks, store a persistent custom UUID, for example `mcp_uuid`.
2. For linked/read-only data blocks, use a compound reference containing library path, ID type, full name, and current-session UID.
3. Return both UUID and current name so humans can understand results.
4. Resolve by UUID first. Name lookup is a convenience fallback and must reject ambiguity.
5. Assign IDs lazily or during an explicit indexing pass. Do not mark the file dirty merely because a read-only query occurred unless the user opted into persistent indexing.

## 8.2 Revisions

Every meaningful scene change increments `scene_revision`.

- MCP mutations increment after successful completion.
- User/UI changes are observed through debounced dependency-graph and property events.
- File load, undo, redo, scene switch, and major imports create explicit events.
- Every read returns the revision it describes.
- Every mutation may specify `expected_scene_revision`.
- A stale mutation fails before changing Blender.

## 8.3 Change set

```json
{
  "from_revision": 17,
  "to_revision": 19,
  "events": [
    {
      "revision": 18,
      "actor": "mcp",
      "operation_id": "...",
      "kind": "material.assignment",
      "changed_refs": [],
      "summary": "Assigned OakFloor_PBR to Floor"
    },
    {
      "revision": 19,
      "actor": "user_ui",
      "kind": "object.transform",
      "changed_refs": [],
      "summary": "Camera moved in Blender UI"
    }
  ]
}
```

---

## 9. MCP resources

Use resources for state that the host or user may browse without invoking a mutation tool.

Recommended URI templates:

```text
blender://system/capabilities
blender://scene/summary
blender://scene/revision/current
blender://scene/revision/{revision}
blender://scene/objects?cursor={cursor}
blender://object/{uuid}
blender://material/{uuid}
blender://camera/{uuid}
blender://render/settings
blender://history/recent
blender://history/operation/{operation_id}
blender://job/{job_id}
blender://artifact/{artifact_id}/manifest
blender://render/latest/manifest
```

Resource requirements:

- bounded payloads;
- pagination for collections;
- last-modified metadata;
- scene revision in every scene-derived resource;
- subscription notifications if supported;
- no secrets or unrestricted local paths;
- deterministic JSON field ordering in tests.

Prompts may define workflows, but prompts must not replace tools or validation.

Recommended prompts:

```text
photorealistic_product_shot
photorealistic_interior
material_diagnosis
lighting_diagnosis
camera_composition_review
asset_import_review
final_render_review
```

---

## 10. Tool surface design

Do not expose hundreds of Blender operators. Do not expose only one generic Python tool either.

Use a compact core tool set with strict schemas and capability-specific optional tools. Provider tools may appear dynamically when configured.

## 10.1 Core system and job tools

### `blender.system.capabilities`

Returns Blender version/build, interactive/headless state, current file, render engines, devices, importers, vision mode, providers, artifact limits, and protocol versions.

### `blender.system.health`

Checks MCP server, Blender bridge, artifact store, render worker launch, provider configuration, vision provider, and recent errors.

### `blender.system.logs`

Returns bounded, redacted logs filtered by component, severity, correlation ID, operation ID, or job ID.

### `blender.job.get`

Returns job status, progress, current phase, outputs, errors, and timestamps.

### `blender.job.list`

Paginated list filtered by type/status/session.

### `blender.job.cancel`

Requests cancellation. It must be idempotent and must never report cancelled before the worker state is updated.

## 10.2 Structured perception tools

### `blender.scene.summary`

Inputs:

```text
include_counts
include_selection
include_collection_roots
include_render_summary
include_warning_summary
```

Outputs:

- scene and view-layer refs;
- revision;
- units and scale;
- frame/time;
- active camera;
- selection and active object;
- counts by object/data type;
- world/render/color/output summary;
- scene world-space bounds;
- collection roots;
- high-level warnings;
- continuation links/cursors, never an arbitrary first-ten truncation.

### `blender.scene.query`

Filters:

```text
name exact/contains/regex
type
collection ref
material ref
selected
visible viewport/render
editable
local/linked
has_modifier
has_missing_assets
within_bbox
near_point
custom tags
```

Projection:

```text
ref, name, type, transform, dimensions, bbox, visibility,
materials, collections, parent, modifiers, custom properties
```

Always paginate and bound output size.

### `blender.object.inspect`

Detail levels:

- `basic`
- `relations`
- `geometry`
- `materials`
- `render`
- `full`

Geometry detail must include base and evaluated statistics where applicable:

- vertices, edges, polygons/triangles;
- instances and realized geometry summary;
- dimensions and world bounds;
- UV maps and active UV;
- color attributes;
- normals/shading state;
- manifold/non-manifold indicators;
- modifier stack;
- subdivision/displacement state;
- material slots;
- missing data warnings.

### `blender.material.inspect`

Return:

- stable ref;
- use-nodes state;
- node types and links;
- Principled inputs by semantic name;
- texture image refs;
- resolution, bit depth where available, packed/external state;
- path existence;
- color space;
- interpolation/projection/extension;
- mapping transforms and real-world scale metadata;
- normal/displacement wiring;
- material users;
- validation warnings.

### `blender.camera.inspect`

Return projection type, lens, sensor, shift, clipping, transforms, DOF, focus target/distance, aperture/blades, resolution/aspect, framing metrics, and visible subject coverage where requested.

### `blender.lighting.inspect`

Return world nodes/HDRI, environment rotation and strength, light list, type, shape, dimensions, power, color/temperature, visibility, linking, and estimated scene coverage.

### `blender.render.inspect`

Return engine/device, sampling, noise threshold, bounces, denoising, passes, motion blur, film, transparency, color management, compositor, output path/format/depth, and active view layer.

### `blender.scene.changes`

Input `since_revision`; output bounded change events and affected refs.

### `blender.scene.raycast`

Input world-space origin/direction/distance or camera pixel coordinate. Return hit ref, point, normal, distance, polygon index, material slot, and UV if available.

### `blender.scene.measure`

Support point-to-point, bounding-box clearance, closest-surface estimate, object dimensions, and camera distance. Return method and uncertainty.

### `blender.scene.validate`

Profiles:

```text
basic
photorealism
asset-import
pre-preview-render
pre-final-render
```

Return issues with stable refs and remediation hints. Never mutate.

## 10.3 Visual tools

### `blender.view.capture`

Inputs:

```json
{
  "source": "active_viewport|active_camera|named_camera|canonical",
  "camera_ref": null,
  "canonical_view": "front|back|left|right|top|bottom|isometric",
  "shading": "solid|material_preview|rendered|wireframe",
  "frame": "current|all|selected|refs",
  "refs": [],
  "overlays": false,
  "gizmos": false,
  "selection_outline": false,
  "transparent": false,
  "width": 1024,
  "height": 1024,
  "max_dimension": 1600,
  "format": "png",
  "annotate_objects": false
}
```

Output includes an MCP image content item when supported and structured content:

```json
{
  "artifact": {},
  "scene_revision": 42,
  "source": "active_camera",
  "camera_ref": {},
  "view_matrix": [],
  "projection_matrix": [],
  "shading": "rendered",
  "width": 1024,
  "height": 1024,
  "method": "gpu_offscreen|workbench_render|camera_render",
  "object_legend": []
}
```

Requirements:

- use GPU offscreen drawing when an interactive 3D region is available;
- provide a camera/workbench fallback when no view region exists;
- report capability failure honestly in true headless mode;
- restore all temporary settings;
- free GPU offscreen objects and temporary images in `finally` blocks;
- avoid OS-window framebuffer grabs as the primary method;
- measure p50/p95 instead of promising a universal sub-100 ms result.

### `blender.view.capture_bundle`

Produces a related set of artifacts using the same camera and revision:

- beauty/image;
- object-label overlay;
- depth;
- normal;
- object or Cryptomatte identifiers;
- wireframe or geometry diagnostic;
- optional albedo/roughness diagnostics.

Not every pass must come from the viewport. A low-sample render worker may produce passes that the viewport cannot provide reliably.

### `blender.vision.analyze`

Inputs:

```text
artifact_id
analysis_profile
question
scene_context_level
reference_artifact_ids
```

Profiles:

```text
composition
lighting
materials
geometry_artifacts
photorealism
reference_match
final_review
```

Strict output:

```json
{
  "analysis_id": "...",
  "artifact_id": "...",
  "scene_revision": 42,
  "vision_mode": "sidecar",
  "model": "...",
  "overall_assessment": "...",
  "observations": [
    {
      "category": "lighting",
      "severity": "warning",
      "confidence": 0.88,
      "description": "The contact shadow under the product is weak, making it appear to float.",
      "regions": [{"x": 0.20, "y": 0.65, "w": 0.55, "h": 0.20}],
      "related_refs": [],
      "evidence": "Visible gap and low occlusion at the base.",
      "suggested_action": {
        "tool": "blender.lighting.configure",
        "intent": "Increase local grounding without crushing the shadow."
      }
    }
  ],
  "uncertainties": [],
  "technical_metrics": {},
  "raw_response_artifact_id": null
}
```

Validate sidecar JSON. Reject invented object refs that are not in the provided legend/context.

### `blender.view.compare`

Compare A/B or current/reference images. Return:

- deterministic metrics where meaningful;
- aligned difference artifact;
- vision comparison report;
- scene revisions and operations separating A and B;
- explicit statement that numeric similarity is not equivalent to realism.

## 10.4 Mutation and transaction tools

### `blender.scene.transaction.begin`

Creates transaction metadata and optionally a temporary `.blend` snapshot for high-risk changes.

### `blender.scene.apply`

Preferred batch mutation tool. Accept a discriminated union of typed operations. Validate all operations before applying any.

Example:

```json
{
  "expected_scene_revision": 42,
  "transaction_id": "...",
  "operations": [
    {
      "op": "object.transform",
      "ref": {},
      "space": "WORLD",
      "location": [0.0, 0.0, 0.8],
      "rotation_euler": [0.0, 0.0, 0.0],
      "scale": [1.0, 1.0, 1.0]
    },
    {
      "op": "material.assign",
      "object_ref": {},
      "slot": 0,
      "material_ref": {}
    }
  ]
}
```

Result:

- per-operation status;
- changed refs;
- before/after revision;
- warnings;
- undo/snapshot metadata;
- validation summary.

### `blender.scene.transaction.commit`

Marks the transaction accepted and updates provenance.

### `blender.scene.transaction.rollback`

Uses undo or snapshot restore according to the transaction strategy. Report limitations and verify resulting fingerprint.

### `blender.scene.save`

Modes:

```text
save
save_as
save_copy
```

Never overwrite unexpectedly. Return path, file hash, revision, and external-file warnings.

## 10.5 Typed operation families

Expose these through `blender.scene.apply` and optionally as convenient single-operation tools.

### Object/collection

```text
collection.create
collection.move_object
object.create_primitive
object.duplicate
object.transform
object.parent
object.rename
object.set_visibility
object.set_origin
object.delete
object.ground_to_surface
object.align_to_surface
object.place_in_bbox
```

### Modifiers and geometry

```text
modifier.add
modifier.update
modifier.remove
modifier.apply
geometry.shade_smooth_by_angle
geometry.add_bevel
geometry.add_subdivision
geometry.add_solidify
geometry.add_displacement
geometry.recalculate_normals
geometry.uv_unwrap
geometry.set_texel_density
geometry.prepare_for_render
```

Use discriminated schemas for supported modifier types. Do not accept arbitrary property dictionaries without validation.

### Materials

```text
material.create_principled
material.import_pbr_set
material.assign
material.set_principled_parameters
material.set_mapping
material.add_imperfection_layer
material.create_glass
material.create_metal
material.create_dielectric
material.validate
```

### Camera

```text
camera.create
camera.configure
camera.look_at
camera.frame_refs
camera.set_dof
camera.set_active
camera.create_turntable_set
```

### Lighting/world

```text
world.set_hdri
world.rotate_hdri
world.set_strength
lighting.create
lighting.configure
lighting.create_studio_rig
lighting.create_sun_sky
lighting.set_linking
lighting.delete_rig
```

### Render/compositor

```text
render.configure
render.enable_passes
render.configure_output
color.configure
compositor.configure_photoreal_finish
```

Every operation must state whether it is read-only, mutating, destructive, idempotent, reversible, or open-world/networked in its metadata/documentation.

---

## 11. Photorealism-specific implementation requirements

Photorealism is a pipeline property. No single material or renderer setting fixes it.

## 11.1 Reference-driven workflow

Add a first-class reference system:

```text
blender.reference.register
blender.reference.inspect
blender.reference.remove
blender.reference.compare
```

A reference record should contain:

- image artifact;
- intended use: composition, material, lighting, object shape, color;
- real dimensions if known;
- camera/lens metadata if known;
- crop/aspect;
- copyright/source notes supplied by the user;
- visual analysis;
- linked scene objects/materials.

The agent should state which reference property it is trying to match. "Make it realistic" without a target is too vague for reliable iteration.

## 11.2 Real-world units and scale

The MCP must expose and validate:

- scene unit system;
- `scale_length`;
- object dimensions in both scene units and meters;
- imported asset source units;
- camera distance and focal length;
- texture mapping scale in meters;
- displacement amplitude in meters or millimeters;
- light dimensions and distance.

Warnings:

- unknown scale;
- suspiciously tiny/large objects;
- inconsistent related object scales;
- unapplied non-uniform scale where it affects modifiers or shading;
- imported asset normalized without preserving provenance.

## 11.3 Geometry realism

Required capabilities:

- small physically plausible bevels on manufactured edges;
- smooth-by-angle and normal inspection;
- subdivision only where silhouette or displacement needs it;
- true displacement or bump chosen according to camera distance;
- enough geometry for close-ups;
- no accidental razor edges;
- no non-manifold or flipped surfaces in visible/render-critical areas;
- contact and intersection checks;
- actual thickness for objects where transmission or silhouette requires it;
- sensible instancing for repeated details.

`geometry.prepare_for_render` must be a dry-run-first diagnostic/operation planner, not a blind "add bevel and subdivision to everything" button.

Suggested result:

```json
{
  "recommendations": [
    {
      "ref": {},
      "issue": "razor_edges",
      "proposed_operation": {
        "op": "geometry.add_bevel",
        "width_m": 0.0008,
        "segments": 3,
        "angle_limit_deg": 35
      },
      "risk": "medium",
      "reason": "Object occupies 640 px and has hard manufactured edges."
    }
  ]
}
```

## 11.4 PBR materials

Create a versioned material node group or builder, for example `MCP_PBR_v1`, instead of generating unique node spaghetti each time.

PBR import must understand semantic maps:

```text
base color/albedo/diffuse
roughness
glossiness, with inversion when required
metallic
normal OpenGL
normal DirectX, with green-channel conversion
height/displacement
ambient occlusion
opacity
emission
transmission or specular maps where supplied
```

Rules:

- color textures use an appropriate color space such as sRGB;
- scalar/vector data maps use Non-Color;
- normal maps pass through a Normal Map node;
- displacement scale and midpoint are explicit;
- material mapping has real-world dimensions;
- packed ORM maps are split correctly;
- missing maps do not leave broken links;
- node socket differences between Blender versions are handled in an adapter;
- material presets remain editable and inspectable;
- imported images are cached and deduplicated by content hash;
- paths are made portable or packed only according to user policy.

Photorealistic imperfections should be semantic and scale-aware:

- fingerprints on frequently touched glossy surfaces;
- dust on upward surfaces;
- micro-scratches following manufacturing/use direction;
- roughness variation before obvious color grunge;
- edge wear only where contact plausibly occurs;
- fabric weave at physically plausible scale;
- subtle normal variation on painted/coated surfaces.

Do not automatically cover every asset in uniform procedural dirt. Humans already invented enough ugly shortcuts.

## 11.5 Lighting

Lighting tools must expose physical relationships, not only arbitrary strength sliders.

Capabilities:

- Poly Haven or local HDRI assignment;
- environment rotation, strength, background visibility, and separate background treatment;
- area light size, shape, power, distance, and color temperature;
- sun/sky configuration;
- key/fill/rim or key/fill/background-card rig with named collections;
- negative fill and reflection cards as geometry when useful;
- light linking when supported;
- shadow catcher setup;
- exposure diagnostics;
- visible catchlight/reflection diagnostics for product work.

`lighting.create_studio_rig` should return a named rig manifest and accept a profile:

```text
soft_product
hard_product
beauty_portrait
interior_window_fill
neutral_reference
```

Profiles provide a starting point, not a final artistic answer.

## 11.6 Camera and composition

Camera tooling must support:

- focal length and sensor size;
- perspective or orthographic mode;
- shift and clipping;
- look-at target without unstable Euler guesswork;
- framing objects with margins;
- aspect ratio and safe areas;
- depth of field with focus object or explicit distance;
- aperture/f-stop and blade settings;
- focus-plane diagnostics;
- camera coverage and clipped-subject warnings;
- turntable or multi-angle camera generation;
- reference composition comparison.

Do not simulate realism by applying excessive depth of field. The validation layer should warn when the focal plane misses the subject or the blur destroys required detail.

## 11.7 Color management and output

Expose:

- view transform, look, exposure, gamma, display, white balance where available;
- scene-linear workflow status;
- false-color diagnostic capture;
- PNG/JPEG display output;
- 16- or 32-bit OpenEXR output;
- multilayer OpenEXR with selected passes;
- output color-space policy;
- compositor status and node graph summary.

Provide profiles such as:

```text
agx_general
pbr_neutral_product
scene_linear_exr
custom
```

Choose by intended deliverable. Do not hardcode a single look for every scene.

## 11.8 Render settings

`render.configure` should accept intent rather than forcing the agent to know every version-specific Cycles property:

```json
{
  "engine": "CYCLES",
  "quality_profile": "preview|review|final",
  "device_policy": "auto|gpu|cpu",
  "noise_target": 0.03,
  "max_samples": 256,
  "denoise": true,
  "denoise_passes": "albedo_normal",
  "light_tree": "auto",
  "transparent_film": false,
  "overrides": {}
}
```

The adapter maps this to supported Blender settings and returns applied values. Runtime capability discovery decides between OptiX, CUDA, HIP, Metal, oneAPI, or CPU. Never assume the user's RTX device is available merely because it exists physically.

## 11.9 Compositing and lens effects

Offer subtle, bounded options:

- glare/bloom;
- vignette;
- lens distortion;
- chromatic aberration;
- film grain;
- color balance;
- mist/atmosphere;
- denoise and sharpening.

Default to disabled or conservative. "Photorealistic" is not a license to pour cinematic seasoning over broken geometry.

---

## 12. Asset pipeline

## 12.1 Provider abstraction

```python
class AssetProvider(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...
    def search(self, request: AssetSearchRequest) -> AssetSearchPage: ...
    def preview(self, asset_id: str) -> ArtifactRef: ...
    def resolve_download(self, request: AssetAcquireRequest) -> AssetManifest: ...
    def download(self, manifest: AssetManifest, job: JobContext) -> CachedAsset: ...
    def license(self, asset_id: str) -> LicenseRecord: ...
```

Providers must not directly mutate Blender. Acquisition ends in a validated cache artifact; a separate import operation changes the scene.

## 12.2 Common asset tools

```text
blender.asset.providers
blender.asset.search
blender.asset.preview
blender.asset.acquire
blender.asset.import
blender.asset.cached
blender.asset.license
blender.asset.remove_cached
```

Search output must be structured, paginated, and include:

- provider;
- asset ID and name;
- type;
- dimensions/scale if known;
- available resolutions/formats;
- preview artifact;
- author/source/license/API terms metadata;
- polygon count where available;
- download size;
- relevance and filters.

## 12.3 Poly Haven

Implement:

- unique application User-Agent;
- current API-terms acknowledgement in configuration;
- provider attribution in UI/docs where required;
- cache by asset ID, resolution, format, and content hash;
- download URL, expected hash, size, and dependencies from API metadata;
- resumable or restart-safe downloads;
- checksum and size validation;
- offline reuse;
- HDRI, texture, and model manifests;
- explicit resolution selection;
- no silent 8K default.

API conditions and endpoints may change. Keep the provider isolated and covered by contract tests.

## 12.4 Sketchfab and other libraries

For each asset:

- filter for downloadable content;
- capture the returned license and author;
- preserve attribution requirements;
- never imply the MCP owns the asset;
- preview before download when possible;
- isolate provider authentication;
- normalize units and axes after import;
- preserve original downloaded archive and manifest hash.

## 12.5 Generated assets

Hyper3D, Hunyuan3D, or other generation providers are asynchronous and optional.

Required workflow:

```text
submit -> job ID -> poll/progress -> acquire artifact -> validate archive
-> import to isolated collection -> normalize -> inspect -> visual review
-> accept or delete
```

Post-import checks:

- actual dimensions and units;
- origin and ground plane;
- axis orientation;
- manifold state;
- overlapping/disconnected components;
- UVs;
- material paths and color spaces;
- texture resolution;
- excessive polygon count;
- duplicate materials/images;
- hidden geometry;
- licensing/provider provenance;
- visual comparison with prompt/reference.

Generated assets should be a fallback for unique objects, not the default source for an entire scene.

## 12.6 Resolution and memory policy

Select texture resolution from:

- expected on-screen pixel footprint;
- UV coverage and texel density;
- camera distance;
- number of materials/textures;
- available GPU memory and render-device policy;
- whether the shot is a close-up;
- final output resolution.

Report the decision. Do not use a simplistic "8K is more realistic" rule.

## 12.7 Import normalization

Every import should land in a temporary or isolated collection and return an import manifest.

Pipeline:

1. validate file/archive and MIME type;
2. extract safely;
3. record source manifest and license;
4. import using a version-compatible adapter;
5. discover newly created data blocks by before/after IDs, not only names;
6. assign MCP refs;
7. fix axes/units according to declared source metadata;
8. compute actual bounds;
9. optionally scale to a real target dimension, preserving scale factor in provenance;
10. deduplicate images/materials by hash when safe;
11. find missing files;
12. validate materials and geometry;
13. place/ground only when explicitly requested;
14. capture preview and run visual review;
15. commit or remove imported collection.

---

## 13. Render job architecture

## 13.1 Why renders are jobs

Preview and final renders can be slow, memory-heavy, cancellable, and failure-prone. They should use MCP task support where the client supports it. Provide a custom job fallback for clients without task support.

Tools:

```text
blender.render.preview
blender.render.final
blender.render.region
blender.job.get
blender.job.cancel
```

## 13.2 Job state machine

```text
queued
preparing_snapshot
validating
starting_worker
loading_scene
compiling_kernels
rendering
compositing
writing_outputs
analyzing
completed
failed
cancelling
cancelled
```

Do not report a job complete until required output files and manifests exist and hashes are computed.

## 13.3 Background worker sequence

1. Validate current scene and camera.
2. Save an immutable temporary `.blend` copy.
3. Write render job JSON.
4. Launch matching Blender executable in background mode.
5. Apply job overrides in worker script.
6. Register lightweight render handlers.
7. Render.
8. Write image(s), EXR/pass outputs, logs, and result manifest.
9. Compute hashes.
10. Optionally run deterministic and VLM analysis.
11. Return job result.
12. Clean temporary snapshot according to retention policy.

Cancellation:

- request graceful Blender cancellation/termination;
- use a timeout before force-kill;
- preserve partial logs;
- never label partial output as final;
- release job locks and temporary files.

## 13.4 Render profiles

Profiles are defaults plus explicit applied settings, not magic names.

### `draft`

- small resolution;
- low samples/high noise target;
- denoise;
- limited expensive features;
- fast iteration.

### `review`

- medium resolution;
- enough samples for material/lighting judgement;
- denoise with supporting passes;
- main render passes enabled.

### `final`

- requested deliverable resolution;
- user/scene-appropriate noise target and max samples;
- output depth/format policy;
- required passes and EXR;
- deterministic seed recorded;
- no hidden quality reductions unless reported.

Do not encode universal sample counts as truth. The job manifest must contain actual values.

## 13.5 Render manifest

```json
{
  "job_id": "...",
  "status": "completed",
  "scene_revision": 52,
  "scene_snapshot_sha256": "...",
  "blend_file_sha256": "...",
  "blender_version": "...",
  "blender_build_hash": "...",
  "camera_ref": {},
  "frame": 1,
  "engine": "CYCLES",
  "device": {
    "backend": "OPTIX",
    "devices": []
  },
  "settings": {},
  "color_management": {},
  "passes": [],
  "assets": [],
  "outputs": [],
  "warnings": [],
  "started_at": "...",
  "completed_at": "...",
  "duration_ms": 0
}
```

---

## 14. Photorealism validation and quality gates

Implement validators as independent, testable checks returning issue codes. Do not bury them in prompts.

## 14.1 Issue format

```json
{
  "code": "MATERIAL_NORMAL_MAP_WRONG_COLORSPACE",
  "severity": "error",
  "category": "material",
  "message": "Normal map is configured as sRGB.",
  "refs": [],
  "evidence": {},
  "suggested_operations": [],
  "autofix_available": true,
  "confidence": 1.0
}
```

Severity:

```text
info
warning
error
blocking
```

Only truly unsafe or invalid final-render conditions should block by default. Artistic warnings remain overridable.

## 14.2 Scene and scale checks

- unit system absent/unknown;
- implausible dimensions relative to declared subject type;
- inconsistent scale across related objects;
- unapplied non-uniform scale affecting bevel/displacement/normal behavior;
- origin or transform anomalies;
- duplicate overlapping imports;
- hidden render-critical collections.

## 14.3 Geometry checks

- non-manifold/open geometry where inappropriate;
- flipped normals;
- degenerate/zero-area faces;
- razor edges on close-up manufactured objects;
- insufficient silhouette resolution;
- excessive geometry for shot distance;
- visible intersections;
- floating objects/contact gaps;
- z-fighting/copanar surfaces;
- missing thickness for transmissive objects;
- unapplied modifiers needed by export/render policy;
- subdivision/displacement mismatch.

## 14.4 UV and texture checks

- no UVs where image textures require them;
- UV stretch/overlap warnings according to material intent;
- inconsistent texel density;
- missing texture files;
- broken packed paths;
- low resolution for projected footprint;
- unnecessarily high resolution for memory budget;
- wrong map color space;
- DirectX normal interpreted as OpenGL;
- disconnected texture nodes;
- displacement present but ineffective;
- obvious tiling at camera distance.

## 14.5 Material checks

- no assigned material on visible surface;
- unsupported/broken node graph;
- non-finite values;
- suspiciously uniform perfect roughness;
- impossible or suspicious material parameter combinations, reported as warnings rather than dogma;
- glass/transmission without thickness or adequate bounces;
- emission unintentionally lighting the scene;
- duplicate near-identical materials;
- image alpha ignored or misused.

## 14.6 Lighting checks

- no meaningful light source;
- world accidentally black/overpowered;
- clipped highlights/shadows from preview metrics;
- subject lacks separation or grounding;
- light dimensions inconsistent with desired shadow softness;
- HDRI visible but incorrectly mapped/rotated;
- excessive fireflies/noise risk;
- many lights without effective sampling settings;
- conflicting color casts.

## 14.7 Camera checks

- no active camera;
- camera inside geometry;
- clipping planes cut visible subject;
- subject outside frame or unsafe margins;
- extreme lens distortion without intent;
- focus plane misses primary subject;
- excessive DOF blur;
- resolution/aspect mismatch with reference/deliverable;
- unintended perspective convergence or orthographic camera.

## 14.8 Render/output checks

- final profile using an unintended preview engine;
- no compatible device available;
- output directory inaccessible;
- lossy/low-bit-depth only when scene-linear grading is required;
- required passes disabled;
- denoising enabled without useful guide passes when post-denoising is requested;
- transparent film/output mismatch;
- compositor references missing nodes/images;
- animation output set to a fragile direct video workflow rather than image sequence;
- estimated memory pressure too high;
- stale scene revision between validation and snapshot.

## 14.9 Image diagnostics

Deterministic metrics:

- luminance histogram;
- clipped-black and clipped-highlight percentages;
- dynamic range estimate;
- saturation distribution;
- white-balance estimate;
- sharpness/edge-energy estimate;
- alpha/subject coverage;
- hot-pixel/firefly candidates;
- flat-region noise estimate;
- depth range and invalid pixels;
- object-mask coverage and overlaps.

Vision diagnostics:

- composition;
- visible floating/intersection problems;
- material plausibility;
- repeated texture patterns;
- scale cues;
- lighting direction/quality;
- shadow and reflection consistency;
- excessive denoise/plastic look;
- artificial edge perfection;
- camera/DOF problems;
- match to supplied reference.

Do not collapse these into one authoritative realism number. A score may be included as navigation, never as proof.

---

## 15. Security and safety

## 15.1 Network

- bind Blender bridge to loopback by default;
- authenticate each session with an unguessable token;
- reject remote binding unless explicitly enabled with authentication and transport security;
- limit connections, frames, payload size, and request rate;
- redact tokens and API keys from logs;
- rotate session tokens at launch.

## 15.2 Filesystem

- define allowed read/write roots;
- canonicalize paths and reject traversal;
- reject symlink escape where relevant;
- protect against zip/tar path traversal;
- cap archive size, extracted size, file count, and compression ratio;
- validate extensions and MIME signatures;
- never overwrite arbitrary user files without explicit path and policy;
- store provider credentials outside `.blend` files and tool output.

## 15.3 Arbitrary Python

Keep `execute_blender_code` only as a developer-only escape hatch.

Requirements:

- disabled by default;
- explicit `--developer-tools` or preference;
- clear destructive/open-code annotation;
- snapshot before execution where possible;
- timeout/cancellation strategy;
- bounded stdout/stderr;
- no returned secrets;
- operation log containing code hash and caller intent;
- no claim that `exec` inside Blender is a secure sandbox.

A read-only Python variant is not automatically safe. Python cannot be reliably sandboxed merely by omitting a few imports.

## 15.4 Human control

Require confirmation policy for:

- deleting many objects/data blocks;
- overwriting a `.blend` or output;
- restoring a snapshot;
- executing arbitrary Python;
- downloading assets with unresolved API/license terms;
- external network use when disabled by policy;
- rendering with unusually high resource estimates.

---

## 16. Agent operating policy

Ship a prompt/resource that tells GLM-5.2 Max how to use the system.

## 16.1 Start of task

1. Call `blender.system.capabilities`.
2. Call `blender.scene.summary`.
3. Read recent scene changes if continuing prior work.
4. Capture current camera or relevant viewport.
5. Call `blender.vision.analyze` when vision is available.
6. State assumptions and a bounded change plan.
7. Save or snapshot before broad changes.

## 16.2 During work

- Use stable refs, not names, after discovery.
- Group related changes in one transaction.
- Make one coherent visual hypothesis per iteration.
- Capture a new visual result after geometry, material, camera, or lighting changes that affect appearance.
- Read the change set after mutation.
- Do not modify camera, lighting, materials, and compositing simultaneously when an A/B comparison is needed.
- Prefer scanned/library assets, then existing local assets, then procedural/manual construction, then generated 3D.
- Prefer real scale and reference measurements over aesthetic guessing.
- Do not add dirt, DOF, bloom, or grain merely because the goal says "realistic."
- Do not repeatedly download the same asset.
- Do not use arbitrary Python when a typed tool exists.

## 16.3 Before final render

1. Run `blender.scene.validate(profile="pre-final-render")`.
2. Resolve or explicitly waive blocking/errors.
3. Confirm active camera and frame.
4. Confirm output directory and formats.
5. Confirm scene revision has not changed after validation.
6. Launch final render job.
7. Inspect manifest and output existence/hash.
8. Analyze final beauty image and relevant passes.
9. Save the accepted `.blend` file or copy.
10. Return output links, manifest, warnings, and unresolved artistic choices.

## 16.4 Iteration budget

Default to a bounded loop, for example up to five preview-analysis-adjust cycles, unless the user explicitly asks for broader exploration. A loop without a stopping condition is not craftsmanship; it is a computer discovering procrastination.

---

## 17. Implementation phases

Each phase must leave the repository in a working, tested state. Do not start all phases in parallel.

## Phase 0 - Inventory and baseline

### Work

- initialize all three submodules;
- record SHAs/remotes and current architecture;
- list every MCP tool/resource/prompt and every Blender command handler;
- run current tests;
- run an end-to-end launch and health call;
- test current screenshot behavior;
- test whether the actual MCP host passes image results to GLM-5.2 Max;
- record current latency and failure behavior;
- inspect thread use, blocking network calls, temp-file cleanup, and background mode;
- identify exact Blender/Python/MCP SDK versions.

### Deliverables

- `docs/mcp_current_state_inventory.md`
- baseline tool catalog JSON
- baseline test/log bundle
- feature-gap matrix mapping existing code to this plan
- explicit decision on vision mode

### Done when

No later phase depends on guessed file names or guessed existing behavior.

## Phase 1 - Protocol, lifecycle, and safety foundation

### Work

- implement framed IPC v1;
- add handshake/capability discovery;
- add request IDs, deadlines, scene revision fields, error schema, and auth token;
- implement non-blocking Blender main-thread poller;
- move HTTP/download work out of Blender;
- add connection retry/reconnect;
- add payload limits and path root validation;
- retain v0 command compatibility adapter;
- resolve the conflict between `--background` launcher mode and interactive bridge requirements.

### Tests

- partial frame delivery;
- multiple frames in one packet;
- malformed length/JSON;
- oversized frame;
- wrong token;
- disconnect during response;
- reconnect after Blender restart;
- deadline expiry;
- 1,000 small sequential requests;
- unregister/re-register without duplicate timers/handlers.

### Done when

- no normal tool depends on unframed JSON parsing;
- no provider download runs inside Blender;
- Blender remains responsive during connection activity;
- errors are structured and correlated;
- compatibility tools still work with deprecation warnings.

## Phase 2 - Stable structured perception

### Work

- implement persistent refs and fallback refs for linked data;
- implement revision tracker and bounded change sets;
- implement scene summary, query, object/material/camera/light/render inspection;
- use evaluated dependency graph for render-relevant geometry;
- implement pagination and field projection;
- expose resources;
- integrate `blender_read_mode` and `blender_graph_tracker` rather than duplicating them.

### Tests

- rename object and resolve by UUID;
- duplicate object and ensure distinct UUID;
- linked/read-only object reference;
- 10,000-object pagination;
- Geometry Nodes/instances/evaluated mesh fixture;
- material with missing texture;
- multiple scenes/view layers;
- undo/redo and user UI change revisions;
- bounded payload size.

### Done when

The agent can reconstruct all render-relevant state without `execute_python` and without relying on a screenshot.

## Phase 3 - Visual perception and vision bridge

### Work

- harden offscreen capture;
- add camera, canonical-view, framing, overlay, and resolution controls;
- add headless/camera fallback and honest capability reporting;
- implement artifact-return contract;
- implement capture bundles and object-label overlays;
- implement deterministic image metrics;
- implement pluggable vision broker;
- add GLM-5V-Turbo sidecar adapter or selected equivalent;
- validate structured vision output;
- add A/B comparison.

### Tests

- capture with hidden/minimized Blender window;
- capture when no 3D area exists;
- capture active camera and named camera;
- repeated captures with no orphan images/GPU resources;
- annotated object IDs map to valid refs;
- vision provider unavailable/invalid JSON/timeout;
- calibration scenes with known composition, floating-object, clipping, and exposure defects;
- text-only agent receives useful report without image input.

### Done when

GLM-5.2 Max can explain what visibly changed and identify seeded visual defects through structured results.

## Phase 4 - Transactions and typed core mutations

### Work

- implement scene revision preconditions;
- implement transaction begin/commit/rollback;
- implement dry-run and operation planning;
- implement batch `scene.apply`;
- add typed collection/object/transform/visibility/parenting/primitive/modifier operations;
- add operation provenance and before/after change reports;
- gate arbitrary Python behind developer mode.

### Tests

- invalid second operation causes no partial committed batch, or rollback restores fingerprint;
- stale revision rejects before mutation;
- idempotency key prevents duplicate object creation on retry;
- rollback after operator exception;
- object deleted by user between plan and apply;
- exact changed-ref reporting;
- user undo/redo integration.

### Done when

At least 80 percent of the core benchmark scene-edit actions require no arbitrary Python and are reversible or explicitly marked otherwise.

## Phase 5 - Materials and asset acquisition

### Work

- implement version-adapted PBR material builder;
- implement map semantic detection and explicit overrides;
- enforce color-space and normal-map rules;
- add mapping scale and displacement configuration;
- implement material validator;
- implement provider base, cache, manifests, checksums, licenses, and secure extraction;
- implement Poly Haven through external worker/service;
- implement import normalization and isolated collection review;
- migrate existing in-Blender provider code.

### Tests

- fixture PBR sets using common naming conventions;
- sRGB vs Non-Color correctness;
- DirectX normal conversion;
- packed ORM;
- missing map and missing file;
- interrupted/resumed download;
- checksum mismatch;
- offline cache reuse;
- archive traversal attack;
- duplicate texture hash reuse;
- imported scale/orientation manifest.

### Done when

A searched PBR asset can be acquired, validated, imported, assigned, inspected, and reviewed without blocking Blender or losing provenance.

## Phase 6 - Camera, lighting, render, and color pipeline

### Work

- implement camera framing/look-at/DOF tools;
- implement HDRI/world and typed lights/studio rig;
- implement Cycles/device discovery and render profile adapter;
- implement color-management profiles;
- implement passes and output configuration;
- implement background Blender render worker;
- implement MCP tasks plus job fallback;
- implement progress, cancellation, manifests, and output artifacts;
- add preview and region rendering.

### Tests

- OptiX/CUDA/CPU capability and fallback fixtures/mocks;
- no GPU available;
- render cancellation;
- worker crash;
- output permission failure;
- current scene changes after snapshot do not alter running job;
- multilayer EXR/pass presence;
- camera clipping and DOF fixture;
- same job manifest is reproducible except timestamps/duration.

### Done when

The agent can configure, launch, monitor, cancel, inspect, and reproduce a preview/final render without freezing the interactive bridge.

## Phase 7 - Photorealism validators and review loop

### Work

- implement validation issue registry;
- implement scene/geometry/UV/material/camera/light/render/file checks;
- implement deterministic image diagnostics;
- implement final visual review profile;
- attach suggested typed operations to fixable issues;
- implement waiver/override records;
- add reference comparison workflow.

### Tests

Seed each issue in a fixture and verify:

- issue code;
- severity;
- related refs;
- evidence;
- no mutation;
- suggested operation validity where offered;
- waiver behavior.

### Done when

A final render cannot be marked accepted without an explicit validation result, output manifest, and visual review status.

## Phase 8 - Optional model libraries and generated 3D

### Work

- migrate Sketchfab to provider architecture;
- add preview/license/filter support;
- migrate Hyper3D and Hunyuan to common asynchronous job contract;
- add generated-asset import cleanup and quality review;
- isolate provider failures and credentials;
- add provider feature flags and dynamic tool listing.

### Tests

- provider disabled/no key/rate limit;
- generation queued/completed/failed/cancelled;
- malformed archive;
- poor generated geometry rejected or quarantined;
- license metadata preserved;
- no duplicate generation when cached artifact exists.

### Done when

External asset services are optional plugins, not structural dependencies of scene control.

## Phase 9 - Hardening, compatibility, and benchmarks

### Work

- support selected Blender versions through adapters/capabilities;
- run soak and failure-injection tests;
- tune output/token budgets;
- test Windows paths/process lifecycle;
- add Linux virtual-display CI for interactive capture where feasible;
- benchmark on the user's target machine;
- create user/developer docs;
- remove obsolete compatibility paths only after migration evidence;
- run end-to-end photorealism benchmark scenes.

### Done when

All acceptance scenarios pass, known limitations are documented, and benchmark evidence is committed.

---

## 18. Testing strategy

## 18.1 Unit tests outside Blender

- schema validation and JSON serialization;
- frame encoding/decoding;
- retry/idempotency logic;
- error mapping;
- asset search normalization;
- cache keys and hash verification;
- safe archive extraction;
- PBR filename semantic mapping;
- render job state machine;
- manifest generation;
- vision JSON validation;
- path policy and log redaction.

## 18.2 Blender integration tests

Use small `.blend` fixtures:

```text
empty_scene.blend
basic_product.blend
large_object_count.blend
linked_library.blend
geometry_nodes_instances.blend
pbr_materials.blend
missing_textures.blend
camera_dof.blend
lighting_hdri.blend
nonmanifold_geometry.blend
intersections_and_floating.blend
multi_scene_view_layer.blend
```

Tests should launch the exact built/installed Blender executable used by the project.

## 18.3 Visual golden tests

Exact pixels can change across GPU, driver, Blender build, denoiser, and color configuration. Use layers of assertions:

1. exact structured state for tool results;
2. exact artifact dimensions/modes/hashes only for stable synthetic outputs;
3. tolerant image metrics for viewport/render outputs;
4. perceptual comparison ranges;
5. seeded-defect detection;
6. human review for final benchmark quality.

Never update golden images automatically merely because CI failed.

## 18.4 Failure injection

Test:

- Blender closes mid-request;
- MCP server restarts;
- half frame received;
- render worker hangs;
- render cancellation races completion;
- asset server returns wrong content length;
- provider returns invalid JSON;
- disk full or permission denied;
- image file disappears before analysis;
- VLM returns prose instead of JSON;
- object renamed/deleted between read and write;
- undo stack unavailable;
- no active camera;
- no 3D viewport;
- no GPU device;
- unsupported node socket/property in a Blender version.

## 18.5 Performance budgets

Measure p50 and p95 on named hardware/software. Suggested release budgets, to be confirmed after baseline:

| Operation | Target |
|---|---:|
| IPC routing overhead, excluding Blender work | p95 under 25 ms |
| small scene summary | p95 under 100 ms |
| first page of 10,000-object query | p95 under 500 ms |
| warm 1024 px viewport capture | aspiration under 250 ms, release gate under 750 ms |
| bounded tool JSON payload | normally under 256 KiB, paginated above it |
| repeated capture/query soak | no unbounded memory or orphan data growth |

Do not advertise `<100 ms` viewport capture as a platform guarantee until measurements include GPU readback, color management, PNG encoding, file/artifact handling, and MCP transfer.

---

## 19. End-to-end acceptance scenarios

## Scenario A - Product render

Input:

- simple untextured manufactured object;
- real dimensions;
- one or more visual references.

Agent must:

1. inspect geometry/scale;
2. add only justified edge treatment;
3. acquire or create plausible plastic/metal/rubber materials;
4. create neutral studio environment;
5. frame camera and set restrained DOF;
6. render preview;
7. diagnose grounding, highlights, roughness, and composition;
8. make at least one evidence-based A/B change;
9. pass final validation;
10. produce PNG, optional EXR, `.blend` copy, and manifest.

## Scenario B - Interior corner

Input:

- room shell, furniture placeholders, window opening;
- daylight reference.

Agent must:

- maintain real scale;
- use wood/fabric/glass maps correctly;
- avoid obvious texture repetition;
- establish window/HDRI/sun lighting;
- keep exposure and white balance plausible;
- detect floating furniture and clipping;
- produce review and final outputs with passes.

## Scenario C - Repair an existing messy scene

Seed:

- duplicate materials;
- missing textures;
- wrong normal-map color space;
- non-uniform scale;
- camera clipping;
- output set to an unsuitable format;
- one user movement during agent work.

Agent must:

- detect issues;
- handle stale revision;
- make typed fixes;
- preserve unrelated user change;
- report unresolved ambiguity rather than guessing destructively.

## Scenario D - Robust cancellation

- launch long final render;
- cancel through MCP;
- verify worker terminates;
- verify job state is cancelled;
- verify partial output is not labeled final;
- verify interactive Blender remains usable;
- verify logs and cleanup.

## Scenario E - Text-only visual loop

- use GLM-5.2 Max as planning model;
- do not provide image input directly to it;
- use vision sidecar analysis;
- verify it can identify and fix seeded floating-object, clipping, and roughness problems through structured visual reports.

---

## 20. Benchmark and evaluation

Measure more than tool-call success.

### 20.1 MCP/engineering metrics

- tool execution success rate;
- end-to-end task success rate;
- recovery after failed/stale call;
- p50/p95 latency by tool;
- render/job completion/cancellation rate;
- malformed response rate;
- scene revision conflicts;
- arbitrary-Python fallback frequency;
- memory/resource leak indicators;
- provider cache hit rate;
- number of iterations to accepted result.

### 20.2 Render quality evaluation

Use:

- reference-match review;
- blind human preference between baseline and MCP result;
- seeded-defect detection/repair;
- technical validation counts;
- preservation of subject dimensions and material intent;
- consistency across repeated runs;
- output/manifest completeness.

A vision model may provide critique, but should not be the sole judge of its own workflow.

---

## 21. Documentation deliverables

Required:

- architecture and sequence diagrams;
- protocol v1 specification;
- generated tool reference with input/output examples;
- supported Blender/version/capability matrix;
- security model;
- vision-mode configuration guide;
- provider/API/license guide;
- render-worker guide;
- troubleshooting guide;
- migration guide from old tool names;
- benchmark report;
- known limitations;
- developer instructions for adding a typed operation, validator, or provider.

---

## 22. Commit and implementation discipline for GLM-5.2 Max

GLM-5.2 Max should follow these rules while implementing:

1. Inspect before editing.
2. Preserve existing working behavior unless the phase explicitly replaces it.
3. Work in vertical slices: schema, server tool, bridge handler, tests, docs.
4. Keep each commit focused on one capability or refactor prerequisite.
5. Run relevant unit and Blender integration tests after each slice.
6. Never mark a phase complete from code inspection alone.
7. Record commands, outputs, fixtures, and limitations in `docs/MCP_IMPLEMENTATION_STATUS.md`.
8. Do not edit Blender core unless a reproducible Python API limitation is documented and an add-on/worker solution was evaluated first.
9. Do not touch unrelated changes such as `BLI_normalized_int_types.hh` as part of this MCP plan.
10. Do not rewrite all three submodules at once.
11. Preserve backward compatibility until the new path has end-to-end evidence.
12. Do not hardcode a specific GPU, absolute path, user account, API key, or Blender install location.
13. Keep secrets out of commits, `.blend` files, logs, screenshots, and tool responses.
14. When uncertain about Blender API behavior, write a minimal executable probe/test instead of inventing an answer.

After each phase, report:

```text
Implemented
Files changed
Tests run and exact results
Manual evidence
Known limitations
Compatibility impact
Next phase entry conditions
```

---

## 23. Explicit anti-patterns

Reject implementations that do any of the following:

- return only a screenshot path and claim the agent saw it;
- depend on GLM-5.2 Max directly understanding an image;
- dump every object/material/node into one enormous tool response;
- identify objects only by name;
- use arbitrary Python for routine operations;
- perform HTTP downloads or polling in Blender's main thread;
- leave persistent Python threads interacting with Blender;
- mutate the scene during read or validation calls;
- silently apply scale, delete objects, overwrite files, or change render settings;
- return errors as successful prose;
- hold an MCP tool call open for an entire final render without tasks/progress/cancellation;
- store unverified provider archives in the scene;
- ignore licenses/API conditions;
- force 8K textures or maximum samples regardless of shot needs;
- add bevel, subdivision, dirt, DOF, bloom, and grain indiscriminately;
- call a result photorealistic without inspecting a render;
- let a VLM mutate Blender directly;
- use a single realism score as an acceptance gate;
- alter Blender core to avoid designing a sound bridge.

---

## 24. Minimum useful release

The first genuinely useful release is complete only when it includes:

- framed/authenticated Blender IPC;
- health and capability discovery;
- stable refs and scene revisions;
- paginated structured scene/object/material/camera/light/render inspection;
- viewport/camera capture returning image plus metadata;
- working vision sidecar path for GLM-5.2 Max;
- transactions and typed transforms/material/camera/light/render operations;
- PBR import with correct map semantics;
- asynchronous Poly Haven acquisition and cache;
- background preview/final render jobs with progress/cancel;
- photorealism validation;
- final output manifest;
- end-to-end product-shot acceptance test.

Everything else can build on that foundation. Without those pieces, the system is still a remote Python console with a camera attached, which is an entertaining prototype but not a reliable rendering agent.

---

## 25. Final implementation order

Use this exact order unless phase-zero evidence proves a dependency must move:

```text
0. Inspect and baseline current submodules
1. Replace transport/lifecycle hazards
2. Build stable refs, revisions, and structured read model
3. Build visual capture plus GLM-compatible vision analysis
4. Build transactions and typed core operations
5. Build PBR material and external asset pipeline
6. Build physical camera/lighting/color/render jobs
7. Build validators and reference-driven review loop
8. Migrate optional asset/generation providers
9. Harden, benchmark, document, and retire compatibility paths
```

The central rule is simple: **the agent must be able to observe and verify before it receives more power to mutate.**
