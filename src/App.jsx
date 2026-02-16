import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { BarChart3, TrendingUp, Target, Activity, Settings } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import ArticlesView from './pages/ArticlesView'
import AlphaCandidates from './pages/AlphaCandidates'
import BacktestingView from './pages/BacktestingView'
import ProcessingStatus from './pages/ProcessingStatus'

function App() {
  const location = useLocation()

  const navigation = [
    { name: 'Dashboard', path: '/', icon: BarChart3 },
    { name: 'Articles', path: '/articles', icon: TrendingUp },
    { name: 'Alpha Candidates', path: '/alpha-candidates', icon: Target },
    { name: 'Backtesting', path: '/backtesting', icon: Activity },
    { name: 'Processing', path: '/processing', icon: Settings },
  ]

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <div className="flex items-center space-x-3">
              <BarChart3 className="h-8 w-8 text-primary-600" />
              <h1 className="text-2xl font-bold text-gray-900">
                Stock Impact Analysis
              </h1>
            </div>
            <div className="text-sm text-gray-500">
              Multi-Horizon Event Study Dashboard
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8">
            {navigation.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`
                    flex items-center space-x-2 px-3 py-4 border-b-2 text-sm font-medium transition-colors
                    ${isActive
                      ? 'border-primary-600 text-primary-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }
                  `}
                >
                  <Icon className="h-4 w-4" />
                  <span>{item.name}</span>
                </Link>
              )
            })}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/articles" element={<ArticlesView />} />
          <Route path="/alpha-candidates" element={<AlphaCandidates />} />
          <Route path="/backtesting" element={<BacktestingView />} />
          <Route path="/processing" element={<ProcessingStatus />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
