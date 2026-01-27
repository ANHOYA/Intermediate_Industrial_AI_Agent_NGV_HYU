import React, { useRef } from 'react';
import { AgentStats } from '../types';

interface SidebarProps {
  onUpload: (content: string) => void;
  stats: AgentStats;
  isProcessing: boolean;
  onStart: () => void;
  onStop: () => void;
  onDownload: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  onUpload,
  stats,
  isProcessing,
  onStart,
  onStop,
  onDownload
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        if (event.target?.result) {
          onUpload(event.target.result as string);
        }
      };
      reader.readAsText(file);
    }
  };

  return (
    <aside className="w-80 bg-white border-r border-gray-200 h-full flex flex-col shadow-sm z-10">
      <div className="p-6 border-b border-gray-100 bg-hanyang text-white">
        <h1 className="text-xl font-bold tracking-tight">HYPER AI</h1>
        <p className="text-sm text-gray-300 opacity-80">Defect Detection Agent</p>
      </div>

      <div className="p-6 flex-1 overflow-y-auto space-y-8">

        {/* API Key Section Removed - Handled via Env Vars */}

        {/* Data Section */}
        <section>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Data Source</h3>
          <div className="space-y-3">
            <div className="p-4 border-2 border-dashed border-gray-300 rounded-lg hover:border-hanyang transition-colors text-center cursor-pointer"
              onClick={() => fileInputRef.current?.click()}>
              <p className="text-sm text-gray-600">Click to upload <code className="bg-gray-100 px-1 rounded">csv file</code></p>
              <input
                type="file"
                ref={fileInputRef}
                accept=".csv"
                className="hidden"
                onChange={handleFileChange}
              />
            </div>
            <div className="text-xs text-gray-500 flex justify-between">
              <span>Loaded Rows:</span>
              <span className="font-mono font-bold text-gray-900">{stats.total}</span>
            </div>
          </div>
        </section>

        {/* Stats Section */}
        <section className="bg-gray-50 p-4 rounded-lg border border-gray-200">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Real-time Stats</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="block text-xs text-gray-500">Processed</span>
              <span className="text-lg font-bold text-gray-900">{stats.processed} <span className="text-gray-400 text-sm">/ {stats.total}</span></span>
            </div>
            <div>
              <span className="block text-xs text-gray-500">Progress</span>
              <span className="text-lg font-bold text-hanyang">
                {stats.total > 0 ? Math.round((stats.processed / stats.total) * 100) : 0}%
              </span>
            </div>
            <div>
              <span className="block text-xs text-gray-500">Normal (0)</span>
              <span className="text-lg font-bold text-green-600">{stats.normal}</span>
            </div>
            <div>
              <span className="block text-xs text-gray-500">Defect (1)</span>
              <span className="text-lg font-bold text-red-600">{stats.abnormal}</span>
            </div>
          </div>
        </section>

        {/* Actions */}
        <section className="space-y-3">
          {!isProcessing ? (
            <button
              onClick={onStart}
              disabled={stats.total === 0}
              className={`w-full py-3 px-4 rounded-md shadow-sm text-sm font-medium text-white transition-all
                  ${stats.total === 0 ? 'bg-gray-300 cursor-not-allowed' : 'bg-hanyang hover:bg-hanyang-light hover:shadow-md'}`}
            >
              Start Analysis
            </button>
          ) : (
            <button
              onClick={onStop}
              className="w-full py-3 px-4 rounded-md shadow-sm text-sm font-medium text-white bg-red-500 hover:bg-red-600 transition-all"
            >
              Stop Process
            </button>
          )}

          <button
            onClick={onDownload}
            disabled={stats.processed === 0}
            className="w-full py-3 px-4 rounded-md border border-gray-300 shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-all disabled:opacity-50"
          >
            Download CSV
          </button>
        </section>

      </div>

      <div className="p-4 border-t border-gray-200 bg-gray-50">
        <p className="text-xs text-gray-400 text-center">
          Powered by Saltlux Luxia & React <br />
          Github : <a href="https://github.com/ANHOYA/Intermediate_Industrial_AI_Agent_NGV_HYU" target="_blank" rel="noopener noreferrer" className="hover:text-gray-600 underline">Link</a>
        </p>
      </div>
    </aside>
  );
};