import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'
import { SettingsModal } from '@/components/SettingsModal'
import { ApiSettingsProvider } from '@/hooks/useApiSettings'

beforeEach(() => {
  window.localStorage.clear()
})

// Provider wrapper required after useApiSettings was converted to a Context
// consumer — bare render() would now throw "must be used within Provider".
function renderWithProvider(ui: React.ReactElement) {
  return render(<ApiSettingsProvider>{ui}</ApiSettingsProvider>)
}

describe('SettingsModal', () => {
  it('renders four inputs and a save button when open', () => {
    renderWithProvider(<SettingsModal open={true} onOpenChange={() => {}} />)
    expect(screen.getByLabelText(/Base URL/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/API Key/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Profile ID/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Tenant ID/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Save/i })).toBeInTheDocument()
  })

  it('saves to localStorage on Save and closes modal', () => {
    let openState = true
    const onOpenChange = (next: boolean) => {
      openState = next
    }
    renderWithProvider(<SettingsModal open={openState} onOpenChange={onOpenChange} />)

    fireEvent.change(screen.getByLabelText(/API Key/i), { target: { value: 'aitkey_xyz' } })
    fireEvent.change(screen.getByLabelText(/Profile ID/i), {
      target: { value: 'profile-aaaaaaaa-bbbb' },
    })
    fireEvent.change(screen.getByLabelText(/Tenant ID/i), {
      target: { value: 'tenant-cccccccc-dddd' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Save/i }))

    const stored = JSON.parse(window.localStorage.getItem('aitegrity_api_settings')!)
    expect(stored.apiKey).toBe('aitkey_xyz')
    expect(stored.profileId).toBe('profile-aaaaaaaa-bbbb')
    expect(openState).toBe(false)
  })
})
