import { useCallback, useEffect, useState } from 'react';
import { Sliders, Mic, BarChart2 } from 'lucide-react';
import type {
  ActivityLogItem,
  ApiKeys,
  EngineInfo,
  ExportDataResponse,
  FeedbackLanguage,
  GradingMode,
  PiiVaultState,
  ReplyMode,
  RowFlashState,
  ScoreEntry,
  SpeechLocale,
} from './types';
import {
  confirmGrace,
  fetchExportData,
  fetchHealth,
  initSession,
  manualEditScore,
  sendVoiceCommand,
} from './lib/api';
import {
  loadApiKeys,
  loadPiiVault,
  saveApiKeys,
  savePiiVault,
} from './lib/piiVault';
import { notifyAction } from './lib/audio';
import { PHYSICS_WRITTEN_DEMO, type DemoPreset } from './lib/demos';
import { TopBar } from './components/TopBar';
import { SettingsDrawer } from './components/SettingsDrawer';
import { SetupPanel } from './components/SetupPanel';
import { GradingWorkspace } from './components/GradingWorkspace';
import { ReviewTabs } from './components/ReviewTabs';

type AppTab = 'setup' | 'grade' | 'review';

export function App() {
  const [activeTab, setActiveTab] = useState<AppTab>('setup');
  const [mode, setMode] = useState<GradingMode>('written');
  const [anchors, setAnchors] = useState<string[]>(PHYSICS_WRITTEN_DEMO.anchors);
  const [maxMarks, setMaxMarks] = useState<number>(10);
  const [feedbackLang, setFeedbackLang] = useState<FeedbackLanguage>('Both');
  const [replyMode, setReplyMode] = useState<ReplyMode>('voice');
  const [speechLocale, setSpeechLocale] = useState<SpeechLocale>('en-IN');

  const [vault, setVault] = useState<PiiVaultState>(() => loadPiiVault());
  const [apiKeys, setApiKeys] = useState<ApiKeys>(() => loadApiKeys());
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [engineInfo, setEngineInfo] = useState<EngineInfo>({
    engine_mode: 'local',
    key_status: 'key not set',
    model: 'deterministic-local',
  });

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isInitializing, setIsInitializing] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);

  const [scoresByRoll, setScoresByRoll] = useState<
    Record<number, Record<string, ScoreEntry>>
  >({});
  const [activeRoll, setActiveRoll] = useState<number | null>(null);
  const [rowFlashes, setRowFlashes] = useState<Record<number, RowFlashState>>({});
  const [lastIgnoredPill, setLastIgnoredPill] = useState<string | null>(null);
  const [statusBanner, setStatusBanner] = useState<{
    type: 'save' | 'edit' | 'error' | 'ignore' | 'info';
    text: string;
  } | null>(null);
  const [pendingGrace, setPendingGrace] = useState<{
    marks: number;
    message: string;
  } | null>(null);
  const [activityLog, setActivityLog] = useState<ActivityLogItem[]>([]);

  const [exportData, setExportData] = useState<ExportDataResponse | null>(null);
  const [isRefreshingExport, setIsRefreshingExport] = useState(false);

  const refreshHealth = useCallback(async (keys: ApiKeys) => {
    try {
      const res = await fetchHealth(keys);
      if (res.engine) setEngineInfo(res.engine);
    } catch {
      // backend might be starting; keep default local badge
    }
  }, []);

  useEffect(() => {
    refreshHealth(apiKeys);
  }, [apiKeys, refreshHealth]);

  const triggerRowFlash = (rollNo: number, state: RowFlashState) => {
    setRowFlashes((prev) => ({ ...prev, [rollNo]: state }));
    setTimeout(() => {
      setRowFlashes((prev) => ({ ...prev, [rollNo]: null }));
    }, 1400);
  };

  const appendLog = (
    transcript: string,
    type: ActivityLogItem['type'],
    message: string
  ) => {
    const item: ActivityLogItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      timestamp: new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }),
      transcript,
      type,
      message,
    };
    setActivityLog((prev) => [item, ...prev].slice(0, 40));
  };

  const syncFromBackend = useCallback(async (sid: string) => {
    setIsRefreshingExport(true);
    try {
      const data = await fetchExportData(sid);
      setExportData(data);
      const nextMap: Record<number, Record<string, ScoreEntry>> = {};
      for (const entry of data.scores) {
        if (!nextMap[entry.roll_no]) nextMap[entry.roll_no] = {};
        nextMap[entry.roll_no][entry.anchor] = entry;
      }
      setScoresByRoll(nextMap);
    } catch {
      // ignore if session not ready
    } finally {
      setIsRefreshingExport(false);
    }
  }, []);

  const startSessionWithConfig = useCallback(
    async (
      targetMode: GradingMode,
      targetAnchors: string[],
      targetMaxMarks: number,
      targetVault: PiiVaultState
    ) => {
      const knownRolls = Object.keys(targetVault.rollToName)
        .map(Number)
        .filter((n) => Number.isFinite(n));
      if (knownRolls.length === 0) return;

      setIsInitializing(true);
      try {
        const res = await initSession({
          mode: targetMode,
          questions: targetMode === 'written' ? targetAnchors : [],
          rubric_items: targetMode === 'oral' ? targetAnchors : [],
          max_marks: targetMaxMarks,
          known_rolls: knownRolls,
          allow_unknown_rolls: false,
        });
        setSessionId(res.session_id);
        setScoresByRoll({});
        setExportData(null);
        setPendingGrace(null);
        setActivityLog([]);
        setStatusBanner(null);
        setLastIgnoredPill(null);
        setActiveRoll(Math.min(...knownRolls));
        setActiveTab('grade');
      } catch (err) {
        setStatusBanner({
          type: 'error',
          text:
            err instanceof Error ? err.message : 'Failed to initialize session.',
        });
      } finally {
        setIsInitializing(false);
      }
    },
    []
  );

  const handleVaultLoaded = (newVault: PiiVaultState, preset?: DemoPreset) => {
    setVault(newVault);
    savePiiVault(newVault);
    if (preset) {
      setMode(preset.mode);
      setAnchors(preset.anchors);
      setMaxMarks(preset.maxMarks);
      void startSessionWithConfig(
        preset.mode,
        preset.anchors,
        preset.maxMarks,
        newVault
      );
    }
  };

  const handleModeChange = (newMode: GradingMode) => {
    setMode(newMode);
    const defaultAnchors =
      newMode === 'written'
        ? ['Q1', 'Q2', 'Q3', 'Q4']
        : ['Clarity', 'Depth', 'Ethics', 'Composure'];
    setAnchors(defaultAnchors);
    if (Object.keys(vault.rollToName).length > 0) {
      void startSessionWithConfig(newMode, defaultAnchors, maxMarks, vault);
    }
  };

  const handleSubmitTranscript = async (transcript: string) => {
    if (!sessionId) {
      setStatusBanner({
        type: 'error',
        text: 'Please load a roster and start a session first.',
      });
      return;
    }

    setIsProcessing(true);
    try {
      const res = await sendVoiceCommand(sessionId, transcript, mode, apiKeys);
      if (res.engine) setEngineInfo(res.engine);

      // 1. IGNORE (self-talk)
      if (res.intent === 'ignore') {
        setLastIgnoredPill(transcript);
        setStatusBanner({
          type: 'ignore',
          text: res.message ?? 'Ignored self-talk.',
        });
        appendLog(transcript, 'ignore', res.message ?? 'Ignored self-talk');
        notifyAction('Ignored', replyMode, 'ignore', speechLocale);
        return;
      }

      // 2. BULK GRACE (pending confirmation)
      if (res.intent === 'bulk_grace') {
        if (res.pending) {
          const match = res.message?.match(/add\s+([\d.]+)\s+grace/i);
          const marks = match ? Number(match[1]) : 1;
          setPendingGrace({
            marks,
            message: res.message ?? 'Confirm bulk grace marks?',
          });
          setStatusBanner({ type: 'info', text: res.message ?? '' });
          appendLog(transcript, 'grace', res.message ?? 'Pending grace');
          notifyAction(res.message ?? 'Confirm grace marks', replyMode, 'success', speechLocale);
        } else {
          const msg = res.voice_error || res.message || 'Could not queue grace.';
          setStatusBanner({ type: 'error', text: msg });
          appendLog(transcript, 'error', msg);
          notifyAction(msg, replyMode, 'error', speechLocale);
        }
        return;
      }

      // 3. CONFIRM / CANCEL GRACE / UNDO
      if (
        res.intent === 'confirm_grace' ||
        res.intent === 'cancel_grace' ||
        res.intent === 'undo'
      ) {
        if (res.intent !== 'undo') setPendingGrace(null);
        const msg = res.message ?? 'Done.';
        setStatusBanner({ type: res.ok ? 'info' : 'error', text: msg });
        appendLog(transcript, res.ok ? 'info' : 'error', msg);
        notifyAction(msg, replyMode, res.ok ? 'success' : 'error', speechLocale);
        if (res.ok) await syncFromBackend(sessionId);
        return;
      }

      // 4. STATUS
      if (res.intent === 'status' && res.status) {
        const totalStudents = Object.keys(vault.rollToName).length;
        const graded = res.status.students_graded;
        const remaining = Math.max(0, totalStudents - graded);
        const msg = `${graded} of ${totalStudents} students graded (${remaining} remaining, ${res.status.total_entries} entries).`;
        setStatusBanner({ type: 'info', text: msg });
        appendLog(transcript, 'info', msg);
        notifyAction(msg, replyMode, 'success', speechLocale);
        return;
      }

      // 5. MULTI-SLICE GRADE / EDIT
      if (res.multi && res.results) {
        const isEdit = res.intent === 'edit';
        const savedMessages: string[] = [];
        const errorMessages: string[] = [];

        setScoresByRoll((prev) => {
          const next = { ...prev };
          for (const item of res.results!) {
            if (item.ok && item.entry) {
              const r = item.entry.roll_no;
              next[r] = { ...(next[r] ?? {}), [item.entry.anchor]: item.entry };
              triggerRowFlash(r, isEdit ? 'amber' : 'green');
              savedMessages.push(`${item.entry.anchor}=${item.entry.score}`);
            } else {
              errorMessages.push(item.voice_error || item.message);
              triggerRowFlash(item.roll_no, 'red');
            }
          }
          return next;
        });

        if (res.roll_no) setActiveRoll(res.roll_no);

        if (res.ok === false || (errorMessages.length > 0 && savedMessages.length === 0)) {
          const errText =
            errorMessages.join(' | ') || res.voice_error || res.message || 'Command rejected.';
          setStatusBanner({ type: 'error', text: errText });
          appendLog(transcript, 'error', errText);
          notifyAction(errText, replyMode, 'error', speechLocale);
        } else {
          const okText = `Roll ${res.roll_no}: ${savedMessages.join(', ')} (Total ${res.total})`;
          const fullText =
            errorMessages.length > 0
              ? `${okText} • Warning: ${errorMessages.join('; ')}`
              : okText;
          setStatusBanner({
            type: isEdit ? 'edit' : 'save',
            text: fullText,
          });
          appendLog(transcript, isEdit ? 'edit' : 'save', fullText);
          const spokenText = `Roll ${res.roll_no} saved, ${res.total}`;
          notifyAction(spokenText, replyMode, 'success', speechLocale);
          void syncFromBackend(sessionId);
        }
        return;
      }

      // 6. SINGLE GRADE / EDIT
      if (res.ok && res.entry) {
        const entry = res.entry;
        const isEdit = res.intent === 'edit';
        setScoresByRoll((prev) => ({
          ...prev,
          [entry.roll_no]: {
            ...(prev[entry.roll_no] ?? {}),
            [entry.anchor]: entry,
          },
        }));
        setActiveRoll(entry.roll_no);
        triggerRowFlash(entry.roll_no, isEdit ? 'amber' : 'green');
        const totalSuffix = res.total !== undefined ? ` (Total ${res.total})` : '';
        const msg = res.message
          ? `${res.message}${totalSuffix}`
          : `Saved Roll ${entry.roll_no} ${entry.anchor} = ${entry.score}${totalSuffix}`;
        setStatusBanner({ type: isEdit ? 'edit' : 'save', text: msg });
        appendLog(transcript, isEdit ? 'edit' : 'save', msg);
        const spokenText = `Roll ${entry.roll_no} saved, ${res.total ?? entry.score}`;
        notifyAction(spokenText, replyMode, 'success', speechLocale);
        void syncFromBackend(sessionId);
        return;
      }

      // 7. REJECTION / OUT OF BOUNDS / ERROR
      const errMsg = res.voice_error || res.message || 'Command rejected.';
      if (res.roll_no) triggerRowFlash(res.roll_no, 'red');
      else if (activeRoll) triggerRowFlash(activeRoll, 'red');
      setStatusBanner({ type: 'error', text: errMsg });
      appendLog(transcript, 'error', errMsg);
      notifyAction(errMsg, replyMode, 'error', speechLocale);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Network error.';
      setStatusBanner({ type: 'error', text: msg });
      notifyAction(msg, replyMode, 'error', speechLocale);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleConfirmGrace = async (action: 'confirm' | 'cancel') => {
    if (!sessionId) return;
    setIsProcessing(true);
    try {
      const res = await confirmGrace(sessionId, action);
      setPendingGrace(null);
      setStatusBanner({ type: res.ok ? 'info' : 'error', text: res.message });
      appendLog(`Grace ${action}`, 'grace', res.message);
      notifyAction(
        res.message,
        replyMode,
        res.ok ? 'success' : 'error',
        speechLocale
      );
      if (res.ok) await syncFromBackend(sessionId);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleManualEdit = async (
    rollNo: number,
    anchor: string,
    score: number,
    comment: string
  ) => {
    if (!sessionId) return;
    const res = await manualEditScore(sessionId, rollNo, anchor, score, comment);
    if (res.ok && res.entry) {
      setScoresByRoll((prev) => ({
        ...prev,
        [rollNo]: { ...(prev[rollNo] ?? {}), [anchor]: res.entry },
      }));
      triggerRowFlash(rollNo, 'amber');
      setStatusBanner({ type: 'edit', text: res.message });
      void syncFromBackend(sessionId);
    } else {
      const msg = res.voice_error || res.message || 'Invalid score.';
      triggerRowFlash(rollNo, 'red');
      setStatusBanner({ type: 'error', text: msg });
      notifyAction(msg, replyMode, 'error', speechLocale);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 pb-10">
      <TopBar
        mode={mode}
        onModeChange={handleModeChange}
        replyMode={replyMode}
        onReplyModeChange={setReplyMode}
        engineInfo={engineInfo}
        onOpenSettings={() => setSettingsOpen(true)}
        vaultCount={Object.keys(vault.rollToName).length}
      />

      {/* Primary Navigation Tabs */}
      <nav className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl gap-1 px-3 sm:px-5">
          <button
            type="button"
            onClick={() => setActiveTab('setup')}
            className={`inline-flex items-center gap-1.5 border-b-2 px-3.5 py-2.5 text-xs font-semibold transition ${
              activeTab === 'setup'
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Sliders className="h-3.5 w-3.5" />
            1. Setup &amp; Vault
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('grade')}
            className={`inline-flex items-center gap-1.5 border-b-2 px-3.5 py-2.5 text-xs font-semibold transition ${
              activeTab === 'grade'
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Mic className="h-3.5 w-3.5" />
            2. Voice Grading
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab('review');
              if (sessionId) void syncFromBackend(sessionId);
            }}
            className={`inline-flex items-center gap-1.5 border-b-2 px-3.5 py-2.5 text-xs font-semibold transition ${
              activeTab === 'review'
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <BarChart2 className="h-3.5 w-3.5" />
            3. Review &amp; Export
          </button>
        </div>
      </nav>

      {/* Active Tab Content */}
      {activeTab === 'setup' && (
        <SetupPanel
          mode={mode}
          anchors={anchors}
          maxMarks={maxMarks}
          feedbackLang={feedbackLang}
          vault={vault}
          sessionId={sessionId}
          isInitializing={isInitializing}
          onUpdateConfig={(cfg) => {
            setMode(cfg.mode);
            setAnchors(cfg.anchors);
            setMaxMarks(cfg.maxMarks);
            setFeedbackLang(cfg.feedbackLang);
          }}
          onVaultLoaded={handleVaultLoaded}
          onStartSession={() =>
            void startSessionWithConfig(mode, anchors, maxMarks, vault)
          }
        />
      )}

      {activeTab === 'grade' && (
        <GradingWorkspace
          mode={mode}
          anchors={anchors}
          maxMarks={maxMarks}
          vault={vault}
          scoresByRoll={scoresByRoll}
          activeRoll={activeRoll}
          onSelectRoll={setActiveRoll}
          rowFlashes={rowFlashes}
          speechLocale={speechLocale}
          onSpeechLocaleChange={setSpeechLocale}
          onSubmitTranscript={handleSubmitTranscript}
          onQuickCommand={(cmd) =>
            void handleSubmitTranscript(
              cmd === 'undo' ? 'undo' : 'Kitne baaki hain?'
            )
          }
          onManualEdit={handleManualEdit}
          pendingGrace={pendingGrace}
          onConfirmGrace={handleConfirmGrace}
          isProcessing={isProcessing}
          lastIgnoredPill={lastIgnoredPill}
          statusBanner={statusBanner}
          activityLog={activityLog}
        />
      )}

      {activeTab === 'review' && (
        <ReviewTabs
          mode={mode}
          anchors={anchors}
          maxMarks={maxMarks}
          feedbackLang={feedbackLang}
          vault={vault}
          scoresByRoll={scoresByRoll}
          exportData={exportData}
          onRefreshExport={() =>
            sessionId ? syncFromBackend(sessionId) : Promise.resolve()
          }
          isRefreshing={isRefreshingExport}
        />
      )}

      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        apiKeys={apiKeys}
        onSaveKeys={(keys) => {
          setApiKeys(keys);
          saveApiKeys(keys);
          void refreshHealth(keys);
        }}
        engineInfo={engineInfo}
      />
    </div>
  );
}

export default App;
