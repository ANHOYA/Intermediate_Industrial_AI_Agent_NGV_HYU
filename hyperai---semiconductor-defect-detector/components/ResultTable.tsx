import React from 'react';
import { AnalysisResult, CsvRow, OBS_ITEMS } from '../types';

interface ResultTableProps {
  rows: CsvRow[];
  results: Record<string, AnalysisResult>;
  currentProcessingId: string | null;
}

export const ResultTable: React.FC<ResultTableProps> = ({ rows, results, currentProcessingId }) => {
  return (
    <div className="flex-1 bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col min-h-0 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-white">
        <h2 className="text-lg font-semibold text-gray-800">Analysis Results</h2>
        <span className="text-xs text-gray-400 uppercase tracking-wide">
          Total Items: {rows.length}
        </span>
      </div>
      
      <div className="flex-1 overflow-auto">
        <table className="w-full text-left border-collapse">
          <thead className="bg-gray-50 sticky top-0 z-10">
            <tr>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider border-b border-gray-200">ID</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider border-b border-gray-200">Image</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider border-b border-gray-200">Status</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider border-b border-gray-200">Prediction</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider border-b border-gray-200">Details (Defects)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center text-gray-400 text-sm">
                  Upload a CSV file to view data
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const result = results[row.id];
                const isCurrent = row.id === currentProcessingId;
                
                return (
                  <tr key={row.id} className={`hover:bg-gray-50 transition-colors ${isCurrent ? 'bg-blue-50' : ''}`}>
                    <td className="px-6 py-4 text-sm font-medium text-gray-900 font-mono">
                      {row.id}
                    </td>
                    <td className="px-6 py-4">
                       <div className="group relative w-12 h-12">
                          <img 
                            src={row.img_url} 
                            alt={row.id} 
                            className="w-full h-full object-cover rounded border border-gray-200 shadow-sm"
                            loading="lazy"
                          />
                          {/* Hover Zoom */}
                          <div className="absolute top-0 left-0 w-48 h-48 bg-white border border-gray-200 shadow-xl rounded-lg opacity-0 group-hover:opacity-100 pointer-events-none z-50 hidden group-hover:block transform translate-x-14 -translate-y-12">
                             <img src={row.img_url} alt={row.id} className="w-full h-full object-contain p-1" />
                          </div>
                       </div>
                    </td>
                    <td className="px-6 py-4">
                      {isCurrent ? (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 animate-pulse">
                          Processing
                        </span>
                      ) : result ? (
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          result.status === 'error' ? 'bg-gray-100 text-gray-800' : 'bg-green-100 text-green-800'
                        }`}>
                          {result.status === 'error' ? 'Error' : 'Done'}
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-400">
                          Pending
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {result && result.status === 'completed' ? (
                        <span className={`font-bold text-sm ${result.label === 1 ? 'text-red-600' : 'text-green-600'}`}>
                          {result.label === 1 ? 'DEFECT (1)' : 'NORMAL (0)'}
                        </span>
                      ) : (
                        <span className="text-gray-300">-</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap gap-1">
                        {result && result.obs ? (
                          Object.entries(result.obs).filter(([_, v]) => v).length > 0 ? (
                            Object.entries(result.obs)
                              .filter(([_, value]) => value)
                              .map(([key, _]) => {
                                const desc = OBS_ITEMS.find(item => item.key === key)?.desc || key;
                                return (
                                  <span key={key} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-100" title={desc}>
                                    {key.replace(/_/g, ' ')}
                                  </span>
                                );
                              })
                          ) : (
                            result.status === 'completed' && <span className="text-xs text-gray-400 italic">No defects detected</span>
                          )
                        ) : (
                          <span className="text-gray-300">-</span>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};