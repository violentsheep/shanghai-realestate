import { DayRecord } from '../types';

// Vite 在构建时把 JSON import 打包进去，无需运行时请求
// 数据文件通过 GitHub Actions 每日更新后重新构建
import rawData from '../../../data/history/data.json';

export const allData: DayRecord[] = rawData as DayRecord[];

export function getLatest(): DayRecord | null {
  if (allData.length === 0) return null;
  return allData[allData.length - 1];
}

export function getLast(n: number): DayRecord[] {
  return allData.slice(-n);
}

export function formatArea(sqm: number | null): string {
  if (sqm === null) return '—';
  if (sqm >= 10000) return `${(sqm / 10000).toFixed(2)}万㎡`;
  return `${sqm.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}㎡`;
}

export function formatNum(n: number | null): string {
  if (n === null) return '—';
  return n.toLocaleString('zh-CN');
}

export function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
