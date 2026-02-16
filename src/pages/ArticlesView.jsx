import { useState, useEffect } from 'react'
import { format, subDays } from 'date-fns'
import { ExternalLink, TrendingUp, TrendingDown } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { api } from '../api/client'

export default function ArticlesView() {
  const [articles, setArticles] = useState([])
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({
    start_date: format(subDays(new Date(), 7), 'yyyy-MM-dd'),
    end_date: format(new Date(), 'yyyy-MM-dd'),
    min_score: 10,
    ticker: '',
  })
  const [selectedArticle, setSelectedArticle] = useState(null)

  useEffect(() => {
    loadArticles()
  }, [])

  const loadArticles = async () => {
    try {
      setLoading(true)
      const response = await api.getArticles({
        ...filters,
        limit: 100,
      })
      setArticles(response.data.articles || [])
    } catch (error) {
      console.error('Error loading articles:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }))
  }

  const handleApplyFilters = () => {
    loadArticles()
  }

  const getReturnChartData = (article) => {
    if (!article) return []
    return [
      { horizon: '-5D', return: article.return_pre_5d || 0, abnormal: null },
      { horizon: '-3D', return: article.return_pre_3d || 0, abnormal: null },
      { horizon: '-1D', return: article.return_pre_1d || 0, abnormal: null },
      { horizon: '0D', return: 0, abnormal: 0 },
      { horizon: '+1D', return: article.return_1d || 0, abnormal: article.abnormal_return_1d || 0 },
      { horizon: '+3D', return: article.return_3d || 0, abnormal: article.abnormal_return_3d || 0 },
      { horizon: '+5D', return: article.return_5d || 0, abnormal: article.abnormal_return_5d || 0 },
      { horizon: '+10D', return: article.return_10d || 0, abnormal: article.abnormal_return_10d || 0 },
    ]
  }

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Filters</h3>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Start Date
            </label>
            <input
              type="date"
              value={filters.start_date}
              onChange={(e) => handleFilterChange('start_date', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              End Date
            </label>
            <input
              type="date"
              value={filters.end_date}
              onChange={(e) => handleFilterChange('end_date', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Min Score
            </label>
            <input
              type="number"
              value={filters.min_score}
              onChange={(e) => handleFilterChange('min_score', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Ticker (optional)
            </label>
            <input
              type="text"
              value={filters.ticker}
              onChange={(e) => handleFilterChange('ticker', e.target.value.toUpperCase())}
              placeholder="e.g., MRNA"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={handleApplyFilters}
              className="w-full px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              Apply Filters
            </button>
          </div>
        </div>
      </div>

      {/* Articles Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">
            Articles with Multi-Horizon Returns ({articles.length})
          </h3>
        </div>
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading articles...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Date / Title
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Ticker
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Score
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Abnormal 1D
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Abnormal 3D
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Volume Ratio
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Gap
                  </th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {articles.map((article) => (
                  <tr key={`${article.id}-${article.ticker}`} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <div className="text-sm font-medium text-gray-900">
                        {format(new Date(article.published_at), 'MMM dd, yyyy HH:mm')}
                      </div>
                      <div className="text-sm text-gray-500 max-w-md truncate">
                        {article.title}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">
                        {article.ticker}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {article.score_total?.toFixed(1)}
                    </td>
                    <td className={`px-6 py-4 whitespace-nowrap text-sm text-right font-medium ${
                      (article.abnormal_return_1d || 0) >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {article.abnormal_return_1d !== null ? (
                        <>
                          {article.abnormal_return_1d >= 0 ? <TrendingUp className="inline h-4 w-4 mr-1" /> : <TrendingDown className="inline h-4 w-4 mr-1" />}
                          {article.abnormal_return_1d >= 0 ? '+' : ''}
                          {article.abnormal_return_1d.toFixed(2)}%
                        </>
                      ) : 'N/A'}
                    </td>
                    <td className={`px-6 py-4 whitespace-nowrap text-sm text-right font-medium ${
                      (article.abnormal_return_3d || 0) >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {article.abnormal_return_3d !== null ? (
                        <>
                          {article.abnormal_return_3d >= 0 ? '+' : ''}
                          {article.abnormal_return_3d.toFixed(2)}%
                        </>
                      ) : 'N/A'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {article.volume_ratio_1d ? `${article.volume_ratio_1d.toFixed(1)}×` : 'N/A'}
                    </td>
                    <td className={`px-6 py-4 whitespace-nowrap text-sm text-right ${
                      Math.abs(article.gap_magnitude || 0) > 3 ? 'font-medium text-purple-600' : 'text-gray-900'
                    }`}>
                      {article.gap_magnitude !== null ? `${article.gap_magnitude >= 0 ? '+' : ''}${article.gap_magnitude.toFixed(2)}%` : 'N/A'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-center">
                      <button
                        onClick={() => setSelectedArticle(article)}
                        className="text-primary-600 hover:text-primary-900 text-sm font-medium"
                      >
                        View Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Article Detail Modal */}
      {selectedArticle && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-start">
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900">
                  {selectedArticle.title}
                </h3>
                <div className="mt-2 flex items-center space-x-4 text-sm text-gray-500">
                  <span>{format(new Date(selectedArticle.published_at), 'MMM dd, yyyy HH:mm')}</span>
                  <span className="px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">
                    {selectedArticle.ticker}
                  </span>
                  <span>Score: {selectedArticle.score_total?.toFixed(1)}</span>
                </div>
              </div>
              <button
                onClick={() => setSelectedArticle(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <span className="text-2xl">&times;</span>
              </button>
            </div>

            <div className="p-6 space-y-6">
              {/* Multi-Horizon Returns Chart */}
              <div>
                <h4 className="text-md font-semibold text-gray-900 mb-4">
                  Multi-Horizon Returns
                </h4>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={getReturnChartData(selectedArticle)}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="horizon" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="return" stroke="#3b82f6" name="Stock Return (%)" strokeWidth={2} />
                    <Line type="monotone" dataKey="abnormal" stroke="#10b981" name="Abnormal Return (%)" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <MetricCard label="Score Total" value={selectedArticle.score_total?.toFixed(1)} />
                <MetricCard label="Keyword Score" value={selectedArticle.score_keyword} />
                <MetricCard label="Surprise Score" value={selectedArticle.score_surprise} />
                <MetricCard label="Reaction Score" value={selectedArticle.score_market_reaction?.toFixed(1) || '0.0'} />
                <MetricCard label="Volume Ratio" value={selectedArticle.volume_ratio_1d ? `${selectedArticle.volume_ratio_1d.toFixed(1)}×` : 'N/A'} />
                <MetricCard label="Volume Z-Score" value={selectedArticle.volume_zscore_1d?.toFixed(2) || 'N/A'} />
                <MetricCard label="Gap Magnitude" value={selectedArticle.gap_magnitude ? `${selectedArticle.gap_magnitude.toFixed(2)}%` : 'N/A'} />
                <MetricCard label="Relevance" value={selectedArticle.ticker_relevance_score?.toFixed(2) || '1.00'} />
              </div>

              {/* Link */}
              {selectedArticle.link && (
                <div>
                  <a
                    href={selectedArticle.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center space-x-2 text-primary-600 hover:text-primary-800"
                  >
                    <ExternalLink className="h-4 w-4" />
                    <span>Read Full Article</span>
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function MetricCard({ label, value }) {
  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="mt-1 text-lg font-semibold text-gray-900">{value}</div>
    </div>
  )
}
