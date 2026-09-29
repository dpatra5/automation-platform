import { X, AlertCircle } from "lucide-react";

interface ErrorToastProps {
  message: string;
  onClose: () => void;
}

export function ErrorToast({ message, onClose }: ErrorToastProps) {
  return (
    <div className="fixed top-5 right-5 z-50 animate-[slideIn_0.3s_ease] max-w-sm">
      <div className="bg-red-600 text-white px-4 py-3 rounded-lg shadow-lg flex items-start gap-3">
        <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
        <span className="flex-1 text-sm">{message}</span>
        <button
          type="button"
          className="hover:bg-red-700 p-1 rounded transition-colors -mr-1"
          onClick={onClose}
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
