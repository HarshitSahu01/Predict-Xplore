"""
STEAD App URL Configuration.

All endpoints are prefixed with /api/stead/
"""

from django.urls import path
from .views import (
    # Model status
    ModelStatusView,
    
    # Video upload
    VideoUploadView,
    VideoUploadHistoryView,
    VideoUploadDetailView,
    
    # Video streaming
    VideoStreamView,
    VideoHLSView,
    VideoThumbnailView,
    FFmpegStatusView,
    
    # Webcam test
    WebcamTestView,
    
    # RTSP jobs (existing)
    RTSPJobListCreateView,
    RTSPJobDetailView,
    RTSPJobControlView,
    RTSPJobInferenceView,
    
    # RTSP Live Processing (new)
    RTSPLiveStartView,
    RTSPLiveStatusView,
    RTSPLiveStopView,
    RTSPLiveControlView,
    RTSPLiveListView,
    RTSPLiveStreamView,
    RTSPLiveHLSView,
    RTSPTestSimulatorView,
    RTSPLiveAnomalyClipView,
    
    # Anomalies
    AnomalyListView,
    AnomalyDetailView,
)

app_name = 'stead'

urlpatterns = [
    # Model status
    path('status/', ModelStatusView.as_view(), name='model-status'),
    
    # FFmpeg status
    path('ffmpeg/status/', FFmpegStatusView.as_view(), name='ffmpeg-status'),
    
    # Video upload endpoints
    path('video/upload/', VideoUploadView.as_view(), name='video-upload'),
    path('video/history/', VideoUploadHistoryView.as_view(), name='video-history'),
    path('video/<uuid:upload_id>/', VideoUploadDetailView.as_view(), name='video-detail'),
    
    # Video streaming endpoints
    path('video/<uuid:upload_id>/stream/', VideoStreamView.as_view(), name='video-stream'),
    path('video/<uuid:upload_id>/hls/', VideoHLSView.as_view(), name='video-hls-playlist'),
    path('video/<uuid:upload_id>/hls/<str:filename>', VideoHLSView.as_view(), name='video-hls-segment'),
    path('video/<uuid:upload_id>/thumbnail/', VideoThumbnailView.as_view(), name='video-thumbnail'),
    
    # Webcam test (development)
    path('webcam/test/', WebcamTestView.as_view(), name='webcam-test'),
    
    # RTSP job endpoints (existing)
    path('rtsp/jobs/', RTSPJobListCreateView.as_view(), name='rtsp-job-list-create'),
    path('rtsp/jobs/<uuid:job_id>/', RTSPJobDetailView.as_view(), name='rtsp-job-detail'),
    path('rtsp/jobs/<uuid:job_id>/control/', RTSPJobControlView.as_view(), name='rtsp-job-control'),
    path('rtsp/jobs/<uuid:job_id>/infer/', RTSPJobInferenceView.as_view(), name='rtsp-job-infer'),
    
    # RTSP Live Processing endpoints (new - what you need)
    path('rtsp/live/', RTSPLiveListView.as_view(), name='rtsp-live-list'),
    path('rtsp/live/start/', RTSPLiveStartView.as_view(), name='rtsp-live-start'),
    path('rtsp/live/<str:job_id>/status/', RTSPLiveStatusView.as_view(), name='rtsp-live-status'),
    path('rtsp/live/<str:job_id>/stop/', RTSPLiveStopView.as_view(), name='rtsp-live-stop'),
    path('rtsp/live/<str:job_id>/control/', RTSPLiveControlView.as_view(), name='rtsp-live-control'),
    path('rtsp/live/<str:job_id>/stream/', RTSPLiveStreamView.as_view(), name='rtsp-live-stream'),
    path('rtsp/live/<str:job_id>/hls/', RTSPLiveHLSView.as_view(), name='rtsp-live-hls-playlist'),
    path('rtsp/live/<str:job_id>/hls/<str:filename>', RTSPLiveHLSView.as_view(), name='rtsp-live-hls-segment'),
    path('rtsp/live/anomaly-clip/<path:filepath>', RTSPLiveAnomalyClipView.as_view(), name='rtsp-live-anomaly-clip'),
    
    # Test simulator - use local video as RTSP stream
    path('rtsp/test/simulate/', RTSPTestSimulatorView.as_view(), name='rtsp-test-simulate'),
    
    # Anomaly endpoints
    path('anomalies/', AnomalyListView.as_view(), name='anomaly-list'),
    path('anomalies/<uuid:anomaly_id>/', AnomalyDetailView.as_view(), name='anomaly-detail'),
]
