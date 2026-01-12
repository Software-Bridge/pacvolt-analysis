# Hello World Docker Application
#

Cross-platform "Hello World" web application demonstrating Docker deployment from Mac development to PC runtime.

## Prerequisites

**On PC (Windows):**
- Docker Desktop for Windows installed and running
- Git (to clone/transfer the files)

**On Mac (Development):**
- Docker Desktop for Mac installed and running

## Files

- `hello.py` - Python Flask web application
- `Dockerfile.hello` - Ubuntu-based Docker image configuration
- `run-hello.sh` - Mac/Linux launcher script
- `run-hello.bat` - Windows launcher script
- `docker-compose.hello.yml` - Docker Compose configuration (optional)

## Quick Start

### On Mac (Development/Testing)

1. Make the launcher script executable:
   ```bash
   chmod +x run-hello.sh
   ```

2. Run the application:
   ```bash
   ./run-hello.sh
   ```

3. The browser will automatically open to http://localhost:8081

### On PC (Windows)

1. Double-click `run-hello.bat` or run from Command Prompt:
   ```cmd
   run-hello.bat
   ```

2. The browser will automatically open to http://localhost:8081

## Alternative: Manual Docker Commands

### Build the image:
```bash
docker build -f Dockerfile.hello -t hello-world-app .
```

### Run the container:
```bash
docker run -d --name hello-world-container -p 8081:5000 hello-world-app
```

### Open browser manually:
Navigate to http://localhost:8081

### Stop the container:
```bash
docker stop hello-world-container
docker rm hello-world-container
```

## Alternative: Using Docker Compose

### Start the application:
```bash
docker-compose -f docker-compose.hello.yml up -d
```

### Stop the application:
```bash
docker-compose -f docker-compose.hello.yml down
```

## How It Works

1. **hello.py** - Simple Flask web server that returns an HTML page with "Hello World"
2. **Dockerfile.hello** - Creates an Ubuntu-based container with Python 3 and Flask
3. **Launcher scripts** - Automate the build, run, and browser opening process
4. **Port mapping** - Container internal port 5000 is mapped to host port 8081

## Troubleshooting

### Docker not running
- **Error:** "Docker is not running"
- **Solution:** Start Docker Desktop and wait for it to fully initialize

### Port already in use
- **Error:** "Port 8081 is already allocated"
- **Solution:** Stop any existing containers using port 8081:
  ```bash
  docker stop hello-world-container
  ```
- **Alternative:** Edit the launcher scripts or docker-compose.yml to use a different port (e.g., 8082)

### Browser doesn't open automatically
- Manually navigate to http://localhost:8081

### Container won't start
- Check Docker logs:
  ```bash
  docker logs hello-world-container
  ```

## Testing Cross-Platform Compatibility

### Transfer from Mac to PC:

1. On Mac, create a zip of all files:
   ```bash
   zip hello-docker.zip hello.py Dockerfile.hello run-hello.bat docker-compose.hello.yml DOCKER-HELLO-README.md
   ```

2. Transfer `hello-docker.zip` to the PC

3. On PC, extract the zip and run `run-hello.bat`

## Next Steps

This "Hello World" application demonstrates:
- ✓ Cross-platform Docker deployment (Mac development → PC runtime)
- ✓ Ubuntu-based containers
- ✓ Python application containerization
- ✓ Web browser integration
- ✓ Port mapping (host 8081 → container 5000)
- ✓ Automatic container cleanup and restart

You can now apply these concepts to containerize the `pva.py` analysis tool!
