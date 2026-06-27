import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import Login from './pages/Login.jsx'

/**
 * Root app shell. Routing only - no business logic here.
 * YOUR WORK: build out Dashboard.jsx (today's plan + chat) and
 * Login.jsx (Google sign-in button hitting backend /auth/login).
 */
function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/login" element={<Login />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
