function formatTime(time) {
  // 後端回傳台灣當地時間，例如 2026-10-16T19:00
  return time.replace('T', ' ')
}

export default function WeatherCard({ data, onRefresh }) {
  const { city, current, meta } = data
  const details = [
    ['體感溫度', `${current.apparent_temperature} °C`],
    ['濕度', `${current.humidity} %`],
    ['降雨量', `${current.precipitation} mm`],
    ['風速', `${current.wind_speed} km/h`],
    ['天氣代碼', `${current.weather_code}（${current.description}）`],
  ]

  return (
    <article className="card" aria-labelledby="weather-city">
      <header className="card__header">
        <div>
          <h2 id="weather-city" className="card__city">
            {city.name}
          </h2>
          <p className="card__sub">
            {city.name_en} · {formatTime(current.time)}
          </p>
        </div>
        <button type="button" className="button" onClick={onRefresh}>
          重新查詢
        </button>
      </header>

      <p className="card__temp">
        <span className="card__temp-value">{current.temperature}</span>
        <span className="card__temp-unit">°C</span>
        <span className="card__desc">{current.description}</span>
      </p>

      <dl className="card__details">
        {details.map(([label, value]) => (
          <div key={label} className="card__detail">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      {meta.stale && (
        <p className="card__notice" role="note">
          氣象資料來源暫時無法連線，這是較早取得的資料，可能不是最新狀況。
        </p>
      )}
      <p className="card__source">
        資料來源：Open-Meteo（{meta.source === 'cache' ? '快取' : '即時'}）
      </p>
    </article>
  )
}
