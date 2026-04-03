import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { getRTSPContainerJobDetails, getContainerAnomalyClipUrl, stopRTSPContainerJob } from '../../services/steadApi';
import { toast } from 'react-toastify';

const AdminRTSPTaskDetail = () => {
    const { taskId } = useParams();
    const navigate = useNavigate();
    const user = useSelector((state) => state.user.users[state.user.users.length - 1]);
    const [task, setTask] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (user?.token && taskId) {
            fetchDetails();
        }
    }, [user, taskId]);

    const fetchDetails = async () => {
        try {
            const data = await getRTSPContainerJobDetails(user.token, taskId);
            setTask(data);
        } catch (err) {
            toast.error('Failed to load task details');
            navigate('/admin/rtsp');
        } finally {
            setLoading(false);
        }
    };

    const handleStop = async () => {
        try {
            await stopRTSPContainerJob(user.token, taskId);
            toast.success('Task stopped');
            fetchDetails();
        } catch (err) {
            toast.error('Failed to stop task');
        }
    };

    if (loading) return <div className="p-8 text-center text-gray-500">Loading details...</div>;
    if (!task) return null;

    return (
        <div className="min-h-screen bg-[#EAECFF] p-6">
            <div className="max-w-6xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex justify-between items-center bg-white p-6 rounded-xl shadow-sm">
                    <div>
                        <button onClick={() => navigate('/admin/rtsp')} className="text-sm text-blue-600 hover:underline mb-2">
                            &larr; Back to RTSP
                        </button>
                        <h1 className="text-2xl font-bold text-[#123087]">
                            Task: {task.task_name}
                        </h1>
                        <p className="text-gray-500 text-sm mt-1">
                            Job ID: <span className="font-mono">{task.job_id}</span>
                        </p>
                    </div>
                    <div>
                        <span className={`px-4 py-2 rounded-full text-sm font-semibold ${task.is_running ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                            }`}>
                            Status: {task.is_running ? 'Running' : task.status}
                        </span>
                        {task.is_running && (
                            <button onClick={handleStop} className="ml-4 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition">
                                Stop Task
                            </button>
                        )}
                    </div>
                </div>

                {/* Runtime info */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-white p-4 rounded-xl shadow-sm">
                        <p className="text-xs text-gray-500 uppercase font-bold">Container</p>
                        <p className="text-lg font-semibold text-[#123087] mt-1">{task.container_name || 'N/A'}</p>
                    </div>
                    <div className="bg-white p-4 rounded-xl shadow-sm">
                        <p className="text-xs text-gray-500 uppercase font-bold">RTSP URL</p>
                        <p className="text-sm font-semibold text-gray-700 mt-1 truncate" title={task.rtsp_url}>
                            {task.rtsp_url}
                        </p>
                    </div>
                    <div className="bg-white p-4 rounded-xl shadow-sm">
                        <p className="text-xs text-gray-500 uppercase font-bold">Started At</p>
                        <p className="text-sm font-semibold text-gray-700 mt-1">
                            {new Date(task.start_time).toLocaleString()}
                        </p>
                    </div>
                    <div className="bg-white p-4 rounded-xl shadow-sm">
                        <p className="text-xs text-gray-500 uppercase font-bold">Ended At</p>
                        <p className="text-sm font-semibold text-gray-700 mt-1">
                            {task.end_time ? new Date(task.end_time).toLocaleString() : '-'}
                        </p>
                    </div>
                </div>

                {/* Anomaly Clips */}
                <div className="bg-white p-6 rounded-xl shadow-sm">
                    <h2 className="text-xl font-semibold text-[#123087] mb-4">
                        Detected Anomalies ({task.stats.anomalies_detected})
                    </h2>
                    {task.stats.anomaly_clips && task.stats.anomaly_clips.length > 0 ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            {task.stats.anomaly_clips.map((clip, idx) => (
                                <div key={idx} className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                                    <div className="flex justify-between items-start mb-3">
                                        <div>
                                            <h3 className="font-semibold text-red-700 text-lg">
                                                {clip.label}
                                            </h3>
                                            <p className="text-xs text-gray-500">
                                                {new Date(clip.timestamp).toLocaleString()}
                                            </p>
                                        </div>
                                        {clip.confidence && (
                                            <span className="bg-red-100 text-red-800 text-xs font-bold px-2 py-1 rounded">
                                                Score: {(clip.confidence * 100).toFixed(1)}%
                                            </span>
                                        )}
                                    </div>
                                    {clip.video_path ? (
                                        <div className="mt-2 text-center rounded bg-black flex justify-center items-center overflow-hidden h-48">
                                            <video
                                                controls
                                                className="max-h-full w-auto max-w-full"
                                                src={getContainerAnomalyClipUrl(clip.video_path)}
                                            >
                                                Your browser does not support video playback.
                                            </video>
                                        </div>
                                    ) : (
                                        <div className="mt-2 h-48 bg-gray-200 flex items-center justify-center text-gray-500 italic rounded">
                                            Video unavaiable or still processing
                                        </div>
                                    )}
                                    <div className="mt-4 flex justify-end">
                                        {clip.video_path && (
                                            <a
                                                href={getContainerAnomalyClipUrl(clip.video_path)}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-xs font-medium text-blue-600 hover:text-blue-800 transition"
                                            >
                                                Download Clip
                                            </a>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="text-center py-10 bg-gray-50 rounded-lg text-gray-500">
                            No anomalies detected yet.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default AdminRTSPTaskDetail;
