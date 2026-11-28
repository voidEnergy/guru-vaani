import React, { useEffect, useState } from 'react';
import * as XLSX from 'xlsx';
import { exportMarksheetXlsx, exportMarksheetCsv } from '../lib/excelExport';
import {
  Download,
  FileSpreadsheet,
  Flame,
  MessageSquareHeart,
  Volume2,
  RefreshCw,
} from 'lucide-react';
import type {
  ExportDataResponse,
  FeedbackLanguage,
  GradingMode,
  PiiVaultState,
  ScoreEntry,
} from '../types';
import { speakText } from '../lib/audio';

interface ReviewTabsProps {
  mode: GradingMode;
  anchors: string[];
  maxMarks: number;
  feedbackLang: FeedbackLanguage;
  vault: PiiVaultState;
  scoresByRoll: Record<number, Record<string, ScoreEntry>>;
  exportData: ExportDataResponse | null;
  onRefreshExport: () => Promise<void>;
  isRefreshing: boolean;
}

type SubTab = 'marksheet' | 'heatmap' | 'cards';

export const ReviewTabs: React.FC<ReviewTabsProps> = ({
  mode,
  anchors,
  maxMarks,
  feedbackLang,
  vault,
  scoresByRoll,
  exportData,
  onRefreshExport,
  isRefreshing,
}) => {
  const [subTab, setSubTab] = useState<SubTab>('marksheet');
  const [editedCards, setEditedCards] = useState<
    Record<number, { english: string; hindi: string }>
  >({});

  useEffect(() => {
    if (!exportData) return;
    setEditedCards((prev) => {
      const next = { ...prev };
      for (const summary of exportData.student_summaries) {
        if (!next[summary.roll_no]) {
          next[summary.roll_no] = {
            english: summary.feedback.english,
            hindi: summary.feedback.hindi,
          };
        }
      }
      return next;
    });
  }, [exportData]);

  const rolls = Object.keys(vault.rollToName)
    .map(Number)
    .sort((a, b) => a - b);

  const buildExportRows = () => {
    const hasAnyFeedback = rolls.some((r) => editedCards[r]);
    const rollKey = vault.rollColumnKey || 'Roll No';
    const nameKey = vault.nameColumnKey || 'Student Name';

    return rolls.map((roll) => {
      const orig = vault.originalRows[roll] ?? {};
      const row: Record<string, string | number> = {
        [rollKey]: roll,
        [nameKey]: vault.rollToName[roll] ?? `Roll ${roll}`,
      };

      for (const [k, v] of Object.entries(orig)) {
        if (k !== rollKey && k !== nameKey) {
          row[k] = v ?? '';
        }
      }

      const rScores = scoresByRoll[roll] ?? {};
      let total = 0;
      let count = 0;
      for (const a of anchors) {
        const entry = rScores[a];
        if (entry) {
          row[a] = entry.score;
          total += entry.score;
          count++;
        } else {
          row[a] = '';
        }
      }
      row['Total'] = count > 0 ? total : '';

      if (hasAnyFeedback) {
        const card = editedCards[roll];
        row['Feedback (EN)'] = card?.english ?? '';
        row['Feedback (HI)'] = card?.hindi ?? '';
      }
      return row;
    });
  };

  const handleDownload = async (format: 'xlsx' | 'csv') => {
    const rows = buildExportRows();
    const filename = `guru-vaani-${mode}-marksheet.${format}`;

    if (format === 'xlsx') {
      await exportMarksheetXlsx({
        filename,
        sheetName: 'GuruVaani_Marksheet',
        rows,
        anchors,
        rollKey: vault.rollColumnKey || 'Roll No',
        nameKey: vault.nameColumnKey || 'Student Name',
      });
    } else {
      const ws = XLSX.utils.json_to_sheet(rows);
      const csvContent = XLSX.utils.sheet_to_csv(ws);
      exportMarksheetCsv(filename, csvContent);
    }
  };

  // Compute per-anchor struggle % (< 50% of maxMarks) + recurring tags from exportData
  const anchorStats = anchors.map((anchor) => {
    const gradedScores: number[] = [];
    for (const roll of rolls) {
      const entry = scoresByRoll[roll]?.[anchor];
      if (entry) gradedScores.push(entry.score);
    }
    const strugglingCount = gradedScores.filter(
      (s) => s < maxMarks * 0.5
    ).length;
    const strugglePct =
      gradedScores.length > 0
        ? Math.round((strugglingCount / gradedScores.length) * 100)
        : 0;
    const avg =
      gradedScores.length > 0
        ? (
            gradedScores.reduce((a, b) => a + b, 0) / gradedScores.length
          ).toFixed(1)
        : '—';

    const tagMap = exportData?.weakness_heatmap?.[anchor] ?? {};
    const topTags = Object.entries(tagMap)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 5);

    return {
      anchor,
      gradedCount: gradedScores.length,
      strugglePct,
      avg,
      topTags,
    };
  });

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-3 sm:p-5">
      {/* Sub-navigation + Refresh */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex rounded-xl bg-slate-200/70 p-1">
          <button
            type="button"
            onClick={() => setSubTab('marksheet')}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              subTab === 'marksheet'
                ? 'bg-white text-indigo-700 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <FileSpreadsheet className="h-3.5 w-3.5" />
            Marksheet &amp; Export
          </button>
          <button
            type="button"
            onClick={() => setSubTab('heatmap')}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              subTab === 'heatmap'
                ? 'bg-white text-indigo-700 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Flame className="h-3.5 w-3.5" />
            Weakness Heatmap
          </button>
          <button
            type="button"
            onClick={() => setSubTab('cards')}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              subTab === 'cards'
                ? 'bg-white text-indigo-700 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <MessageSquareHeart className="h-3.5 w-3.5" />
            {mode === 'oral' ? 'Candidate Cards' : 'Bilingual PTM Cards'}
          </button>
        </div>

        <button
          type="button"
          onClick={onRefreshExport}
          disabled={isRefreshing}
          className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`}
          />
          Sync Backend
        </button>
      </div>

      {/* TAB 1: Marksheet & Export */}
      {subTab === 'marksheet' && (
        <div className="rounded-2xl border border-slate-200 bg-white shadow-xs">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3.5">
            <div>
              <h2 className="text-sm font-bold text-slate-900">
                Final Marksheet (Local PII Re-attached)
              </h2>
              <p className="text-xs text-slate-500">
                Student names are merged locally from browser{' '}
                <code>localStorage</code> right before export.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleDownload('xlsx')}
                className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3.5 py-2 text-xs font-semibold text-white shadow-xs hover:bg-emerald-700"
              >
                <Download className="h-3.5 w-3.5" />
                Download .xlsx
              </button>
              <button
                type="button"
                onClick={() => handleDownload('csv')}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                <Download className="h-3.5 w-3.5" />
                Download .csv
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs">
              <thead className="bg-slate-50 text-[11px] font-semibold uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Roll No</th>
                  <th className="px-4 py-3">Student Name (Local)</th>
                  {anchors.map((a) => (
                    <th key={a} className="px-3 py-3 text-center">
                      {a}
                    </th>
                  ))}
                  <th className="px-4 py-3 text-right">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rolls.map((roll) => {
                  const rScores = scoresByRoll[roll] ?? {};
                  const total = Object.values(rScores).reduce(
                    (s, e) => s + e.score,
                    0
                  );
                  return (
                    <tr key={roll} className="hover:bg-slate-50">
                      <td className="px-4 py-2.5 font-bold text-indigo-700">
                        {roll}
                      </td>
                      <td className="px-4 py-2.5 font-medium text-slate-900">
                        {vault.rollToName[roll]}
                      </td>
                      {anchors.map((a) => (
                        <td
                          key={a}
                          className="px-3 py-2.5 text-center font-semibold text-slate-700"
                        >
                          {rScores[a] ? rScores[a].score : '—'}
                        </td>
                      ))}
                      <td className="px-4 py-2.5 text-right font-bold text-slate-900">
                        {Object.keys(rScores).length > 0 ? total : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2: Weakness Heatmap */}
      {subTab === 'heatmap' && (
        <div className="grid gap-4 sm:grid-cols-2">
          {anchorStats.map((stat) => {
            const barColor =
              stat.strugglePct >= 50
                ? 'bg-rose-500'
                : stat.strugglePct >= 25
                  ? 'bg-amber-500'
                  : 'bg-emerald-500';
            return (
              <div
                key={stat.anchor}
                className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">
                      {stat.anchor}
                    </h3>
                    <p className="text-xs text-slate-500">
                      {stat.gradedCount} graded • Avg {stat.avg}/{maxMarks}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                      stat.strugglePct >= 50
                        ? 'bg-rose-100 text-rose-800'
                        : stat.strugglePct >= 25
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-emerald-100 text-emerald-800'
                    }`}
                  >
                    {stat.strugglePct}% struggling
                  </span>
                </div>

                {/* Progress Bar */}
                <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                    style={{ width: `${Math.max(stat.strugglePct, 4)}%` }}
                  />
                </div>

                {/* Top Sanitized Tags */}
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {stat.topTags.length === 0 ? (
                    <span className="text-[11px] text-slate-400">
                      No recurring error tags recorded yet.
                    </span>
                  ) : (
                    stat.topTags.map(([tag, count]) => (
                      <span
                        key={tag}
                        className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-700"
                      >
                        <span>{tag}</span>
                        <span className="font-bold text-indigo-600">
                          ×{count}
                        </span>
                      </span>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* TAB 3: Bilingual PTM / Candidate Cards */}
      {subTab === 'cards' && (
        <div className="grid gap-4 sm:grid-cols-2">
          {(exportData?.student_summaries ?? []).length === 0 ? (
            <div className="col-span-full rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-xs text-slate-500">
              Grade at least one student to generate bilingual PTM / Candidate
              cards.
            </div>
          ) : (
            exportData!.student_summaries.map((summary) => {
              const name =
                vault.rollToName[summary.roll_no] ?? `Roll ${summary.roll_no}`;
              const card = editedCards[summary.roll_no] ?? {
                english: summary.feedback.english,
                hindi: summary.feedback.hindi,
              };

              return (
                <div
                  key={summary.roll_no}
                  className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-xs font-bold text-indigo-600">
                        Roll #{summary.roll_no}
                      </span>
                      <h3 className="text-sm font-bold text-slate-900">
                        {name}
                      </h3>
                    </div>
                    <span className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-800">
                      Avg: {summary.average}/{maxMarks}
                    </span>
                  </div>

                  {(feedbackLang === 'English' || feedbackLang === 'Both') && (
                    <div>
                      <div className="flex items-center justify-between">
                        <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                          English Summary
                        </label>
                        <button
                          type="button"
                          onClick={() => speakText(card.english, 'en-IN')}
                          className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800"
                        >
                          <Volume2 className="h-3.5 w-3.5" />
                          Listen (English)
                        </button>
                      </div>
                      <textarea
                        rows={2}
                        value={card.english}
                        onChange={(e) =>
                          setEditedCards((prev) => ({
                            ...prev,
                            [summary.roll_no]: {
                              ...card,
                              english: e.target.value,
                            },
                          }))
                        }
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50 p-2 text-xs text-slate-800 focus:border-indigo-400 focus:bg-white focus:outline-none"
                      />
                    </div>
                  )}

                  {(feedbackLang === 'Hindi' || feedbackLang === 'Both') && (
                    <div>
                      <div className="flex items-center justify-between">
                        <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                          Hindi Summary (हिन्दी)
                        </label>
                        <button
                          type="button"
                          onClick={() => speakText(card.hindi, 'hi-IN')}
                          className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800"
                        >
                          <Volume2 className="h-3.5 w-3.5" />
                          Listen (Hindi)
                        </button>
                      </div>
                      <textarea
                        rows={2}
                        value={card.hindi}
                        onChange={(e) =>
                          setEditedCards((prev) => ({
                            ...prev,
                            [summary.roll_no]: {
                              ...card,
                              hindi: e.target.value,
                            },
                          }))
                        }
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50 p-2 text-xs text-slate-800 focus:border-indigo-400 focus:bg-white focus:outline-none"
                      />
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};
