import React, { useEffect } from 'react';
import { Evidence } from '../api/types';
import { X } from 'lucide-react';

interface Props {
  evidence: Evidence | null;
  screenshotPath: string | null;
  onClose: () => void;
}

export const EvidenceViewer = ({ evidence, screenshotPath, onClose }: Props) => {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  if (!evidence && !screenshotPath) return null;

  const url = (path: string) => `/${path}`;

  return (
    <dialog
      open
      aria-label={screenshotPath ? 'Screenshot preview' : `Evidence: ${evidence?.type}`}
      className="fixed inset-0 z-50 w-full h-full max-w-none max-h-none bg-ink/40 backdrop-blur-sm p-4 flex items-center justify-center"
    >
      <div className="card w-full max-w-5xl overflow-hidden shadow-pop flex flex-col max-h-full">
        <div className="flex justify-between items-center px-5 py-3.5 border-b border-line">
          <h3 className="text-sm font-semibold text-ink">
            {screenshotPath ? 'Screenshot' : `Evidence — ${evidence?.type.replace(/_/g, ' ')}`}
          </h3>
          <button onClick={onClose} aria-label="Close" className="btn-ghost !p-1.5">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-4 bg-canvas flex items-center justify-center min-h-[40vh]">
          {screenshotPath ? (
            <img
              src={url(screenshotPath)}
              alt="Step screenshot"
              className="max-w-full max-h-[72vh] object-contain rounded-xl border border-line bg-surface"
            />
          ) : evidence?.type === 'video' ? (
            // Silent screen capture of the run: no audio track, so no captions.
            <video
              src={url(evidence.file_path)}
              controls
              autoPlay
              muted
              aria-label="Silent screen recording of the test run"
              className="max-w-full max-h-[72vh] rounded-xl border border-line"
            />
          ) : (
            <a href={url(evidence!.file_path)} download className="btn-primary">
              Download {evidence!.type.replace(/_/g, ' ')}
            </a>
          )}
        </div>
      </div>
    </dialog>
  );
};
