import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

// NOTE: StrictMode intentionally disabled. Its dev-only double-mount
// (mount → unmount → remount) breaks the react-three-fiber canvas + the
// async VRM loader, leaving the 3D avatar invisible on a full page load.
ReactDOM.createRoot(document.getElementById('root')).render(
  <App />,
)
