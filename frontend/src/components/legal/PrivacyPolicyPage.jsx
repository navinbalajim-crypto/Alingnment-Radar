import React, { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Shield, Lock, Eye, Mic, Cpu, UserCheck, Trash2, Mail, ExternalLink, CheckCircle } from 'lucide-react'
import { LegalNavbar } from './LegalNavbar'
import { LegalFooter } from './LegalFooter'

export function PrivacyPolicyPage() {
  useEffect(() => {
    const prevOverflow = document.body.style.overflowY
    document.body.style.overflowY = 'auto'
    window.scrollTo(0, 0)
    return () => {
      document.body.style.overflowY = prevOverflow
    }
  }, [])

  return (
    <div className="min-h-screen bg-[#F2F2F7] text-neutral-900 transition-colors dark:bg-neutral-950 dark:text-neutral-100">
      <LegalNavbar />

      <main className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
        {/* Header Hero */}
        <div className="mb-10 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-apple-blue/20 bg-apple-blue/10 px-3.5 py-1 text-xs font-semibold text-apple-blue dark:bg-apple-blue/20">
            <Shield className="h-3.5 w-3.5" />
            <span>Privacy & Data Protection</span>
          </div>
          <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-5xl">
            Privacy Policy
          </h1>
          <p className="mt-3 text-sm text-neutral-500 dark:text-neutral-400 sm:text-base">
            Effective Date: October 30, 2026 • Version 1.2
          </p>
        </div>

        {/* Content Card */}
        <div className="space-y-10 rounded-3xl border border-black/[0.06] bg-white p-6 shadow-subtle sm:p-10 dark:border-white/[0.08] dark:bg-neutral-900">
          
          {/* Executive Summary */}
          <section className="rounded-2xl border border-sky-200/60 bg-sky-50/50 p-5 dark:border-sky-500/20 dark:bg-sky-950/20">
            <h2 className="flex items-center gap-2 text-base font-bold text-sky-900 dark:text-sky-200">
              <CheckCircle className="h-5 w-5 text-sky-600 dark:text-sky-400" />
              Our Core Privacy Commitment
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-sky-800/90 dark:text-sky-300/90">
              Alignment Radar is designed to make interpersonal communications clearer and more constructive. We prioritize your privacy: we never sell your personal data, we never use your private conversations or voice notes to train public AI foundation models, and we strictly limit data collection to what is required to deliver real-time messaging, AI alignment coaching, and speech transcription.
            </p>
          </section>

          {/* Section 1: Overview */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              1. Overview & Scope
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              This Privacy Policy explains how Alignment Radar (&quot;we,&quot; &quot;our,&quot; or &quot;us&quot;) collects, uses, stores, and protects personal information when you access or use our application available at{' '}
              <a
                href="https://alingnment-radar-fdrx.vercel.app"
                target="_blank"
                rel="noreferrer"
                className="font-medium text-apple-blue underline hover:opacity-80"
              >
                https://alingnment-radar-fdrx.vercel.app
              </a>{' '}
              and associated services (the &quot;Service&quot;).
            </p>
          </section>

          {/* Section 2: Information We Collect */}
          <section className="space-y-4">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              2. Information We Collect
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              We collect information in the following categories to provide and enhance our services:
            </p>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-2xl border border-black/[0.06] bg-neutral-50/80 p-4 dark:border-white/[0.08] dark:bg-neutral-800/50">
                <div className="flex items-center gap-2 font-semibold text-neutral-900 dark:text-white">
                  <UserCheck className="h-4 w-4 text-apple-blue" />
                  <span>Google Account Information</span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-neutral-600 dark:text-neutral-400 sm:text-sm">
                  When you sign in using &quot;Sign in with Google&quot;, we receive your public profile details: email address, display name, profile avatar photo, and Google user ID (<code className="rounded bg-neutral-200 px-1 py-0.5 text-xs dark:bg-neutral-700">sub</code>). We do <strong>not</strong> access your Google Drive, Gmail messages, contacts, or calendar.
                </p>
              </div>

              <div className="rounded-2xl border border-black/[0.06] bg-neutral-50/80 p-4 dark:border-white/[0.08] dark:bg-neutral-800/50">
                <div className="flex items-center gap-2 font-semibold text-neutral-900 dark:text-white">
                  <Lock className="h-4 w-4 text-emerald-500" />
                  <span>Direct Account Information</span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-neutral-600 dark:text-neutral-400 sm:text-sm">
                  If you register directly with email and password, we store your email address, display name, custom uploaded profile avatar, and your password securely hashed using salted bcrypt.
                </p>
              </div>

              <div className="rounded-2xl border border-black/[0.06] bg-neutral-50/80 p-4 dark:border-white/[0.08] dark:bg-neutral-800/50">
                <div className="flex items-center gap-2 font-semibold text-neutral-900 dark:text-white">
                  <Mic className="h-4 w-4 text-purple-500" />
                  <span>Chat & Voice Messages</span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-neutral-600 dark:text-neutral-400 sm:text-sm">
                  Text messages, replies, reactions, and uploaded audio voice recordings that you exchange in direct or group chats. Audio recordings are securely hosted to allow intended recipients to play back voice notes.
                </p>
              </div>

              <div className="rounded-2xl border border-black/[0.06] bg-neutral-50/80 p-4 dark:border-white/[0.08] dark:bg-neutral-800/50">
                <div className="flex items-center gap-2 font-semibold text-neutral-900 dark:text-white">
                  <Cpu className="h-4 w-4 text-amber-500" />
                  <span>AI Interaction & Transcripts</span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-neutral-600 dark:text-neutral-400 sm:text-sm">
                  Voice message transcripts generated by our speech recognition pipeline, as well as AI-assisted alignment scores, tone clarification suggestions, and translation summaries.
                </p>
              </div>
            </div>
          </section>

          {/* Section 3: Google API Limited Use Disclosure */}
          <section className="space-y-3 rounded-2xl border border-amber-200/80 bg-amber-50/60 p-5 dark:border-amber-500/20 dark:bg-amber-950/20">
            <h2 className="flex items-center gap-2 text-base font-bold text-amber-900 dark:text-amber-200">
              <Shield className="h-5 w-5 text-amber-600 dark:text-amber-400" />
              3. Google API Services User Data Policy Compliance
            </h2>
            <p className="text-sm leading-relaxed text-amber-900/90 dark:text-amber-200/90">
              Alignment Radar&#39;s use and transfer of information received from Google APIs to any other app will adhere to the{' '}
              <a
                href="https://developers.google.com/terms/api-services-user-data-policy"
                target="_blank"
                rel="noreferrer"
                className="font-medium underline hover:text-amber-700 dark:hover:text-amber-100"
              >
                Google API Services User Data Policy
              </a>
              , including the Limited Use requirements.
            </p>
            <ul className="list-inside list-disc space-y-1.5 text-xs text-amber-800 dark:text-amber-300 sm:text-sm">
              <li>We only request the minimal scopes necessary (<code className="rounded bg-amber-200/60 px-1 py-0.5 text-xs dark:bg-amber-900/60">openid</code>, <code className="rounded bg-amber-200/60 px-1 py-0.5 text-xs dark:bg-amber-900/60">email</code>, <code className="rounded bg-amber-200/60 px-1 py-0.5 text-xs dark:bg-amber-900/60">profile</code>) to authenticate you.</li>
              <li>We do not transfer or disclose Google user data to third parties for advertising or commercial marketing purposes.</li>
              <li>Google account data is not used to train generalized artificial intelligence or machine learning models.</li>
            </ul>
          </section>

          {/* Section 4: How We Use Your Data */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              4. How We Use Information
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              We process personal data solely for legitimate and explicit service operations:
            </p>
            <ul className="list-inside list-disc space-y-2 text-sm text-neutral-600 dark:text-neutral-300 sm:text-base">
              <li><strong>Authentication & Profile Management:</strong> Verifying your identity, creating your member profile, and managing authenticated sessions.</li>
              <li><strong>Real-Time Communication:</strong> Delivering messages, voice notes, media files, and notifications in real time via secure WebSockets.</li>
              <li><strong>AI Alignment & Clarification:</strong> Providing optional, real-time feedback on potential message ambiguities to prevent misunderstandings between team members.</li>
              <li><strong>Speech-to-Text Transcription:</strong> Transcribing spoken voice notes into text so recipients can read or search them easily.</li>
              <li><strong>Safety & Integrity:</strong> Detecting spam, abusive behavior, and safeguarding against unauthorized access or platform disruption.</li>
            </ul>
          </section>

          {/* Section 5: AI Processing & Third-Party Service Providers */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              5. AI Processing & Third-Party Providers
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              To deliver specialized capabilities, we collaborate with industry-leading infrastructure providers under strict confidentiality:
            </p>
            <ul className="list-inside list-disc space-y-2 text-sm text-neutral-600 dark:text-neutral-300 sm:text-base">
              <li><strong>Speech Transcription (Groq Whisper / Speech APIs):</strong> Voice notes sent by users are processed transiently via secure inference endpoints exclusively to generate readable transcripts.</li>
              <li><strong>AI Alignment Insights (LLM Endpoints):</strong> Contextual alignment coaching and recommendations are generated in real-time. Unsent drafts are only analyzed when the user explicitly provides consent in the application settings.</li>
              <li><strong>Hosting & Databases:</strong> Our backend is hosted on Render, frontend on Vercel, and persistent data on managed cloud PostgreSQL databases with TLS encryption in transit and at rest.</li>
            </ul>
          </section>

          {/* Section 6: Data Retention & Security */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              6. Data Retention & Security Measures
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              We employ robust administrative, technical, and physical safeguards:
            </p>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-black/[0.06] bg-neutral-50 p-4 dark:border-white/[0.08] dark:bg-neutral-800">
                <div className="text-xs font-bold uppercase tracking-wider text-apple-blue">Encryption</div>
                <div className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">All data in transit is protected with TLS 1.3 / HTTPS and secure WSS protocols.</div>
              </div>
              <div className="rounded-xl border border-black/[0.06] bg-neutral-50 p-4 dark:border-white/[0.08] dark:bg-neutral-800">
                <div className="text-xs font-bold uppercase tracking-wider text-emerald-500">Access Control</div>
                <div className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">Protected endpoints require signed JWT credentials; passwords use salted bcrypt hashing.</div>
              </div>
              <div className="rounded-xl border border-black/[0.06] bg-neutral-50 p-4 dark:border-white/[0.08] dark:bg-neutral-800">
                <div className="text-xs font-bold uppercase tracking-wider text-purple-500">Retention</div>
                <div className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">Data is retained while your account remains active or until you request deletion.</div>
              </div>
            </div>
          </section>

          {/* Section 7: Your Rights & Controls */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              7. Your Rights & Choices
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              You retain full authority over your personal information:
            </p>
            <ul className="list-inside list-disc space-y-2 text-sm text-neutral-600 dark:text-neutral-300 sm:text-base">
              <li><strong>Profile Updates:</strong> You can edit your display name, avatar, and account settings at any time in the app settings.</li>
              <li><strong>AI Draft Consent:</strong> You can enable or disable AI pre-send draft analysis whenever you wish.</li>
              <li><strong>Account Deletion:</strong> You can request full deletion of your account, message history, and uploaded media by contacting support.</li>
              <li><strong>Revoking Google Access:</strong> You can revoke Alignment Radar&#39;s access to your Google account at any time through your{' '}
                <a
                  href="https://myaccount.google.com/permissions"
                  target="_blank"
                  rel="noreferrer"
                  className="text-apple-blue underline hover:opacity-80"
                >
                  Google Account Security Settings
                </a>.
              </li>
            </ul>
          </section>

          {/* Section 8: Contact */}
          <section className="space-y-3 rounded-2xl border border-black/[0.06] bg-neutral-50 p-6 dark:border-white/[0.08] dark:bg-neutral-800/60">
            <h2 className="flex items-center gap-2 text-lg font-bold text-neutral-900 dark:text-white">
              <Mail className="h-5 w-5 text-apple-blue" />
              8. Contact Us
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300">
              If you have any questions, concerns, or privacy requests regarding this Privacy Policy or your personal data, please contact us at:
            </p>
            <div className="text-sm font-semibold text-neutral-800 dark:text-neutral-200">
              Email:{' '}
              <a
                href="mailto:privacy@alignmentradar.com"
                className="text-apple-blue underline hover:opacity-80"
              >
                privacy@alignmentradar.com
              </a>
              <span className="mx-2 text-neutral-300">•</span>
              Application:{' '}
              <a
                href="https://alingnment-radar-fdrx.vercel.app"
                className="text-apple-blue underline hover:opacity-80"
              >
                Alignment Radar
              </a>
            </div>
          </section>

        </div>
      </main>

      <LegalFooter />
    </div>
  )
}

