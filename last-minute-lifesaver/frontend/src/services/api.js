/**
 * Thin wrapper around backend calls. Point BASE_URL at your deployed
 * Cloud Run URL once you deploy.
 */
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://lifesaver-backend-dsmv.onrender.com'

/**
 * Helper: get the user_id from URL params or localStorage.
 * In production this would come from a proper auth session/JWT.
 */
function getUserId() {
  const params = new URLSearchParams(window.location.search)
  const fromUrl = params.get('user_id')
  if (fromUrl) {
    localStorage.setItem('lmls_user_id', fromUrl)
    return fromUrl
  }
  return localStorage.getItem('lmls_user_id') || 'demo_user'
}

/**
 * Helper: make a fetch call with standard error handling.
 */
async function apiFetch(path, options = {}) {
  const url = `${BASE_URL}${path}`
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!res.ok) {
    const errorBody = await res.text()
    throw new Error(`API error ${res.status}: ${errorBody}`)
  }

  return res.json()
}

/**
 * POST /tasks/extract — extract tasks from raw text using Gemini.
 * @param {string} rawText - Raw syllabus, email, or notes to extract tasks from.
 * @returns {Promise<{tasks: Array, count: number}>}
 */
export async function extractTasks(rawText) {
  const userId = getUserId()
  return apiFetch('/tasks/extract', {
    method: 'POST',
    body: JSON.stringify({ raw_text: rawText, user_id: userId }),
  })
}

/**
 * POST /plan/generate — generate an optimized schedule plan.
 * @returns {Promise<Object>} The generated plan with slots.
 */
export async function generatePlan() {
  const userId = getUserId()
  return apiFetch(`/plan/generate?user_id=${userId}`, {
    method: 'POST',
  })
}

/**
 * GET /plan/today — fetch the latest plan with enriched slot details.
 * @returns {Promise<{plan: Object}>}
 */
export async function getTodayPlan() {
  const userId = getUserId()
  return apiFetch(`/plan/today?user_id=${userId}`)
}

/**
 * POST /drift/check — trigger the agentic drift detection loop.
 * @returns {Promise<Object>} Drift detection results and actions taken.
 */
export async function checkDrift() {
  const userId = getUserId()
  return apiFetch(`/drift/check?user_id=${userId}`, {
    method: 'POST',
  })
}

/**
 * GET /tasks/ — list all tasks for the current user.
 * @returns {Promise<{tasks: Array}>}
 */
export async function listTasks() {
  const userId = getUserId()
  return apiFetch(`/tasks/?user_id=${userId}`)
}

/**
 * PATCH /tasks/{taskId} — update a task's status.
 * @param {string} taskId - The task ID to update.
 * @param {string} status - New status: not_started | in_progress | done | blocked
 * @returns {Promise<Object>}
 */
export async function updateTaskStatus(taskId, status) {
  return apiFetch(`/tasks/${taskId}?status=${status}`, {
    method: 'PATCH',
  })
}

/**
 * GET /drift/action-log — fetch the action log for explainability.
 * @returns {Promise<{action_log: Array}>}
 */
export async function getActionLog() {
  const userId = getUserId()
  return apiFetch(`/drift/action-log?user_id=${userId}`)
}

export { BASE_URL, getUserId }
