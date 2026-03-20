from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from predictor.models import Task, Container, ContainerAnomaly
import subprocess
import os
import json
import psutil
from datetime import datetime

class RTSPContainerTaskView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        rtsp_url = request.data.get('rtsp_url')
        container_id = request.data.get('container_id')
        fps = request.data.get('fps', 15)

        if not rtsp_url or not container_id:
            return Response({"error": "rtsp_url and container_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            container = Container.objects.get(id=container_id)
        except Container.DoesNotExist:
            return Response({"error": "Container not found."}, status=status.HTTP_404_NOT_FOUND)

        task = Task.objects.create(
            task_name=f"RTSP Stream ({container.name}) - {rtsp_url[-10:]}",
            user=request.user,
            status='Pending',
            start_time=datetime.now(),
            container=container,
            rtsp_url=rtsp_url,
            fps=fps
        )

        payload = {
            "fps": fps
        }

        # Start subprocess
        import sys
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bgprocessing', 'rtsp_container_bg.py')
        bg_process = subprocess.Popen([sys.executable, script_path, str(task.task_id), json.dumps(payload)])

        task.subprocess_id = bg_process.pid
        task.save()

        return Response({
            "message": "RTSP Container processing started.",
            "task_id": task.task_id
        }, status=status.HTTP_201_CREATED)

    def get(self, request, *args, **kwargs):
        # List all RTSP tasks (those with a container and rtsp_url attached)
        tasks = Task.objects.filter(user=request.user, rtsp_url__isnull=False).order_by('-start_time')
        data = []
        for t in tasks:
            # Also fetch stats
            anomalies = t.anomalies.all()
            data.append({
                "job_id": t.task_id, # for frontend compatibility
                "task_name": t.task_name,
                "status": t.status,
                "is_running": t.status == 'Running',
                "start_time": t.start_time,
                "end_time": t.end_time,
                "container_name": t.container.name if t.container else None,
                "rtsp_url": t.rtsp_url,
                "stats": {
                    "total_frames": getattr(t, 'total_frames', 0), # optional if we track
                    "anomalies_detected": anomalies.count(),
                    "status": t.status.lower()
                }
            })
        return Response(data, status=status.HTTP_200_OK)

class RTSPContainerTaskDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, task_id, *args, **kwargs):
        try:
            task = Task.objects.get(task_id=task_id, user=request.user)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=status.HTTP_404_NOT_FOUND)
            
        anomalies = task.anomalies.all().order_by('-timestamp')
        anomaly_data = []
        from django.conf import settings
        
        for a in anomalies:
            anomaly_data.append({
                "id": a.id,
                "timestamp": a.timestamp,
                "confidence": a.confidence,
                "label": a.label,
                "video_path": a.video_clip.name if a.video_clip else None
            })
            
        data = {
            "job_id": task.task_id,
            "task_name": task.task_name,
            "status": task.status,
            "is_running": task.status == 'Running',
            "start_time": task.start_time,
            "end_time": task.end_time,
            "container_name": task.container.name if task.container else None,
            "rtsp_url": task.rtsp_url,
            "fps": task.fps,
            "stats": {
                "anomalies_detected": len(anomaly_data),
                "anomaly_clips": anomaly_data,
                "status": task.status.lower()
            }
        }
        return Response(data, status=status.HTTP_200_OK)

class RTSPContainerTaskActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, task_id, action, *args, **kwargs):
        try:
            task = Task.objects.get(task_id=task_id, user=request.user)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=status.HTTP_404_NOT_FOUND)

        if action == "stop":
            if task.status in ['Completed', 'Failed', 'Stopped']:
                return Response({"error": "Task already ended."}, status=status.HTTP_400_BAD_REQUEST)

            if task.subprocess_id:
                try:
                    p = psutil.Process(task.subprocess_id)
                    p.terminate()
                    p.wait(timeout=5)
                except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                    try:
                        p.kill() # force kill
                    except:
                        pass

            task.status = "Stopped"
            task.end_time = datetime.now()
            task.save()
            return Response({
                "success": True,
                "job_id": task.task_id,
                "stats": {
                    "status": "stopped",
                    "anomalies_detected": task.anomalies.count()
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)
