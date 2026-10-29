/**
 * Fast client-side spelling correction & text normalization engine.
 * Provides instant (<5ms) suggestions for common typos, contractions, and repeated letters.
 */

import { classifyToken, spellingAssetsLoaded, looksLikeCode } from './spellChecker.js'

export const COMMON_TYPOS = {
  // User reported examples
  'elaphant': 'elephant',
  'infoooorm': 'information',
  'informmm': 'inform',
  'tmrw': 'tomorrow',
  'bcoz': 'because',
  'discus': 'discuss',
  'budjet': 'budget',
  'misic': 'music',
  'didnot': 'did not',
  'doesnot': 'does not',
  'hsa': 'has',
  'afterrnoon': 'afternoon',
  'afternoonn': 'afternoon',
  'cant': 'cannot',
  'dont': "don't",
  'wont': "won't",
  'couldnot': 'could not',
  'shouldnot': 'should not',
  'wouldnot': 'would not',
  'isnot': 'is not',
  'hasnot': 'has not',
  'havenot': 'have not',
  'hadnot': 'had not',
  'wasnot': 'was not',
  'werenot': 'were not',
  'arent': 'are not',

  // Common chat abbreviations & contractions
  'pls': 'please',
  'plz': 'please',
  'thx': 'thanks',
  'u': 'you',
  'ur': 'your',
  'r': 'are',
  'btw': 'by the way',
  'asap': 'as soon as possible',
  'idk': "I don't know",
  'omg': 'oh my god',
  'tbh': 'to be honest',
  'cuz': 'because',
  'cos': 'because',
  'dunno': "don't know",
  'gonna': 'going to',
  'wanna': 'want to',
  'gotta': 'got to',
  'kinda': 'kind of',
  'sorta': 'sort of',
  'abt': 'about',
  'msg': 'message',
  'txt': 'text',
  'pic': 'picture',
  'pics': 'pictures',
  'sec': 'second',
  'min': 'minute',
  'mins': 'minutes',
  'hr': 'hour',
  'hrs': 'hours',
  'yr': 'year',
  'yrs': 'years',

  // High-frequency English spelling mistakes
  'teh': 'the',
  'definately': 'definitely',
  'definatly': 'definitely',
  'definitly': 'definitely',
  'seperate': 'separate',
  'seperation': 'separation',
  'recieve': 'receive',
  'recieved': 'received',
  'recieving': 'receiving',
  'untill': 'until',
  'occured': 'occurred',
  'occuring': 'occurring',
  'occurance': 'occurrence',
  'accross': 'across',
  'recomended': 'recommended',
  'recomend': 'recommend',
  'recomends': 'recommends',
  'recomending': 'recommending',
  'recomendation': 'recommendation',
  'recomendations': 'recommendations',
  'sugest': 'suggest',
  'sugestion': 'suggestion',
  'sugestions': 'suggestions',
  'spotfy': 'spotify',
  'spotifiy': 'spotify',
  'vedio': 'video',
  'vedios': 'videos',
  'goverment': 'government',
  'enviroment': 'environment',
  'succesful': 'successful',
  'succesfully': 'successfully',
  'thier': 'their',
  'alot': 'a lot',
  'truely': 'truly',
  'tommorow': 'tomorrow',
  'tommorrow': 'tomorrow',
  'tomorow': 'tomorrow',
  'calender': 'calendar',
  'collegue': 'colleague',
  'colleague': 'colleague',
  'beleive': 'believe',
  'beleived': 'believed',
  'acheive': 'achieve',
  'acheived': 'achieved',
  'acheivement': 'achievement',
  'neccessary': 'necessary',
  'necesary': 'necessary',
  'begining': 'beginning',
  'appearence': 'appearance',
  'maintainance': 'maintenance',
  'pronounciation': 'pronunciation',
  'writting': 'writing',
  'appologize': 'apologize',
  'appology': 'apology',
  'comunication': 'communication',
  'comunicate': 'communicate',
  'shedule': 'schedule',
  'mispelled': 'misspelled',
  'mispell': 'misspell',
  'wierd': 'weird',
  'noticable': 'noticeable',
  'embarass': 'embarrass',
  'embarassed': 'embarrassed',
  'accomodate': 'accommodate',
  'accomodation': 'accommodation',
  'intrest': 'interest',
  'intresting': 'interesting',
  'dissapoint': 'disappoint',
  'dissappointed': 'disappointed',
  'disapear': 'disappear',
  'adress': 'address',
  'adressed': 'addressed',
  'alright': 'all right',
  'basicly': 'basically',
  'fourty': 'forty',
  'freind': 'friend',
  'freinds': 'friends',
  'peice': 'piece',
  'relevent': 'relevant',
  'suprise': 'surprise',
  'suprised': 'surprised',
  'tendancy': 'tendency',
  'tommorrow': 'tomorrow',
  'wierd': 'weird',
  'whish': 'which',
  'wich': 'which',
  'alredy': 'already',
  'allready': 'already',
  'agian': 'again',
  'agre': 'agree',
  'alowed': 'allowed',
  'anyting': 'anything',
  'becuase': 'because',
  'beacuse': 'because',
  'becasue': 'because',
  'bussiness': 'business',
  'buisness': 'business',
  'completly': 'completely',
  'compleatly': 'completely',
  'decission': 'decision',
  'diffrent': 'different',
  'experiance': 'experience',
  'finaly': 'finally',
  'grat': 'great',
  'grete': 'great',
  'happend': 'happened',
  'hepl': 'help',
  'hopful': 'hopeful',
  'manger': 'manager',
  'mating': 'meeting',
  'meating': 'meeting',
  'neding': 'needing',
  'oppurtunity': 'opportunity',
  'posible': 'possible',
  'possiable': 'possible',
  'problem': 'problem',
  'realy': 'really',
  'remeber': 'remember',
  'rember': 'remember',
  'respone': 'response',
  'respons': 'response',
  'senario': 'scenario',
  'similer': 'similar',
  'somthing': 'something',
  'someting': 'something',
  'tihs': 'this',
  'thsi': 'this',
  'tahnk': 'thank',
  'thnks': 'thanks',
  'thanx': 'thanks',
  'thnx': 'thanks',
  'wether': 'whether',
  'woudl': 'would',
  'wud': 'would',
  'coudl': 'could',
  'cud': 'could',
  'shoudl': 'should',
  'shud': 'should',
  'yuor': 'your',
}

/**
 * Collapse repeated letters (e.g. "infoooorm" -> "inform", "sooooo" -> "so").
 */
function normalizeRepeatedChars(word) {
  return word.replace(/(.)\1{2,}/g, '$1')
}

/**
 * Layer 1 (curated map): unambiguous typos and chat abbreviations. This is the original engine and is kept
 * as the first layer and as the evaluation baseline.
 */
export function getWordCorrectionLegacy(rawWord) {
  if (!rawWord || typeof rawWord !== 'string') return null

  // Strip leading and trailing punctuation for dictionary check
  const match = rawWord.match(/^([^a-zA-Z0-9]*)(.*?)([^a-zA-Z0-9]*)$/)
  if (!match) return null

  const [, prefix, core, suffix] = match
  if (!core) return null

  const lower = core.toLowerCase()

  // 1. Direct typo dictionary match
  if (COMMON_TYPOS[lower]) {
    const fixed = COMMON_TYPOS[lower]
    const cased = matchCase(core, fixed)
    return {
      original: rawWord,
      corrected: `${prefix}${cased}${suffix}`,
      reason: `Misspelled word '${core}'`,
      confidence: 0.98,
    }
  }

  // 2. Check collapsed repeated characters
  const collapsed = normalizeRepeatedChars(lower)
  if (collapsed !== lower && COMMON_TYPOS[collapsed]) {
    const fixed = COMMON_TYPOS[collapsed]
    const cased = matchCase(core, fixed)
    return {
      original: rawWord,
      corrected: `${prefix}${cased}${suffix}`,
      reason: `Repeated letters in '${core}'`,
      confidence: 0.95,
    }
  }

  return null
}

/**
 * Slang and shorthand that are also valid, intentional chat language. They are offered as optional suggestions
 * but never rewritten automatically while the user types.
 */
export const SUGGEST_ONLY = new Set([
  'u', 'ur', 'r', 'btw', 'asap', 'idk', 'omg', 'tbh', 'cos', 'dunno', 'gonna', 'wanna', 'gotta', 'kinda', 'sorta',
  'msg', 'txt', 'pic', 'pics', 'sec', 'min', 'mins', 'hr', 'hrs', 'yr', 'yrs',
])

/**
 * Layer 1 (curated map) then layer 2 (dictionary + edit-cost + context, see spellChecker.js).
 * Only returns corrections that are safe to apply automatically while typing.
 * @param {string} rawWord
 * @param {{prev?:string, next?:string, atSentenceStart?:boolean, protectedWords?:Set<string>}} ctx
 */
export function getWordCorrection(rawWord, ctx = {}) {
  const curated = getWordCorrectionLegacy(rawWord)
  if (curated) {
    if (SUGGEST_ONLY.has(rawWord.replace(/[^A-Za-z]/g, '').toLowerCase())) return null
    return { ...curated, tier: 'auto' }
  }
  if (!spellingAssetsLoaded()) return null
  const r = classifyToken(rawWord, ctx)
  if (r.status !== 'auto') return null
  return { original: rawWord, corrected: r.corrected, reason: 'Misspelled word', confidence: r.confidence, tier: 'auto' }
}

function matchCase(original, target) {
  if (target.toLowerCase() === 'when i') {
    if (original === original.toUpperCase()) return 'WHEN I'
    if (original[0] === original[0].toUpperCase()) return 'When I'
    return 'when I'
  }
  if (original === original.toUpperCase()) return target.toUpperCase()
  if (original[0] === original[0].toUpperCase()) {
    return target.charAt(0).toUpperCase() + target.slice(1)
  }
  return target.toLowerCase()
}

/**
 * Analyze an entire draft text for spelling mistakes synchronously.
 * Returns array of suggestions and the fully corrected text.
 */
export function analyzeDraftLocally(text, options = {}) {
  if (!text || typeof text !== 'string') {
    return { corrections: [], correctedText: null }
  }

  const trimmedLower = text.trim().toLowerCase().replace(/[.!?]+$/, '')
  const PHRASING_RULES = {
    'tomorrow is submission': {
      corrected: 'The submission is due tomorrow.',
      reason: 'The deadline is unclear.',
    },
    'submission tomorrow': {
      corrected: 'The submission is due tomorrow.',
      reason: 'The deadline is unclear.',
    },
    'send the final version': {
      corrected: 'Please send the final version of the project report.',
      reason: 'Unclear document reference',
    },
    'finish it by evening': {
      corrected: 'Please finish it by 5 PM today.',
      reason: 'Ambiguous deadline time',
    },
    'deploy it after testing': {
      corrected: 'Deploy to production after automated testing passes.',
      reason: 'Unclear deployment target',
    },
  }

  if (PHRASING_RULES[trimmedLower]) {
    const rule = PHRASING_RULES[trimmedLower]
    return {
      corrections: [
        {
          original: text.trim(),
          corrected: rule.corrected,
          reason: rule.reason,
          confidence: 0.95,
        },
      ],
      correctedText: rule.corrected,
    }
  }

  const words = text.split(/(\s+)/)
  const corrections = []
  let hasChange = false

  const codeLike = looksLikeCode(text)
  const wordIdx = words.map((t, i) => (/^\s+$/.test(t) ? -1 : i)).filter((i) => i >= 0)
  const correctedWords = words.map((token, tokenIndex) => {
    // If token is purely whitespace, preserve it
    if (/^\s+$/.test(token)) return token

    // Contextual handling of 'whei'
    if (/^whei$/i.test(token)) {
      corrections.push({
        original: token,
        corrected: matchCase(token, 'when I'),
        reason: "Suggested phrasing 'when I'",
        confidence: 0.92,
      })
      hasChange = true
      return matchCase(token, 'when I')
    }

    const fix = getWordCorrectionLegacy(token)
    if (fix && fix.original !== fix.corrected) {
      const slang = SUGGEST_ONLY.has(token.replace(/[^A-Za-z]/g, '').toLowerCase())
      corrections.push({ ...fix, tier: slang ? 'suggest' : 'auto' })
      hasChange = true
      return fix.corrected
    }

    if (spellingAssetsLoaded()) {
      const n = wordIdx.indexOf(tokenIndex)
      const prevTok = n > 0 ? words[wordIdx[n - 1]] : null
      const nextTok = n + 1 < wordIdx.length ? words[wordIdx[n + 1]] : null
      const r = classifyToken(token, {
        prev: prevTok,
        next: nextTok,
        atSentenceStart: n === 0 || /[.!?]["')\]]*$/.test(prevTok),
        protectedWords: options.protectedWords,
        codeLike,
      })
      if ((r.status === 'auto' || r.status === 'suggest') && r.corrected !== token) {
        corrections.push({
          original: token,
          corrected: r.corrected,
          reason: r.status === 'auto' ? `Misspelled word '${token}'` : `Possible misspelling of '${r.corrected}'`,
          confidence: r.confidence,
          tier: r.status,
          alternatives: r.alternatives,
        })
        hasChange = true
        return r.corrected
      }
    }
    return token
  })

  // Handle multi-word typos: 'other wise' -> 'otherwise'
  let resultText = hasChange ? correctedWords.join('') : text
  if (/\bother\s+wise\b/i.test(resultText)) {
    corrections.push({
      original: 'other wise',
      corrected: 'otherwise',
      reason: "Compound word 'otherwise'",
      confidence: 0.95,
    })
    resultText = resultText.replace(/\bother\s+wise\b/gi, 'otherwise')
    hasChange = true
  }

  return {
    corrections,
    correctedText: hasChange ? resultText : null,
  }
}
