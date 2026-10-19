import { useState } from 'react'
import { MAX_CITY_LENGTH } from '../api/weatherApi.js'

export default function SearchForm({ cities, onSearch, disabled }) {
  const [value, setValue] = useState('')
  const [hint, setHint] = useState('')

  function handleSubmit(event) {
    event.preventDefault()
    const city = value.trim()
    if (!city) {
      setHint('請輸入城市名稱，或從清單選擇')
      return
    }
    setHint('')
    onSearch(city)
  }

  function handlePick(event) {
    if (event.target.value) {
      setValue(event.target.value)
      setHint('')
    }
  }

  return (
    <form className="search" onSubmit={handleSubmit} noValidate>
      <div className="search__row">
        <label className="search__field">
          <span className="search__label">城市名稱</span>
          <input
            type="text"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            maxLength={MAX_CITY_LENGTH}
            placeholder="例如：臺南、Taipei、高雄"
            autoComplete="off"
            enterKeyHint="search"
            aria-invalid={hint ? 'true' : undefined}
            aria-describedby={hint ? 'search-hint' : undefined}
          />
        </label>
        <button type="submit" className="button button--primary" disabled={disabled}>
          {disabled ? '查詢中…' : '查詢'}
        </button>
      </div>

      {cities.length > 0 && (
        <label className="search__field">
          <span className="search__label">或選擇縣市</span>
          <select value="" onChange={handlePick}>
            <option value="">請選擇</option>
            {cities.map((city) => (
              <option key={city.id} value={city.name}>
                {city.name}（{city.name_en}）
              </option>
            ))}
          </select>
        </label>
      )}

      {hint && (
        <p id="search-hint" className="search__hint" role="alert">
          {hint}
        </p>
      )}
    </form>
  )
}
