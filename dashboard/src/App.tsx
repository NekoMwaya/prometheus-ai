import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import {
  Globe, Mail, Zap, Shield, Eye, GitBranch, Bot, Search,
  CheckCircle2, XCircle, AlertTriangle, Loader2, ChevronDown,
  Activity, Sparkles, ArrowRight, RefreshCw, X
} from 'lucide-react'
import './App.css'

// ─── Types ────────────────────────────────────────────────────────────────────

type Phase = 'idle' | 'running' | 'complete'

interface Finding {
  id: number
  severity: 'critical' | 'high' | 'medium' | 'low'
  category: string
  title: string
  description: string
  fix: string
}

interface AgentState { status: 'pending' | 'active' | 'complete' | 'error'; message: string }

interface Pipeline {
  interface: AgentState; scraper: AgentState; visual: AgentState; github: AgentState;
}

interface SuiteResult {
  status: 'pass' | 'fail' | 'warning'
  checks_passed?: number; checks_total?: number
  pages_visited?: number; elements_tested?: number
}

interface Report {
  overall_score: number; verdict: string
  suites: Record<string, SuiteResult>
  findings: Finding[]
  pages_visited: number; elements_tested: number
}

interface Assessment {
  url: string; email: string; status: string
  logs: Array<{ agent: string; message: string; time: string }>
  pipeline: Pipeline; report: Report | null
}

// ─── Constants ────────────────────────────────────────────────────────────────

const SUITES = [
  { id: 'exploratory', name: 'Exploratory', icon: Search,       desc: 'Crawl pages, interact with every element, validate outcomes' },
  { id: 'user_flows',  name: 'User Flows',  icon: ArrowRight,   desc: 'Execute custom end-to-end journeys with screenshot evidence' },
  { id: 'prelaunch',   name: 'Prelaunch',   icon: CheckCircle2, desc: 'SEO, broken links, accessibility, mobile layout, meta tags' },
]

const AGENTS = [
  { id: 'interface', name: 'Orchestrator',  icon: Bot,       color: '#818cf8' },
  { id: 'scraper',   name: 'Scraper Agent', icon: Search,    color: '#22d3ee' },
  { id: 'visual',    name: 'Visual Agent',  icon: Eye,       color: '#c084fc' },
  { id: 'github',    name: 'GitHub Agent',  icon: GitBranch, color: '#4ade80' },
]

const SEV_CFG = {
  critical: { cls: 'sev-critical', label: 'Critical' },
  high:     { cls: 'sev-high',     label: 'High'     },
  medium:   { cls: 'sev-medium',   label: 'Medium'   },
  low:      { cls: 'sev-low',      label: 'Low'      },
}

const SUITE_LABELS: Record<string, string> = {
  exploratory: 'Exploratory Tests',
  user_flows:  'User Flow Tests',
  prelaunch:   'Prelaunch Checks',
}

function scoreColor(s: number) {
  if (s >= 80) return '#22c55e'
  if (s >= 60) return '#eab308'
  return '#ef4444'
}

function agentTag(name: string) {
  const n = name.toLowerCase()
  if (n.includes('interface') || n.includes('orchestrat')) return 'interface'
  if (n.includes('scraper') || n.includes('firecrawl'))   return 'scraper'
  if (n.includes('visual') || n.includes('playwright'))   return 'visual'
  if (n.includes('github'))                                return 'github'
  return 'system'
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  // Form
  const [url,   setUrl]   = useState('')
  const [email, setEmail] = useState('')
  const [suites, setSuites] = useState<string[]>(['exploratory', 'prelaunch'])
  const [flow,   setFlow]   = useState('')
  const [flowOpen, setFlowOpen] = useState(false)
  const [errMsg, setErrMsg] = useState('')

  // Session
  const [phase,     setPhase]     = useState<Phase>('idle')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [data,      setData]      = useState<Assessment | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Report UX
  const [sevFilter, setSevFilter] = useState<string>('all')
  const [expanded,  setExpanded]  = useState<Set<number>>(new Set())

  const logRef = useRef<HTMLDivElement>(null)

  // Auto-scroll logs
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [data?.logs.length])

  // Poll
  useEffect(() => {
    if (!sessionId || phase === 'complete') return
    const iv = setInterval(async () => {
      try {
        const r = await axios.get<Assessment>(`http://127.0.0.1:8000/api/status/${sessionId}`)
        setData(r.data)
        if (r.data.status === 'complete') { setPhase('complete'); clearInterval(iv) }
      } catch { /* ignore */ }
    }, 900)
    return () => clearInterval(iv)
  }, [sessionId, phase])

  const toggleSuite = (id: string) =>
    setSuites(p => p.includes(id) ? p.filter(s => s !== id) : [...p, id])

  const toggleFinding = (id: number) =>
    setExpanded(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n })

  const reset = () => {
    setPhase('idle'); setSessionId(null); setData(null); setUrl(''); setEmail('')
    setSevFilter('all'); setExpanded(new Set())
  }

  const handleSubmit = async () => {
    if (!url) { setErrMsg('Please enter a website or GitHub URL'); return }
    setErrMsg(''); setSubmitting(true)
    try {
      const r = await axios.post<{ session_id: string }>('http://127.0.0.1:8000/api/assess', {
        url, email, test_suites: suites, user_flow: flow,
      })
      setSessionId(r.data.session_id)
      setPhase('running')
    } catch {
      setErrMsg('Cannot connect to backend. Start the server: python backend/main.py')
    } finally {
      setSubmitting(false)
    }
  }

  const findings = data?.report?.findings ?? []
  const filtered = sevFilter === 'all' ? findings : findings.filter(f => f.severity === sevFilter)

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="app">
      {/* Atmosphere */}
      <div className="bg-mesh" />
      <div className="bg-grid" />

      {/* ── Header ── */}
      <header className="header">
        <div className="header-inner">
          <a className="logo" href="#">
            <span className="logo-glyph">🔮</span>
            <span className="logo-name">Prometheus <span>AI</span></span>
          </a>
          <div className="header-right">
            {phase !== 'idle' && (
              <button className="back-btn" onClick={reset}>
                <RefreshCw size={13} /> New analysis
              </button>
            )}
            <div className="live-badge"><span className="live-dot" /> Live</div>
          </div>
        </div>
      </header>

      {/* ── Hero (only on idle) ── */}
      {phase === 'idle' && (
        <section className="hero">
          <div className="hero-pill"><Sparkles size={13} /> Autonomous Browser Testing Agents</div>
          <h1 className="hero-title">
            Ship with<br /><span className="grad">Confidence</span>
          </h1>
          <p className="hero-sub">
            Point us at your URL. Our AI agents crawl every page, test every flow,
            and surface prelaunch issues — delivered to your inbox.
          </p>
          <div className="hero-stats">
            {[
              { v: '3',      l: 'AI Agents'    },
              { v: '12+',    l: 'Test Types'   },
              { v: '< 3 min',l: 'Avg Runtime'  },
            ].map(s => (
              <div key={s.l} className="h-stat">
                <span className="h-stat-val">{s.v}</span>
                <span className="h-stat-lbl">{s.l}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Input Form (only on idle) ── */}
      {phase === 'idle' && (
        <section className="input-section">
          <div className="input-card">
            <div className="input-glow" />

            <div className="input-row">
              <div className="field">
                <div className="field-lbl"><Globe size={13} /> Website or GitHub URL</div>
                <input
                  className="field-inp" type="url" value={url}
                  placeholder="https://your-site.com or github.com/org/repo"
                  onChange={e => setUrl(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                />
              </div>
              <div className="field">
                <div className="field-lbl"><Mail size={13} /> Notification Email <span style={{ color:'var(--text-3)', marginLeft:'.3rem', fontWeight:400 }}>(optional)</span></div>
                <input
                  className="field-inp" type="email" value={email}
                  placeholder="you@company.com"
                  onChange={e => setEmail(e.target.value)}
                />
              </div>
            </div>

            <div className="suite-section">
              <div className="suite-lbl"><Shield size={13} /> Select test suites</div>
              <div className="suite-grid">
                {SUITES.map(s => {
                  const Icon = s.icon; const on = suites.includes(s.id)
                  return (
                    <button key={s.id} className={`suite-card ${on ? 'on' : ''}`} onClick={() => toggleSuite(s.id)}>
                      <div className="suite-top">
                        <span className="suite-icon"><Icon size={16} /></span>
                        <span className={`suite-check ${on ? 'on' : ''}`}>✓</span>
                      </div>
                      <div className="suite-name">{s.name}</div>
                      <div className="suite-desc">{s.desc}</div>
                    </button>
                  )
                })}
              </div>
            </div>

            <button className="flow-toggle" onClick={() => setFlowOpen(v => !v)}>
              <ChevronDown size={13} className={flowOpen ? 'open' : ''} />
              Define custom user flows (optional)
            </button>
            {flowOpen && (
              <textarea
                className="flow-ta" rows={5} value={flow}
                placeholder={'Describe steps in plain language:\n1. Go to "/signup"\n2. Fill email, password, and submit\n3. Expect to see onboarding page with text "Create your first project"'}
                onChange={e => setFlow(e.target.value)}
              />
            )}

            {errMsg && (
              <div className="err-msg">
                <X size={13} style={{ display:'inline', marginRight:'.4rem' }} />{errMsg}
              </div>
            )}

            <div className="submit-row">
              <button className="run-btn" onClick={handleSubmit} disabled={submitting || !url}>
                {submitting ? <Loader2 size={18} className="spin" /> : <Zap size={18} />}
                {submitting ? 'Starting analysis…' : 'Run Analysis'}
              </button>
              {email && (
                <p className="email-note">
                  Results will be<br />emailed to <strong>{email}</strong>
                </p>
              )}
            </div>
          </div>
        </section>
      )}

      {/* ── Pipeline ── */}
      {phase !== 'idle' && data && (
        <section className="pipeline-section wrap">
          <div className="psec-header">
            <div className="psec-title">
              {phase === 'running'
                ? <><Activity size={15} className="pulse-ico" /> Assessment in Progress…</>
                : <><CheckCircle2 size={15} style={{ color:'var(--success)' }} /> Assessment Complete</>
              }
            </div>
          </div>
          <div className="psec-url"><Globe size={13} />{data.url}</div>

          <div className="agent-grid">
            {AGENTS.map(ag => {
              const state = data.pipeline[ag.id as keyof Pipeline]
              const st    = state?.status ?? 'pending'
              const Icon  = ag.icon
              return (
                <div key={ag.id} className={`agent-card st-${st}`}>
                  <div className="agent-icon-wrap">
                    {st === 'active'   ? <Loader2 size={20} className="spin" style={{ color: ag.color }} />
                     : st === 'complete' ? <CheckCircle2 size={20} style={{ color: 'var(--success)' }} />
                     : <Icon size={20} style={{ color: st === 'pending' ? 'var(--text-3)' : ag.color }} />}
                  </div>
                  <div className="agent-name">{ag.name}</div>
                  <div className="agent-msg">{state?.message ?? 'Waiting…'}</div>
                  <div className={`agent-dot dot-${st}`} />
                </div>
              )
            })}
          </div>

          {data.report && (
            <div className="stats-row">
              <span className="stat-pill"><Globe size={12} />{data.report.pages_visited} pages crawled</span>
              <span className="stat-pill"><Activity size={12} />{data.report.elements_tested} elements tested</span>
              <span className="stat-pill"><Shield size={12} />{data.report.findings.length} findings</span>
            </div>
          )}
        </section>
      )}

      {/* ── Log Feed ── */}
      {phase !== 'idle' && data && (
        <section className="log-section wrap">
          <div className="log-bar">
            <span className="log-bar-title">Live Agent Feed</span>
            <span className={`log-status-badge ${phase === 'running' ? 'rec' : ''}`}>
              {phase === 'running' ? '● Recording' : '◆ Complete'}
            </span>
          </div>
          <div className="log-body" ref={logRef}>
            {data.logs.map((l, i) => (
              <div key={i} className="log-entry">
                <span className={`log-tag tag-${agentTag(l.agent)}`}>{l.agent}</span>
                <span className="log-txt">{l.message}</span>
                <span className="log-ts">{l.time}</span>
              </div>
            ))}
            {phase === 'running' && (
              <div className="log-entry">
                <span className="log-tag tag-system">SYS</span>
                <span className="log-txt log-thinking">Processing…</span>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ── Report ── */}
      {phase === 'complete' && data?.report && (() => {
        const r = data.report
        const sc = scoreColor(r.overall_score)
        return (
          <section className="report-section wrap">
            {/* Score row */}
            <div className="report-hero">
              <div className="score-card">
                <div className="score-ring" style={{ '--sc': sc, '--pct': r.overall_score } as any}>
                  <div className="score-inner">
                    <span className="score-num" style={{ color: sc }}>{r.overall_score}</span>
                    <span className="score-denom">/ 100</span>
                  </div>
                </div>
                <div>
                  <div className="verdict">{r.verdict}</div>
                  <div className="verdict-sub">
                    {r.overall_score >= 80
                      ? 'Your site is launch‑ready.'
                      : r.overall_score >= 60
                      ? 'Some issues need attention before launch.'
                      : 'Critical issues detected. Do not launch yet.'}
                  </div>
                </div>
              </div>

              <div className="suites-col">
                {Object.entries(r.suites).map(([key, s]) => (
                  <div key={key} className={`suite-res ${s.status}`}>
                    <div className="suite-res-ico">
                      {s.status === 'pass'    ? <CheckCircle2 size={18} />
                       : s.status === 'fail'  ? <XCircle size={18} />
                       : <AlertTriangle size={18} />}
                    </div>
                    <div className="suite-res-name">{SUITE_LABELS[key] ?? key}</div>
                    {s.checks_passed !== undefined && s.checks_total !== undefined && (
                      <div className="suite-prog">
                        <div className="prog-bar">
                          <div className="prog-fill" style={{ width: `${(s.checks_passed / s.checks_total) * 100}%` }} />
                        </div>
                        <span>{s.checks_passed}/{s.checks_total}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Findings */}
            <div className="findings-card">
              <div className="findings-hdr">
                <h3>Findings</h3>
                <div className="sev-filters">
                  {(['all', 'critical', 'high', 'medium', 'low'] as const).map(sev => (
                    <button key={sev} className={`sev-btn ${sevFilter === sev ? 'active' : ''}`} onClick={() => setSevFilter(sev)}>
                      {sev === 'all' ? 'All' : SEV_CFG[sev].label}
                      {sev !== 'all' && (
                        <span className="sev-count">{findings.filter(f => f.severity === sev).length}</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              <div className="findings-list">
                {filtered.length === 0 ? (
                  <div className="no-findings"><CheckCircle2 size={24} style={{ color:'var(--success)' }} /> No findings for this severity</div>
                ) : filtered.map(f => {
                  const sc = SEV_CFG[f.severity]
                  const open = expanded.has(f.id)
                  return (
                    <div key={f.id} className="finding">
                      <div className="finding-hdr" onClick={() => toggleFinding(f.id)}>
                        <span className={`sev-badge ${sc.cls}`}>{sc.label}</span>
                        <span className="finding-cat">{f.category}</span>
                        <span className="finding-title">{f.title}</span>
                        <ChevronDown size={14} className={`finding-chevron ${open ? 'open' : ''}`} />
                      </div>
                      {open && (
                        <div className="finding-body">
                          <p className="finding-desc">{f.description}</p>
                          <div className="finding-fix">
                            <CheckCircle2 size={14} style={{ flexShrink:0, marginTop:'.15rem' }} />
                            <span><strong>Fix:</strong> {f.fix}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          </section>
        )
      })()}

      <footer className="footer">
        Prometheus AI — Built for the Band of Agents Hackathon 2026 &nbsp;·&nbsp; Multi-agent autonomous testing powered by Band.ai
      </footer>
    </div>
  )
}
