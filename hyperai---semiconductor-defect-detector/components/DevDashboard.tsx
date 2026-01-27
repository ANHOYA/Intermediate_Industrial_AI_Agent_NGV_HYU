import React, { useState, useEffect } from 'react';
import { Sidebar } from './Sidebar';
import { LogViewer } from './LogViewer';
import { ResultTable } from './ResultTable';
import { useDefectAnalysis } from '../hooks/useDefectAnalysis';
import { calculateMetrics, parseLabeledCsv, Metrics } from '../utils/metrics';

// Default labeled CSV path (configured in vite/proxy or copied asset)
import defaultLabeledCsv from '../assets/default_labeled.csv?raw';

export const DevDashboard: React.FC = () => {
    const {
        rows,
        results,
        logs,
        stats,
        isProcessing,
        currentProcessingId,
        handleUpload,
        handleStart,
        handleStop,
        setRows
    } = useDefectAnalysis();

    const [groundTruth, setGroundTruth] = useState<Record<string, number>>({});
    const [metrics, setMetrics] = useState<Metrics | null>(null);

    // Load default labeled data on mount
    useEffect(() => {
        if (defaultLabeledCsv) {
            handleLabeledUpload(defaultLabeledCsv);
        }
    }, []);

    // Update metrics whenever results change
    useEffect(() => {
        if (Object.keys(groundTruth).length > 0 && Object.keys(results).length > 0) {
            const m = calculateMetrics(results, groundTruth);
            setMetrics(m);
        }
    }, [results, groundTruth]);

    const handleLabeledUpload = (content: string) => {
        const map = parseLabeledCsv(content);
        setGroundTruth(map);
        // Also clear existing results if needed? or just update truth
        console.log(`Loaded ${Object.keys(map).length} ground truth labels`);
    };

    const handleDownload = () => {
        // Same as main dashboard
        const header = "id,label\n";
        const csvContent = rows.map(row => {
            const res = results[row.id];
            const label = res ? res.label : 0;
            return `${row.id},${label}`;
        }).join("\n");

        const blob = new Blob([header + csvContent], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'dev_submission.csv';
        a.click();
        window.URL.revokeObjectURL(url);
    };

    return (
        <div className="flex h-screen w-full bg-gray-100 overflow-hidden font-sans border-t-4 border-orange-500">
            <Sidebar
                onUpload={handleUpload}
                onLabeledUpload={handleLabeledUpload}
                stats={stats}
                isProcessing={isProcessing}
                onStart={handleStart}
                onStop={handleStop}
                onDownload={handleDownload}
                isDevMode={true}
            />

            <main className="flex-1 flex flex-col min-w-0 h-full">
                <header className="bg-white border-b border-gray-200 px-8 py-4 flex justify-between items-center shadow-sm">
                    <div>
                        <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
                            Dev Dashboard <span className="bg-orange-100 text-orange-800 text-xs px-2 py-1 rounded">Developer Mode</span>
                        </h2>
                        <p className="text-sm text-gray-500">Eval F1 Score & Calibration</p>
                    </div>

                    {/* Metrics Panel */}
                    {metrics && (
                        <div className="flex gap-4 text-sm">
                            <div className="bg-blue-50 px-3 py-1 rounded border border-blue-200">
                                <span className="text-gray-500 block text-xs">F1 Score</span>
                                <span className="font-bold text-blue-700 text-lg">{(metrics.f1Score * 100).toFixed(1)}%</span>
                            </div>
                            <div className="bg-gray-50 px-3 py-1 rounded border border-gray-200">
                                <span className="text-gray-500 block text-xs">Accuracy</span>
                                <span className="font-bold text-gray-700">{(metrics.accuracy * 100).toFixed(1)}%</span>
                            </div>
                            <div className="bg-gray-50 px-3 py-1 rounded border border-gray-200 hidden xl:block">
                                <span className="text-gray-500 block text-xs">Precision</span>
                                <span className="font-bold text-gray-700">{(metrics.precision * 100).toFixed(1)}%</span>
                            </div>
                            <div className="bg-gray-50 px-3 py-1 rounded border border-gray-200 hidden xl:block">
                                <span className="text-gray-500 block text-xs">Recall</span>
                                <span className="font-bold text-gray-700">{(metrics.recall * 100).toFixed(1)}%</span>
                            </div>
                            <div className="bg-orange-50 px-3 py-1 rounded border border-orange-200 flex flex-col text-xs justify-center">
                                <div>TP: {metrics.tp} / FP: {metrics.fp}</div>
                                <div>TN: {metrics.tn} / FN: {metrics.fn}</div>
                            </div>
                        </div>
                    )}
                </header>

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
};
