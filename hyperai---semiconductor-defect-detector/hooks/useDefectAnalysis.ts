
import { useState, useCallback, useRef } from 'react';
import { CsvRow, AnalysisResult, LogEntry, AgentStats } from '../types';
// import { DEFAULT_API_KEY } from '../constants';
import { observeImage } from '../services/saltlux';

export const useDefectAnalysis = () => {
    const [isProcessing, setIsProcessing] = useState(false);
    const [rows, setRows] = useState<CsvRow[]>([]);
    const [results, setResults] = useState<Record<string, AnalysisResult>>({});
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [currentProcessingId, setCurrentProcessingId] = useState<string | null>(null);
    const stopRef = useRef(false);

    const addLog = useCallback((level: LogEntry['level'], message: string, detail?: string) => {
        const entry: LogEntry = {
            id: Math.random().toString(36).substring(7),
            timestamp: new Date(),
            level,
            message,
            detail
        };
        setLogs(prev => [...prev, entry]);
    }, []);

    const decide = (obs: Record<string, boolean>) => {
        const defectCount = Object.values(obs).filter(Boolean).length;
        const label = defectCount >= 1 ? 1 : 0;
        const uncertain = defectCount === 0 || defectCount === 1;
        return { label, uncertain, defectCount };
    };

    const processRow = async (row: CsvRow): Promise<AnalysisResult> => {
        addLog('info', `Processing ${row.id}...`);

        try {
            addLog('info', `[${row.id}] Step 1: Initial Observation (Strict=False)`);
            const obs1 = await observeImage(row.img_url, false);
            const decision1 = decide(obs1);

            let finalLabel: 0 | 1 = decision1.label as 0 | 1;
            let finalObs = obs1;

            if (decision1.uncertain) {
                addLog('warning', `[${row.id}] Uncertain result (defects=${decision1.defectCount}). Re-checking...`);

                const obs2 = await observeImage(row.img_url, true);
                const decision2 = decide(obs2);

                if (decision2.label === 1) {
                    finalLabel = 1;
                    finalObs = obs2;
                    addLog('success', `[${row.id}] Re-check confirmed defect.`);
                } else {
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
                label: 0,
                status: 'error',
                timestamp: Date.now()
            };
        }
    };

    const handleStart = async () => {
        stopRef.current = false;
        setIsProcessing(true);
        addLog('info', '--- BATCH STARTED (Concurrency: 5) ---');

        const BATCH_SIZE = 10;

        // Helper to process a batch
        const processBatch = async (batch: CsvRow[]) => {
            const promises = batch.map(row => processRow(row));
            await Promise.all(promises);
        };

        for (let i = 0; i < rows.length; i += BATCH_SIZE) {
            if (stopRef.current) {
                addLog('warning', 'Batch processing stopped by user.');
                break;
            }

            const batch = rows.slice(i, i + BATCH_SIZE);
            setCurrentProcessingId(`Batch ${Math.floor(i / BATCH_SIZE) + 1}`); // Just for UI indication

            await processBatch(batch);

            // Small breathing room between batches
            await new Promise(r => setTimeout(r, 100));
        }

        setCurrentProcessingId(null);
        setIsProcessing(false);
        addLog('info', '--- BATCH FINISHED ---');
    };

    const handleStop = () => {
        stopRef.current = true;
    };

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
                const values = line.split(',').map(v => v.trim());
                return {
                    id: values[idIdx],
                    img_url: values[urlIdx]
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

    const stats: AgentStats = {
        total: rows.length,
        processed: Object.keys(results).length,
        normal: Object.values(results).filter((r) => r.label === 0).length,
        abnormal: Object.values(results).filter((r) => r.label === 1).length,
        errors: Object.values(results).filter((r) => r.status === 'error').length,
    };

    return {
        rows,
        results,
        logs,
        stats,
        isProcessing,
        currentProcessingId,
        handleUpload,
        handleStart,
        handleStop,
        stopRef,
        setRows
    };
};
