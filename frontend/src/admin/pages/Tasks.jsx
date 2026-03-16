import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useSelector } from 'react-redux';
import { Link } from 'react-router-dom';
import { FiRefreshCw } from 'react-icons/fi';
import AdminNavbar from '../../components/AdminNavbar';

const Tasks = () => {
    const [tasks, setTasks] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    // Retrieve auth token from state
    const user = useSelector((state) => state.user.users[state.user.users.length - 1]);
    const token = user?.token;

    const fetchTasks = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await axios.get("http://127.0.0.1:8000/model/tasks/", {
                headers: {
                    Authorization: `Token ${token}`
                }
            });
            setTasks(response.data);
        } catch (err) {
            setError("Failed to fetch tasks");
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (token) {
            fetchTasks();
        }
    }, [token]);

    const killTask = async (taskId) => {
        if (!window.confirm("Are you sure you want to kill this task?")) return;

        try {
            await axios.delete("http://127.0.0.1:8000/model/container-bg/", {
                headers: {
                    Authorization: `Token ${token}`
                },
                data: { task_id: taskId }
            });
            fetchTasks();
        } catch (err) {
            console.error(err);
            alert("Failed to kill task: " + (err.response?.data?.error || err.response?.data?.detail || err.message));
        }
    };

    // Determine status color styling
    const getStatusColor = (status) => {
        switch (status) {
            case 'Completed': return 'text-green-600 bg-green-100';
            case 'Running': return 'text-blue-600 bg-blue-100';
            case 'Failed': return 'text-red-600 bg-red-100';
            case 'Pending': return 'text-yellow-600 bg-yellow-100';
            default: return 'text-gray-600 bg-gray-100';
        }
    };

    return (
        <div className="h-screen w-screen bg-[#EAECFF] overflow-auto">
            <AdminNavbar />
            <div className="flex flex-col mx-20 mt-6">
                <main className="flex-1 p-6 overflow-y-auto">
                    <div className="bg-white rounded-2xl shadow-md overflow-hidden">
                        {/* Header */}
                        <div className="p-6 border-b border-gray-200 flex justify-between items-center bg-[#EAECFF]">
                            <h1 className="text-3xl font-bold text-[#39407D]">Background Tasks</h1>
                            <button
                                onClick={fetchTasks}
                                disabled={loading}
                                className="flex items-center gap-2 bg-[#39407D] hover:bg-purple-700 text-white px-4 py-2 rounded-md transition-colors shadow-sm disabled:opacity-50"
                            >
                                <FiRefreshCw className={loading ? "animate-spin" : ""} />
                                {loading ? "Refreshing..." : "Refresh Status"}
                            </button>
                        </div>

                        {/* Error message */}
                        {error && (
                            <div className="p-4 bg-red-50 text-red-600 border-b border-red-200">
                                {error}
                            </div>
                        )}

                        {/* Tasks Table */}
                        <div className="overflow-x-auto">
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="bg-gray-50 text-gray-600 text-sm uppercase tracking-wider border-b border-gray-200">
                                        <th className="p-4 font-semibold">Task ID</th>
                                        <th className="p-4 font-semibold">Task Name</th>
                                        <th className="p-4 font-semibold">User</th>
                                        <th className="p-4 font-semibold">PID</th>
                                        <th className="p-4 font-semibold">Status</th>
                                        <th className="p-4 font-semibold">Start Time</th>
                                        <th className="p-4 font-semibold">End Time</th>
                                        <th className="p-4 font-semibold">Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-200">
                                    {tasks.length === 0 && !loading ? (
                                        <tr>
                                            <td colSpan="7" className="p-8 text-center text-gray-500 italic">
                                                No background tasks found.
                                            </td>
                                        </tr>
                                    ) : (
                                        tasks.map((task) => (
                                            <tr key={task.task_id} className="hover:bg-gray-50 transition-colors">
                                                <td className="p-4 text-xs font-mono" title={task.task_id}>
                                                    {task.log_file ? (
                                                        <Link to={`/admin/tasks/${task.task_id}/logs`} className="text-blue-600 hover:text-blue-800 hover:underline">
                                                            {task.task_id.substring(0, 8)}...
                                                        </Link>
                                                    ) : (
                                                        <span className="text-gray-500">{task.task_id.substring(0, 8)}...</span>
                                                    )}
                                                </td>
                                                <td className="p-4 text-sm font-medium text-gray-800">{task.task_name}</td>
                                                <td className="p-4 text-sm text-gray-600">{task.user}</td>
                                                <td className="p-4 text-sm font-mono text-gray-500">{task.subprocess_id || '-'}</td>
                                                <td className="p-4">
                                                    <span className={`px-3 py-1 text-xs font-semibold rounded-full ${getStatusColor(task.status)}`}>
                                                        {task.status}
                                                    </span>
                                                </td>
                                                <td className="p-4 text-sm text-gray-600">
                                                    {task.start_time ? new Date(task.start_time).toLocaleString() : '-'}
                                                </td>
                                                <td className="p-4 text-sm text-gray-600">
                                                    {task.end_time ? new Date(task.end_time).toLocaleString() : '-'}
                                                </td>
                                                <td className="p-4">
                                                    {(task.status === 'Pending' || task.status === 'Running') && (
                                                        <button
                                                            onClick={() => killTask(task.task_id)}
                                                            className="px-3 py-1 text-xs font-semibold rounded-md bg-red-500 text-white hover:bg-red-600 transition-colors"
                                                        >
                                                            Kill
                                                        </button>
                                                    )}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </main>
            </div>
        </div>
    );
};

export default Tasks;
