import { useEffect, useState, useMemo, useCallback, useRef, lazy, Suspense } from 'react'
import axios from 'axios'
import {
  Activity, Database, Radar, Server, Zap, Search, X, Layers, BarChart2, Users,
  Link as LinkIcon, Clock, CheckCircle2, XCircle, PieChart as PieChartIcon,
  Fingerprint, Globe, Filter, Download, Eye, Upload, Loader2
} from 'lucide-react'
const GraphView = lazy(() => import('./GraphView'))
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area, Legend } from 'recharts'

const API = import.meta.env.VITE_PLATFORM_API_URL || ''

const defang = (val: string): string => {
  if (!val) return val
  return val.replace(/\./g, '[.]').replace(/https?/gi, (m) => m.replace(/t/g, 'x'))
}

export default function App() {
  const [tab, setTab] = useState('overview')
  const [entities, setEntities] = useState<any[]>([])
  const [stats, setStats] = useState({ processed: 0, pending: 0, failed: 0, entities: 0, relations: 0, entity_types: {} as Record<string, number>, documents: 0, new: 0, known: 0, updated: 0, conflicting: 0, uncertain: 0 })
  const [feed, setFeed] = useState<any[]>([])
  const [docs, setDocs] = useState<any[]>([])
  const [graph, setGraph] = useState<any>({ nodes: [], links: [] })
  const [timeline, setTimeline] = useState<any>(null)
  const [selEntity, setSelEntity] = useState<any>(null)
  const [selDoc, setSelDoc] = useState<any>(null)
  const [search, setSearch] = useState('')
  const searchRef = useRef('')
  const [gFilter, setGFilter] = useState('ALL')
  const [graphQuery, setGraphQuery] = useState('')
  const [graphSearch, setGraphSearch] = useState('')
  const [graphSince, setGraphSince] = useState('')
  const [graphUntil, setGraphUntil] = useState('')
  const [graphLimit, setGraphLimit] = useState(200)
  const [graphOffset, setGraphOffset] = useState(0)
  const [graphFocus, setGraphFocus] = useState<any>(null)
  const [dFilter, setDFilter] = useState('ALL')
  const [loading, setLoading] = useState(false)

  const [system, setSystem] = useState<any>(null)
  const [error, setError] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [notice, setNotice] = useState('')
  const [showUpload, setShowUpload] = useState(false)
  const [uploadTitle, setUploadTitle] = useState('')
  const [uploadContent, setUploadContent] = useState('')
  const [uploadSource, setUploadSource] = useState('Manual Upload')
  const [uploadDate, setUploadDate] = useState('')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [docLimit] = useState(50)
  const [entityLimit] = useState(250)
  const [entityOffset, setEntityOffset] = useState(0)
  const [docOffset, setDocOffset] = useState(0)
  const requestRef = useRef<AbortController | null>(null)
  const graphKey = useRef('')
  const drawerRequest = useRef(0)

  const message = (err: any) => {
    const detail = err?.response?.data?.detail
    return typeof detail === 'string' ? detail : Array.isArray(detail)
      ? detail.map((d: any) => d.msg).join('; ') : 'Unable to reach the platform. Please retry.'
  }

  const load = useCallback(async (queryOverride?: string, polling = false) => {
    if (polling && (requestRef.current || document.hidden)) return
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    setRefreshing(true)
    setError('')
    const q = queryOverride !== undefined ? queryOverride : searchRef.current
    const jobs: Promise<void>[] = []
    const get = (path: string, update: (data: any) => void) => {
      jobs.push(axios.get(`${API}/api/v1/${path}`, { signal: controller.signal, timeout: 45000 })
        .then(r => { if (!controller.signal.aborted) update(r.data) })
        .catch(err => { if (!controller.signal.aborted) setError(message(err)) }))
    }
    get('system/status', setSystem)
    get('dashboard/stats', data => setStats(data.metrics))
    if (tab === 'overview' || tab === 'analytics') get('intelligence/feed', setFeed)
    const graphParams = new URLSearchParams({query: graphQuery, entity_type: gFilter,
      limit: String(graphLimit), offset: String(graphOffset)})
    if (graphSince) graphParams.set('since', graphSince)
    if (graphUntil) graphParams.set('until', graphUntil)
    if (graphFocus) graphParams.set('focus_id', graphFocus.id)
    if (tab === 'overview' || tab === 'graph') get(tab === 'graph' ? `graph/explore?${graphParams}` : 'graph', data => {
      const key = JSON.stringify(data)
      if (key !== graphKey.current) { graphKey.current = key; setGraph(data) }
    })
    if (tab === 'entities') get(`entities?limit=${entityLimit}&offset=${entityOffset}`, setEntities)
    if (tab === 'databanks') get(`documents?limit=${docLimit}&offset=${docOffset}${q ? '&query=' + encodeURIComponent(q) : ''}`, setDocs)
    await Promise.allSettled(jobs)
    if (requestRef.current === controller) {
      requestRef.current = null
      setRefreshing(false)
      setLastUpdated(new Date())
    }
  }, [tab, docLimit, entityLimit, entityOffset, docOffset, graphQuery, gFilter, graphSince, graphUntil, graphFocus, graphLimit, graphOffset])

  useEffect(() => {
    load()
    const interval = setInterval(() => load(undefined, true), 30000)
    return () => { clearInterval(interval); requestRef.current?.abort() }
  }, [load])

  const handleSearchSubmit = (event: any) => {
    if (event.key === 'Enter') {
      searchRef.current = search.trim()
      setDocOffset(0)
      setTab('databanks')
      if (tab === 'databanks') load(searchRef.current)
    }
  }

  const importReport = async (event: any) => {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      if (uploadFile) {
        const form = new FormData()
        form.append('file', uploadFile)
        form.append('source_name', uploadSource)
        if (uploadDate) form.append('published_at', uploadDate)
        await axios.post(`${API}/api/v1/upload-file`, form)
      } else {
        await axios.post(`${API}/api/v1/upload`, { title: uploadTitle, content: uploadContent,
          source_name: uploadSource, published_at: uploadDate || null })
      }
      setShowUpload(false); setUploadContent(''); setUploadTitle(''); setUploadFile(null)
      setNotice('Report submitted. Processing status appears in the document library.')
      setTab('databanks')
      if (tab === 'databanks') load()
    } catch (err) { setError(message(err)) }
    finally { setBusy(false) }
  }

  const collect = async () => {
    setBusy(true); setError('')
    try {
      const response = await axios.post(`${API}/api/v1/trigger-ingestion`)
      setNotice(response.data.message)
    } catch (err) { setError(message(err)) }
    finally { setBusy(false) }
  }

  const exportReport = async (kind: string, format: string) => {
    setBusy(true); setError('')
    try {
      const response = await axios.get(`${API}/api/v1/exports/${kind}`, { responseType: 'blob' })
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url; link.download = `openthreat-${kind}.${format.toLowerCase()}`
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch { setError('Export failed. Please check the platform connection and retry.') }
    finally { setBusy(false) }
  }

  const retryReport = async () => {
    if (!selDoc) return
    setBusy(true)
    try {
      await axios.post(`${API}/api/v1/documents/${selDoc.id}/retry`)
      await openDoc(selDoc.id)
      setNotice('Report queued for another processing attempt.'); load()
    } catch (err) { setError(message(err)) }
    finally { setBusy(false) }
  }

  const openEntity = useCallback(async (id: string, name: string, group: string) => {
    const request = ++drawerRequest.current
    setLoading(true)
    setSelEntity({ id, name, group })
    setTimeline(null) // Clear previous to prevent stale data flashing
    try {
      const r = await axios.get(`${API}/api/v1/intelligence/entity/${id}/timeline`)
      if (request === drawerRequest.current) setTimeline(r.data)
    } catch (e) { if (request === drawerRequest.current) { setError(message(e)); setTimeline({ timeline: [], context: 'Unable to load this entity profile.' }) } }
    if (request === drawerRequest.current) setLoading(false)
  }, [])

  const openDoc = async (id: string) => {
    try {
      const r = await axios.get(`${API}/api/v1/documents/${id}`)
      setSelDoc(r.data)
    } catch (e) { setError(message(e)) }
  }

  // --- computed ---
  const pie = useMemo(() => [
    { name: 'NEW', value: stats.new || 0, color: '#34d399' },
    { name: 'KNOWN', value: stats.known || 0, color: '#94a3b8' },
    { name: 'UPDATED', value: stats.updated || 0, color: '#818cf8' },
    { name: 'CONFLICTING', value: stats.conflicting || 0, color: '#f87171' },
    { name: 'UNCERTAIN', value: stats.uncertain || 0, color: '#fbbf24' }
  ].filter(d => d.value > 0), [stats])

  const typeCounts = useMemo(() => Object.entries(stats.entity_types || {}).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count), [stats])

  const entityTypes = useMemo(() => {
    const s = new Set<string>()
    Object.keys(stats.entity_types || {}).forEach(type => s.add(type))
    return Array.from(s).sort()
  }, [stats])

  const fNodes = useMemo(() => graph.nodes || [], [graph])
  const fLinks = useMemo(() => {
    const ids = new Set(fNodes.map((n: any) => n.id))
    return (graph.links || []).filter((l: any) => ids.has(l.source?.id || l.source) && ids.has(l.target?.id || l.target))
  }, [graph, fNodes])
  const filteredGraph = useMemo(() => ({ nodes: fNodes, links: fLinks }), [fNodes, fLinks])
  const fDir = useMemo(() => [...(dFilter === 'ALL' ? entities : entities.filter(e => e.type === dFilter))].sort((a, b) => b.relations - a.relations), [entities, dFilter])

  const color = (t: string) => {
    const m: Record<string, string> = { THREAT_ACTOR: '#ea580c', MALWARE: '#dc2626', TOOL: '#2563eb', VULNERABILITY: '#d97706', TECHNIQUE: '#7c3aed', ORGANIZATION: '#0d9488', OBSERVABLE: '#ec4899' }
    return m[t] || '#64748b'
  }

  const Badge = ({ type }: { type: string }) => (
    <span className="text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded-sm" style={{ color: color(type), backgroundColor: color(type) + '15', border: '1px solid ' + color(type) + '30' }}>
      {type.replace(/_/g, ' ')}
    </span>
  )

  // confidence area chart data from feed
  const confTrend = useMemo(() => {
    return (feed || []).slice(0, 60).reverse().map((f: any, i: number) => ({
      idx: i,
      confidence: f.confidence || 0,
      type: f.change_type || 'UNKNOWN'
    }))
  }, [feed])

  return (
    <div className="flex h-screen bg-[#09090b] text-slate-300 font-sans overflow-hidden">
      {/* SIDEBAR */}
      <div className="w-[180px] xl:w-[240px] bg-[#09090b] border-r border-white/[0.06] flex flex-col shrink-0">
        <div className="p-5 border-b border-white/[0.06] flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center"><Radar size={18} className="text-white" /></div>
          <div><h1 className="text-white font-bold text-sm tracking-tight" title="OpenThreat NLP: An NLP-Driven System for Semantic Correlation and Temporal Analysis of Cyber Threat Intelligence">OpenThreat NLP</h1></div>
        </div>
        <div className="p-3 flex-1 overflow-y-auto">
          <p className="text-[9px] text-slate-600 font-bold tracking-[0.2em] uppercase mb-3 px-3">Workspace</p>
          {[
            { id: 'overview', icon: Activity, label: 'Overview' },
            { id: 'analytics', icon: BarChart2, label: 'Analytics' },
            { id: 'graph', icon: Layers, label: 'Knowledge Graph' },
            { id: 'entities', icon: Users, label: 'Threat Directory' },
            { id: 'databanks', icon: Database, label: 'Databanks' }
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-[13px] font-medium mb-0.5 transition-all ${tab === t.id ? 'bg-white/[0.06] text-white' : 'text-slate-500 hover:text-slate-300 hover:bg-white/[0.03]'}`}>
              <t.icon size={15} strokeWidth={tab === t.id ? 2 : 1.5} /> {t.label}
            </button>
          ))}
          <p className="text-[9px] text-slate-600 font-bold tracking-[0.2em] uppercase mt-6 mb-3 px-3">System</p>
          <button onClick={() => setTab('integrations')} className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-[13px] font-medium mb-0.5 transition-all ${tab === 'integrations' ? 'bg-white/[0.06] text-white' : 'text-slate-500 hover:text-slate-300 hover:bg-white/[0.03]'}`}>
            <Globe size={15} strokeWidth={1.5} /> Data Sources
          </button>
          <button onClick={() => setTab('exports')} className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-[13px] font-medium mb-0.5 transition-all ${tab === 'exports' ? 'bg-white/[0.06] text-white' : 'text-slate-500 hover:text-slate-300 hover:bg-white/[0.03]'}`}>
            <Download size={15} strokeWidth={1.5} /> Export Reports
          </button>
        </div>
        <div className="p-4 border-t border-white/[0.06]">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-full bg-indigo-900/60 flex items-center justify-center text-[10px] font-bold text-indigo-300">A</div>
            <div><p className="text-xs font-medium text-slate-300">Analyst</p></div>
          </div>
        </div>
      </div>

      {/* MAIN */}
      <div className="flex-1 flex flex-col min-w-0 z-0 relative">
        {/* TOP BAR */}
        <div className="h-14 border-b border-white/[0.06] flex justify-between items-center px-6 shrink-0 relative z-10 bg-[#09090b]">
          <div className="flex items-center gap-5">
            <h2 className="text-[15px] text-white font-semibold capitalize">{tab === 'entities' ? 'Threat Directory' : tab === 'integrations' ? 'Data Sources' : tab === 'exports' ? 'Export Reports' : tab}</h2>
            <div className="h-4 w-px bg-white/10"></div>
            <div className="flex items-center gap-4 text-[11px] text-slate-500">
              <span className="flex items-center gap-1"><Server size={12} /> NLP: <span className={system?.nlp?.ready ? "text-emerald-500" : "text-amber-400"}>{system?.nlp?.ready ? "Ready" : system?.nlp?.status || "Checking"}</span></span>
              <span className="flex items-center gap-1"><Database size={12} /> Search: <span className={system?.qdrant === "online" ? "text-emerald-500" : "text-amber-400"}>{system?.qdrant || "Checking"}</span></span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => setShowUpload(true)} className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-md text-[11px] font-medium"><Upload size={12}/> Import Report</button>
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-600" />
              <input type="text" placeholder="Search and press Enter..." value={search} onChange={e => setSearch(e.target.value)} onKeyDown={handleSearchSubmit} className="bg-white/[0.04] border border-white/[0.08] text-[13px] rounded-md pl-8 pr-3 py-1.5 w-60 text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50" />
            </div>
            <button disabled={refreshing} onClick={() => load()} className="flex items-center gap-1.5 bg-white/[0.04] border border-white/[0.08] text-slate-300 px-3 py-1.5 rounded-md text-[11px] font-medium hover:bg-white/[0.08] transition-colors"><Zap size={12} className={refreshing ? "text-indigo-400 animate-pulse" : "text-indigo-400"} /> {refreshing ? "Refreshing" : "Refresh"}</button>
          </div>
        </div>

        <div className="flex-1 overflow-auto">
          <div className="p-6 max-w-[1500px] mx-auto">
          {error && <div role="alert" className="mb-4 p-3 rounded-lg border border-red-500/20 bg-red-500/10 text-sm text-red-300 flex justify-between gap-4"><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error"><X size={16}/></button></div>}
          {notice && <div role="status" className="mb-4 p-3 rounded-lg border border-indigo-500/20 bg-indigo-500/10 text-sm text-indigo-300 flex justify-between gap-4"><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Dismiss notification"><X size={16}/></button></div>}


          {/* ===== OVERVIEW ===== */}
          {tab === 'overview' && <>
            <p className="text-xs text-slate-500 mb-4">{stats.pending} reports queued or processing · {stats.failed} failed · {lastUpdated ? `Last checked ${lastUpdated.toLocaleTimeString()}` : 'Connecting to the platform'}</p>
            <div className="grid grid-cols-3 xl:grid-cols-6 gap-3 mb-6">
              {[
                { l: 'Processed', v: stats.processed },
                { l: 'New Intel', v: stats.new, c: 'text-emerald-400' },
                { l: 'Known', v: stats.known },
                { l: 'Updated', v: stats.updated, c: 'text-indigo-400' },
                { l: 'Conflicts', v: stats.conflicting, c: 'text-red-400' },
                { l: 'Uncertain', v: stats.uncertain, c: 'text-amber-400' }
              ].map((s, i) => (
                <div key={i} className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-4">
                  <p className="text-[11px] text-slate-500 mb-1">{s.l}</p>
                  <p className={`text-xl font-bold ${s.c || 'text-white'}`}>{(s.v || 0).toLocaleString()}</p>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-5 gap-4" style={{ height: '520px' }}>
              <div className="col-span-3 bg-white/[0.03] border border-white/[0.06] rounded-lg flex flex-col overflow-hidden">
                <div className="px-4 py-3 border-b border-white/[0.06] flex justify-between items-center z-10 relative bg-[#09090b]/50 backdrop-blur">
                  <h3 className="text-[13px] text-white font-medium flex items-center gap-2"><Layers size={14} className="text-indigo-500" /> Knowledge Graph <span className="text-[10px] text-slate-500">({graph.nodes?.length || 0} of {graph.total_entities || 0} entities)</span></h3>
                  <button onClick={() => setTab('graph')} className="text-[11px] text-indigo-400 hover:text-indigo-300">Expand</button>
                </div>
                <div className="flex-1 relative">
                  <Suspense fallback={<p className="p-5 text-sm text-slate-500">Loading graph…</p>}><GraphView data={graph} onSelect={openEntity} /></Suspense>
                </div>
              </div>
              <div className="col-span-2 bg-white/[0.03] border border-white/[0.06] rounded-lg flex flex-col overflow-hidden">
                <div className="px-4 py-3 border-b border-white/[0.06]">
                  <h3 className="text-[13px] text-white font-medium flex items-center gap-2"><Activity size={14} className="text-indigo-500" /> Live Intelligence Feed</h3>
                </div>
                <div className="flex-1 overflow-y-auto p-3 space-y-2">
                  {feed.length === 0 && <p className="text-center text-slate-600 text-sm mt-10">Awaiting data...</p>}
                  {feed.slice(0, 30).map((f, i) => (
                    <div key={i} className="bg-white/[0.02] border border-white/[0.05] p-3 rounded-md">
                      <div className="flex justify-between items-start mb-1">
                        <span className={`text-[9px] font-bold tracking-wider uppercase px-1.5 py-0.5 rounded ${f.change_type === 'NEW' ? 'bg-emerald-500/10 text-emerald-400' : f.change_type === 'CONFLICTING' ? 'bg-red-500/10 text-red-400' : 'bg-white/[0.05] text-slate-400'}`}>{f.change_type}</span>
                        <span className="text-[10px] text-slate-600">{f.timestamp ? new Date(f.timestamp).toLocaleTimeString() : ''}</span>
                      </div>
                      <p className="text-[12px] text-slate-300 leading-snug">{f.description || 'Intelligence processed'}</p>
                      <div className="mt-1.5 flex items-center gap-2">
                        <span className="text-[9px] text-slate-600 bg-white/[0.04] px-1.5 py-0.5 rounded font-mono">{f.entity_type}</span>
                        {f.confidence != null && <span className="text-[9px] text-slate-600 font-mono">{(f.confidence * 100).toFixed(0)}%</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>}

          {/* ===== ANALYTICS ===== */}
          {tab === 'analytics' && <>
            <div className="grid grid-cols-4 gap-3 mb-6">
              {[
                { l: 'Total Entities', v: stats.entities, c: 'text-indigo-400' },
                { l: 'Pending Reports', v: stats.pending },
                { l: 'Active Relations', v: stats.relations },
                { l: 'Documents', v: stats.documents }
              ].map((s, i) => (
                <div key={i} className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-4">
                  <p className="text-[11px] text-slate-500 mb-1">{s.l}</p>
                  <p className={`text-xl font-bold ${s.c || 'text-white'}`}>{(s.v || 0).toLocaleString()}</p>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="col-span-2 bg-white/[0.03] border border-white/[0.06] rounded-lg p-5" style={{ height: 300 }}>
                <h3 className="text-[13px] text-white font-medium mb-4 flex items-center gap-2"><BarChart2 size={14} className="text-indigo-500" /> Extraction Scores (Recent Feed Entries)</h3>
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={confTrend} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                    <defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} /><stop offset="95%" stopColor="#6366f1" stopOpacity={0} /></linearGradient></defs>
                    <XAxis dataKey="idx" hide />
                    <YAxis tick={{ fill: '#475569', fontSize: 10 }} axisLine={false} tickLine={false} domain={[0, 1]} tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} />
                    <Tooltip contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: 6, fontSize: 12 }} formatter={(v: any) => [`${(v * 100).toFixed(1)}%`, 'Confidence']} />
                    <Area type="monotone" dataKey="confidence" stroke="#6366f1" strokeWidth={1.5} fill="url(#cg)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-5" style={{ height: 300 }}>
                <h3 className="text-[13px] text-white font-medium mb-4 flex items-center gap-2"><PieChartIcon size={14} className="text-indigo-500" /> Novelty Distribution</h3>
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={pie} cx="50%" cy="45%" innerRadius={55} outerRadius={80} paddingAngle={2} dataKey="value" stroke="none">
                      {pie.map((e, i) => <Cell key={i} fill={e.color} />)}
                    </Pie>
                    <Tooltip contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: 6, fontSize: 12 }} />
                    <Legend verticalAlign="bottom" height={30} iconType="circle" wrapperStyle={{ fontSize: 10 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-5" style={{ height: 350 }}>
                <h3 className="text-[13px] text-white font-medium mb-4 flex items-center gap-2"><Layers size={14} className="text-indigo-500" /> Entity Composition</h3>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={typeCounts} layout="vertical" margin={{ top: 0, right: 20, left: 10, bottom: 0 }}>
                    <XAxis type="number" hide />
                    <YAxis dataKey="name" type="category" tick={{ fill: '#94a3b8', fontSize: 11 }} width={110} axisLine={false} tickLine={false} />
                    <Tooltip cursor={{ fill: 'rgba(255,255,255,0.03)' }} contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: 6, fontSize: 12 }} />
                    <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={18}>
                      {typeCounts.map((e, i) => <Cell key={i} fill={color(e.name)} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-5" style={{ height: 350 }}>
                <h3 className="text-[13px] text-white font-medium mb-4 flex items-center gap-2"><Activity size={14} className="text-indigo-500" /> Recent Extraction Scores by Class</h3>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={pie.map(p => ({
                    name: p.name,
                    avg: feed.filter(f => f.change_type === p.name).reduce((s, f) => s + (f.confidence || 0), 0) / (feed.filter(f => f.change_type === p.name).length || 1)
                  }))} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} axisLine={false} tickLine={false} domain={[0, 1]} tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} />
                    <Tooltip cursor={{ fill: 'rgba(255,255,255,0.03)' }} contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: 6, fontSize: 12 }} formatter={(v: any) => [`${(v * 100).toFixed(1)}%`, 'Avg Confidence']} />
                    <Bar dataKey="avg" fill="#818cf8" radius={[4, 4, 0, 0]} barSize={32} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </>}

          {/* ===== KNOWLEDGE GRAPH ===== */}
          {tab === 'graph' && (
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl overflow-hidden flex flex-col" style={{ height: 'calc(100vh - 130px)', minHeight: 480 }}>
              <div className="order-3 flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.08] bg-[#0c0c10] px-4 py-3 text-xs text-slate-400">
                <div className="space-y-1">
                <span>{refreshing ? 'Updating…' : `${graph.nodes?.length || 0} displayed · ${graph.total_matches ?? 0} matching ${graphFocus ? 'neighbors' : 'entities'} · ${graph.total_entities || 0} total`}</span>
                <p className="text-[10px] text-slate-500">From result {graph.total_matches ? graphOffset + 1 : 0} · Positive active relations · Amber edges require review{graph.links_truncated ? ' · Edge limit reached; narrow your view' : ''}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                <button disabled={refreshing || !graph.has_more || graphLimit >= 1000} onClick={() => setGraphLimit(v => Math.min(1000, v + 200))} className="rounded-md border border-indigo-400/25 bg-indigo-500/10 px-3 py-2 text-indigo-300 hover:bg-indigo-500/20 disabled:opacity-30 disabled:cursor-not-allowed">Load 200 more</button>
                <button disabled={refreshing || graphOffset === 0} onClick={() => setGraphOffset(v => Math.max(0, v - graphLimit))} className="rounded-md border border-white/10 px-3 py-2 hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed">Previous page</button>
                <button disabled={refreshing || !graph.has_more} onClick={() => setGraphOffset(v => v + graphLimit)} className="rounded-md border border-white/10 px-3 py-2 hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed">Next page</button>
                </div>
              </div>
              <div className="order-1 space-y-3 bg-[#0c0c10] px-4 py-4 border-b border-white/[0.08]">
                <div><h3 className="text-sm font-semibold text-white">Explore intelligence connections</h3><p className="mt-1 text-xs text-slate-500">Search your entire knowledge base, then explore an entity's connections.</p></div>
                <form className="flex flex-wrap items-end gap-3 text-xs" onSubmit={e => { e.preventDefault(); setGraphOffset(0); setGraphLimit(200); setGraphQuery(graphSearch.trim()) }}>
                  <label className="flex-1 min-w-52 text-slate-400">Entity name or alias<input aria-label="Search all graph entities and aliases" placeholder="Search across all stored entities…" value={graphSearch} onChange={e => setGraphSearch(e.target.value)} className="block mt-1.5 w-full border border-white/10 bg-white/5 rounded-md px-3 py-2 text-white focus:outline-none focus:border-indigo-400" /></label>
                  <button className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-md px-4 py-2 border border-indigo-500">Search</button>
                  <label className="text-slate-400">Last seen from<input aria-label="Last seen from" type="date" value={graphSince} onChange={e => { setGraphOffset(0); setGraphSince(e.target.value) }} className="block mt-1.5 border border-white/10 bg-white/5 text-white rounded-md px-2 py-2 [color-scheme:dark]" /></label>
                  <label className="text-slate-400">Last seen to<input aria-label="Last seen to" type="date" value={graphUntil} onChange={e => { setGraphOffset(0); setGraphUntil(e.target.value) }} className="block mt-1.5 border border-white/10 bg-white/5 text-white rounded-md px-2 py-2 [color-scheme:dark]" /></label>
                  <button type="button" onClick={() => { setGraphSearch(''); setGraphQuery(''); setGraphSince(''); setGraphUntil(''); setGFilter('ALL'); setGraphFocus(null); setGraphOffset(0); setGraphLimit(200) }} className="rounded-md border border-white/10 px-3 py-2 text-slate-300 hover:bg-white/5">Reset</button>
                </form>
                {graphFocus && <p className="rounded-md bg-indigo-500/10 border border-indigo-500/20 px-3 py-2 text-xs text-indigo-300">Neighbors of {graphFocus.name} · The center entity remains visible when filtering.</p>}
                <div className="flex flex-wrap gap-1.5">
                {['ALL', ...entityTypes].map(f => (
                  <button key={f} onClick={() => { setGraphOffset(0); setGraphLimit(200); setGFilter(f) }} className={`text-[10px] font-semibold px-2.5 py-1 rounded transition-colors ${gFilter === f ? 'bg-indigo-500 text-white' : 'text-slate-400 hover:bg-white/[0.06]'}`}>
                    {f.replace(/_/g, ' ')}
                  </button>
                ))}
                </div>
              </div>
              <div className="relative order-2 flex-1 min-h-48"><Suspense fallback={<p className="p-5 text-sm text-slate-500">Loading graph…</p>}><GraphView data={filteredGraph} onSelect={openEntity} /></Suspense></div>
            </div>
          )}

          {/* ===== THREAT DIRECTORY ===== */}
          {tab === 'entities' && (
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-lg overflow-hidden flex flex-col" style={{ height: 'calc(100vh - 130px)' }}>
              <div className="px-4 py-3 border-b border-white/[0.06] flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <Filter size={14} className="text-slate-500" />
                  {['ALL', ...entityTypes].map(f => (
                    <button key={f} onClick={() => setDFilter(f)} className={`text-[10px] font-semibold px-2.5 py-1 rounded transition-colors ${dFilter === f ? 'bg-white/[0.08] text-indigo-400' : 'text-slate-500 hover:text-slate-300'}`}>
                      {f.replace(/_/g, ' ')}
                    </button>
                  ))}
                </div>
                <span className="text-[11px] text-slate-500 font-mono">{fDir.length} shown / {stats.entities} total</span>
              </div>
              <div className="flex-1 overflow-y-auto">
                <table className="w-full text-left">
                  <thead className="sticky top-0 bg-[#0f0f11] z-10 border-b border-white/[0.06]">
                    <tr>
                      <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Entity</th>
                      <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Type</th>
                      <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Confidence</th>
                      <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">First Seen</th>
                      <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider text-right">Active Relations</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    {fDir.map((e: any, i: number) => (
                      <tr key={i} onClick={() => openEntity(e.id, e.name, e.type)} className="hover:bg-white/[0.03] cursor-pointer transition-colors group">
                        <td className="px-5 py-3"><span className="text-[13px] font-medium text-slate-200 group-hover:text-indigo-400 transition-colors">{e.name}</span></td>
                        <td className="px-5 py-3"><Badge type={e.type} /></td>
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-20 h-1 bg-white/[0.06] rounded-full overflow-hidden"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${(e.confidence || 0) * 100}%` }}></div></div>
                            <span className="text-[11px] text-slate-500 font-mono">{((e.confidence || 0) * 100).toFixed(0)}%</span>
                          </div>
                        </td>
                        <td className="px-5 py-3 text-[11px] text-slate-500">{e.first_seen_at ? new Date(e.first_seen_at).toLocaleDateString() : '-'}</td>
                        <td className="px-5 py-3 text-right"><span className="text-[13px] font-semibold text-slate-400 group-hover:text-indigo-400">{e.relations || 0}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between px-5 py-3 text-sm text-indigo-400"><button disabled={!entityOffset || refreshing} onClick={() => setEntityOffset(v => Math.max(0, v - entityLimit))}>Previous</button><span className="text-xs text-slate-500">Page {Math.floor(entityOffset / entityLimit) + 1} · Filters apply to this page</span><button disabled={entities.length < entityLimit || refreshing} onClick={() => setEntityOffset(v => v + entityLimit)}>Next</button></div>
            </div>
          )}

          {/* ===== DATABANKS ===== */}
          {tab === 'databanks' && (
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-lg overflow-hidden flex flex-col" style={{ height: 'calc(100vh - 130px)' }}>
              <div className="px-4 py-3 border-b border-white/[0.06] flex justify-between items-center">
                <h3 className="text-[13px] text-white font-medium flex items-center gap-2"><Database size={14} className="text-indigo-500" /> Intelligence Documents</h3>
              </div>
              <div className="flex-1 overflow-y-auto">
                <table className="w-full text-left">
                  <thead className="sticky top-0 bg-[#0f0f11] z-10 border-b border-white/[0.06]">
                    <tr>
                      <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Document</th>
                      <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider text-center">Status</th>
                      <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider text-center">Ingested</th>
                      <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider text-right">Similarity</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    {docs.map((d: any, i: number) => (
                      <tr key={i} onClick={() => openDoc(d.id)} className="hover:bg-white/[0.03] cursor-pointer transition-colors group">
                        <td className="px-5 py-3"><p className="text-[13px] text-slate-200 group-hover:text-indigo-400 transition-colors truncate max-w-[500px]">{d.title}</p></td>
                        <td className="px-5 py-3 text-center">
                          <span className={`inline-flex items-center gap-1 text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded ${d.status === 'COMPLETED' ? 'bg-emerald-500/10 text-emerald-400' : d.status === 'FAILED' ? 'bg-red-500/10 text-red-400' : 'bg-amber-500/10 text-amber-400'}`}>
                            {d.status === 'COMPLETED' ? <CheckCircle2 size={10} /> : d.status === 'FAILED' ? <XCircle size={10} /> : <Clock size={10} />}
                            {d.status || 'PENDING'}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-center text-[11px] text-slate-500">{d.date ? new Date(d.date).toLocaleDateString() : '-'}</td>
                        <td className="px-5 py-3 text-right">
                          {d.score != null ? (
                            <span className="text-[12px] font-mono text-indigo-400">{(d.score * 100).toFixed(1)}%</span>
                          ) : <span className="text-[11px] text-slate-600">N/A</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!searchRef.current && <div className="flex items-center justify-between px-5 py-3 text-sm text-indigo-400"><button disabled={!docOffset || refreshing} onClick={() => setDocOffset(v => Math.max(0, v - docLimit))}>Previous</button><span className="text-xs text-slate-500">Page {Math.floor(docOffset / docLimit) + 1}</span><button disabled={docs.length < docLimit || refreshing} onClick={() => setDocOffset(v => v + docLimit)}>Next</button></div>}
              {docs.length === 0 && <p className="p-5 text-sm text-slate-500">{refreshing ? 'Loading reports…' : 'No reports found. Import a report or collect the latest sources.'}</p>}
            </div>
          )}

          {/* ===== DATA SOURCES ===== */}
          {tab === 'integrations' && (
            <div className="space-y-4">
              <p className="text-[13px] text-slate-400 mb-4">Collectors check public sources periodically. Status reflects the last collection attempt.</p>
              <button disabled={busy} onClick={collect} className="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-md text-sm">{busy ? 'Requesting…' : 'Collect Latest Reports'}</button>
              {[
                { name: 'NVD (National Vulnerability Database)', type: 'REST API', key: 'NVDCollector', desc: 'Recent CVE descriptions from the NIST NVD API.' },
                { name: 'CISA Known Exploited Vulnerabilities', type: 'JSON Feed', key: 'CISACollector', desc: 'Exploitation context from the CISA KEV catalog.' },
                { name: 'Threat Intelligence RSS Feeds', type: 'RSS', key: 'RSSCollector', desc: 'BleepingComputer, The Hacker News, and KrebsOnSecurity.' },
                { name: 'Semantic Search', type: 'Vector Store', key: 'qdrant', desc: 'Document similarity search. Individual report indexing status is shown in the library.' }
              ].map((src, i) => (
                <div key={i} className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-5 flex justify-between items-start">
                  <div>
                    <h4 className="text-[14px] text-white font-medium mb-1">{src.name}</h4>
                    <p className="text-[12px] text-slate-400 mb-2">{src.desc}</p>
                    <span className="text-[9px] font-bold tracking-wider uppercase bg-white/[0.04] text-slate-500 px-2 py-0.5 rounded">{src.type}</span>
                  </div>
                  <span className="text-[10px] font-bold tracking-wider uppercase bg-white/[0.04] text-slate-400 px-2 py-0.5 rounded flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-500 inline-block"></span> {src.key === "qdrant" ? system?.qdrant || "Checking" : system?.collectors?.[src.key]?.status || "Not checked"}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* ===== EXPORT REPORTS ===== */}
          {tab === 'exports' && (
            <div className="space-y-4">
              <p className="text-[13px] text-slate-400 mb-4">Generate and download intelligence reports from the platform.</p>
              {[
                { name: 'Entity Summary Report', desc: 'All extracted entities with confidence scores, types, and first-seen dates.', fmt: 'CSV', kind: 'entities' },
                { name: 'Relationship Graph Export', desc: 'Full knowledge graph data including all nodes and edges.', fmt: 'JSON', kind: 'graph' },
                { name: 'Intelligence Feed Log', desc: 'Complete classification audit with reasons and source document identifiers.', fmt: 'CSV', kind: 'feed' },
                { name: 'STIX 2.1 Bundle', desc: 'Supported entities and confirmed positive relationships in STIX 2.1. Observables, uncertain facts, and disputed relationships are excluded.', fmt: 'JSON', kind: 'stix' }
              ].map((r, i) => (
                <div key={i} className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-5 flex justify-between items-center">
                  <div>
                    <h4 className="text-[14px] text-white font-medium mb-1">{r.name}</h4>
                    <p className="text-[12px] text-slate-400">{r.desc}</p>
                  </div>
                  <button disabled={busy} onClick={() => exportReport(r.kind, r.fmt)} className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-[11px] font-semibold px-3 py-1.5 rounded transition-colors">
                    <Download size={12} /> Export {r.fmt}
                  </button>
                </div>
              ))}
            </div>
          )}

          </div>
        </div>
      </div>

      {showUpload && <div className="fixed inset-0 bg-black/70 z-[300] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="import-title">
        <form onSubmit={importReport} className="w-full max-w-xl bg-[#111114] border border-white/10 rounded-xl p-6 space-y-4 max-h-[90vh] overflow-auto">
          <div className="flex justify-between items-center"><h2 id="import-title" className="text-lg">Import Threat Report</h2><button type="button" onClick={() => setShowUpload(false)} aria-label="Close import"><X size={18}/></button></div>
          <p className="text-xs text-slate-500">Upload a PDF, text, Markdown, or HTML report (up to 10 MB), or paste report text. Scanned PDFs require OCR.</p>
          <label className="block text-xs text-slate-400">Report file<input type="file" accept=".pdf,.txt,.md,.html,.htm" onChange={e => setUploadFile(e.target.files?.[0] || null)} className="block w-full mt-2 text-sm"/></label>
          {!uploadFile && <><label className="block text-xs text-slate-400">Title<input required value={uploadTitle} maxLength={300} onChange={e => setUploadTitle(e.target.value)} className="block w-full mt-1 bg-white/5 rounded border border-white/10 p-2 text-sm"/></label>
          <label className="block text-xs text-slate-400">Report text<textarea required value={uploadContent} maxLength={500000} onChange={e => setUploadContent(e.target.value)} rows={7} className="block w-full mt-1 bg-white/5 rounded border border-white/10 p-2 text-sm"/></label></>}
          <div className="grid grid-cols-2 gap-3"><label className="text-xs text-slate-400">Source name<input required maxLength={200} value={uploadSource} onChange={e => setUploadSource(e.target.value)} className="block w-full mt-1 bg-white/5 rounded border border-white/10 p-2 text-sm"/></label>
          <label className="text-xs text-slate-400">Publication date (optional)<input type="date" value={uploadDate} onChange={e => setUploadDate(e.target.value)} className="block w-full mt-1 bg-white/5 rounded border border-white/10 p-2 text-sm"/></label></div>
          {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
          <button disabled={busy} className="w-full flex justify-center items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md p-2 text-sm">{busy && <Loader2 size={14} className="animate-spin"/>}{busy ? 'Submitting…' : 'Analyze Report'}</button>
        </form>
      </div>}
      {/* ===== DOCUMENT DRAWER ===== */}
      {selDoc && (
        <div className="fixed inset-y-0 right-0 w-full max-w-[800px] bg-[#0c0c0e]/98 backdrop-blur-xl border-l border-white/[0.08] z-[200] flex flex-col shadow-2xl">
          <div className="p-5 border-b border-white/[0.06] flex justify-between items-start">
            <div className="min-w-0 flex-1 mr-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[9px] font-bold tracking-wider uppercase bg-white/[0.06] text-slate-400 px-2 py-0.5 rounded">Document</span>
                <span className={`text-[9px] font-bold tracking-wider uppercase px-2 py-0.5 rounded ${(selDoc.status || 'PENDING') === 'COMPLETED' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'}`}>{selDoc.status || 'PENDING'}</span>
              </div>
              <h2 className="text-lg font-bold text-white leading-snug truncate">{selDoc.title}</h2>
            </div>
            <button onClick={() => setSelDoc(null)} className="w-7 h-7 rounded-full flex items-center justify-center text-slate-500 hover:text-white hover:bg-white/[0.08] transition-colors shrink-0"><X size={16} /></button>
          </div>
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-white/[0.03] border border-white/[0.06] p-3 rounded-lg">
                <p className="text-[9px] font-bold uppercase text-slate-500 mb-1">Ingested</p>
                <p className="text-[12px] text-slate-300 font-mono">{selDoc.date ? new Date(selDoc.date).toLocaleString() : '-'}</p>
              </div>
              <div className="bg-white/[0.03] border border-white/[0.06] p-3 rounded-lg">
                <p className="text-[9px] font-bold uppercase text-slate-500 mb-1">Source</p>
                {selDoc.url ? <a href={selDoc.url} target="_blank" rel="noreferrer" className="text-[12px] text-indigo-400 hover:underline truncate block">{selDoc.url}</a> : <p className="text-[12px] text-slate-500">Internal feed</p>}
              </div>
            </div>
            <div className="bg-white/[0.03] p-3 rounded-lg text-xs text-slate-400">Search indexing: {selDoc.embedding_status || 'Unknown'} · Published: {selDoc.published_at ? new Date(selDoc.published_at).toLocaleDateString() : 'Date unavailable'}</div>
            {selDoc.error && <p className="text-sm text-red-300">{selDoc.error}</p>}
            {(selDoc.status === 'FAILED' || selDoc.embedding_status === 'FAILED') && <button disabled={busy} onClick={retryReport} className="bg-indigo-600 px-4 py-2 rounded text-white text-sm">Retry Processing</button>}
            <div>
              <h3 className="text-[12px] font-semibold text-white mb-2 flex items-center gap-2"><Eye size={14} className="text-indigo-500" /> Raw Intelligence Content</h3>
              <div className="bg-white/[0.02] border border-white/[0.06] p-4 rounded-lg text-slate-300 font-mono text-[12px] leading-relaxed whitespace-pre-wrap max-h-[60vh] overflow-y-auto">
                {selDoc.content || 'No content available.'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ===== ENTITY DRAWER ===== */}
      {selEntity && (
        <div className="fixed inset-y-0 right-0 w-full max-w-[850px] bg-[#0c0c0e]/98 backdrop-blur-xl border-l border-white/[0.08] z-[200] flex flex-col shadow-2xl">
          <div className="p-5 border-b border-white/[0.06] flex justify-between items-start">
            <div className="flex gap-3 min-w-0 flex-1 mr-4">
              <div className="w-11 h-11 rounded-lg flex items-center justify-center font-bold text-lg shrink-0" style={{ backgroundColor: color(selEntity.group) + '15', color: color(selEntity.group) }}>
                {(selEntity.name || '?').charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1"><Badge type={selEntity.group} /></div>
                <h2 className="text-lg font-bold text-white truncate">{selEntity.name}</h2>
                <button className="mt-2 text-xs text-indigo-300 hover:text-white" onClick={() => {
                  setGraphFocus({id: selEntity.id, name: selEntity.name}); setGraphSearch(''); setGraphQuery('');
                  setGFilter('ALL'); setGraphSince(''); setGraphUntil(''); setGraphOffset(0); setGraphLimit(200);
                  drawerRequest.current++; setSelEntity(null); setTimeline(null); setTab('graph')
                }}>Explore connections in graph</button>
              </div>
            </div>
            <button onClick={() => { drawerRequest.current++; setTimeline(null); setSelEntity(null) }} className="w-7 h-7 rounded-full flex items-center justify-center text-slate-500 hover:text-white hover:bg-white/[0.08] transition-colors shrink-0"><X size={16} /></button>
          </div>
          {loading || !timeline ? (
            <div className="flex-1 flex items-center justify-center"><p className="text-slate-500 text-sm">Loading entity profile...</p></div>
          ) : (
          <div className="flex-1 overflow-y-auto p-5 space-y-6">
            {/* Context */}
            <div className="bg-white/[0.03] border border-white/[0.06] p-4 rounded-lg">
              <h3 className="text-[10px] font-bold uppercase text-slate-500 mb-2">Source Context</h3>
              <p className="text-[13px] text-slate-300 leading-relaxed">{timeline.context}</p>
            </div>

            {/* Related Entities */}
            {timeline.related && timeline.related.length > 0 && (
              <div>
                <h3 className="text-[13px] font-medium text-white border-b border-white/[0.06] pb-2 mb-3 flex items-center gap-2"><LinkIcon size={14} className="text-indigo-500" /> Related Entities ({timeline.related.length})</h3>
                <div className="grid grid-cols-2 gap-2">
                  {timeline.related.slice(0, 20).map((r: any, i: number) => (
                    <div key={i} className="bg-white/[0.02] border border-white/[0.05] p-2.5 rounded-md flex justify-between items-center">
                      <div className="min-w-0 flex-1 mr-2">
                        <p className="text-[11px] text-slate-300 truncate">{r.value}</p>
                        <p className="text-[9px] text-slate-600 mt-0.5">{r.relation}</p>
                      </div>
                      <Badge type={r.type} />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* IOCs */}
            {timeline.iocs && (
              <div>
                <h3 className="text-[13px] font-medium text-white border-b border-white/[0.06] pb-2 mb-3 flex items-center gap-2"><Fingerprint size={14} className="text-indigo-500" /> Technical Indicators ({timeline.iocs.length})</h3>
                <p className="text-xs text-slate-500 mb-3">Indicators with an active, non-negated relationship to this entity. Extracted values require source review before being treated as malicious.</p>
                {timeline.iocs.length === 0 && <p className="text-sm text-slate-400 mb-3">No directly linked indicators recorded. Supporting reports may still contain indicators that have not been linked to this entity.</p>}
                <div className="space-y-2">
                  {timeline.iocs.map((ioc: any, i: number) => (
                    <div key={i} className="bg-white/[0.02] border border-white/[0.05] p-3 rounded-md flex justify-between items-center">
                      <div>
                        <span className="text-[9px] font-bold tracking-wider uppercase text-slate-500 mr-2">{ioc.type}</span>
                        <span className="text-[12px] font-mono text-slate-300 break-all">{defang(ioc.value)}</span>
                      </div>
                      <span className="text-[10px] text-emerald-500 font-mono shrink-0 ml-2">{((ioc.confidence || 0) * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* TTPs */}
            {(() => {
              const ttps = Array.from(new Set((timeline.timeline || []).map((e: any) => e.mitre_attack_id).filter(Boolean)))
              return ttps.length > 0 ? (
                <div>
                  <h3 className="text-[13px] font-medium text-white border-b border-white/[0.06] pb-2 mb-3 flex items-center gap-2"><Radar size={14} className="text-indigo-500" /> MITRE ATT&CK TTPs</h3>
                  <div className="flex flex-wrap gap-2">
                    {ttps.map((t: any, i: number) => (
                      <span key={i} className="bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 font-mono text-[12px] font-semibold px-3 py-1.5 rounded">{t}</span>
                    ))}
                  </div>
                </div>
              ) : null
            })()}

            {/* Timeline */}
            <div>
              <h3 className="text-[13px] font-medium text-white border-b border-white/[0.06] pb-2 mb-4 flex items-center gap-2"><Activity size={14} className="text-indigo-500" /> Intelligence Lifecycle ({(timeline.timeline || []).length} events)</h3>
              <div className="border-l border-white/[0.08] ml-3 space-y-4">
                {(timeline.timeline || []).slice(0, 100).map((ev: any, i: number) => (
                  <div key={i} className="relative pl-5">
                    <div className={`absolute w-2 h-2 rounded-full -left-1 top-2 ${ev.status === 'HISTORICAL' ? 'bg-slate-600' : 'bg-indigo-500'}`}></div>
                    <div className="bg-white/[0.02] border border-white/[0.05] p-4 rounded-lg">
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-[10px] text-slate-500 flex items-center gap-1"><Clock size={10} /> {ev.date ? (ev.date.length <= 10 ? ev.date : new Date(ev.date).toLocaleString()) : 'Date unavailable'}</span>
                        <span className={`text-[8px] font-bold tracking-widest uppercase px-1.5 py-0.5 rounded ${ev.status === 'HISTORICAL' ? 'bg-white/[0.04] text-slate-500' : 'bg-indigo-500/10 text-indigo-400'}`}>{ev.status}{ev.review_required ? " · REVIEW" : ""}</span>
                      </div>
                      <p className="text-[13px] text-slate-200 font-medium mb-2">{ev.description}</p>
                      {ev.evidence && (
                        <div className="bg-white/[0.02] border-l-2 border-indigo-500/50 p-3 rounded-r-md">
                          <p className="text-[11px] text-slate-400 italic leading-relaxed">"{ev.evidence}"</p>
                          <p className="text-[9px] text-indigo-400 mt-1.5 font-mono uppercase tracking-wider">Source: {ev.source_name}</p>
                        </div>
                      )}
                      {ev.source_url && /^https?:\/\//i.test(ev.source_url) && <a href={ev.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex mt-2 text-xs text-indigo-400 hover:text-indigo-300 underline">Open source report ↗</a>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          )}
        </div>
      )}
    </div>
  )
}
