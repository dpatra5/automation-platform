import { useState } from 'react'
import { Navbar } from './components/Navbar'
import { Sidebar } from './components/Sidebar'
import { ProjectPlanPage } from './pages/ProjectPlanPage'
import { ApiTestingPage } from './pages/ApiTestingPage'
import { LoadTestingPage } from './pages/LoadTestingPage'
import { RewindAutomationToolPage } from './pages/RewindAutomationToolPage'
import { WelcomePage } from './pages/WelcomePage'
import type { MenuKey } from './types'
import './App.css'

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [activeKey, setActiveKey] = useState<MenuKey | null>(null)

  const handleSelect = (key: MenuKey) => {
    setActiveKey(key)
    setSidebarOpen(false)
  }

  const renderPage = () => {
    switch (activeKey) {
      case 'project-plan':
        return <ProjectPlanPage />
      case 'api-testing':
        return <ApiTestingPage />
      case 'load-testing':
        return <LoadTestingPage />
      case 'ui-automation':
        return <RewindAutomationToolPage />
      default:
        return <WelcomePage onSelect={handleSelect} />
    }
  }

  return (
    <div className="app">
      <Navbar onToggleMenu={() => setSidebarOpen((open) => !open)} />
      <Sidebar
        isOpen={sidebarOpen}
        activeKey={activeKey}
        onSelect={handleSelect}
        onClose={() => setSidebarOpen(false)}
      />
      <main className="content">{renderPage()}</main>
    </div>
  )
}

export default App
