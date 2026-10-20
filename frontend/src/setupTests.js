import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => cleanup())

// jsdom 沒有實作 Canvas；直接回傳 null（和不支援 Canvas 的瀏覽器一樣），避免每個測試都印出警告
HTMLCanvasElement.prototype.getContext = () => null
