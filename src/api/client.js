import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const api = {
  getArticles: (params) => apiClient.get('/articles', { params }),
  getAlphaCandidates: (params) => apiClient.get('/alpha-candidates', { params }),
  getBacktestResults: (params) => apiClient.get('/backtest-results', { params }),
  getProcessingStatus: () => apiClient.get('/processing-status'),
  getScoreDistribution: (params) => apiClient.get('/score-distribution', { params }),
  getTickerPerformance: (params) => apiClient.get('/ticker-performance', { params }),
}

export default apiClient
