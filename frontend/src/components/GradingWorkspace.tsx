import React, { useState } from 'react';
import {
  UserCheck,
  AlertTriangle,
  Check,
  X,
  Edit3,
  Clock,
} from 'lucide-react';
import type {
  ActivityLogItem,
  GradingMode,
  PiiVaultState,
  RowFlashState,
  ScoreEntry,
  SpeechLocale,
} from '../types';
import { MicConsole } from './MicConsole';

interface GradingWorkspaceProps {
  mode: GradingMode;
  anchors: string[];
  maxMarks: number;
  vault: PiiVaultState;
  scoresByRoll: Record<number, Record<string, ScoreEntry>>;
  activeRoll: number | null;
  onSelectRoll: (roll: number) => void;
  rowFlashes: Record<number, RowFlashState>;
  speechLocale: SpeechLocale;
  onSpeechLocaleChange: (loc: SpeechLocale) => void;
  onSubmitTranscript: (transcript: string) => void;
  onQuickCommand: (cmd: 'undo' | 'status') => void;
  onManualEdit: (
    rollNo: number,
    anchor: string,
    score: number,
    comment: string
  ) => Promise<void>;
  pendingGrace: { marks: number; message: string } | null;
  onConfirmGrace: (action: 'confirm' | 'cancel') => void;
  isProcessing: boolean;
  lastIgnoredPill: string | null;
  statusBanner: {
    type: 'save' | 'edit' | 'error' | 'ignore' | 'info';
    text: string;
  } | null;
  activityLog: ActivityLogItem[];
}

export const GradingWorkspace: React.FC<GradingWorkspaceProps> = ({
  mode,
  anchors,
  maxMarks,
  vault,
  scoresByRoll,
  activeRoll,
  onSelectRoll,
  rowFlashes,
  speechLocale,
  onSpeechLocaleChange,
  onSubmitTranscript,
  onQuickCommand,
  onManualEdit,
  pendingGrace,
  onConfirmGrace,
  isProcessing,
  lastIgnoredPill,
  statusBanner,
  activityLog,
}) => {
  const [editingCell, setEditingCell] = useState<{
    rollNo: number;
    anchor: string;
    score: string;
    comment: string;
  } | null>(null);

  const rolls = Object.keys(vault.rollToName)
    .map(Number)
    .sort((a, b) => a - b);

  const currentRoll = activeRoll ?? rolls[0] ?? null;
  const currentStudentName =
    currentRoll !== null ? vault.rollToName[currentRoll] ?? `Roll ${currentRoll}` : '';
  const currentScores = currentRoll !== null ? scoresByRoll[currentRoll] ?? {} : {};
  const currentTotal = Object.values(currentScores).reduce(
    (sum, e) => sum + e.score,
    0
  );
  const maxTotal = anchors.length * maxMarks;

  const handleSaveCell = async () => {
    if (!editingCell) return;
    const num = Number(editingCell.score);
    if (!Number.isFinite(num)) return;
    await onManualEdit(
      editingCell.rollNo,
      editingCell.anchor,
      num,
      editingCell.comment
    );
    setEditingCell(null);
  };

  return (
    <div className="mx-auto max-w-7xl p-3 sm:p-5">
      {/* Centered Fixed Bulk Grace Confirm/Cancel Modal Overlay */}
      {pendingGrace && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-xs"
          role="dialog"
          aria-modal="true"
          aria-labelledby="bulk-grace-modal-title"
        >
          <div className="w-full max-w-md rounded-2xl border-2 border-amber-400 bg-amber-50 p-5 shadow-2xl">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-700">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div>
                <h3
                  id="bulk-grace-modal-title"
                  className="text-base font-bold text-amber-950"
                >
                  Confirm Bulk Grace Marks (+{pendingGrace.marks})
                </h3>
                <p className="mt-1 text-sm text-amber-900">{pendingGrace.message}</p>
                <p className="mt-1.5 text-xs font-medium text-amber-700">
                  You can also say &ldquo;confirm&rdquo; or &ldquo;cancel&rdquo; by voice.
                </p>
              </div>
            </div>
            <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => onConfirmGrace('cancel')}
                disabled={isProcessing}
                className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-amber-300 bg-white px-4 py-2.5 text-sm font-semibold text-amber-900 hover:bg-amber-100 disabled:opacity-50"
              >
                <X className="h-4 w-4" />
                Cancel
              </button>
              <button
                type="button"
                onClick={() => onConfirmGrace('confirm')}
                disabled={isProcessing}
                className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-amber-600 px-5 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-amber-700 disabled:opacity-50"
              >
                <Check className="h-4 w-4" />
                Confirm Grace
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Responsive Grid: Single-column mobile, 2-column desktop */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Left Column: Active Student Card + Scrollable Editable Marksheet */}
        <div className="flex flex-col gap-4 lg:col-span-7">
          {/* Active Student Card */}
          {currentRoll !== null && (
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-50 font-bold text-indigo-700 ring-1 ring-indigo-200">
                    #{currentRoll}
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5">
                      <h2 className="text-base font-bold text-slate-900">
                        {currentStudentName}
                      </h2>
                      <UserCheck className="h-4 w-4 text-emerald-600" />
                    </div>
                    <p className="text-xs text-slate-500">
                      {mode === 'written' ? 'Written Script' : 'Oral Viva'} •{' '}
                      {Object.keys(currentScores).length}/{anchors.length} graded
                    </p>
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-lg font-extrabold text-indigo-700">
                    {currentTotal}{' '}
                    <span className="text-xs font-medium text-slate-400">
                      / {maxTotal}
                    </span>
                  </div>
                  <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                    Total Score
                  </span>
                </div>
              </div>

              {/* Active student anchor pills */}
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {anchors.map((anchor) => {
                  const entry = currentScores[anchor];
                  return (
                    <button
                      key={anchor}
                      type="button"
                      onClick={() =>
                        setEditingCell({
                          rollNo: currentRoll,
                          anchor,
                          score: entry ? String(entry.score) : '',
                          comment: entry?.comment ?? '',
                        })
                      }
                      className={`flex flex-col rounded-xl border p-2.5 text-left transition ${
                        entry
                          ? 'border-indigo-200 bg-indigo-50/40 hover:border-indigo-400'
                          : 'border-slate-200 bg-slate-50 hover:border-slate-300'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-700">
                          {anchor}
                        </span>
                        <Edit3 className="h-3 w-3 text-slate-400" />
                      </div>
                      <span className="mt-1 text-base font-extrabold text-slate-900">
                        {entry ? entry.score : '—'}
                        <span className="text-[11px] font-normal text-slate-400">
                          /{maxMarks}
                        </span>
                      </span>
                      {entry?.comment && (
                        <span className="mt-0.5 line-clamp-1 text-[10px] text-slate-500">
                          {entry.comment}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Inline Cell Edit Popover */}
          {editingCell && (
            <div className="rounded-2xl border border-indigo-300 bg-indigo-50/80 p-3.5 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-indigo-950">
                  Manual Edit — Roll #{editingCell.rollNo} • {editingCell.anchor}
                </span>
                <button
                  type="button"
                  onClick={() => setEditingCell(null)}
                  className="text-slate-400 hover:text-slate-700"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="mt-2.5 flex flex-wrap gap-2">
                <input
                  type="number"
                  step={0.5}
                  min={0}
                  max={maxMarks}
                  value={editingCell.score}
                  onChange={(e) =>
                    setEditingCell({ ...editingCell, score: e.target.value })
                  }
                  placeholder={`0–${maxMarks}`}
                  className="w-24 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-bold text-slate-900"
                />
                <input
                  type="text"
                  value={editingCell.comment}
                  onChange={(e) =>
                    setEditingCell({ ...editingCell, comment: e.target.value })
                  }
                  placeholder="Optional feedback note..."
                  className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900"
                />
                <button
                  type="button"
                  onClick={handleSaveCell}
                  className="rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
                >
                  Save
                </button>
              </div>
            </div>
          )}

          {/* Scrollable Editable Marksheet */}
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">
                Live Marksheet ({rolls.length} Students)
              </h3>
              <span className="text-[11px] text-slate-400">
                Tap any cell to edit
              </span>
            </div>
            <div className="max-h-[380px] overflow-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead className="sticky top-0 z-10 bg-slate-50 text-[11px] font-semibold uppercase text-slate-500 shadow-2xs">
                  <tr>
                    <th className="px-3 py-2.5">Roll</th>
                    <th className="px-3 py-2.5">Student (Local)</th>
                    {anchors.map((a) => (
                      <th key={a} className="px-2.5 py-2.5 text-center">
                        {a}
                      </th>
                    ))}
                    <th className="px-3 py-2.5 text-right">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rolls.map((roll) => {
                    const rowScores = scoresByRoll[roll] ?? {};
                    const total = Object.values(rowScores).reduce(
                      (s, e) => s + e.score,
                      0
                    );
                    const flash = rowFlashes[roll];
                    const flashClass =
                      flash === 'green'
                        ? 'animate-flash-green'
                        : flash === 'amber'
                          ? 'animate-flash-amber'
                          : flash === 'red'
                            ? 'animate-flash-red'
                            : '';

                    const isSelected = roll === currentRoll;

                    return (
                      <tr
                        key={roll}
                        onClick={() => onSelectRoll(roll)}
                        className={`cursor-pointer transition ${flashClass} ${
                          isSelected
                            ? 'bg-indigo-50/60'
                            : 'hover:bg-slate-50'
                        }`}
                      >
                        <td className="px-3 py-2.5 font-bold text-indigo-700">
                          {roll}
                        </td>
                        <td className="px-3 py-2.5 font-medium text-slate-800">
                          {vault.rollToName[roll]}
                        </td>
                        {anchors.map((a) => {
                          const entry = rowScores[a];
                          return (
                            <td key={a} className="px-2 py-2 text-center">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onSelectRoll(roll);
                                  setEditingCell({
                                    rollNo: roll,
                                    anchor: a,
                                    score: entry ? String(entry.score) : '',
                                    comment: entry?.comment ?? '',
                                  });
                                }}
                                title={entry?.comment || 'Click to edit'}
                                className={`min-w-[2.2rem] rounded-md px-1.5 py-1 font-semibold transition ${
                                  entry
                                    ? 'bg-slate-100 text-slate-900 hover:bg-indigo-100'
                                    : 'text-slate-300 hover:bg-slate-100 hover:text-slate-600'
                                }`}
                              >
                                {entry ? entry.score : '—'}
                              </button>
                            </td>
                          );
                        })}
                        <td className="px-3 py-2.5 text-right font-bold text-slate-900">
                          {Object.keys(rowScores).length > 0 ? total : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Column: Mic Console + Recent Activity */}
        <div className="flex flex-col gap-4 lg:col-span-5">
          <MicConsole
            mode={mode}
            speechLocale={speechLocale}
            onSpeechLocaleChange={onSpeechLocaleChange}
            onSubmitTranscript={onSubmitTranscript}
            onQuickCommand={onQuickCommand}
            isProcessing={isProcessing}
            lastIgnoredPill={lastIgnoredPill}
            statusBanner={statusBanner}
          />

          {/* Recent Voice Activity Log */}
          <div className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-xs">
            <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-500">
              <Clock className="h-3.5 w-3.5" />
              <span>Voice Command Log</span>
            </div>
            <div className="mt-2.5 max-h-56 space-y-2 overflow-y-auto">
              {activityLog.length === 0 ? (
                <p className="text-xs text-slate-400">
                  No commands yet. Tap the mic or try a sample utterance above.
                </p>
              ) : (
                activityLog.map((item) => (
                  <div
                    key={item.id}
                    className={`rounded-xl border px-3 py-2 text-xs ${
                      item.type === 'save'
                        ? 'border-emerald-200 bg-emerald-50/50'
                        : item.type === 'edit'
                          ? 'border-amber-200 bg-amber-50/50'
                          : item.type === 'error'
                            ? 'border-red-200 bg-red-50/60'
                            : item.type === 'ignore'
                              ? 'border-slate-200 bg-slate-50 text-slate-500'
                              : 'border-slate-200 bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-slate-800 line-clamp-1">
                        &ldquo;{item.transcript}&rdquo;
                      </span>
                      <span className="shrink-0 text-[10px] text-slate-400">
                        {item.timestamp}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-slate-600">
                      {item.message}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
