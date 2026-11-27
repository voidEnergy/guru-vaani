import React, { useRef, useState } from 'react';
import * as XLSX from 'xlsx';
import {
  Upload,
  ShieldCheck,
  Sparkles,
  Play,
  FileSpreadsheet,
  Sliders,
  Languages,
  CheckCircle2,
} from 'lucide-react';
import type {
  FeedbackLanguage,
  GradingMode,
  PiiVaultState,
} from '../types';
import {
  PHYSICS_WRITTEN_DEMO,
  UPSC_ORAL_DEMO,
  demoToVault,
  type DemoPreset,
} from '../lib/demos';

interface SetupPanelProps {
  mode: GradingMode;
  anchors: string[];
  maxMarks: number;
  feedbackLang: FeedbackLanguage;
  vault: PiiVaultState;
  sessionId: string | null;
  isInitializing: boolean;
  onUpdateConfig: (cfg: {
    mode: GradingMode;
    anchors: string[];
    maxMarks: number;
    feedbackLang: FeedbackLanguage;
  }) => void;
  onVaultLoaded: (vault: PiiVaultState, preset?: DemoPreset) => void;
  onStartSession: () => void;
}

export const SetupPanel: React.FC<SetupPanelProps> = ({
  mode,
  anchors,
  maxMarks,
  feedbackLang,
  vault,
  sessionId,
  isInitializing,
  onUpdateConfig,
  onVaultLoaded,
  onStartSession,
}) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [anchorInput, setAnchorInput] = useState(anchors.join(', '));
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);

  const rollCount = Object.keys(vault.rollToName).length;

  const handleAnchorsBlur = () => {
    const parsed = anchorInput
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    if (parsed.length > 0) {
      onUpdateConfig({ mode, anchors: parsed, maxMarks, feedbackLang });
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    setUploadSuccess(null);

    try {
      const data = await file.arrayBuffer();
      const workbook = XLSX.read(data, { type: 'array' });
      const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
      const rows = XLSX.utils.sheet_to_json<Record<string, string | number>>(
        firstSheet,
        { defval: '' }
      );

      if (!rows.length) {
        setUploadError('The uploaded spreadsheet has no rows.');
        return;
      }

      const headers = Object.keys(rows[0]);
      const rollCol =
        headers.find((h) => /roll|id|no|candidate/i.test(h)) ?? headers[0];
      const nameCol =
        headers.find((h) => /name|student|candidate/i.test(h) && h !== rollCol) ??
        headers[1] ??
        headers[0];

      const rollToName: Record<number, string> = {};
      const originalRows: Record<number, Record<string, string | number>> = {};

      for (const row of rows) {
        const rawRoll = row[rollCol];
        const parsedRoll = Number(String(rawRoll).replace(/[^\d]/g, ''));
        if (!Number.isFinite(parsedRoll) || parsedRoll <= 0) continue;

        const studentName = String(row[nameCol] ?? `Roll ${parsedRoll}`).trim();
        rollToName[parsedRoll] = studentName;
        originalRows[parsedRoll] = row;
      }

      const count = Object.keys(rollToName).length;
      if (count === 0) {
        setUploadError(
          `Could not find numeric roll numbers in column "${rollCol}".`
        );
        return;
      }

      const newVault: PiiVaultState = {
        rollToName,
        originalRows,
        originalHeaders: headers,
        rollColumnKey: rollCol,
        nameColumnKey: nameCol,
      };
      onVaultLoaded(newVault);
      setUploadSuccess(
        `Loaded ${count} students into Local PII Vault (${file.name}).`
      );
    } catch (err) {
      setUploadError(
        err instanceof Error ? err.message : 'Failed to parse spreadsheet.'
      );
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleLoadDemo = (preset: DemoPreset) => {
    setUploadError(null);
    setAnchorInput(preset.anchors.join(', '));
    const v = demoToVault(preset);
    onVaultLoaded(v, preset);
    setUploadSuccess(`Loaded ${preset.label} into Local PII Vault.`);
  };

  return (
    <div className="mx-auto max-w-4xl space-y-5 p-3 sm:p-6">
      {/* Zero-PII Banner */}
      <div className="flex flex-col gap-2 rounded-2xl border border-emerald-200 bg-emerald-50/80 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-sm">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-emerald-950">
              Zero-PII Local Vault Active
            </h2>
            <p className="text-xs text-emerald-800">
              Student names &amp; uploaded roster columns stay strictly in
              browser <code className="rounded bg-emerald-100 px-1">localStorage</code>.
              Backend APIs only ever receive <code className="rounded bg-emerald-100 px-1">roll_no</code>,
              schema, and transcripts.
            </p>
          </div>
        </div>
        <div className="shrink-0 rounded-full bg-white px-3 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200">
          {rollCount} student{rollCount === 1 ? '' : 's'} in vault
        </div>
      </div>

      {/* Step 1: Roster Upload or 1-Click Demos */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs sm:p-5">
        <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
          <FileSpreadsheet className="h-4 w-4 text-indigo-600" />
          <span>1. Load Roster (Strict Local-Only)</span>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Upload any <code>.xlsx</code> or <code>.csv</code> roster, or load a
          ready-to-test demo batch.
        </p>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <button
            type="button"
            onClick={() => handleLoadDemo(PHYSICS_WRITTEN_DEMO)}
            className="flex flex-col items-start rounded-xl border border-indigo-200 bg-indigo-50/60 p-3.5 text-left transition hover:border-indigo-400 hover:bg-indigo-50"
          >
            <span className="inline-flex items-center gap-1 rounded-full bg-indigo-600 px-2 py-0.5 text-[10px] font-semibold text-white">
              <Sparkles className="h-2.5 w-2.5" />
              Written Demo
            </span>
            <span className="mt-2 text-xs font-bold text-slate-900">
              Load 10-Student Physics Written Demo
            </span>
            <span className="mt-0.5 text-[11px] text-slate-600">
              Rolls 11–20 • Q1–Q4 • Max 10
            </span>
          </button>

          <button
            type="button"
            onClick={() => handleLoadDemo(UPSC_ORAL_DEMO)}
            className="flex flex-col items-start rounded-xl border border-violet-200 bg-violet-50/60 p-3.5 text-left transition hover:border-violet-400 hover:bg-violet-50"
          >
            <span className="inline-flex items-center gap-1 rounded-full bg-violet-600 px-2 py-0.5 text-[10px] font-semibold text-white">
              <Sparkles className="h-2.5 w-2.5" />
              Oral Viva Demo
            </span>
            <span className="mt-2 text-xs font-bold text-slate-900">
              Load 8-Candidate UPSC Oral Viva Demo
            </span>
            <span className="mt-0.5 text-[11px] text-slate-600">
              Rolls 101–108 • Clarity, Depth, Ethics, Composure
            </span>
          </button>

          <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 p-3.5 text-center transition hover:border-indigo-400 hover:bg-indigo-50/30">
            <Upload className="h-5 w-5 text-slate-500" />
            <span className="mt-1.5 text-xs font-semibold text-slate-800">
              Upload .xlsx / .csv
            </span>
            <span className="mt-0.5 text-[11px] text-slate-500">
              Parsed locally in browser
            </span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={handleFileUpload}
              className="hidden"
            />
          </label>
        </div>

        {uploadError && (
          <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700 ring-1 ring-red-200">
            {uploadError}
          </p>
        )}
        {uploadSuccess && (
          <p className="mt-3 flex items-center gap-1.5 rounded-lg bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-800 ring-1 ring-emerald-200">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            {uploadSuccess}
          </p>
        )}
      </section>

      {/* Step 2: Exam / Rubric Schema & Feedback Language */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs sm:p-5">
        <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
          <Sliders className="h-4 w-4 text-indigo-600" />
          <span>2. Exam Schema &amp; Feedback Settings</span>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label className="block text-xs font-semibold text-slate-700">
              {mode === 'written'
                ? 'Question Anchors (comma-separated)'
                : 'Rubric Items (comma-separated)'}
            </label>
            <input
              type="text"
              value={anchorInput}
              onChange={(e) => setAnchorInput(e.target.value)}
              onBlur={handleAnchorsBlur}
              placeholder={
                mode === 'written'
                  ? 'Q1, Q2, Q3, Q4'
                  : 'Clarity, Depth, Ethics, Composure'
              }
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700">
              Max Marks per Item
            </label>
            <input
              type="number"
              min={1}
              max={100}
              step={0.5}
              value={maxMarks}
              onChange={(e) =>
                onUpdateConfig({
                  mode,
                  anchors,
                  maxMarks: Math.max(1, Number(e.target.value) || 10),
                  feedbackLang,
                })
              }
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 focus:outline-none"
            />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 pt-4">
          <div className="flex items-center gap-2">
            <Languages className="h-4 w-4 text-slate-500" />
            <span className="text-xs font-semibold text-slate-700">
              Feedback Language:
            </span>
            <div className="flex rounded-lg bg-slate-100 p-0.5">
              {(['English', 'Hindi', 'Both'] as FeedbackLanguage[]).map((lang) => (
                <button
                  key={lang}
                  type="button"
                  onClick={() =>
                    onUpdateConfig({ mode, anchors, maxMarks, feedbackLang: lang })
                  }
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                    feedbackLang === lang
                      ? 'bg-white text-indigo-700 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {lang}
                </button>
              ))}
            </div>
          </div>

          <button
            type="button"
            disabled={rollCount === 0 || isInitializing}
            onClick={onStartSession}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            {isInitializing
              ? 'Starting Session...'
              : sessionId
                ? 'Apply & Start Grading'
                : 'Start Grading Session'}
          </button>
        </div>
      </section>

      {/* Local Roster Preview */}
      {rollCount > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs sm:p-5">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Local Vault Preview ({rollCount} students — stays on this device)
          </h3>
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(vault.rollToName)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([roll, name]) => (
                <span
                  key={roll}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700"
                >
                  <span className="font-bold text-indigo-700">#{roll}</span>
                  <span>{name}</span>
                </span>
              ))}
          </div>
        </section>
      )}
    </div>
  );
};
