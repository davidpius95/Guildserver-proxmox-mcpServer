# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# openssh-client backs execute_container_command's `pct exec` path -- the
# Proxmox API has no LXC exec endpoint.
RUN apt-get update && apt-get install -y \
    git \
    curl \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install "mcp<2" mcpo uv

# Copy project files
COPY . .

# Create virtual environment and install dependencies
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install -e ".[dev]"

# Expose port
EXPOSE 8811

# Set environment variables
ENV PROXMOX_MCP_CONFIG="/app/proxmox-config/config.json"
ENV API_HOST="0.0.0.0"
ENV API_PORT="8811"

# Startup command
CMD ["mcpo", "--host", "0.0.0.0", "--port", "8811", "--", \
     "/bin/bash", "-c", "cd /app && source .venv/bin/activate && python -m proxmox_mcp.server"]
