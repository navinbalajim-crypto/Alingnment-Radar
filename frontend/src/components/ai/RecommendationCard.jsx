import React, { useState, useMemo } from 'react'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { ExternalLink, Share2, Check, Music, Video, Globe, X } from 'lucide-react'
import { useChat } from '../../context/ChatContext'

export function RecommendationCard({ recommendation, compact = false, className = '' }) {
  const { shareRecommendation, dismissRecommendation } = useChat()
  const [isSharing, setIsSharing] = useState(false)
  const [isDismissed, setIsDismissed] = useState(false)
  const [shareError, setShareError] = useState(null)
  const [imgError, setImgError] = useState(false)

  const published_date = recommendation?.published_date
  const formattedDate = useMemo(() => {
    if (!published_date) return null
    try {
      if (/^\d{4}$/.test(published_date)) return published_date
      const d = new Date(published_date)
      if (isNaN(d.getTime())) return null
      const year = d.getFullYear()
      if (year > new Date().getFullYear()) return null
      return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short' })
    } catch {
      return null
    }
  }, [published_date])

  if (!recommendation || isDismissed || recommendation.is_dismissed) return null

  const {
    id,
    source,
    title,
    url,
    snippet,
    category,
    extra_data = {},
    is_shared_in_chat,
  } = recommendation

  const author = extra_data.artist || (Array.isArray(extra_data.artists) ? extra_data.artists.join(', ') : extra_data.artists) || extra_data.channel || extra_data.publisher || extra_data.author || null
  const thumbnail = !imgError ? (extra_data.thumbnail || extra_data.image_url || null) : null

  const getSourceIcon = (src) => {
    const s = (src || '').toLowerCase()
    if (s.includes('spotify')) return <Music className="w-3.5 h-3.5 text-emerald-500" />
    if (s.includes('youtube')) return <Video className="w-3.5 h-3.5 text-red-500" />
    return <Globe className="w-3.5 h-3.5 text-blue-500" />
  }

  const getSourceBadgeVariant = (src) => {
    const s = (src || '').toLowerCase()
    if (s.includes('spotify')) return 'emerald'
    if (s.includes('youtube')) return 'rose'
    return 'blue'
  }

  const handleShare = async () => {
    if (isSharing || is_shared_in_chat) return
    setIsSharing(true)
    setShareError(null)
    try {
      await shareRecommendation(id)
    } catch (err) {
      setShareError(err.response?.data?.detail || 'Failed to share card.')
    } finally {
      setIsSharing(false)
    }
  }

  const handleDismiss = async () => {
    setIsDismissed(true)
    if (dismissRecommendation) {
      try {
        await dismissRecommendation(id)
      } catch (err) {
        console.error('Failed to dismiss recommendation:', err)
      }
    }
  }

  return (
    <div
      className={`rounded-2xl bg-white dark:bg-neutral-900 border border-neutral-200/90 dark:border-neutral-800 shadow-subtle hover:shadow-apple transition-all duration-200 ${
        compact ? 'p-2.5 my-1 mx-0 max-w-full' : 'my-2.5 mx-2 p-3.5 max-w-md'
      } ${className}`}
    >
      {/* Header bar */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5">
          {getSourceIcon(source)}
          <span className="text-xs font-semibold text-neutral-800 dark:text-neutral-200 capitalize">
            {source}
          </span>
          {category && (
            <Badge variant="neutral" size="sm" className="ml-1 text-[10px]">
              {category}
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {formattedDate && (
            <span className="text-[10px] text-neutral-400">
              {formattedDate}
            </span>
          )}
          <button
            type="button"
            onClick={handleDismiss}
            className="p-1 rounded-md text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
            title="Dismiss recommendation"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main card body with optional thumbnail */}
      <div className="flex gap-3 items-start">
        {thumbnail && (
          <div className={`${compact ? 'w-12 h-12' : 'w-16 h-16'} rounded-xl overflow-hidden bg-neutral-100 dark:bg-neutral-800 shrink-0 border border-black/5`}>
            <img
              src={thumbnail}
              alt={title}
              onError={() => setImgError(true)}
              className="w-full h-full object-cover"
            />
          </div>
        )}

        <div className="flex-1 min-w-0">
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 hover:text-apple-blue dark:hover:text-blue-400 line-clamp-2 transition-colors flex items-center gap-1 group"
          >
            <span>{title}</span>
            <ExternalLink className="w-3 h-3 opacity-60 group-hover:opacity-100 shrink-0" />
          </a>

          {author && (
            <p className="text-[11px] font-medium text-neutral-500 dark:text-neutral-400 mt-0.5 truncate">
              by {author}
            </p>
          )}

          {snippet && (
            <p className="text-[11px] text-neutral-600 dark:text-neutral-400 mt-1 line-clamp-2 leading-relaxed">
              {snippet}
            </p>
          )}
        </div>
      </div>

      {shareError && (
        <p className="text-[11px] text-red-500 mt-2">{shareError}</p>
      )}

      {/* Card actions */}
      <div className={`flex items-center justify-between ${compact ? 'mt-2 pt-2' : 'mt-3 pt-2.5'} border-t border-neutral-100 dark:border-neutral-800 text-xs`}>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-apple-blue dark:text-blue-400 font-medium hover:underline inline-flex items-center gap-1"
        >
          <span>Open link</span>
          <ExternalLink className="w-3 h-3" />
        </a>

        {is_shared_in_chat ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-neutral-400 font-medium">
            <Check className="w-3 h-3 text-emerald-500" />
            Shared in conversation
          </span>
        ) : (
          <Button
            size="sm"
            variant="secondary"
            onClick={handleShare}
            isLoading={isSharing}
            className="text-xs py-1 px-2.5 gap-1.5"
          >
            <Share2 className="w-3 h-3" />
            <span>Share in Chat</span>
          </Button>
        )}
      </div>
    </div>
  )
}
