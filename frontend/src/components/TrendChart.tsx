// @ts-nocheck
import React from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, AreaChart, Area
} from 'recharts';
import { DayRecord } from '../types';
import { formatDate } from '../utils/data';

interface ChartData {
  date: string;
  [key: string]: number | string | null;
}

interface TrendChartProps {
  data: DayRecord[];
  title: string;
  series: {
    key: string;
    label: string;
    color: string;
    getValue: (r: DayRecord) => number | null;
    unit?: string;
  }[];
  area?: boolean;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-lg p-3 text-sm">
      <p className="font-semibold text-gray-700 mb-2">{label}</p>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-gray-500">{p.name}：</span>
          <span className="font-medium text-gray-800">
            {p.value != null ? p.value.toLocaleString('zh-CN') : '—'}
            {p.unit || ''}
          </span>
        </div>
      ))}
    </div>
  );
};

export function TrendChart({ data, title, series, area = false }: TrendChartProps) {
  const chartData: ChartData[] = data.map(r => {
    const row: ChartData = { date: formatDate(r.date) };
    series.forEach(s => { row[s.key] = s.getValue(r); });
    return row;
  });

  const ChartComponent = area ? AreaChart : LineChart;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={220}>
        <ChartComponent data={chartData}>
          <defs>
            {series.map(s => (
              <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={s.color} stopOpacity={0.15} />
                <stop offset="95%" stopColor={s.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} width={50}
            tickFormatter={(v) => v >= 10000 ? `${(v/10000).toFixed(0)}万` : v.toLocaleString('zh-CN')} />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
          {series.map(s =>
            area ? (
              <Area key={s.key} type="monotone" dataKey={s.key} name={s.label}
                stroke={s.color} strokeWidth={2} fill={`url(#grad-${s.key})`}
                dot={false} activeDot={{ r: 4 }} connectNulls />
            ) : (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.label}
                stroke={s.color} strokeWidth={2}
                dot={false} activeDot={{ r: 4 }} connectNulls />
            )
          )}
        </ChartComponent>
      </ResponsiveContainer>
    </div>
  );
}
