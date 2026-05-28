import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import { ApiSettingsProvider } from '@/hooks/useApiSettings'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ApiSettingsProvider>
      <App />
    </ApiSettingsProvider>
  </React.StrictMode>,
)
