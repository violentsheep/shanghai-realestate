import React, { useState } from 'react';
import { allData, getLatest, getLast, formatArea, formatNum } from '../utils/data';
import { StatCard } from '../components/StatCard';
import { TrendChart } from '../components/TrendChart';
import { Building2, TrendingUp, LayoutList, RefreshCw } from 'lucide-react';

const RANGES = [
  { label: '近30天', value: 30 },
  { label: '近60天', value: 60 },
  { label: '全部',   value: 9999 },
];

export default function Dashboard() {
  const [range, setRange] = useState(30);
  const latest = getLatest();
  const prev = allData.length >= 2 ? allData[allData.length - 2] : null;
  const chartData = getLast(range);

  if (!latest) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-4">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center">
          <Building2 size={24} className="text-white" />
        </div>
        <h1 className="text-lg font-bold text-gray-700">上海楼市数据</h1>
        <p className="text-sm text-gray-400">数据采集中，今日数据将于 08:30 后更新</p>
        <p className="text-xs text-gray-300">数据来源：上海市房地产交易中心</p>
      </div>
    );
  }

  const sh = latest.second_hand;
  const nh = latest.new_house;
  const li = latest.listing;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center">
              <Building2 size={16} className="text-white" />
            </div>
            <div>
              <h1 className="text-base font-bold text-gray-900">上海楼市数据</h1>
              <p className="text-xs text-gray-400">数据来源：上海市房地产交易中心</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <RefreshCw size={12} />
            <span>每日 08:00 更新</span>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">

        {/* 日期标题 */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-gray-900">
              {latest.date} 数据快报
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              一手房为当日成交 · 二手房为昨日网签（T+1）
            </p>
          </div>
          {/* 时间范围切换 */}
          <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
            {RANGES.map(r => (
              <button key={r.value}
                onClick={() => setRange(r.value)}
                className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-all ${
                  range === r.value
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}>
                {r.label}
              </button>
            ))}
          </div>
        </div>

        {/* ── 二手房 ── */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <LayoutList size={15} className="text-blue-500" />
            <h2 className="text-sm font-semibold text-gray-700">二手房（存量房网签）</h2>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <StatCard title="成交套数"
              value={`${formatNum(sh.units)} 套`}
              sub="昨日网签"
              curr={sh.units}
              prev={prev?.second_hand.units}
              accent="blue" />
            <StatCard title="成交面积"
              value={formatArea(sh.area)}
              sub="昨日网签"
              curr={sh.area}
              prev={prev?.second_hand.area}
              accent="blue" />
            <StatCard title="套均面积"
              value={sh.avg_area ? `${sh.avg_area} ㎡` : '—'}
              sub="成交面积 ÷ 套数"
              curr={sh.avg_area}
              prev={prev?.second_hand.avg_area}
              accent="violet" />
            <StatCard title="挂牌套数"
              value={`${formatNum(li.total)} 套`}
              sub="出售挂牌总量"
              curr={li.total}
              prev={prev?.listing.total}
              accent="amber" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <TrendChart
              data={chartData}
              title="二手房每日成交套数"
              area
              series={[{
                key: 'sh_units',
                label: '成交套数',
                color: '#3b82f6',
                getValue: r => r.second_hand.units,
              }]}
            />
            <TrendChart
              data={chartData}
              title="二手房套均面积走势（㎡）"
              series={[{
                key: 'sh_avg',
                label: '套均面积',
                color: '#8b5cf6',
                getValue: r => r.second_hand.avg_area,
              }]}
            />
          </div>
          <div className="mt-3">
            <TrendChart
              data={chartData}
              title="二手房挂牌套数趋势"
              area
              series={[{
                key: 'listing',
                label: '挂牌套数',
                color: '#f59e0b',
                getValue: r => r.listing.total,
              }]}
            />
          </div>
        </section>

        {/* ── 一手房 ── */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp size={15} className="text-emerald-500" />
            <h2 className="text-sm font-semibold text-gray-700">一手房（新建商品房）</h2>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
            <StatCard title="成交套数"
              value={`${formatNum(nh.units)} 套`}
              sub="今日累计"
              curr={nh.units}
              prev={prev?.new_house.units}
              accent="emerald" />
            <StatCard title="成交面积"
              value={formatArea(nh.area)}
              sub="今日累计"
              curr={nh.area}
              prev={prev?.new_house.area}
              accent="emerald" />
            <StatCard title="套均面积"
              value={nh.avg_area ? `${nh.avg_area} ㎡` : '—'}
              sub="成交面积 ÷ 套数"
              curr={nh.avg_area}
              prev={prev?.new_house.avg_area}
              accent="rose" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <TrendChart
              data={chartData}
              title="一手房每日成交套数"
              area
              series={[{
                key: 'nh_units',
                label: '成交套数',
                color: '#10b981',
                getValue: r => r.new_house.units,
              }]}
            />
            <TrendChart
              data={chartData}
              title="一手房套均面积走势（㎡）"
              series={[{
                key: 'nh_avg',
                label: '套均面积',
                color: '#f43f5e',
                getValue: r => r.new_house.avg_area,
              }]}
            />
          </div>
        </section>

        {/* ── 数据表格 ── */}
        <section>
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-700">历史数据明细</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 text-gray-500 text-xs">
                    <th className="px-4 py-3 text-left font-medium">日期</th>
                    <th className="px-4 py-3 text-right font-medium">二手房套数</th>
                    <th className="px-4 py-3 text-right font-medium">二手房面积</th>
                    <th className="px-4 py-3 text-right font-medium">二手房套均</th>
                    <th className="px-4 py-3 text-right font-medium">挂牌套数</th>
                    <th className="px-4 py-3 text-right font-medium">一手房套数</th>
                    <th className="px-4 py-3 text-right font-medium">一手房面积</th>
                    <th className="px-4 py-3 text-right font-medium">一手房套均</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {[...chartData].reverse().map((r, i) => (
                    <tr key={r.date} className={i === 0 ? 'bg-blue-50/50' : 'hover:bg-gray-50'}>
                      <td className="px-4 py-3 font-medium text-gray-900">{r.date}</td>
                      <td className="px-4 py-3 text-right text-gray-700">{formatNum(r.second_hand.units)}</td>
                      <td className="px-4 py-3 text-right text-gray-700">{formatArea(r.second_hand.area)}</td>
                      <td className="px-4 py-3 text-right text-gray-500">
                        {r.second_hand.avg_area ? `${r.second_hand.avg_area}㎡` : '—'}
                      </td>
                      <td className="px-4 py-3 text-right text-amber-600 font-medium">
                        {formatNum(r.listing.total)}
                      </td>
                      <td className="px-4 py-3 text-right text-gray-700">{formatNum(r.new_house.units)}</td>
                      <td className="px-4 py-3 text-right text-gray-700">{formatArea(r.new_house.area)}</td>
                      <td className="px-4 py-3 text-right text-gray-500">
                        {r.new_house.avg_area ? `${r.new_house.avg_area}㎡` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* Footer */}
        <footer className="text-center text-xs text-gray-400 pb-6">
          数据来源：<a href="https://www.fangdi.com.cn" target="_blank" rel="noopener noreferrer"
            className="underline hover:text-gray-600">上海市房地产交易中心（网上房地产）</a>
          &nbsp;·&nbsp;每日自动采集，仅供参考
        </footer>
      </main>
    </div>
  );
}
