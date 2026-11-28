import type { ReplyMode } from '../types';

let sharedAudioCtx: AudioContext | null = null;
let speakingState = false;
let cooldownTimer: number | null = null;
let micAbortHandler: (() => void) | null = null;
const speakingListeners = new Set<(speaking: boolean) => void>();

function setSpeakingState(next: boolean): void {
  if (speakingState === next) return;
  speakingState = next;
  speakingListeners.forEach((cb) => {
    try {
      cb(next);
    } catch {
      // ignore subscriber errors
    }
  });
}

export function getIsSpeaking(): boolean {
  return speakingState;
}

export function subscribeSpeaking(cb: (speaking: boolean) => void): () => void {
  speakingListeners.add(cb);
  cb(speakingState);
  return () => {
    speakingListeners.delete(cb);
  };
}

export function registerMicAbortHandler(handler: (() => void) | null): () => void {
  micAbortHandler = handler;
  return () => {
    if (micAbortHandler === handler) {
      micAbortHandler = null;
    }
  };
}

export function stopSpeaking(): void {
  if (cooldownTimer !== null) {
    window.clearTimeout(cooldownTimer);
    cooldownTimer = null;
  }
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    try {
      window.speechSynthesis.cancel();
    } catch {
      // ignore speechSynthesis errors
    }
  }
  setSpeakingState(false);
}

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtx) return null;
  if (!sharedAudioCtx) {
    sharedAudioCtx = new AudioCtx();
  }
  if (sharedAudioCtx.state === 'suspended') {
    sharedAudioCtx.resume().catch(() => {});
  }
  return sharedAudioCtx;
}

/**
 * Web Audio API double-beep for out-of-bounds / error rejection.
 */
export function playDoubleBeep(): void {
  const ctx = getAudioContext();
  if (!ctx) return;

  const playTone = (startTime: number, freq: number, duration: number) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(freq, startTime);
    gain.gain.setValueAtTime(0.14, startTime);
    gain.gain.exponentialRampToValueAtTime(0.001, startTime + duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(startTime);
    osc.stop(startTime + duration);
  };

  const now = ctx.currentTime;
  playTone(now, 440, 0.11);
  playTone(now + 0.16, 330, 0.14);
}

/**
 * Subtle success chime for Silent Haptic or quick confirmation.
 */
export function playSoftChime(): void {
  const ctx = getAudioContext();
  if (!ctx) return;
  const now = ctx.currentTime;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(660, now);
  osc.frequency.exponentialRampToValueAtTime(880, now + 0.09);
  gain.gain.setValueAtTime(0.08, now);
  gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(now);
  osc.stop(now + 0.12);
}

export function triggerHaptic(pattern: number | number[] = 40): void {
  if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
    try {
      navigator.vibrate(pattern);
    } catch {
      // ignore on unsupported desktop browsers
    }
  }
}

export function speakText(text: string, lang: 'en-IN' | 'hi-IN' = 'en-IN'): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
  try {
    if (cooldownTimer !== null) {
      window.clearTimeout(cooldownTimer);
      cooldownTimer = null;
    }
    // Half-duplex gating: abort any active SpeechRecognition before TTS starts
    micAbortHandler?.();
    window.speechSynthesis.cancel();

    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = lang;
    utter.rate = 1.02;
    const voices = window.speechSynthesis.getVoices();
    const matched = voices.find((v) => v.lang.toLowerCase().startsWith(lang.toLowerCase().split('-')[0]));
    if (matched) utter.voice = matched;

    const handleEnd = () => {
      if (cooldownTimer !== null) {
        window.clearTimeout(cooldownTimer);
      }
      // 250 ms post-speech cooldown before passive capture resumes
      cooldownTimer = window.setTimeout(() => {
        cooldownTimer = null;
        setSpeakingState(false);
      }, 250);
    };

    utter.onend = handleEnd;
    utter.onerror = handleEnd;

    setSpeakingState(true);
    window.speechSynthesis.speak(utter);
  } catch {
    setSpeakingState(false);
  }
}

export const speak = speakText;

export function notifyAction(
  message: string,
  replyMode: ReplyMode,
  kind: 'success' | 'error' | 'ignore' = 'success',
  lang: 'en-IN' | 'hi-IN' = 'en-IN'
): void {
  if (kind === 'error') {
    playDoubleBeep();
    triggerHaptic([70, 50, 70]);
    if (replyMode === 'voice') {
      speakText(message, lang);
    }
    return;
  }

  if (kind === 'ignore') {
    if (replyMode === 'haptic') {
      triggerHaptic(20);
    }
    return;
  }

  if (replyMode === 'voice') {
    speakText(message, lang);
  } else {
    playSoftChime();
    triggerHaptic(35);
  }
}
