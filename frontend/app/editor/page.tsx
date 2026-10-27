"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { VideoPlayer } from "../../components/VideoPlayer";
import { FragmentData } from "../../components/FragmentCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function EditorStudioContent() {
  const searchParams = useSearchParams();
  const fragmentIdStr = searchParams.get("fragmentId");
  const querySourceUrl = searchParams.get("sourceUrl") || "";

  const [fragment, setFragment] = useState<FragmentData | null>(null);
  const [sourceUrl, setSourceUrl] = useState(querySourceUrl);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(0);
  const [isSaving, setIsSaving] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [editError, setEditError] = useState("");

  useEffect(() => {
    if (!fragmentIdStr) {
      setLoadError("Идентификатор клипа не передан в URL.");
      setLoading(false);
      return;
    }

    const fetchFragment = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/fragments/${fragmentIdStr}`, {
          cache: "no-store",
        });
        if (!res.ok) {
          throw new Error("Не удалось загрузить данные клипа с сервера.");
        }
        const data: FragmentData = await res.json();
        setFragment(data);
        const effStart = data.start_time;
        const effEnd = data.end_time;
        setStart(effStart);
        setEnd(effEnd);

        if (!sourceUrl && (data as any).youtube_url) {
          setSourceUrl((data as any).youtube_url);
        }
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : "Ошибка загрузки клипа");
      } finally {
        setLoading(false);
      }
    };

    fetchFragment();
  }, [fragmentIdStr]);

  const duration = +(end - start).toFixed(1);
  const isValid = start < end && duration >= 5.0 && duration <= 65.0;

  const formatSec = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = (sec % 60).toFixed(1);
    return `${mins}:${parseFloat(secs) < 10 ? "0" : ""}${secs}`;
  };

  const adjustStart = (delta: number) => {
    setEditError("");
    const updated = Math.max(0, +(start + delta).toFixed(1));
    if (updated < end - 1) {
      setStart(updated);
    }
  };

  const adjustEnd = (delta: number) => {
    setEditError("");
    const updated = +(end + delta).toFixed(1);
    if (updated > start + 1) {
      setEnd(updated);
    }
  };

  const resolveBackendUrl = (url?: string) => {
    if (!url) return undefined;
    if (url.startsWith("http://") || url.startsWith("https://")) return url;
    const cleanBase = API_URL.replace(/\/+$/, "");
    const cleanPath = url.startsWith("/") ? url : `/${url}`;
    return `${cleanBase}${cleanPath}`;
  };

  const handleSave = async () => {
    if (!isValid || !fragment) {
      setEditError("Длительность клипа обязана составлять от 5 до 65 секунд.");
      return;
    }

    setIsSaving(true);
    setStatusMessage("Сохранение и перенарезка клипа...");
    setEditError("");

    try {
      const res = await fetch(`${API_URL}/api/v1/fragments/${fragment.id}/adjust`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          adjusted_start_time: start,
          adjusted_end_time: end,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Не удалось обновить границы клипа.");
      }

      setStatusMessage("Границы сохранены! Запущен фоновый перерендеринг в Celery.");
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Ошибка сохранения");
    } finally {
      setIsSaving(false);
      setTimeout(() => setStatusMessage(""), 5000);
    }
  };

  const handleDownload = async () => {
    if (!fragment) return;
    setIsDownloading(true);
    try {
      const defaultDownloadPath = `/api/v1/fragments/${fragment.id}/download`;
      const url = resolveBackendUrl(fragment.download_url) ?? resolveBackendUrl(defaultDownloadPath)!;

      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `short_${fragment.id}.mp4`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch {
      alert("Не удалось скачать видео");
    } finally {
      setTimeout(() => setIsDownloading(false), 1500);
    }
  };

  const youtubePreview = (url: string, timeSec: number) => {
    try {
      const parsed = new URL(url);
      const host = parsed.hostname.replace(/^www\./, "");
      let videoId = "";
      if (host === "youtu.be") {
        videoId = parsed.pathname.replace(/^\//, "");
      } else if (parsed.searchParams.has("v")) {
        videoId = parsed.searchParams.get("v") || "";
      }
      if (videoId) {
        return `https://www.youtube.com/watch?v=${videoId}&t=${Math.floor(timeSec)}s`;
      }
    } catch {}
    return url;
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-black text-white p-6">
        <div className="flex items-center gap-3 text-sm text-zinc-400">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
          <span>Загрузка студии монтажа...</span>
        </div>
      </div>
    );
  }

  if (loadError || !fragment) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-black text-white p-6">
        <div className="max-w-md rounded-2xl border border-red-800 bg-red-950/40 p-6 text-center">
          <h2 className="text-lg font-bold text-red-300 mb-2">Ошибка открытия студии</h2>
          <p className="text-sm text-zinc-400 mb-5">{loadError || "Фрагмент не найден"}</p>
          <button
            type="button"
            onClick={() => window.close()}
            className="rounded-xl bg-zinc-800 px-4 py-2 text-xs font-semibold text-white hover:bg-zinc-700"
          >
            Закрыть вкладку
          </button>
        </div>
      </div>
    );
  }

  const score = fragment.virality_score ?? 75;
  const hookScore = fragment.hook_score ?? Math.min(30, Math.round(score * 0.30));
  const autonomyScore = fragment.autonomy_score ?? Math.min(30, Math.round(score * 0.30));
  const punchlineScore = fragment.punchline_score ?? Math.min(25, Math.round(score * 0.25));
  const viralMultiplier = fragment.viral_multiplier ?? Math.max(0, score - (hookScore + autonomyScore + punchlineScore));
  const videoSrc = resolveBackendUrl(fragment.stream_url);

  return (
    <div className="min-h-screen bg-black text-white flex flex-col">
      {/* Шапка студии монтажа */}
      <header className="sticky top-0 z-30 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur-md px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => window.close()}
            className="rounded-xl border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-400 hover:bg-zinc-800 hover:text-white transition"
          >
            ← Закрыть вкладку
          </button>
          <div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-violet-400 block">
              Студия монтажа 9:16
            </span>
            <h1 className="text-base font-bold text-white truncate max-w-lg">
              {fragment.title}
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleDownload}
            disabled={isDownloading}
            className="flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800 transition disabled:opacity-50"
          >
            {isDownloading ? "Загрузка..." : "⬇ Скачать MP4"}
          </button>

          <button
            type="button"
            onClick={handleSave}
            disabled={!isValid || isSaving}
            className="flex items-center gap-2 rounded-xl bg-violet-600 px-5 py-2 text-xs font-semibold text-white hover:bg-violet-500 transition disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-violet-900/30"
          >
            {isSaving ? "Сохранение..." : "✂ Сохранить и перенарезать"}
          </button>
        </div>
      </header>

      {/* Основная рабочая область */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Левая колонка: вертикальный плеер 9:16 */}
          <div className="lg:col-span-5 flex flex-col items-center">
            <div className="w-full max-w-[320px]">
              <VideoPlayer
                streamUrl={videoSrc}
                previewUrl={youtubePreview(sourceUrl, start)}
                title={fragment.title}
                autoPlay={false}
              />
            </div>
            <p className="mt-3 text-xs text-zinc-500 text-center">
              Вертикальный формат 9:16 с умным кадрированием спикера
            </p>
          </div>

          {/* Правая колонка: управление таймкодами и аудит */}
          <div className="lg:col-span-7 flex flex-col gap-6">
            {/* Карточка длительности */}
            <div className="flex items-center justify-between rounded-2xl bg-zinc-900/90 border border-zinc-800 p-4">
              <div>
                <span className="text-xs text-zinc-400 block">Хронометраж клипа:</span>
                <span className={`font-mono text-xl font-bold ${isValid ? "text-violet-400" : "text-red-400"}`}>
                  {duration} сек.
                </span>
              </div>
              <span className="text-xs text-zinc-500">
                (допустимо от 5 до 65 секунд)
              </span>
            </div>

            {/* Сообщения об успехе или ошибке */}
            {statusMessage && (
              <div className="rounded-xl border border-emerald-800 bg-emerald-950/40 p-3.5 text-xs text-emerald-300">
                ✓ {statusMessage}
              </div>
            )}
            {editError && (
              <div className="rounded-xl border border-red-800 bg-red-950/40 p-3.5 text-xs text-red-300">
                ✕ {editError}
              </div>
            )}

            {/* Блок настройки таймлайна */}
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5 space-y-6">
              <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-300">
                Точная подгонка границ таймкода
              </h2>

              {/* Начало клипа */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-zinc-300">
                    Старт: {formatSec(start)} ({start} с)
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => adjustStart(-1.0)}
                      className="rounded-lg bg-zinc-800 hover:bg-zinc-700 px-2.5 py-1 text-xs text-zinc-300"
                    >
                      –1с
                    </button>
                    <button
                      type="button"
                      onClick={() => adjustStart(-0.1)}
                      className="rounded-lg bg-zinc-800 hover:bg-zinc-700 px-2 py-1 text-xs text-zinc-300"
                    >
                      –100мс
                    </button>
                    <button
                      type="button"
                      onClick={() => adjustStart(0.1)}
                      className="rounded-lg bg-zinc-800 hover:bg-zinc-700 px-2 py-1 text-xs text-zinc-300"
                    >
                      +100мс
                    </button>
                    <button
                      type="button"
                      onClick={() => adjustStart(1.0)}
                      className="rounded-lg bg-zinc-800 hover:bg-zinc-700 px-2.5 py-1 text-xs text-zinc-300"
                    >
                      +1с
                    </button>
                  </div>
                </div>
                <input
                  type="range"
                  min={Math.max(0, +(start - 20).toFixed(1))}
                  max={Math.max(start + 0.1, +(end - 1).toFixed(1))}
                  step={0.1}
                  value={start}
                  onChange={(e) => {
                    setEditError("");
                    const val = parseFloat(e.target.value);
                    if (val < end - 1) setStart(+val.toFixed(1));
                  }}
                  className="w-full h-2 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-violet-500"
                />
              </div>

              {/* Финал клипа */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-zinc-300">
                    Финал: {formatSec(end)} ({end} с)
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => adjustEnd(-1.0)}
                      className="rounded-lg bg-zinc-800 hover:bg-zinc-700 px-2.5 py-1 text-xs text-zinc-300"
                    >
                      –1с
                    </button>
                    <button
                      type="button"
                      onClick={() => adjustEnd(-0.1)}
                      className="rounded-lg bg-zinc-800 hover:bg-zinc-700 px-2 py-1 text-xs text-zinc-300"
                    >
                      –100мс
                    </button>
                    <button
                      type="button"
                      onClick={() => adjustEnd(0.1)}
                      className="rounded-lg bg-zinc-800 hover:bg-zinc-700 px-2 py-1 text-xs text-zinc-300"
                    >
                      +100мс
                    </button>
                    <button
                      type="button"
                      onClick={() => adjustEnd(1.0)}
                      className="rounded-lg bg-zinc-800 hover:bg-zinc-700 px-2.5 py-1 text-xs text-zinc-300"
                    >
                      +1с
                    </button>
                  </div>
                </div>
                <input
                  type="range"
                  min={Math.max(0, +(start + 1).toFixed(1))}
                  max={+(end + 25).toFixed(1)}
                  step={0.1}
                  value={end}
                  onChange={(e) => {
                    setEditError("");
                    const val = parseFloat(e.target.value);
                    if (val > start + 1) setEnd(+val.toFixed(1));
                  }}
                  className="w-full h-2 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-violet-500"
                />
              </div>
            </div>

            {/* Аналитика вирусности с единым цветом */}
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Оценка потенциала клипа
                </span>
                <span className="font-mono text-sm font-bold text-violet-400">
                  {score}/100 Virality Score
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="rounded-xl bg-zinc-950/80 p-3 border border-zinc-800">
                  <div className="flex justify-between items-center text-zinc-400 mb-1.5">
                    <span>🎯 Хук:</span>
                    <span className="font-semibold text-violet-300">{hookScore}/30</span>
                  </div>
                  <div className="h-1.5 w-full bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-violet-500 rounded-full"
                      style={{ width: `${Math.min(100, (hookScore / 30) * 100)}%` }}
                    />
                  </div>
                </div>

                <div className="rounded-xl bg-zinc-950/80 p-3 border border-zinc-800">
                  <div className="flex justify-between items-center text-zinc-400 mb-1.5">
                    <span>🌐 Смысл:</span>
                    <span className="font-semibold text-violet-300">{autonomyScore}/30</span>
                  </div>
                  <div className="h-1.5 w-full bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-violet-500 rounded-full"
                      style={{ width: `${Math.min(100, (autonomyScore / 30) * 100)}%` }}
                    />
                  </div>
                </div>

                <div className="rounded-xl bg-zinc-950/80 p-3 border border-zinc-800">
                  <div className="flex justify-between items-center text-zinc-400 mb-1.5">
                    <span>⚡ Финал:</span>
                    <span className="font-semibold text-violet-300">{punchlineScore}/25</span>
                  </div>
                  <div className="h-1.5 w-full bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-violet-500 rounded-full"
                      style={{ width: `${Math.min(100, (punchlineScore / 25) * 100)}%` }}
                    />
                  </div>
                </div>

                <div className="rounded-xl bg-zinc-950/80 p-3 border border-zinc-800">
                  <div className="flex justify-between items-center text-zinc-400 mb-1.5">
                    <span>🚀 Вирусность:</span>
                    <span className="font-semibold text-violet-300">{viralMultiplier}/15</span>
                  </div>
                  <div className="h-1.5 w-full bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-violet-500 rounded-full"
                      style={{ width: `${Math.min(100, (viralMultiplier / 15) * 100)}%` }}
                    />
                  </div>
                </div>
              </div>

              {fragment.hook_reason && (
                <div className="rounded-xl bg-violet-950/20 border border-violet-900/40 p-3 text-xs text-violet-300">
                  <span className="font-semibold block mb-0.5">🔥 Почему это залетит:</span>
                  {fragment.hook_reason}
                </div>
              )}

              {fragment.internal_criticism && (
                <div className="rounded-xl bg-zinc-950/80 border border-zinc-800 p-3 text-xs text-zinc-300">
                  <span className="font-semibold text-zinc-400 block mb-0.5">⚖ Вердикт критика:</span>
                  {fragment.internal_criticism}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default function EditorStudioPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-black text-white p-6">
          <div className="flex items-center gap-3 text-sm text-zinc-400">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
            <span>Загрузка страницы студии...</span>
          </div>
        </div>
      }
    >
      <EditorStudioContent />
    </Suspense>
  );
}
