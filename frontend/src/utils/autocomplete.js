/**
 * Instant, offline writing suggestions: current-word completion and common chat phrase continuations.
 * Pure functions, no network. Suggestions never invent dates, names or commitments; they only
 * finish the words the user has already started with neutral, widely used phrasing.
 */

export const MAX_SUGGESTIONS = 3

// Neutral work-chat phrases (lower case). A phrase matches when the user's last 2-4 words are a prefix of it.
const PHRASES = [
  'tomorrow is submission day',
  'tomorrow is submission deadline',
  'tomorrow is the submission deadline.',
  'tomorrow is the subject submission date.',
  'please send the final document.',
  'please send the report',
  'please send the latest version for review.',
  'please send me the details',
  'please let me know',
  'please share the updated file',
  'please confirm the time',
  'can you send the report',
  'can you share the document',
  'can you confirm the deadline',
  'can we move the meeting',
  'can we schedule a call',
  'could you review the draft',
  'could you please check',
  'let me know if you have any questions.',
  'let me know when you are free',
  'let me check and get back to you.',
  'i will send it',
  'i will share the update',
  'i will check and confirm',
  'i will get back to you',
  'i have sent the file',
  'i have updated the document',
  'thanks for the update.',
  'thanks for your help.',
  'thank you for sharing',
  'looking forward to your reply.',
  'the meeting is scheduled',
  'the deadline is',
  'the report is ready',
  'the final version is ready',
  'the submission is due',
  'we need to finalize the',
  'we need to discuss the',
  'we should review the',
  'what is the deadline',
  'what time works for you',
  'when is the meeting',
  'is the document ready',
  'is the report ready',
  'sounds good to me.',
  'that works for me.',
  'submit the report',
  'submit the final version',
  'submit the assignment',
]

const WORDS = [
  'about', 'above', 'access', 'action', 'afternoon', 'agenda', 'agree', 'alignment', 'already', 'always',
  'announcement', 'another', 'approval', 'approve', 'assignment', 'attached', 'available', 'because', 'before',
  'budget', 'calendar', 'cancel', 'changes', 'checklist', 'clarify', 'client', 'complete', 'confirm',
  'confirmation', 'conversation', 'deadline', 'decision', 'deliver', 'delivery', 'details', 'discuss',
  'discussion', 'document', 'documentation', 'draft', 'earlier', 'everyone', 'example', 'feedback', 'final',
  'finalize', 'following', 'forward', 'friday', 'handover', 'important', 'information', 'invitation',
  'meeting', 'message', 'milestone', 'monday', 'morning', 'necessary', 'otherwise', 'owner', 'participants',
  'please', 'presentation', 'priority', 'probably', 'progress', 'project', 'proposal', 'question', 'receive',
  'recommend', 'reminder', 'report', 'request', 'requirements', 'response', 'responsible', 'review',
  'schedule', 'section', 'shared', 'should', 'someone', 'something', 'status', 'submission', 'submit',
  'subject', 'summary', 'support', 'tomorrow', 'tonight', 'tuesday', 'understand', 'update', 'urgent',
  'version', 'wednesday', 'whether', 'without', 'yesterday', 'thursday', 'through', 'together', 'timeline',
]

const tokenize = (text) => {
  const tokens = []
  const re = /\S+/g
  let m
  while ((m = re.exec(text)) !== null) tokens.push({ word: m[0], start: m.index })
  return tokens
}

const matchCase = (typed, word) =>
  typed && typed[0] !== typed[0].toLowerCase() && typed[0] === typed[0].toUpperCase()
    ? word[0].toUpperCase() + word.slice(1)
    : word

/**
 * @param {string} textBeforeCaret
 * @returns {{id: string, text: string, from: number, kind: 'local'}[]}
 *   `text` replaces textBeforeCaret.slice(from); earlier text is never touched.
 */
export function getLocalSuggestions(textBeforeCaret) {
  const text = textBeforeCaret || ''
  if (!text.trim()) return []

  const endsWithSpace = /\s$/.test(text)
  // Only the current sentence/line matters for phrase matching.
  const clauseStart = Math.max(
    text.lastIndexOf('\n') + 1,
    ...['.', '!', '?'].map((p) => text.lastIndexOf(p) + 1),
  )
  const tokens = tokenize(text.slice(clauseStart)).map((t) => ({ ...t, start: t.start + clauseStart }))
  if (tokens.length === 0) return []

  const typed = tokens.map((t) => t.word.toLowerCase())
  const starts = tokens.map((t) => t.start)
  if (endsWithSpace) {
    typed.push('')
    starts.push(text.length)
  }

  const out = []
  const seen = new Set()
  const push = (s) => {
    const key = s.text.toLowerCase()
    if (key === text.slice(s.from).toLowerCase() || seen.has(key)) return
    seen.add(key)
    out.push({ id: `local-${out.length}-${key}`, kind: 'local', ...s })
  }

  for (let k = Math.min(4, typed.length); k >= 2 && out.length < MAX_SUGGESTIONS; k--) {
    const tail = typed.slice(-k)
    const from = starts[starts.length - k]
    for (const phrase of PHRASES) {
      const p = phrase.split(' ')
      if (p.length < k) continue
      let ok = true
      for (let i = 0; i < k - 1 && ok; i++) ok = p[i] === tail[i]
      const last = tail[k - 1]
      if (!ok || !p[k - 1].startsWith(last) || (p.length === k && p[k - 1].length === last.length)) continue
      const typedHead = text.slice(from, starts[starts.length - 1])
      const lastWord = matchCase(last, p[k - 1])
      push({ text: typedHead + lastWord + (p.length > k ? ' ' + p.slice(k).join(' ') : ''), from })
      if (out.length >= MAX_SUGGESTIONS) break
    }
  }

  if (!endsWithSpace) {
    const partial = typed[typed.length - 1].replace(/^[("'[]+/, '')
    if (partial.length >= 3 && /^[a-z]+$/.test(partial)) {
      const from = starts[starts.length - 1]
      const lead = tokens[tokens.length - 1].word.length - tokens[tokens.length - 1].word.replace(/^[("'[]+/, '').length
      for (const w of WORDS) {
        if (out.length >= MAX_SUGGESTIONS) break
        if (w.startsWith(partial) && w !== partial) {
          push({ text: text.slice(from, from + lead) + matchCase(tokens[tokens.length - 1].word.slice(lead), w), from })
        }
      }
    }
  }

  // Present every suggestion as the whole sentence so far, completed. The leading words are the user's own
  // text, so replacing from the sentence start changes nothing they typed.
  const sentenceFrom = starts[0]
  return out.slice(0, MAX_SUGGESTIONS).map((s) => ({
    ...s,
    text: text.slice(sentenceFrom, s.from) + s.text,
    from: sentenceFrom,
  }))
}
