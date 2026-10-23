"use client";

import { useState } from "react";
import { VideoPlayer } from "./VideoPlayer";
import { TimeRangeSlider } from "./TimeRangeSlider";

export interface FragmentData {
  id: number;
  title: string;
  start_time: number;
  end_time: number;
  duration: number;
  virality_score?: number;
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
}

export function FragmentCard({
  fragment,
  index,
  sourceUrl,
  apiUrl,
  youtubePreviewUrl,
}: FragmentCardProps) {
  const [showCriticism, setShowCriticism] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const [currentStart, setCurrentStart] = useState(fragment.start_time);
  const [currentEnd, setCurrentEnd] = useState(fragment.end_time);

  const score = fragment.virality_score ?? 75;

  const getScoreBadgeColor = (val: number) => {
    if (val >= 80) return "bg-emerald-500/10 text-emerald-400 border-emerald-500/30";
    if (val >= 70) return "bg-amber-500/10 text-amber-400 border-amber-500/30";
    return "bg-zinc-500/10 text-zinc-400 border-zinc-700";
  };

  const handleDownload = async () => {
    setIsDownloading(true);
    try {
      const url =
        fragment.download_url ?? `${apiUrl}/api/v1/fragments/${fragment.id}/download`;

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
            {formatTime(currentStart)} — {formatTime(currentEnd)}
          </span>
        </div>

        <div className="my-4">
          <VideoPlayer
            streamUrl={fragment.stream_url}
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
              className="text-xs text-zinc-500 hover:text-zinc-300 flex items-center gap-1 transition"
            >
              <span>{showCriticism ? "▲ Скрыть рецензию критика" : "▼ Рецензия состязательного критика"}</span>
            </button>

            {showCriticism && (
              <div className="mt-2 rounded-xl bg-zinc-900 border border-zinc-800 p-3 text-xs text-zinc-400 leading-relaxed">
                {fragment.internal_criticism}
              </div>
            )}
          </div>
        )}

        <TimeRangeSlider
          fragmentId={fragment.id}
          initialStart={fragment.start_time}
          initialEnd={fragment.end_time}
          apiUrl={apiUrl}
          onAdjusted={(newStart, newEnd) => {
            setCurrentStart(newStart);
            setCurrentEnd(newEnd);
          }}
        />
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