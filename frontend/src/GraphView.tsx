import { memo, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

const colors: Record<string, string> = { THREAT_ACTOR: '#ea580c', MALWARE: '#dc2626', TOOL: '#2563eb', VULNERABILITY: '#d97706', TECHNIQUE: '#7c3aed', ORGANIZATION: '#0d9488', OBSERVABLE: '#ec4899' }
const escapeLabel = (value: string) => value.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!))

export default memo(function GraphView({ data, onSelect }: { data: any, onSelect: (id: string, name: string, group: string) => void }) {
  const container = useRef<HTMLDivElement>(null)
  const graphRef = useRef<any>(undefined)
  const [size, setSize] = useState({ width: 400, height: 400 })
  // The force engine mutates node positions and link endpoints; keep API state immutable.
  const graph = useMemo(() => ({ nodes: data.nodes.map((n: any) => ({ ...n })), links: data.links.map((l: any) => ({ ...l })) }), [data])
  useEffect(() => {
    if (!container.current) return
    const observer = new ResizeObserver(entries => {
      const box = entries[0].contentRect
      setSize({ width: Math.max(1, box.width), height: Math.max(1, box.height) })
    })
    observer.observe(container.current)
    return () => observer.disconnect()
  }, [])
  return <div ref={container} className="absolute inset-0">
    {graph.nodes.length === 0 ? <p className="p-6 text-sm text-slate-500">No graph data yet. Import a report to extract entities and relationships.</p> : <ForceGraph2D
      ref={graphRef} width={size.width} height={size.height} graphData={graph} backgroundColor="transparent"
      nodeColor={(n: any) => colors[n.group] || '#64748b'} nodeRelSize={4}
      nodeLabel={(n: any) => escapeLabel(`${n.name} (${n.group.replace(/_/g, ' ')})`)}
      linkLabel={(l: any) => escapeLabel(l.label || '')} linkColor={(l: any) => l.review_required ? '#f59e0b' : 'rgba(255,255,255,0.2)'}
      linkDirectionalArrowLength={3} linkDirectionalArrowRelPos={1} cooldownTicks={60}
      onEngineStop={() => graphRef.current?.zoomToFit(300, 35)}
      onNodeClick={(n: any) => onSelect(n.id, n.name, n.group)}
    />}
  </div>
})
