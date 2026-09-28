import React from "react";
import { Link } from "react-router-dom";
import { Project } from "../api/types";
import { StatusBadge } from "./StatusBadge";
import { Globe, FileText, ChevronRight, Trash2 } from "lucide-react";
import { formatDate } from "../utils/formatters";

interface Props {
  project: Project;
  onDelete: (project: Project) => void;
}

export const ProjectCard = ({ project, onDelete }: Props) => {
  return (
    <div className="relative">
      <Link
        to={`/projects/${project.id}`}
        className="card card-hover group flex flex-col p-5 h-full"
      >
        <div className="flex justify-between items-start gap-3 mb-3">
          <h3 className="text-base font-semibold text-ink group-hover:text-primary-600 transition-colors">
            {project.name}
          </h3>
          {/* Space kept for the delete button, which sits outside the link. */}
          <span className="flex items-center gap-2 pr-8">
            {project.last_run_status && (
              <StatusBadge status={project.last_run_status} />
            )}
          </span>
        </div>

        <p className="text-sm text-ink-muted line-clamp-2 min-h-[40px]">
          {project.description || "No description provided."}
        </p>

        <div className="mt-4 flex items-center gap-2 text-xs text-ink-muted">
          <Globe className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">{project.base_url}</span>
        </div>

        <div className="mt-4 pt-4 border-t border-line flex items-center justify-between">
          <div className="flex items-center gap-4 text-xs text-ink-muted">
            <span className="flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5" />
              {project.test_case_count || 0} tests
            </span>
            <span>{formatDate(project.created_at)}</span>
          </div>
          <ChevronRight className="w-4 h-4 text-ink-muted group-hover:text-primary-500 transition-colors" />
        </div>
      </Link>

      {/* Outside the card link: a delete button nested in an anchor would
          navigate as well as delete. */}
      <button
        type="button"
        onClick={() => onDelete(project)}
        aria-label={`Delete ${project.name}`}
        title="Delete this project"
        className="absolute top-4 right-4 p-1.5 rounded-lg text-ink-muted hover:text-rose-500 hover:bg-rose-50 transition-colors"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
};
