import React, { useEffect, useMemo, useRef, useState } from "react";
import { Play, Pause, RotateCcw } from "lucide-react";
import { StepResult } from "../api/types";

interface Props {
  results: StepResult[];
  onFrameClick?: (path: string) => void;
}

const SPEEDS = [0.5, 1, 2] as const;
const BASE_FRAME_MS = 900;

/**
 * Plays a run back from its per-step screenshots.
 *
 * Chrome only paints — and therefore only films — a window that is in front, so
 * a headed run left in the background can still produce an unusable video file.
 * The screenshots are taken by the runner itself and are always there, so this
 * gives every run a replay to watch regardless of what the recorder managed.
 */
export const Filmstrip = ({ results, onFrameClick }: Props) => {
  const frames = useMemo(
    () => results.filter((r) => !!r.screenshot_path),
    [results],
  );
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<number>(1);
  const timer = useRef<number | null>(null);

  // Keep the cursor inside the strip when a running test adds frames.
  useEffect(() => {
    if (index > frames.length - 1) setIndex(Math.max(0, frames.length - 1));
  }, [frames.length, index]);

  useEffect(() => {
    if (!playing || frames.length < 2) return;
    timer.current = window.setTimeout(() => {
      setIndex((current) => {
        if (current >= frames.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, BASE_FRAME_MS / speed);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [playing, index, speed, frames.length]);

  if (frames.length === 0) {
    return (
      <p className="text-sm text-ink-muted">
        This run captured no screenshots, so there is nothing to replay yet.
      </p>
    );
  }

  const current = frames[Math.min(index, frames.length - 1)];
  const atEnd = index >= frames.length - 1;

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => onFrameClick?.(current.screenshot_path!)}
        className="block w-full rounded-xl overflow-hidden border border-line bg-canvas"
      >
        <img
          src={`/${current.screenshot_path}`}
          alt={`Step ${index + 1} of ${frames.length}`}
          className="w-full max-h-[62vh] object-contain"
        />
      </button>

      <div className="flex items-center gap-3">
        <button
          onClick={() =>
            atEnd && !playing
              ? (setIndex(0), setPlaying(true))
              : setPlaying((p) => !p)
          }
          className="btn-secondary !py-1.5 !px-3"
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? (
            <Pause className="w-4 h-4" />
          ) : atEnd ? (
            <RotateCcw className="w-4 h-4" />
          ) : (
            <Play className="w-4 h-4" />
          )}
        </button>

        <input
          type="range"
          min={0}
          max={frames.length - 1}
          value={Math.min(index, frames.length - 1)}
          onChange={(e) => {
            setPlaying(false);
            setIndex(Number(e.target.value));
          }}
          aria-label="Scrub through the run"
          className="flex-1 accent-primary-500"
        />

        <span className="text-xs font-mono text-ink-muted tabular-nums w-16 text-right">
          {index + 1}/{frames.length}
        </span>

        <div className="flex gap-1">
          {SPEEDS.map((s) => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`px-2 py-1 rounded-lg text-[11px] font-semibold ${
                speed === s
                  ? "bg-primary-50 text-primary-600"
                  : "text-ink-muted hover:text-ink"
              }`}
            >
              {s}×
            </button>
          ))}
        </div>
      </div>

      {current.error_message && (
        <pre className="rounded-xl bg-rose-50 border border-rose-100 px-4 py-3 text-xs text-rose-600 font-mono whitespace-pre-wrap overflow-x-auto">
          {current.error_message}
        </pre>
      )}
    </div>
  );
};
