# Webcam Streamer

Python-based MJPEG webcam streaming server with web interface.

I built this to check on my cat when I'm out and about.

## Features

- Multi-camera support with hot-switching
- Automatic camera capability detection
- Responsive web UI with live preview
- Snapshot functionality
- Configurable quality and framerate

## Dependencies

- Python 3
- OpenCV Python bindings
- v4l-utils

### Arch Linux Installation

```bash
pacman -S python python-opencv v4l-utils
```

Package references:
- [python](https://archlinux.org/packages/extra/x86_64/python/)
- [python-opencv](https://archlinux.org/packages/extra/x86_64/python-opencv/)
- [v4l-utils](https://archlinux.org/packages/extra/x86_64/v4l-utils/)

## Usage

```bash
chmod +x webcam_streamer.py
./webcam_streamer.py
```

Access the stream at `http://localhost:8086`

## Configuration

Edit variables at the top of the script:

- `SERVER_PORT`: HTTP server port (default: 8086)
- `JPEG_QUALITY`: Compression quality 1-100 (default: 85)
- `DEFAULT_FPS`: Target framerate (default: 30)

## Requirements

- Linux with V4L2 support
- USB/integrated webcam
