import type { ApiKeys, PiiVaultState } from '../types';

const VAULT_STORAGE_KEY = 'guru_vaani_pii_vault_v1';
const KEYS_STORAGE_KEY = 'guru_vaani_api_keys_v1';

export const EMPTY_VAULT: PiiVaultState = {
  rollToName: {},
  originalRows: {},
  originalHeaders: ['Roll No', 'Student Name'],
  rollColumnKey: 'Roll No',
  nameColumnKey: 'Student Name',
};

export function loadPiiVault(): PiiVaultState {
  try {
    const raw = localStorage.getItem(VAULT_STORAGE_KEY);
    if (!raw) return EMPTY_VAULT;
    const parsed = JSON.parse(raw) as PiiVaultState;
    return {
      rollToName: parsed.rollToName ?? {},
      originalRows: parsed.originalRows ?? {},
      originalHeaders: parsed.originalHeaders ?? ['Roll No', 'Student Name'],
      rollColumnKey: parsed.rollColumnKey ?? 'Roll No',
      nameColumnKey: parsed.nameColumnKey ?? 'Student Name',
    };
  } catch {
    return EMPTY_VAULT;
  }
}

export function savePiiVault(vault: PiiVaultState): void {
  try {
    localStorage.setItem(VAULT_STORAGE_KEY, JSON.stringify(vault));
  } catch {
    // ignore quota errors
  }
}

export function clearPiiVault(): void {
  try {
    localStorage.removeItem(VAULT_STORAGE_KEY);
  } catch {
    // ignore
  }
}

export function loadApiKeys(): ApiKeys {
  try {
    const raw = localStorage.getItem(KEYS_STORAGE_KEY);
    if (!raw) return { geminiKey: '', openaiKey: '' };
    const parsed = JSON.parse(raw) as Partial<ApiKeys>;
    return {
      geminiKey: parsed.geminiKey ?? '',
      openaiKey: parsed.openaiKey ?? '',
    };
  } catch {
    return { geminiKey: '', openaiKey: '' };
  }
}

export function saveApiKeys(keys: ApiKeys): void {
  try {
    localStorage.setItem(KEYS_STORAGE_KEY, JSON.stringify(keys));
  } catch {
    // ignore
  }
}
