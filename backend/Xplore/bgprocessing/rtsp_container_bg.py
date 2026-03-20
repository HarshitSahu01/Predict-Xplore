import sys
import os
import json
import time
import subprocess
import threading
import cv2
import re
import django
from datetime import datetime
from pathlib import Path

# Setup Django Environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Xplore.settings')
django.setup()

from django.conf import settings
from predictor.models import Task, Container, ContainerAnomaly

# How many frames to keep in buffer before and after anomaly
PRE_ANOMALY_FRAMES = 60
POST_ANOMALY_FRAMES = 60

def process_rtsp_container(task_id, payload):
    log_dir = os.path.join(settings.MEDIA_ROOT, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{task_id}.log")
    
    def log(message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = f"[{timestamp}] {message}\n"
        print(record, end='')
        with open(log_path, "a") as f:
            f.write(record)

    try:
        task = Task.objects.get(task_id=task_id)
        task.status = 'Running'
        task.subprocess_id = os.getpid()
        task.log_file = log_path
        task.save()
        
        container = task.container
        if not container:
            raise Exception("No container linked to this task")
        
        image_name = f"user_{container.name}:latest"
        rtsp_url = task.rtsp_url
        if not rtsp_url:
            raise Exception("No RTSP URL provided")
        
        log(f"Starting RTSP Container Task for {image_name} on {rtsp_url}")

        # Start background thread to capture RTSP stream for saving clips
        frame_buffer = []
        buffer_lock = threading.Lock()
        is_running = True
        
        anomaly_event = threading.Event()
        anomaly_data = {}
        
        def capture_stream():
            cap = cv2.VideoCapture(rtsp_url)
            fps = task.fps or cap.get(cv2.CAP_PROP_FPS) or 15
            
            nonlocal is_running
            frame_interval = 1.0 / fps
            
            anomaly_writer = None
            anomaly_frames_left = 0
            
            # Anomaly clipping paths
            anomaly_dir = os.path.join(settings.MEDIA_ROOT, 'container_anomalies')
            os.makedirs(anomaly_dir, exist_ok=True)
            
            while is_running:
                loop_start = time.time()
                ret, frame = cap.read()
                
                if not ret:
                    time.sleep(0.5)
                    # Try to reconnect
                    cap.release()
                    cap = cv2.VideoCapture(rtsp_url)
                    continue
                
                with buffer_lock:
                    frame_buffer.append(frame.copy())
                    if len(frame_buffer) > PRE_ANOMALY_FRAMES:
                        frame_buffer.pop(0)
                        
                # Check if we need to start or continue writing an anomaly clip
                if anomaly_event.is_set():
                    anomaly_event.clear()
                    # Start new anomaly recording
                    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
                    clip_filename = f"anomaly_{task_id}_{timestamp_str}.mp4"
                    clip_path = os.path.join(anomaly_dir, clip_filename)
                    
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    height, width = frame.shape[:2]
                    anomaly_writer = cv2.VideoWriter(clip_path, fourcc, fps, (width, height))
                    
                    # Write pre-anomaly buffer
                    with buffer_lock:
                        for b_frame in frame_buffer:
                            anomaly_writer.write(b_frame)
                            
                    anomaly_frames_left = POST_ANOMALY_FRAMES
                    log(f"Started recording anomaly clip: {clip_filename}")
                    
                    # Save DB object
                    from django.core.files.base import ContentFile
                    # Store rel path
                    rel_path = f"container_anomalies/{clip_filename}"
                    ContainerAnomaly.objects.create(
                        task=task,
                        video_clip=rel_path,
                        confidence=anomaly_data.get('confidence', 0.0),
                        label=anomaly_data.get('label', 'Suspicious')
                    )
                
                if anomaly_writer:
                    anomaly_writer.write(frame)
                    anomaly_frames_left -= 1
                    if anomaly_frames_left <= 0:
                        anomaly_writer.release()
                        anomaly_writer = None
                        log("Finished recording anomaly clip")
                
                # Sleep to maintain fps
                elapsed = time.time() - loop_start
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
                    
            if anomaly_writer:
                anomaly_writer.release()
            cap.release()

        # Start capture thread
        capture_thread = threading.Thread(target=capture_stream, daemon=True)
        capture_thread.start()

        # Start Docker container
        # We pass RTSP_URL as env so the container can also process it
        log("Starting Docker container...")
        cmd = [
            "docker", "run", "--rm", 
            "-e", f"RTSP_URL={rtsp_url}",
            image_name,
            "python", "inference.py"
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Parse stdout looking for anomalies
        # E.g. "[0-15] Suspicious (Confidence: 0.85)"
        anomaly_pattern = re.compile(r'(?i)(suspicious|anomaly|abnormal)[^\d]*([\d\.]+)')
        
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                log(f"CONTAINER: {line.strip()}")
                
                # Check for anomaly trigger
                match = anomaly_pattern.search(line)
                if match:
                    label = match.group(1).capitalize()
                    conf = float(match.group(2))
                    
                    if conf >= 0.5: # Hardcoded min threshold just in case
                        if not anomaly_writer_active(anomaly_event):
                            log(f"Anomaly detected from container output! {label} - {conf}")
                            anomaly_data['confidence'] = conf
                            anomaly_data['label'] = label
                            anomaly_event.set()

        process.wait()
        
        if process.returncode != 0:
            log(f"Container exited with non-zero code: {process.returncode}")
            raise Exception("Docker container crashed")

        # Cleanup
        is_running = False
        capture_thread.join(timeout=5)
        
        # Complete Task
        log("RTSP Container Processing Complete.")
        task = Task.objects.get(task_id=task_id)
        task.status = 'Completed'
        task.end_time = datetime.now()
        task.save()
        
    except Exception as e:
        error_msg = f"Error in RTSP processing: {e}"
        print(error_msg)
        try:
            log(error_msg)
            task = Task.objects.get(task_id=task_id)
            task.status = 'Failed'
            task.end_time = datetime.now()
            task.save()
        except:
            pass

def anomaly_writer_active(event):
    return event.is_set()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        task_id = sys.argv[1]
        payload_str = sys.argv[2]
        payload = json.loads(payload_str)
        process_rtsp_container(task_id, payload)
    else:
        print("Required arguments not provided.")
