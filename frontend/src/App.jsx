import SearchForm from './components/SearchForm.jsx'
import { ErrorMessage, Loading } from './components/StatusMessage.jsx'
import WeatherCard from './components/WeatherCard.jsx'
import { useCities } from './hooks/useCities.js'
import { useWeather } from './hooks/useWeather.js'

export default function App() {
  const cities = useCities()
  const { status, data, error, search, retry } = useWeather()

  return (
    <div className="app">
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
      </main>

      <footer className="app__footer">
        <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
          Weather data by Open-Meteo
        </a>
      </footer>
    </div>
  )
}
