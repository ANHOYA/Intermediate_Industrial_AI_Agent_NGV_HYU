import { AnalysisResult, CsvRow } from '../types';

export interface Metrics {
    tp: number;
    tn: number;
    fp: number;
    fn: number;
    accuracy: number;
    precision: number;
    recall: number;
    f1Score: number;
}

export const parseLabeledCsv = (content: string): Record<string, number> => {
    const lines = content.split('\n').filter(l => l.trim());
    const header = lines[0].split(',').map(h => h.trim());
    const idIdx = header.indexOf('id');
    const labelIdx = header.indexOf('label');

    if (idIdx === -1 || labelIdx === -1) return {};

    const map: Record<string, number> = {};
    lines.slice(1).forEach(line => {
        const cols = line.split(',').map(c => c.trim());
        if (cols[idIdx] && cols[labelIdx]) {
            map[cols[idIdx]] = parseInt(cols[labelIdx], 10);
        }
    });
    return map;
};

export const calculateMetrics = (
    results: Record<string, AnalysisResult>,
    groundTruth: Record<string, number>
): Metrics => {
    let tp = 0, tn = 0, fp = 0, fn = 0;

    Object.values(results).forEach(res => {
        const trueLabel = groundTruth[res.id];
        if (trueLabel === undefined) return; // Skip if no ground truth

        const predLabel = res.label;

        if (predLabel === 1 && trueLabel === 1) tp++;
        else if (predLabel === 0 && trueLabel === 0) tn++;
        else if (predLabel === 1 && trueLabel === 0) fp++;
        else if (predLabel === 0 && trueLabel === 1) fn++;
    });

    const accuracy = (tp + tn) / (tp + tn + fp + fn) || 0;
    const precision = tp / (tp + fp) || 0;
    const recall = tp / (tp + fn) || 0;
    const f1Score = (2 * precision * recall) / (precision + recall) || 0;

    return { tp, tn, fp, fn, accuracy, precision, recall, f1Score };
};
