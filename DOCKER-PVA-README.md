# PacVolt Analysis (pva.py) Docker Application

Dockerized version of the PacVolt Analysis tool for cross-platform deployment from Mac development to PC runtime.

## New Features

This Dockerized version includes all original pva.py features plus:

- **Web Interface**: After processing completes, a web page automatically opens displaying:
  - List of input files processed
  - Fault file used (if applicable)
  - Output file location
  - Processing status
- **--no-browser flag**: Skip the web interface for batch processing

## Prerequisites

**On PC (Windows):**
- Docker Desktop for Windows installed and running
- Git (to clone/transfer the files)
- **Important:** Docker Desktop must have file sharing enabled for your drives
  - Open Docker Desktop → Settings → Resources → File Sharing
  - Ensure the drive containing your data (typically C:) is checked/enabled
  - Click "Apply & Restart" if you make changes

**On Mac (Development):**
- Docker Desktop for Mac installed and running

## Files

- `pva.py` - Python CLI tool for CSV data conversion and analysis
- `Dockerfile.pva` - Ubuntu-based Docker image configuration
- `run-pva.sh` - Mac/Linux launcher script
- `run-pva.bat` - Windows launcher script
- `DOCKER-PVA-README.md` - This file

## Quick Start

### On Mac (Development/Testing)

1. Make the launcher script executable:
   ```bash
   chmod +x run-pva.sh
   ```

2. Run the application with your data:
   ```bash
   ./run-pva.sh -d ~/path/to/data -o output.csv -v
   ```

3. The browser will automatically open to http://localhost:8081 showing the file summary

### On PC (Windows)

1. Double-click `run-pva.bat` with arguments, or run from Command Prompt:
   ```cmd
   run-pva.bat -d C:\path\to\data -o output.csv -v
   ```

2. The browser will automatically open to http://localhost:8081 showing the file summary

## Usage Examples

### Directory Mode (Recommended)

Process all .log files in a directory with FaultLog integration:

```bash
# Mac/Linux
./run-pva.sh -d ~/dev/data/testing_12.20.25 -o output.csv -v

# Windows
run-pva.bat -d C:\data\testing_12.20.25 -o output.csv -v
```

### With Time Margin

Add 5-minute margin around fault time ranges:

```bash
./run-pva.sh -d ~/dev/data/testing_12.20.25 -o output.csv -m 5m -v
```

### With Data Exclusion

Only include data within fault cluster ranges:

```bash
./run-pva.sh -d ~/dev/data/testing_12.20.25 -o output.csv -e ALL -m 5m -v
```

### With Overlap Policy

Merge all overlapping data files:

```bash
./run-pva.sh -d ~/dev/data/testing_12.20.25 -o output.csv -p ALL -v
```

### Skip Browser (Batch Mode)

Process without opening the web interface:

```bash
./run-pva.sh -d ~/dev/data/testing_12.20.25 -o output.csv --no-browser -v
```

### Single File Mode

Convert a single CSV file:

```bash
./run-pva.sh -i input.csv -o output.csv -v
```

### With Fault File

Include fault data in single file mode:

```bash
./run-pva.sh -i input.csv -o output.csv -f FaultLog.csv -v
```

## Command Line Options

All pva.py options are supported:

- `-d, --dir DIR` - Directory containing .log files (directory mode)
- `-i, --input FILE` - Input CSV file (file mode)
- `-o, --output FILE` - Output CSV file (required)
- `-f, --fault-file FILE` - Fault log file to integrate
- `-m, --margin TIME` - Time margin (e.g., "5m", "30s")
- `-p, --overlap POLICY` - Overlap policy: ONLY_RECENT (default) or ALL
- `-e, --exclude POLICY` - Exclusion policy: NONE (default) or ALL
- `-v, --verbose` - Enable verbose output
- `--no-browser` - Skip opening browser with file summary
- `--min-time TIME` - Minimum timestamp filter
- `--max-time TIME` - Maximum timestamp filter

## How It Works

1. **Launcher Script** - Builds Docker image and runs container with:
   - Home directory mounted as `/home/user` (for accessing input files)
   - Current directory mounted as `/workspace` (for output files)
   - Port 8081 (host) mapped to port 5000 (container) for web interface
   - All command-line arguments passed through to pva.py

2. **pva.py Processing** - Runs inside container:
   - Converts .log files to .csv
   - Processes data according to specified options
   - Generates output file
   - Starts Flask web server (unless --no-browser specified)

3. **Web Interface** - Displays summary in browser:
   - Input files used
   - Fault file (if applicable)
   - Output file location
   - Processing status

## File Path Handling

### Mac/Linux (run-pva.sh)

- **Absolute paths starting with $HOME**: Automatically converted to container paths
  - `~/dev/data/file.csv` → `/home/user/dev/data/file.csv`
- **Relative paths**: Work from current directory
  - `data/file.csv` → `/workspace/data/file.csv`

### Windows (run-pva.bat)

- **Absolute paths**: Use Windows format with drive letter
  - Example: `C:\Users\YourName\data\file.csv`
  - The script automatically converts these to Docker format
  - Paths starting with `%USERPROFILE%` are mounted as `/home/user` in the container
- **Relative paths**: Work from current directory
  - Example: `data\file.csv` → works if data folder is in current directory
- **Important Notes:**
  - Always use backslashes `\` for Windows paths (not forward slashes `/`)
  - Paths must be on a drive that Docker Desktop has file sharing enabled for
  - UNC paths (`\\server\share`) are not supported - copy data locally first
  - Spaces in paths are OK: `C:\Program Files\data\file.csv`

## Troubleshooting

### Docker not running
- **Error:** "Docker is not running"
- **Solution:** Start Docker Desktop and wait for it to fully initialize

### Port already in use
- **Error:** "Port 8081 is already allocated"
- **Solution:** Stop any existing containers using port 8081:
  ```bash
  docker stop pva-container
  ```
- **Alternative:** Edit the launcher scripts to use a different port (e.g., 8082)

### Browser doesn't open automatically
- Manually navigate to http://localhost:8081
- Or use `--no-browser` flag if you don't need the web interface

### Container won't start
- Check Docker logs:
  ```bash
  docker logs pva-container
  ```

### File not found errors
- Ensure paths are correct (use absolute paths or paths relative to current directory)
- Verify files exist before running
- For Mac: Use `~/` or full paths starting with `/Users/`
- For Windows: Use full paths like `C:\Users\...`

### Permission denied errors
- On Mac/Linux: Ensure run-pva.sh is executable (`chmod +x run-pva.sh`)
- Verify Docker has file sharing enabled for the directories you're accessing

### Directory not found (Windows)
- **Error:** "Directory not found" even though the directory exists
- **Causes:**
  1. Docker Desktop file sharing not enabled for the drive
  2. Path uses UNC paths (\\server\share) - Docker doesn't support these
  3. Directory is on a network drive - may need additional configuration
- **Solutions:**
  1. Enable file sharing in Docker Desktop:
     - Open Docker Desktop → Settings → Resources → File Sharing
     - Add the drive containing your data (e.g., C:)
     - Click "Apply & Restart"
  2. Move data to a local drive (C:, D:, etc.) if it's on a network share
  3. Try using full paths: `run-pva.bat -d C:\Users\YourName\data -o output.csv`
  4. Ensure you're using Windows paths (backslashes) in the command, not Unix paths

## Data File Requirements

Directory mode expects these files:
- `24HR.log` - 24-hour recent data
- `24prev.log` - Previous 24-hour data
- `FaultLog.log` - Fault log data (required)
- `Month.log` - Monthly data

Files are automatically converted to .csv format during processing.

## Output

### Console Output (with -v flag)
- File conversion progress
- Time range information
- Overlap detection results
- Fault cluster identification
- Processing statistics

### Generated Files
- Main output CSV (specified by -o option)
- Intermediate debug files (24HR-out.csv, 24prev-out.csv)
- Converted CSV files (from .log files)

### Web Interface (unless --no-browser)
- Opens automatically after processing
- Displays file summary at http://localhost:8081
- Server runs until Ctrl+C

## Testing Cross-Platform Compatibility

### Transfer from Mac to PC:

1. On Mac, create a zip of all files:
   ```bash
   zip pva-docker.zip pva.py Dockerfile.pva run-pva.bat run-pva.sh DOCKER-PVA-README.md
   ```

2. Transfer `pva-docker.zip` to the PC

3. On PC, extract the zip

4. Place your data files in an accessible directory

5. Run `run-pva.bat` with appropriate arguments

## Advanced Usage

### Running Without Launcher Scripts

If you need more control, run Docker directly:

```bash
# Build the image
docker build -f Dockerfile.pva -t pva-app .

# Run with volume mounts
docker run --rm \
  -v "$HOME:/home/user" \
  -v "$(pwd):/workspace" \
  -w /workspace \
  -p 8081:5000 \
  pva-app -d /home/user/dev/data -o output.csv -v
```

### Debugging

Run with shell access:

```bash
docker run --rm -it \
  -v "$HOME:/home/user" \
  -v "$(pwd):/workspace" \
  -w /workspace \
  pva-app /bin/bash
```

## Next Steps

This Docker application demonstrates:
- ✓ Cross-platform Python application deployment (Mac development → PC runtime)
- ✓ Ubuntu-based containers
- ✓ File processing with volume mounts
- ✓ Web browser integration
- ✓ Port mapping (host 8081 → container 5000)
- ✓ Automatic path conversion
- ✓ Complete argument pass-through
- ✓ Flask web server integration

The application is ready for deployment to Windows PC for production use!
