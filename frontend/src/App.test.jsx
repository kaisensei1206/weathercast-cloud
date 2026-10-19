import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'
import { ApiError, fetchCities, fetchWeather } from './api/weatherApi.js'
import { CITIES, TAINAN } from './test/fixtures.js'

// 元件測試只換掉 API 模組，不碰 fetch，HTTP 細節由 weatherApi.test.js 負責
vi.mock('./api/weatherApi.js', async (importOriginal) => ({
  ...(await importOriginal()),
  fetchCities: vi.fn(),
  fetchWeather: vi.fn(),
}))

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { promise, resolve }
}

async function searchFor(user, city) {
  await user.type(screen.getByLabelText('城市名稱'), city)
  await user.click(screen.getByRole('button', { name: '查詢' }))
}

beforeEach(() => {
  fetchCities.mockResolvedValue(CITIES)
})

describe('App', () => {
  it('shows loading, then the weather card with every field', async () => {
    const user = userEvent.setup()
    const pending = deferred()
    fetchWeather.mockReturnValue(pending.promise)
    render(<App />)

    await searchFor(user, '臺南')
    expect(fetchWeather).toHaveBeenCalledWith('臺南')
    expect(screen.getByRole('status')).toHaveTextContent('查詢中')
    expect(screen.getByRole('button', { name: '查詢中…' })).toBeDisabled()

    pending.resolve(TAINAN)
    const card = await screen.findByRole('article')
    expect(within(card).getByRole('heading', { name: '臺南市' })).toBeInTheDocument()
    for (const text of ['27.1', '29.9 °C', '78 %', '0.2 mm', '9.4 km/h', '61（小雨）']) {
      expect(card).toHaveTextContent(text)
    }
    expect(card).toHaveTextContent('2026-10-16 19:00')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('searches with a preset city chosen from the list', async () => {
    const user = userEvent.setup()
    fetchWeather.mockResolvedValue(TAINAN)
    render(<App />)

    const select = await screen.findByLabelText('或選擇縣市')
    await user.selectOptions(select, '臺南市')
    expect(screen.getByLabelText('城市名稱')).toHaveValue('臺南市')
    await user.click(screen.getByRole('button', { name: '查詢' }))

    expect(fetchWeather).toHaveBeenCalledWith('臺南市')
    expect(await screen.findByRole('article')).toBeInTheDocument()
  })

  it('still allows typing a city when the city list fails to load', async () => {
    const user = userEvent.setup()
    fetchCities.mockRejectedValue(new ApiError('network', 'offline'))
    fetchWeather.mockResolvedValue(TAINAN)
    render(<App />)

    await searchFor(user, 'Tainan')
    expect(await screen.findByRole('article')).toBeInTheDocument()
    expect(screen.queryByLabelText('或選擇縣市')).not.toBeInTheDocument()
  })

  it('asks for a city instead of calling the API when the input is empty', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: '查詢' }))

    expect(screen.getByRole('alert')).toHaveTextContent('請輸入城市名稱')
    expect(fetchWeather).not.toHaveBeenCalled()
  })

  it.each([
    ['not_found', '找不到城市：Tokyo', '找不到這個城市'],
    ['network', '無法連線', '網路連線失敗'],
    ['timeout', '太久沒有回應', '連線逾時'],
    ['server', '氣象資料來源暫時無法使用', '伺服器發生錯誤'],
  ])('shows the %s error state', async (kind, message, title) => {
    const user = userEvent.setup()
    fetchWeather.mockRejectedValue(new ApiError(kind, message))
    render(<App />)

    await searchFor(user, 'Tokyo')

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByRole('heading', { name: title })).toBeInTheDocument()
  })

  it('treats an unexpected error as a server error', async () => {
    const user = userEvent.setup()
    fetchWeather.mockRejectedValue(new Error('boom'))
    render(<App />)

    await searchFor(user, 'Tainan')

    expect(await screen.findByRole('heading', { name: '伺服器發生錯誤' })).toBeInTheDocument()
  })

  it('retries the same city after an error', async () => {
    const user = userEvent.setup()
    fetchWeather.mockRejectedValueOnce(new ApiError('network', 'offline')).mockResolvedValueOnce(TAINAN)
    render(<App />)

    await searchFor(user, 'Tainan')
    await user.click(await screen.findByRole('button', { name: '重新查詢' }))

    expect(await screen.findByRole('article')).toBeInTheDocument()
    expect(fetchWeather).toHaveBeenNthCalledWith(2, 'Tainan')
  })

  it('refreshes the card with the same city', async () => {
    const user = userEvent.setup()
    fetchWeather.mockResolvedValue(TAINAN)
    render(<App />)

    await searchFor(user, 'Tainan')
    await user.click(await screen.findByRole('button', { name: '重新查詢' }))

    expect(fetchWeather).toHaveBeenCalledTimes(2)
    expect(fetchWeather).toHaveBeenLastCalledWith('Tainan')
  })
})
