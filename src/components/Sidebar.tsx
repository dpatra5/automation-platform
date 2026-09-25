import { MENU_ITEMS, type MenuKey } from '../types'

interface SidebarProps {
  isOpen: boolean
  activeKey: MenuKey | null
  onSelect: (key: MenuKey) => void
  onClose: () => void
}

export function Sidebar({ isOpen, activeKey, onSelect, onClose }: SidebarProps) {
  return (
    <>
      {isOpen && <div className="sidebar-overlay" onClick={onClose} />}
      <nav className={`sidebar ${isOpen ? 'sidebar-open' : ''}`}>
        <ul>
          {MENU_ITEMS.map((item) => (
            <li key={item.key}>
              <button
                type="button"
                className={`sidebar-item ${activeKey === item.key ? 'sidebar-item-active' : ''}`}
                onClick={() => onSelect(item.key)}
              >
                <span className="sidebar-icon">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </>
  )
}
