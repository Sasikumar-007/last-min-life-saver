/**
 * Dashboard: today's plan + chat/voice input + manual "check drift" button.
 *
 * YOUR WORK:
 *   - Render today's plan (GET /plan/today) as a timeline/list
 *   - A text input that posts raw_text to /tasks/extract, then triggers
 *     /plan/generate and refreshes the view
 *   - A "what should I do right now" button (voice or text) that just
 *     surfaces the next unfinished slot from the plan
 *   - A manual "Check in now" button that calls /drift/check, so you can
 *     trigger the agentic loop on demand during your demo instead of
 *     waiting for the real Cloud Scheduler interval
 *   - A simple action log view (reads action_log via a backend endpoint
 *     you add) so judges can see WHY the agent did what it did
 */

import { useState, useEffect, useCallback } from 'react'
import {
  extractTasks,
  generatePlan,
  getTodayPlan,
  checkDrift,
  updateTaskStatus,
  getActionLog,
  getUserId,
} from '../services/api'

// ─── Status badge config ─────────────────────────────────────
const STATUS_CONFIG = {
  done: { label: 'Done', bg: 'bg-emerald-500/15', text: 'text-emerald-400', ring: 'ring-emerald-500/30', icon: '✓' },
  in_progress: { label: 'In Progress', bg: 'bg-amber-500/15', text: 'text-amber-400', ring: 'ring-amber-500/30', icon: '◐' },
  not_started: { label: 'Not Started', bg: 'bg-gray-500/15', text: 'text-gray-400', ring: 'ring-gray-500/30', icon: '○' },
  blocked: { label: 'Blocked', bg: 'bg-red-500/15', text: 'text-red-400', ring: 'ring-red-500/30', icon: '✕' },
}

// ─── Helpers ──────────────────────────────────────────────────
function formatTime(isoStr) {
  if (!isoStr) return '--:--'
  try {
    const d = new Date(isoStr)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch { return '--:--' }
}

function formatDate(isoStr) {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
  } catch { return '' }
}

function formatTimestamp(isoStr) {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return '' }
}

export default function Dashboard() {
  // ─── State ──────────────────────────────────────────────────
  const [plan, setPlan] = useState(null)
  const [rawText, setRawText] = useState('')
  const [actionLog, setActionLog] = useState([])
  const [loading, setLoading] = useState({ plan: false, extract: false, drift: false })
  const [toast, setToast] = useState(null)
  const [highlightedSlot, setHighlightedSlot] = useState(null)
  const [driftResult, setDriftResult] = useState(null)
  const [showActionLog, setShowActionLog] = useState(false)

  // ─── Toast helper ───────────────────────────────────────────
  const showToast = useCallback((message, type = 'info') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }, [])

  // ─── Load plan on mount ─────────────────────────────────────
  const loadPlan = useCallback(async () => {
    try {
      setLoading(prev => ({ ...prev, plan: true }))
      const data = await getTodayPlan()
      setPlan(data.plan)
    } catch (err) {
      console.error('Failed to load plan:', err)
    } finally {
      setLoading(prev => ({ ...prev, plan: false }))
    }
  }, [])

  const loadActionLog = useCallback(async () => {
    try {
      const data = await getActionLog()
      setActionLog(data.action_log || [])
    } catch (err) {
      console.error('Failed to load action log:', err)
    }
  }, [])

  useEffect(() => {
    loadPlan()
    loadActionLog()
  }, [loadPlan, loadActionLog])

  // ─── Extract & Plan ─────────────────────────────────────────
  const handleExtractAndPlan = async () => {
    if (!rawText.trim()) {
      showToast('Please paste some text to extract tasks from.', 'warning')
      return
    }

    try {
      setLoading(prev => ({ ...prev, extract: true }))
      showToast('🔍 Extracting tasks with Gemini...', 'info')

      const extractResult = await extractTasks(rawText)
      showToast(`📋 Extracted ${extractResult.count} tasks. Generating plan...`, 'success')

      await generatePlan()
      showToast('✅ Plan generated! Your schedule is ready.', 'success')

      setRawText('')
      await loadPlan()
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error')
    } finally {
      setLoading(prev => ({ ...prev, extract: false }))
    }
  }

  // ─── Mark task done ──────────────────────────────────────────
  const handleToggleStatus = async (taskId, currentStatus) => {
    const newStatus = currentStatus === 'done' ? 'not_started' : 'done'
    try {
      await updateTaskStatus(taskId, newStatus)
      showToast(`Task marked as ${newStatus === 'done' ? 'done ✓' : 'not started'}`, 'success')
      await loadPlan()
    } catch (err) {
      showToast(`Failed to update: ${err.message}`, 'error')
    }
  }

  // ─── What should I do now? ──────────────────────────────────
  const handleWhatNow = () => {
    if (!plan || !plan.slots || plan.slots.length === 0) {
      showToast('No plan yet. Extract tasks and generate a plan first!', 'warning')
      return
    }

    const now = new Date()
    const nextSlot = plan.slots.find(slot => {
      const status = slot.status || 'not_started'
      if (status === 'done') return false
      try {
        return new Date(slot.end) > now
      } catch { return false }
    })

    if (nextSlot) {
      setHighlightedSlot(nextSlot.task_id)
      showToast(`👉 Focus on: "${nextSlot.title}" (${formatTime(nextSlot.start)} - ${formatTime(nextSlot.end)})`, 'info')
      setTimeout(() => setHighlightedSlot(null), 5000)
    } else {
      showToast('🎉 All tasks completed! You\'re all caught up.', 'success')
    }
  }

  // ─── Check drift ────────────────────────────────────────────
  const handleCheckDrift = async () => {
    try {
      setLoading(prev => ({ ...prev, drift: true }))
      showToast('🔄 Running drift check...', 'info')

      const result = await checkDrift()
      setDriftResult(result)

      if (result.drift_detected) {
        showToast(`⚠️ Drift detected! ${result.actions_taken?.length || 0} corrective action(s) taken.`, 'warning')
      } else {
        showToast('✅ No drift — you\'re on track!', 'success')
      }

      await loadPlan()
      await loadActionLog()
    } catch (err) {
      showToast(`Drift check failed: ${err.message}`, 'error')
    } finally {
      setLoading(prev => ({ ...prev, drift: false }))
    }
  }

  // ─── Render ─────────────────────────────────────────────────
  const slots = plan?.slots || []

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-950 to-gray-900 text-white">
      {/* ── Toast notification ── */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 max-w-sm px-5 py-3 rounded-2xl shadow-2xl backdrop-blur-xl border transition-all duration-500 animate-slide-in
          ${toast.type === 'error' ? 'bg-red-500/15 border-red-500/30 text-red-300' :
            toast.type === 'warning' ? 'bg-amber-500/15 border-amber-500/30 text-amber-300' :
            toast.type === 'success' ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300' :
            'bg-indigo-500/15 border-indigo-500/30 text-indigo-300'}`}
        >
          <p className="text-sm font-medium">{toast.message}</p>
        </div>
      )}

      {/* ── Header ── */}
      <header className="border-b border-white/5 bg-white/[0.02] backdrop-blur-xl sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">Last-Minute Life Saver</h1>
              <p className="text-xs text-gray-500">AI-powered schedule agent</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* What should I do now? */}
            <button
              id="what-now-btn"
              onClick={handleWhatNow}
              className="px-4 py-2 rounded-xl text-sm font-medium bg-white/5 hover:bg-white/10 border border-white/10 hover:border-indigo-500/30 text-gray-300 hover:text-indigo-300 transition-all duration-300"
            >
              <span className="mr-1.5">🎯</span>What now?
            </button>

            {/* Check drift */}
            <button
              id="check-drift-btn"
              onClick={handleCheckDrift}
              disabled={loading.drift}
              className="px-4 py-2 rounded-xl text-sm font-medium bg-gradient-to-r from-amber-500/15 to-orange-500/15 hover:from-amber-500/25 hover:to-orange-500/25 border border-amber-500/20 text-amber-300 transition-all duration-300 disabled:opacity-50"
            >
              {loading.drift ? (
                <span className="flex items-center gap-2">
                  <span className="w-3.5 h-3.5 border-2 border-amber-400/30 border-t-amber-400 rounded-full animate-spin" />
                  Checking...
                </span>
              ) : (
                <><span className="mr-1.5">🔄</span>Check in now</>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {/* ── Text input: Extract & Plan ── */}
        <section id="extract-section" className="bg-white/[0.03] backdrop-blur-sm border border-white/5 rounded-2xl p-6 hover:border-indigo-500/20 transition-colors duration-500">
          <h2 className="text-base font-semibold text-gray-300 mb-3 flex items-center gap-2">
            <span className="w-7 h-7 bg-indigo-500/15 rounded-lg flex items-center justify-center text-sm">📝</span>
            Paste your syllabus, email, or notes
          </h2>
          <textarea
            id="raw-text-input"
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            rows={5}
            placeholder={'Paste anything here...\n\nExamples:\n• "Math assignment due Friday, should take 2 hours"\n• A full course syllabus with multiple deadlines\n• A forwarded email about a group project'}
            className="w-full bg-black/20 border border-white/10 rounded-xl px-4 py-3 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500/40 resize-none transition-all duration-300"
          />
          <div className="flex items-center justify-between mt-3">
            <p className="text-xs text-gray-600">
              Gemini will extract tasks, deadlines, and effort estimates automatically.
            </p>
            <button
              id="extract-plan-btn"
              onClick={handleExtractAndPlan}
              disabled={loading.extract || !rawText.trim()}
              className="px-5 py-2.5 rounded-xl text-sm font-semibold bg-gradient-to-r from-indigo-500 to-violet-500 hover:from-indigo-400 hover:to-violet-400 text-white shadow-lg shadow-indigo-500/20 hover:shadow-indigo-500/40 transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed hover:-translate-y-0.5 active:translate-y-0"
            >
              {loading.extract ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Processing...
                </span>
              ) : (
                'Extract & Plan ✨'
              )}
            </button>
          </div>
        </section>

        {/* ── Drift result panel ── */}
        {driftResult && (
          <section className={`rounded-2xl p-5 border backdrop-blur-sm transition-all duration-500 ${
            driftResult.drift_detected
              ? 'bg-amber-500/5 border-amber-500/20'
              : 'bg-emerald-500/5 border-emerald-500/20'
          }`}>
            <div className="flex items-start justify-between">
              <div>
                <h3 className={`font-semibold text-sm ${driftResult.drift_detected ? 'text-amber-300' : 'text-emerald-300'}`}>
                  {driftResult.drift_detected ? '⚠️ Drift Detected' : '✅ On Track'}
                </h3>
                <p className="text-xs text-gray-400 mt-1">{driftResult.message}</p>
                {driftResult.reasoning && (
                  <p className="text-xs text-gray-500 mt-2 italic border-l-2 border-gray-700 pl-3">
                    {driftResult.reasoning}
                  </p>
                )}
              </div>
              <button
                onClick={() => setDriftResult(null)}
                className="text-gray-600 hover:text-gray-400 text-lg transition-colors"
              >
                ×
              </button>
            </div>
            {driftResult.actions_taken && driftResult.actions_taken.length > 0 && (
              <div className="mt-3 space-y-1.5">
                <p className="text-xs font-medium text-gray-400">Actions taken by AI:</p>
                {driftResult.actions_taken.map((action, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs text-gray-500">
                    <span className={`w-1.5 h-1.5 rounded-full ${action.status === 'executed' ? 'bg-emerald-500' : 'bg-red-500'}`} />
                    <span className="font-mono text-gray-400">{action.tool}</span>
                    <span>— {action.status}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* ── Today's Plan Timeline ── */}
        <section id="plan-timeline">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-300 flex items-center gap-2">
              <span className="w-7 h-7 bg-violet-500/15 rounded-lg flex items-center justify-center text-sm">📅</span>
              Today's Plan
            </h2>
            {plan && (
              <p className="text-xs text-gray-600">
                Generated {formatTimestamp(plan.generated_at)}
              </p>
            )}
          </div>

          {loading.plan ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-8 h-8 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
            </div>
          ) : slots.length === 0 ? (
            <div className="bg-white/[0.02] border border-white/5 rounded-2xl py-16 text-center">
              <div className="w-16 h-16 mx-auto mb-4 bg-gray-800/50 rounded-2xl flex items-center justify-center text-2xl">
                📭
              </div>
              <p className="text-gray-500 text-sm">No plan yet.</p>
              <p className="text-gray-600 text-xs mt-1">Paste some text above and click "Extract & Plan" to get started.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {slots.map((slot, index) => {
                const statusCfg = STATUS_CONFIG[slot.status] || STATUS_CONFIG.not_started
                const isHighlighted = highlightedSlot === slot.task_id
                const isPast = (() => {
                  try { return new Date(slot.end) < new Date() } catch { return false }
                })()

                return (
                  <div
                    key={`${slot.task_id}-${index}`}
                    id={`slot-${slot.task_id}`}
                    className={`group relative flex items-center gap-4 bg-white/[0.03] border rounded-xl px-5 py-4 transition-all duration-500 hover:bg-white/[0.06] cursor-pointer
                      ${isHighlighted ? 'border-indigo-500/50 bg-indigo-500/10 ring-1 ring-indigo-500/30 scale-[1.01]' : 'border-white/5 hover:border-white/10'}
                      ${isPast && slot.status !== 'done' ? 'opacity-70' : ''}`}
                    onClick={() => handleToggleStatus(slot.task_id, slot.status)}
                  >
                    {/* Timeline connector */}
                    <div className="flex flex-col items-center self-stretch">
                      <div className={`w-3 h-3 rounded-full ring-2 ${statusCfg.ring} ${slot.status === 'done' ? 'bg-emerald-500' : 'bg-gray-700'} transition-colors duration-300`} />
                      {index < slots.length - 1 && (
                        <div className="w-0.5 flex-1 bg-white/5 mt-1" />
                      )}
                    </div>

                    {/* Time column */}
                    <div className="w-24 flex-shrink-0 text-right">
                      <p className="text-sm font-mono text-gray-400">{formatTime(slot.start)}</p>
                      <p className="text-xs font-mono text-gray-600">{formatTime(slot.end)}</p>
                    </div>

                    {/* Task info */}
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium truncate ${slot.status === 'done' ? 'line-through text-gray-500' : 'text-gray-200'}`}>
                        {slot.title || 'Untitled Task'}
                      </p>
                      <div className="flex items-center gap-3 mt-1">
                        {slot.type && (
                          <span className="text-xs text-gray-600 capitalize">{slot.type}</span>
                        )}
                        {slot.effort_minutes && (
                          <span className="text-xs text-gray-600">{slot.effort_minutes}m</span>
                        )}
                        {slot.deadline && (
                          <span className="text-xs text-gray-600">Due {formatDate(slot.deadline)}</span>
                        )}
                      </div>
                    </div>

                    {/* Status badge */}
                    <div className={`px-3 py-1 rounded-lg text-xs font-medium ring-1 ${statusCfg.bg} ${statusCfg.text} ${statusCfg.ring}`}>
                      {statusCfg.icon} {statusCfg.label}
                    </div>

                    {/* Click hint */}
                    <div className="absolute right-3 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity text-xs text-gray-600">
                      click to toggle ✓
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>

        {/* ── Action Log (Explainability for judges) ── */}
        <section id="action-log-section">
          <button
            id="toggle-action-log-btn"
            onClick={() => {
              setShowActionLog(!showActionLog)
              if (!showActionLog) loadActionLog()
            }}
            className="flex items-center gap-2 text-sm font-medium text-gray-400 hover:text-gray-300 transition-colors mb-3"
          >
            <span className="w-7 h-7 bg-gray-800/50 rounded-lg flex items-center justify-center text-sm">🧠</span>
            AI Decision Log
            <span className="text-xs text-gray-600">({actionLog.length} entries)</span>
            <svg
              className={`w-4 h-4 text-gray-600 transition-transform duration-300 ${showActionLog ? 'rotate-180' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {showActionLog && (
            <div className="space-y-2 animate-fade-in">
              {actionLog.length === 0 ? (
                <div className="bg-white/[0.02] border border-white/5 rounded-xl py-8 text-center">
                  <p className="text-gray-600 text-sm">No actions logged yet. Run a drift check to see AI decisions here.</p>
                </div>
              ) : (
                actionLog.map((entry, i) => (
                  <div
                    key={entry.id || i}
                    className="bg-white/[0.02] border border-white/5 rounded-xl px-5 py-3 hover:border-white/10 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-indigo-500/60" />
                        <span className="text-xs font-mono text-indigo-400">{entry.action_taken}</span>
                        <span className="text-xs text-gray-600">via {entry.trigger}</span>
                      </div>
                      <span className="text-xs text-gray-600">{formatTimestamp(entry.timestamp)}</span>
                    </div>
                    {entry.reasoning && (
                      <p className="text-xs text-gray-400 leading-relaxed border-l-2 border-indigo-500/20 pl-3">
                        💭 {entry.reasoning}
                      </p>
                    )}
                    {entry.details && (
                      <details className="mt-2">
                        <summary className="text-xs text-gray-600 cursor-pointer hover:text-gray-400 transition-colors">
                          Show details
                        </summary>
                        <pre className="text-xs text-gray-600 mt-1 bg-black/20 rounded-lg p-2 overflow-x-auto">
                          {JSON.stringify(entry.details, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </section>
      </main>

      {/* ── Footer ── */}
      <footer className="border-t border-white/5 mt-12">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between text-xs text-gray-700">
          <span>Last-Minute Life Saver · Hackathon 2026</span>
          <span>Powered by Gemini 2.0 Flash</span>
        </div>
      </footer>

      {/* ── Inline styles for animations ── */}
      <style>{`
        @keyframes slide-in {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        .animate-slide-in { animation: slide-in 0.4s cubic-bezier(0.16, 1, 0.3, 1); }

        @keyframes fade-in {
          from { opacity: 0; transform: translateY(-8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in { animation: fade-in 0.3s ease-out; }
      `}</style>
    </div>
  )
}
