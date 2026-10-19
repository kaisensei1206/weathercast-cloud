import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import WeatherCard from './WeatherCard.jsx'
import { TAINAN } from '../test/fixtures.js'

describe('WeatherCard', () => {
  it('shows live data without a stale notice', () => {
    render(<WeatherCard data={TAINAN} onRefresh={vi.fn()} />)

    expect(screen.queryByRole('note')).not.toBeInTheDocument()
    expect(screen.getByText(/Open-Meteo（即時）/)).toBeInTheDocument()
  })

  it('warns when the backend returns stale cached data', () => {
    const stale = { ...TAINAN, meta: { ...TAINAN.meta, source: 'cache', stale: true } }
    render(<WeatherCard data={stale} onRefresh={vi.fn()} />)

    expect(screen.getByRole('note')).toHaveTextContent('可能不是最新')
    expect(screen.getByText(/Open-Meteo（快取）/)).toBeInTheDocument()
  })
})
