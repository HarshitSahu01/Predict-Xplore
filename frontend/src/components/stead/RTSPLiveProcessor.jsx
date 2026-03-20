/**
 * RTSP Live Processor Component
 * 
 * Main component for RTSP live anomaly detection.
 * Features:
 * - Start/Stop RTSP live processing
 * - Real-time status monitoring
 * - Output video playback
 * - Anomaly detection results
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { toast } from 'react-toastify';
import {
  startRTSPLive,
  startTestSimulation,
  getRTSPLiveStatus,
  stopRTSPLive,
  controlRTSPLive,
  listRTSPLiveJobs,
  checkFFmpegStatus,
  getRTSPLiveStreamUrl,
  getAnomalyClipUrl
} from '../../services/steadApi';
import {
  setModelStatus,
  setFFmpegStatus,
  setLoading,
  setError,
  addLiveJob,
  updateLiveJob,
  setCurrentJob,
  clearCurrentJob,
  setLiveJobs
} from '../../redux/reducers/steadSlice';

const RTSPLiveProcessor = () => {
  const dispatch = useDispatch();
  const user = useSelector((state) => state.user.users[state.user.users.length - 1]);
  const { modelStatus, ffmpegStatus, currentJob, liveJobs, loading, error } = useSelector((state) => state.stead);

  // Form state
  const [streamUrl, setStreamUrl] = useState('');
  const [fps, setFps] = useState(15);
  const [threshold, setThreshold] = useState(0.7);

  // Processing state
  const [isProcessing, setIsProcessing] = useState(false);
  const [jobStatus, setJobStatus] = useState(null);
  const [completedResult, setCompletedResult] = useState(null);

  // Polling interval
  const pollingRef = useRef(null);

  // Check statuses on mount
  useEffect(() => {
    if (user?.token) {
      fetchStatuses();
      fetchJobs();
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, [user?.token]);

  const fetchStatuses = async () => {
    try {
      const [modelRes, ffmpegRes] = await Promise.all([
        checkModelStatus(user.token),
        checkFFmpegStatus(user.token)
      ]);
      dispatch(setModelStatus(modelRes));
      dispatch(setFFmpegStatus(ffmpegRes));
    } catch (err) {
      console.error('Error fetching statuses:', err);
    }
  };

  const fetchJobs = async () => {
    try {
      const res = await listRTSPLiveJobs(user.token);
      dispatch(setLiveJobs(res));
    } catch (err) {
      console.error('Error fetching jobs:', err);
    }
  };

  // Start processing
  const handleStartProcessing = async () => {
    if (!user?.token) {
      toast.error('Please login first');
      return;
    }

    dispatch(setLoading(true));
    dispatch(setError(null));
    setCompletedResult(null);

    try {
      let response;

      // Use RTSP URL
      if (!streamUrl.trim()) {
        toast.error('Please enter a stream URL');
        dispatch(setLoading(false));
        return;
      }

      response = await startRTSPLive(user.token, streamUrl, {
        fps,
        threshold
      });

      if (response.success) {
        dispatch(addLiveJob(response));
        setIsProcessing(true);
        toast.success('Processing started!');

        // Start polling for status
        startStatusPolling(response.job_id);
      } else {
        toast.error(response.error || 'Failed to start processing');
      }
    } catch (err) {
      const errorMsg = err.response?.data?.error || err.message;
      toast.error(errorMsg);
      dispatch(setError(errorMsg));
    } finally {
      dispatch(setLoading(false));
    }
  };

  // Start polling for job status
  const startStatusPolling = useCallback((jobId) => {
    // Clear existing interval
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
    }

    // Poll immediately
    pollJobStatus(jobId);

    // Then poll every 2 seconds
    pollingRef.current = setInterval(() => {
      pollJobStatus(jobId);
    }, 2000);
  }, [user?.token]);

  const pollJobStatus = async (jobId) => {
    try {
      const status = await getRTSPLiveStatus(user.token, jobId);
      setJobStatus(status);
      dispatch(updateLiveJob({ jobId, data: status }));

      // Check if job has completed
      if (!status.is_running && status.stats?.status === 'stopped') {
        // Job completed
        setIsProcessing(false);
        clearInterval(pollingRef.current);
        pollingRef.current = null;

        // Fetch final results
        handleStopProcessing(jobId, true);
      }
    } catch (err) {
      console.error('Error polling status:', err);
    }
  };

  // Stop processing
  const handleStopProcessing = async (jobId = null, autoStopped = false) => {
    const targetJobId = jobId || currentJob?.job_id || jobStatus?.job_id;

    if (!targetJobId) {
      toast.error('No active job to stop');
      return;
    }

    try {
      const response = await stopRTSPLive(user.token, targetJobId);

      if (response.success) {
        setCompletedResult(response);
        setIsProcessing(false);
        dispatch(clearCurrentJob());

        if (!autoStopped) {
          toast.success('Processing stopped!');
        } else {
          toast.info('Processing completed!');
        }
      } else {
        toast.error(response.error || 'Failed to stop processing');
      }
    } catch (err) {
      const errorMsg = err.response?.data?.error || err.message;
      toast.error(errorMsg);
    } finally {
      // Stop polling
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    }
  };

  // Pause/Resume
  const handlePauseResume = async () => {
    const jobId = currentJob?.job_id || jobStatus?.job_id;
    if (!jobId) return;

    const action = jobStatus?.is_paused ? 'resume' : 'pause';

    try {
      await controlRTSPLive(user.token, jobId, action);
      toast.success(`Processing ${action}d`);
    } catch (err) {
      toast.error(err.response?.data?.error || err.message);
    }
  };

  // Format time
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen bg-[#EAECFF] p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-[#123087] mb-2">
            RTSP Live Anomaly Detection
          </h1>
          <p className="text-gray-600">
            Process RTSP streams or video files with STEAD model for real-time anomaly detection
          </p>
        </div>

        {/* Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          {/* Model Status */}
          <div className={`bg-white rounded-xl p-4 shadow-sm border-l-4 ${modelStatus.status === 'ready' ? 'border-green-500' : 'border-yellow-500'
            }`}>
            <h3 className="text-sm font-medium text-gray-500 mb-1">STEAD Model</h3>
            <p className={`text-lg font-semibold ${modelStatus.status === 'ready' ? 'text-green-600' : 'text-yellow-600'
              }`}>
              {modelStatus.status === 'ready' ? 'Ready' : 'Loading...'}
            </p>
            <p className="text-xs text-gray-400 mt-1">
              Device: {modelStatus.device || 'N/A'}
            </p>
          </div>

          {/* FFmpeg Status */}
          <div className={`bg-white rounded-xl p-4 shadow-sm border-l-4 ${ffmpegStatus.available ? 'border-green-500' : 'border-red-500'
            }`}>
            <h3 className="text-sm font-medium text-gray-500 mb-1">FFmpeg</h3>
            <p className={`text-lg font-semibold ${ffmpegStatus.available ? 'text-green-600' : 'text-red-600'
              }`}>
              {ffmpegStatus.available ? 'Available' : 'Not Found'}
            </p>
            <p className="text-xs text-gray-400 mt-1 truncate">
              {ffmpegStatus.path || 'Install FFmpeg for streaming'}
            </p>
          </div>

          {/* Active Jobs */}
          <div className="bg-white rounded-xl p-4 shadow-sm border-l-4 border-blue-500">
            <h3 className="text-sm font-medium text-gray-500 mb-1">Active Jobs</h3>
            <p className="text-lg font-semibold text-blue-600">
              {liveJobs.filter(j => j.is_running).length}
            </p>
            <p className="text-xs text-gray-400 mt-1">
              Total: {liveJobs.length} jobs
            </p>
          </div>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left Panel - Configuration */}
          <div className="bg-white rounded-xl p-6 shadow-sm">
            <h2 className="text-xl font-semibold text-[#123087] mb-4">
              Configuration
            </h2>

            {/* RTSP URL Input */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Stream URL
              </label>
              <input
                type="text"
                value={streamUrl}
                onChange={(e) => setStreamUrl(e.target.value)}
                placeholder="rtsp://camera.local:554/stream or tcp://localhost:8554"
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#6966FF] focus:border-transparent"
                disabled={isProcessing}
              />
              <p className="text-xs text-gray-500 mt-1">
                Supports RTSP, TCP, UDP streams, or video file paths
              </p>
            </div>

            {/* Parameters */}
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  FPS
                </label>
                <input
                  type="number"
                  value={fps}
                  onChange={(e) => setFps(parseInt(e.target.value) || 15)}
                  min="1"
                  max="60"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#6966FF]"
                  disabled={isProcessing}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Threshold
                </label>
                <input
                  type="number"
                  value={threshold}
                  onChange={(e) => setThreshold(parseFloat(e.target.value) || 0.7)}
                  min="0"
                  max="1"
                  step="0.1"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#6966FF]"
                  disabled={isProcessing}
                />
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-4">
              {!isProcessing ? (
                <button
                  onClick={handleStartProcessing}
                  disabled={loading || !streamUrl}
                  className={`flex-1 py-3 px-6 rounded-xl font-semibold text-white transition ${loading || !streamUrl
                    ? 'bg-gray-400 cursor-not-allowed'
                    : 'bg-[#6966FF] hover:bg-[#5855DD]'
                    }`}
                >
                  {loading ? 'Starting...' : 'Start Processing'}
                </button>
              ) : (
                <>
                  <button
                    onClick={handlePauseResume}
                    className="flex-1 py-3 px-6 rounded-xl font-semibold bg-yellow-500 text-white hover:bg-yellow-600 transition"
                  >
                    {jobStatus?.is_paused ? 'Resume' : 'Pause'}
                  </button>
                  <button
                    onClick={() => handleStopProcessing()}
                    className="flex-1 py-3 px-6 rounded-xl font-semibold bg-red-500 text-white hover:bg-red-600 transition"
                  >
                    Stop
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Right Panel - Status & Results */}
          <div className="bg-white rounded-xl p-6 shadow-sm">
            <h2 className="text-xl font-semibold text-[#123087] mb-4">
              {isProcessing ? 'Live Status' : 'Results'}
            </h2>

            {/* Processing Status */}
            {isProcessing && jobStatus && (
              <div className="space-y-4">
                {/* Status Badge */}
                <div className="flex items-center justify-between">
                  <span className={`px-3 py-1 rounded-full text-sm font-medium ${jobStatus.is_paused
                    ? 'bg-yellow-100 text-yellow-800'
                    : 'bg-green-100 text-green-800'
                    }`}>
                    {jobStatus.is_paused ? 'Paused' : 'Processing'}
                  </span>
                  <span className="text-sm text-gray-500">
                    Job: {jobStatus.job_id?.slice(0, 8)}...
                  </span>
                </div>

                {/* Stats Grid */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-xs text-gray-500">Frames Processed</p>
                    <p className="text-xl font-bold text-[#123087]">
                      {jobStatus.stats?.total_frames || 0}
                    </p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-xs text-gray-500">Clips Analyzed</p>
                    <p className="text-xl font-bold text-[#123087]">
                      {jobStatus.stats?.total_clips_processed || 0}
                    </p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-xs text-gray-500">Anomalies Found</p>
                    <p className="text-xl font-bold text-red-600">
                      {jobStatus.stats?.anomalies_detected || 0}
                    </p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-xs text-gray-500">Current FPS</p>
                    <p className="text-xl font-bold text-[#123087]">
                      {jobStatus.stats?.current_fps?.toFixed(1) || 0}
                    </p>
                  </div>
                </div>

                {/* Progress Bar (Removed for continuous stream) */}
                <div className="mt-4">
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>Continuous Collection</span>
                    <span className="animate-pulse text-red-500 font-bold ml-2">● LIVE</span>
                  </div>
                </div>
              </div>
            )}

            {/* Completed Results Summary */}
            {completedResult && !isProcessing && (
              <div className="space-y-4">
                {/* Success Badge */}
                <div className="flex items-center gap-2">
                  <span className="px-3 py-1 rounded-full bg-green-100 text-green-800 text-sm font-medium">
                    Processing Complete
                  </span>
                </div>

                {/* Summary Stats */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-green-50 rounded-lg p-3">
                    <p className="text-xs text-gray-500">Total Frames</p>
                    <p className="text-xl font-bold text-green-700">
                      {completedResult.stats?.total_frames || 0}
                    </p>
                  </div>
                  <div className="bg-red-50 rounded-lg p-3">
                    <p className="text-xs text-gray-500">Anomalies Detected</p>
                    <p className="text-xl font-bold text-red-700">
                      {completedResult.stats?.anomalies_detected || 0}
                    </p>
                  </div>
                </div>

                {/* Output Video */}
                {completedResult.output?.output_video && (
                  <div className="mt-4">
                    <h3 className="text-sm font-medium text-gray-700 mb-2">
                      Output Video
                    </h3>
                    <video
                      controls
                      className="w-full rounded-lg bg-black"
                      src={`${getRTSPLiveStreamUrl(completedResult.job_id)}?token=${user.token}`}
                    >
                      Your browser does not support video playback.
                    </video>

                    {/* Download Button */}
                    <a
                      href={completedResult.streaming_urls?.output_video}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 inline-flex items-center gap-2 px-4 py-2 bg-[#6966FF] text-white rounded-lg hover:bg-[#5855DD] transition"
                    >
                      Download Full Session Recording
                    </a>
                  </div>
                )}
              </div>
            )}

            {/* Shared Anomaly List (shown during live and after complete) */}
            {((isProcessing && jobStatus?.stats?.anomaly_clips?.length > 0) ||
              (!isProcessing && completedResult?.stats?.anomaly_clips?.length > 0)) && (
                <div className="mt-8">
                  <h3 className="text-sm font-medium text-gray-700 mb-2">
                    Detected Anomalies
                  </h3>
                  <div className="max-h-96 overflow-y-auto space-y-4 pr-2">
                    {((isProcessing ? jobStatus.stats : completedResult.stats).anomaly_clips).map((clip, idx) => (
                      <div
                        key={idx}
                        className="flex flex-col bg-red-50 rounded-lg p-3 border border-red-100"
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div>
                            <p className="text-sm font-medium text-red-800 flex items-center gap-2">
                              Anomaly #{idx + 1}
                              <span className="text-xs bg-red-200 text-red-800 px-2 py-0.5 rounded-full">
                                Score: {(clip.anomaly_score * 100).toFixed(1)}%
                              </span>
                            </p>
                            <p className="text-xs text-gray-500 mt-1">
                              Frames {clip.frame_start} - {clip.frame_end}
                            </p>
                          </div>
                        </div>

                        {clip.video_path ? (
                          <div className="mt-2 text-center">
                            <video
                              controls
                              preload="metadata"
                              className="w-full rounded-lg bg-black object-contain max-h-[300px]"
                              src={`${getAnomalyClipUrl(clip.video_path)}?token=${user.token}`}
                            >
                              Your browser does not support video playback.
                            </video>
                            <a
                              href={`${getAnomalyClipUrl(clip.video_path)}?token=${user.token}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="mt-2 text-xs text-blue-600 hover:text-blue-800 inline-block align-right"
                            >
                              Download Clip
                            </a>
                          </div>
                        ) : (
                          <p className="text-xs text-gray-400 mt-1 italic w-full text-center">
                            Clip extraction unavailable or processing...
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

            {/* Empty State */}
            {!isProcessing && !completedResult && (
              <div className="text-center py-12">
                <div className="w-16 h-16 mx-auto bg-gray-100 rounded-full flex items-center justify-center mb-4">
                  <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                </div>
                <p className="text-gray-500">
                  Configure settings and start processing to see results
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Previous Jobs */}
        {liveJobs.length > 0 && (
          <div className="mt-8 bg-white rounded-xl p-6 shadow-sm">
            <h2 className="text-xl font-semibold text-[#123087] mb-4">
              Previous Jobs
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-left text-sm text-gray-500 border-b">
                    <th className="pb-3 pr-4">Job ID</th>
                    <th className="pb-3 pr-4">Status</th>
                    <th className="pb-3 pr-4">Frames</th>
                    <th className="pb-3 pr-4">Anomalies</th>
                    <th className="pb-3 pr-4">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {liveJobs.slice(0, 10).map((job) => (
                    <tr key={job.job_id} className="border-b last:border-0">
                      <td className="py-3 pr-4 font-mono text-sm">
                        {job.job_id?.slice(0, 12)}...
                      </td>
                      <td className="py-3 pr-4">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${job.is_running
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-800'
                          }`}>
                          {job.is_running ? 'Running' : job.stats?.status || 'Stopped'}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-sm">
                        {job.stats?.total_frames || 0}
                      </td>
                      <td className="py-3 pr-4 text-sm text-red-600 font-medium">
                        {job.stats?.anomalies_detected || 0}
                      </td>
                      <td className="py-3 pr-4">
                        {!job.is_running && job.output_video && (
                          <button
                            onClick={() => setCompletedResult(job)}
                            className="text-[#6966FF] text-sm hover:underline"
                          >
                            View Results
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default RTSPLiveProcessor;
