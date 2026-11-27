import type {
  ApiKeys,
  EngineInfo,
  ExportDataResponse,
  SessionInitRequest,
  SessionInitResponse,
  VoiceCommandResponse,
} from '../types';

function buildHeaders(keys?: ApiKeys): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (keys?.geminiKey?.trim()) {
    headers['X-Gemini-Key'] = keys.geminiKey.trim();
  }
  if (keys?.openaiKey?.trim()) {
    headers['X-OpenAI-Key'] = keys.openaiKey.trim();
  }
  return headers;
}

export async function fetchHealth(keys?: ApiKeys): Promise<{
  status: string;
  service: string;
  version: string;
  engine: EngineInfo;
}> {
  const res = await fetch('/api/health', {
    method: 'GET',
    headers: buildHeaders(keys),
  });
  if (!res.ok) {
    throw new Error(`Health check failed (${res.status})`);
  }
  return res.json();
}

export async function initSession(
  payload: SessionInitRequest
): Promise<SessionInitResponse> {
  const res = await fetch('/api/session/init', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Session init failed (${res.status}): ${errText}`);
  }
  return res.json();
}

export async function sendVoiceCommand(
  sessionId: string,
  transcript: string,
  mode?: 'written' | 'oral',
  keys?: ApiKeys
): Promise<VoiceCommandResponse> {
  const res = await fetch('/api/voice/command', {
    method: 'POST',
    headers: buildHeaders(keys),
    body: JSON.stringify({
      session_id: sessionId,
      transcript,
      mode,
    }),
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Voice command failed (${res.status}): ${errText}`);
  }
  return res.json();
}

export async function confirmGrace(
  sessionId: string,
  action: 'confirm' | 'cancel'
): Promise<{ ok: boolean; message: string }> {
  const res = await fetch('/api/session/confirm-grace', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      action,
    }),
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Confirm grace failed (${res.status}): ${errText}`);
  }
  return res.json();
}

export async function manualEditScore(
  sessionId: string,
  rollNo: number,
  anchor: string,
  score: number,
  comment = ''
): Promise<{ ok: boolean; message: string; voice_error?: string; entry?: any }> {
  const res = await fetch('/api/session/manual-edit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      roll_no: rollNo,
      anchor,
      score,
      comment,
    }),
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Manual edit failed (${res.status}): ${errText}`);
  }
  return res.json();
}

export async function fetchExportData(
  sessionId: string
): Promise<ExportDataResponse> {
  const res = await fetch(
    `/api/session/export-data?session_id=${encodeURIComponent(sessionId)}`,
    { method: 'GET' }
  );
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Export data failed (${res.status}): ${errText}`);
  }
  return res.json();
}
