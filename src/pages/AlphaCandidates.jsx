import { useState, useEffect } from 'react'
import { format, subDays } from 'date-fns'
import { Target, TrendingUp, ExternalLink } from 'lucide-react'
import { api } from '../api/client'

export default function AlphaCandidates() {
  const [candidates, setCandidates] = useState([])
  const [loading, setLoading] = useState(true)
  const [targetDate, setTargetDate] = useState(format(subDays(new Date(), 30), 'yyyy-MM-dd'))

  useEffect(() => {
    loadCandidates()
  }, [])

  const loadCandidates = async () => {
    try {
      setLoading(true)
      const response = await api.getAlphaCandidates({
        date: targetDate,
        min_score: 15,
        min_abnormal_return: 3.0,
        limit: 20,
      })
      setCandidates(response.data.candidates || [])
    } catch (error) {
      console.error('Error loading alpha candidates:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleDateChange = (date) => {
    setTargetDate(date)
  }

  const handleApply = () => {
    loadCandidates()
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-green-500 to-emerald-600 rounded-lg shadow-lg p-6 text-white">
        <div className="flex items-center space-x-3 mb-2">
          <Target className="h-8 w-8" />
          <h2 className="text-2xl font-bold">Alpha Candidates</h2>
        </div>
        <p className="text-green-50">
          High-conviction signals: High score + High abnormal return + Low confounding
        </p>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-end space-x-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Target Date
            </label>
            <input
              type="date"
              value={targetDate}
              onChange={(e) => handleDateChange(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            />
          </div>
          <button
            onClick={handleApply}
            className="px-6 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            Load Candidates
          </button>
        </div>
      </div>

      {/* Candidates List */}
      {loading ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          Loading alpha candidates...
        </div>
      ) : candidates.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <Target className="h-12 w-12 text-gray-400 mx-auto mb-3" />
          <p className="text-gray-500">No alpha candidates found for {format(new Date(targetDate), 'MMM dd, yyyy')}</p>
          <p className="text-sm text-gray-400 mt-2">
            Try selecting a different date or adjusting the criteria
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {candidates.map((candidate, index) => (
            <div
              key={`${candidate.id}-${candidate.ticker}`}
              className="bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow overflow-hidden"
            >
              <div className="p-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center space-x-3">
                    <div className="flex items-center justify-center w-10 h-10 rounded-full bg-green-100 text-green-600 font-bold">
                      #{index + 1}
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="px-3 py-1 text-sm font-bold rounded-full bg-blue-100 text-blue-800">
                          {candidate.ticker}
                        </span>
                        <span className="text-sm text-gray-500">
                          {format(new Date(candidate.published_at), 'MMM dd, HH:mm')}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-green-600">
                      {candidate.abnormal_return_1d >= 0 ? '+' : ''}
                      {candidate.abnormal_return_1d.toFixed(2)}%
                    </div>
                    <div className="text-xs text-gray-500">Abnormal Return</div>
                  </div>
                </div>

                <h3 className="text-lg font-semibold text-gray-900 mb-3">
                  {candidate.title}
                </h3>

                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">Score</div>
                    <div className="text-lg font-semibold text-gray-900">
                      {candidate.score.toFixed(1)}
                    </div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">Confidence</div>
                    <div className="text-lg font-semibold text-gray-900">
                      {(candidate.confidence * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">Volume Ratio</div>
                    <div className="text-lg font-semibold text-gray-900">
                      {candidate.volume_ratio ? `${candidate.volume_ratio.toFixed(1)}×` : 'N/A'}
                    </div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">Gap</div>
                    <div className={`text-lg font-semibold ${
                      Math.abs(candidate.gap || 0) > 3 ? 'text-purple-600' : 'text-gray-900'
                    }`}>
                      {candidate.gap ? `${candidate.gap >= 0 ? '+' : ''}${candidate.gap.toFixed(2)}%` : 'N/A'}
                    </div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">Confounders</div>
                    <div className="text-lg font-semibold text-gray-900">
                      {candidate.confounders || 0}
                    </div>
                  </div>
                </div>

                {candidate.link && (
                  <a
                    href={candidate.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center space-x-2 text-primary-600 hover:text-primary-800 text-sm font-medium"
                  >
                    <ExternalLink className="h-4 w-4" />
                    <span>Read Full Article</span>
                  </a>
                )}
              </div>

              {/* Quality Indicators */}
              <div className="bg-gray-50 px-6 py-3 border-t border-gray-200">
                <div className="flex items-center space-x-4 text-sm">
                  {candidate.score > 20 && (
                    <span className="flex items-center text-green-600">
                      <TrendingUp className="h-4 w-4 mr-1" />
                      High Score
                    </span>
                  )}
                  {candidate.volume_ratio && candidate.volume_ratio > 2 && (
                    <span className="flex items-center text-blue-600">
                      <TrendingUp className="h-4 w-4 mr-1" />
                      Volume Spike
                    </span>
                  )}
                  {candidate.confidence > 0.8 && (
                    <span className="flex items-center text-purple-600">
                      <Target className="h-4 w-4 mr-1" />
                      High Confidence
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
