export type GradingMode = 'written' | 'oral';
export type ReplyMode = 'voice' | 'haptic';
export type FeedbackLanguage = 'English' | 'Hindi' | 'Both';
export type SpeechLocale = 'en-IN' | 'hi-IN';

export interface EngineInfo {
  engine_mode: 'local' | 'gemini' | 'openai' | string;
  key_status: string;
  model: string;
}

export interface ScoreEntry {
  roll_no: number;
  anchor: string;
  score: number;
  max_marks: number;
  comment: string;
  tags: string[];
  timestamp: string;
}

export interface StudentSummary {
  roll_no: number;
  average: number;
  scores: Record<string, number>;
  feedback: {
    english: string;
    hindi: string;
    transliteration?: string;
  };
}

export interface ExportDataResponse {
  session_id: string;
  mode: GradingMode;
  max_marks: number;
  scores: ScoreEntry[];
  student_summaries: StudentSummary[];
  weakness_heatmap: Record<string, Record<string, number>>;
}

export interface SessionInitRequest {
  mode: GradingMode;
  questions: string[];
  rubric_items: string[];
  max_marks: number;
  known_rolls: number[];
  allow_unknown_rolls: boolean;
}

export interface SessionInitResponse {
  session_id: string;
  mode: GradingMode;
  max_marks: number;
  questions: string[];
  rubric_items: string[];
  known_rolls: number[];
}

export interface VoiceResultItem {
  ok: boolean;
  message: string;
  voice_error?: string;
  entry?: ScoreEntry;
  anchor: string;
  roll_no: number;
}

export interface VoiceCommandResponse {
  intent: string;
  ok?: boolean;
  multi?: boolean;
  roll_no?: number;
  total?: number;
  results?: VoiceResultItem[];
  entry?: ScoreEntry;
  enhanced_comment?: string;
  message?: string;
  voice_error?: string;
  pending?: boolean;
  status?: {
    session_id: string;
    mode: string;
    students_graded: number;
    total_entries: number;
    undo_depth: number;
    pending_grace: { marks: number } | null;
    finished: boolean;
  };
  engine?: EngineInfo;
}

export interface LocalStudentRecord {
  roll_no: number;
  student_name: string;
  original_row?: Record<string, string | number>;
}

export interface PiiVaultState {
  rollToName: Record<number, string>;
  originalRows: Record<number, Record<string, string | number>>;
  originalHeaders: string[];
  rollColumnKey: string;
  nameColumnKey: string;
}

export interface ApiKeys {
  geminiKey: string;
  openaiKey: string;
}

export type RowFlashState = 'green' | 'amber' | 'red' | null;

export interface ActivityLogItem {
  id: string;
  timestamp: string;
  transcript: string;
  type: 'save' | 'edit' | 'error' | 'ignore' | 'info' | 'grace';
  message: string;
}
