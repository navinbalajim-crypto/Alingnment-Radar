/**
 * Client-side pre-send ambiguity detection engine.
 * Identifies unclear drafts while preserving casual phrases and specific details.
 */

const CASUAL_PATTERNS = [
  /^(?:hi|hello|hey|yo|hola|bro|buddy|dude|mate)(?:\s+[a-zA-Z0-9_-]+)*[!.?]*$/i,
  /^(?:ok|okay|k|cool|sure|yep|yeah|yes|no|nope|nah|fine|alright|done|checked)[!.?]*$/i,
  /^(?:thanks|thank you|thx|ty|great|nice|awesome|perfect|sounds good)[!.?]*$/i,
  /^(?:okay|ok|sure|cool),\s*(?:i will|i'll)\s*(?:check|look|do it|see|review|handle it)[!.?]*$/i,
  /^(?:good morning|good afternoon|good evening|good night|gm|gn)[!.?]*$/i,
  /^(?:bye|see you|cya|take care|later)[!.?]*$/i,
]

const SPECIFIC_TIME_PATTERNS = [
  /\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b/i,
  /\b\d{1,2}\s*(?:o'clock|hrs?|hours?)\b/i,
  /\b\d{1,2}:\d{2}\b/,
  /\b(?:noon|midnight|end of day|eod|cob)\b/i,
]

const SPECIFIC_TASK_KEYWORDS = [
  'frontend', 'backend', 'api', 'integration', 'ui', 'ux', 'report',
  'assignment', 'presentation', 'slides', 'documentation', 'pr', 'pull request',
  'database', 'schema', 'code review', 'sprint', 'feature', 'bug', 'issue',
  'deployment', 'build', 'pipeline', 'proposal', 'contract', 'invoice', 'paper',
  'exam', 'test', 'quiz', 'homework', 'deliverable', 'milestone', 'implementation'
]

export function detectDraftAmbiguityLocally(draft, { contextText = '' } = {}) {
  if (!draft || draft.trim().length < 5) return null

  const clean = draft.trim()
  const cleanLower = clean.toLowerCase()

  // 1. Skip casual greetings, acknowledgments, and routine conversational remarks
  for (const pat of CASUAL_PATTERNS) {
    if (pat.test(cleanLower)) return null
  }

  const ctxLower = (contextText || '').toLowerCase()

  // 2. Check for deadline / submission mentions
  const deadlineSignals = ['deadline', 'submission', 'submit', 'due date', 'is due', 'turn in', 'hand in']
  const hasDeadlineSignal = deadlineSignals.some((sig) => cleanLower.includes(sig))

  if (hasDeadlineSignal) {
    const hasTime = SPECIFIC_TIME_PATTERNS.some((pat) => pat.test(cleanLower))
    const hasTask = SPECIFIC_TASK_KEYWORDS.some((tk) => new RegExp(`\\b${tk}\\b`, 'i').test(cleanLower))
    const taskInContext = SPECIFIC_TASK_KEYWORDS.some((tk) => new RegExp(`\\b${tk}\\b`, 'i').test(ctxLower))

    // Specific! E.g. "Tomorrow at 10 AM IST, we need to submit the frontend implementation."
    if ((hasTask || taskInContext) && hasTime) {
      return null
    }

    const vagueDeadlinePatterns = [
      /^(?:tomorrow|today|tonight|this week|friday|monday)\s+(?:is|has)?\s*(?:the\s+)?deadline[!.?]*$/i,
      /^(?:the\s+)?deadline\s+is\s+(?:tomorrow|today|tonight|this week|friday|monday)[!.?]*$/i,
      /^(?:we have|there is)\s+(?:a\s+)?deadline(?:\s+tomorrow|\s+today)?[!.?]*$/i,
      /^(?:need to|we must|should|have to)\s+submit(?:\s+it|\s+this)?(?:\s+tomorrow|\s+today|\s+soon)?[!.?]*$/i,
      /^tomorrow\s+(?:is\s+)?(?:submission|submitting)[!.?]*$/i,
    ]

    const isVagueDeadline = vagueDeadlinePatterns.some((pat) => pat.test(cleanLower))

    if (isVagueDeadline || (!hasTask && !taskInContext) || (!hasTime && (cleanLower.includes('tomorrow') || cleanLower.includes('today')))) {
      const missingItems = []
      const suggestedActions = []

      if (!hasTask && !taskInContext) {
        missingItems.push('which task or deliverable is due')
        suggestedActions.push('Add the task or deliverable.')
      }

      if (!hasTime) {
        missingItems.push('the exact deadline time')
        suggestedActions.push('Add the deadline time if known.')
      }

      suggestedActions.push('Clarify missing details.')

      const explanation = missingItems.length > 0
        ? `The recipient may not know ${missingItems.join(' or ')}.`
        : 'The recipient may need the exact time and deliverable requirements.'

      let improved
      if (!hasTask && !hasTime) {
        improved = `${clean} — please specify which task and the exact time.`
      } else if (!hasTask && hasTime) {
        improved = `${clean} (for [task name])`
      } else if (hasTask && !hasTime) {
        improved = `${clean} by [time, e.g. 5:00 PM]`
      } else {
        improved = clean
      }

      return {
        ambiguityDetected: true,
        ambiguityDetails: explanation,
        suggestedActions,
        clarificationPrompt: 'What task and time does this deadline refer to?',
        improvedDraft: improved,
      }
    }
  }

  // 3. Vague referents ("Check that thing", "Fix it now")
  const vagueReferents = [
    /^(?:can you|please|kindly|pls)?\s*(?:check|fix|look at|review|update|test)\s+(?:that|it|that thing|this thing)[!.?]*$/i,
    /^(?:did you|have you)\s+(?:finish|finished|do|done|check|checked)\s+(?:it|that)[!.?]*$/i,
  ]
  if (vagueReferents.some((pat) => pat.test(cleanLower))) {
    if (!ctxLower || ctxLower.split(/\s+/).length < 4) {
      return {
        ambiguityDetected: true,
        ambiguityDetails: 'The recipient may not know which specific item, task, or file you are referring to.',
        suggestedActions: [
          'Specify the exact deliverable, PR, or file name.',
          'Include a link or identifier to give immediate context.',
        ],
        clarificationPrompt: 'Which specific item or task are you referring to?',
        improvedDraft: `${clean} ([specify task or file name])`,
      }
    }
  }

  return null
}
