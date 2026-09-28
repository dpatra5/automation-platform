import React, { useState } from "react";
import {
  useProjects,
  useCreateProject,
  useDeleteProject,
} from "../hooks/useProjects";
import { ProjectCard } from "../components/ProjectCard";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { SkeletonLoader } from "../components/SkeletonLoader";
import { EmptyState } from "../components/EmptyState";
import { Project } from "../api/types";
import { Plus, X, FolderPlus } from "lucide-react";

export const ProjectsList = () => {
  const { data: projects, isLoading, isError } = useProjects();
  const createProject = useCreateProject();
  const deleteProject = useDeleteProject();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form, setForm] = useState({ name: "", base_url: "", description: "" });
  const [doomed, setDoomed] = useState<Project | null>(null);
  const [deleteError, setDeleteError] = useState("");

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    createProject.mutate(form, {
      onSuccess: () => {
        setIsModalOpen(false);
        setForm({ name: "", base_url: "", description: "" });
      },
    });
  };

  const confirmDelete = () => {
    if (!doomed) return;
    setDeleteError("");
    deleteProject.mutate(doomed.id, {
      onSuccess: () => setDoomed(null),
      onError: (e: any) =>
        setDeleteError(
          e?.response?.data?.message || "Could not delete this project.",
        ),
    });
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap gap-4 justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">
            Projects
          </h1>
          <p className="text-sm text-ink-muted mt-1">
            Every app you regression test lives here.
          </p>
        </div>
        <button onClick={() => setIsModalOpen(true)} className="btn-primary">
          <Plus className="w-4 h-4" /> New project
        </button>
      </header>

      {isError && (
        <div className="card border-rose-100 bg-rose-50 p-4 text-sm text-rose-600">
          Could not reach the API. Is the backend running on port 8000?
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          <SkeletonLoader className="h-48" count={3} />
        </div>
      ) : projects?.length === 0 ? (
        <EmptyState
          icon={FolderPlus}
          title="No projects yet"
          description="Create a project, then add your first test case and build its steps by hand."
          action={
            <button
              onClick={() => setIsModalOpen(true)}
              className="btn-primary"
            >
              <Plus className="w-4 h-4" /> Create project
            </button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {projects?.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onDelete={setDoomed}
            />
          ))}
        </div>
      )}

      {doomed && (
        <ConfirmDialog
          title={`Delete "${doomed.name}"?`}
          body={
            <>
              Its {doomed.test_case_count || 0} test case
              {doomed.test_case_count === 1 ? "" : "s"}, every run recorded
              against them and all their evidence — screenshots, video, traces
              and logs — will be deleted from disk. This cannot be undone.
            </>
          }
          confirmLabel="Delete project"
          isBusy={deleteProject.isPending}
          error={deleteError}
          onConfirm={confirmDelete}
          onCancel={() => {
            setDoomed(null);
            setDeleteError("");
          }}
        />
      )}

      {isModalOpen && (
        <dialog
          open
          aria-label="Create project"
          className="fixed inset-0 z-50 w-full h-full max-w-none max-h-none bg-ink/40 backdrop-blur-sm p-4 flex items-center justify-center"
        >
          <div className="card w-full max-w-md p-6 shadow-pop">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Create project</h2>
              <button
                onClick={() => setIsModalOpen(false)}
                aria-label="Close"
                className="btn-ghost !p-1.5"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="label" htmlFor="project-name">
                  Project name
                </label>
                <input
                  id="project-name"
                  required
                  type="text"
                  className="field"
                  placeholder="Main app dashboard"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div>
                <label className="label" htmlFor="project-url">
                  Base URL
                </label>
                <input
                  id="project-url"
                  required
                  type="url"
                  className="field"
                  placeholder="https://app.example.com"
                  value={form.base_url}
                  onChange={(e) =>
                    setForm({ ...form, base_url: e.target.value })
                  }
                />
                <p className="text-xs text-ink-muted mt-1.5">
                  Recording opens this URL, and anything off this origin is
                  treated as a sign-in detour.
                </p>
              </div>
              <div>
                <label className="label" htmlFor="project-desc">
                  Description
                </label>
                <textarea
                  id="project-desc"
                  rows={3}
                  className="field resize-none"
                  placeholder="Optional"
                  value={form.description}
                  onChange={(e) =>
                    setForm({ ...form, description: e.target.value })
                  }
                />
              </div>
              {createProject.isError && (
                <p className="text-sm text-rose-500">
                  Could not create the project. Check the API is running.
                </p>
              )}
              <button
                type="submit"
                disabled={createProject.isPending}
                className="btn-primary w-full"
              >
                {createProject.isPending ? "Creating…" : "Create project"}
              </button>
            </form>
          </div>
        </dialog>
      )}
    </div>
  );
};
