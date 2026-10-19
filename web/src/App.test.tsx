// Smoke test for the web skeleton (T0.1): proves React, Vitest and Testing Library are wired up.
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import App from './App.tsx'

test('renders the LinkGuard title', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: 'LinkGuard' })).toBeDefined()
})
