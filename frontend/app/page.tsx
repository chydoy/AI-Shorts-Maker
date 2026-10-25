"use client";

import { FormEvent, useEffect, useState } from "react";
import { FragmentCard, FragmentData } from "../components/FragmentCard";

type StageItem = {
  key: string;
  title: string;
  status: "pending" | "in_progress" | "completed" | "failed";
};

type TaskStatusResponse = {
  task_id: number;
  status: string;
  youtube_url: string;
  progress: number;
  transcription_progress: number;
  current_step: string;
  step_label: string;
  is_completed: boolean;
  is_failed: boolean;
  error_message?: string;
  stages: StageItem[];
  clips_summary?: {
    total: number;
    ready: number;
    pending: number;
    error: number;
  };
  clips?: FragmentData[];
};

type ProcessResponse = {
  task_id: number;
  celery_task_id: string;
  status: string;
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
  const [fragments, setFragments] = useState<FragmentData[]>([]);
  const [sourceUrl, setSourceUrl] = useState("");
  const [status, setStatus] = useState("idle");
  const [stepLabel, setStepLabel] = useState("");
  const [progress, setProgress] = useState(0);
  const [transcriptionProgress, setTranscriptionProgress] = useState(0);
  const [stages, setStages] = useState<StageItem[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"top" | "archive">("top");

  useEffect(() => {
    if (!task?.task_id || status === "completed" || status === "error") {
      return;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const response = await fetch(
          `${API_URL}/api/v1/tasks/${task.task_id}/status`,
          { cache: "no-store" },
        );

        if (!response.ok) throw new Error("Не удалось получить статус задачи.");

        const data: TaskStatusResponse = await response.json();

        if (cancelled) return;

        setSourceUrl(data.youtube_url);
        setProgress(data.progress ?? 0);
        setTranscriptionProgress(data.transcription_progress ?? 0);
        setStepLabel(data.step_label ?? data.status);
        if (data.stages) setStages(data.stages);

        if (data.is_completed || data.status === "completed") {
          // Если клипы уже пришли в status эндпоинте:
          if (data.clips && data.clips.length > 0) {
            setFragments(data.clips);
          } else {
            // Фолбэк на /fragments
            const fragmentsRes = await fetch(
              `${API_URL}/api/v1/tasks/${task.task_id}/fragments`,
              { cache: "no-store" },
            );
            if (fragmentsRes.ok) {
              const fData = await fragmentsRes.json();
              setFragments(fData.fragments ?? []);
            }
          }
          setStatus("completed");
          setProgress(100);
          setLoading(false);
        } else if (data.is_failed || data.status === "error") {
          setStatus("error");
          setError(data.error_message || "Celery не смог обработать видео. Проверьте логи worker.");
          setLoading(false);
        } else {
          setStatus(data.status);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Неизвестная ошибка.");
          setLoading(false);
        }
      }
    };

    poll();
    const interval = window.setInterval(poll, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [task?.task_id, status]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setFragments([]);
    setProgress(0);
    setTranscriptionProgress(0);
    setStages([]);

    if (!isYouTubeUrl(url)) {
      setError("Введите корректную ссылку на YouTube.");
      return;
    }

    setLoading(true);
    setStatus("pending");
    setStepLabel("Инициализация задачи...");

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
    setStepLabel("");
    setProgress(0);
    setTranscriptionProgress(0);
    setStages([]);
    setError("");
    setLoading(false);
    setActiveTab("top");
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
            Вставь ссылку: система скачает видео, распознает речь, отберёт
            хайповые моменты через LLM и нарежет клипы 9:16.
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

          {/* КАРТОЧКА 10 (Влад): Прогресс-бар 0–100% и 4 стадии */}
          {status !== "idle" && !error && (
            <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
              <div className="flex items-center justify-between gap-4 mb-3">
                <div>
                  <p className="font-semibold text-white">{stepLabel || "Обработка..."}</p>
                  {task && (
                    <p className="mt-0.5 text-xs text-zinc-500">
                      Задача #{task.task_id}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm font-bold text-violet-400">
                    {progress}%
                  </span>
                  {loading && (
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-violet-400" />
                  )}
                </div>
              </div>

              {/* Шкала 0-100% */}
              <div className="h-2.5 w-full overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="h-full bg-violet-500 transition-all duration-500 ease-out"
                  style={{ width: `${Math.min(100, Math.max(progress, 3))}%` }}
                />
              </div>
              {status === "transcribing" && (
              <div className="mt-5">
                <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                  <span className="text-zinc-300">Распознавание речи (Whisper)</span>
                  <span className="font-mono font-semibold text-violet-400">
                    {transcriptionProgress}%
                  </span>
                </div>

                <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                    style={{
                      width: `${Math.min(100, Math.max(0, transcriptionProgress))}%`,
                    }}
                  />
                </div>
              </div>
            )}

              {/* Индивидуальные прогресс-бары для каждого этапа */}
              {stages.length > 0 && (
                <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {stages.map((st) => {
                    const isDone = st.status === "completed";
                    const isCurr = st.status === "in_progress";
                    const isFail = st.status === "failed";

                    let stagePercent = 0;
                    let stageLabel = "В очереди";

                    if (isDone) {
                      stagePercent = 100;
                      stageLabel = "100%";
                    } else if (isFail) {
                      stagePercent = 100;
                      stageLabel = "Сбой";
                    } else if (isCurr) {
                      if (st.key === "transcribing") {
                        stagePercent = transcriptionProgress || 45;
                        stageLabel = `${stagePercent}%`;
                      } else if (st.key === "downloading") {
                        stagePercent = 65;
                        stageLabel = "Загрузка...";
                      } else if (st.key === "analyzing") {
                        stagePercent = 75;
                        stageLabel = "Анализ...";
                      } else if (st.key === "cutting") {
                        stagePercent = 80;
                        stageLabel = "Нарезка...";
                      } else {
                        stagePercent = 50;
                        stageLabel = "В работе";
                      }
                    }

                    return (
                      <div
                        key={st.key}
                        className={`rounded-2xl border p-3.5 text-xs transition flex flex-col justify-between gap-2.5 ${
                          isDone
                            ? "border-emerald-500/30 bg-emerald-950/20 text-emerald-300"
                            : isCurr
                            ? "border-violet-500/50 bg-violet-950/30 text-violet-200 ring-1 ring-violet-500/30 shadow-md shadow-violet-950/30"
                            : isFail
                            ? "border-red-500/30 bg-red-950/20 text-red-300"
                            : "border-zinc-800 bg-zinc-950/40 text-zinc-500"
                        }`}
                      >
                        <div>
                          <div className="flex items-center justify-between gap-1 mb-1">
                            <span className="font-semibold text-zinc-200 truncate">
                              {st.title}
                            </span>
                            <span className="text-[11px] font-mono shrink-0">
                              {isDone ? "✓" : isFail ? "✕" : isCurr ? "●" : "○"}
                            </span>
                          </div>
                          <p className="text-[11px] opacity-75">{stageLabel}</p>
                        </div>

                        {/* Индивидуальная полоса прогресса этапа */}
                        <div className="h-1.5 w-full bg-zinc-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all duration-300 ${
                              isDone
                                ? "bg-emerald-500"
                                : isFail
                                ? "bg-red-500"
                                : isCurr
                                ? "bg-violet-500 animate-pulse"
                                : "bg-transparent"
                            }`}
                            style={{ width: `${stagePercent}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </section>

        {status === "completed" && (
          <section className="mt-10">
            {(() => {
              const topClips = fragments.filter((f) => (f.virality_score ?? 0) >= 75);
              const archiveClips = fragments.filter((f) => (f.virality_score ?? 0) < 75);
              const displayedClips = activeTab === "top" ? topClips : archiveClips;

              return (
                <>
                  <div className="mb-6 flex flex-col sm:flex-row sm:items-end justify-between gap-4">
                    <div>
                      <h2 className="text-2xl font-bold">Соревновательная таблица клипов</h2>
                      <p className="mt-1 text-sm text-zinc-500">
                        Всего отобрано {fragments.length} {fragments.length === 1 ? "фрагмент" : "фрагментов"} по шкале вирусности
                      </p>
                    </div>
                    <button
                      onClick={reset}
                      className="rounded-xl border border-zinc-700 px-4 py-2 text-sm font-semibold transition hover:bg-zinc-900 self-start sm:self-auto"
                    >
                      Новое видео
                    </button>
                  </div>

                  {/* Вкладки соревновательной таблицы: Топ клипов (75+) и Архив (<75) */}
                  <div className="flex items-center gap-3 border-b border-zinc-800 pb-4 mb-6">
                    <button
                      type="button"
                      onClick={() => setActiveTab("top")}
                      className={`flex items-center gap-2 rounded-2xl px-5 py-2.5 text-sm font-semibold transition ${
                        activeTab === "top"
                          ? "bg-violet-600 text-white shadow-lg shadow-violet-600/30"
                          : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-white"
                      }`}
                    >
                      <span>🔥 Топ клипов (75+)</span>
                      <span className="rounded-full bg-white/20 px-2 py-0.5 text-xs font-bold">
                        {topClips.length}
                      </span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setActiveTab("archive")}
                      className={`flex items-center gap-2 rounded-2xl px-5 py-2.5 text-sm font-semibold transition ${
                        activeTab === "archive"
                          ? "bg-violet-600 text-white shadow-lg shadow-violet-600/30"
                          : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-white"
                      }`}
                    >
                      <span>📁 Архив (&lt;75)</span>
                      <span className="rounded-full bg-white/20 px-2 py-0.5 text-xs font-bold">
                        {archiveClips.length}
                      </span>
                    </button>
                  </div>

                  {displayedClips.length === 0 ? (
                    <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-8 text-center text-zinc-400">
                      {activeTab === "top"
                        ? "В этой выборке нет клипов со скором 75+. Проверьте вкладку «Архив (<75)». "
                        : "В архиве пока пусто: все найденные моменты набрали более 75 баллов!"}
                    </div>
                  ) : (
                    <div className="grid gap-6 md:grid-cols-2">
                      {displayedClips.map((fragment, index) => (
                        <FragmentCard
                          key={fragment.id}
                          fragment={fragment}
                          index={index}
                          sourceUrl={sourceUrl}
                          apiUrl={API_URL}
                          youtubePreviewUrl={youtubePreviewUrl}
                        />
                      ))}
                    </div>
                  )}
                </>
              );
            })()}
          </section>
        )}

      </div>
    </main>
  );
}