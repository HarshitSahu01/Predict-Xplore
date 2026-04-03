import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './App.css';
import Homepage from './user/Homepage';
import Modeltestpage from './user/Modeltestpage';
import Modeltestrunpage from './user/Modeltestrunpage';
import Reportpage from './user/Reportpage';
import Login from './components/Login';
import OTP from './components/OTP';
import Register from './components/Register';
import CreateModel from './admin/pages/CreateModel';
import AdminModelTest from './admin/pages/AdminModelTest';
import CreatePipeline from './admin/pages/CreatePipeline';
import ModelProceed from './admin/pages/ModelProceed';
import AdminDashboard from './admin/pages/AdminDashboard';
import AdminReport from './admin/pages/AdminReport';
import AdminModelList from './admin/pages/AdminModelList';
import Containers from './admin/pages/Containers';
import { ToastContainer, Slide } from 'react-toastify';
import ManageUser from './admin/pages/ManageUser';
import ContainerTestRun from './components/ContainerTestRun';
import Tasks from './admin/pages/Tasks';
import TaskLog from './admin/pages/TaskLog';
import ProtectedRoute from './components/ProtectedRoute';
import LandingRoute from './components/LandingRoute';

// STEAD Anomaly Detection Pages
import STEADDashboard from './user/STEADDashboard';
import RTSPLivePage from './user/RTSPLivePage';
import VideoUploadPage from './user/VideoUploadPage';

// Admin STEAD Pages
import AdminSTEADDashboard from './admin/pages/AdminSTEADDashboard';
import AdminRTSPLivePage from './admin/pages/AdminRTSPLivePage';
import AdminVideoUploadPage from './admin/pages/AdminVideoUploadPage';
import AdminRTSPTaskDetail from './components/stead/AdminRTSPTaskDetail';

function App() {
  return (
    <div>
      <ToastContainer position="top-left" transition={Slide} className="mt-10" />
      <Router>
        <Routes>
          <Route path='/' element={<LandingRoute><Register role="user" /></LandingRoute>} />
          {/* login part */}
          <Route path="/login" element={<LandingRoute><Login /></LandingRoute>} />
          <Route path="/otp" element={<LandingRoute><OTP /></LandingRoute>} />
          <Route path="/user/register" element={<LandingRoute><Register role="user" /></LandingRoute>} />
          <Route path="/admin/register" element={<LandingRoute><Register role="admin" /></LandingRoute>} />
          {/* login part end */}
          <Route path="/home" element={<Homepage />} />
          <Route path="/model-test" element={<Modeltestpage />} />
          <Route path="/model-test-run" element={<Modeltestrunpage />} />
          <Route path="/reports" element={<Reportpage />} />
          <Route path="/container-test-run" element={<ContainerTestRun />} />

          {/* STEAD Anomaly Detection Routes */}
          <Route path="/stead" element={<STEADDashboard />} />
          <Route path="/stead/rtsp-live" element={<RTSPLivePage />} />
          <Route path="/stead/video-upload" element={<VideoUploadPage />} />

          {/* Admin Pages */}
          <Route path="/admin/dashboard" element={<AdminDashboard />} />
          <Route path="/admin/models" element={<AdminModelList />} />
          <Route path="/admin/containers" element={<Containers />} />
          <Route path="/admin/create-model" element={<CreateModel />} />
          <Route path="/admin/create-pipeline" element={<CreatePipeline />} />
          <Route path="/admin/reports" element={<AdminReport />} />
          <Route path="/admin/tasks" element={<ProtectedRoute><Tasks /></ProtectedRoute>} />
          <Route path="/admin/tasks/:taskId/logs" element={<ProtectedRoute><TaskLog /></ProtectedRoute>} />

          <Route path="/admin/manage-user" element={<ManageUser />} />
          <Route path="/admin/model-proceed" element={<ModelProceed />} />
          <Route path="/admin/model-test" element={<AdminModelTest />} />

          {/* Admin STEAD Anomaly Detection Routes */}
          <Route path="/admin/stead" element={<AdminSTEADDashboard />} />
          <Route path="/admin/stead/rtsp-live" element={<AdminRTSPLivePage />} />
          <Route path="/admin/rtsp/task/:taskId" element={<AdminRTSPTaskDetail />} />
          <Route path="/admin/stead/video-upload" element={<AdminVideoUploadPage />} />
        </Routes>
      </Router>
    </div>
  );
}

export default App;