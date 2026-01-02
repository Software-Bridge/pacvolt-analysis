#!/bin/bash
# Launcher script for Mac/Linux
# Starts the Docker container and opens the browser

echo "=============================="
echo "Hello World Docker Launcher"
echo "=============================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Build the image if it doesn't exist
echo "Building Docker image..."
docker build -f Dockerfile.hello -t hello-world-app .

# Stop any existing container
docker stop hello-world-container 2>/dev/null || true
docker rm hello-world-container 2>/dev/null || true

# Start the container in the background
echo "Starting container..."
docker run -d --name hello-world-container -p 8081:5000 hello-world-app

# Wait for the server to start
echo "Waiting for server to start..."
sleep 3

# Open the browser (Mac)
echo "Opening browser..."
open http://localhost:8081

echo ""
echo "=============================="
echo "✓ Application is running!"
echo "=============================="
echo "URL: http://localhost:8081"
echo ""
echo "To stop the application:"
echo "  docker stop hello-world-container"
echo "=============================="
