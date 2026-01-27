import React from 'react';
import { Sidebar } from './Sidebar';
import { LogViewer } from './LogViewer';
import { ResultTable } from './ResultTable';
import { useDefectAnalysis } from '../hooks/useDefectAnalysis';

export const MainDashboard: React.FC = () => {
    const {
        rows,
        results,
        logs,
        stats,
        isProcessing,
        currentProcessingId,
        handleUpload,
        handleStart,
        handleStop
    } = useDefectAnalysis();

    const handleDownload = () => {
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
        a.download = 'submission.csv';
        a.click();
        window.URL.revokeObjectURL(url);
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
