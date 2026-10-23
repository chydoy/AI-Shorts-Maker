"use client";

import { useState } from "react";

interface TimeRangeSliderProps {
  fragmentId: number;
  initialStart: number;
  initialEnd: number;
  apiUrl: string;
  onAdjusted?: (newStart: number, newEnd: number) => void;
}

export function TimeRangeSlider({
  fragmentId,
  initialStart,
  initialEnd,
  apiUrl,
  onAdjusted,
}: TimeRangeSliderProps) {
  const [start, setStart] = useState(initialStart);
  const [end, setEnd] = useState(initialEnd);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState("");

  const duration = +(end - start).toFixed(1);
  const isValid = start < end && duration >= 5 && duration <= 65;

  const formatMs = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = (sec % 60).toFixed(1);
    return `${mins}:${parseFloat(secs) < 10 ? "0" : ""}${secs}`;
  };

  const handleStartChange = (val: number) => {
    setError("");
    const newStart = Math.min(val, end - 0.1);
    setStart(+newStart.toFixed(1));
  };

  const handleEndChange = (val: number) => {
    setError("");
    const newEnd = Math.max(val, start + 0.1);
    setEnd(+newEnd.toFixed(1));
  };

  const saveAdjustment = async () => {
    if (!isValid) {
      setError("Длительность должна быть от 5 до 65 секунд.");
      return;
    }

    setIsSaving(true);
    setStatusMessage("Сохранение границ...");

    try {
      const res = await fetch(`${apiUrl}/api/v1/fragments/${fragmentId}/adjust`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          adjusted_start_time: start,
          adjusted_end_time: end,
        }),
      });

      if (!res.ok) throw new Error("Не удалось обновить границы");

      setStatusMessage("Границы успешно обновлены!");
      if (onAdjusted) onAdjusted(start, end);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка обновления");
    } finally {
      setIsSaving(false);
      setTimeout(() => setStatusMessage(""), 3000);
    }
  };

  return (
    <div className="mt-4 rounded-xl bg-zinc-900/90 p-4 border border-zinc-800">
      <div className="flex justify-between items-center mb-2 text-xs text-zinc-400">
        <span className="font-semibold text-zinc-300">Точная подгонка границ (шаг 100 мс)</span>
        <span className={`font-mono ${isValid ? "text-violet-400" : "text-red-400"}`}>
          Длина: {duration}с {!isValid && "(нужно 5–65с)"}
        </span>
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <span className="w-12 text-xs text-zinc-500">Старт:</span>
          <input
            type="range"
            min={Math.max(0, initialStart - 10)}
            max={initialEnd - 5}
            step={0.1}
            value={start}
            onChange={(e) => handleStartChange(parseFloat(e.target.value))}
            className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-violet-500"
          />
          <span className="font-mono text-xs w-16 text-right text-zinc-300">
            {formatMs(start)}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="w-12 text-xs text-zinc-500">Конец:</span>
          <input
            type="range"
            min={start + 5}
            max={initialEnd + 15}
            step={0.1}
            value={end}
            onChange={(e) => handleEndChange(parseFloat(e.target.value))}
            className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-violet-500"
          />
          <span className="font-mono text-xs w-16 text-right text-zinc-300">
            {formatMs(end)}
          </span>
        </div>
      </div>

      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
      {statusMessage && <p className="mt-2 text-xs text-green-400">{statusMessage}</p>}

      <div className="mt-3 flex justify-end">
        <button
          type="button"
          onClick={saveAdjustment}
          disabled={!isValid || isSaving}
          className="rounded-lg bg-zinc-800 hover:bg-violet-600 px-3 py-1.5 text-xs font-semibold text-zinc-200 hover:text-white transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSaving ? "Применение..." : "Применить изменения"}
        </button>
      </div>
    </div>
  );
}