import React from "react";
import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ProjectsList } from "./pages/ProjectsList";
import { ProjectDetail } from "./pages/ProjectDetail";
import { TestCaseDetail } from "./pages/TestCaseDetail";
import { RunDetail } from "./pages/RunDetail";
import { BatchDetail } from "./pages/BatchDetail";
import { RunsHistory } from "./pages/RunsHistory";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<ProjectsList />} />
        <Route path="projects/:id" element={<ProjectDetail />} />
        <Route path="test-cases/:id" element={<TestCaseDetail />} />
        <Route path="runs/:id" element={<RunDetail />} />
        <Route path="sequences/:id" element={<BatchDetail />} />
        <Route path="history" element={<RunsHistory />} />
      </Route>
    </Routes>
  );
}

export default App;
