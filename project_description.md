# Predict-Xplore: Project Description

## 1) Application Structure

## 1.1 High-level architecture
- **Frontend**: React + Vite app in `/frontend`
  - Routing and pages in `src/App.jsx`
  - State management via Redux Toolkit (`src/redux`)
  - UI for users and admins (model testing, pipelines, reports, containers, STEAD RTSP/video workflows)
- **Backend**: Django + Django REST Framework app in `/backend/Xplore`
  - Django project config in `Xplore/settings.py`, `Xplore/urls.py`
  - Apps:
    - `users` (custom auth, OTP, RBAC-like user roles)
    - `predictor` (model upload/testing/pipeline/container lifecycle)
    - `stead` (anomaly detection for uploaded videos and RTSP streams)
- **Containerized local development**: `docker-compose.yml` with `frontend` and `backend` services

## 1.2 Backend app boundaries
- **users app**
  - Custom `User` model with role + JSON `user_roles`
  - Registration/login/token/OTP verification
  - Admin user CRUD for non-admin accounts
- **predictor app**
  - Model registry and model execution
  - Test-case upload and report generation
  - Pipeline execution (sequential model chain)
  - Container creation/run/update/delete APIs
  - Task tracking/logging for background jobs
- **stead app**
  - STEAD model inference for anomaly detection
  - Video upload processing with output video + HLS + thumbnails
  - RTSP job orchestration and live stream management
  - Anomaly persistence and retrieval

---

## 2) Database Structure (Current)

The project uses **Django ORM** with SQLite by default (`db.sqlite3` in settings).

## 2.1 ORMs and persistence technologies
- **Primary ORM**: Django ORM (`django.db.models`)
- **Serializer layer**: Django REST Framework serializers
- **No SQLAlchemy/Prisma/TypeORM** detected
- **Task/process state** persisted in DB via `Task`, `RTSPJob`, `VideoUpload`, etc.

## 2.2 Core entities

### users app
- **User**
  - Identity: `username`, `email`, `phone_number`
  - Auth/security: `password` (hashed), `otp`, `otp_expiry`, `is_active`, `is_staff`
  - Authorization: `role` (`admin`/`user`), `user_roles` (JSON list)

### predictor app
- **Model**
  - Metadata: `name`, `description`, `model_type`
  - Files: `model_file`, `model_thumbnail`
  - Access config: `allowed_users` (JSON), `classes` (JSON), `allowed_xai_models` (JSON)
  - Ownership: `created_by`
- **Pipeline**
  - `name`, `created_by`, `is_active`, `allowed_models` (JSON)
- **TestCase**
  - Input references: `test_image`, optional `video_feed_url`
  - Links: optional `pipeline`, optional `model`
  - Execution fields: `status`, optional `xai_algo`, `created_by`
- **Report**
  - Links: `test_case`, optional `model`
  - Outputs: `report_file`, optional `xai_visualization`, optional `bounding_boxes` (JSON)
- **Container**
  - `name`, `description`, `allowed_users` (JSON), `created_by`
- **ContainerGithub**
  - One-to-one with `Container`
  - `repo_url`, `github_folder`, `folder_hash`, `updated_at`
- **Task**
  - Lifecycle: `status`, `start_time`, `end_time`, `subprocess_id`, `log_file`
  - Ownership: `user`
  - RTSP container context: `container`, `rtsp_url`, `fps`
- **ContainerAnomaly**
  - Link: `task`
  - Detection output: `video_clip`, `confidence`, `label`, `timestamp`

### stead app
- **RTSPJob**
  - Stream config: `name`, `rtsp_url`, `fps`, `buffer_size`, `threshold`
  - Runtime stats: `total_frames_processed`, `total_anomalies_detected`, `last_anomaly_at`
  - Lifecycle timestamps: `started_at`, `stopped_at`, `created_at`, `updated_at`
- **AnomalyDetection**
  - Link: `job`
  - Detection payload: `anomaly_score`, `label`, `frame_start`, `frame_end`, `video_chunk`, `model_output` (JSON)
- **VideoUpload**
  - Input: `video_file`, `original_filename`, `user`
  - Outputs: `output_video`, `output_video_web`, `hls_playlist`, `thumbnail`
  - Results: `has_anomaly`, `max_anomaly_score`, `avg_anomaly_score`, counts, fps/resolution, `result_details` (JSON)
  - Error + lifecycle: `error_message`, `status`, `created_at`, `processed_at`

---

## 3) Data Processing Flow

## 3.1 Authentication and session flow
- User registers → OTP verification → login
- Backend uses DRF Token Authentication (`rest_framework.authtoken`)
- Frontend attaches token for protected endpoints

## 3.2 Model inference flow (`predictor`)
1. **Upload input image** via `/model/instance/upload` → creates `TestCase` with `test_image`.
2. **Run inference** via `/model/instance/predict` with `test_case_id` + model IDs.
3. Backend loads selected `Model` rows and runs inference in thread pool (`ThreadPoolExecutor`).
4. For each model:
   - Image segmentation: loads architecture + weights, predicts mask.
   - Human detection: loads detector model, predicts detections.
   - Optional XAI generation via Grad-CAM related utilities.
5. Backend generates PDF report (`utils/generate.py`) and stores `Report` row with file.
6. Response returns per-model download URLs.

## 3.3 Pipeline flow (`PredictPipeline`)
- Runs selected models **sequentially** (output of one stage becomes next stage input).
- Produces one final report tied to last model output.

## 3.4 Container creation/update/run flow

### A) Container creation (preferred async path)
- API: `/model/container-bg/`
- Creates `Task(status=Pending)`
- Spawns background process `bgprocessing/create_container_bg.py`
- Worker actions:
  1. Collect source from zip OR GitHub folder
  2. Validate required files (`inference.py`, `requirements.txt`, `model.pth`, `Dockerfile`)
  3. Build docker image `user_<container_name>:latest`
  4. Persist `Container`; if GitHub source, persist `ContainerGithub` with folder hash
  5. Update task status/logs

### B) Container update from GitHub
- API: `/model/container-update/`
- Spawns `bgprocessing/update_container_github_bg.py`
- Pulls changed files, then:
  - full `docker build` if Dockerfile changed
  - otherwise patches running temp container (`docker cp` + optional `pip install`) and commits image
- Updates stored `folder_hash`

### C) Container run
- API: `/model/run-container/`
- Saves input file, runs docker image with mounted input/output volumes
- Reads outputs (`results.csv`, output video), optionally transcodes video with ffmpeg
- Streams output via `/model/outputs/<job_id>/<filename>` (range-enabled)

### D) RTSP container anomaly flow
- API: `/model/tasks/rtsp/start/`
- Creates `Task` + spawns `bgprocessing/rtsp_container_bg.py`
- Worker runs container inference against RTSP URL, parses stdout anomaly patterns
- Captures pre/post anomaly frames and stores `ContainerAnomaly` clips

## 3.5 STEAD video and RTSP processing flow

### Uploaded video
1. Upload video in STEAD endpoint
2. Run STEAD inference (`stead_model/inference.py`) on clips of 16 frames
3. Produce annotated output video, anomaly metadata
4. Post-process for playback: web MP4 conversion + HLS playlist + thumbnail (`video_streaming.py`)
5. Save all metadata in `VideoUpload`

### RTSP live
- RTSP processors buffer frames and periodically run STEAD inference on frame windows.
- Job and anomaly state tracked through `RTSPJob` and `AnomalyDetection`.
- Live endpoints expose status/control/list/stream/HLS/anomaly clips.

---

## 4) How Models/Containers Are Created, Stored, and Process Output

## 4.1 Models
- **Created** via `CreateModelView` / `UploadModelView`
  - Supports multipart, base64, and URL download (GitHub raw links etc.)
- **Stored** in `Model` DB row + model artifact file in media storage
- **Processed** during predict endpoints using model type specific loaders/inference
- **Output artifacts**:
  - model output image (`MEDIA_ROOT/model_output/...`)
  - report PDF (`Report.report_file`)
  - optional XAI visualization in report

## 4.2 Containers
- **Created** either direct sync endpoint (`CreateContainer`) or async task endpoint (`ContainerBGView`)
- **Stored** as:
  - docker image (`user_<name>:latest`) in Docker daemon
  - metadata in `Container`
  - optional GitHub linkage in `ContainerGithub`
- **Processed outputs** by mounted host volume exchange (`/app/inputs`, `/app/outputs`) and returned as file URLs
- **Task observability** through `Task` model + log files under media logs

---

## 5) Current Optimizations Present
- Thread-based parallel model execution in `PredictView`.
- Caching GitHub model listing in `GithubIntegration` (`django.core.cache`).
- Streaming responses with byte-range support for video.
- Background subprocesses for long-running container operations.
- Singleton-like pattern for STEAD model loading to avoid repeated model initialization.

---

## 6) Optimization Opportunities (Current Codebase)

## 6.1 Architecture and scalability
1. **Move long-running jobs to a task queue** (Celery/RQ + Redis) instead of ad-hoc subprocesses.
2. **Separate inference workers** from API workers (CPU/GPU worker pools).
3. **Use PostgreSQL in production**; SQLite is not ideal for concurrent task-heavy workloads.

## 6.2 Data model and query optimization
1. Replace frequent `JSONField` access-control fields (`allowed_users`, `allowed_models`) with relational tables for queryability.
2. Add DB indexes on high-frequency filters (`Task.status`, `Task.start_time`, `Report.created_at`, `RTSPJob.status`).
3. Add explicit soft-delete or retention policies for reports/videos/clips to control storage growth.

## 6.3 Container pipeline hardening
1. Avoid broad process termination patterns; track and stop only known process IDs.
2. Add strict input validation/sanitization for uploaded zips and GitHub paths.
3. Add image build cache policy and immutable image tags (versioned tags + latest pointer).
4. Persist task logs in DB or object storage with rotation policy.

## 6.4 Inference performance
1. Add model registry cache/preload for hot models.
2. Use batched inference where possible for multi-image workflows.
3. Add GPU-awareness and worker scheduling to prevent overcommit.
4. Avoid repeated conversion/encoding passes for unchanged output videos.

## 6.5 API and reliability
1. Standardize endpoint naming and remove duplicate route patterns.
2. Introduce versioned APIs (`/api/v1/...`) consistently.
3. Add request/response schema contracts and stronger validation.
4. Add retry/backoff/circuit breaker on GitHub/FFmpeg/docker external calls.

## 6.6 Security
1. Disable `DEBUG=True` and harden production settings.
2. Enforce strict auth on report/image endpoints currently marked `AllowAny` where needed.
3. Strengthen OTP implementation (current `send_otp` stub returns static value).
4. Add upload size/type/content checks and malware-safe handling for container uploads.

---

## 7) “Optimal Way” to Operate This Application Going Forward

1. **Split services** into API, async worker, scheduler, and media/object storage.
2. **Adopt task queue orchestration** for model inference + container build/update + RTSP processing.
3. **Use PostgreSQL + Redis + object storage** (e.g., S3-compatible) for robust production operation.
4. **Introduce model/container registry lifecycle** with versioning, metadata, and rollback.
5. **Unify reporting/streaming pipelines** with standardized artifact management and retention.
6. **Add full observability**: structured logs, metrics, traces, and task dashboards.
7. **Harden security/compliance**: strict RBAC, input validation, secrets management, signed download URLs.
8. **Establish CI quality gates**: lint/test/type/security scans with migration checks before deploy.

---

## 8) Quick Summary
- Predict-Xplore is a Django + React platform for model testing, explainability, report generation, container-based inference, and STEAD-based anomaly detection.
- Persistence is fully Django ORM-based, currently SQLite-centric.
- Core outputs are reports, model output images, anomaly clips, and web-streamable videos.
- The system already has useful async and streaming capabilities, but would benefit significantly from queue-based orchestration, relational normalization, stronger security, and production-grade infrastructure patterns.
