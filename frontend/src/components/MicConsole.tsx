import React, { useEffect, useRef, useState } from 'react';
import {
  Mic,
  MicOff,
  Send,
  Undo2,
  BarChart3,
  Sparkles,
  Keyboard,
  Volume2,
} from 'lucide-react';
import type { GradingMode, SpeechLocale } from '../types';
import { ORAL_SAMPLE_UTTERANCES, SAMPLE_UTTERANCES } from '../lib/demos';
import {
  registerMicAbortHandler,
  stopSpeaking,
  subscribeSpeaking,
} from '../lib/audio';

interface SpeechRecognitionEventLike {
  results: {
    [index: number]: {
      [index: number]: { transcript: string };
      isFinal: boolean;
    };
    length: number;
  };
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort?: () => void;
}

interface MicConsoleProps {
  mode: GradingMode;
  speechLocale: SpeechLocale;
  onSpeechLocaleChange: (loc: SpeechLocale) => void;
  onSubmitTranscript: (transcript: string) => void;
  onQuickCommand: (cmd: 'undo' | 'status') => void;
  isProcessing: boolean;
  lastIgnoredPill: string | null;
  statusBanner: {
    type: 'save' | 'edit' | 'error' | 'ignore' | 'info';
    text: string;
  } | null;
}

export const MicConsole: React.FC<MicConsoleProps> = ({
  mode,
  speechLocale,
  onSpeechLocaleChange,
  onSubmitTranscript,
  onQuickCommand,
  isProcessing,
  lastIgnoredPill,
  statusBanner,
}) => {
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [micMode, setMicMode] = useState<'toggle' | 'hold'>('toggle');
  const [liveTranscript, setLiveTranscript] = useState('');
  const [manualText, setManualText] = useState('');
  const [speechSupported, setSpeechSupported] = useState(true);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const finalTranscriptRef = useRef('');
  const latestTranscriptRef = useRef('');
  const isListeningRef = useRef(false);
  const activeCaptureModeRef = useRef<'toggle' | 'hold'>('toggle');
  const silenceTimerRef = useRef<number | null>(null);
  const bargeInTimerRef = useRef<number | null>(null);

  const clearSilenceTimer = () => {
    if (silenceTimerRef.current !== null) {
      window.clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  };

  const clearBargeInTimer = () => {
    if (bargeInTimerRef.current !== null) {
      window.clearTimeout(bargeInTimerRef.current);
      bargeInTimerRef.current = null;
    }
  };

  const abortListening = () => {
    clearBargeInTimer();
    clearSilenceTimer();
    finalTranscriptRef.current = '';
    latestTranscriptRef.current = '';
    setLiveTranscript('');
    const rec = recognitionRef.current;
    recognitionRef.current = null;
    if (rec) {
      try {
        rec.onresult = null;
        rec.onend = null;
        rec.onerror = null;
        if (typeof rec.abort === 'function') {
          rec.abort();
        } else {
          rec.stop();
        }
      } catch {
        // ignore
      }
    }
    isListeningRef.current = false;
    setIsListening(false);
  };

  useEffect(() => {
    const win = window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    if (!win.SpeechRecognition && !win.webkitSpeechRecognition) {
      setSpeechSupported(false);
    }
    const unsubSpeaking = subscribeSpeaking(setIsSpeaking);
    const unsubAbort = registerMicAbortHandler(abortListening);
    return () => {
      unsubSpeaking();
      unsubAbort();
      clearBargeInTimer();
      clearSilenceTimer();
    };
  }, []);

  const stopListening = () => {
    clearBargeInTimer();
    clearSilenceTimer();
    if (!isListeningRef.current) return;
    try {
      recognitionRef.current?.stop();
    } catch {
      // ignore
    }
    isListeningRef.current = false;
    setIsListening(false);
  };

  const startListening = (captureMode: 'toggle' | 'hold' = micMode) => {
    if (isListeningRef.current || isProcessing) return;
    const win = window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    const SpeechRec = win.SpeechRecognition || win.webkitSpeechRecognition;
    if (!SpeechRec) {
      setSpeechSupported(false);
      return;
    }

    // Instant Barge-In: stop any active TTS immediately and wait 150 ms before recognition.start()
    stopSpeaking();
    clearBargeInTimer();
    clearSilenceTimer();
    activeCaptureModeRef.current = captureMode;
    finalTranscriptRef.current = '';
    latestTranscriptRef.current = '';
    setLiveTranscript('');
    isListeningRef.current = true;
    setIsListening(true);

    bargeInTimerRef.current = window.setTimeout(() => {
      bargeInTimerRef.current = null;
      if (!isListeningRef.current) return;
      try {
        const rec = new SpeechRec();
        rec.lang = speechLocale;
        rec.continuous = true;
        rec.interimResults = true;

        rec.onresult = (event: SpeechRecognitionEventLike) => {
          let interim = '';
          let finalStr = '';
          for (let i = 0; i < event.results.length; i++) {
            const res = event.results[i];
            if (res.isFinal) {
              finalStr += res[0].transcript + ' ';
            } else {
              interim += res[0].transcript;
            }
          }
          const combined = (finalStr + interim).trim();
          finalTranscriptRef.current = finalStr.trim();
          latestTranscriptRef.current = combined;
          setLiveTranscript(combined);

          if (activeCaptureModeRef.current === 'toggle' && combined) {
            clearSilenceTimer();
            silenceTimerRef.current = window.setTimeout(() => {
              stopListening();
            }, 1600);
          }
        };

        rec.onerror = () => {
          clearSilenceTimer();
          isListeningRef.current = false;
          setIsListening(false);
        };

        rec.onend = () => {
          clearSilenceTimer();
          isListeningRef.current = false;
          setIsListening(false);
          const text = (
            finalTranscriptRef.current || latestTranscriptRef.current
          ).trim();
          if (text) {
            onSubmitTranscript(text);
            finalTranscriptRef.current = '';
            latestTranscriptRef.current = '';
            setLiveTranscript('');
          }
        };

        recognitionRef.current = rec;
        rec.start();
      } catch {
        clearSilenceTimer();
        isListeningRef.current = false;
        setIsListening(false);
      }
    }, 150);
  };

  // Spacebar push-to-talk (when not typing in an input/textarea)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || e.repeat) return;
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button') {
        return;
      }
      e.preventDefault();
      startListening('hold');
    };
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return;
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button') {
        return;
      }
      e.preventDefault();
      stopListening();
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  });

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = manualText.trim();
    if (!trimmed || isProcessing) return;
    stopSpeaking();
    onSubmitTranscript(trimmed);
    setManualText('');
  };

  const sampleList = mode === 'oral' ? ORAL_SAMPLE_UTTERANCES : SAMPLE_UTTERANCES;

  return (
    <div className="flex flex-col gap-3">
      {/* Status Banner & Ignored Self-Talk Pill */}
      {(statusBanner || lastIgnoredPill) && (
        <div className="flex flex-wrap items-center gap-2">
          {statusBanner && (
            <div
              className={`flex-1 rounded-xl px-3 py-2 text-xs font-medium ring-1 ${
                statusBanner.type === 'save'
                  ? 'bg-emerald-50 text-emerald-900 ring-emerald-200'
                  : statusBanner.type === 'edit'
                    ? 'bg-amber-50 text-amber-900 ring-amber-200'
                    : statusBanner.type === 'error'
                      ? 'bg-red-50 text-red-900 ring-red-300'
                      : statusBanner.type === 'ignore'
                        ? 'bg-slate-100 text-slate-600 ring-slate-200'
                        : 'bg-indigo-50 text-indigo-900 ring-indigo-200'
              }`}
            >
              {statusBanner.text}
            </div>
          )}
          {lastIgnoredPill && (
            <span className="inline-flex items-center rounded-full bg-slate-200/80 px-2.5 py-1 text-[11px] font-medium text-slate-500">
              Ignored self-talk: &ldquo;{lastIgnoredPill}&rdquo;
            </span>
          )}
        </div>
      )}

      {/* No-Mic Evaluator Test Strip */}
      <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-xs">
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-500">
            <Sparkles className="h-3.5 w-3.5 text-indigo-500" />
            Try Sample Voice Utterances
          </span>
          <span className="text-[10px] text-slate-400">No-mic evaluator strip</span>
        </div>

        <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-2">
          {sampleList.map((sample) => (
            <button
              key={sample.id}
              type="button"
              disabled={isProcessing}
              onClick={() => {
                stopSpeaking();
                onSubmitTranscript(sample.transcript);
              }}
              title={sample.transcript}
              className="flex flex-col items-start rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-left transition hover:border-indigo-300 hover:bg-indigo-50/50 disabled:opacity-50"
            >
              <span className="text-[11px] font-semibold text-slate-800 line-clamp-1">
                {sample.label}
              </span>
              <span className="text-[10px] text-slate-500 line-clamp-1">
                {sample.transcript}
              </span>
            </button>
          ))}
        </div>

        {/* Direct Transcript Input */}
        <form onSubmit={handleManualSubmit} className="mt-2.5 flex gap-1.5">
          <input
            type="text"
            value={manualText}
            onChange={(e) => setManualText(e.target.value)}
            placeholder={
              mode === 'oral'
                ? 'Type Hinglish command (e.g. "Roll 103 Clarity saadhe saat")'
                : 'Type Hinglish command (e.g. "Roll 14 Q1 saadhe saat")'
            }
            className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-slate-50 px-3 py-2 text-xs text-slate-900 focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-200 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!manualText.trim() || isProcessing}
            className="inline-flex shrink-0 items-center gap-1 rounded-xl bg-slate-900 px-3 py-2 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40"
          >
            <Send className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Send</span>
          </button>
        </form>
      </div>

      {/* Thumb-Friendly Mic Console (sticky on mobile bottom) */}
      <div className="sticky bottom-2 z-20 rounded-2xl border border-slate-200 bg-slate-900 p-3 text-white shadow-xl lg:static">
        <div className="flex items-center justify-between gap-2 text-[11px]">
          {/* Speech Locale Toggle */}
          <div
            className="flex items-center gap-1 rounded-lg bg-slate-800 p-0.5"
            title="en-IN handles Hinglish best; hi-IN supports full Devanagari Hindi"
          >
            {(['en-IN', 'hi-IN'] as SpeechLocale[]).map((loc) => (
              <button
                key={loc}
                type="button"
                onClick={() => onSpeechLocaleChange(loc)}
                title={
                  loc === 'en-IN'
                    ? 'en-IN handles Hinglish best'
                    : 'hi-IN supports full Devanagari Hindi'
                }
                className={`rounded-md px-2 py-1 font-medium transition ${
                  speechLocale === loc
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-300 hover:text-white'
                }`}
              >
                {loc}
              </button>
            ))}
          </div>

          {/* Tap vs Hold */}
          <div className="flex items-center gap-1 rounded-lg bg-slate-800 p-0.5">
            <button
              type="button"
              onClick={() => setMicMode('toggle')}
              className={`rounded-md px-2 py-1 font-medium transition ${
                micMode === 'toggle'
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Tap
            </button>
            <button
              type="button"
              onClick={() => setMicMode('hold')}
              className={`rounded-md px-2 py-1 font-medium transition ${
                micMode === 'hold'
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Hold
            </button>
          </div>

          {/* Quick Undo & Status */}
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => {
                stopSpeaking();
                onQuickCommand('undo');
              }}
              disabled={isProcessing}
              title="Undo last action"
              className="inline-flex items-center gap-1 rounded-lg bg-slate-800 px-2 py-1 text-slate-200 hover:bg-slate-700 disabled:opacity-40"
            >
              <Undo2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Undo</span>
            </button>
            <button
              type="button"
              onClick={() => {
                stopSpeaking();
                onQuickCommand('status');
              }}
              disabled={isProcessing}
              title="Check grading status"
              className="inline-flex items-center gap-1 rounded-lg bg-slate-800 px-2 py-1 text-slate-200 hover:bg-slate-700 disabled:opacity-40"
            >
              <BarChart3 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Status</span>
            </button>
          </div>
        </div>

        {/* TTS Active Hint */}
        {isSpeaking && !isListening && (
          <div className="mt-2 flex items-center gap-1.5 rounded-lg bg-indigo-950/90 px-3 py-1.5 text-xs font-medium text-indigo-200 ring-1 ring-indigo-500/40">
            <Volume2 className="h-3.5 w-3.5 shrink-0 animate-pulse text-indigo-400" />
            <span>Speaking... Tap Mic to interrupt</span>
          </div>
        )}

        {/* Live Transcript Preview */}
        {liveTranscript && (
          <div className="mt-2 rounded-lg bg-slate-800/90 px-3 py-1.5 text-xs text-indigo-200">
            &ldquo;{liveTranscript}&rdquo;
          </div>
        )}

        {/* Main Thumb Mic Button */}
        <div className="mt-2.5 flex items-center gap-3">
          <button
            type="button"
            disabled={!speechSupported || isProcessing}
            onClick={
              micMode === 'toggle'
                ? () => (isListening ? stopListening() : startListening('toggle'))
                : undefined
            }
            onPointerDown={micMode === 'hold' ? () => startListening('hold') : undefined}
            onPointerUp={micMode === 'hold' ? stopListening : undefined}
            onPointerLeave={
              micMode === 'hold' && isListening ? stopListening : undefined
            }
            className={`flex h-14 flex-1 items-center justify-center gap-2.5 rounded-xl text-sm font-bold shadow-md transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ${
              isListening
                ? 'animate-pulse bg-rose-600 text-white ring-4 ring-rose-400/40'
                : 'bg-indigo-600 text-white hover:bg-indigo-500'
            }`}
          >
            {isListening ? (
              <>
                <MicOff className="h-5 w-5" />
                <span>Listening ({speechLocale}) — Tap/Release to Grade</span>
              </>
            ) : (
              <>
                <Mic className="h-5 w-5" />
                <span>
                  {speechSupported
                    ? micMode === 'toggle'
                      ? 'Tap to Speak Grade'
                      : 'Hold to Speak Grade'
                    : 'Web Speech Unavailable (Use Test Strip)'}
                </span>
              </>
            )}
          </button>
        </div>

        <div className="mt-1.5 flex items-center justify-center gap-1 text-[10px] text-slate-400">
          <Keyboard className="h-3 w-3" />
          <span>Tip: Hold Spacebar anywhere for push-to-talk</span>
        </div>
      </div>
    </div>
  );
};
