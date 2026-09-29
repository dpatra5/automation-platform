import { ReviewCard } from "./ReviewCard";
import type { StoryTasksData } from "../models/sprintGuard.types";
import {
  Search,
  Filter,
  ArrowUpDown,
  Clock,
  Tag,
  Layers,
  Monitor,
  Server,
  Database,
  Link,
  TestTube,
  FileText,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useState, useMemo } from "react";

interface StoryTasksReviewProps {
  storyTasks: StoryTasksData;
  isLoading: boolean;
  onApprove: () => void;
  onModify: (feedback: string) => void;
  isReadOnly?: boolean;
}

const priorityConfig = {
  High: { bg: "bg-red-100", text: "text-red-700", border: "border-red-200" },
  Medium: {
    bg: "bg-amber-100",
    text: "text-amber-700",
    border: "border-amber-200",
  },
  Low: {
    bg: "bg-emerald-100",
    text: "text-emerald-700",
    border: "border-emerald-200",
  },
};

const typeConfig: Record<
  string,
  {
    bg: string;
    text: string;
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  Frontend: { bg: "bg-purple-100", text: "text-purple-700", icon: Monitor },
  Backend: { bg: "bg-blue-100", text: "text-blue-700", icon: Server },
  Database: { bg: "bg-orange-100", text: "text-orange-700", icon: Database },
  API: { bg: "bg-cyan-100", text: "text-cyan-700", icon: Link },
  Testing: { bg: "bg-green-100", text: "text-green-700", icon: TestTube },
  Documentation: { bg: "bg-slate-100", text: "text-slate-700", icon: FileText },
};

type SortField = "taskId" | "title" | "type" | "priority" | "estimate";
type SortDirection = "asc" | "desc";

export function StoryTasksReview({
  storyTasks,
  isLoading,
  onApprove,
  onModify,
  isReadOnly = false,
}: StoryTasksReviewProps) {
  const story = storyTasks.story;
  const tasks = storyTasks.tasks || [];

  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState<string>("all");
  const [filterPriority, setFilterPriority] = useState<string>("all");
  const [sortField, setSortField] = useState<SortField>("taskId");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [showStoryDetails, setShowStoryDetails] = useState(true);

  // Get unique types for filter
  const taskTypes = useMemo(() => {
    const types = new Set(tasks.map((t) => t.type));
    return Array.from(types);
  }, [tasks]);

  // Filter and sort tasks
  const filteredTasks = useMemo(() => {
    let result = [...tasks];

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (t) =>
          t.title.toLowerCase().includes(query) ||
          t.description.toLowerCase().includes(query) ||
          t.taskId.toLowerCase().includes(query),
      );
    }

    // Type filter (case-insensitive)
    if (filterType !== "all") {
      result = result.filter(
        (t) => t.type?.toLowerCase() === filterType.toLowerCase(),
      );
    }

    // Priority filter (case-insensitive)
    if (filterPriority !== "all") {
      result = result.filter(
        (t) => t.priority?.toLowerCase() === filterPriority.toLowerCase(),
      );
    }

    // Sort
    result.sort((a, b) => {
      let aVal: string | number = a[sortField] || "";
      let bVal: string | number = b[sortField] || "";

      if (sortField === "estimate") {
        aVal = parseInt(a.estimate) || 0;
        bVal = parseInt(b.estimate) || 0;
      }

      if (aVal < bVal) return sortDirection === "asc" ? -1 : 1;
      if (aVal > bVal) return sortDirection === "asc" ? 1 : -1;
      return 0;
    });

    return result;
  }, [
    tasks,
    searchQuery,
    filterType,
    filterPriority,
    sortField,
    sortDirection,
  ]);

  // Calculate total estimate
  const totalEstimate = useMemo(() => {
    return tasks.reduce((acc, t) => acc + (parseInt(t.estimate) || 0), 0);
  }, [tasks]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => (
    <ArrowUpDown
      className={`w-3 h-3 ${sortField === field ? "text-blue-500" : "text-slate-300"}`}
    />
  );

  return (
    <ReviewCard
      title="Story & Tasks"
      onApprove={onApprove}
      onModify={onModify}
      isLoading={isLoading}
      approveLabel="Approve & Continue"
      isReadOnly={isReadOnly}
    >
      <div className="space-y-6">
        {/* Main Story Card */}
        <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
          <button
            onClick={() => setShowStoryDetails(!showStoryDetails)}
            className="w-full bg-gradient-to-r from-slate-50 to-white px-4 py-3 border-b border-slate-200 flex items-center justify-between"
          >
            <div className="flex items-center gap-3">
              <Layers className="w-5 h-5 text-slate-600" />
              <span className="font-medium text-slate-700">
                {story.type || "Story"}
              </span>
              <span
                className={`px-2 py-0.5 rounded text-xs font-medium ${
                  priorityConfig[story.priority]?.bg || "bg-gray-100"
                } ${priorityConfig[story.priority]?.text || "text-gray-700"}`}
              >
                {story.priority}
              </span>
              <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                {story.story_points} SP
              </span>
            </div>
            {showStoryDetails ? (
              <ChevronUp className="w-5 h-5 text-slate-400" />
            ) : (
              <ChevronDown className="w-5 h-5 text-slate-400" />
            )}
          </button>

          {showStoryDetails && (
            <div className="p-4 space-y-4">
              <h3 className="text-lg font-semibold text-slate-800">
                {story.title}
              </h3>

              <div className="bg-slate-50 p-3 rounded-lg">
                <p className="text-sm text-slate-700 whitespace-pre-wrap">
                  {story.description}
                </p>
              </div>

              {story.acceptance_criteria.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                    Acceptance Criteria
                  </h4>
                  <ul className="space-y-2">
                    {story.acceptance_criteria.map((ac, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 bg-emerald-50 p-2.5 rounded-lg border-l-4 border-emerald-500"
                      >
                        <span className="text-emerald-600 font-bold text-xs mt-0.5">
                          AC{i + 1}
                        </span>
                        <span className="text-sm text-slate-700">{ac}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="flex flex-wrap gap-2 pt-2">
                {story.labels.map((label, i) => (
                  <span
                    key={i}
                    className="flex items-center gap-1 px-2 py-1 bg-slate-100 text-slate-600 rounded text-xs"
                  >
                    <Tag className="w-3 h-3" />
                    {label}
                  </span>
                ))}
                {story.components.map((comp, i) => (
                  <span
                    key={i}
                    className="flex items-center gap-1 px-2 py-1 bg-blue-50 text-blue-600 rounded text-xs"
                  >
                    <Layers className="w-3 h-3" />
                    {comp}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Tasks Section */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wide flex items-center gap-2">
              Implementation Tasks
              <span className="bg-slate-200 text-slate-600 px-2 py-0.5 rounded-full text-xs font-normal">
                {tasks.length}
              </span>
            </h4>
            <div className="flex items-center gap-2 text-xs">
              <Clock className="w-4 h-4 text-slate-400" />
              <span className="text-slate-600">Total: {totalEstimate}h</span>
            </div>
          </div>

          {/* Search and Filters */}
          <div className="flex flex-col sm:flex-row gap-3 mb-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search tasks..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
            <div className="flex gap-2">
              <div className="relative">
                <Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <select
                  value={filterType}
                  onChange={(e) => setFilterType(e.target.value)}
                  className="pl-8 pr-8 py-2 text-sm border border-slate-200 rounded-lg appearance-none bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                >
                  <option value="all">All Types</option>
                  {taskTypes.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </div>
              <select
                value={filterPriority}
                onChange={(e) => setFilterPriority(e.target.value)}
                className="px-3 py-2 text-sm border border-slate-200 rounded-lg appearance-none bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                <option value="all">All Priorities</option>
                <option value="High">High</option>
                <option value="Medium">Medium</option>
                <option value="Low">Low</option>
              </select>
            </div>
          </div>

          {/* Tasks Table */}
          <div className="border border-slate-200 rounded-xl overflow-hidden">
            <table className="w-full">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100"
                    onClick={() => handleSort("taskId")}
                  >
                    <div className="flex items-center gap-1">
                      ID <SortIcon field="taskId" />
                    </div>
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100"
                    onClick={() => handleSort("title")}
                  >
                    <div className="flex items-center gap-1">
                      Title <SortIcon field="title" />
                    </div>
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100"
                    onClick={() => handleSort("type")}
                  >
                    <div className="flex items-center gap-1">
                      Type <SortIcon field="type" />
                    </div>
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100"
                    onClick={() => handleSort("priority")}
                  >
                    <div className="flex items-center gap-1">
                      Priority <SortIcon field="priority" />
                    </div>
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100"
                    onClick={() => handleSort("estimate")}
                  >
                    <div className="flex items-center gap-1">
                      Estimate <SortIcon field="estimate" />
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredTasks.length > 0 ? (
                  filteredTasks.map((task, index) => {
                    return (
                      <tr
                        key={task.taskId || index}
                        className="hover:bg-slate-50 transition-colors group"
                      >
                        <td className="px-4 py-3">
                          <span className="font-mono text-xs text-slate-500 bg-slate-100 px-2 py-1 rounded">
                            {task.taskId}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div>
                            <p className="font-medium text-sm text-slate-800">
                              {task.title}
                            </p>
                            <p className="text-xs text-slate-500 mt-0.5 line-clamp-1 group-hover:line-clamp-none">
                              {task.description}
                            </p>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-slate-700">
                            {task.type}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-slate-700">
                            {task.priority}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="flex items-center gap-1 text-sm text-slate-600">
                            <Clock className="w-3.5 h-3.5 text-slate-400" />
                            {task.estimate}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-8 text-center text-slate-500 text-sm"
                    >
                      {searchQuery ||
                      filterType !== "all" ||
                      filterPriority !== "all"
                        ? "No tasks match your filters"
                        : "No tasks defined"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Summary by Type */}
          <div className="flex flex-wrap gap-2 mt-4">
            {Object.entries(
              tasks.reduce(
                (acc, t) => {
                  acc[t.type] = (acc[t.type] || 0) + 1;
                  return acc;
                },
                {} as Record<string, number>,
              ),
            ).map(([type, count]) => {
              const style = typeConfig[type] || {
                bg: "bg-gray-100",
                text: "text-gray-700",
                icon: FileText,
              };
              const Icon = style.icon;
              return (
                <span
                  key={type}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${style.bg} ${style.text}`}
                >
                  <Icon className="w-3 h-3" />
                  {type}: {count}
                </span>
              );
            })}
          </div>
        </div>
      </div>
    </ReviewCard>
  );
}
