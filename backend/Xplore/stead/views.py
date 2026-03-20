"""
STEAD Anomaly Detection API Views.

Provides endpoints for:
- Video upload and anomaly detection
- RTSP stream management
- Model status checking
- Anomaly history retrieval
- FFmpeg-based video streaming
"""

from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from django.conf import settings
from django.http import FileResponse, StreamingHttpResponse, Http404
import logging
import os
import tempfile
import time
import uuid as uuid_lib
from pathlib import Path

from .models import RTSPJob, AnomalyDetection, VideoUpload
from .serializers import (
    RTSPJobSerializer, RTSPJobCreateSerializer,
    AnomalyDetectionSerializer, VideoUploadSerializer,
    VideoUploadRequestSerializer
)
from .rtsp_processor import stream_manager
from .stead_model import get_stead_model, run_anomaly_detection
from .video_streaming import get_stream_manager, FFmpegProcessor
from .rtsp_live_processor import get_live_manager, RTSPLiveProcessor
from .authentication import QueryParamTokenAuthentication

logger = logging.getLogger(__name__)


class ModelStatusView(APIView):
    """
    GET /api/stead/status/
    
    Check if the STEAD model is loaded and ready.
    Returns model configuration and system info.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            import torch
            
            model = get_stead_model()
            
            return Response({
                'status': 'ready',
                'model_loaded': model.model is not None,
                'device': str(model.device),
                'cuda_available': torch.cuda.is_available(),
                'cuda_device_name': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                'threshold': model.threshold,
                'frames_required': model.T,
                'frame_size': list(model.FRAME_SIZE)
            })
            
        except Exception as e:
            logger.error(f"Model status check failed: {e}")
            return Response({
                'status': 'error',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VideoUploadView(APIView):
    """
    POST /api/stead/video/upload/
    
    Upload a video file for STEAD anomaly detection.
    Generates annotated output video and prepares for streaming.
    Returns detection results including streaming URLs.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = VideoUploadRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        video_file = serializer.validated_data['video']
        threshold = request.data.get('threshold', 0.7)
        
        try:
            threshold = float(threshold)
            if not 0 <= threshold <= 1:
                threshold = 0.7
        except (ValueError, TypeError):
            threshold = 0.7
        
        # Create VideoUpload record
        upload = VideoUpload.objects.create(
            user=request.user,
            video_file=video_file,
            original_filename=video_file.name,
            status='processing'
        )
        
        try:
            # Create output directories
            upload_dir = Path(settings.MEDIA_ROOT) / 'stead_uploads'
            output_dir = Path(settings.MEDIA_ROOT) / 'stead_outputs'
            upload_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Get the file path
            video_path = upload.video_file.path
            video_id = str(upload.id)
            
            # Generate output path
            output_filename = f"output_{video_id}.mp4"
            output_path = str(output_dir / output_filename)
            
            # Run anomaly detection with annotated output
            result = run_anomaly_detection(
                video_path,
                output_path=output_path,
                threshold=threshold,
                save_output=True
            )
            
            # Process with FFmpeg for web streaming
            stream_manager_inst = get_stream_manager()
            stream_result = stream_manager_inst.process_output_video(
                video_id=video_id,
                input_video_path=video_path,
                annotated_video_path=output_path
            )
            
            # Update upload record
            upload.status = 'completed'
            upload.has_anomaly = result['has_anomaly']
            upload.max_anomaly_score = result['max_anomaly_score']
            upload.avg_anomaly_score = result.get('avg_anomaly_score')
            upload.total_clips = result['total_clips']
            upload.anomaly_count = result['anomaly_count']
            upload.total_frames = result['total_frames']
            upload.fps = result.get('video_fps')
            upload.resolution = result.get('resolution')
            
            # Store output paths
            upload.output_video = f"stead_outputs/{output_filename}"
            
            if stream_result.get('web_ready'):
                upload.output_video_web = os.path.relpath(
                    stream_result['web_ready'], settings.MEDIA_ROOT
                )
            
            if stream_result.get('hls_playlist'):
                upload.hls_playlist = os.path.relpath(
                    stream_result['hls_playlist'], settings.MEDIA_ROOT
                )
            
            if stream_result.get('thumbnail'):
                upload.thumbnail = os.path.relpath(
                    stream_result['thumbnail'], settings.MEDIA_ROOT
                )
            
            upload.result_details = {
                'anomaly_clips': result['anomaly_clips'],
                'total_frames': result['total_frames'],
                'video_fps': result.get('video_fps'),
                'threshold_used': result['threshold_used'],
                'all_clips': result.get('all_clips', [])
            }
            upload.processed_at = timezone.now()
            upload.save()
            
            # Build response with streaming URLs
            stream_urls = upload.get_stream_urls(request)
            
            return Response({
                'success': True,
                'upload_id': str(upload.id),
                'filename': video_file.name,
                'result': {
                    'has_anomaly': result['has_anomaly'],
                    'max_anomaly_score': result['max_anomaly_score'],
                    'avg_anomaly_score': result.get('avg_anomaly_score'),
                    'anomaly_count': result['anomaly_count'],
                    'total_clips': result['total_clips'],
                    'total_frames': result['total_frames'],
                    'fps': result.get('video_fps'),
                    'resolution': result.get('resolution'),
                    'anomaly_clips': result['anomaly_clips'],
                    'threshold_used': result['threshold_used']
                },
                'streaming': {
                    'original_video': stream_urls['original'],
                    'output_video': stream_urls['output'],
                    'web_ready_video': stream_urls['web_ready'],
                    'hls_playlist': stream_urls['hls'],
                    'thumbnail': stream_urls['thumbnail']
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error processing video: {e}")
            import traceback
            traceback.print_exc()
            
            upload.status = 'error'
            upload.error_message = str(e)
            upload.save()
            
            return Response({
                'success': False,
                'upload_id': str(upload.id),
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VideoUploadHistoryView(APIView):
    """
    GET /api/stead/video/history/
    
    Get history of video uploads for the current user.
    Includes streaming URLs for each video.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        uploads = VideoUpload.objects.filter(user=request.user)
        serializer = VideoUploadSerializer(uploads, many=True, context={'request': request})
        return Response(serializer.data)


class VideoUploadDetailView(APIView):
    """
    GET /api/stead/video/<uuid:upload_id>/
    DELETE /api/stead/video/<uuid:upload_id>/
    
    Get or delete a specific video upload.
    Includes streaming URLs in response.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, upload_id):
        try:
            upload = VideoUpload.objects.get(id=upload_id, user=request.user)
            serializer = VideoUploadSerializer(upload, context={'request': request})
            return Response(serializer.data)
        except VideoUpload.DoesNotExist:
            return Response(
                {'error': 'Upload not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def delete(self, request, upload_id):
        try:
            upload = VideoUpload.objects.get(id=upload_id, user=request.user)
            
            # Delete the video file
            if upload.video_file:
                if os.path.exists(upload.video_file.path):
                    os.remove(upload.video_file.path)
            
            # Delete output videos and HLS files
            stream_manager_inst = get_stream_manager()
            stream_manager_inst.cleanup_video(str(upload.id))
            
            upload.delete()
            return Response({'message': 'Upload deleted successfully'})
            
        except VideoUpload.DoesNotExist:
            return Response(
                {'error': 'Upload not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class VideoStreamView(APIView):
    """
    GET /api/stead/video/<uuid:upload_id>/stream/
    
    Stream the output video directly (MP4).
    Supports range requests for video seeking.
    """
    authentication_classes = [QueryParamTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, upload_id):
        try:
            upload = VideoUpload.objects.get(id=upload_id, user=request.user)
            
            # Prefer web-ready version, fallback to original output
            video_path = None
            if upload.output_video_web:
                video_path = Path(settings.MEDIA_ROOT) / upload.output_video_web
            elif upload.output_video:
                video_path = Path(settings.MEDIA_ROOT) / str(upload.output_video)
            
            if not video_path or not video_path.exists():
                raise Http404("Output video not found")
            
            # Support range requests for video seeking
            file_size = video_path.stat().st_size
            range_header = request.META.get('HTTP_RANGE', '').strip()
            
            if range_header:
                # Parse range header
                range_match = range_header.replace('bytes=', '').split('-')
                start = int(range_match[0]) if range_match[0] else 0
                end = int(range_match[1]) if range_match[1] else file_size - 1
                
                length = end - start + 1
                
                def file_iterator():
                    with open(video_path, 'rb') as f:
                        f.seek(start)
                        remaining = length
                        while remaining > 0:
                            chunk_size = min(8192, remaining)
                            data = f.read(chunk_size)
                            if not data:
                                break
                            remaining -= len(data)
                            yield data
                
                response = StreamingHttpResponse(
                    file_iterator(),
                    status=206,
                    content_type='video/mp4'
                )
                response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
                response['Content-Length'] = length
                response['Accept-Ranges'] = 'bytes'
                
            else:
                # Full file response
                response = FileResponse(
                    open(video_path, 'rb'),
                    content_type='video/mp4'
                )
                response['Content-Length'] = file_size
                response['Accept-Ranges'] = 'bytes'
            
            response['Content-Disposition'] = f'inline; filename="{upload.original_filename}_output.mp4"'
            return response
            
        except VideoUpload.DoesNotExist:
            raise Http404("Upload not found")


class VideoHLSView(APIView):
    """
    GET /api/stead/video/<uuid:upload_id>/hls/
    GET /api/stead/video/<uuid:upload_id>/hls/<str:filename>
    
    Serve HLS playlist and segments for adaptive streaming.
    This is the recommended way for frontend video playback.
    """
    authentication_classes = [QueryParamTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, upload_id, filename=None):
        try:
            upload = VideoUpload.objects.get(id=upload_id, user=request.user)
            
            if not upload.hls_playlist:
                raise Http404("HLS stream not available")
            
            hls_dir = Path(settings.MEDIA_ROOT) / Path(upload.hls_playlist).parent
            
            if filename is None:
                # Return playlist
                file_path = hls_dir / 'playlist.m3u8'
                content_type = 'application/vnd.apple.mpegurl'
            elif filename.endswith('.m3u8'):
                file_path = hls_dir / filename
                content_type = 'application/vnd.apple.mpegurl'
            elif filename.endswith('.ts'):
                file_path = hls_dir / filename
                content_type = 'video/MP2T'
            else:
                raise Http404("Invalid file type")
            
            if not file_path.exists():
                raise Http404("HLS file not found")
            
            response = FileResponse(
                open(file_path, 'rb'),
                content_type=content_type
            )
            
            # Enable CORS for HLS
            response['Access-Control-Allow-Origin'] = '*'
            return response
            
        except VideoUpload.DoesNotExist:
            raise Http404("Upload not found")


class VideoThumbnailView(APIView):
    """
    GET /api/stead/video/<uuid:upload_id>/thumbnail/
    
    Get the thumbnail image for a video.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, upload_id):
        try:
            upload = VideoUpload.objects.get(id=upload_id, user=request.user)
            
            if not upload.thumbnail:
                raise Http404("Thumbnail not available")
            
            thumbnail_path = Path(settings.MEDIA_ROOT) / upload.thumbnail
            
            if not thumbnail_path.exists():
                raise Http404("Thumbnail not found")
            
            return FileResponse(
                open(thumbnail_path, 'rb'),
                content_type='image/jpeg'
            )
            
        except VideoUpload.DoesNotExist:
            raise Http404("Upload not found")


class FFmpegStatusView(APIView):
    """
    GET /api/stead/ffmpeg/status/
    
    Check if FFmpeg is available for video processing.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            ffmpeg = FFmpegProcessor()
            available = ffmpeg.is_available()
            
            return Response({
                'ffmpeg_available': available,
                'ffmpeg_path': ffmpeg.ffmpeg_path if available else None,
                'ffprobe_path': ffmpeg.ffprobe_path
            })
        except Exception as e:
            return Response({
                'ffmpeg_available': False,
                'error': str(e)
            })


class WebcamTestView(APIView):
    """
    POST /api/stead/webcam/test/
    
    Test STEAD model with local webcam (for development testing).
    Captures 16 frames and runs inference.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        import cv2
        
        camera_index = request.data.get('camera_index', 0)
        threshold = request.data.get('threshold', 0.7)
        
        try:
            camera_index = int(camera_index)
            threshold = float(threshold)
        except (ValueError, TypeError):
            return Response(
                {'error': 'Invalid camera_index or threshold'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            cap = cv2.VideoCapture(camera_index)
            
            if not cap.isOpened():
                return Response(
                    {'error': f'Cannot open camera {camera_index}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            frames = []
            for _ in range(16):
                ret, frame = cap.read()
                if not ret:
                    cap.release()
                    return Response(
                        {'error': 'Failed to capture frames from webcam'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                frames.append(frame)
                time.sleep(0.066)  # ~15 FPS
            
            cap.release()
            
            model = get_stead_model()
            result = model.predict_frames(frames, threshold=threshold)
            
            return Response({
                'success': True,
                'camera_index': camera_index,
                'result': result
            })
            
        except Exception as e:
            logger.error(f"Webcam test error: {e}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============= RTSP Job Views =============

class RTSPJobListCreateView(APIView):
    """
    GET /api/stead/rtsp/jobs/
    POST /api/stead/rtsp/jobs/
    
    List all RTSP jobs or create a new one.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        jobs = RTSPJob.objects.filter(user=request.user)
        serializer = RTSPJobSerializer(jobs, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        serializer = RTSPJobCreateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Create the job
        job = RTSPJob.objects.create(
            user=request.user,
            **serializer.validated_data
        )
        
        try:
            # Start the RTSP stream
            stream_manager.add_stream(
                job_id=str(job.id),
                stream_url=job.rtsp_url,
                fps=job.fps
            )
            
            # Update job status
            job.status = 'running'
            job.started_at = timezone.now()
            job.save()
            
            return Response(
                RTSPJobSerializer(job).data,
                status=status.HTTP_201_CREATED
            )
            
        except ConnectionError as e:
            job.status = 'error'
            job.save()
            return Response(
                {'error': f'Cannot connect to stream: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            job.status = 'error'
            job.save()
            logger.error(f"Error starting RTSP job: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RTSPJobDetailView(APIView):
    """
    GET /api/stead/rtsp/jobs/<uuid:job_id>/
    DELETE /api/stead/rtsp/jobs/<uuid:job_id>/
    
    Get details or delete a specific RTSP job.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, job_id):
        try:
            job = RTSPJob.objects.get(id=job_id, user=request.user)
            
            # Get live status from stream manager
            processor = stream_manager.get_stream(str(job.id))
            live_status = processor.get_status() if processor else None
            
            data = RTSPJobSerializer(job).data
            data['live_status'] = live_status
            
            return Response(data)
            
        except RTSPJob.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def delete(self, request, job_id):
        try:
            job = RTSPJob.objects.get(id=job_id, user=request.user)
            
            # Stop the stream if running
            stream_manager.remove_stream(str(job.id))
            
            # Delete job and related anomalies
            job.delete()
            
            return Response({'message': 'Job deleted successfully'})
            
        except RTSPJob.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class RTSPJobControlView(APIView):
    """
    POST /api/stead/rtsp/jobs/<uuid:job_id>/control/
    
    Control an RTSP job (start, stop, pause).
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, job_id):
        action = request.data.get('action')
        
        if action not in ['start', 'stop', 'pause']:
            return Response(
                {'error': 'Invalid action. Use: start, stop, or pause'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            job = RTSPJob.objects.get(id=job_id, user=request.user)
            
            if action == 'start':
                if job.status == 'running':
                    return Response({'message': 'Job is already running'})
                
                stream_manager.add_stream(str(job.id), job.rtsp_url, job.fps)
                job.status = 'running'
                job.started_at = timezone.now()
                job.stopped_at = None
                
            elif action == 'stop':
                stream_manager.remove_stream(str(job.id))
                job.status = 'stopped'
                job.stopped_at = timezone.now()
                
            elif action == 'pause':
                stream_manager.remove_stream(str(job.id))
                job.status = 'paused'
            
            job.save()
            return Response(RTSPJobSerializer(job).data)
            
        except RTSPJob.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"RTSP control error: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RTSPJobInferenceView(APIView):
    """
    POST /api/stead/rtsp/jobs/<uuid:job_id>/infer/
    
    Run inference on the current frame buffer for an RTSP job.
    Returns anomaly detection result for the latest 16 frames.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, job_id):
        try:
            job = RTSPJob.objects.get(id=job_id, user=request.user)
            
            if job.status != 'running':
                return Response(
                    {'error': 'Job is not running'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            processor = stream_manager.get_stream(str(job.id))
            if not processor:
                return Response(
                    {'error': 'Stream processor not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            if not processor.has_enough_frames():
                return Response({
                    'ready': False,
                    'message': f'Not enough frames. Current: {len(processor.frame_buffer)}/16',
                    'frames_available': len(processor.frame_buffer)
                })
            
            # Get frames and run inference
            frames = processor.get_frames_for_inference()
            model = get_stead_model()
            result = model.predict_frames(frames, threshold=job.threshold)
            
            # Update job statistics
            job.total_frames_processed += 16
            
            # If anomaly detected, save it
            if result['has_anomaly']:
                job.total_anomalies_detected += 1
                job.last_anomaly_at = timezone.now()
                
                AnomalyDetection.objects.create(
                    job=job,
                    anomaly_score=result['anomaly_score'],
                    label=result['label'],
                    frame_start=job.total_frames_processed - 16,
                    frame_end=job.total_frames_processed,
                    model_output=result
                )
            
            job.save()
            
            return Response({
                'ready': True,
                'result': result,
                'total_frames_processed': job.total_frames_processed,
                'total_anomalies_detected': job.total_anomalies_detected
            })
            
        except RTSPJob.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Inference error: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============= Anomaly Views =============

class AnomalyListView(APIView):
    """
    GET /api/stead/anomalies/
    
    List anomalies for the current user.
    Optional query params: job_id, limit
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        job_id = request.query_params.get('job_id')
        limit = request.query_params.get('limit', 100)
        
        try:
            limit = int(limit)
        except ValueError:
            limit = 100
        
        if job_id:
            anomalies = AnomalyDetection.objects.filter(
                job__id=job_id,
                job__user=request.user
            )[:limit]
        else:
            anomalies = AnomalyDetection.objects.filter(
                job__user=request.user
            )[:limit]
        
        serializer = AnomalyDetectionSerializer(anomalies, many=True)
        return Response(serializer.data)


class AnomalyDetailView(APIView):
    """
    GET /api/stead/anomalies/<uuid:anomaly_id>/
    DELETE /api/stead/anomalies/<uuid:anomaly_id>/
    
    Get or delete a specific anomaly record.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, anomaly_id):
        try:
            anomaly = AnomalyDetection.objects.get(
                id=anomaly_id,
                job__user=request.user
            )
            serializer = AnomalyDetectionSerializer(anomaly)
            return Response(serializer.data)
        except AnomalyDetection.DoesNotExist:
            return Response(
                {'error': 'Anomaly not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def delete(self, request, anomaly_id):
        try:
            anomaly = AnomalyDetection.objects.get(
                id=anomaly_id,
                job__user=request.user
            )
            anomaly.delete()
            return Response({'message': 'Anomaly deleted successfully'})
        except AnomalyDetection.DoesNotExist:
            return Response(
                {'error': 'Anomaly not found'},
                status=status.HTTP_404_NOT_FOUND
            )


# ============= RTSP Live Processing Views =============

class RTSPLiveStartView(APIView):
    """
    POST /api/stead/rtsp/live/start/
    
    Start RTSP live processing.
    Takes an RTSP URL (or video file path/TCP stream), runs STEAD inference,
    and produces annotated output video with FFmpeg streaming.
    
    Request body:
    {
        "stream_url": "rtsp://...", // or tcp://localhost:8554 or /path/to/video.mp4
        "fps": 15,                  // Optional, default 15
        "threshold": 0.7            // Optional, default 0.7
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        stream_url = request.data.get('stream_url')
        
        if not stream_url:
            return Response(
                {'error': 'stream_url is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Parse optional parameters
        fps = request.data.get('fps', 15)
        threshold = request.data.get('threshold', 0.7)
        
        try:
            fps = int(fps)
            threshold = float(threshold)
        except (ValueError, TypeError) as e:
            return Response(
                {'error': f'Invalid parameter: {e}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get output directory
            output_dir = str(Path(settings.MEDIA_ROOT) / 'stead_live_outputs')
            
            # Get the live manager
            live_manager = get_live_manager()
            
            # Create and start the processor
            processor = live_manager.create_job(
                stream_url=stream_url,
                output_dir=output_dir,
                fps=fps,
                threshold=threshold
            )
            
            # Start processing
            success = processor.start()
            
            if not success:
                return Response({
                    'success': False,
                    'error': processor.error_message or 'Failed to start processing'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': True,
                'job_id': processor.job_id,
                'message': 'RTSP live processing started',
                'stream_url': stream_url,
                'fps': fps,
                'threshold': threshold,
                'status': processor.get_status()
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error starting RTSP live processing: {e}")
            import traceback
            traceback.print_exc()
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RTSPLiveStatusView(APIView):
    """
    GET /api/stead/rtsp/live/<str:job_id>/status/
    
    Get status of an RTSP live processing job.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, job_id):
        live_manager = get_live_manager()
        processor = live_manager.get_job(job_id)
        
        if not processor:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(processor.get_status())


class RTSPLiveStopView(APIView):
    """
    POST /api/stead/rtsp/live/<str:job_id>/stop/
    
    Stop an RTSP live processing job and get the results.
    Returns output video paths and streaming URLs.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, job_id):
        live_manager = get_live_manager()
        processor = live_manager.get_job(job_id)
        
        if not processor:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            # Stop the processor and get results
            result = processor.stop()
            
            # Build streaming URLs
            streaming_urls = self._build_streaming_urls(request, result)
            
            return Response({
                'success': result.get('success', False),
                'job_id': result.get('job_id'),
                'stats': result.get('stats'),
                'output': {
                    'output_video': result.get('output_video'),
                    'web_ready': result.get('web_ready'),
                    'hls_playlist': result.get('hls_playlist'),
                    'thumbnail': result.get('thumbnail')
                },
                'streaming_urls': streaming_urls,
                'error': result.get('error')
            })
            
        except Exception as e:
            logger.error(f"Error stopping RTSP live processing: {e}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _build_streaming_urls(self, request, result):
        """Build streaming URLs from result paths."""
        urls = {}
        base_url = request.build_absolute_uri(settings.MEDIA_URL)
        
        # For each path, convert to relative media path
        for key in ['output_video', 'web_ready', 'hls_playlist', 'thumbnail']:
            path = result.get(key)
            if path and os.path.exists(path):
                # Make relative to MEDIA_ROOT
                try:
                    rel_path = os.path.relpath(path, settings.MEDIA_ROOT)
                    urls[key] = f"{base_url}{rel_path}"
                except ValueError:
                    urls[key] = None
            else:
                urls[key] = None
        
        return urls


class RTSPLiveControlView(APIView):
    """
    POST /api/stead/rtsp/live/<str:job_id>/control/
    
    Control an RTSP live processing job (pause/resume).
    
    Request body:
    {
        "action": "pause" | "resume"
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, job_id):
        action = request.data.get('action')
        
        if action not in ['pause', 'resume']:
            return Response(
                {'error': 'Invalid action. Use: pause or resume'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        live_manager = get_live_manager()
        processor = live_manager.get_job(job_id)
        
        if not processor:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if action == 'pause':
            processor.pause()
        elif action == 'resume':
            processor.resume()
        
        return Response({
            'success': True,
            'action': action,
            'status': processor.get_status()
        })


class RTSPLiveListView(APIView):
    """
    GET /api/stead/rtsp/live/
    
    List all RTSP live processing jobs.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        live_manager = get_live_manager()
        statuses = live_manager.get_all_statuses()
        
        return Response({
            'jobs': list(statuses.values()),
            'total': len(statuses)
        })


class RTSPLiveStreamView(APIView):
    """
    GET /api/stead/rtsp/live/<str:job_id>/stream/
    
    Stream the output video of a completed RTSP live processing job.
    Supports range requests for video seeking.
    """
    authentication_classes = [QueryParamTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, job_id):
        live_manager = get_live_manager()
        processor = live_manager.get_job(job_id)
        
        if not processor:
            raise Http404("Job not found")
        
        # Prefer web-ready version
        video_path = processor.web_ready_path or processor.output_video_path
        
        if not video_path or not os.path.exists(video_path):
            raise Http404("Output video not found. Job may still be processing.")
        
        video_path = Path(video_path)
        file_size = video_path.stat().st_size
        
        # Support range requests
        range_header = request.META.get('HTTP_RANGE', '').strip()
        
        if range_header:
            range_match = range_header.replace('bytes=', '').split('-')
            start = int(range_match[0]) if range_match[0] else 0
            end = int(range_match[1]) if range_match[1] else file_size - 1
            length = end - start + 1
            
            def file_iterator():
                with open(video_path, 'rb') as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk_size = min(8192, remaining)
                        data = f.read(chunk_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data
            
            response = StreamingHttpResponse(
                file_iterator(),
                status=206,
                content_type='video/mp4'
            )
            response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response['Content-Length'] = length
            response['Accept-Ranges'] = 'bytes'
        else:
            response = FileResponse(
                open(video_path, 'rb'),
                content_type='video/mp4'
            )
            response['Content-Length'] = file_size
            response['Accept-Ranges'] = 'bytes'
        
        response['Content-Disposition'] = f'inline; filename="live_output_{job_id}.mp4"'
        return response


class RTSPLiveHLSView(APIView):
    """
    GET /api/stead/rtsp/live/<str:job_id>/hls/
    GET /api/stead/rtsp/live/<str:job_id>/hls/<str:filename>
    
    Serve HLS playlist and segments for a completed RTSP live job.
    """
    authentication_classes = [QueryParamTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, job_id, filename=None):
        live_manager = get_live_manager()
        processor = live_manager.get_job(job_id)
        
        if not processor:
            raise Http404("Job not found")
        
        if not processor.hls_playlist_path:
            raise Http404("HLS stream not available. Job may still be processing.")
        
        hls_dir = Path(processor.hls_playlist_path).parent
        
        if filename is None:
            file_path = hls_dir / 'playlist.m3u8'
            content_type = 'application/vnd.apple.mpegurl'
        elif filename.endswith('.m3u8'):
            file_path = hls_dir / filename
            content_type = 'application/vnd.apple.mpegurl'
        elif filename.endswith('.ts'):
            file_path = hls_dir / filename
            content_type = 'video/MP2T'
        else:
            raise Http404("Invalid file type")
        
        if not file_path.exists():
            raise Http404("HLS file not found")
        
        response = FileResponse(
            open(file_path, 'rb'),
            content_type=content_type
        )
        response['Access-Control-Allow-Origin'] = '*'
        return response


class RTSPTestSimulatorView(APIView):
    """
    POST /api/stead/rtsp/test/simulate/
    
    Test endpoint that uses a local video file as a simulated RTSP stream.
    Useful for testing when no actual RTSP camera is available.
    
    Request body:
    {
        "video_path": "/path/to/test_video.mp4",  // or use default test video
        "fps": 15,
        "threshold": 0.7
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        video_path = request.data.get('video_path')
        fps = request.data.get('fps', 15)
        threshold = request.data.get('threshold', 0.7)
        
        # If no video path provided, look for test videos
        if not video_path:
            # Check for common test video locations
            possible_paths = [
                '/home/maaza/predict-xplore-iit-b/Predict-Xplore/VID-20250814-WA0006.mp4',
                '/home/maaza/predict-xplore-iit-b/Predict-Xplore/predict Xplore nov25.mp4',
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    video_path = path
                    break
        
        if not video_path or not os.path.exists(video_path):
            return Response({
                'error': 'Test video not found. Please provide video_path.',
                'available_test_videos': [p for p in [
                    '/home/maaza/predict-xplore-iit-b/Predict-Xplore/VID-20250814-WA0006.mp4',
                    '/home/maaza/predict-xplore-iit-b/Predict-Xplore/predict Xplore nov25.mp4',
                ] if os.path.exists(p)]
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            fps = int(fps)
            threshold = float(threshold)
        except (ValueError, TypeError) as e:
            return Response(
                {'error': f'Invalid parameter: {e}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Use the video file directly as stream URL
            output_dir = str(Path(settings.MEDIA_ROOT) / 'stead_live_outputs')
            
            live_manager = get_live_manager()
            processor = live_manager.create_job(
                stream_url=video_path,  # OpenCV can read video files directly
                output_dir=output_dir,
                fps=fps,
                threshold=threshold
            )
            
            success = processor.start()
            
            if not success:
                return Response({
                    'success': False,
                    'error': processor.error_message or 'Failed to start processing'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': True,
                'job_id': processor.job_id,
                'message': 'Test simulation started',
                'source_video': video_path,
                'fps': fps,
                'threshold': threshold,
                'note': 'Use /api/stead/rtsp/live/<job_id>/status/ to check progress',
                'stop_endpoint': f'/api/stead/rtsp/live/{processor.job_id}/stop/'
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error in test simulation: {e}")
            import traceback
            traceback.print_exc()
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RTSPLiveAnomalyClipView(APIView):
    """
    GET /api/stead/rtsp/live/anomaly-clip/<path:filepath>
    
    Serves generated extracted mp4 anomaly clips directly to the frontend.
    """
    authentication_classes = [QueryParamTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, filepath):
        try:
            video_path = Path(settings.MEDIA_ROOT) / filepath
            
            if not video_path.exists() or not video_path.is_file():
                raise Http404("Anomaly clip not found.")
                
            file_size = video_path.stat().st_size
            range_header = request.META.get('HTTP_RANGE', '').strip()
            
            if range_header:
                range_match = range_header.replace('bytes=', '').split('-')
                start = int(range_match[0]) if range_match[0] else 0
                end = int(range_match[1]) if range_match[1] else file_size - 1
                length = end - start + 1
                
                def file_iterator():
                    with open(video_path, 'rb') as f:
                        f.seek(start)
                        remaining = length
                        while remaining > 0:
                            chunk_size = min(8192, remaining)
                            data = f.read(chunk_size)
                            if not data:
                                break
                            remaining -= len(data)
                            yield data
                
                response = StreamingHttpResponse(
                    file_iterator(),
                    status=206,
                    content_type='video/mp4'
                )
                response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
                response['Content-Length'] = length
                response['Accept-Ranges'] = 'bytes'
            else:
                response = FileResponse(
                    open(video_path, 'rb'),
                    content_type='video/mp4'
                )
                response['Content-Length'] = file_size
                response['Accept-Ranges'] = 'bytes'
            
            response['Content-Disposition'] = f'inline; filename="{video_path.name}"'
            return response
        except Exception as e:
            raise Http404(f"Error serving clip: {e}")

