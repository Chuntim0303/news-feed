import { useState, useEffect } from 'react'
import { format, subDays } from 'date-fns'
import { TrendingUp, TrendingDown, Activity, Target } from 'lucide-react'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { api } from '../api/client'

export default function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [scoreDistribution, setScoreDistribution] = useState([])
  const [tickerPerformance, setTickerPerformance] = useState([])
  const [stats, setStats] = useState({
    totalArticles: 0,
    avgAbnormalReturn: 0,
    topMovers: 0,
    alphaCandidates: 0,
  })

  useEffect(() => {
    loadDashboardData()
  }, [])

  const loadDashboardData = async () => {
    try {
      setLoading(true)
      const endDate = format(new Date(), 'yyyy-MM-dd')
      const startDate = format(subDays(new Date(), 30), 'yyyy-MM-dd')

      const [distResponse, tickerResponse, articlesResponse] = await Promise.all([
        api.getScoreDistribution({ start_date: startDate, end_date: endDate }),
        api.getTickerPerformance({ start_date: startDate, end_date: endDate, limit: 10 }),
        api.getArticles({ start_date: startDate, end_date: endDate, min_score: 5, limit: 1000 }),
      ])

      setScoreDistribution(distResponse.data.distribution || [])
      setTickerPerformance(tickerResponse.data.tickers || [])

      const articles = articlesResponse.data.articles || []
      const abnormalReturns = articles
        .filter(a => a.abnormal_return_1d !== null)
        .map(a => a.abnormal_return_1d)
      
      setStats({
        totalArticles: articles.length,
        avgAbnormalReturn: abnormalReturns.length > 0
          ? abnormalReturns.reduce((a, b) => a + b, 0) / abnormalReturns.length
          : 0,
        topMovers: articles.filter(a => Math.abs(a.abnormal_return_1d || 0) > 3).length,
        alphaCandidates: articles.filter(a => 
          (a.score_total || 0) > 15 && Math.abs(a.abnormal_return_1d || 0) > 3
        ).length,
      })

    } catch (error) {
      console.error('Error loading dashboard data:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading dashboard...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <StatCard
          title="Total Articles"
          value={stats.totalArticles}
          icon={Activity}
          color="blue"
        />
        <StatCard
          title="Avg Abnormal Return"
          value={`${stats.avgAbnormalReturn >= 0 ? '+' : ''}${stats.avgAbnormalReturn.toFixed(2)}%`}
          icon={stats.avgAbnormalReturn >= 0 ? TrendingUp : TrendingDown}
          color={stats.avgAbnormalReturn >= 0 ? 'green' : 'red'}
        />
        <StatCard
          title="Top Movers (>3%)"
          value={stats.topMovers}
          icon={TrendingUp}
          color="purple"
        />
        <StatCard
          title="Alpha Candidates"
          value={stats.alphaCandidates}
          icon={Target}
          color="orange"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Score Distribution */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Score Distribution & Hit Rates
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={scoreDistribution}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="score_bucket" />
              <YAxis yAxisId="left" />
              <YAxis yAxisId="right" orientation="right" />
              <Tooltip />
              <Legend />
              <Bar yAxisId="left" dataKey="count" fill="#3b82f6" name="Article Count" />
              <Bar yAxisId="right" dataKey="hit_rate" fill="#10b981" name="Hit Rate" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Ticker Performance */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Top Tickers by Abnormal Return
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={tickerPerformance.slice(0, 10)} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis dataKey="ticker" type="category" width={60} />
              <Tooltip />
              <Legend />
              <Bar dataKey="avg_abnormal_return_1d" fill="#8b5cf6" name="Avg Abnormal Return 1D (%)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Ticker Performance Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">
            Ticker Performance Summary (Last 30 Days)
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Ticker
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Sector
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Articles
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Avg Score
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Abnormal 1D
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Abnormal 3D
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Avg Volume Ratio
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {tickerPerformance.map((ticker) => (
                <tr key={ticker.ticker} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {ticker.ticker}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {ticker.sector || 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                    {ticker.article_count}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                    {ticker.avg_score?.toFixed(1)}
                  </td>
                  <td className={`px-6 py-4 whitespace-nowrap text-sm text-right font-medium ${
                    ticker.avg_abnormal_return_1d >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {ticker.avg_abnormal_return_1d >= 0 ? '+' : ''}
                    {ticker.avg_abnormal_return_1d?.toFixed(2)}%
                  </td>
                  <td className={`px-6 py-4 whitespace-nowrap text-sm text-right font-medium ${
                    ticker.avg_abnormal_return_3d >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {ticker.avg_abnormal_return_3d >= 0 ? '+' : ''}
                    {ticker.avg_abnormal_return_3d?.toFixed(2)}%
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                    {ticker.avg_volume_ratio?.toFixed(1)}×
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function StatCard({ title, value, icon: Icon, color }) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    red: 'bg-red-50 text-red-600',
    purple: 'bg-purple-50 text-purple-600',
    orange: 'bg-orange-50 text-orange-600',
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <p className="mt-2 text-3xl font-semibold text-gray-900">{value}</p>
        </div>
        <div className={`p-3 rounded-full ${colorClasses[color]}`}>
          <Icon className="h-6 w-6" />
        </div>
      </div>
    </div>
  )
}
