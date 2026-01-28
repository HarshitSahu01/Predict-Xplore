import React, { useEffect, useState } from 'react';
import axios from 'axios';

const GithubModelPicker = ({ modelClosed }) => {
    const [models, setModels] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        axios.get('http://127.0.0.1:8000/model/github-integration/')
            .then(response => {
                setModels(response.data);
                setLoading(false);
            })
            .catch(err => {
                console.error("Error fetching github models:", err);
                setError("Failed to fetch models");
                setLoading(false);
            });
    }, []);

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center backdrop-blur-sm">
            <div className="bg-white rounded-2xl w-[95%] md:w-[400px] max-h-[80vh] flex flex-col p-6 relative shadow-2xl animate-fade-in-up">
                {/* Close Button */}
                <button
                    onClick={() => modelClosed()}
                    className="absolute top-4 right-4 text-gray-400 hover:text-gray-800 text-2xl font-bold transition-colors"
                >
                    &times;
                </button>

                <h2 className="text-xl font-bold mb-4 text-gray-800 border-b pb-3">Select Model from GitHub</h2>

                {loading ? (
                    <div className="flex-1 flex flex-col items-center justify-center py-10">
                        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600 mb-3"></div>
                        <p className="text-sm text-gray-500">Fetching models...</p>
                    </div>
                ) : error ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-red-500 py-8">
                        <p>{error}</p>
                        <button onClick={() => modelClosed()} className="mt-4 text-indigo-600 hover:underline">Cancel</button>
                    </div>
                ) : (
                    <div className="flex-1 overflow-y-auto custom-scrollbar pr-1 -mr-2">
                        {models.length === 0 ? (
                            <p className="text-center text-gray-500 py-8">No models found in the repository.</p>
                        ) : (
                            <div className="space-y-3 pb-2">
                                {models.map((model, index) => (
                                    <div
                                        key={index}
                                        onClick={() => modelClosed(model.download_url)}
                                        className="p-3 border border-gray-200 rounded-lg hover:bg-indigo-50 hover:border-indigo-300 cursor-pointer transition-all duration-200 group flex flex-col items-start"
                                    >
                                        <p className="font-semibold text-gray-700 text-sm break-all group-hover:text-indigo-700">
                                            {model.name}
                                        </p>
                                        <div className="flex justify-between w-full items-center mt-2">
                                            <span className="text-[10px] uppercase font-bold text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                                                {(model.size / (1024 * 1024)).toFixed(2)} MB
                                            </span>
                                            <span className="text-indigo-600 text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                                                Select &rarr;
                                            </span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>
            <style>{`
                .animate-fade-in-up {
                    animation: fadeInUp 0.3s ease-out forwards;
                }
                @keyframes fadeInUp {
                    from { opacity: 0; transform: translateY(20px); }
                    to { opacity: 1; transform: translateY(0); }
                }
            `}</style>
        </div>
    );
};

export default GithubModelPicker;