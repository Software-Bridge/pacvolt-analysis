#!/bin/bash
# Launcher script for PacVolt Analysis on Mac/Linux
# Runs pva.py in a Docker container with all arguments passed through

echo "=============================="
echo "PacVolt Analysis Docker Launcher"
echo "=============================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Build the image if it doesn't exist or if requested
echo "Building Docker image..."
docker build -f Dockerfile.pva -t pva-app .

if [ $? -ne 0 ]; then
    echo "Error: Failed to build Docker image"
    exit 1
fi

# Stop any existing container
docker stop pva-container 2>/dev/null || true
docker rm pva-container 2>/dev/null || true

# Get the user's home directory
USER_HOME="$HOME"

# Mount the home directory and the current working directory
# This allows accessing files via absolute paths and relative paths
CURRENT_DIR=$(pwd)

echo "Starting container..."
echo "Mounting: $USER_HOME -> /home/user"
echo "Mounting: $CURRENT_DIR -> /workspace"

# Convert arguments - replace home directory paths with container paths
DOCKER_ARGS=()
for arg in "$@"; do
    # Replace home directory in paths
    if [[ "$arg" == "$USER_HOME"* ]]; then
        # Convert absolute path starting with HOME
        container_path="/home/user${arg#$USER_HOME}"
        DOCKER_ARGS+=("$container_path")
    elif [[ "$arg" == "~"* ]]; then
        # Convert tilde paths
        container_path="/home/user${arg#\~}"
        DOCKER_ARGS+=("$container_path")
    elif [[ "$arg" == "/"* ]]; then
        # For other absolute paths, try to make them relative to current dir
        # or leave as is (may not work in container)
        DOCKER_ARGS+=("$arg")
    else
        # Relative paths and flags pass through
        DOCKER_ARGS+=("$arg")
    fi
done

# Run the container
# - Mount home directory for data access
# - Mount current directory as working directory
# - Map port 8081 (host) to 5000 (container) for web interface
# - Remove container after exit
docker run --rm \
    --name pva-container \
    -v "$USER_HOME:/home/user" \
    -v "$CURRENT_DIR:/workspace" \
    -w /workspace \
    -p 8081:5000 \
    pva-app "${DOCKER_ARGS[@]}"

echo ""
echo "=============================="
echo "Container finished"
echo "=============================="
