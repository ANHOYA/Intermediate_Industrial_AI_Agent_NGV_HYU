export interface CsvRow {
  id: string;
  img_url: string;
  [key: string]: string;
}

export interface AnalysisResult {
  id: string;
  label: 0 | 1;
  status: 'pending' | 'processing' | 'completed' | 'error';
  confidence?: number;
  reasoning?: string;
  obs?: Record<string, boolean>;
  timestamp: number;
}

export interface LogEntry {
  id: string;
  timestamp: Date;
  level: 'info' | 'success' | 'warning' | 'error';
  message: string;
  detail?: string;
}

export interface AgentStats {
  total: number;
  processed: number;
  normal: number;
  abnormal: number;
  errors: number;
}

export interface AppState {
  apiKey: string;
  isProcessing: boolean;
  rows: CsvRow[];
  results: Record<string, AnalysisResult>;
  logs: LogEntry[];
  currentProcessingId: string | null;
}

export const OBS_ITEMS = [
  { key: "package_damage", desc: "크랙/파손/깨짐 등 패키지 손상" },
  { key: "lead_missing_or_broken", desc: "리드 결손/단선" },
  { key: "lead_severe_bend_or_contact", desc: "심한 휨 또는 리드끼리 접촉" },
  { key: "solder_bridge_or_blob", desc: "솔더 브리지 또는 납땜 뭉침" },
  { key: "misalignment_severe", desc: "소자 위치가 과도하게 틀어짐" },
] as const;

export const KEYS = OBS_ITEMS.map(item => item.key);