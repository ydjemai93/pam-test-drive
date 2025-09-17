import React from "react";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import { LayoutWithRouter } from "@/polymet/components/layout-with-router";
import Dashboard from "@/polymet/pages/dashboard";
import CreateAgentPage from "@/polymet/pages/create-agent";
import AllAgentsPage from "@/polymet/pages/all-agents";
import CallHistoryPage from "@/polymet/pages/call-history";
import AgentDetailsPage from "@/polymet/pages/agent-details";
import PlaygroundPage from "@/polymet/pages/playground";
import LoginPage from "@/polymet/pages/login";
import FontProvider from "@/polymet/components/font-provider";
import { Toaster } from "@/polymet/components/sonner";

export default function App() {
  return (
    <FontProvider>
      <Router>
        <Toaster />
        <Routes>
          {/* Public routes */}
          <Route path="/login" element={<LoginPage />} />

          {/* Protected routes */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          <Route
            path="/dashboard"
            element={
              <LayoutWithRouter>
                <Dashboard />
              </LayoutWithRouter>
            }
          />

          <Route
            path="/create-agent"
            element={
              <LayoutWithRouter>
                <CreateAgentPage />
              </LayoutWithRouter>
            }
          />

          <Route
            path="/agents"
            element={
              <LayoutWithRouter>
                <AllAgentsPage />
              </LayoutWithRouter>
            }
          />

          <Route
            path="/agents/:agentId"
            element={
              <LayoutWithRouter>
                <AgentDetailsPage />
              </LayoutWithRouter>
            }
          />

          <Route
            path="/calls"
            element={
              <LayoutWithRouter>
                <CallHistoryPage />
              </LayoutWithRouter>
            }
          />

          <Route
            path="/playground"
            element={
              <LayoutWithRouter>
                <PlaygroundPage />
              </LayoutWithRouter>
            }
          />

          <Route
            path="/settings"
            element={
              <LayoutWithRouter>
                <Dashboard />
              </LayoutWithRouter>
            }
          />

          <Route
            path="/help"
            element={
              <LayoutWithRouter>
                <Dashboard />
              </LayoutWithRouter>
            }
          />

          <Route
            path="/docs"
            element={
              <LayoutWithRouter>
                <Dashboard />
              </LayoutWithRouter>
            }
          />
        </Routes>
      </Router>
    </FontProvider>
  );
}
