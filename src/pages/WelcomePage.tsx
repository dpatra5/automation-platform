import { MENU_ITEMS, type MenuKey } from '../types'

interface WelcomePageProps {
  onSelect: (key: MenuKey) => void
}

export function WelcomePage({ onSelect }: WelcomePageProps) {
  return (
    <div className="page">
      <div className="welcome-hero">
        <h1>Welcome to Automation Platform</h1>
        <p className="page-description">
          Open the menu in the upper-left corner and choose a workflow to get started.
        </p>
      </div>
      <div className="result-grid">
        {MENU_ITEMS.map((item) => (
          <button
            type="button"
            className="result-card welcome-card"
            key={item.key}
            onClick={() => onSelect(item.key)}
          >
            <div className="welcome-card-icon">{item.icon}</div>
            <h3>{item.label}</h3>
            <p>{item.description}</p>
          </button>
        ))}
      </div>
    </div>
  )
}
