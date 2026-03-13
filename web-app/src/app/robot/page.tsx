"use client";

import { useEffect, useState } from "react";

import {
  createRobotTask,
  listElders,
  listRobotTasks,
  type RobotTask,
  type RobotTaskStatus,
  updateRobotTaskStatus,
} from "@/services/medguard";
import type { Elder } from "@/types";

interface InputTarget {
  value: string;
}

const TASK_STATUSES: RobotTaskStatus[] = [
  "queued",
  "running",
  "completed",
  "failed",
];

export default function RobotPage() {
  const [elders, setElders] = useState<Elder[]>([]);
  const [selectedElderId, setSelectedElderId] = useState("");
  const [tasks, setTasks] = useState<RobotTask[]>([]);
  const [taskType, setTaskType] = useState<"pick_and_place" | "sort_session">(
    "sort_session",
  );
  const [planJsonText, setPlanJsonText] = useState(
    '{"slots":["morning","night"]}',
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listElders()
      .then((data: Elder[]) => {
        setElders(data);
        if (data.length > 0) {
          setSelectedElderId(data[0].id);
        }
      })
      .catch(() => setError("Could not load elders"));
  }, []);

  useEffect(() => {
    listRobotTasks(selectedElderId || undefined)
      .then((data: RobotTask[]) => setTasks(data))
      .catch(() => setError("Could not load robot tasks"));
  }, [selectedElderId]);

  const onCreateTask = async (event: {
    preventDefault: () => void;
  }): Promise<void> => {
    event.preventDefault();
    if (!selectedElderId) return;

    setError(null);
    setSaving(true);

    try {
      const parsedPlan = JSON.parse(planJsonText) as Record<string, unknown>;
      const task = await createRobotTask({
        elderId: selectedElderId,
        taskType,
        planJson: parsedPlan,
      });
      setTasks((current: RobotTask[]) => [task, ...current]);
    } catch {
      setError("Could not create robot task. Ensure plan JSON is valid.");
    } finally {
      setSaving(false);
    }
  };

  const onUpdateStatus = async (
    taskId: string,
    status: RobotTaskStatus,
  ): Promise<void> => {
    try {
      const updated = await updateRobotTaskStatus(taskId, status);
      setTasks((current: RobotTask[]) =>
        current.map((task: RobotTask) => (task.id === taskId ? updated : task)),
      );
    } catch {
      setError("Could not update robot task status");
    }
  };

  return (
    <>
      <section className="card">
        <h1>Robot Console</h1>
        <p>Create and monitor SO101 tasks with live backend state.</p>
        {error ? <p>{error}</p> : null}
      </section>

      <section className="card">
        <h2>Filter by elder</h2>
        <select
          value={selectedElderId}
          onChange={(event: { target: InputTarget }) =>
            setSelectedElderId(event.target.value)
          }
        >
          <option value="">All elders</option>
          {elders.map((elder: Elder) => (
            <option key={elder.id} value={elder.id}>
              {elder.fullName}
            </option>
          ))}
        </select>
      </section>

      <section className="card">
        <h2>Create robot task</h2>
        <form onSubmit={onCreateTask}>
          <p>
            <label>
              Task type
              <br />
              <select
                value={taskType}
                onChange={(event: { target: InputTarget }) =>
                  setTaskType(
                    event.target.value as "pick_and_place" | "sort_session",
                  )
                }
              >
                <option value="sort_session">sort_session</option>
                <option value="pick_and_place">pick_and_place</option>
              </select>
            </label>
          </p>
          <p>
            <label>
              Plan JSON
              <br />
              <textarea
                value={planJsonText}
                onChange={(event: { target: InputTarget }) =>
                  setPlanJsonText(event.target.value)
                }
                rows={4}
              />
            </label>
          </p>
          <button type="submit" disabled={saving || !selectedElderId}>
            {saving ? "Saving..." : "Create task"}
          </button>
        </form>
      </section>

      <section className="card">
        <h2>Task timeline</h2>
        {tasks.length === 0 ? (
          <p>No robot tasks yet.</p>
        ) : (
          <ul>
            {tasks.map((task: RobotTask) => (
              <li key={task.id}>
                <strong>{task.taskType}</strong> ({task.status}) started{" "}
                {task.startedAt}
                <br />
                {TASK_STATUSES.map((status: RobotTaskStatus) => (
                  <button
                    key={status}
                    onClick={() => onUpdateStatus(task.id, status)}
                    disabled={task.status === status}
                  >
                    {status}
                  </button>
                ))}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
