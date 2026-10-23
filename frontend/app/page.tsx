 "use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type Fragment = {
  id: number;
  title: string;
  start_time: number;
  end_time: number;
  duration: number;
  reasoning: string;
  summary: string;
};

type ProcessResponse = {
  task_id: number;
  celery_task_id: string;
  status: string;
};

type TaskStatusResponse = {
  task_id: number;
  status: string;
  youtube_url: string;
  progress: number;
  current_step: string;
  step_label: string;
  is_completed: boolean;
  is_failed: boolean;
  error_message: string | null;
  stages: Array<{
    key: string;
    title: string;
    status: "pending" | "in_progress" | "completed" | "failed";
  }>;
};

type FragmentsResponse = {
  task_id: number;
  status: string;
  youtube_url: string;
  count: number;
  fragments: Fragment[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function isYouTubeUrl(value: string): boolean {
  try {
    const url = new URL(value);
    const host = url.hostname.replace(/^www\./, "");
    return (
      host === "youtube.com" ||
      host === "youtu.be" ||
      host === "m.youtube.com"
    );
  } catch {
    return false;
  }
}

function formatTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

function youtubePreviewUrl(sourceUrl: string, startTime: number): string {
  try {
    const source = new URL(sourceUrl);
    let videoId = "";

    if (source.hostname.replace(/^www\./, "") === "youtu.be") {
      videoId = source.pathname.replace("/", "");
    } else {
      videoId = source.searchParams.get("v") ?? "";
      if (!videoId && source.pathname.startsWith("/shorts/")) {
        videoId = source.pathname.split("/")[2] ?? "";
      }
    }

    if (!videoId) return sourceUrl;
    return `https://www.youtube.com/watch?v=${encodeURIComponent(
      videoId,
    )}&t=${Math.floor(startTime)}s`;
  } catch {
    return sourceUrl;
  }
}

export default function Home() {
  const [url, setUrl] = useState("");
  const [task, setTask] = useState<ProcessResponse | null>(null);
  const [fragments, setFragments] = useState<Fragment[]>([]);
  const [sourceUrl, setSourceUrl] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [taskStatus, setTaskStatus] = useState<TaskStatusResponse | null>(null);

  const statusText = useMemo(() => {
    const labels: Record<string, string> = {
      idle: "",
      pending: "Задача поставлена в очередь…",
      downloading: "Скачиваем аудиодорожку…",
      transcribing: "Распознаём речь…",
      analyzing: "Ищем лучшие моменты с помощью AI…",
      cutting: "Создаём вертикальные клипы…",
      completed: "Готово!",
      error: "Обработка завершилась с ошибкой.",
    };
    return labels[status] ?? status;
  }, [status]);

useEffect(() => {
    if (!task?.task_id) return;

    let cancelled = false;
    let finished = false;
    let intervalId: number | undefined;

    const poll = async () => {
      try {
        const response = await fetch(
          `${API_URL}/api/v1/tasks/${task.task_id}/status`,
          { cache: "no-store" },
        );
        if (!response.ok) throw new Error("Не удалось получить статус задачи.");

        const data: TaskStatusResponse = await response.json();
        if (cancelled || finished) return;

        setTaskStatus(data);
        setSourceUrl(data.youtube_url);
        setStatus(data.status);
        setError("");

        if (data.is_completed || data.status === "completed") {
          const fragmentsResponse = await fetch(
            `${API_URL}/api/v1/tasks/${task.task_id}/fragments`,
            { cache: "no-store" },
          );
          if (!fragmentsResponse.ok) {
            throw new Error("Обработка завершена, но не удалось загрузить фрагменты.");
          }
          const fragmentsData: FragmentsResponse = await fragmentsResponse.json();
          if (cancelled) return;
          setFragments(fragmentsData.fragments);
          setStatus("completed");
          setLoading(false);
          finished = true;
          if (intervalId !== undefined) window.clearInterval(intervalId);
        } else if (data.is_failed || data.status === "error") {
          setError(data.error_message || "Обработка завершилась с ошибкой.");
          setStatus("error");
          setLoading(false);
          finished = true;
          if (intervalId !== undefined) window.clearInterval(intervalId);
        }
      } catch (err) {
        if (!cancelled && !finished) {
          setError(err instanceof Error ? err.message : "Неизвестная ошибка.");
        }
      }
    };

    void poll();
    intervalId = window.setInterval(() => {
      if (!finished) void poll();
    }, 2000);

    return () => {
      cancelled = true;
      if (intervalId !== undefined) window.clearInterval(intervalId);
    };
  }, [task?.task_id]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setFragments([]);
    setTaskStatus(null);

    if (!isYouTubeUrl(url)) {
      setError("Введите корректную ссылку на YouTube.");
      return;
    }

    setLoading(true);
    setStatus("pending");

    try {
      const response = await fetch(`${API_URL}/api/v1/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ youtube_url: url }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail ?? "Не удалось запустить обработку.");
      }

      setTask(data);
      setSourceUrl(url);
    } catch (err) {
      setStatus("error");
      setLoading(false);
      setError(err instanceof Error ? err.message : "Неизвестная ошибка.");
    }
  }

  function reset() {
    setUrl("");
    setTask(null);
    setFragments([]);
    setSourceUrl("");
    setStatus("idle");
    setError("");
    setLoading(false);
    setTaskStatus(null);
  }

  return (
    <main className="min-h-screen px-4 py-12">
      <div className="mx-auto max-w-5xl">
        <header className="mb-10 text-center">
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.3em] text-violet-400">
            AI Shorts Maker
          </p>
          <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
            Найди лучшие моменты
            <span className="block text-violet-400">из YouTube-видео</span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-zinc-400">
            Вставь ссылку — система скачает аудио, расшифрует речь и с помощью
            AI предложит фрагменты до 60 секунд.
          </p>
        </header>

        <section className="rounded-3xl border border-zinc-800 bg-zinc-950/80 p-5 shadow-2xl sm:p-8">
          <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row">
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
              disabled={loading}
              className="min-h-14 flex-1 rounded-2xl border border-zinc-700 bg-zinc-900 px-5 text-base outline-none transition placeholder:text-zinc-600 focus:border-violet-500 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={loading}
              className="min-h-14 rounded-2xl bg-violet-600 px-7 font-semibold transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Обрабатываем…" : "Найти моменты"}
            </button>
          </form>

          {error && (
            <div className="mt-4 rounded-2xl border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
              {error}
            </div>
          )}

          {status !== "idle" && (
            <div className="mt-5 rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="font-semibold">{taskStatus?.step_label || statusText}</p>
                  {task && (
                    <p className="mt-1 text-sm text-zinc-500">Задача #{task.task_id}</p>
                  )}
                </div>
                <span className="font-mono text-sm font-semibold text-violet-300">
                  {taskStatus?.progress ?? 0}%
                </span>
              </div>

              <div
                className="mt-4 h-2 overflow-hidden rounded-full bg-zinc-800"
                role="progressbar"
                aria-label="Прогресс обработки видео"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={taskStatus?.progress ?? 0}
              >
                <div
                  className={`h-full rounded-full transition-all duration-500 ${status === "error" ? "bg-red-500" : status === "completed" ? "bg-emerald-500" : "bg-violet-500"}`}
                  style={{ width: `${taskStatus?.progress ?? 0}%` }}
                />
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                {(taskStatus?.stages ?? [
                  { key: "downloading", title: "Загрузка видео", status: "pending" as const },
                  { key: "transcribing", title: "Транскрибация речи Faster-Whisper", status: "pending" as const },
                  { key: "analyzing", title: "Семантический отбор и скоринг LLM", status: "pending" as const },
                  { key: "cutting", title: "Нарезка вертикального MP4 через FFmpeg", status: "pending" as const },
                ]).map((stage) => {
                  const styles = {
                    pending: "border-zinc-700 bg-zinc-950 text-zinc-500",
                    in_progress: "border-blue-500/60 bg-blue-950/40 text-blue-200 animate-pulse",
                    completed: "border-emerald-700/60 bg-emerald-950/30 text-emerald-300",
                    failed: "border-red-700/70 bg-red-950/40 text-red-300",
                  };
                  const icons = {
                    pending: "○",
                    in_progress: "◉",
                    completed: "✓",
                    failed: "!",
                  };
                  const labels = {
                    pending: "Ожидание",
                    in_progress: "В работе",
                    completed: "Готово",
                    failed: "Ошибка",
                  };
                  const stageState = stage.status;
                  const title = stage.key === "analyzing"
                    ? "Семантический отбор и скоринг LLM"
                    : stage.title;
                  return (
                    <div key={stage.key} className={`flex items-start gap-3 rounded-xl border p-3 ${styles[stageState]}`}>
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-black/20 text-sm font-bold">
                        {icons[stageState]}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">{title}</p>
                        <p className="mt-1 text-xs opacity-80">{labels[stageState]}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
              {error && (
                <p className="mt-4 rounded-xl border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">
                  {error}
                </p>
              )}
            </div>
          )}
        </section>

        {status === "completed" && (
          <section className="mt-10">
            <div className="mb-5 flex items-end justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold">Найденные фрагменты</h2>
                <p className="mt-1 text-sm text-zinc-500">
                  {fragments.length} {fragments.length === 1 ? "момент" : "моментов"} до 60 секунд
                </p>
              </div>
              <button
                onClick={reset}
                className="rounded-xl border border-zinc-700 px-4 py-2 text-sm transition hover:bg-zinc-900"
              >
                Новое видео
              </button>
            </div>

            {fragments.length === 0 ? (
              <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-8 text-center text-zinc-400">
                AI не нашёл подходящих фрагментов.
              </div>
            ) : (
              <div className="grid gap-5 md:grid-cols-2">
                {fragments.map((fragment, index) => (
                  <article
                    key={fragment.id}
                    className="rounded-3xl border border-zinc-800 bg-zinc-950 p-6 transition hover:border-zinc-700"
                  >
                    <div className="mb-5 flex items-start justify-between gap-4">
                      <span className="rounded-full bg-violet-500/10 px-3 py-1 text-xs font-semibold text-violet-300">
                        #{index + 1}
                      </span>
                      <span className="font-mono text-sm text-zinc-400">
                        {formatTime(fragment.start_time)} —{" "}
                        {formatTime(fragment.end_time)}
                      </span>
                    </div>

                    <h3 className="text-xl font-semibold leading-snug">
                      {fragment.title}
                    </h3>

                    {fragment.summary && (
                      <p className="mt-3 text-sm leading-6 text-zinc-400">
                        {fragment.summary}
                      </p>
                    )}

                    {fragment.reasoning && (
                      <p className="mt-4 border-l-2 border-violet-500/50 pl-3 text-xs leading-5 text-zinc-500">
                        {fragment.reasoning}
                      </p>
                    )}

                    <div className="mt-6 flex items-center justify-between border-t border-zinc-800 pt-5">
                      <span className="text-sm text-zinc-500">
                        Длительность: {Math.round(fragment.duration)} сек.
                      </span>
                      <a
                        href={youtubePreviewUrl(
                          sourceUrl,
                          fragment.start_time,
                        )}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-xl bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-950 transition hover:bg-white"
                      >
                        ▶ Предпросмотр
                      </a>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}