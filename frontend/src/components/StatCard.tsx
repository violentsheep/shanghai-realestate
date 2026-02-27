import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string;
  sub?: string;
  prev?: number | null;
  curr?: number | null;
  accent?: string;
}

export function StatCard({ title, value, sub, prev, curr, accent = 'blue' }: StatCardProps) {
  let trend: 'up' | 'down' | 'flat' | null = null;
  let pct = '';

  if (prev != null && curr != null && prev !== 0) {
    const diff = ((curr - prev) / prev) * 100;
    if (Math.abs(diff) < 0.5) trend = 'flat';
    else if (diff > 0) trend = 'up';
    else trend = 'down';
    pct = `${diff > 0 ? '+' : ''}${diff.toFixed(1)}%`;
  }

  const accentMap: Record<string, string> = {
    blue:   'from-blue-500 to-blue-600',
    emerald:'from-emerald-500 to-emerald-600',
    violet: 'from-violet-500 to-violet-600',
    amber:  'from-amber-500 to-amber-600',
    rose:   'from-rose-500 to-rose-600',
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-500 font-medium">{title}</span>
        {trend && (
          <span className={`flex items-center gap-0.5 text-xs font-semibold px-2 py-0.5 rounded-full ${
            trend === 'up' ? 'bg-rose-50 text-rose-600' :
            trend === 'down' ? 'bg-emerald-50 text-emerald-600' :
            'bg-gray-100 text-gray-500'
          }`}>
            {trend === 'up' && <TrendingUp size={11} />}
            {trend === 'down' && <TrendingDown size={11} />}
            {trend === 'flat' && <Minus size={11} />}
            {pct}
          </span>
        )}
      </div>
      <div className={`text-2xl font-bold bg-gradient-to-r ${accentMap[accent]} bg-clip-text text-transparent`}>
        {value}
      </div>
      {sub && <div className="text-xs text-gray-400">{sub}</div>}
    </div>
  );
}
