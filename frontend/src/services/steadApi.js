/**
 * STEAD API Service
 * 
 * Provides all API calls for STEAD anomaly detection features.
 * Base URL: http://127.0.0.1:8000/api/stead/
 */

import axios from 'axios';

const BASE_URL = 'http://127.0.0.1:8000/api/stead';

/**
 * Get the authorization header with token
 */
const getAuthHeader = (token) => ({
  'Content-Type': 'application/json',
  'Authorization': `Token ${token}`
});

const PREDICTOR_BASE_URL = 'http://127.0.0.1:8000/api/predictor';

/**
 * Get multipart form header for file uploads
 */
const getMultipartHeader = (token) => ({
  'Content-Type': 'multipart/form-data',
  'Authorization': `Token ${token}`
});

// ============= Model Status =============

/**
 * Check STEAD model status
 * GET /api/stead/status/
 */
export const checkModelStatus = async (token) => {
  const response = await axios.get(`${BASE_URL}/status/`, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

/**
 * Check FFmpeg availability
 * GET /api/stead/ffmpeg/status/
 */
export const checkFFmpegStatus = async (token) => {
  const response = await axios.get(`${BASE_URL}/ffmpeg/status/`, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

// ============= Video Upload =============

/**
 * Upload video for anomaly detection
 * POST /api/stead/video/upload/
 */
export const uploadVideo = async (token, videoFile, threshold = 0.7, onProgress = null) => {
  const formData = new FormData();
  formData.append('video', videoFile);
  formData.append('threshold', threshold);

  const config = {
    headers: getMultipartHeader(token),
    onUploadProgress: onProgress ? (progressEvent) => {
      const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
      onProgress(percentCompleted);
    } : undefined
  };

  const response = await axios.post(`${BASE_URL}/video/upload/`, formData, config);
  return response.data;
};

/**
 * Get video upload history
 * GET /api/stead/video/history/
 */
export const getVideoHistory = async (token) => {
  const response = await axios.get(`${BASE_URL}/video/history/`, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

/**
 * Get video upload details
 * GET /api/stead/video/<uuid>/
 */
export const getVideoDetails = async (token, uploadId) => {
  const response = await axios.get(`${BASE_URL}/video/${uploadId}/`, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

/**
 * Delete video upload
 * DELETE /api/stead/video/<uuid>/
 */
export const deleteVideo = async (token, uploadId) => {
  const response = await axios.delete(`${BASE_URL}/video/${uploadId}/`, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

// ============= RTSP Live Processing =============

/**
 * Start RTSP live processing
 * POST /api/stead/rtsp/live/start/
 */
export const startRTSPLive = async (token, streamUrl, options = {}) => {
  const data = {
    stream_url: streamUrl,
    fps: options.fps || 15,
    threshold: options.threshold || 0.7
  };

  const response = await axios.post(`${BASE_URL}/rtsp/live/start/`, data, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

/**
 * Start RTSP test simulation (uses local video file)
 * POST /api/stead/rtsp/test/simulate/
 */
export const startTestSimulation = async (token, options = {}) => {
  const data = {
    video_path: options.videoPath || null,
    fps: options.fps || 15,
    threshold: options.threshold || 0.7
  };

  const response = await axios.post(`${BASE_URL}/rtsp/test/simulate/`, data, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

/**
 * Get RTSP live job status
 * GET /api/stead/rtsp/live/<job_id>/status/
 */
export const getRTSPLiveStatus = async (token, jobId) => {
  const response = await axios.get(`${BASE_URL}/rtsp/live/${jobId}/status/`, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

/**
 * Stop RTSP live processing
 * POST /api/stead/rtsp/live/<job_id>/stop/
 */
export const stopRTSPLive = async (token, jobId) => {
  const response = await axios.post(`${BASE_URL}/rtsp/live/${jobId}/stop/`, {}, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

/**
 * Control RTSP live job (pause/resume)
 * POST /api/stead/rtsp/live/<job_id>/control/
 */
export const controlRTSPLive = async (token, jobId, action) => {
  const response = await axios.post(`${BASE_URL}/rtsp/live/${jobId}/control/`,
    { action },
    { headers: getAuthHeader(token) }
  );
  return response.data;
};

/**
 * List all RTSP live jobs
 * GET /api/stead/rtsp/live/
 */
export const listRTSPLiveJobs = async (token) => {
  const response = await axios.get(`${BASE_URL}/rtsp/live/`, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

/**
 * Get RTSP live stream URL
 */
export const getRTSPLiveStreamUrl = (jobId) => {
  return `${BASE_URL}/rtsp/live/${jobId}/stream/`;
};

/**
 * Get RTSP live HLS URL
 */
export const getRTSPLiveHLSUrl = (jobId) => {
  return `${BASE_URL}/rtsp/live/${jobId}/hls/`;
};

/**
 * Get anomaly clip URL
 */
export const getAnomalyClipUrl = (clipPath) => {
  return `${BASE_URL}/rtsp/live/anomaly-clip/${clipPath}`;
};

// ============= RTSP Container Live Processing =============

export const getContainerList = async (token) => {
  const response = await axios.get(`${PREDICTOR_BASE_URL}/list-container/`, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

export const startRTSPContainerJob = async (token, streamUrl, containerId, fps = 15) => {
  const response = await axios.post(`${PREDICTOR_BASE_URL}/tasks/rtsp/start/`, {
    rtsp_url: streamUrl,
    container_id: containerId,
    fps: fps
  }, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

export const listRTSPContainerJobs = async (token) => {
  const response = await axios.get(`${PREDICTOR_BASE_URL}/tasks/rtsp/`, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

export const getRTSPContainerJobDetails = async (token, taskId) => {
  const response = await axios.get(`${PREDICTOR_BASE_URL}/tasks/rtsp/${taskId}/`, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

export const stopRTSPContainerJob = async (token, taskId) => {
  const response = await axios.post(`${PREDICTOR_BASE_URL}/tasks/rtsp/${taskId}/stop/`, {}, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

export const getContainerAnomalyClipUrl = (clipPath) => {
  return `http://127.0.0.1:8000/media/${clipPath}`;
};

// ============= Anomalies =============

/**
 * List anomalies
 * GET /api/stead/anomalies/
 */
export const listAnomalies = async (token, jobId = null, limit = 100) => {
  let url = `${BASE_URL}/anomalies/?limit=${limit}`;
  if (jobId) {
    url += `&job_id=${jobId}`;
  }

  const response = await axios.get(url, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

/**
 * Get anomaly details
 * GET /api/stead/anomalies/<uuid>/
 */
export const getAnomalyDetails = async (token, anomalyId) => {
  const response = await axios.get(`${BASE_URL}/anomalies/${anomalyId}/`, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

/**
 * Delete anomaly
 * DELETE /api/stead/anomalies/<uuid>/
 */
export const deleteAnomaly = async (token, anomalyId) => {
  const response = await axios.delete(`${BASE_URL}/anomalies/${anomalyId}/`, {
    headers: getAuthHeader(token)
  });
  return response.data;
};

// ============= Video Streaming URLs =============

/**
 * Get video stream URL (for video element src)
 */
export const getVideoStreamUrl = (uploadId) => {
  return `${BASE_URL}/video/${uploadId}/stream/`;
};

/**
 * Get video HLS URL
 */
export const getVideoHLSUrl = (uploadId) => {
  return `${BASE_URL}/video/${uploadId}/hls/`;
};

/**
 * Get video thumbnail URL
 */
export const getVideoThumbnailUrl = (uploadId) => {
  return `${BASE_URL}/video/${uploadId}/thumbnail/`;
};

export default {
  // Status
  checkModelStatus,
  checkFFmpegStatus,

  // Video Upload
  uploadVideo,
  getVideoHistory,
  getVideoDetails,
  deleteVideo,

  // RTSP Live
  startRTSPLive,
  startTestSimulation,
  getRTSPLiveStatus,
  stopRTSPLive,
  controlRTSPLive,
  listRTSPLiveJobs,
  getRTSPLiveStreamUrl,
  getRTSPLiveHLSUrl,
  getAnomalyClipUrl,

  // Anomalies
  listAnomalies,
  getAnomalyDetails,
  deleteAnomaly,

  getVideoStreamUrl,
  getVideoHLSUrl,
  getVideoThumbnailUrl,

  // RTSP Container
  getContainerList,
  startRTSPContainerJob,
  listRTSPContainerJobs,
  getRTSPContainerJobDetails,
  stopRTSPContainerJob,
  getContainerAnomalyClipUrl
};
