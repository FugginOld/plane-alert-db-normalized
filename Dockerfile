FROM python:3.10-slim

# git is required for repository operations (e.g. gitpython used by pipeline scripts).
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install Python dependencies before copying the rest of the repo so
# this layer is cached even when source files change.
COPY scripts/requirements.txt ./scripts/requirements.txt
RUN pip install --no-cache-dir -r scripts/requirements.txt

# Copy the full repository contents into the image.
# Volatile directories (data/, taxonomy/, cache/, build/, logs/) are
# expected to be bind-mounted at runtime so that changes made inside
# the container are persisted back to the host.
COPY . .

# Ensure directories that may not exist yet (logs, build artifacts) are
# present so the container starts cleanly even before bind mounts attach.
RUN mkdir -p \
        cache/public_sources \
        build/weekly_update \
        logs

# Make the weekly-update wrapper executable.
RUN chmod +x docker/weekly_update.sh

# Run as non-root user.
RUN useradd --no-create-home --shell /bin/false appuser
USER appuser

# Default command: interactive Bash shell.
# Override with a specific command when running non-interactively,
# e.g.:  docker run … aircraft-taxonomy-db /workspace/docker/weekly_update.sh
CMD ["/bin/bash"]
