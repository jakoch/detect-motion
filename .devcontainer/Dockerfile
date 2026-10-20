# syntax=docker/dockerfile:1

# Use official Python slim image (Debian Trixie)
ARG PYTHON_VERSION=3.13-slim-trixie
FROM python:${PYTHON_VERSION}

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
    apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx \
    ffmpeg \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    git && \
    echo "Cleanup apt cache" && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN echo "Copy entrypoint script" && \
    chmod +x /usr/local/bin/entrypoint.sh

RUN echo "Create data directories with proper permissions for vscode user" && \
    mkdir -p /data/video /data/keep /data/quarantine && \
    chown -R vscode:vscode /data

WORKDIR /workspaces/detect-motion

# Use entrypoint for docker run, but allow override for dev container
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

CMD ["detect-motion", "--help"]
