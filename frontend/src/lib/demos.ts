import type { GradingMode, PiiVaultState } from '../types';

export interface DemoPreset {
  id: 'physics_written' | 'upsc_oral';
  label: string;
  mode: GradingMode;
  anchors: string[];
  maxMarks: number;
  students: Array<{ roll_no: number; name: string; section?: string }>;
}

export const PHYSICS_WRITTEN_DEMO: DemoPreset = {
  id: 'physics_written',
  label: '10-Student Physics Written Demo',
  mode: 'written',
  anchors: ['Q1', 'Q2', 'Q3', 'Q4'],
  maxMarks: 10,
  students: [
    { roll_no: 11, name: 'Aarav Sharma', section: 'XII-A' },
    { roll_no: 12, name: 'Ananya Verma', section: 'XII-A' },
    { roll_no: 13, name: 'Rohan Deshmukh', section: 'XII-A' },
    { roll_no: 14, name: 'Priya Nair', section: 'XII-A' },
    { roll_no: 15, name: 'Kabir Mehta', section: 'XII-A' },
    { roll_no: 16, name: 'Sneha Iyer', section: 'XII-A' },
    { roll_no: 17, name: 'Vikram Singh', section: 'XII-A' },
    { roll_no: 18, name: 'Meera Kulkarni', section: 'XII-A' },
    { roll_no: 19, name: 'Arjun Reddy', section: 'XII-A' },
    { roll_no: 20, name: 'Divya Joshi', section: 'XII-A' },
  ],
};

export const UPSC_ORAL_DEMO: DemoPreset = {
  id: 'upsc_oral',
  label: '8-Candidate UPSC Oral Viva Demo',
  mode: 'oral',
  anchors: ['Clarity', 'Depth', 'Ethics', 'Composure'],
  maxMarks: 10,
  students: [
    { roll_no: 101, name: 'Siddharth Rao', section: 'Panel-1' },
    { roll_no: 102, name: 'Neha Chaturvedi', section: 'Panel-1' },
    { roll_no: 103, name: 'Pranav Kulkarni', section: 'Panel-1' },
    { roll_no: 104, name: 'Ishita Banerjee', section: 'Panel-1' },
    { roll_no: 105, name: 'Aditya Mishra', section: 'Panel-1' },
    { roll_no: 106, name: 'Kavya Menon', section: 'Panel-1' },
    { roll_no: 107, name: 'Harshvardhan Patel', section: 'Panel-1' },
    { roll_no: 108, name: 'Ritu Saxena', section: 'Panel-1' },
  ],
};

export function demoToVault(preset: DemoPreset): PiiVaultState {
  const rollToName: Record<number, string> = {};
  const originalRows: Record<number, Record<string, string | number>> = {};
  const groupCol = preset.mode === 'oral' ? 'Panel' : 'Class';

  for (const s of preset.students) {
    rollToName[s.roll_no] = s.name;
    originalRows[s.roll_no] = {
      'Roll No': s.roll_no,
      'Student Name': s.name,
      [groupCol]: s.section ?? '',
    };
  }

  return {
    rollToName,
    originalRows,
    originalHeaders: ['Roll No', 'Student Name', groupCol],
    rollColumnKey: 'Roll No',
    nameColumnKey: 'Student Name',
  };
}

export interface SampleUtterance {
  id: string;
  label: string;
  badge: string;
  transcript: string;
}

export const SAMPLE_UTTERANCES: SampleUtterance[] = [
  {
    id: 'compound',
    label: '1. Compound + Fraction + Venting',
    badge: 'Multi-slice',
    transcript:
      'Roll 14: Q1 saadhe saat good structure, Q2 do are ye kya ghatiya diagram banaya hai, Q3 paanch',
  },
  {
    id: 'selftalk',
    label: '2. Pure Self-Talk',
    badge: 'Ignored',
    transcript: 'Are ye kya diagram banaya hai',
  },
  {
    id: 'oob',
    label: '3. Out-of-Bounds (12/10)',
    badge: 'Rejected',
    transcript: 'Roll 15 Q1 baarah',
  },
  {
    id: 'edit',
    label: '4. Single Edit',
    badge: 'Edit',
    transcript: 'Roll 14 Q2 ko chaar kar do',
  },
  {
    id: 'grace',
    label: '5. Bulk Grace',
    badge: 'Confirm',
    transcript: 'Sabko Q3 mein ek grace mark',
  },
  {
    id: 'status',
    label: '6. Status Query',
    badge: 'Status',
    transcript: 'Kitne baaki hain?',
  },
];

export const ORAL_SAMPLE_UTTERANCES: SampleUtterance[] = [
  {
    id: 'oral-compound',
    label: '1. Multi-Rubric + Fraction',
    badge: 'Multi-slice',
    transcript:
      'Roll 103 Clarity aath, Depth paanch, Ethics saadhe saat, Composure nau',
  },
  {
    id: 'oral-selftalk',
    label: '2. Pure Self-Talk',
    badge: 'Ignored',
    transcript: 'Are ye kya bol raha hai',
  },
  {
    id: 'oral-oob',
    label: '3. Out-of-Bounds (12/10)',
    badge: 'Rejected',
    transcript: 'Roll 105 Clarity baarah',
  },
  {
    id: 'oral-edit',
    label: '4. Single Edit',
    badge: 'Edit',
    transcript: 'Roll 103 Depth ko saat kar do',
  },
  {
    id: 'oral-grace',
    label: '5. Bulk Grace',
    badge: 'Confirm',
    transcript: 'Sabko Ethics mein ek grace mark',
  },
  {
    id: 'oral-status',
    label: '6. Status Query',
    badge: 'Status',
    transcript: 'Kitne baaki hain?',
  },
];
