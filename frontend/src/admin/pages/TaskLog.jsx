import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { useSelector } from 'react-redux';
import { useParams, Link } from 'react-router-dom';
import { FiRefreshCw, FiArrowLeft } from 'react-icons/fi';
import AdminNavbar from '../../components/AdminNavbar';

const TaskLog = () => {
    const { taskId } = useParams();
    const [log, setLog] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const logEndRef = useRef(null);

    const user = useSelector((state) => state.user.users[state.user.users.length - 1]);
    const token = user?.token;

    const fetchLog = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await axios.get(`http://127.0.0.1:8000/model/tasks/${taskId}/logs/`, {
                headers: {
                    Authorization: `Token ${token}`
                }
            });
            setLog(response.data.log);
        } catch (err) {
            setError(err.response?.data?.log || err.response?.data?.error || "Failed to fetch log.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (token) {
            fetchLog();

            const intervalId = setInterval(() => {
                fetchLog();
            }, 10000); // 10 seconds

            return () => clearInterval(intervalId);
        }
    }, [token, taskId]);

    useEffect(() => {
        if (logEndRef.current) {
            logEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [log]);

    return (
        <div className="h-screen w-screen bg-[#EAECFF] overflow-auto">
            <AdminNavbar />
            <div className="flex flex-col mx-20 mt-6">
                <main className="flex-1 p-6 overflow-y-auto">
                    <div className="bg-white rounded-2xl shadow-md overflow-hidden flex flex-col h-[75vh]">
                        {/* Header */}
                        <div className="p-6 border-b border-gray-200 flex justify-between items-center bg-[#EAECFF]">
                            <div className="flex items-center gap-4">
                                <Link to="/admin/tasks" className="p-2 hover:bg-gray-200 rounded-full transition-colors text-gray-500">
                                    <FiArrowLeft size={24} />
                                </Link>
                                <div>
                                    <h1 className="text-2xl font-bold text-[#39407D]">Task Logs</h1>
                                    <p className="text-sm text-gray-500 font-mono mt-1">{taskId}</p>
                                </div>
                            </div>
                            <button
                                onClick={fetchLog}
                                disabled={loading}
                                className="flex items-center gap-2 bg-[#39407D] hover:bg-purple-700 text-white px-4 py-2 rounded-md transition-colors shadow-sm disabled:opacity-50"
                            >
                                <FiRefreshCw className={loading ? "animate-spin" : ""} />
                                {loading ? "Syncing..." : "Sync Logs"}
                            </button>
                        </div>

                        {/* Error message */}
                        {error && (
                            <div className="p-4 bg-red-50 text-red-600 border-b border-red-200">
                                {error}
                            </div>
                        )}

                        {/* Log Viewer */}
                        <div className="flex-grow p-4 bg-gray-900 overflow-y-auto font-mono text-sm text-green-400">
                            {log ? (
                                <pre className="whitespace-pre-wrap">{log}</pre>
                            ) : (
                                <div className="flex h-full items-center justify-center text-gray-600 italic">
                                    Awaiting logs...
                                </div>
                            )}
                            <div ref={logEndRef} />
                        </div>
                    </div>
                </main>
            </div>
        </div>
    );
};

export default TaskLog;
