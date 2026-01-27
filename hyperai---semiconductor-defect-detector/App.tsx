import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { LogViewer } from './components/LogViewer';
import { ResultTable } from './components/ResultTable';
import { AppState, CsvRow, AnalysisResult, LogEntry, AgentStats, KEYS } from './types';
import { DEFAULT_API_KEY } from './constants';
import { observeImage } from './services/saltlux';

function App() {
  // const [apiKey, setApiKey] = useState(DEFAULT_API_KEY); // Removed in favor of Env Var
  const [isProcessing, setIsProcessing] = useState(false);
  const [shouldStop, setShouldStop] = useState(false);

  const [rows, setRows] = useState<CsvRow[]>([]);
  const [results, setResults] = useState<Record<string, AnalysisResult>>({});
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [currentProcessingId, setCurrentProcessingId] = useState<string | null>(null);

  // Helper to add logs
  const addLog = (level: LogEntry['level'], message: string, detail?: string) => {
    const entry: LogEntry = {
      id: Math.random().toString(36).substring(7),
      timestamp: new Date(),
      level,
      message,
      detail
    };
    setLogs(prev => [...prev, entry]);
  };

  // CSV Parsing Logic
  const handleUpload = (content: string) => {
    try {
      const lines = content.split('\n').filter(line => line.trim() !== '');
      if (lines.length < 2) throw new Error("File is empty or invalid");

      const headers = lines[0].split(',').map(h => h.trim());
      const idIdx = headers.indexOf('id');
      const urlIdx = headers.indexOf('img_url');

      if (idIdx === -1 || urlIdx === -1) {
        throw new Error("CSV must contain 'id' and 'img_url' columns");
      }

      const parsedRows: CsvRow[] = lines.slice(1).map(line => {
        // Handle CSVs that might have commas in values? (Simplification: assuming standard simple CSV)
        const values = line.split(',').map(v => v.trim());
        return {
          id: values[idIdx],
          img_url: values[urlIdx],
          // Store other columns if needed
        };
      }).filter(r => r.id && r.img_url);

      setRows(parsedRows);
      setResults({});
      setLogs([]);
      addLog('info', `Loaded ${parsedRows.length} rows from CSV`);
    } catch (e: any) {
      addLog('error', 'Failed to parse CSV', e.message);
      alert("Invalid CSV format. Please ensure headers 'id' and 'img_url' exist.");
    }
  };

  // Agent Logic: Decision Maker
  const decide = (obs: Record<string, boolean>) => {
    const defectCount = Object.values(obs).filter(Boolean).length;
    const label = defectCount >= 1 ? 1 : 0;
    // Uncertain if 0 (missed?) or 1 (false positive?)
    const uncertain = defectCount === 0 || defectCount === 1;
    return { label, uncertain, defectCount };
  };

  // Agent Logic: Core Workflow
  const processRow = async (row: CsvRow): Promise<AnalysisResult> => {
    addLog('info', `Processing ${row.id}...`);

    try {
      // Step 1: Observe (Normal)
      addLog('info', `[${row.id}] Step 1: Initial Observation (Strict=False)`);
      const obs1 = await observeImage(row.img_url, false, DEFAULT_API_KEY);
      const decision1 = decide(obs1);

      let finalLabel: 0 | 1 = decision1.label as 0 | 1;
      let finalObs = obs1;

      // Step 2: Check Uncertainty
      if (decision1.uncertain) {
        addLog('warning', `[${row.id}] Uncertain result (defects=${decision1.defectCount}). Re-checking...`);

        // Step 3: Observe (Strict)
        // strict=True: More conservative, "If ambiguous, false".
        const obs2 = await observeImage(row.img_url, true, DEFAULT_API_KEY);
        const decision2 = decide(obs2);

        // Logic from baseline:
        // If re-check finds defect (label2 == 1), confirm as Abnormal.
        // Else keep original result.
        if (decision2.label === 1) {
          finalLabel = 1;
          finalObs = obs2; // Use the strict observation as the proof
          addLog('success', `[${row.id}] Re-check confirmed defect.`);
        } else {
          // Keep original label (likely 0 if dec1 was 0, or 1 if dec1 was 1 but strict said 0? 
          // Wait, baseline says: "If re-check finds defect, Abnormal. Else keep label1".
          // If label1 was 1 and label2 is 0 -> We keep label1 (1). 
          // (This logic seems to bias towards Abnormal if EITHER normal OR strict finds it, 
          // UNLESS label1 was 0 and label2 is 0).
          addLog('info', `[${row.id}] Re-check did not confirm new defects. Maintaining original.`);
        }
      } else {
        addLog('success', `[${row.id}] Decision clear.`);
      }

      const result: AnalysisResult = {
        id: row.id,
        label: finalLabel,
        status: 'completed',
        obs: finalObs,
        timestamp: Date.now()
      };

      setResults(prev => ({ ...prev, [row.id]: result }));
      return result;

    } catch (error: any) {
      addLog('error', `[${row.id}] Failed`, error.message);
      return {
        id: row.id,
        label: 0, // Fallback to normal on error
        status: 'error',
        timestamp: Date.now()
      };
    }
  };

  // Orchestrator
  const startAnalysis = async () => {
    if (rows.length === 0) return;
    setIsProcessing(true);
    setShouldStop(false);
    addLog('info', 'Starting analysis batch...');

    // Process sequentially
    for (let i = 0; i < rows.length; i++) {
      if (shouldStop) break; // This checks stale state in closure, need Ref or check inside loop?
      // Actually state updates inside async loop in React are tricky. 
      // We'll check a ref or just use the set state callback? 
      // For simplicity in this structure, we handle stop via a mutable variable check if we extracted loop,
      // but here we are in a functional component.
      // Better: check a ref.
    }
    // Rewriting loop to be cleaner with useEffect or just a recursive function
    // But basic for loop with await is fine if we check a ref.
  };

  // We need a ref for stopping because the loop closure captures 'shouldStop' as false initially.
  const stopRef = React.useRef(false);

  const handleStart = async () => {
    stopRef.current = false;
    setIsProcessing(true);
    addLog('info', '--- BATCH STARTED ---');

    for (const row of rows) {
      if (stopRef.current) {
        addLog('warning', 'Batch processing stopped by user.');
        break;
      }

      // Skip if already done? No, let's re-run or maybe simple skip. 
      // Let's re-run for this demo to allow retries.

      setCurrentProcessingId(row.id);

      await processRow(row);

      // Rate limit sleep (200ms)
      await new Promise(r => setTimeout(r, 200));
    }

    setCurrentProcessingId(null);
    setIsProcessing(false);
    addLog('info', '--- BATCH FINISHED ---');
  };

  const handleStop = () => {
    stopRef.current = true;
    setShouldStop(true); // Trigger UI update
  };

  const handleDownload = () => {
    const header = "id,label\n";
    const csvContent = rows.map(row => {
      const res = results[row.id];
      // Default to 0 if not processed
      const label = res ? res.label : 0;
      return `${row.id},${label}`;
    }).join("\n");

    const blob = new Blob([header + csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'submission.csv';
    a.click();
    window.URL.revokeObjectURL(url);
    addLog('success', 'Downloaded submission.csv');
  };

  // Stats calculation
  const stats: AgentStats = {
    total: rows.length,
    processed: Object.keys(results).length,
    normal: Object.values(results).filter((r: AnalysisResult) => r.label === 0).length,
    abnormal: Object.values(results).filter((r: AnalysisResult) => r.label === 1).length,
    errors: Object.values(results).filter((r: AnalysisResult) => r.status === 'error').length,
  };

  return (
    <div className="flex h-screen w-full bg-gray-100 overflow-hidden font-sans">
      <Sidebar
        onUpload={handleUpload}
        stats={stats}
        isProcessing={isProcessing}
        onStart={handleStart}
        onStop={handleStop}
        onDownload={handleDownload}
      />

      <main className="flex-1 flex flex-col min-w-0 h-full">
        {/* Header */}
        <header className="bg-white border-b border-gray-200 px-8 py-4 flex justify-between items-center shadow-sm">
          <div>
            <h2 className="text-xl font-bold text-gray-800">Dashboard</h2>
            <p className="text-sm text-gray-500">Multimodal Agent Monitoring</p>
          </div>
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${isProcessing ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`}></span>
            <span className="text-sm font-medium text-gray-600">
              {isProcessing ? 'Agent Active' : 'Agent Idle'}
            </span>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 p-8 flex flex-col gap-6 min-h-0">
          <LogViewer logs={logs} />
          <ResultTable
            rows={rows}
            results={results}
            currentProcessingId={currentProcessingId}
          />
        </div>
      </main>
    </div>
  );
}

export default App;