import { describe, expect, it } from 'vitest'
import { defaultParams, deserialize, makeSubflow, serialize } from './graph'
import type { NodeSchema } from './types'

const schema: NodeSchema = {type:'inject',label:'Inject',category:'Input',description:'',inputs:[{name:'value',type:'any',required:false,default:null}],outputs:[{name:'result',type:'any',required:true,default:null}]}
const graph = {name:'한글 flow',nodes:[{id:'a',type:'inject',position:{x:10,y:20},params:{value:{text:'한국어'}}}],edges:[]}
describe('graph persistence', () => {
  it('round trips parameters and positions without UI state', () => {
    const loaded = deserialize(JSON.parse(JSON.stringify(graph)),[schema])
    const saved = serialize(loaded.nodes,loaded.edges,loaded.name)
    expect(saved.nodes).toEqual(graph.nodes)
    expect(saved.name).toBe(graph.name)
    expect(saved.nodes[0]).not.toHaveProperty('data')
  })
  it.each([null,{}, {...graph,nodes:[...graph.nodes,...graph.nodes]}, {...graph,nodes:[{...graph.nodes[0],type:'unknown'}]}, {...graph,edges:[{id:'e',source:'a',target:'absent',source_handle:'result',target_handle:'value'}]}])('rejects malformed imported graphs', raw => {
    expect(()=>deserialize(raw,[schema])).toThrow()
  })
})

it('preserves subflow definitions through graph roundtrip',()=>{
  const inputSchema={...schema,type:'subflow_input'}
  const body={nodes:[{...graph.nodes[0],type:'subflow_input'}],edges:[],output_node:'a',output_handle:'result'}
  const withFlow={...graph,subflows:{identity:body}}
  const loaded=deserialize(withFlow,[schema,inputSchema])
  expect(serialize(loaded.nodes,loaded.edges,loaded.name,loaded.subflows).subflows).toEqual(withFlow.subflows)
  expect(makeSubflow(deserialize({name:'inner',...body},[inputSchema]).nodes,[],'a')).toEqual(body)
})
it('rejects a subflow without its required boundary input',()=>{
  expect(()=>makeSubflow(deserialize(graph,[schema]).nodes,[],'a')).toThrow('Subflow Input')
})
it('does not prefill inactive merge literals with null',()=>{
  const merge={...schema,kind:'merge',inputs:[{name:'left',type:'any',required:false,default:null},{name:'right',type:'any',required:false,default:null},{name:'mode',type:'str',required:false,default:'first'}]}
  expect(defaultParams(merge)).toEqual({mode:'first'})
})
