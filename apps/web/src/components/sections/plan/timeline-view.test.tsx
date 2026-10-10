import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { listStudyGoals, type StudyGoal } from "@/lib/api";
import { TimelineView } from "./timeline-view";

vi.mock("@/lib/api", () => ({ listStudyGoals: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

function goal(courseId: string, title: string): StudyGoal {
  return {
    id: courseId, course_id: courseId, user_id: "student", title,
    objective: "Practice", success_metric: null, current_milestone: null,
    next_action: null, status: "active", confidence: null, target_date: null,
    metadata_json: null, linked_task_count: 0, created_at: null,
    updated_at: null, completed_at: null,
  };
}

it("shows loading on course changes and ignores a late previous course response", async () => {
  let resolveFirst!: (goals: StudyGoal[]) => void;
  let resolveSecond!: (goals: StudyGoal[]) => void;
  vi.mocked(listStudyGoals)
    .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
    .mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve; }));

  const { rerender } = render(<TimelineView courseId="course-1" />);
  expect(screen.getByText("加载中…")).toBeInTheDocument();
  rerender(<TimelineView courseId="course-2" />);
  expect(screen.getByText("加载中…")).toBeInTheDocument();
  await act(async () => { resolveSecond([goal("course-2", "Current course goal")]); });
  expect(screen.getByText("Current course goal")).toBeInTheDocument();
  expect(screen.queryByText("加载中…")).not.toBeInTheDocument();

  await act(async () => { resolveFirst([goal("course-1", "Stale course goal")]); });
  expect(screen.getByText("Current course goal")).toBeInTheDocument();
  expect(screen.queryByText("Stale course goal")).not.toBeInTheDocument();
});
