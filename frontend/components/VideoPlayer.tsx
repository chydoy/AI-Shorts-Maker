"use client";

import { useEffect, useRef, useState } from "react";

interface VideoPlayerProps {
  streamUrl?: string | null;
  previewUrl: string;
  title: string;
  autoPlay?: boolean;
}

export function VideoPlayer({
  streamUrl,
  previewUrl,
  title,
  autoPlay = false,
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [isRetrying, setIsRetrying] = useState(false);

  useEffect(() => {
    if (autoPlay && videoRef.current && streamUrl && !hasError) {
      videoRef.current
        .play()
        .then(() => setIsPlaying(true))
        .catch(() => setIsPlaying(false));
    }
  }, [autoPlay, streamUrl, hasError]);

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      videoRef.current.play();
      setIsPlaying(true);
    }
  };

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration);
      setHasError(false);
      setIsRetrying(false);
    }
  };

  const handleVideoError = () => {
    if (retryCount < 4) {
      setIsRetrying(true);
      setTimeout(() => {
        setRetryCount((prev) => prev + 1);
        setIsRetrying(false);
        if (videoRef.current) {
          videoRef.current.load();
        }
      }, 2000);
    } else {
      setHasError(true);
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      setCurrentTime(time);
    }
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen().catch(() => {});
      setIsFullscreen(false);
    }
  };

  const formatSec = (sec: number) => {
    const s = Math.floor(sec);
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m}:${rem.toString().padStart(2, "0")}`;
  };

  if (isRetrying) {
    return (
      <div className="relative aspect-[9/16] w-full max-w-[280px] mx-auto overflow-hidden rounded-2xl bg-zinc-900 border border-zinc-800 flex flex-col items-center justify-center p-4 text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-600 border-t-violet-400 mb-3" />
        <p className="text-sm font-medium text-zinc-300 mb-1">Загрузка видео...</p>
        <p className="text-xs text-zinc-500">Подключение видеопотока...</p>
      </div>
    );
  }

  if (!streamUrl || hasError) {
    return (
      <div className="relative aspect-[9/16] w-full max-w-[280px] mx-auto overflow-hidden rounded-2xl bg-zinc-900 border border-zinc-800 flex flex-col items-center justify-center p-4 text-center">
        <div className="rounded-full bg-violet-500/20 p-4 mb-3">
          <svg className="w-8 h-8 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <p className="text-sm font-medium text-zinc-300 mb-1">Рендеринг видео...</p>
        <p className="text-xs text-zinc-500 mb-4">Файл еще подготавливается на сервере</p>
        <a
          href={previewUrl}
          target="_blank"
          rel="noreferrer"
          className="rounded-xl bg-violet-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-violet-500"
        >
          Предпросмотр YouTube ↗
        </a>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="group relative aspect-[9/16] w-full max-w-[280px] mx-auto overflow-hidden rounded-2xl bg-black border border-zinc-800 shadow-xl"
    >
      <video
        ref={videoRef}
        src={streamUrl}
        aria-label={title}
        playsInline
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onError={handleVideoError}
        onClick={togglePlay}
        className="h-full w-full object-cover cursor-pointer"
      />

      <div
        className={`absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-black/30 flex flex-col justify-between p-3 transition-opacity duration-200 ${
          isPlaying ? "opacity-0 group-hover:opacity-100" : "opacity-100"
        }`}
      >
        <div className="flex justify-between items-center text-xs text-zinc-300">
          <span className="truncate max-w-[180px] font-medium">{title}</span>
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={0}
              max={duration || 100}
              step={0.1}
              value={currentTime}
              onChange={handleSeek}
              className="w-full h-1.5 bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-violet-500"
            />
          </div>

          <div className="flex items-center justify-between text-xs text-zinc-400">
            <span>{formatSec(currentTime)} / {formatSec(duration)}</span>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={togglePlay}
                className="p-1 rounded bg-white/10 hover:bg-white/20 text-white transition"
              >
                {isPlaying ? "⏸" : "▶"}
              </button>
              <button
                type="button"
                onClick={toggleFullscreen}
                className="p-1 rounded bg-white/10 hover:bg-white/20 text-white transition"
              >
                {isFullscreen ? "⤢" : "⤡"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}