# Unified Blender MCP test image.
# Pinned base + apt blender for reproducibility. CPU-only by design; GPU is optional.
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Pin Blender via Debian bookworm's blender package. bookworm ships blender 3.4.x.
# We record the exact version in the test status JSON at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         blender \
         ca-certificates \
         python3 \
         python3-pip \
         python3-venv \
         xvfb \
         mesa-utils \
         libgl1-mesa-dri \
         libgl1-mesa-glx \
         libegl1-mesa \
         libxrender1 \
         libxxf86vm1 \
         libxfixes3 \
         libxi6 \
         libxkbcommon0 \
         libsm6 \
         libice6 \
         libglx-mesa0 \
         curl \
         jq \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime.
RUN useradd --create-home --uid 1000 --shell /bin/bash blender
WORKDIR /opt/blender_mcp
RUN chown -R blender:blender /opt/blender_mcp

# Copy the three submodules + the top-level docs/plan.
COPY --chown=blender:blender tools/blender_mcp      ./tools/blender_mcp
COPY --chown=blender:blender tools/blender_read_mode ./tools/blender_read_mode
COPY --chown=blender:blender tools/blender_graph_tracker ./tools/blender_graph_tracker
COPY --chown=blender:blender docs                   ./docs

# Python path: repo tools root so `import blender_mcp` etc. work.
ENV PYTHONPATH=/opt/blender_mcp/tools

USER blender

# Default entrypoint is a shell; the compose file overrides the command per suite.
CMD ["bash", "-lc", "echo 'blender-mcp test image ready'; blender --version | head -3"]
