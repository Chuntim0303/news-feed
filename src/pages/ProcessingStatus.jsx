import { useState, useEffect } from 'react'
import { Settings, CheckCircle, XCircle, Clock, AlertTriangle } from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts'
import { api } from '../api/client'

const STATUS_COLORS = {
  complete: '#10b981',
  partial: '#f59e0b',
  failed: '#ef4444',
  not_started: '#6b7280',
}

export default function ProcessingStatus() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadStatus()
    const interval = setInterval(loadStatus, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [])

  const loadStatus = async () => {
    try {
      setLoading(true)
      const response = await api.getProcessingStatus()
      setStatus(response.data)
    } catch (error) {
      console.error('Error loading processing status:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading && !status) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading processing status...</div>
      </div>
    )
  }

  const statusCounts = status?.status_counts || []
  const failures = status?.recent_failures || []

  const chartData = statusCounts.map(s => ({
    name: s.processing_status,
    value: s.count,
    color: STATUS_COLORS[s.processing_status] || '#6b7280'
  }))

  const totalProcessed = statusCounts.reduce((sum, s) => sum + s.count, 0)
  const completeCount = statusCounts.find(s => s.processing_status === 'complete')?.count || 0
  const successRate = totalProcessed > 0 ? (completeCount / totalProcessed) * 100 : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-gray-700 to-gray-900 rounded-lg shadow-lg p-6 text-white">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Settings className="h-8 w-8" />
            <div>
              <h2 className="text-2xl font-bold">Processing Status</h2>
              <p className="text-gray-300 text-sm mt-1">
                Event study processing pipeline health (Last 7 days)
              </p>
            </div>
          </div>
          <button
            onClick={loadStatus}
            className="px-4 py-2 bg-white text-gray-900 rounded-md hover:bg-gray-100 text-sm font-medium"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Total Processed</p>
              <p className="mt-2 text-3xl font-semibold text-gray-900">
                {totalProcessed}
              </p>
            </div>
            <div className="p-3 rounded-full bg-blue-50 text-blue-600">
              <Settings className="h-6 w-6" />
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Complete</p>
              <p className="mt-2 text-3xl font-semibold text-green-600">
                {completeCount}
              </p>
            </div>
            <div className="p-3 rounded-full bg-green-50 text-green-600">
              <CheckCircle className="h-6 w-6" />
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Success Rate</p>
              <p className="mt-2 text-3xl font-semibold text-gray-900">
                {successRate.toFixed(0)}%
              </p>
            </div>
            <div className={`p-3 rounded-full ${
              successRate >= 95 ? 'bg-green-50 text-green-600' : 'bg-yellow-50 text-yellow-600'
            }`}>
              {successRate >= 95 ? <CheckCircle className="h-6 w-6" /> : <AlertTriangle className="h-6 w-6" />}
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Failed (3+ retries)</p>
              <p className="mt-2 text-3xl font-semibold text-red-600">
                {failures.length}
              </p>
            </div>
            <div className="p-3 rounded-full bg-red-50 text-red-600">
              <XCircle className="h-6 w-6" />
            </div>
          </div>
        </div>
      </div>

      {/* Status Distribution Chart */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Processing Status Distribution
        </h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                outerRadius={100}
                fill="#8884d8"
                dataKey="value"
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>

          <div className="space-y-3">
            {statusCounts.map((status) => {
              const Icon = status.processing_status === 'complete' ? CheckCircle :
                          status.processing_status === 'failed' ? XCircle :
                          status.processing_status === 'partial' ? Clock : AlertTriangle
              
              return (
                <div key={status.processing_status} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <div className="flex items-center space-x-3">
                    <Icon className="h-5 w-5" style={{ color: STATUS_COLORS[status.processing_status] }} />
                    <span className="font-medium text-gray-900 capitalize">
                      {status.processing_status.replace('_', ' ')}
                    </span>
                  </div>
                  <span className="text-lg font-semibold text-gray-900">
                    {status.count}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Recent Failures */}
      {failures.length > 0 && (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 bg-red-50">
            <div className="flex items-center space-x-2">
              <XCircle className="h-5 w-5 text-red-600" />
              <h3 className="text-lg font-semibold text-red-900">
                Recent Failures (3+ Retries)
              </h3>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Article / Title
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Ticker
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Failure Reason
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Retry Count
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Last Attempt
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {failures.map((failure) => (
                  <tr key={`${failure.article_id}-${failure.ticker}`} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <div className="text-sm font-medium text-gray-900">
                        Article #{failure.article_id}
                      </div>
                      <div className="text-sm text-gray-500 max-w-md truncate">
                        {failure.title}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">
                        {failure.ticker}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-sm text-red-600">
                        {failure.failure_reason || 'Unknown error'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {failure.retry_count}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(failure.last_processed_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
