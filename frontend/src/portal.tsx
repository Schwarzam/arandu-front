import { FormEvent, useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Chart as ChartJS, Legend, LinearScale, PointElement, Tooltip } from 'chart.js'
import { Scatter } from 'react-chartjs-2'
import { BookOpen, CalendarDays, ChevronLeft, ChevronRight, Crosshair, LogIn, LogOut, RefreshCw, Search, X } from 'lucide-react'

ChartJS.register(LinearScale, PointElement, Tooltip, Legend)

type User = { username?: string; name?: string; email?: string }
type DayTotal = { day: string; detections: number }
type Document = { path: string; title: string; section: string }
type SearchObject = { dia_object_id: number; ra: number; dec: number; n_dia_sources?: number; separation_arcsec: number }
type Source = { dia_source_id: number; midpoint_mjd_tai: number; band?: string; psf_flux?: number }
type ObjectDetails = { object: SearchObject; sources: Source[] }
const weekDays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const api = async <T,>(url: string, init?: RequestInit): Promise<T> => { const response = await fetch(url, { credentials: 'include', ...init }); if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || `Request failed (${response.status})`) }; return response.status === 204 ? (undefined as T) : response.json() as Promise<T> }
const isoDate = (value: Date) => value.toISOString().slice(0, 10)
const monthLabel = (value: Date) => value.toLocaleDateString(undefined, { month: 'long', year: 'numeric', timeZone: 'UTC' })
const firstOfMonth = (value: Date) => new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), 1))
const plusMonths = (value: Date, count: number) => new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + count, 1))

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [username, setUsername] = useState(''), [password, setPassword] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(''); try { onLogin((await api<{ user: User }>('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) })).user) } catch (err) { setError(err instanceof Error ? err.message : 'Could not sign in.') } finally { setBusy(false) } }
  return <main className="login-shell"><form className="login-card" onSubmit={submit}><img src="/assets/logo.png" alt="Arandu" className="brand-logo" /><h1>Arandu Portal</h1><p>Sign in with your ADSS account to explore observing activity.</p><label>Username<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>{error && <p className="error">{error}</p>}<button disabled={busy}><LogIn size={17} /> {busy ? 'Signing in…' : 'Sign in'}</button></form></main>
}

function Calendar() {
  const [month, setMonth] = useState(firstOfMonth(new Date())), [totals, setTotals] = useState<Record<string, DayTotal>>({}), [loading, setLoading] = useState(false), [error, setError] = useState('')
  useEffect(() => { let cancelled = false, retry: number | undefined; const start = firstOfMonth(month), end = plusMonths(start, 1); const load = () => { setLoading(true); setError(''); api<{ days: DayTotal[]; pending: boolean }>(`/api/calendar?start=${isoDate(start)}&end=${isoDate(end)}`).then(result => { if (!cancelled) { setTotals(Object.fromEntries(result.days.map(day => [day.day, day]))); if (result.pending) retry = window.setTimeout(load, 3000) } }).catch(err => !cancelled && setError(err instanceof Error ? err.message : 'Could not load calendar data.')).finally(() => !cancelled && setLoading(false)) }; load(); return () => { cancelled = true; if (retry) window.clearTimeout(retry) } }, [month])
  const cells = useMemo(() => { const start = firstOfMonth(month), leading = start.getUTCDay(), days = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0)).getUTCDate(); return Array.from({ length: leading + days }, (_, index) => index < leading ? null : new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), index - leading + 1))) }, [month])
  const today = isoDate(new Date())
  return <section className="page"><div className="page-heading"><div><span className="eyebrow">Observing activity</span><h2>Calendar</h2><p>DIA source detections recorded each UTC day.</p></div><div className="calendar-controls"><button aria-label="Previous month" className="icon-button" onClick={() => setMonth(value => plusMonths(value, -1))}><ChevronLeft /></button><strong>{monthLabel(month)}</strong><button aria-label="Next month" className="icon-button" onClick={() => setMonth(value => plusMonths(value, 1))}><ChevronRight /></button></div></div>{error && <p className="error">{error}</p>}<div className="calendar" aria-busy={loading}>{weekDays.map(day => <div className="weekday" key={day}>{day}</div>)}{cells.map((day, i) => { if (!day) return <div className="calendar-cell blank" key={`blank-${i}`} />; const key = isoDate(day), total = totals[key]; return <article className={`calendar-cell ${key === today ? 'today' : ''}`} key={key}><time dateTime={key}>{day.getUTCDate()}</time>{loading ? <span className="loading-dot" /> : <div className="calendar-numbers"><span><b>{total?.detections ?? 0}</b> detections</span></div>}</article> })}</div><p className="calendar-note">The outlined day is today. Counts are refreshed daily by the server.</p></section>
}

function ObjectDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const [detail, setDetail] = useState<ObjectDetails | null>(null), [error, setError] = useState(''), [sourceId, setSourceId] = useState<number | null>(null)
  useEffect(() => { api<ObjectDetails>(`/api/objects/${id}`).then(result => { setDetail(result); setSourceId(result.sources.at(-1)?.dia_source_id ?? null) }).catch(err => setError(err instanceof Error ? err.message : 'Could not load this object.')) }, [id])
  const points = detail?.sources.filter(item => Number.isFinite(Number(item.psf_flux)) && Number.isFinite(Number(item.midpoint_mjd_tai))) ?? []
  const xValues = points.map(item => Number(item.midpoint_mjd_tai)), yValues = points.map(item => Number(item.psf_flux))
  const rawMinX = Math.min(...xValues), rawMaxX = Math.max(...xValues), rawMinY = Math.min(...yValues), rawMaxY = Math.max(...yValues)
  const xPadding = Math.max((rawMaxX - rawMinX) * 0.04, 0.01), yPadding = Math.max((rawMaxY - rawMinY) * 0.08, Math.abs(rawMaxY) * 0.03, 1)
  const minX = rawMinX - xPadding, maxX = rawMaxX + xPadding, minY = rawMinY - yPadding, maxY = rawMaxY + yPadding
  const colors: Record<string, string> = { u: '#6d5bd0', g: '#159da0', r: '#d65a4a', i: '#d49b20', z: '#8858b7', y: '#786d37' }
  const filterPalette = ['#159da0', '#d65a4a', '#6d5bd0', '#d49b20', '#8858b7', '#167c48', '#bd4f88', '#4c76ba', '#9b671f', '#268f94']
  const bands = [...new Set(points.map(item => (item.band ?? 'unknown').toLowerCase()))]
  const chartData = { datasets: bands.map((band, index) => ({ label: band, data: points.filter(item => (item.band ?? 'unknown').toLowerCase() === band).map(item => ({ x: Number(item.midpoint_mjd_tai), y: Number(item.psf_flux), sourceId: item.dia_source_id })), backgroundColor: colors[band] ?? filterPalette[index % filterPalette.length], pointRadius: 5, pointHoverRadius: 7 })) }
  const chartOptions = { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' as const }, tooltip: { callbacks: { label: (context: any) => `${context.dataset.label}: MJD ${Number(context.parsed.x).toFixed(5)}, flux ${Number(context.parsed.y).toFixed(3)}` } } }, scales: { x: { type: 'linear' as const, title: { display: true, text: 'MJD TAI' }, min: minX, max: maxX }, y: { title: { display: true, text: 'PSF flux' }, min: minY, max: maxY } } }
  const active = detail?.sources.find(item => item.dia_source_id === sourceId)
  return <div className="detail-backdrop" role="dialog" aria-modal="true"><section className="detail-panel"><button className="close-button" onClick={onClose} aria-label="Close details"><X /></button>{error && <p className="error">{error}</p>}{!detail && !error && <p>Loading object…</p>}{detail && <><span className="eyebrow">DIA object</span><h2>{detail.object.dia_object_id}</h2><p className="muted">RA {Number(detail.object.ra).toFixed(6)}° · Dec {Number(detail.object.dec).toFixed(6)}° · {detail.sources.length} detections</p><h3>PSF flux light curve</h3>{points.length ? <div className="lightcurve"><Scatter data={chartData} options={chartOptions} /></div> : <p className="muted">No usable flux points are available.</p>}<h3>Image cutouts</h3>{detail.sources.length ? <><label className="epoch-picker">Detection epoch<select value={sourceId ?? ''} onChange={e => setSourceId(Number(e.target.value))}>{detail.sources.map(item => <option key={item.dia_source_id} value={item.dia_source_id}>MJD {Number(item.midpoint_mjd_tai).toFixed(5)} {item.band ? `(${item.band})` : ''}</option>)}</select></label>{active && <div className="cutouts">{(['science', 'template', 'difference'] as const).map(kind => <figure key={kind}><img src={`/api/cutouts/${active.dia_source_id}/${kind}.png`} alt={`${kind} cutout`} /><figcaption>{kind}</figcaption></figure>)}</div>}</> : <p className="muted">No cutouts available.</p>}</>}</section></div>
}

function ConeSearch() {
  const [ra, setRa] = useState(''), [dec, setDec] = useState(''), [radius, setRadius] = useState('30'), [results, setResults] = useState<SearchObject[]>([]), [error, setError] = useState(''), [loading, setLoading] = useState(false), [objectId, setObjectId] = useState<number | null>(null)
  async function submit(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError(''); setResults([])
    try {
      const result = await api<{ objects: SearchObject[] }>('/api/search/cone', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ra: Number(ra), dec: Number(dec), radius_arcsec: Number(radius), limit: 100 }) })
      setResults(result.objects)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not complete the cone search.') } finally { setLoading(false) }
  }
  return <section className="page"><div className="page-heading"><div><span className="eyebrow">DIA object catalogue</span><h2>Cone search</h2><p>Find objects around a sky position using ICRS right ascension and declination.</p></div></div><form className="search-form" onSubmit={submit}><label>Right ascension (°)<input type="number" min="0" max="359.999999" step="any" placeholder="0–360" value={ra} onChange={e => setRa(e.target.value)} required /></label><label>Declination (°)<input type="number" min="-90" max="90" step="any" placeholder="−90–90" value={dec} onChange={e => setDec(e.target.value)} required /></label><label>Radius (arcsec)<input type="number" min="0.01" max="7200" step="any" value={radius} onChange={e => setRadius(e.target.value)} required /></label><button disabled={loading}><Search size={17} /> {loading ? 'Searching…' : 'Search'}</button></form>{error && <p className="error">{error}</p>}{results.length > 0 && <div className="result-table-wrap"><table><caption>{results.length} matching object — select an ID for its light curve and cutouts.</caption><thead><tr><th>Object ID</th><th>RA</th><th>Dec</th><th>Separation</th><th>Sources</th></tr></thead><tbody>{results.map(object => <tr key={object.dia_object_id} className="clickable-row" onClick={() => setObjectId(object.dia_object_id)}><td><button className="object-link">{object.dia_object_id}</button></td><td>{Number(object.ra).toFixed(6)}°</td><td>{Number(object.dec).toFixed(6)}°</td><td>{Number(object.separation_arcsec).toFixed(2)}″</td><td>{object.n_dia_sources ?? '—'}</td></tr>)}</tbody></table></div>}{!loading && !error && results.length === 0 && <div className="empty-results"><Crosshair size={25} /><p>Enter a position and radius to search the Arandu catalogue.</p></div>}{objectId !== null && <ObjectDetail id={objectId} onClose={() => setObjectId(null)} />}</section>
}

function Docs() {
  const [documents, setDocuments] = useState<Document[]>([]), [selected, setSelected] = useState(''), [markdown, setMarkdown] = useState(''), [error, setError] = useState('')
  useEffect(() => { api<{ documents: Document[] }>('/api/docs').then(({ documents }) => { setDocuments(documents); setSelected(documents[0]?.path ?? '') }).catch(err => setError(err instanceof Error ? err.message : 'Could not load documentation.')) }, [])
  useEffect(() => { if (!selected) return; setError(''); api<{ markdown: string }>(`/api/docs/${selected}`).then(result => setMarkdown(result.markdown)).catch(err => setError(err instanceof Error ? err.message : 'Could not load this document.')) }, [selected])
  const selectedDir = selected.includes('/') ? selected.slice(0, selected.lastIndexOf('/') + 1) : ''
  const assetUrl = (source?: string) => !source || /^(https?:|#|mailto:)/.test(source) ? source : source.endsWith('.md') ? undefined : `/api/docs-assets/${selectedDir}${source}`
  return <section className="page docs-page"><div className="page-heading"><div><span className="eyebrow">Repository documentation</span><h2>Documentation</h2><p>Markdown files under <code>docs/</code> are discovered and rendered automatically.</p></div><RefreshCw size={19} className="muted" /></div>{error && <p className="error">{error}</p>}<div className="docs-layout"><nav className="docs-nav" aria-label="Documentation"><div className="docs-nav-header"><p>Pages</p><span aria-label={`${documents.length} documents`}>{documents.length}</span></div><div className="docs-nav-list">{documents.map(document => <button key={document.path} className={selected === document.path ? 'active' : ''} onClick={() => setSelected(document.path)}><small>{document.section}</small><span>{document.title}</span></button>)}</div></nav><article className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: ({ src, alt }) => <img src={assetUrl(src)} alt={alt ?? ''} />, a: ({ href, children }) => href?.endsWith('.md') ? <button className="markdown-link" onClick={() => setSelected(`${selectedDir}${href}`)}>{children}</button> : <a href={assetUrl(href)}>{children}</a> }}>{markdown}</ReactMarkdown></article></div></section>
}

export default function App() {
  const [user, setUser] = useState<User | null>(null), [page, setPage] = useState<'calendar' | 'search' | 'docs'>('calendar'), [checking, setChecking] = useState(true)
  useEffect(() => { api<{ user: User }>('/api/auth/me').then(result => setUser(result.user)).catch(() => {}).finally(() => setChecking(false)) }, [])
  if (checking) return <main className="login-shell">Loading portal…</main>
  if (!user) return <Login onLogin={setUser} />
  async function logout() { await api('/api/auth/logout', { method: 'POST' }); setUser(null) }
  return <div className="app-shell"><header><img src="/assets/logo.png" alt="Arandu" className="header-logo" /><nav><button className={page === 'calendar' ? 'active' : ''} onClick={() => setPage('calendar')}><CalendarDays size={18} /> Calendar</button><button className={page === 'search' ? 'active' : ''} onClick={() => setPage('search')}><Search size={18} /> Cone search</button><button className={page === 'docs' ? 'active' : ''} onClick={() => setPage('docs')}><BookOpen size={18} /> Docs</button></nav><div className="user-menu"><span>{user.name || user.username || user.email || 'ADSS user'}</span><button className="icon-button" title="Sign out" onClick={logout}><LogOut size={18} /></button></div></header>{page === 'calendar' ? <Calendar /> : page === 'search' ? <ConeSearch /> : <Docs />}</div>
}
