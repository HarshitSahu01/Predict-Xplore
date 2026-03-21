"""
RTSP Live Processing for STEAD Anomaly Detection.

This module handles:
- Continuous RTSP stream capture
- STEAD model inference on video chunks
- Annotated output video generation (MP4)
- FFmpeg streaming of output video

Workflow:
1. Input RTSP URL → STEAD instance running → Predict video output
2. Output video saved as MP4
3. FFmpeg streaming of the output
"""

import cv2
import threading
import time
import os
import logging
import uuid
import queue
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any
import subprocess
import signal

logger = logging.getLogger(__name__)


class RTSPLiveProcessor:
    """
    Real-time RTSP stream processor with STEAD anomaly detection.
    
    Captures frames from RTSP stream, runs STEAD inference,
    and produces annotated output video.
    """
    
    FRAME_BUFFER_SIZE = 16  # STEAD requires 16 frames
    
    def __init__(
        self,
        stream_url: str,
        output_dir: str,
        fps: int = 15,
        threshold: float = 0.7,
        job_id: str = None,
        on_anomaly_callback: Callable = None
    ):
        """
        Args:
            stream_url: RTSP URL, TCP URL, or video file path
            output_dir: Directory to save output videos
            fps: Target frames per second
            threshold: Anomaly detection threshold
            job_id: Unique identifier for this job
            on_anomaly_callback: Function called when anomaly is detected
        """
        self.stream_url = stream_url
        self.output_dir = Path(output_dir)
        self.fps = fps
        self.threshold = threshold
        self.job_id = job_id or str(uuid.uuid4())
        self.on_anomaly_callback = on_anomaly_callback
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Buffers
        self.frame_buffer = deque(maxlen=self.FRAME_BUFFER_SIZE)
        self.original_frame_buffer = deque(maxlen=self.FRAME_BUFFER_SIZE)
        
        # State
        self.is_running = False
        self.is_paused = False
        self.cap = None
        self.video_writer = None
        self.capture_thread = None
        self.inference_thread = None
        
        # Statistics
        self.stats = {
            'start_time': None,
            'end_time': None,
            'total_frames': 0,
            'total_clips_processed': 0,
            'anomalies_detected': 0,
            'anomaly_clips': [],
            'current_fps': 0,
            'status': 'idle'
        }
        
        # Inference queue
        self.inference_queue = queue.Queue(maxsize=10)
        
        # Output paths
        self.output_video_path = None
        self.web_ready_path = None
        self.hls_playlist_path = None
        self.thumbnail_path = None
        
        # Model reference (lazy loaded)
        self._model = None
        
        # Video properties
        self.frame_width = None
        self.frame_height = None
        self.source_fps = None
        
        # Anomaly clip recording state
        self.anomaly_writer = None
        self.anomaly_clip_path = None
        self.anomaly_clip_start_frame = 0
        self.is_recording_anomaly = False
        self.anomaly_post_buffer_frames = 45  # Keep recording for ~3 secs after anomaly ends
        self.anomaly_frames_since_last = 0
        self.anomaly_clip_index = 0
        self.anomaly_max_score = 0.0
        
        # Error tracking
        self.error_message = None
        
        # Thread safety lock
        self.lock = threading.Lock()
    
    def _get_model(self):
        """Lazy load the STEAD model."""
        if self._model is None:
            from .stead_model import get_stead_model
            self._model = get_stead_model()
        return self._model
    
    def _init_video_capture(self) -> bool:
        """Initialize video capture from stream."""
        try:
            # Handle different input types
            if isinstance(self.stream_url, int):
                self.cap = cv2.VideoCapture(self.stream_url)
            elif self.stream_url.isdigit():
                self.cap = cv2.VideoCapture(int(self.stream_url))
            else:
                self.cap = cv2.VideoCapture(self.stream_url)
            
            if not self.cap.isOpened():
                self.error_message = f"Cannot open stream: {self.stream_url}"
                logger.error(self.error_message)
                return False
            
            # Get video properties
            self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.source_fps = self.cap.get(cv2.CAP_PROP_FPS)
            
            if self.source_fps <= 0:
                self.source_fps = self.fps
            
            logger.info(f"Stream opened: {self.frame_width}x{self.frame_height} @ {self.source_fps} fps")
            return True
            
        except Exception as e:
            self.error_message = str(e)
            logger.error(f"Failed to initialize capture: {e}")
            return False
    
    def _init_video_writer(self) -> bool:
        """Initialize video writer for output."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"stead_output_{self.job_id}_{timestamp}.mp4"
            self.output_video_path = str(self.output_dir / filename)
            
            # Use H264 codec for better compatibility
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            
            self.video_writer = cv2.VideoWriter(
                self.output_video_path,
                fourcc,
                self.source_fps or self.fps,
                (self.frame_width, self.frame_height)
            )
            
            if not self.video_writer.isOpened():
                self.error_message = "Failed to create video writer"
                logger.error(self.error_message)
                return False
            
            logger.info(f"Output video: {self.output_video_path}")
            return True
            
        except Exception as e:
            self.error_message = str(e)
            logger.error(f"Failed to initialize video writer: {e}")
            return False
    
    def start(self) -> bool:
        """
        Start processing the RTSP stream.
        
        Returns:
            bool indicating success
        """
        if self.is_running:
            logger.warning("Processor is already running")
            return True
        
        # Initialize capture
        if not self._init_video_capture():
            self.stats['status'] = 'error'
            return False
        
        # Initialize writer
        if not self._init_video_writer():
            self.cap.release()
            self.stats['status'] = 'error'
            return False
        
        # Start processing
        self.is_running = True
        self.is_paused = False
        self.stats['start_time'] = datetime.now().isoformat()
        self.stats['status'] = 'running'
        
        # Start capture thread
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        
        # Start inference thread
        self.inference_thread = threading.Thread(target=self._inference_loop, daemon=True)
        self.inference_thread.start()
        
        logger.info(f"Started RTSP live processor: {self.job_id}")
        return True
    
    def _capture_loop(self):
        """Main capture loop - runs in separate thread."""
        frame_interval = 1.0 / self.fps
        start_time = time.time()
        fps_counter = 0
        fps_start_time = time.time()
        
        try:
            while self.is_running:
                loop_start = time.time()
                
                if self.is_paused:
                    time.sleep(0.1)
                    continue
                
                ret, frame = self.cap.read()
                
                if not ret:
                    logger.warning("Failed to read frame")
                    # Try to reconnect
                    time.sleep(0.5)
                    self.cap.release()
                    if not self._init_video_capture():
                        self.stop()
                        break
                    continue
                
                with self.lock:
                    # Store original frame
                    self.original_frame_buffer.append(frame.copy())
                    
                    # Store frame for inference
                    self.frame_buffer.append(frame.copy())
                    
                    self.stats['total_frames'] += 1
                    fps_counter += 1
                
                # When buffer is full, queue for inference
                if len(self.frame_buffer) >= self.FRAME_BUFFER_SIZE:
                    try:
                        frames_for_inference = list(self.frame_buffer)
                        original_frames = list(self.original_frame_buffer)
                        self.inference_queue.put_nowait((frames_for_inference, original_frames))
                        self.frame_buffer.clear()
                        self.original_frame_buffer.clear()
                    except queue.Full:
                        logger.warning("Inference queue full, dropping frame batch")
                
                # Calculate FPS
                fps_elapsed = time.time() - fps_start_time
                if fps_elapsed >= 1.0:
                    self.stats['current_fps'] = fps_counter / fps_elapsed
                    fps_counter = 0
                    fps_start_time = time.time()
                
                # Maintain target FPS
                elapsed = time.time() - loop_start
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
                    
        except Exception as e:
            logger.error(f"Capture loop error: {e}")
            self.error_message = str(e)
        finally:
            self.stats['status'] = 'stopped'
    
    def _inference_loop(self):
        """Inference loop - runs STEAD model on frame batches."""
        model = self._get_model()
        
        try:
            while self.is_running:
                try:
                    # Get frames from queue
                    frames, original_frames = self.inference_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                try:
                    # Run inference
                    result = model.predict_frames(frames, threshold=self.threshold)
                    
                    with self.lock:
                        self.stats['total_clips_processed'] += 1
                    
                    # Annotate and write frames
                    has_anomaly = result.get('has_anomaly', False)
                    anomaly_score = result.get('anomaly_score', 0)
                    
                    for i, frame in enumerate(original_frames):
                        annotated_frame = self._annotate_frame(
                            frame,
                            has_anomaly,
                            anomaly_score,
                            i,
                            len(original_frames)
                        )
                        self.video_writer.write(annotated_frame)
                        
                        # Handle anomaly clip recording
                        if has_anomaly:
                            self.anomaly_frames_since_last = 0
                            self.anomaly_max_score = max(self.anomaly_max_score, anomaly_score)
                            
                            if not self.is_recording_anomaly:
                                # Start new clip
                                self.is_recording_anomaly = True
                                self.anomaly_clip_index += 1
                                self.anomaly_clip_start_frame = self.stats['total_frames'] - 16 + i
                                
                                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                                filename = f"stead_anomaly_{self.job_id}_{self.anomaly_clip_index}_{timestamp}.mp4"
                                self.anomaly_clip_path = str(self.output_dir / filename)
                                
                                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                                self.anomaly_writer = cv2.VideoWriter(
                                    self.anomaly_clip_path,
                                    fourcc,
                                    self.source_fps or self.fps,
                                    (self.frame_width, self.frame_height)
                                )
                                logger.info(f"Started recording anomaly clip: {self.anomaly_clip_path}")
                                
                            if self.anomaly_writer:
                                self.anomaly_writer.write(annotated_frame)
                                
                        elif self.is_recording_anomaly:
                            self.anomaly_frames_since_last += 1
                            if self.anomaly_writer:
                                self.anomaly_writer.write(annotated_frame)
                                
                            # Stop clip if buffer exhausted
                            if self.anomaly_frames_since_last >= self.anomaly_post_buffer_frames:
                                self._finalize_anomaly_clip()
                    
                    # Track anomalies structurally
                    if has_anomaly and self.anomaly_frames_since_last == 0 and not getattr(self, '_fired_anomaly_callback_for_current', False):
                        # Only increment the master count once per continuous anomaly event if desired,
                        # but keeping as per original logic to increment immediately.
                        # Setting flag to only fire the callback once per anomaly event.
                        self._fired_anomaly_callback_for_current = True
                        with self.lock:
                            self.stats['anomalies_detected'] += 1
                            
                    elif not has_anomaly and self.anomaly_frames_since_last >= self.anomaly_post_buffer_frames:
                        self._fired_anomaly_callback_for_current = False
                            
                except Exception as e:
                    logger.error(f"Inference error: {e}")
                    # Write frames without annotation on error
                    for frame in original_frames:
                        self.video_writer.write(frame)
                        if self.is_recording_anomaly and self.anomaly_writer:
                           self.anomaly_writer.write(frame)
                        
        except Exception as e:
            logger.error(f"Inference loop error: {e}")
            
    def _finalize_anomaly_clip(self):
        """Stop current anomaly writer and enqueue it for web conversion."""
        self.is_recording_anomaly = False
        if self.anomaly_writer:
            self.anomaly_writer.release()
            self.anomaly_writer = None
            
        logger.info(f"Finished recording anomaly clip: {self.anomaly_clip_path}")
        
        # We spawn a thread to convert the MP4 so it doesn't block inference loop
        def convert_and_register_clip(raw_path, job_id, clip_idx, start_frame, score):
            from .video_streaming import get_stream_manager
            
            try:
                stream_manager = get_stream_manager()
                
                web_ready_filename = f"{Path(raw_path).stem}_web.mp4"
                web_ready_path = str(Path(raw_path).parent / web_ready_filename)
                
                success = stream_manager.ffmpeg.convert_to_web_format(
                    input_path=raw_path,
                    output_path=web_ready_path,
                    crf=26  # Slightly lower quality for faster encoding of short clips
                )
                
                if success:
                    # Make path relative to MEDIA_ROOT
                    from django.conf import settings
                    rel_path = os.path.relpath(web_ready_path, settings.MEDIA_ROOT)
                    
                    anomaly_info = {
                        'clip_index': clip_idx,
                        'frame_start': start_frame,
                        'frame_end': self.stats['total_frames'],
                        'anomaly_score': float(score),
                        'timestamp': datetime.now().isoformat(),
                        'video_path': rel_path
                    }
                    
                    with self.lock:
                        self.stats['anomaly_clips'].append(anomaly_info)
                        
                    if self.on_anomaly_callback:
                        self.on_anomaly_callback(anomaly_info)
                        
                    # Clean up the raw opencv mp4 to save space
                    try:
                        os.remove(raw_path)
                    except Exception:
                        pass
                else:
                    logger.error("Failed to convert anomaly clip to web format")
            except Exception as e:
                logger.error(f"Error finalizing anomaly clip: {e}")

        threading.Thread(
            target=convert_and_register_clip,
            args=(self.anomaly_clip_path, self.job_id, self.anomaly_clip_index, self.anomaly_clip_start_frame, self.anomaly_max_score),
            daemon=True
        ).start()
        
        self.anomaly_max_score = 0.0
    
    def _annotate_frame(
        self,
        frame,
        has_anomaly: bool,
        anomaly_score: float,
        frame_idx: int,
        total_frames: int
    ):
        """Add annotation overlay to frame."""
        annotated = frame.copy()
        
        # Colors
        if has_anomaly:
            box_color = (0, 0, 255)  # Red for anomaly
            text_color = (0, 0, 255)
        else:
            box_color = (0, 255, 0)  # Green for normal
            text_color = (0, 255, 0)
        
        # Draw border
        cv2.rectangle(annotated, (0, 0), (self.frame_width - 1, self.frame_height - 1), box_color, 3)
        
        # Status text background
        cv2.rectangle(annotated, (0, 0), (350, 90), (0, 0, 0), -1)
        
        # Status text
        status_text = "ANOMALY DETECTED" if has_anomaly else "NORMAL"
        cv2.putText(annotated, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, text_color, 2)
        
        # Score text
        score_text = f"Score: {anomaly_score:.3f}"
        cv2.putText(annotated, score_text, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cv2.putText(annotated, timestamp, (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Progress indicator (for clip)
        progress_width = int((frame_idx + 1) / total_frames * 100)
        cv2.rectangle(annotated, (10, self.frame_height - 20), (10 + progress_width, self.frame_height - 10), box_color, -1)
        
        return annotated
    
    def pause(self):
        """Pause processing."""
        self.is_paused = True
        self.stats['status'] = 'paused'
        logger.info(f"Paused processor: {self.job_id}")
    
    def resume(self):
        """Resume processing."""
        self.is_paused = False
        self.stats['status'] = 'running'
        logger.info(f"Resumed processor: {self.job_id}")
    
    def stop(self) -> dict:
        """
        Stop processing and finalize output.
        
        Returns:
            dict with processing results and output paths
        """
        logger.info(f"Stopping processor: {self.job_id}")
        
        self.is_running = False
        self.stats['end_time'] = datetime.now().isoformat()
        self.stats['status'] = 'stopped'
        
        # Wait for threads to finish
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=5)
        
        if self.inference_thread and self.inference_thread.is_alive():
            self.inference_thread.join(timeout=5)
            
        if self.is_recording_anomaly:
            self._finalize_anomaly_clip()
        
        # Process remaining frames in buffer
        self._process_remaining_frames()
        
        # Release resources
        if self.cap:
            self.cap.release()
        
        if self.video_writer:
            self.video_writer.release()
        
        # Generate streaming assets
        result = self._generate_streaming_assets()
        
        return result
    
    def _process_remaining_frames(self):
        """Process any remaining frames in the buffer."""
        if len(self.original_frame_buffer) == 0:
            return
        
        # Write remaining frames without inference
        for frame in self.original_frame_buffer:
            if self.video_writer:
                self.video_writer.write(frame)
    
    def _generate_streaming_assets(self) -> dict:
        """Generate web-ready video, HLS stream, and thumbnail using FFmpeg."""
        from .video_streaming import get_stream_manager
        
        result = {
            'job_id': self.job_id,
            'success': False,
            'output_video': self.output_video_path,
            'web_ready': None,
            'hls_playlist': None,
            'thumbnail': None,
            'stats': self.stats,
            'error': self.error_message
        }
        
        if not self.output_video_path or not os.path.exists(self.output_video_path):
            result['error'] = "Output video not found"
            return result
        
        try:
            stream_manager = get_stream_manager()
            
            # Process output video for streaming
            streaming_result = stream_manager.process_output_video(
                video_id=self.job_id,
                input_video_path=self.output_video_path,
                annotated_video_path=self.output_video_path
            )
            
            result['web_ready'] = streaming_result.get('web_ready')
            result['hls_playlist'] = streaming_result.get('hls_playlist')
            result['thumbnail'] = streaming_result.get('thumbnail')
            result['success'] = streaming_result.get('success', False)
            
            self.web_ready_path = result['web_ready']
            self.hls_playlist_path = result['hls_playlist']
            self.thumbnail_path = result['thumbnail']
            
        except Exception as e:
            logger.error(f"Error generating streaming assets: {e}")
            result['error'] = str(e)
        
        return result
    
    def get_status(self) -> dict:
        """Get current processing status."""
        with self.lock:
            return {
                'job_id': self.job_id,
                'stream_url': self.stream_url,
                'is_running': self.is_running,
                'is_paused': self.is_paused,
                'stats': self.stats.copy(),
                'output_video': self.output_video_path,
                'web_ready': self.web_ready_path,
                'hls_playlist': self.hls_playlist_path,
                'thumbnail': self.thumbnail_path,
                'error': self.error_message
            }


class RTSPLiveManager:
    """
    Manages multiple RTSP live processing jobs.
    Singleton pattern for global access.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.processors = {}
            cls._instance.lock = threading.Lock()
        return cls._instance
    
    def create_job(
        self,
        stream_url: str,
        output_dir: str,
        fps: int = 15,
        threshold: float = 0.7,
        on_anomaly_callback: Callable = None
    ) -> RTSPLiveProcessor:
        """
        Create and start a new processing job.
        
        Returns:
            RTSPLiveProcessor instance
        """
        job_id = str(uuid.uuid4())
        
        processor = RTSPLiveProcessor(
            stream_url=stream_url,
            output_dir=output_dir,
            fps=fps,
            threshold=threshold,
            job_id=job_id,
            on_anomaly_callback=on_anomaly_callback
        )
        
        with self.lock:
            self.processors[job_id] = processor
        
        return processor
    
    def get_job(self, job_id: str) -> Optional[RTSPLiveProcessor]:
        """Get a processor by job ID."""
        return self.processors.get(job_id)
    
    def list_jobs(self) -> list:
        """List all active job IDs."""
        return list(self.processors.keys())
    
    def get_all_statuses(self) -> dict:
        """Get status of all jobs."""
        statuses = {}
        for job_id, processor in self.processors.items():
            statuses[job_id] = processor.get_status()
        return statuses
    
    def stop_job(self, job_id: str) -> Optional[dict]:
        """Stop a job and return results."""
        processor = self.processors.get(job_id)
        if processor:
            result = processor.stop()
            # Don't remove from dict - keep for history
            return result
        return None
    
    def remove_job(self, job_id: str):
        """Remove a job from the manager."""
        with self.lock:
            if job_id in self.processors:
                processor = self.processors[job_id]
                if processor.is_running:
                    processor.stop()
                del self.processors[job_id]
    
    def stop_all(self):
        """Stop all running jobs."""
        with self.lock:
            for job_id in list(self.processors.keys()):
                self.processors[job_id].stop()


# Global manager instance
_live_manager = None


def get_live_manager() -> RTSPLiveManager:
    """Get the global RTSPLiveManager instance."""
    global _live_manager
    if _live_manager is None:
        _live_manager = RTSPLiveManager()
    return _live_manager
