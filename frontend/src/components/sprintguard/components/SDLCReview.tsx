import { ReviewCard } from "./ReviewCard";
import type { SDLCTestPlanData, SDLCPhase } from "../models/sprintGuard.types";
import {
  Target,
  Clock,
  AlertTriangle,
  CheckCircle,
  Link2,
  FileText,
  ChevronDown,
  ChevronUp,
  Users,
  Calendar,
  Wrench,
  Shield,
  BarChart3,
  Layers,
} from "lucide-react";
import { useState } from "react";

interface SDLCReviewProps {
  sdlcTestplan: SDLCTestPlanData;
  isLoading: boolean;
  onApprove: () => void;
  onModify: (feedback: string) => void;
  isReadOnly?: boolean;
}

const complexityColors: Record<string, string> = {
  Low: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Medium: "bg-amber-50 text-amber-700 border-amber-200",
  High: "bg-rose-50 text-rose-700 border-rose-200",
};

function PhaseCard({
  phase,
  index,
  isLast,
}: {
  phase: SDLCPhase;
  index: number;
  isLast: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="relative flex gap-4">
      {/* Timeline connector */}
      <div className="flex flex-col items-center">
        <div className="w-11 h-11 rounded-full bg-slate-900 text-white flex items-center justify-center font-bold text-lg shadow-lg shadow-slate-300 z-10 ring-4 ring-white">
          {index + 1}
        </div>
        {!isLast && (
          <div className="w-0.5 flex-1 bg-gradient-to-b from-slate-400 to-transparent min-h-[24px]" />
        )}
      </div>

      {/* Phase content */}
      <div
        className={`flex-1 mb-4 bg-white border rounded-2xl overflow-hidden shadow-sm hover:shadow-lg transition-all duration-300 ${
          expanded
            ? "border-slate-300 ring-1 ring-slate-200"
            : "border-slate-200"
        }`}
      >
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-between p-4 text-left hover:bg-slate-50 transition-colors"
        >
          <div className="flex items-center gap-3 flex-wrap">
            <h4 className="font-semibold text-slate-800">{phase.phase}</h4>
            <span className="text-xs bg-slate-100 text-slate-700 px-3 py-1 rounded-full flex items-center gap-1 font-medium border border-slate-200">
              <Clock className="w-3 h-3" />
              {phase.estimatedEffort || "TBD"}
            </span>
            {phase.workHours && (
              <span className="text-xs bg-slate-100 text-slate-600 px-3 py-1 rounded-full">
                {phase.workHours} hrs
              </span>
            )}
          </div>
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors ${
              expanded
                ? "bg-slate-200 text-slate-700"
                : "bg-slate-100 text-slate-400"
            }`}
          >
            {expanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </div>
        </button>

        {expanded && (
          <div className="px-4 pb-4 space-y-4 border-t border-slate-100 pt-4 bg-slate-50/50">
            {/* Objective */}
            {phase.objective && (
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-slate-200 flex items-center justify-center flex-shrink-0">
                  <Target className="w-4 h-4 text-slate-700" />
                </div>
                <div>
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    Objective
                  </span>
                  <p className="text-sm text-slate-700 mt-1">
                    {phase.objective}
                  </p>
                </div>
              </div>
            )}

            {/* Resources & Tools */}
            {(phase.resourcesRequired ||
              (phase.tools && phase.tools.length > 0)) && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {phase.resourcesRequired && (
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
                      <Users className="w-4 h-4 text-slate-600" />
                    </div>
                    <div>
                      <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                        Resources
                      </span>
                      <p className="text-sm text-slate-600 mt-1">
                        {phase.resourcesRequired}
                      </p>
                    </div>
                  </div>
                )}
                {phase.tools && phase.tools.length > 0 && (
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
                      <Wrench className="w-4 h-4 text-slate-600" />
                    </div>
                    <div>
                      <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                        Tools
                      </span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {phase.tools.map((tool, i) => (
                          <span
                            key={`tool-${tool}-${i}`}
                            className="text-xs bg-white border border-slate-200 px-2 py-0.5 rounded"
                          >
                            {tool}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Dependencies & Deliverables */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {phase.dependencies && phase.dependencies.length > 0 && (
                <div className="bg-white rounded-lg p-3 border border-slate-200">
                  <div className="flex items-center gap-2 mb-2">
                    <Link2 className="w-4 h-4 text-slate-600" />
                    <span className="text-xs font-semibold text-slate-600 uppercase">
                      Dependencies
                    </span>
                  </div>
                  <ul className="space-y-1">
                    {phase.dependencies.map((dep, i) => (
                      <li
                        key={`dep-${i}`}
                        className="text-sm text-slate-600 flex items-start gap-1.5"
                      >
                        <span className="text-slate-400 mt-0.5">•</span>
                        {dep}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {phase.deliverables && phase.deliverables.length > 0 && (
                <div className="bg-white rounded-lg p-3 border border-slate-200">
                  <div className="flex items-center gap-2 mb-2">
                    <FileText className="w-4 h-4 text-slate-600" />
                    <span className="text-xs font-semibold text-slate-600 uppercase">
                      Deliverables
                    </span>
                  </div>
                  <ul className="space-y-1">
                    {phase.deliverables.map((del, i) => (
                      <li
                        key={`del-${i}`}
                        className="text-sm text-slate-600 flex items-start gap-1.5"
                      >
                        <CheckCircle className="w-3 h-3 text-green-500 mt-1 shrink-0" />
                        {del}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Challenges & Mitigation */}
            {((phase.expectedChallenges &&
              phase.expectedChallenges.length > 0) ||
              (phase.mitigationPlan && phase.mitigationPlan.length > 0)) && (
              <div className="bg-amber-50 rounded-lg p-3 border border-amber-200">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {phase.expectedChallenges &&
                    phase.expectedChallenges.length > 0 && (
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <AlertTriangle className="w-4 h-4 text-amber-500" />
                          <span className="text-xs font-semibold text-amber-700 uppercase">
                            Challenges
                          </span>
                        </div>
                        <ul className="space-y-1">
                          {phase.expectedChallenges.map((challenge, i) => (
                            <li
                              key={`challenge-${i}`}
                              className="text-sm text-amber-800 flex items-start gap-1.5"
                            >
                              <span className="text-amber-400 mt-0.5">•</span>
                              {challenge}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  {phase.mitigationPlan && phase.mitigationPlan.length > 0 && (
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <Shield className="w-4 h-4 text-green-600" />
                        <span className="text-xs font-semibold text-green-700 uppercase">
                          Mitigation
                        </span>
                      </div>
                      <ul className="space-y-1">
                        {phase.mitigationPlan.map((plan, i) => (
                          <li
                            key={`mitigation-${i}`}
                            className="text-sm text-green-800 flex items-start gap-1.5"
                          >
                            <CheckCircle className="w-3 h-3 text-green-500 mt-1 shrink-0" />
                            {plan}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SectionDivider({
  icon: Icon,
  title,
}: {
  icon: React.ElementType;
  title: string;
}) {
  return (
    <div className="flex items-center gap-3 py-3">
      <div className="w-11 h-11 rounded-2xl bg-slate-900 flex items-center justify-center shadow-lg shadow-slate-300">
        <Icon className="w-5 h-5 text-white" />
      </div>
      <h3 className="text-lg font-bold text-slate-800 tracking-tight">
        {title}
      </h3>
      <div className="flex-1 h-px bg-gradient-to-r from-slate-300 via-slate-200 to-transparent" />
    </div>
  );
}

export function SDLCReview({
  sdlcTestplan,
  isLoading,
  onApprove,
  onModify,
  isReadOnly = false,
}: SDLCReviewProps) {
  const { project_overview, agile_execution_plan, sdlc_phases } = sdlcTestplan;

  // Check if we have meaningful data from LLM
  const hasOverviewData =
    project_overview &&
    (project_overview.complexity ||
      project_overview.estimated_duration ||
      project_overview.total_work_hours ||
      project_overview.resource_count ||
      (project_overview.recommended_team &&
        project_overview.recommended_team.length > 0));

  const hasAgileData =
    agile_execution_plan &&
    (agile_execution_plan.methodology ||
      agile_execution_plan.sprint_count ||
      agile_execution_plan.sprint_duration ||
      agile_execution_plan.epic_name);

  return (
    <ReviewCard
      title="SDLC Plan"
      onApprove={onApprove}
      onModify={onModify}
      isLoading={isLoading}
      approveLabel="Approve & Continue"
      isReadOnly={isReadOnly}
    >
      <div className="space-y-8">
        {/* ============ PROJECT OVERVIEW ============ */}
        <SectionDivider icon={BarChart3} title="Project Overview" />

        {hasOverviewData ? (
          <div className="bg-gradient-to-br from-slate-50 via-white to-slate-50/40 rounded-2xl p-6 border border-slate-200 shadow-sm">
            {/* Stats Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white rounded-2xl p-4 text-center shadow-sm border border-slate-100 hover:shadow-md transition-shadow">
                <div
                  className={`inline-block px-4 py-1.5 rounded-full text-sm font-semibold border ${
                    complexityColors[
                      project_overview?.complexity || "Medium"
                    ] || complexityColors.Medium
                  }`}
                >
                  {project_overview?.complexity || "Medium"}
                </div>
                <p className="text-xs text-slate-500 mt-2 font-medium">
                  Complexity
                </p>
              </div>
              <div className="bg-white rounded-2xl p-4 text-center shadow-sm border border-slate-100 hover:shadow-md transition-shadow">
                <p className="text-2xl font-bold text-slate-900">
                  {project_overview?.estimated_duration || "-"}
                </p>
                <p className="text-xs text-slate-500 mt-1 font-medium">
                  Duration
                </p>
              </div>
              <div className="bg-white rounded-2xl p-4 text-center shadow-sm border border-slate-100 hover:shadow-md transition-shadow">
                <p className="text-2xl font-bold text-slate-900">
                  {project_overview?.total_work_hours || "-"}
                </p>
                <p className="text-xs text-slate-500 mt-1 font-medium">
                  Work Hours
                </p>
              </div>
              <div className="bg-white rounded-2xl p-4 text-center shadow-sm border border-slate-100 hover:shadow-md transition-shadow">
                <p className="text-2xl font-bold text-slate-900">
                  {project_overview?.resource_count || "-"}
                </p>
                <p className="text-xs text-slate-500 mt-1 font-medium">
                  Resources
                </p>
              </div>
            </div>

            {/* Recommended Team */}
            {project_overview?.recommended_team &&
              project_overview.recommended_team.length > 0 && (
                <div className="mt-6">
                  <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-3">
                    Recommended Team
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {project_overview.recommended_team.map((member, i) => (
                      <span
                        key={`team-${member}-${i}`}
                        className="flex items-center gap-2 text-sm bg-white px-4 py-2 rounded-full border border-slate-200 text-slate-700 shadow-sm hover:border-slate-300 hover:shadow transition-all"
                      >
                        <Users className="w-4 h-4 text-slate-600" />
                        {member}
                      </span>
                    ))}
                  </div>
                </div>
              )}

            {/* Agile Execution */}
            {hasAgileData && (
              <div className="mt-6 pt-6 border-t border-slate-200">
                <div className="flex items-center gap-2 mb-3">
                  <Calendar className="w-4 h-4 text-slate-700" />
                  <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
                    Agile Execution Plan
                  </p>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {agile_execution_plan?.methodology && (
                    <div className="bg-white rounded-xl p-3 border border-slate-100">
                      <p className="text-xs text-slate-500">Methodology</p>
                      <p className="text-sm font-semibold text-slate-800">
                        {agile_execution_plan.methodology}
                      </p>
                    </div>
                  )}
                  {agile_execution_plan?.sprint_count && (
                    <div className="bg-white rounded-xl p-3 border border-slate-100">
                      <p className="text-xs text-slate-500">Sprints</p>
                      <p className="text-sm font-semibold text-slate-800">
                        {agile_execution_plan.sprint_count}
                      </p>
                    </div>
                  )}
                  {agile_execution_plan?.sprint_duration && (
                    <div className="bg-white rounded-xl p-3 border border-slate-100">
                      <p className="text-xs text-slate-500">Sprint Duration</p>
                      <p className="text-sm font-semibold text-slate-800">
                        {agile_execution_plan.sprint_duration}
                      </p>
                    </div>
                  )}
                  {agile_execution_plan?.epic_name && (
                    <div className="bg-white rounded-xl p-3 border border-slate-100">
                      <p className="text-xs text-slate-500">Epic</p>
                      <p className="text-sm font-semibold text-slate-800">
                        {agile_execution_plan.epic_name}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="bg-slate-50 rounded-2xl p-6 border border-slate-200 text-center">
            <p className="text-slate-500 text-sm">
              Project overview data not available
            </p>
          </div>
        )}

        {/* ============ SDLC PHASES ============ */}
        <SectionDivider icon={Layers} title="SDLC Phases" />

        {sdlc_phases && sdlc_phases.length > 0 ? (
          <div>
            {/* Summary Stats */}
            <div className="flex items-center justify-between mb-4 px-2">
              <p className="text-sm text-slate-600">
                <span className="font-semibold text-slate-900">
                  {sdlc_phases.length}
                </span>{" "}
                phases defined
              </p>
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1.5 text-sm text-slate-600 bg-slate-100 px-3 py-1.5 rounded-full">
                  <FileText className="w-4 h-4 text-slate-600" />
                  {sdlc_phases.reduce(
                    (acc, p) => acc + (p.deliverables?.length || 0),
                    0,
                  )}{" "}
                  Deliverables
                </span>
              </div>
            </div>

            {/* Phase Timeline */}
            <div className="pl-1">
              {sdlc_phases.map((phase, index) => (
                <PhaseCard
                  key={`phase-${phase.phase}-${index}`}
                  phase={phase}
                  index={index}
                  isLast={index === sdlc_phases.length - 1}
                />
              ))}
            </div>
          </div>
        ) : (
          <div className="bg-slate-50 rounded-2xl p-6 border border-slate-200 text-center">
            <p className="text-slate-500 text-sm">No SDLC phases defined</p>
          </div>
        )}
      </div>
    </ReviewCard>
  );
}
