import React, { useEffect, useRef } from 'react';
import { LogEntry } from '../types';

interface LogViewerProps {
  logs: LogEntry[];
}

export const LogViewer: React.FC<LogViewerProps> = ({ logs }) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <div className="bg-black rounded-lg shadow-inner overflow-hidden flex flex-col h-64 border border-gray-800">
      <div className="px-4 py-2 bg-gray-900 border-b border-gray-800 flex items-center justify-between">
        <span className="text-xs font-mono text-green-400">root@hyper-ai:~/logs $</span>
        <div className="flex gap-1">
          <div className="w-2 h-2 rounded-full bg-red-500"></div>
          <div className="w-2 h-2 rounded-full bg-yellow-500"></div>
          <div className="w-2 h-2 rounded-full bg-green-500"></div>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 font-mono text-xs space-y-1 scrollbar-hide">
        {logs.length === 0 && (
            <div className="text-gray-600 italic opacity-50">Waiting for agent activity...</div>
        )}
        {logs.map((log) => (
          <div key={log.id} className="flex gap-2">
            <span className="text-gray-500 shrink-0">[{log.timestamp.toLocaleTimeString()}]</span>
            <span className={`shrink-0 font-bold w-16 ${
              log.level === 'info' ? 'text-blue-400' :
              log.level === 'success' ? 'text-green-400' :
              log.level === 'warning' ? 'text-yellow-400' :
              'text-red-500'
            }`}>
              {log.level.toUpperCase()}
            </span>
            <span className="text-gray-300 break-words">
              {log.message} {log.detail && <span className="text-gray-500">| {log.detail}</span>}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};