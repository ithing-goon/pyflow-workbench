import type { Edge, Node } from '@xyflow/react'
import type { FlowData, Graph, NodeSchema, Subflow } from './types'

export const STORAGE_KEY = 'pyflow.graph.v1'
export function defaultParams(schema: NodeSchema): Record<string,unknown> {
  return Object.fromEntries(schema.inputs.filter(p=>!p.required && !(schema.kind==='merge' && ['left','right'].includes(p.name))).map(p=>[p.name,p.default]))
}
export function serialize(nodes: Node<FlowData>[], edges: Edge[], name: string, subflows: Record<string,Subflow> = {}): Graph {
  return { id: 'editor', name, subflows, nodes: nodes.map(n => ({id: n.id, type: n.data.nodeType, position: n.position, params: n.data.params})), edges: edges.map(e => ({id: e.id, source: e.source, target: e.target, source_handle: e.sourceHandle || 'result', target_handle: e.targetHandle || ''})) }
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

// Drafts can have unconnected inputs, but must be structurally well formed.
export function deserialize(raw: unknown, catalog: NodeSchema[]) {
  if (!object(raw) || typeof raw.name !== 'string' || !Array.isArray(raw.nodes) || !Array.isArray(raw.edges)) throw new Error('Invalid graph JSON')
  const ids = new Set<string>()
  const nodes: Node<FlowData>[] = raw.nodes.map(n => {
    if (!object(n) || typeof n.id !== 'string' || ids.has(n.id) || !object(n.position) || !Number.isFinite(n.position.x) || !Number.isFinite(n.position.y) || !object(n.params)) throw new Error('Invalid or duplicate node')
    const schema = catalog.find(s => s.type === n.type)
    if (!schema) throw new Error(`Unknown node type: ${n.type}`)
    ids.add(n.id)
    return {id: n.id, type: 'pipeline', position: n.position as {x: number; y: number}, data: {nodeType: schema.type, schema, params: n.params}}
  })
  const edgeIds = new Set<string>()
  const inputs = new Set<string>()
  const edges: Edge[] = raw.edges.map(e => {
    if (!object(e) || typeof e.id !== 'string' || edgeIds.has(e.id) || typeof e.source !== 'string' || typeof e.target !== 'string' || typeof e.source_handle !== 'string' || typeof e.target_handle !== 'string') throw new Error('Invalid or duplicate edge')
    const source = nodes.find(n => n.id === e.source), target = nodes.find(n => n.id === e.target)
    if (!source?.data.schema.outputs.some(p => p.name === e.source_handle) || !target?.data.schema.inputs.some(p => p.name === e.target_handle)) throw new Error('Edge references missing node or port')
    const inputKey = JSON.stringify([e.target, e.target_handle])
    if (inputs.has(inputKey)) throw new Error('Multiple edges to one input')
    inputs.add(inputKey); edgeIds.add(e.id)
    return {id:e.id, source:e.source, target:e.target, sourceHandle:e.source_handle, targetHandle:e.target_handle}
  })
  const subflows: Record<string,Subflow> = Object.create(null)
  if (raw.subflows !== undefined) {
    if (!object(raw.subflows)) throw new Error('Invalid subflow library')
    for (const [name,flow] of Object.entries(raw.subflows)) {
      if (!name.trim() || !object(flow) || typeof flow.output_node !== 'string' || (flow.output_handle !== undefined && typeof flow.output_handle !== 'string') || flow.subflows !== undefined) throw new Error('Invalid subflow definition')
      const body = deserialize({name,nodes:flow.nodes,edges:flow.edges},catalog)
      subflows[name] = makeSubflow(body.nodes,body.edges,flow.output_node,typeof flow.output_handle === 'string' ? flow.output_handle : 'result')
    }
  }
  return {name: raw.name, nodes, edges, subflows}
}

export function makeSubflow(nodes: Node<FlowData>[], edges: Edge[], outputId: string, outputHandle = 'result'): Subflow {
  const inputs = nodes.filter(n=>n.data.nodeType==='subflow_input')
  if (inputs.length !== 1) throw new Error('A subflow needs exactly one Subflow Input node')
  if (edges.some(e=>e.target===inputs[0].id)) throw new Error('Subflow Input cannot have incoming edges')
  const output = nodes.find(n=>n.id===outputId)
  if (!output?.data.schema.outputs.some(p=>p.name===outputHandle)) throw new Error('Select a valid output node and port')
  const graph = serialize(nodes,edges,'subflow')
  return {nodes:graph.nodes,edges:graph.edges,output_node:outputId,output_handle:outputHandle}
}

export function batchSample(): Graph {
  const node = (id:string,type:string,x:number,y:number,params:Record<string,unknown>={})=>({id,type,position:{x,y},params})
  const edge = (id:string,source:string,target:string,target_handle='value')=>({id,source,target,source_handle:'result',target_handle})
  return {id:'batch-example',name:'Batch cleanup with a reusable subflow',nodes:[node('source','inject',0,100,{value:[' alpha   beta ','한국어   문서']}),node('split','split',260,100),node('map','map_subflow',520,100,{flow:'clean_text'}),node('join','join',780,100),node('debug','debug',1040,100)],edges:[edge('1','source','split'),edge('2','split','map'),edge('3','map','join'),edge('4','join','debug')],subflows:{clean_text:{nodes:[node('input','subflow_input',0,100),node('clean','normalize_text',300,100)],edges:[edge('1','input','clean','text')],output_node:'clean',output_handle:'result'}}}
}

export function mergeSample(catalog: NodeSchema[]): Graph {
  const base = sample(catalog,true)
  base.name = 'Switch branches rejoin through Merge'
  base.nodes.push({id:'merge',type:'merge',position:{x:880,y:150},params:{}},{id:'result',type:'debug',position:{x:1160,y:150},params:{}})
  base.edges.push({id:'m1',source:'node-3',target:'merge',source_handle:'result',target_handle:'left'},{id:'m2',source:'node-4',target:'merge',source_handle:'result',target_handle:'right'},{id:'m3',source:'merge',target:'result',source_handle:'result',target_handle:'value'})
  return base
}

export function sample(catalog: NodeSchema[], branching = false): Graph {
  const types = branching ? ['inject', 'switch', 'debug', 'debug'] : ['text_input', 'normalize_text', 'chunk_text', 'debug']
  const nodes = types.map((type, i) => {
    const schema = catalog.find(n => n.type === type)
    if (!schema) throw new Error(`Missing built-in node: ${type}`)
    return {id: `node-${i+1}`, type, position: {x: 60 + i * 270, y: 140}, params: Object.fromEntries(schema.inputs.filter(p => !p.required).map(p => [p.name, p.default]))}
  })
  if (branching) {
    nodes[0].params.value = {needs_ocr:true}
    nodes[1].params.operator = 'truthy'
    nodes[2].params.label = 'True branch'; nodes[3].params.label = 'False branch'
    nodes[2].position = {x:600,y:40}; nodes[3].position = {x:600,y:320}
  } else nodes[0].params.text = 'PyFlow visual pipeline workbench.\n\n한국어 문서를 정규화하고 청킹합니다.'
  const edge = (i: number, source: number, target: number, input: string, output = 'result') => ({id:`e${i}`, source:`node-${source}`, target:`node-${target}`, source_handle:output, target_handle:input})
  return {id:'example',name:branching?'Conditional routing':'Document pipeline',nodes,edges:branching?[edge(1,1,2,'value'),edge(2,2,3,'value','true'),edge(3,2,4,'value','false')]:[edge(1,1,2,'text'),edge(2,2,3,'text'),edge(3,3,4,'value')]}
}
