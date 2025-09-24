#!/usr/bin/env python3
import cv2
from http.server import BaseHTTPRequestHandler, HTTPServer
import time
import subprocess
import re
import urllib.parse
import threading
import queue

# Configuration Variables - Edit these as needed
SERVER_HOST = '0.0.0.0'  # Use '0.0.0.0' to accept connections from any IP, or set to specific IP
SERVER_PORT = 8086       # Port number for the web server
APP_TITLE = 'Webcam Streamer'  # Application title shown in browser
JPEG_QUALITY = 85        # JPEG compression quality (1-100, higher = better quality)
DEFAULT_FPS = 30         # Target frames per second
BUFFER_SIZE = 2          # Frame buffer size (increase if you have frame drops)

class ThreadedWebcamStreamer:
    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.cap = None
        self.width = 640
        self.height = 480
        self.fps = DEFAULT_FPS
        self.max_fps = DEFAULT_FPS
        self.available_resolutions = []
        
        self.frame_queue = queue.Queue(maxsize=BUFFER_SIZE)
        self.current_frame = None
        self.capture_thread = None
        self.running = False
        
        self.open_camera()
        self.start_capture_thread()

    def detect_camera_capabilities(self):
        if not self.cap or not self.cap.isOpened():
            return
        
        fps_to_test = [60, 45, 36, 30, 25, 20, 15]
        max_fps = 15
        
        for test_fps in fps_to_test:
            self.cap.set(cv2.CAP_PROP_FPS, test_fps)
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            if actual_fps > max_fps:
                max_fps = actual_fps
        
        self.max_fps = int(max_fps)
        self.fps = self.max_fps

    def open_camera(self):
        if self.cap:
            self.cap.release()
            time.sleep(0.5)
            
        self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_V4L2)
        
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            
            self.detect_camera_capabilities()
            self.available_resolutions = get_camera_specs(self.camera_id)
            
            if self.available_resolutions:
                max_w, max_h = self.available_resolutions[0]
                self.set_resolution(max_w, max_h)
            
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            print(f"Camera {self.camera_id}: {self.width}x{self.height} @ {self.fps}fps")
        else:
            raise Exception(f"Could not open camera {self.camera_id}")

    def start_capture_thread(self):
        if self.capture_thread and self.capture_thread.is_alive():
            self.stop_capture_thread()
            
        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_frames, daemon=True)
        self.capture_thread.start()

    def stop_capture_thread(self):
        self.running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=2)

    def _capture_frames(self):
        while self.running:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                
                if ret:
                    try:
                        if self.frame_queue.full():
                            try:
                                self.frame_queue.get_nowait()
                            except queue.Empty:
                                pass
                        
                        self.frame_queue.put(frame, block=False)
                    except queue.Full:
                        pass
                
                time.sleep(1.0 / self.fps)
            else:
                time.sleep(0.1)

    def set_resolution(self, width, height):
        if self.cap:
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            ret, _ = self.cap.read()
            
            self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def switch_camera(self, camera_id):
        print(f"Switching from camera {self.camera_id} to {camera_id}")
        self.stop_capture_thread()
        self.camera_id = camera_id
        
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break
        
        self.current_frame = None
        self.open_camera()
        self.start_capture_thread()
        print(f"Camera switch to {camera_id} complete")
        return True

    def get_frame(self):
        try:
            frame = self.frame_queue.get_nowait()
            self.current_frame = frame
        except queue.Empty:
            frame = self.current_frame
            
        if frame is not None:
            _, buffer = cv2.imencode('.jpg', frame, [
                cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY,
                cv2.IMWRITE_JPEG_OPTIMIZE, 1
            ])
            return buffer.tobytes()
        return None

def get_available_cameras():
    cameras = {}
    
    try:
        result = subprocess.run(['v4l2-ctl', '--list-devices'], 
                              capture_output=True, text=True)
        
        current_device = None
        for line in result.stdout.split('\n'):
            if line and not line.startswith('\t'):
                current_device = line.strip()
            elif line.startswith('\t/dev/video'):
                device_path = line.strip()
                device_num = int(re.search(r'/dev/video(\d+)', device_path).group(1))
                if device_num % 2 == 0:
                    cameras[device_num] = {
                        'name': current_device,
                        'path': device_path
                    }
    except:
        pass
    
    return cameras

def get_camera_specs(device_num):
    try:
        result = subprocess.run(['v4l2-ctl', f'--device=/dev/video{device_num}', '--list-formats-ext'], 
                              capture_output=True, text=True)
        
        resolutions = []
        current_format = None
        
        for line in result.stdout.split('\n'):
            if 'MJPG' in line or 'YUYV' in line:
                current_format = 'MJPG' if 'MJPG' in line else 'YUYV'
            elif 'Size: Discrete' in line and current_format:
                size_match = re.search(r'(\d+)x(\d+)', line)
                if size_match:
                    width, height = int(size_match.group(1)), int(size_match.group(2))
                    if (width, height) not in resolutions:
                        resolutions.append((width, height))
        
        resolutions.sort(key=lambda x: x[0] * x[1], reverse=True)
        return resolutions
    except:
        return [(1280, 720), (640, 480)]

def find_best_camera():
    cameras = get_available_cameras()
    if not cameras:
        return 0
    
    best_camera = None
    best_resolution = 0
    
    for cam_id in cameras:
        resolutions = get_camera_specs(cam_id)
        if resolutions:
            max_res = resolutions[0][0] * resolutions[0][1]
            if max_res > best_resolution:
                best_resolution = max_res
                best_camera = cam_id
    
    return best_camera if best_camera is not None else list(cameras.keys())[0]

# Global variables
cameras = get_available_cameras()
current_camera = find_best_camera()
streamer = ThreadedWebcamStreamer(current_camera)

class StreamHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
        
    def do_GET(self):
        global current_camera, streamer, cameras
        
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            camera_options = ""
            for cam_id, cam_info in cameras.items():
                # Fix dropdown selection - use current_camera instead of streamer.camera_id
                selected = "selected" if cam_id == current_camera else ""
                camera_options += f'<option value="{cam_id}" {selected}>{cam_info["name"]}</option>'
            
            html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{APP_TITLE}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: white;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        
        .container {{
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.2);
            text-align: center;
            max-width: 95vw;
            max-height: 95vh;
            overflow-y: auto;
        }}
        
        h1 {{
            font-size: 3rem;
            font-weight: 700;
            margin-bottom: 30px;
            background: linear-gradient(45deg, #fff, #f0f0f0);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .controls-panel {{
            display: flex;
            justify-content: center;
            margin-bottom: 30px;
            padding: 20px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
        }}
        
        .control-group {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            align-items: center;
        }}
        
        label {{
            font-weight: 600;
            font-size: 0.9rem;
            opacity: 0.9;
        }}
        
        select {{
            background: rgba(255, 255, 255, 0.2);
            border: 2px solid rgba(255, 255, 255, 0.3);
            color: white;
            padding: 10px 15px;
            border-radius: 20px;
            font-size: 0.9rem;
            min-width: 200px;
        }}
        
        .stats {{
            font-size: 1.1rem;
            margin-bottom: 30px;
            opacity: 0.9;
            font-weight: 500;
            padding: 15px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
        }}
        
        .video-wrapper {{
            position: relative;
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.4);
            background: #000;
            margin-bottom: 25px;
            max-width: 100%;
            max-height: 60vh;
        }}
        
	.live-indicator {{
            position: absolute;
            top: 20px;
            left: 20px;
            background: #ff4757;
            color: white;
            padding: 15px 20px 12px 40px;
            border-radius: 25px;
            font-weight: bold;
            font-size: 0.9rem;
            z-index: 10;
            animation: pulse 2s infinite;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            align-items: flex-end;
            padding-bottom: 13px;
        }}
        
        .live-indicator::before {{
            content: '';
            position: absolute;
            left: 20px;
            top: 50%;
            transform: translateY(-50%);
            width: 8px;
            height: 8px;
            background: white;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
        }}
        
        #stream {{
            width: 100%;
            height: auto;
            display: block;
            max-width: 100%;
            max-height: 60vh;
            object-fit: contain;
        }}
        
        .action-controls {{
            display: flex;
            gap: 15px;
            justify-content: center;
            flex-wrap: wrap;
            margin-bottom: 25px;
        }}
        
        .btn {{
            background: rgba(255, 255, 255, 0.2);
            border: 2px solid rgba(255, 255, 255, 0.3);
            color: white;
            padding: 12px 24px;
            border-radius: 30px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            text-decoration: none;
            font-size: 0.95rem;
        }}
        
        .btn:hover {{
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
            transform: translateY(-3px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
        }}
        
        .notice {{
            background: rgba(255, 165, 0, 0.2);
            border: 2px solid rgba(255, 165, 0, 0.5);
            color: #ffcc80;
            padding: 15px;
            border-radius: 15px;
            font-size: 0.95rem;
            font-weight: 500;
        }}
        
        @media (max-width: 768px) {{
            .container {{ padding: 20px; margin: 10px; }}
            h1 {{ font-size: 2rem; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{APP_TITLE}</h1>
        
        <div class="controls-panel">
            <div class="control-group">
                <label for="cameraSelect">Camera:</label>
                <select id="cameraSelect" onchange="switchCamera()">
                    {camera_options}
                </select>
            </div>
        </div>
        
        <div class="stats">
            <strong>Current:</strong> {streamer.width} × {streamer.height} • {streamer.fps} FPS • Quality {JPEG_QUALITY}% • Camera {current_camera}
        </div>
        
        <div class="video-wrapper">
            <div class="live-indicator">LIVE</div>
            <img id="stream" src="/stream.mjpg" alt="Live webcam stream" />
        </div>
        
        <div class="action-controls">
            <button class="btn" onclick="toggleFullscreen()">Fullscreen</button>
            <button class="btn" onclick="saveSnapshot()">Snapshot</button>
            <button class="btn" onclick="location.reload()">Refresh</button>
        </div>
        
        <div class="notice">
            <strong>Notice:</strong> After changing cameras, click the "Refresh" button above to see the new camera feed.
        </div>
    </div>

    <script>
        function switchCamera() {{
            const select = document.getElementById('cameraSelect');
            const newCameraId = select.value;
            
            fetch('/api/camera?id=' + newCameraId)
                .then(response => {{
                    if (response.ok) {{
                        console.log('Camera switched to ' + newCameraId);
                    }}
                }});
        }}
        
        function toggleFullscreen() {{
            const img = document.getElementById('stream');
            if (!document.fullscreenElement) {{
                img.requestFullscreen();
            }} else {{
                document.exitFullscreen();
            }}
        }}
        
        function saveSnapshot() {{
            const img = document.getElementById('stream');
            const canvas = document.createElement('canvas');
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0);
            
            const link = document.createElement('a');
            const cam = document.getElementById('cameraSelect').selectedOptions[0].text.replace(/[^a-zA-Z0-9]/g, '_');
            link.download = cam + '_' + new Date().toISOString().slice(0,19).replace(/:/g, '-') + '.jpg';
            link.href = canvas.toDataURL('image/jpeg', 1.0);
            link.click();
        }}
        
        document.getElementById('stream').onerror = function() {{
            setTimeout(() => {{
                this.src = '/stream.mjpg?' + Date.now();
            }}, 2000);
        }};
        
        function handleResize() {{
            const container = document.querySelector('.container');
            const video = document.getElementById('stream');
            if (window.innerWidth < 768) {{
                container.style.maxHeight = '95vh';
                video.style.maxHeight = '40vh';
            }} else {{
                container.style.maxHeight = '95vh';
                video.style.maxHeight = '60vh';
            }}
        }}
        
        window.addEventListener('resize', handleResize);
        handleResize();
    </script>
</body>
</html>'''
            
            self.wfile.write(html.encode('utf-8'))
            
        elif self.path.startswith('/api/camera') and 'id=' in self.path:
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            new_camera_id = int(params['id'][0])
            
            if new_camera_id in cameras:
                current_camera = new_camera_id
                streamer.switch_camera(current_camera)
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
            
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'close')
            self.end_headers()
            
            try:
                while True:
                    frame_data = streamer.get_frame()
                    if frame_data:
                        self.wfile.write(b'--frame\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', str(len(frame_data)))
                        self.end_headers()
                        self.wfile.write(frame_data)
                        self.wfile.write(b'\r\n')
                        self.wfile.flush()
                    time.sleep(0.033)
            except (ConnectionResetError, BrokenPipeError):
                pass
            except Exception as e:
                print(f"Streaming error: {e}")
        else:
            self.send_error(404)

if __name__ == '__main__':
    print('Available cameras:')
    for cam_id, cam_info in cameras.items():
        print(f"  {cam_id}: {cam_info['name']}")
    
    print(f'\nStarting with camera: {current_camera}')
    print(f'Server: http://{SERVER_HOST}:{SERVER_PORT}/')
    print(f'Access from browser at: http://localhost:{SERVER_PORT}/')
    
    try:
        server = HTTPServer((SERVER_HOST, SERVER_PORT), StreamHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')
        streamer.stop_capture_thread()
        if streamer.cap:
            streamer.cap.release()