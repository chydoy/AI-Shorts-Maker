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

type TaskResponse = {
  id: number;
  status: string;
  youtube_url: string;
  fragments_count: number;
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

  const statusText = useMemo(() => {
    const labels: Record<string, string> = {
      idle: "",
      pending: "Задача поставлена в очередь…",
      downloading: "Скачиваем аудиодорожку…",
      transcribing: "Распознаём речь…",
      analyzing: "Ищем лучшие моменты с помощью AI…",
      completed: "Готово!",
      error: "Обработка завершилась с ошибкой.",
    };
    return labels[status] ?? status;
  }, [status]);

useEffect(() => {
    if (!task?.task_id || status === "completed" || status === "error") {
      return;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const response = await fetch(
          `${API_URL}/api/v1/tasks/${task.task_id}`,
          { cache: "no-store" },
        );

        if (!response.ok) throw new Error("Не удалось получить статус задачи.");

        const data: TaskResponse = await response.json();

        if (cancelled) return;

        setSourceUrl(data.youtube_url);

        if (data.status === "completed") {
          const fragmentsResponse = await fetch(
            `${API_URL}/api/v1/tasks/${task.task_id}/fragments`,
            { cache: "no-store" },
          );

          if (!fragmentsResponse.ok) {
            throw new Error("Не удалось загрузить найденные фрагменты.");
          }

          const fragmentsData: FragmentsResponse =
            await fragmentsResponse.json();

          if (!cancelled) {
            // Сохраняем фрагменты и обновляем статус одновременно,
            // чтобы отмена эффекта не происходила до сохранения данных
            setFragments(fragmentsData.fragments);
            setStatus("completed");
            setLoading(false);
          }
        } else if (data.status === "error") {
          if (!cancelled) {
            setStatus("error");
            setError("Celery не смог обработать видео. Проверьте логи worker.");
            setLoading(false);
          }
        } else {
          if (!cancelled) {
            setStatus(data.status);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Неизвестная ошибка.",
          );
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

          {status !== "idle" && !error && (
            <div className="mt-5 rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="font-semibold">{statusText}</p>
                  {task && (
                    <p className="mt-1 text-sm text-zinc-500">
                      Задача #{task.task_id}
                    </p>
                  )}
                </div>
                {loading && (
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-600 border-t-violet-400" />
                )}
              </div>

              {loading && (
                <div className="mt-4 h-2 overflow-hidden rounded-full bg-zinc-800">
                  <div className="h-full w-1/2 animate-pulse rounded-full bg-violet-500" />
                </div>
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