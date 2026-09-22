import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Background, Controls, Edge, MiniMap, Node, Panel, ReactFlow, addEdge, useEdgesState, useNodesState, Connection } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { CirclePlay, Code2, Search, Trash2 } from 'lucide-react'
import { PipelineNode } from './PipelineNode'
import { ParameterField } from './ParameterField'
import { batchSample, defaultParams, deserialize, makeSubflow, mergeSample, sample, serialize, STORAGE_KEY } from './graph'
import type { FlowData, Graph, NodeRun, NodeSchema, RunResult, Subflow } from './types'
import './styles.css'

const nodeTypes = { pipeline: PipelineNode }

export default function App() {
  const [catalog, setCatalog] = useState<NodeSchema[]>([])
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<FlowData>>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [name, setName] = useState('Document pipeline')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [result, setResult] = useState<RunResult | null>(null)
  const [nodeRuns, setNodeRuns] = useState<NodeRun[]>([])
  const [running, setRunning] = useState(false)
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [invalidFields, setInvalidFields] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const fileInput = useRef<HTMLInputElement>(null)
  const [subflows, setSubflows] = useState<Record<string,Subflow>>({})
  const [subflowName, setSubflowName] = useState('my_subflow')
  const [outputHandle, setOutputHandle] = useState('result')
  const [returnGraph, setReturnGraph] = useState<Graph | null>(null)
  const [nestedRuns, setNestedRuns] = useState<Record<string,{scope:string[];node:NodeRun}>>({})

  const loadGraph = useCallback((raw: unknown, items: NodeSchema[]) => {
    const loaded = deserialize(raw, items)
    setNodes(loaded.nodes); setEdges(loaded.edges); setName(loaded.name)
    setSelectedId(null); setInvalidFields([]); setResult(null); setNodeRuns([])
    setSubflows(loaded.subflows);setNestedRuns({});setReturnGraph(null)
  }, [setEdges, setNodes])

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/nodes', {signal:controller.signal}).then(async response => {
      if (!response.ok) throw new Error(`API unavailable (${response.status})`)
      return response.json() as Promise<NodeSchema[]>
    }).then(items => {
      setCatalog(items)
      loadGraph(sample(items),items)
      try {
        const saved = localStorage.getItem(STORAGE_KEY)
        if (saved) {loadGraph(JSON.parse(saved),items); setNotice('Saved draft restored')}
      } catch (err) {setError(`Saved draft could not be restored: ${String(err)}`)}
      setLoading(false)
    }).catch(err => {if (!controller.signal.aborted) {setLoading(false);setError(`Cannot load nodes: ${String(err)}. Start the Python API and reload.`)}})
    return () => controller.abort()
  }, [loadGraph])

  const onConnect = useCallback((connection: Connection) => {
    if (running) return
    if (edges.some(e => e.target === connection.target && e.targetHandle === connection.targetHandle)) {setError('An input accepts only one connection');return}
    if (connection.target === selectedId) setInvalidFields(items=>items.filter(k=>k!==connection.targetHandle))
    setEdges(items => addEdge(connection,items));setError('')
  }, [edges, running, selectedId, setEdges])
  const selected = nodes.find(node => node.id === selectedId)
  const categories = useMemo(() => [...new Set(catalog.map(item => item.category))], [catalog])
  const graph = () => serialize(nodes,edges,name,subflows)

  const addNode = (schema: NodeSchema, params: Record<string,unknown> = {}) => {
    if (running) return
    setNodes(items => [...items,{id:`node-${crypto.randomUUID()}`,type:'pipeline',position:{x:220+items.length*35,y:100+items.length*35},data:{nodeType:schema.type,schema,params:{...defaultParams(schema),...params}}}])
  }
  const setParam = (key: string, value: unknown) => {
    if (!running) setNodes(items => items.map(n => n.id === selectedId ? {...n,data:{...n.data,params:{...n.data.params,[key]:value}}} : n))
  }
  const removeSelected = () => {
    setNodes(ns => ns.filter(n => n.id !== selectedId))
    setEdges(es => es.filter(e => e.source !== selectedId && e.target !== selectedId))
    setInvalidFields([]);setSelectedId(null)
  }
  const save = () => {
    try {localStorage.setItem(STORAGE_KEY,JSON.stringify(graph()));setNotice('Draft saved in this browser');setError('')}
    catch (err) {setError(`Save failed: ${String(err)}`)}
  }
  const exportGraph = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(graph(),null,2)],{type:'application/json'}))
    const a = document.createElement('a'); a.href = url;a.download='pyflow-graph.json';a.click()
    setTimeout(() => URL.revokeObjectURL(url),1000)
  }
  const importGraph = async (file?: File) => {
    if (!file) return
    try {loadGraph(JSON.parse(await file.text()),catalog);setError('');setNotice('Graph imported; save to keep this draft')}
    catch (err) {setError(`Import failed: ${String(err)}`)}
    if (fileInput.current) fileInput.current.value = ''
  }
  const validate = async (payload: Graph) => {
    const response = await fetch('/api/graphs/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
    const body = await response.json()
    if (!response.ok) throw new Error(JSON.stringify(body.detail || body))
    if (!body.valid) throw new Error(body.errors.join('\n'))
  }
  const check = async () => {
    try {await validate(graph());setError('');setNotice('Graph validation passed')}
    catch (err) {setError(String(err))}
  }
  const defineSubflow = async () => {
    try {
      const key = subflowName.trim()
      if (!key || !selectedId) throw new Error('Enter a subflow name and select its output node')
      const definition = makeSubflow(nodes,edges,selectedId,outputHandle)
      const library = {...subflows,[key]:definition}
      // Validate the body using its preview input value before replacing a definition.
      await validate({...graph(),subflows:library})
      setSubflows(library);setError('');setNotice(`Subflow ${key} updated. Save draft or Export to persist.`)
    } catch (err) {setError(String(err))}
  }
  const openSubflow = (key: string) => {
    const back = returnGraph || graph()
    loadGraph({id:key,name:key,...subflows[key],subflows},catalog)
    setReturnGraph(back);setSubflowName(key);setSelectedId(subflows[key].output_node);setOutputHandle(subflows[key].output_handle)
  }
  const useSubflow = (key:string, map=false) => {
    const schema = catalog.find(s=>s.type === (map?'map_subflow':'subflow'))
    if (schema) addNode(schema,{flow:key})
  }
  const run = async () => {
    if (running) return
    setRunning(true);setResult(null);setNodeRuns([]);setNestedRuns({});setError('');setNotice('')
    setNodes(items => items.map(n => ({...n,data:{...n.data,status:'pending'}})))
    try {
      const response = await fetch('/api/runs/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(graph())})
      if (!response.ok) {const body = await response.json();throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail))}
      if (!response.body) throw new Error('Streaming response unavailable')
      const reader = response.body.getReader(), decoder = new TextDecoder()
      let buffer = '', complete = false
      const accept = (line: string) => {
        if (!line.trim()) return
        const event = JSON.parse(line)
        if (event.event === 'error') throw new Error(event.error)
        if (event.event === 'node') {
          const update = event.node as NodeRun
          const scope = (event.scope || []) as string[]
          if (scope.length) {
            const key = JSON.stringify([...scope,update.node_id])
            setNestedRuns(items=>({...items,[key]:{scope,node:update}}))
          } else {
            setNodeRuns(items => [...items.filter(n => n.node_id !== update.node_id),update])
            setNodes(items => items.map(n => n.id === update.node_id ? {...n,data:{...n.data,status:update.status}} : n))
          }
        }
        if (event.event === 'complete') {setResult(event.result);setNodeRuns(event.result.nodes);complete=true}
      }
      try {
        while (true) {
          const {done,value} = await reader.read()
          if (done) break
          buffer += decoder.decode(value,{stream:true})
          let newline
          while ((newline = buffer.indexOf('\n')) >= 0) {accept(buffer.slice(0,newline));buffer=buffer.slice(newline+1)}
        }
        buffer += decoder.decode();accept(buffer)
        if (!complete) throw new Error('Run stream ended before completion')
      } finally {await reader.cancel();reader.releaseLock()}
    } catch (err) {
      setError(String(err))
      setNodes(items => items.map(n => ['running','pending'].includes(n.data.status || '') ? {...n,data:{...n.data,status:undefined}} : n))
    } finally {setRunning(false)}
  }

  const disabled = running || loading || !catalog.length || invalidFields.length > 0
  return <main>
    <header className="topbar"><div className="brand"><span><Code2 size={19}/></span><b>PyFlow</b><em>Workbench · 0.3</em></div>
      <input className="flow-name" aria-label="Flow name" value={name} disabled={running} onChange={e=>setName(e.target.value)}/>
      <button onClick={save} disabled={disabled}>Save draft</button><button onClick={exportGraph} disabled={disabled}>Export</button>
      <button onClick={()=>fileInput.current?.click()} disabled={disabled}>Import</button><input ref={fileInput} aria-label="Import graph file" type="file" accept=".json" hidden onChange={e=>void importGraph(e.target.files?.[0])}/>
      <button onClick={check} disabled={disabled}>Validate</button>
      <button className="run" onClick={run} disabled={disabled}><CirclePlay size={17}/>{running?'Running…':'Run pipeline'}</button>
    </header>
    <section className="workspace">
      <aside className="palette"><h2>Node library</h2><label className="search"><Search size={15}/><input placeholder="Search nodes" value={filter} onChange={e=>setFilter(e.target.value)}/></label>
        <div className="examples"><button disabled={disabled} onClick={()=>loadGraph(sample(catalog),catalog)}>Document example</button><button disabled={disabled} onClick={()=>loadGraph(sample(catalog,true),catalog)}>Switch example</button><button disabled={disabled} onClick={()=>loadGraph(mergeSample(catalog),catalog)}>Merge example</button><button disabled={disabled} onClick={()=>loadGraph(batchSample(),catalog)}>Batch + subflow</button><button disabled={disabled} onClick={()=>loadGraph({name:'New flow',nodes:[],edges:[],subflows},catalog)}>New flow</button></div>
        <div className="subflow-library"><h3>Subflows</h3>{Object.keys(subflows).length===0&&<p className="muted">Add one Subflow Input, connect your nodes, select an output node, then define the canvas as a subflow.</p>}{Object.keys(subflows).map(key=><div key={key}><b>{key}</b><div><button disabled={disabled} onClick={()=>openSubflow(key)}>Open {key}</button><button disabled={disabled} onClick={()=>useSubflow(key)}>Use {key}</button><button disabled={disabled} onClick={()=>useSubflow(key,true)}>Map {key}</button></div></div>)}{returnGraph&&<button disabled={disabled} onClick={()=>loadGraph({...returnGraph,subflows},catalog)}>Back to parent flow</button>}</div>
        {categories.map(category=><div className="category" key={category}><h3>{category}</h3>{catalog.filter(n=>n.category===category&&`${n.label} ${n.description}`.toLowerCase().includes(filter.toLowerCase())).map(schema=><button disabled={running} key={schema.type} onClick={()=>addNode(schema)}><span><Code2 size={15}/></span><div><b>{schema.label}</b><small>{schema.description}</small></div></button>)}</div>)}
      </aside>
      <div className="canvas"><ReactFlow nodes={nodes} edges={edges} onNodesChange={changes=>{if(!running)onNodesChange(changes)}} onEdgesChange={changes=>{if(!running)onEdgesChange(changes)}} onConnect={onConnect} onNodeClick={(_,node)=>{if(!invalidFields.length){setSelectedId(node.id);setOutputHandle(node.data.schema.outputs[0]?.name || 'result')}}} onPaneClick={()=>{if(!invalidFields.length)setSelectedId(null)}} nodesDraggable={!running} nodesConnectable={!running} deleteKeyCode={null} nodeTypes={nodeTypes} fitView snapToGrid snapGrid={[16,16]}>
        <Background gap={16} size={1}/><Controls/><MiniMap pannable zoomable nodeColor="#5d67f6"/><Panel position="top-left" className="canvas-label">DAG editor <span>{nodes.length} nodes · {edges.length} edges</span></Panel>
      </ReactFlow></div>
      <aside className="inspector">
        {error&&<pre role="alert" className="error-banner">{error}</pre>}{notice&&<p role="status" className="notice">{notice}</p>}
        <h2>{selected ? selected.data.schema.label : 'Inspector'}</h2>
        {selected ? <><p>{selected.data.schema.description}</p><h3>Parameters</h3>{selected.data.schema.inputs.map(port=>{
          const connected = edges.some(e=>e.target===selected.id&&e.targetHandle===port.name)
          return <div key={`${selected.id}:${port.name}`}><ParameterField port={port} value={selected.data.params[port.name]} connected={connected} disabled={running} onChange={v=>setParam(port.name,v)} onValidity={valid=>setInvalidFields(items=>valid?items.filter(k=>k!==port.name):[...new Set([...items,port.name])])}/>{connected&&<button disabled={running} onClick={()=>setEdges(es=>es.filter(e=>!(e.target===selected.id&&e.targetHandle===port.name)))}>Disconnect {port.name}</button>}</div>
        })}<button className="delete" disabled={running} onClick={removeSelected}><Trash2 size={15}/>Delete node</button><section className="define-subflow"><h3>Define canvas as subflow</h3><label>Name<input aria-label="Subflow name" value={subflowName} disabled={disabled} onChange={e=>setSubflowName(e.target.value)}/></label><label>Output port<select aria-label="Subflow output port" value={outputHandle} disabled={disabled} onChange={e=>setOutputHandle(e.target.value)}>{selected.data.schema.outputs.map(p=><option key={p.name} value={p.name}>{p.name}</option>)}</select></label><button disabled={disabled} onClick={defineSubflow}>Define subflow</button><p className="muted">Output: {selected.id}. The canvas needs one Subflow Input node. An existing name updates that definition.</p></section></>:<p className="muted">Select a node to configure inputs. Connect ports by dragging. Run manually to inject values.</p>}
        <div className="results"><h3>Debug · latest run</h3>{result&&<div className={`run-status ${result.status}`}>{result.status}</div>}{!nodeRuns.length?<p className="muted">Run a graph to inspect outputs, logs and metrics.</p>:nodeRuns.map(node=><details key={node.node_id} open><summary>{nodes.find(n=>n.id===node.node_id)?.data.schema.label || node.node_id}<span>{node.status}</span></summary>{node.error&&<pre>{node.error}</pre>}{node.result&&<><h4>Output</h4><pre className="output-preview">{JSON.stringify(node.result.outputs,null,2)}</pre><h4>Metrics</h4><pre>{JSON.stringify(node.result.metrics,null,2)}</pre>{node.result.logs.map((log,i)=><p className="log" key={i}>{log}</p>)}</>}</details>)}</div>
        {Object.keys(nestedRuns).length>0&&<div className="results"><h3>Subflow trace</h3>{Object.entries(nestedRuns).map(([key,{scope,node}])=><details key={key}><summary>{[...scope,node.node_id].join(' / ')}<span>{node.status}</span></summary>{node.error&&<pre>{node.error}</pre>}{node.result&&<pre>{JSON.stringify(node.result.outputs,null,2)}</pre>}</details>)}</div>}
      </aside>
    </section>
  </main>
}
