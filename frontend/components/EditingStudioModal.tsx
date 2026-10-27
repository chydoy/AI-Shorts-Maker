"use client";

import { useEffect, useState } from "react";
import { FragmentData } from "./FragmentCard";
import { VideoPlayer } from "./VideoPlayer";

interface EditingStudioModalProps {
  fragment: FragmentData;
  sourceUrl: string;
  apiUrl: string;
  youtubePreviewUrl: (sourceUrl: string, start: number) => string;
  onClose: () => void;
  onSaved: (fragmentId: number, newStart: number, newEnd: number) => void;
}

export function EditingStudioModal({
  fragment,
  sourceUrl,
  apiUrl,
  youtubePreviewUrl,
  onClose,
  onSaved,
}: EditingStudioModalProps) {
  const [start, setStart] = useState(fragment.start_time);
  const [end, setEnd] = useState(fragment.end_time);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState("");

  const duration = +(end - start).toFixed(1);
  const isValid = start < end && duration >= 5.0 && duration <= 65.0;

  // Закрытие студии по клавише Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const formatSec = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = (sec % 60).toFixed(1);
    return `${mins}:${parseFloat(secs) < 10 ? "0" : ""}${secs}`;
  };

  const adjustStart = (delta: number) => {
    setError("");
    const updated = Math.max(0, +(start + delta).toFixed(1));
    if (updated < end - 1) {
      setStart(updated);
    }
  };

  const adjustEnd = (delta: number) => {
    setError("");
    const updated = +(end + delta).toFixed(1);
    if (updated > start + 1) {
      setEnd(updated);
    }
  };

  const resolveBackendUrl = (url?: string) => {
    if (!url) return undefined;
    if (url.startsWith("http://") || url.startsWith("https://")) return url;
    const cleanBase = apiUrl.replace(/\/+$/, "");
    const cleanPath = url.startsWith("/") ? url : `/${url}`;
    return `${cleanBase}${cleanPath}`;
  };

  const videoSrc = resolveBackendUrl(fragment.stream_url);

  const handleSave = async () => {
    if (!isValid) {
      setError("Длительность клипа обязана составлять от 5 до 65 секунд.");
      return;
    }

    setIsSaving(true);
    setStatusMessage("Отправка новых границ на рендеринг...");

    try {
      const res = await fetch(`${apiUrl}/api/v1/fragments/${fragment.id}/adjust`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          adjusted_start_time: start,
          adjusted_end_time: end,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail ?? "Не удалось обновить границы клипа");
      }

      setStatusMessage("Границы успешно обновлены! Клип отправлен на перерендеринг.");
      onSaved(fragment.id, start, end);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка обновления");
    } finally {
      setIsSaving(false);
      setTimeout(() => setStatusMessage(""), 4000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/95 backdrop-blur-md p-3 sm:p-6 overflow-y-auto">
      <div className="relative w-full max-w-5xl rounded-3xl border border-zinc-800 bg-zinc-950 p-6 sm:p-8 shadow-2xl flex flex-col gap-6">
        {/* Заголовок студии */}
        <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
          <div className="flex items-center gap-3">
            <span className="rounded-xl bg-violet-600/20 px-3 py-1 text-xs font-bold text-violet-400 border border-violet-500/30">
              Студия монтажа 9:16
            </span>
            <h2 className="text-xl font-bold text-white truncate max-w-[280px] sm:max-w-xl">
              {fragment.title}
            </h2>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-xl bg-zinc-900 px-3 py-1.5 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-white transition"
          >
            ✕ Закрыть [Esc]
          </button>
        </div>

        {/* Основная рабочая область: слева плеер 9:16, справа таймлайн */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-start">
          {/* Вертикальный плеер 9:16 */}
          <div className="md:col-span-5 flex flex-col items-center">
            <div className="w-full max-w-[280px]">
              <VideoPlayer
                streamUrl={videoSrc}
                previewUrl={youtubePreviewUrl(sourceUrl, start)}
                title={fragment.title}
                autoPlay={false}
              />
            </div>
            <p className="mt-3 text-xs text-zinc-500 text-center">
              Предпросмотр клипа в вертикальном формате 9:16
            </p>
          </div>

          {/* Инструменты управления таймкодами */}
          <div className="md:col-span-7 flex flex-col gap-5">
            {/* Карточки цитат начала и завершения */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4">
                <span className="text-xs font-semibold text-zinc-400 block mb-1">
                  🎯 Первые слова (Хук):
                </span>
                <p className="text-sm italic text-violet-300">
                  «{fragment.first_words || "Начало фрагмента"}»
                </p>
              </div>

              <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4">
                <span className="text-xs font-semibold text-zinc-400 block mb-1">
                  ⚡ Финальные слова (Финал):
                </span>
                <p className="text-sm italic text-emerald-300">
                  «{fragment.last_words || "Завершение мысли"}»
                </p>
              </div>
            </div>

            {/* Блок индикации длительности */}
            <div className="flex items-center justify-between rounded-2xl bg-zinc-900 border border-zinc-800 px-5 py-3">
              <span className="text-sm text-zinc-400">Итоговый хронометраж:</span>
              <div className="flex items-center gap-2">
                <span
                  className={`font-mono text-lg font-bold ${
                    isValid ? "text-violet-400" : "text-red-400"
                  }`}
                >
                  {duration} сек.
                </span>
                <span className="text-xs text-zinc-500">
                  (допустимо от 5 до 65 сек)
                </span>
              </div>
            </div>

            {/* Визуальная шкала таймлайна */}
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-5 space-y-5">
              {/* Старт таймкода */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-zinc-300">
                    Точка старта: {formatSec(start)} ({start} с)
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => adjustStart(-1.0)}
                      className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
                    >
                      –1с
                    </button>
                    <button
                      type="button"
                      onClick={() => adjustStart(-0.1)}
                      className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
                    >
                      –0.1с
                    </button>
                    <button
                      type="button"
                      onClick={() => adjustStart(0.1)}
                      className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
                    >
                      +0.1с
                    </button>
                    <button
                      type="button"
                      onClick={() => adjustStart(1.0)}
                      className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
                    >
                      +1с
                    </button>
                  </div>
                </div>

                <input
                  type="range"
                  min={Math.max(0, Math.min(start - 10, fragment.start_time - 30))}
                  max={Math.max(0.1, end - 1)}
                  step={0.1}
                  value={start}
                  onChange={(e) => setStart(+parseFloat(e.target.value).toFixed(1))}
                  className="w-full h-2 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-violet-500"
                />
              </div>

              {/* Конец таймкода */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-zinc-300">
                    Точка финиша: {formatSec(end)} ({end} с)
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => adjustEnd(-1.0)}
                      className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
                    >
                      –1с
                    </button>
                    <button
                      type="button"
                      onClick={() => adjustEnd(-0.1)}
                      className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
                    >
                      –0.1с
                    </button>
                    <button
                      type="button"
                      onClick={() => adjustEnd(0.1)}
                      className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
                    >
                      +0.1с
                    </button>
                    <button
                      type="button"
                      onClick={() => adjustEnd(1.0)}
                      className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
                    >
                      +1с
                    </button>
                  </div>
                </div>

                <input
                  type="range"
                  min={start + 1}
                  max={Math.max(end + 10, fragment.end_time + 30)}
                  step={0.1}
                  value={end}
                  onChange={(e) => setEnd(+parseFloat(e.target.value).toFixed(1))}
                  className="w-full h-2 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-violet-500"
                />
              </div>
            </div>

            {/* Сообщения об ошибках и статусе */}
            {error && (
              <div className="rounded-xl border border-red-900 bg-red-950/40 p-3 text-xs text-red-300">
                {error}
              </div>
            )}
            {statusMessage && (
              <div className="rounded-xl border border-emerald-900 bg-emerald-950/40 p-3 text-xs text-emerald-300">
                {statusMessage}
              </div>
            )}

            {/* Кнопка сохранения */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-xl border border-zinc-700 px-5 py-2.5 text-sm font-semibold text-zinc-300 hover:bg-zinc-900 transition"
              >
                Отмена
              </button>

              <button
                type="button"
                onClick={handleSave}
                disabled={!isValid || isSaving}
                className="flex items-center gap-2 rounded-xl bg-violet-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-violet-600/30"
              >
                {isSaving ? (
                  <>
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Сохранение...
                  </>
                ) : (
                  <>✂ Применить и перерендерить</>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
