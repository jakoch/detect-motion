# syntax=docker/dockerfile:1

# Use official Python slim image (Debian Trixie)
ARG PYTHON_VERSION=3.13-slim-trixie
FROM python:${PYTHON_VERSION}

# uv resolves and installs the project (pin the tag for reproducible builds)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000
RUN echo "Create vscode user (UID 1000)" && \
    groupadd --gid $USER_GID $USERNAME && \
    useradd --uid $USER_UID --gid $USER_GID -m $USERNAME && \
    apt-get update && \
    apt-get install -y --no-install-recommends sudo && \
    echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME

# Install OpenCV runtime dependencies, video codec support, and git
RUN echo "Install packages" && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1 \
    ffmpeg \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    git && \
    echo "Cleanup apt cache" && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY .devcontainer/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN echo "Copy entrypoint script" && \
    sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && \
    chmod +x /usr/local/bin/entrypoint.sh

# Install the project into a venv outside the workspace. A dev container
# bind-mounts the workspace over /workspaces/detect-motion, which would
# otherwise hide the installed environment.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspaces/detect-motion
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN echo "Install project with uv" && \
    uv sync --frozen

RUN echo "Create data directories with proper permissions for vscode user" && \
    mkdir -p /data/video /data/keep /data/drop && \
    chown -R vscode:vscode /data /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Use entrypoint for docker run, but allow override for dev container
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

CMD ["detect-motion", "--help"]
