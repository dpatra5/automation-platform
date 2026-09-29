interface NavbarProps {
  onToggleMenu: () => void
}

export function Navbar({ onToggleMenu }: NavbarProps) {
  return (
    <header className="navbar">
      <button
        type="button"
        className="hamburger-btn"
        aria-label="Toggle menu"
        onClick={onToggleMenu}
      >
        <span />
        <span />
        <span />
      </button>
      <span className="navbar-title">Automation Platform</span>
    </header>
  )
}
