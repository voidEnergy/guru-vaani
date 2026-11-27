import React, { useState } from 'react';
import { X, KeyRound, Trash2, Check, ShieldAlert } from 'lucide-react';
import type { ApiKeys, EngineInfo } from '../types';

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
  apiKeys: ApiKeys;
  onSaveKeys: (keys: ApiKeys) => void;
  engineInfo: EngineInfo;
}

export const SettingsDrawer: React.FC<SettingsDrawerProps> = ({
  open,
  onClose,
  apiKeys,
  onSaveKeys,
  engineInfo,
}) => {
  const [geminiKey, setGeminiKey] = useState(apiKeys.geminiKey);
  const [openaiKey, setOpenaiKey] = useState(apiKeys.openaiKey);

  if (!open) return null;

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    onSaveKeys({ geminiKey: geminiKey.trim(), openaiKey: openaiKey.trim() });
    onClose();
  };

  const handleClear = () => {
    setGeminiKey('');
    setOpenaiKey('');
    onSaveKeys({ geminiKey: '', openaiKey: '' });
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/50 backdrop-blur-xs">
      <div className="flex h-full w-full max-w-md flex-col bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-indigo-600" />
            <h2 className="text-base font-semibold text-slate-900">
              Engine & API Key Settings
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSave} className="flex flex-1 flex-col gap-5 overflow-y-auto p-5">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5 text-xs text-slate-600">
            <p className="font-semibold text-slate-800">
              Current Engine:{' '}
              <span className="text-indigo-700">
                {engineInfo.engine_mode === 'local'
                  ? 'Local Voice Engine (key not set)'
                  : `${engineInfo.engine_mode} (${engineInfo.model})`}
              </span>
            </p>
            <p className="mt-1">
              Guru-Vaani boots and runs 100% deterministically with zero API keys.
              Optionally add a Gemini or OpenAI key below to send via{' '}
              <code className="rounded bg-slate-200 px-1">X-Gemini-Key</code> /{' '}
              <code className="rounded bg-slate-200 px-1">X-OpenAI-Key</code>{' '}
              headers for cloud feedback polishing.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
              Gemini API Key (Optional)
            </label>
            <input
              type="password"
              value={geminiKey}
              onChange={(e) => setGeminiKey(e.target.value)}
              placeholder="AIza..."
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
              OpenAI API Key (Optional)
            </label>
            <input
              type="password"
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
              placeholder="sk-..."
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 focus:outline-none"
            />
          </div>

          <div className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
            <span>
              Student names and PII never leave your browser. Keys are stored
              only in your browser&apos;s <code>localStorage</code>.
            </span>
          </div>

          <div className="mt-auto flex items-center justify-between gap-3 border-t border-slate-200 pt-4">
            <button
              type="button"
              onClick={handleClear}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Clear Keys
            </button>
            <button
              type="submit"
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
            >
              <Check className="h-3.5 w-3.5" />
              Save & Apply
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
