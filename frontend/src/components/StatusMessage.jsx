const TITLES = {
  invalid_input: '輸入有誤',
  not_found: '找不到這個城市',
  network: '網路連線失敗',
  timeout: '連線逾時',
  server: '伺服器發生錯誤',
}

const HINTS = {
  not_found: '目前支援臺灣 22 縣市，可以輸入中文、英文，或從清單選擇。',
  network: '請確認網路連線，或稍後再試。',
  timeout: '伺服器可能正在啟動，請再試一次。',
  server: '這不是你的問題，請稍後再試。',
}

export function Loading() {
  return (
    <p className="status status--loading" role="status">
      <span className="spinner" aria-hidden="true" />
      查詢中…
    </p>
  )
}

export function ErrorMessage({ error, onRetry }) {
  const kind = TITLES[error?.kind] ? error.kind : 'server'
  const showDetail = error?.message && kind !== 'network' && kind !== 'timeout'
  return (
    <div className={`status status--error status--${kind}`} role="alert">
      <h2 className="status__title">{TITLES[kind]}</h2>
      {showDetail && <p>{error.message}</p>}
      {HINTS[kind] && <p className="status__hint">{HINTS[kind]}</p>}
      <button type="button" className="button" onClick={onRetry}>
        重新查詢
      </button>
    </div>
  )
}
