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
  { key: "defect_package", desc: "패키지 불량 (파손, 크랙, 정렬불량 등)" },
  { key: "defect_pin", desc: "핀 불량 (결손, 휨, 솔더, 체결이상 등)" },
] as const;

export const KEYS = OBS_ITEMS.map(item => item.key);