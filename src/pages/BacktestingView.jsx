import { useState, useEffect } from 'react'
import { Activity, TrendingUp, AlertCircle } from 'lucide-react'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { api } from '../api/client'

export default function BacktestingView() {
  const [backtestResults, setBacktestResults] = useState({})
  const [loading, setLoading] = useState(true)
  const [selectedDate, setSelectedDate] = useState(null)

  useEffect(() => {
    loadBacktestResults()
  }, [])

  const loadBacktestResults = async () => {
    try {
      setLoading(true)
      const response = await api.getBacktestResults({ limit: 10 })
      const results = response.data.backtest_results || {}
      setBacktestResults(results)
      
      // Select most recent date
      const dates = Object.keys(results).sort().reverse()
      if (dates.length > 0) {
        setSelectedDate(dates[0])
      }
    } catch (error) {
      console.error('Error loading backtest results:', error)
    } finally {
      setLoading(false)
    }
  }

  const getSelectedResults = () => {
    if (!selectedDate || !backtestResults[selectedDate]) return []
    return backtestResults[selectedDate]
  }

  const calculateSummary = (results) => {
    if (!results || results.length === 0) return null

    const totalArticles = results.reduce((sum, r) => sum + (r.article_count || 0), 0)
    const avgHitRate = results.reduce((sum, r) => sum + (r.hit_rate || 0), 0) / results.length
    const precisionAtK = results[0]?.precision_at_k || 0

    return {
      totalArticles,
      avgHitRate,
      precisionAtK,
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading backtest results...</div>
      </div>
    )
  }

  const results = getSelectedResults()
  const summary = calculateSummary(results)
  const dates = Object.keys(backtestResults).sort().reverse()

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-500 to-indigo-600 rounded-lg shadow-lg p-6 text-white">
        <div className="flex items-center space-x-3 mb-2">
          <Activity className="h-8 w-8" />
          <h2 className="text-2xl font-bold">Backtesting Results</h2>
        </div>
        <p className="text-purple-50">
          Model performance validation and calibration metrics
        </p>
      </div>

      {/* Date Selector */}
      <div className="bg-white rounded-lg shadow p-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Select Backtest Date
        </label>
        <select
          value={selectedDate || ''}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="w-full md:w-64 px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
        >
          {dates.map((date) => (
            <option key={date} value={date}>
              {new Date(date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
            </option>
          ))}
        </select>
      </div>

      {summary && (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">Total Articles</p>
                  <p className="mt-2 text-3xl font-semibold text-gray-900">
                    {summary.totalArticles}
                  </p>
                </div>
                <div className="p-3 rounded-full bg-blue-50 text-blue-600">
                  <Activity className="h-6 w-6" />
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">Avg Hit Rate</p>
                  <p className="mt-2 text-3xl font-semibold text-gray-900">
                    {(summary.avgHitRate * 100).toFixed(0)}%
                  </p>
                </div>
                <div className="p-3 rounded-full bg-green-50 text-green-600">
                  <TrendingUp className="h-6 w-6" />
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">Precision@K</p>
                  <p className="mt-2 text-3xl font-semibold text-gray-900">
                    {summary.precisionAtK ? (summary.precisionAtK * 100).toFixed(0) + '%' : 'N/A'}
                  </p>
                </div>
                <div className="p-3 rounded-full bg-purple-50 text-purple-600">
                  <AlertCircle className="h-6 w-6" />
                </div>
              </div>
            </div>
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Hit Rate by Score Bucket */}
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                Hit Rate by Score Bucket
              </h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={results}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="score_bucket" />
                  <YAxis />
                  <Tooltip formatter={(value) => `${(value * 100).toFixed(1)}%`} />
                  <Legend />
                  <Bar dataKey="hit_rate" fill="#10b981" name="Hit Rate" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Average Abnormal Return by Bucket */}
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                Avg Abnormal Return by Score Bucket
              </h3>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={results}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="score_bucket" />
                  <YAxis />
                  <Tooltip formatter={(value) => `${value.toFixed(2)}%`} />
                  <Legend />
                  <Line type="monotone" dataKey="avg_abnormal_return_1d" stroke="#8b5cf6" strokeWidth={2} name="Avg Abnormal Return (%)" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Detailed Table */}
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">
                Detailed Metrics by Score Bucket
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Score Bucket
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Article Count
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Avg Abnormal Return
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Hit Rate
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Precision@K
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {results.map((result) => (
                    <tr key={result.score_bucket} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {result.score_bucket}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                        {result.article_count}
                      </td>
                      <td className={`px-6 py-4 whitespace-nowrap text-sm text-right font-medium ${
                        (result.avg_abnormal_return_1d || 0) >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {result.avg_abnormal_return_1d !== null ? (
                          <>
                            {result.avg_abnormal_return_1d >= 0 ? '+' : ''}
                            {result.avg_abnormal_return_1d.toFixed(2)}%
                          </>
                        ) : 'N/A'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                        {result.hit_rate !== null ? `${(result.hit_rate * 100).toFixed(1)}%` : 'N/A'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                        {result.precision_at_k !== null ? `${(result.precision_at_k * 100).toFixed(1)}%` : 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
