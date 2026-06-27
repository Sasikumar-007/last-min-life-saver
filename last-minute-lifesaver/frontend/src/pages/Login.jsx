/**
 * Login: Google sign-in. Redirects to backend's /auth/login,
 * which kicks off the OAuth flow (needs Calendar + Gmail scopes).
 */

import { BASE_URL } from '../services/api'

export default function Login() {
  const handleLogin = () => {
    window.location.href = `${BASE_URL}/auth/login`
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-900 via-indigo-950 to-gray-900 relative overflow-hidden">
      {/* Animated background orbs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-indigo-500/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-violet-500/15 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-500/5 rounded-full blur-3xl" />
      </div>

      {/* Login card */}
      <div className="relative z-10 max-w-md w-full mx-4">
        <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-3xl p-10 shadow-2xl text-center">
          {/* Logo / Icon */}
          <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-2xl mb-6 shadow-lg shadow-indigo-500/25 transform hover:scale-105 transition-transform duration-300">
            <svg className="w-10 h-10 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>

          {/* App name */}
          <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">
            Last-Minute
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-violet-400">
              Life Saver
            </span>
          </h1>

          {/* Tagline */}
          <p className="text-gray-400 text-sm mb-8 leading-relaxed max-w-xs mx-auto">
            Your AI-powered schedule agent that extracts tasks, plans your time,
            and proactively adapts when you drift off track.
          </p>

          {/* Feature pills */}
          <div className="flex flex-wrap justify-center gap-2 mb-8">
            {['📋 Smart Extraction', '📅 Auto-Planning', '🔄 Drift Detection'].map((feature) => (
              <span
                key={feature}
                className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-white/5 text-gray-300 border border-white/10"
              >
                {feature}
              </span>
            ))}
          </div>

          {/* Google Sign-In Button */}
          <button
            onClick={handleLogin}
            id="google-sign-in-btn"
            className="w-full group relative inline-flex items-center justify-center gap-3 bg-white hover:bg-gray-50 text-gray-800 px-6 py-4 rounded-2xl font-semibold text-base shadow-lg shadow-black/10 transition-all duration-300 hover:shadow-xl hover:shadow-black/20 hover:-translate-y-0.5 active:translate-y-0"
          >
            {/* Google G icon */}
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Sign in with Google
          </button>

          {/* Permissions note */}
          <p className="text-gray-500 text-xs mt-6 leading-relaxed">
            We'll request access to your Google Calendar and Gmail to
            schedule tasks and draft emails on your behalf.
            <span className="block mt-1 text-gray-600">
              Emails are always drafts — never auto-sent.
            </span>
          </p>
        </div>

        {/* Bottom decoration */}
        <div className="mt-8 text-center">
          <p className="text-gray-600 text-xs">
            Built with Gemini 2.0 Flash · FastAPI · React
          </p>
        </div>
      </div>
    </div>
  )
}
