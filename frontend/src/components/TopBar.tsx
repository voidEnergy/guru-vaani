import React from 'react';
import {
  Mic,
  Volume2,
  Vibrate,
  Settings,
  ShieldCheck,
  Cpu,
  Sparkles,
  BookOpen,
  MessageSquare,
} from 'lucide-react';
import type { EngineInfo, GradingMode, ReplyMode } from '../types';

interface TopBarProps {
  mode: GradingMode;
  onModeChange: (mode: GradingMode) => void;
  replyMode: ReplyMode;
  onReplyModeChange: (mode: ReplyMode) => void;
  engineInfo: EngineInfo;
  onOpenSettings: () => void;
  vaultCount: number;
}

export const TopBar: React.FC<TopBarProps> = ({
  mode,
  onModeChange,
  replyMode,
  onReplyModeChange,
  engineInfo,
  onOpenSettings,
  vaultCount,
}) => {
  const isLocal = engineInfo.engine_mode === 'local';

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-slate-900 text-white shadow-sm">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-3 py-2.5 sm:px-5">
        {/* Left: Brand + Mode Pill */}
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 shadow-inner">
            <Mic className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold tracking-tight sm:text-lg">
                Guru-Vaani
              </span>
              <span className="hidden items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-300 ring-1 ring-emerald-500/30 sm:inline-flex">
                <ShieldCheck className="h-3 w-3" />
                Zero-PII Vault ({vaultCount})
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-300">
              {isLocal ? (
                <span className="inline-flex items-center gap-1 text-amber-300">
                  <Cpu className="h-3 w-3" />
                  Local Voice Engine (key not set)
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-sky-300">
                  <Sparkles className="h-3 w-3" />
                  Cloud: {engineInfo.engine_mode} ({engineInfo.model})
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Right: Mode Pill, Reply Toggle, Settings */}
        <div className="flex items-center gap-1.5 sm:gap-2.5">
          {/* Written / Oral Mode Pill */}
          <div
            className="flex rounded-lg bg-slate-800 p-0.5 ring-1 ring-slate-700"
            role="group"
            aria-label="Grading Mode"
          >
            <button
              type="button"
              onClick={() => onModeChange('written')}
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition ${
                mode === 'written'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-300 hover:text-white'
              }`}
            >
              <BookOpen className="h-3.5 w-3.5" />
              <span>Written</span>
            </button>
            <button
              type="button"
              onClick={() => onModeChange('oral')}
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition ${
                mode === 'oral'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-300 hover:text-white'
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5" />
              <span>Oral</span>
            </button>
          </div>

          {/* Voice Reply vs Silent Haptic Toggle */}
          <button
            type="button"
            onClick={() =>
              onReplyModeChange(replyMode === 'voice' ? 'haptic' : 'voice')
            }
            title={
              replyMode === 'voice'
                ? 'Voice Reply active (tap to switch to Silent Haptic)'
                : 'Silent Haptic active (tap to switch to Voice Reply)'
            }
            className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium ring-1 transition ${
              replyMode === 'voice'
                ? 'bg-slate-800 text-indigo-200 ring-indigo-500/40 hover:bg-slate-700'
                : 'bg-slate-800 text-amber-200 ring-amber-500/40 hover:bg-slate-700'
            }`}
          >
            {replyMode === 'voice' ? (
              <>
                <Volume2 className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Voice Reply</span>
              </>
            ) : (
              <>
                <Vibrate className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Silent Haptic</span>
              </>
            )}
          </button>

          {/* Settings Gear */}
          <button
            type="button"
            onClick={onOpenSettings}
            aria-label="Open API Settings"
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800 text-slate-300 ring-1 ring-slate-700 transition hover:bg-slate-700 hover:text-white"
          >
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
};
