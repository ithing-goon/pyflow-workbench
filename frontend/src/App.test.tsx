import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import App from './App'
import { STORAGE_KEY } from './graph'

// Test editor state and controls. Canvas layout/dragging needs a real browser.
vi.mock('@xyflow/react', async importOriginal => {
  const actual = await importOriginal<typeof import('@xyflow/react')>()
  return {...actual, ReactFlow:({nodes,edges,onNodeClick,children}: {nodes: {id:string;data:{status?:string}}[];edges:unknown[];onNodeClick:(e:null,n:{id:string})=>void;children:ReactNode})=><div><span data-testid="counts">{nodes.length}/{edges.length}</span><button onClick={()=>onNodeClick(null,nodes[0])}>Select first node</button>{nodes.map(n=><span key={n.id}>{n.id}:{n.data.status || 'idle'}</span>)}{children}</div>,Background:()=>null,Controls:()=>null,MiniMap:()=>null,Panel:({children}:{children:ReactNode})=><div>{children}</div>}
})

const input = (name:string,type:string,required=true,defaultValue:unknown=null)=>({name,type,required,default:defaultValue})
const catalog = [
  {type:'text_input',label:'Text Input',inputs:[input('text','str',false,'sample')],outputs:[input('result','str')]},
  {type:'normalize_text',label:'Normalize Text',inputs:[input('text','str')],outputs:[input('result','str')]},
  {type:'chunk_text',label:'Chunk Text',inputs:[input('text','str'),input('size','int',false,400),input('overlap','int',false,40)],outputs:[input('result','list[str]')]},
  {type:'debug',label:'Debug',inputs:[input('value','any')],outputs:[input('result','any')]},
  {type:'inject',label:'Inject',inputs:[input('value','any',false,null)],outputs:[input('result','any')]},
  {type:'switch',label:'Switch',inputs:[input('value','any'),input('operator','str',false,'truthy')],outputs:[input('true','any'),input('false','any')]},
  {type:'merge',label:'Merge',kind:'merge',inputs:[input('left','any',false,null),input('right','any',false,null),input('mode','str',false,'first')],outputs:[input('result','any')]},
  {type:'split',label:'Split',inputs:[input('value','any')],outputs:[input('result','dict')]},
  {type:'join',label:'Join',inputs:[input('value','dict')],outputs:[input('result','any')]},
  {type:'subflow_input',label:'Subflow Input',inputs:[input('value','any',false,null)],outputs:[input('result','any')]},
  {type:'subflow',label:'Subflow',inputs:[input('value','any'),input('flow','str')],outputs:[input('result','any')]},
  {type:'map_subflow',label:'Map Subflow',inputs:[input('value','dict'),input('flow','str')],outputs:[input('result','dict')]},
].map(n=>({...n,category:'Test',description:''}))
afterEach(()=>vi.unstubAllGlobals())
function setup(stream?: Response) {
  vi.stubGlobal('fetch',vi.fn(async (url:string)=>url==='/api/nodes'?{ok:true,json:async()=>catalog}:stream || {ok:true,json:async()=>({valid:true})}))
  render(<App/> )
}
it('saves and restores a draft with the same node positions and params', async()=>{
  setup()
  await waitFor(()=>expect(screen.getByTestId('counts').textContent).toBe('4/3'))
  fireEvent.change(screen.getByLabelText('Flow name'),{target:{value:'Saved pipeline'}})
  fireEvent.click(screen.getByText('Save draft'))
  expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).name).toBe('Saved pipeline')
  expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).nodes).toHaveLength(4)
})
it('restores a saved draft on load',async()=>{
  localStorage.setItem(STORAGE_KEY,JSON.stringify({name:'Restored',nodes:[{id:'a',type:'text_input',position:{x:123,y:456},params:{text:'stored'}}],edges:[]}))
  setup()
  await waitFor(()=>expect(screen.getByTestId('counts').textContent).toBe('1/0'))
  expect((screen.getByLabelText('Flow name') as HTMLInputElement).value).toBe('Restored')
})
it('deletes incident edges with a node',async()=>{
  setup()
  await waitFor(()=>expect(screen.getByTestId('counts').textContent).toBe('4/3'))
  fireEvent.click(screen.getByText('Select first node'))
  fireEvent.click(screen.getByText('Delete node'))
  expect(screen.getByTestId('counts').textContent).toBe('3/2')
})
it('shows streamed output and completion status',async()=>{
  const node={node_id:'node-1',node_type:'text_input',status:'succeeded',result:{value:'한국어 결과',outputs:{result:'한국어 결과'},logs:['done'],metrics:{latency_ms:1}}}
  const events=[{event:'node',node:{...node,status:'running',result:undefined}},{event:'node',node},{event:'complete',result:{run_id:'test',status:'succeeded',nodes:[node]}}]
  setup(new Response(events.map(e=>JSON.stringify(e)).join('\n')+'\n'))
  await waitFor(()=>expect(screen.getByTestId('counts').textContent).toBe('4/3'))
  fireEvent.click(screen.getByText('Run pipeline'))
  await waitFor(()=>expect(screen.getByText(/한국어 결과/)).toBeTruthy())
  expect(screen.getByText('done')).toBeTruthy()
})
it('shows API startup errors',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')))
  render(<App/> )
  await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('Cannot load nodes'))
})

it('opens, defines, reuses and saves a subflow with the parent graph',async()=>{
  setup()
  await waitFor(()=>expect(screen.getByTestId('counts').textContent).toBe('4/3'))
  fireEvent.click(screen.getByText('Batch + subflow'))
  expect(screen.getByTestId('counts').textContent).toBe('5/4')
  fireEvent.click(screen.getByText('Open clean_text'))
  expect(screen.getByTestId('counts').textContent).toBe('2/1')
  fireEvent.change(screen.getByLabelText('Subflow name'),{target:{value:'reusable_clean'}})
  fireEvent.click(screen.getByText('Define subflow'))
  await waitFor(()=>expect(screen.getByText('Use reusable_clean')).toBeTruthy())
  fireEvent.click(screen.getByText('Back to parent flow'))
  expect(screen.getByTestId('counts').textContent).toBe('5/4')
  fireEvent.click(screen.getByText('Use reusable_clean'))
  expect(screen.getByTestId('counts').textContent).toBe('6/4')
  fireEvent.click(screen.getByText('Save draft'))
  const stored=JSON.parse(localStorage.getItem(STORAGE_KEY)!)
  expect(stored.subflows.reusable_clean.output_node).toBe('clean')
  expect(stored.nodes[5].params.flow).toBe('reusable_clean')
})

it('keeps same-id child events separate from parent status',async()=>{
  const parent={node_id:'node-1',node_type:'text_input',status:'succeeded'}
  const events=[{event:'node',scope:[],node:parent},{event:'node',scope:['node-1','item:0'],node:{...parent,status:'failed',error:'child failure'}},{event:'complete',result:{run_id:'test',status:'failed',nodes:[parent]}}]
  setup(new Response(events.map(e=>JSON.stringify(e)).join('\n')+'\n'))
  await waitFor(()=>expect(screen.getByTestId('counts').textContent).toBe('4/3'))
  fireEvent.click(screen.getByText('Run pipeline'))
  await waitFor(()=>expect(screen.getByText('Subflow trace')).toBeTruthy())
  expect(screen.getByText('node-1:succeeded')).toBeTruthy()
  expect(screen.getByText(/node-1 \/ item:0 \/ node-1/)).toBeTruthy()
})

it('loads merge example with distinct input handles',async()=>{
  setup()
  await waitFor(()=>expect(screen.getByTestId('counts').textContent).toBe('4/3'))
  fireEvent.click(screen.getByText('Merge example'))
  fireEvent.click(screen.getByText('Save draft'))
  const stored=JSON.parse(localStorage.getItem(STORAGE_KEY)!)
  expect(stored.edges.filter((e:{target:string})=>e.target==='merge').map((e:{target_handle:string})=>e.target_handle)).toEqual(['left','right'])
})
