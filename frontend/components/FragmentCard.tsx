"use client";

import { useState } from "react";
import { VideoPlayer } from "./VideoPlayer";

export interface FragmentData {
  id: number;
  title: string;
  start_time: number;
  end_time: number;
  duration: number;
  virality_score?: number;
  hook_score?: number;
  autonomy_score?: number;
  punchline_score?: number;
  viral_multiplier?: number;
  hook_reason?: string;
  internal_criticism?: string;
  first_words?: string;
  last_words?: string;
  stream_url?: string;
  download_url?: string;
  summary?: string;
  reasoning?: string;
}

interface FragmentCardProps {
  fragment: FragmentData;
  index: number;
  sourceUrl: string;
  apiUrl: string;
  youtubePreviewUrl: (sourceUrl: string, start: number) => string;
  onOpenStudio?: (fragment: FragmentData) => void;
}

export function FragmentCard({
  fragment,
  index,
  sourceUrl,
  apiUrl,
  youtubePreviewUrl,
  onOpenStudio,
}: FragmentCardProps) {
  const [showCriticism, setShowCriticism] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const currentStart = fragment.start_time;
  const currentEnd = fragment.end_time;

  const score = fragment.virality_score ?? 75;
  const hookScore = fragment.hook_score ?? Math.min(30, Math.round(score * 0.30));
  const autonomyScore = fragment.autonomy_score ?? Math.min(30, Math.round(score * 0.30));
  const punchlineScore = fragment.punchline_score ?? Math.min(25, Math.round(score * 0.25));
  const viralMultiplier = fragment.viral_multiplier ?? Math.max(0, score - (hookScore + autonomyScore + punchlineScore));

  const getScoreBadgeColor = (val: number) => {
    if (val >= 80) return "bg-emerald-500/10 text-emerald-400 border-emerald-500/30";
    if (val >= 70) return "bg-amber-500/10 text-amber-400 border-amber-500/30";
    return "bg-zinc-500/10 text-zinc-400 border-zinc-700";
  };

  const resolveBackendUrl = (url?: string) => {
    if (!url) return undefined;
    if (url.startsWith("http://") || url.startsWith("https://")) return url;
    const cleanBase = apiUrl.replace(/\/+$/, "");
    const cleanPath = url.startsWith("/") ? url : `/${url}`;
    return `${cleanBase}${cleanPath}`;
  };

  const videoSrc = resolveBackendUrl(fragment.stream_url);

  const handleDownload = async () => {
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

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <article className="flex flex-col justify-between rounded-3xl border border-zinc-800 bg-zinc-950 p-6 transition hover:border-zinc-700">
      <div>
        <div className="mb-4 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-violet-500/10 px-3 py-1 text-xs font-semibold text-violet-300">
              #{index + 1}
            </span>
            <span
              className={`rounded-full border px-3 py-1 text-xs font-bold ${getScoreBadgeColor(
                score,
              )}`}
            >
              ★ {score}/100 Virality
            </span>
          </div>

          <span className="font-mono text-sm text-zinc-400">
            {formatTime(currentStart)} – {formatTime(currentEnd)}
          </span>
        </div>

        <div className="my-4">
          <VideoPlayer
            streamUrl={videoSrc}
            previewUrl={youtubePreviewUrl(sourceUrl, currentStart)}
            title={fragment.title}
          />
        </div>

        <h3 className="text-lg font-semibold leading-snug text-white mt-2">
          {fragment.title}
        </h3>

        {(fragment.first_words || fragment.summary) && (
          <p className="mt-2 text-sm italic text-zinc-400">
            «{fragment.first_words ?? fragment.summary}…»
          </p>
        )}

        {/* Структурированный блок вирусности (суб-баллы хука, автономности, панчлайна) */}
        <div className="mt-4 rounded-2xl bg-zinc-900/90 border border-zinc-800/80 p-4">
          <div className="text-xs font-bold uppercase tracking-wider text-zinc-400 mb-3 flex items-center justify-between">
            <span>Анализ вирусного потенциала</span>
            <span className="font-mono text-violet-400">{score} баллов</span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-xl bg-zinc-950/70 p-2.5 border border-zinc-800">
              <div className="flex justify-between items-center text-zinc-400 mb-1">
                <span>🎯 Сила хука:</span>
                <span className="font-semibold text-violet-300">{hookScore}/30</span>
              </div>
              <div className="h-1.5 w-full bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-violet-500 rounded-full"
                  style={{ width: `${Math.min(100, (hookScore / 30) * 100)}%` }}
                />
              </div>
            </div>

            <div className="rounded-xl bg-zinc-950/70 p-2.5 border border-zinc-800">
              <div className="flex justify-between items-center text-zinc-400 mb-1">
                <span>🌐 Автономность:</span>
                <span className="font-semibold text-sky-300">{autonomyScore}/30</span>
              </div>
              <div className="h-1.5 w-full bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-sky-500 rounded-full"
                  style={{ width: `${Math.min(100, (autonomyScore / 30) * 100)}%` }}
                />
              </div>
            </div>

            <div className="rounded-xl bg-zinc-950/70 p-2.5 border border-zinc-800">
              <div className="flex justify-between items-center text-zinc-400 mb-1">
                <span>⚡ Панчлайн:</span>
                <span className="font-semibold text-emerald-300">{punchlineScore}/25</span>
              </div>
              <div className="h-1.5 w-full bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full"
                  style={{ width: `${Math.min(100, (punchlineScore / 25) * 100)}%` }}
                />
              </div>
            </div>

            <div className="rounded-xl bg-zinc-950/70 p-2.5 border border-zinc-800">
              <div className="flex justify-between items-center text-zinc-400 mb-1">
                <span>🚀 Множитель:</span>
                <span className="font-semibold text-amber-300">{viralMultiplier}/15</span>
              </div>
              <div className="h-1.5 w-full bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-amber-500 rounded-full"
                  style={{ width: `${Math.min(100, (viralMultiplier / 15) * 100)}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        {fragment.hook_reason && (
          <div className="mt-3 rounded-xl bg-violet-950/20 border border-violet-900/40 p-3 text-xs text-violet-300">
            <span className="font-semibold block mb-0.5">🔥 Почему это залетит (Хук):</span>
            {fragment.hook_reason}
          </div>
        )}

        {fragment.internal_criticism && (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setShowCriticism(!showCriticism)}
              className="text-xs text-zinc-400 hover:text-zinc-200 flex items-center gap-1 transition"
            >
              <span>{showCriticism ? "▲ Скрыть рецензию состязательного критика" : "▼ Рецензия состязательного критика (Self-Debate)"}</span>
            </button>

            {showCriticism && (
              <div className="mt-2 rounded-xl bg-zinc-900 border border-zinc-800 p-3 text-xs text-zinc-300 leading-relaxed space-y-1">
                <span className="font-semibold text-zinc-400 block mb-1">
                  ⚖ Вердикт критика:
                </span>
                {fragment.internal_criticism}
              </div>
            )}
          </div>
        )}

        {/* Кнопка перехода в полноэкранную студию редактирования */}
        {onOpenStudio && (
          <div className="mt-4">
            <button
              type="button"
              onClick={() => onOpenStudio(fragment)}
              className="w-full flex items-center justify-center gap-2 rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-2 text-xs font-semibold text-zinc-200 hover:bg-violet-600 hover:text-white hover:border-violet-500 transition"
            >
              <span>✂ Открыть в студии монтажа 9:16</span>
            </button>
          </div>
        )}
      </div>

      <div className="mt-6 flex items-center justify-between border-t border-zinc-800 pt-4">
        <span className="text-xs text-zinc-500">
          Длительность: {Math.round(currentEnd - currentStart)} сек.
        </span>

        <button
          type="button"
          onClick={handleDownload}
          disabled={isDownloading}
          className="flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-violet-500 disabled:opacity-50"
        >
          {isDownloading ? (
            <>
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Скачивание...
            </>
          ) : (
            <>⬇ Скачать MP4</>
          )}
        </button>
      </div>
    </article>
  );
}