import { Suspense, lazy } from 'react'
import SearchForm from './components/SearchForm.jsx'
import { ErrorMessage, Loading } from './components/StatusMessage.jsx'
import WeatherBackdrop from './components/WeatherBackdrop.jsx'
import WeatherCard from './components/WeatherCard.jsx'
import { useCities } from './hooks/useCities.js'
import { useWeather } from './hooks/useWeather.js'
import { useWeatherScene } from './hooks/useWeatherScene.js'
import { skyTone } from './weather/effects.js'

// 地圖套件（Leaflet）比較大，分成另一個檔案，等畫面出來後才下載，不拖慢首頁
const SatelliteMap = lazy(() => import('./components/SatelliteMap.jsx'))

export default function App() {
  const cities = useCities()
  const { status, data, error, search, retry } = useWeather()
  const scene = useWeatherScene(status, data)

  return (
    <>
      <WeatherBackdrop scene={scene} />
      <div className="app" data-sky-tone={skyTone(scene) ?? 'theme'}>
        <header className="app__header">
          <h1>WeatherCast</h1>
          <p>查詢臺灣 22 縣市的目前天氣</p>
        </header>

        <main>
          <SearchForm cities={cities} onSearch={search} disabled={status === 'loading'} />

          <section className="result" aria-live="polite">
            {status === 'loading' && <Loading />}
            {status === 'error' && <ErrorMessage error={error} onRetry={retry} />}
            {status === 'success' && <WeatherCard data={data} onRefresh={retry} />}
          </section>

          <Suspense fallback={null}>
            <SatelliteMap />
          </Suspense>
        </main>

        <footer className="app__footer">
          <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
            Weather data by Open-Meteo
          </a>
        </footer>
      </div>
    </>
  )
}
