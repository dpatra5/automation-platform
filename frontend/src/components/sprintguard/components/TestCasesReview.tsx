import { ReviewCard } from "./ReviewCard";
import type { TestCasesData, TestCase } from "../models/sprintGuard.types";
import {
  FileText,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Shield,
  Monitor,
  Search,
  Filter,
} from "lucide-react";
import { useState, useMemo } from "react";

interface TestCasesReviewProps {
  testCases: TestCasesData;
  isLoading: boolean;
  onApprove: () => void;
  onModify: (feedback: string) => void;
  isReadOnly?: boolean;
}

const typeConfig: Record<
  string,
  {
    bg: string;
    text: string;
    border: string;
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  Positive: {
    bg: "bg-emerald-50",
    text: "text-emerald-700",
    border: "border-emerald-200",
    icon: CheckCircle,
  },
  Negative: {
    bg: "bg-red-50",
    text: "text-red-700",
    border: "border-red-200",
    icon: XCircle,
  },
  Boundary: {
    bg: "bg-amber-50",
    text: "text-amber-700",
    border: "border-amber-200",
    icon: AlertTriangle,
  },
  Validation: {
    bg: "bg-blue-50",
    text: "text-blue-700",
    border: "border-blue-200",
    icon: Shield,
  },
  UI: {
    bg: "bg-purple-50",
    text: "text-purple-700",
    border: "border-purple-200",
    icon: Monitor,
  },
};

const priorityConfig = {
  High: { bg: "bg-red-100", text: "text-red-700" },
  Medium: { bg: "bg-amber-100", text: "text-amber-700" },
  Low: { bg: "bg-emerald-100", text: "text-emerald-700" },
};

function TestCaseCard({
  testCase,
  index,
}: {
  testCase: TestCase;
  index: number;
}) {
  const [expanded, setExpanded] = useState(index === 0);
  const typeStyle = typeConfig[testCase.type] || typeConfig.Positive;
  const TypeIcon = typeStyle.icon;
  const priorityStyle =
    priorityConfig[testCase.priority] || priorityConfig.Medium;

  return (
    <div
      className={`border rounded-xl overflow-hidden ${typeStyle.border} ${typeStyle.bg}`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 text-left hover:bg-white/50 transition-colors"
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <span className="font-mono text-xs bg-white/80 px-2 py-1 rounded text-slate-600 shrink-0">
            {testCase.testCaseId}
          </span>
          <span className="font-medium text-slate-800 truncate">
            {testCase.title}
          </span>
        </div>
        <div className="flex items-center gap-2 ml-4 shrink-0">
          <span
            className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${typeStyle.text} bg-white/60`}
          >
            <TypeIcon className="w-3 h-3" />
            {testCase.type}
          </span>
          <span
            className={`px-2 py-0.5 rounded-full text-xs font-medium ${priorityStyle.bg} ${priorityStyle.text}`}
          >
            {testCase.priority}
          </span>
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-slate-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-slate-400" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-white/50 pt-4">
          {/* Objective + traceability */}
          {(testCase.objective ||
            testCase.requirementId ||
            (testCase.acceptanceCriteriaIds &&
              testCase.acceptanceCriteriaIds.length > 0)) && (
            <div className="bg-white/60 rounded-lg p-3 space-y-2">
              {testCase.objective && (
                <div>
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    Objective
                  </span>
                  <p className="mt-1 text-sm text-slate-700">
                    {testCase.objective}
                  </p>
                </div>
              )}
              {(testCase.requirementId ||
                (testCase.acceptanceCriteriaIds &&
                  testCase.acceptanceCriteriaIds.length > 0)) && (
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-semibold text-slate-500 uppercase tracking-wide">
                    Traceability:
                  </span>
                  {testCase.requirementId && (
                    <span className="px-2 py-0.5 rounded bg-slate-200 text-slate-700 font-mono">
                      REQ {testCase.requirementId}
                    </span>
                  )}
                  {testCase.acceptanceCriteriaIds?.map((id) => (
                    <span
                      key={id}
                      className="px-2 py-0.5 rounded bg-slate-200 text-slate-700 font-mono"
                    >
                      {id}
                    </span>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {testCase.severity && (
                  <span className="px-2 py-0.5 rounded bg-slate-900 text-white">
                    Severity: {testCase.severity}
                  </span>
                )}
                {testCase.automationEligible !== undefined && (
                  <span
                    className={`px-2 py-0.5 rounded font-medium ${
                      testCase.automationEligible
                        ? "bg-emerald-600 text-white"
                        : "bg-slate-300 text-slate-700"
                    }`}
                  >
                    {testCase.automationEligible
                      ? "Automation-ready"
                      : "Manual only"}
                  </span>
                )}
                {testCase.tags?.map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-0.5 rounded bg-white text-slate-600 border border-slate-200"
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Preconditions */}
          {testCase.preconditions && testCase.preconditions.length > 0 ? (
            <div className="bg-white/60 rounded-lg p-3">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Preconditions
              </span>
              <ul className="mt-1 text-sm text-slate-700 list-disc pl-5 space-y-0.5">
                {testCase.preconditions.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
          ) : (
            testCase.preCondition && (
              <div className="bg-white/60 rounded-lg p-3">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Pre-condition
                </span>
                <p className="mt-1 text-sm text-slate-700">
                  {testCase.preCondition}
                </p>
              </div>
            )
          )}

          {/* Test Data */}
          {testCase.testData && Object.keys(testCase.testData).length > 0 && (
            <div className="bg-white/60 rounded-lg p-3">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Test Data
              </span>
              <pre className="mt-1 text-xs bg-slate-900 text-slate-100 rounded p-2 overflow-auto">
                {JSON.stringify(testCase.testData, null, 2)}
              </pre>
            </div>
          )}

          {/* Test Steps */}
          <div>
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
              Test Steps
            </span>
            <div className="mt-2 space-y-2">
              {(testCase.automationSteps && testCase.automationSteps.length > 0
                ? testCase.automationSteps
                : testCase.steps.map((s, i) => ({
                    sequence: i + 1,
                    action: s,
                    expectedResult: "",
                  }))
              ).map((step, i) => (
                <div
                  key={`${testCase.testCaseId}-step-${step.sequence ?? i + 1}`}
                  className="flex gap-3 p-3 bg-white/60 rounded-lg"
                >
                  <span className="w-6 h-6 bg-slate-700 text-white rounded-full flex items-center justify-center text-xs font-bold shrink-0">
                    {step.sequence ?? i + 1}
                  </span>
                  <div className="flex-1 space-y-1">
                    <p className="text-sm text-slate-700">{step.action}</p>
                    {step.expectedResult && (
                      <p className="text-xs text-emerald-700">
                        Expected: {step.expectedResult}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Expected Result */}
          <div className="bg-emerald-50/80 rounded-lg p-3 border border-emerald-200/50">
            <span className="text-xs font-semibold text-emerald-700 uppercase tracking-wide flex items-center gap-1">
              <CheckCircle className="w-3.5 h-3.5" />
              Expected Result
            </span>
            <p className="mt-1 text-sm text-emerald-800">
              {testCase.expectedResult}
            </p>
          </div>

          {/* Postconditions + cleanup */}
          {((testCase.postconditions && testCase.postconditions.length > 0) ||
            (testCase.cleanup && testCase.cleanup.length > 0)) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {testCase.postconditions &&
                testCase.postconditions.length > 0 && (
                  <div className="bg-white/60 rounded-lg p-3">
                    <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                      Postconditions
                    </span>
                    <ul className="mt-1 text-sm text-slate-700 list-disc pl-5 space-y-0.5">
                      {testCase.postconditions.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ul>
                  </div>
                )}
              {testCase.cleanup && testCase.cleanup.length > 0 && (
                <div className="bg-white/60 rounded-lg p-3">
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    Cleanup
                  </span>
                  <ul className="mt-1 text-sm text-slate-700 list-disc pl-5 space-y-0.5">
                    {testCase.cleanup.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function KPICard({
  title,
  value,
  icon: Icon,
  bgColor,
  textColor,
}: {
  title: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
  bgColor: string;
  textColor: string;
}) {
  return (
    <div className={`${bgColor} rounded-xl p-4 border border-white/20`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
            {title}
          </p>
          <p className={`text-2xl font-bold mt-1 ${textColor}`}>{value}</p>
        </div>
        <div
          className={`w-10 h-10 rounded-lg ${textColor} bg-white/50 flex items-center justify-center`}
        >
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  );
}

export function TestCasesReview({
  testCases,
  isLoading,
  onApprove,
  onModify,
  isReadOnly = false,
}: TestCasesReviewProps) {
  const cases = testCases.test_cases || [];
  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState<string>("all");
  const [filterPriority, setFilterPriority] = useState<string>("all");

  // Calculate KPIs
  const kpis = useMemo(
    () => ({
      total: cases.length,
      positive: cases.filter((tc) => tc.type === "Positive").length,
      negative: cases.filter((tc) => tc.type === "Negative").length,
      highPriority: cases.filter((tc) => tc.priority === "High").length,
    }),
    [cases],
  );

  // Filter cases
  const filteredCases = useMemo(() => {
    let result = [...cases];

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (tc) =>
          tc.title.toLowerCase().includes(query) ||
          tc.testCaseId.toLowerCase().includes(query) ||
          tc.expectedResult.toLowerCase().includes(query),
      );
    }

    if (filterType !== "all") {
      result = result.filter((tc) => tc.type === filterType);
    }

    if (filterPriority !== "all") {
      result = result.filter((tc) => tc.priority === filterPriority);
    }

    return result;
  }, [cases, searchQuery, filterType, filterPriority]);

  // Get unique types
  const testTypes = useMemo(() => {
    const types = new Set(cases.map((tc) => tc.type));
    return Array.from(types);
  }, [cases]);

  return (
    <ReviewCard
      title="Test Cases"
      onApprove={onApprove}
      onModify={onModify}
      isLoading={isLoading}
      approveLabel="Approve & Create Jira"
      isReadOnly={isReadOnly}
    >
      <div className="space-y-6">
        {/* KPI Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPICard
            title="Total Test Cases"
            value={kpis.total}
            icon={FileText}
            bgColor="bg-slate-100"
            textColor="text-slate-700"
          />
          <KPICard
            title="Positive"
            value={kpis.positive}
            icon={CheckCircle}
            bgColor="bg-emerald-50"
            textColor="text-emerald-600"
          />
          <KPICard
            title="Negative"
            value={kpis.negative}
            icon={XCircle}
            bgColor="bg-red-50"
            textColor="text-red-600"
          />
          <KPICard
            title="High Priority"
            value={kpis.highPriority}
            icon={AlertTriangle}
            bgColor="bg-amber-50"
            textColor="text-amber-600"
          />
        </div>

        {/* Test Type Distribution */}
        <div className="flex flex-wrap gap-2 p-4 bg-slate-50 rounded-xl border border-slate-100">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide mr-2">
            Distribution:
          </span>
          {Object.entries(
            cases.reduce(
              (acc, tc) => {
                acc[tc.type] = (acc[tc.type] || 0) + 1;
                return acc;
              },
              {} as Record<string, number>,
            ),
          ).map(([type, count]) => {
            const style = typeConfig[type] || typeConfig.Positive;
            const Icon = style.icon;
            return (
              <span
                key={type}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${style.bg} ${style.text} border ${style.border}`}
              >
                <Icon className="w-3 h-3" />
                {type}: {count}
              </span>
            );
          })}
        </div>

        {/* Search and Filters */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search test cases..."
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
                {testTypes.map((type) => (
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

        {/* Test Cases List */}
        {filteredCases.length > 0 ? (
          <div className="space-y-3">
            {filteredCases.map((testCase, index) => (
              <TestCaseCard
                key={testCase.testCaseId || index}
                testCase={testCase}
                index={index}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-slate-500">
            {searchQuery || filterType !== "all" || filterPriority !== "all"
              ? "No test cases match your filters"
              : "No test cases defined"}
          </div>
        )}
      </div>
    </ReviewCard>
  );
}
