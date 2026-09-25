import { MENU_ITEMS } from '../types'

export function WelcomePage() {
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
          <div className="result-card welcome-card" key={item.key}>
            <div className="welcome-card-icon">{item.icon}</div>
            <h3>{item.label}</h3>
            <p>{item.description}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
