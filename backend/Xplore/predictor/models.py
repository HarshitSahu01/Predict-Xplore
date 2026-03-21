from django.conf import settings
from django.db import models
from django.contrib.auth import get_user_model
import uuid

# Get the user model
User = get_user_model()

class Model(models.Model):
    # Add all types of architectures supported by Predict-Xplore
    MODEL_TYPES = [
        ('ImageSegmentation', 'Image Segmentation'),
        ('ObjectDetection', 'Object Detection'),
        ('HumanDetection', 'Human Detection'),
    ]
    name = models.CharField(max_length=255, help_text="Name of the machine learning model")
    description = models.TextField(help_text="Description of the model")
    model_file = models.FileField(upload_to='models_weights/', help_text="Path to the uploaded model file")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, help_text="Admin who uploaded the model")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Timestamp of model creation")
    model_type = models.CharField(
        max_length=50, null=False, blank=False, choices=MODEL_TYPES, help_text="Type of the model (e.g., image segmentation, object detection)"
    )
    model_thumbnail = models.ImageField(upload_to='model_images/', help_text="Image of the model", null=True, blank=True)
    allowed_xai_models = models.JSONField(default=list, help_text="List of allowed XAI models for this model", null=True, blank=True)
    classes = models.JSONField(default=list, help_text="List of allowed target classes for the model", null=True, blank=True)
    allowed_users = models.JSONField(default=list, help_text="List of allowed user types for this model", null=True, blank=True)

    def __str__(self):
        return self.name


class Pipeline(models.Model):
    name = models.CharField(max_length=255, verbose_name="Pipeline Name")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Created By")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    allowed_models = models.JSONField(default=list)

    def __str__(self):
        return self.name


class TestCase(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Completed', 'Completed'),
    ]
    pipeline = models.ForeignKey(Pipeline, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Pipeline")
    model = models.ForeignKey(Model, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Model")
    test_image = models.ImageField(upload_to="test_images/", null=True, blank=True, verbose_name="Test Image")
    video_feed_url = models.URLField(max_length=500, null=True, blank=True, verbose_name="Video Feed URL")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Created By")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="Pending", verbose_name="Status")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    xai_algo = models.CharField(
        max_length=32,
        choices=settings.XAI_ALGOS,
        null=True,
        blank=True,
        help_text="Which XAI algorithm to run (if any)",
    )

    def __str__(self):
        return f"Test Case {self.id} - Status: {self.status}"


# models.py
class Report(models.Model):
    test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE, verbose_name="Test Case")
    model = models.ForeignKey(Model, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Model Used")  # <-- NEW
    report_file = models.FileField(upload_to='reports/', help_text="Generated report file (PDF, etc.)")
    xai_visualization = models.ImageField(upload_to='xai_visualizations/', null=True, blank=True)
    bounding_boxes = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")



class Container(models.Model):

    name = models.CharField(max_length=255, help_text="Name of the machine learning model")
    description = models.TextField(help_text="Description of the model")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, help_text="Admin who uploaded the model")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Timestamp of model creation")
    allowed_users = models.JSONField(default=list, help_text="List of allowed user types for this model", null=True, blank=True)

    def __str__(self):
        return self.name

class ContainerGithub(models.Model):
    container = models.OneToOneField(Container, on_delete=models.CASCADE, related_name='github_info', help_text="Linked container")
    repo_url = models.URLField(max_length=500, help_text="GitHub Repository URL")
    github_folder = models.CharField(max_length=255, help_text="Path to folder within the repository")
    folder_hash = models.CharField(max_length=255, help_text="Latest commit SHA for this specific folder tree")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last time the update check was performed")

    def __str__(self):
        return f"GitHub Link for {self.container.name}"

class Task(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Running', 'Running'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
    ]
    task_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, help_text="Unique task identifier")
    task_name = models.CharField(max_length=255, help_text="Name of the task")
    user = models.ForeignKey(User, on_delete=models.CASCADE, help_text="User who initiated the task", null=True, blank=True)
    subprocess_id = models.IntegerField(null=True, blank=True, help_text="PID of the spawned subprocess")
    start_time = models.DateTimeField(auto_now_add=True, help_text="Time the task started")
    end_time = models.DateTimeField(null=True, blank=True, help_text="Time the task finished")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Pending', help_text="Current state of task")
    log_file = models.CharField(max_length=500, null=True, blank=True, help_text="Path to log file")
    
    # RTSP Container specific fields
    container = models.ForeignKey(Container, on_delete=models.SET_NULL, null=True, blank=True, help_text="Container linked to this RTSP task")
    rtsp_url = models.CharField(max_length=500, null=True, blank=True, help_text="RTSP URL for streaming")
    fps = models.IntegerField(null=True, blank=True, help_text="Frames per second to capture")

    def __str__(self):
        return f"{self.task_name} - {self.status}"

class ContainerAnomaly(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='anomalies')
    video_clip = models.FileField(upload_to='container_anomalies/', null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    confidence = models.FloatField(null=True, blank=True)
    label = models.CharField(max_length=100, default='Suspicious')
    
    def __str__(self):
        return f"Anomaly for {self.task.task_name} at {self.timestamp}"