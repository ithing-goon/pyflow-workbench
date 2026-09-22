import { Handle, NodeProps, Position } from '@xyflow/react'
import { Braces, Check, CircleAlert, LoaderCircle } from 'lucide-react'
import type { FlowData } from './types'

export function PipelineNode({ data, selected }: NodeProps) {
  const typed = data as FlowData
  const Icon = typed.status === 'succeeded' ? Check : typed.status === 'failed' ? CircleAlert : typed.status === 'running' ? LoaderCircle : Braces
  return <div className={`pipeline-node ${selected ? 'selected' : ''} ${typed.status ?? ''}`}>
    <header><span className="node-icon"><Icon size={14}/></span><strong>{typed.schema.label}</strong></header>
    <p>{typed.schema.description || typed.schema.category}</p>
    <div className="ports inputs">
      {typed.schema.inputs.map((port) => <div className="port" key={port.name}>
        <Handle type="target" position={Position.Left} id={port.name} style={{top: '50%', left: -15}} />
        <span>{port.name}</span><small>{port.type}</small>
      </div>)}
    </div>
    <div className="ports outputs">
      {typed.schema.outputs.map((port) => <div className="port" key={port.name}>
        <small>{port.type}</small><span>{port.name}</span>
        <Handle type="source" position={Position.Right} id={port.name} style={{top: '50%', right: -15}} />
      </div>)}
    </div>
    <footer>{typed.schema.category} · {typed.status || 'idle'}</footer>
  </div>
}
