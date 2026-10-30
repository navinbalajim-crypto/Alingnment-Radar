import React, { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { FileText, CheckSquare, AlertTriangle, ShieldCheck, HelpCircle, Mail } from 'lucide-react'
import { LegalNavbar } from './LegalNavbar'
import { LegalFooter } from './LegalFooter'

export function TermsOfServicePage() {
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
            <FileText className="h-3.5 w-3.5" />
            <span>Terms & Conditions</span>
          </div>
          <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-5xl">
            Terms of Service
          </h1>
          <p className="mt-3 text-sm text-neutral-500 dark:text-neutral-400 sm:text-base">
            Effective Date: October 30, 2026 • Version 1.2
          </p>
        </div>

        {/* Content Card */}
        <div className="space-y-10 rounded-3xl border border-black/[0.06] bg-white p-6 shadow-subtle sm:p-10 dark:border-white/[0.08] dark:bg-neutral-900">
          
          {/* Summary Box */}
          <section className="rounded-2xl border border-sky-200/60 bg-sky-50/50 p-5 dark:border-sky-500/20 dark:bg-sky-950/20">
            <h2 className="flex items-center gap-2 text-base font-bold text-sky-900 dark:text-sky-200">
              <CheckSquare className="h-5 w-5 text-sky-600 dark:text-sky-400" />
              Welcome to Alignment Radar
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-sky-800/90 dark:text-sky-300/90">
              These Terms of Service govern your access to and use of Alignment Radar, an AI-assisted real-time communication platform. By accessing or using our application, you agree to these terms. If you do not agree, please do not use our services.
            </p>
          </section>

          {/* Section 1: Acceptance */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              1. Acceptance of Terms
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              By accessing or using Alignment Radar via our website{' '}
              <a
                href="https://alingnment-radar-fdrx.vercel.app"
                target="_blank"
                rel="noreferrer"
                className="font-medium text-apple-blue underline hover:opacity-80"
              >
                https://alingnment-radar-fdrx.vercel.app
              </a>{' '}
              or related APIs, you enter into a legally binding agreement with Alignment Radar. You represent that you are at least 13 years of age (or the minimum legal age required in your jurisdiction) and have the full legal capacity to enter into these Terms.
            </p>
          </section>

          {/* Section 2: Description of Service */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              2. Description of the Service
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              Alignment Radar provides collaborative messaging tools, including:
            </p>
            <ul className="list-inside list-disc space-y-1.5 text-sm text-neutral-600 dark:text-neutral-300 sm:text-base">
              <li>Direct one-on-one and group real-time chat.</li>
              <li>Voice messaging with automated speech-to-text transcription.</li>
              <li>AI-powered alignment indicators, ambiguity detection, and draft clarification coaching.</li>
              <li>Secure account authentication via Google OAuth 2.0 or direct credential login.</li>
            </ul>
          </section>

          {/* Section 3: User Accounts & Google Sign-In */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              3. User Accounts & Google Sign-In
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              To use our messaging features, you must create an account. You agree to:
            </p>
            <ul className="list-inside list-disc space-y-2 text-sm text-neutral-600 dark:text-neutral-300 sm:text-base">
              <li>Provide accurate, current, and complete registration information.</li>
              <li>Maintain the security of your password or third-party authentication credentials.</li>
              <li>Notify us immediately of any unauthorized use or security breach related to your account.</li>
              <li>When signing in via Google, you grant us permission to access your basic profile information (name, email, and avatar) solely to set up and manage your profile in accordance with our{' '}
                <Link to="/privacy" className="text-apple-blue underline hover:opacity-80">
                  Privacy Policy
                </Link>.
              </li>
            </ul>
          </section>

          {/* Section 4: Acceptable Use */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              4. Acceptable Use Policy
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              You agree not to use the Service to:
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-red-200/60 bg-red-50/40 p-4 dark:border-red-500/20 dark:bg-red-950/20">
                <div className="text-xs font-bold uppercase tracking-wider text-red-600 dark:text-red-400">Prohibited Conduct</div>
                <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-red-800 dark:text-red-300">
                  <li>Harass, abuse, threaten, or defame other users.</li>
                  <li>Transmit hate speech or sexually explicit material.</li>
                  <li>Impersonate any individual, organization, or entity.</li>
                  <li>Distribute spam, unauthorized marketing, or chain letters.</li>
                </ul>
              </div>

              <div className="rounded-xl border border-red-200/60 bg-red-50/40 p-4 dark:border-red-500/20 dark:bg-red-950/20">
                <div className="text-xs font-bold uppercase tracking-wider text-red-600 dark:text-red-400">Technical Violations</div>
                <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-red-800 dark:text-red-300">
                  <li>Attempt to compromise or bypass server security measures.</li>
                  <li>Deploy bots, spiders, or automated scrapers without consent.</li>
                  <li>Upload viruses, trojans, or malicious attachments.</li>
                  <li>Interfere with network performance or socket infrastructure.</li>
                </ul>
              </div>
            </div>
          </section>

          {/* Section 5: AI Assistive Features & Disclaimer */}
          <section className="space-y-3 rounded-2xl border border-amber-200/80 bg-amber-50/60 p-5 dark:border-amber-500/20 dark:bg-amber-950/20">
            <h2 className="flex items-center gap-2 text-base font-bold text-amber-900 dark:text-amber-200">
              <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
              5. AI Features & Assistive Disclaimer
            </h2>
            <p className="text-sm leading-relaxed text-amber-900/90 dark:text-amber-200/90">
              Alignment Radar utilizes state-of-the-art machine learning models to provide communication feedback, alignment scoring, and speech transcriptions. By using these features, you acknowledge and agree:
            </p>
            <ul className="list-inside list-disc space-y-1.5 text-xs text-amber-800 dark:text-amber-300 sm:text-sm">
              <li><strong>Assistive Only:</strong> AI recommendations and transcripts are suggestive guidance, not professional, legal, medical, or contractual advice.</li>
              <li><strong>User Responsibility:</strong> You retain complete discretion and sole responsibility for reviewing, editing, and deciding what messages to send and how you interact with others.</li>
              <li><strong>Accuracy:</strong> While we strive for high precision, AI models may occasionally produce inaccurate transcripts or misinterpret context.</li>
            </ul>
          </section>

          {/* Section 6: Content Ownership */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              6. Content Ownership & License
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              <strong>Your Content:</strong> You retain full ownership and intellectual property rights in all messages, voice recordings, documents, and media that you submit. By transmitting content, you grant Alignment Radar a limited, non-exclusive license solely to host, transmit, transcode, and display the content as necessary to operate the service for you and your conversation participants.
            </p>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              <strong>Our Platform:</strong> The Alignment Radar brand, codebase, user interface, radar visualizations, and designs are protected by copyright and intellectual property laws and remain our exclusive property.
            </p>
          </section>

          {/* Section 7: Disclaimers & Limitation of Liability */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              7. Disclaimers & Limitation of Liability
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              THE SERVICE IS PROVIDED ON AN &quot;AS IS&quot; AND &quot;AS AVAILABLE&quot; BASIS WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, OR NON-INFRINGEMENT.
            </p>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              TO THE MAXIMUM EXTENT PERMITTED BY LAW, ALIGNMENT RADAR SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES ARISING OUT OF YOUR USE OF THE SERVICE, INCLUDING LOSS OF DATA, REPUTATION, OR BUSINESS OPPORTUNITIES.
            </p>
          </section>

          {/* Section 8: Termination */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              8. Termination
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              We reserve the right to suspend or terminate your account or access to the Service at any time, with or without notice, in the event of any violation of these Terms or behavior that harms other users or the platform. You may delete your account at any time by contacting our support team.
            </p>
          </section>

          {/* Section 9: Governing Law & Updates */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white sm:text-2xl">
              9. Governing Law & Modifications
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300 sm:text-base">
              We may modify these Terms of Service periodically to reflect changes in our service or legal obligations. We will notify users of material changes by updating the Effective Date. Your continued use of the Service following such updates signifies your acceptance of the revised Terms.
            </p>
          </section>

          {/* Section 10: Contact Us */}
          <section className="space-y-3 rounded-2xl border border-black/[0.06] bg-neutral-50 p-6 dark:border-white/[0.08] dark:bg-neutral-800/60">
            <h2 className="flex items-center gap-2 text-lg font-bold text-neutral-900 dark:text-white">
              <Mail className="h-5 w-5 text-apple-blue" />
              10. Contact Us
            </h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300">
              For any questions or inquiries regarding these Terms of Service, please contact our legal and support team:
            </p>
            <div className="text-sm font-semibold text-neutral-800 dark:text-neutral-200">
              Email:{' '}
              <a
                href="mailto:terms@alignmentradar.com"
                className="text-apple-blue underline hover:opacity-80"
              >
                terms@alignmentradar.com
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

