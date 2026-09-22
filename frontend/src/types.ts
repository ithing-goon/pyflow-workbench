export type PortSchema = { name: string; type: string; required: boolean; default: unknown }
export type NodeSchema = { type: string; label: string; category: string; description: string; inputs: PortSchema[]; outputs: PortSchema[]; kind?: string }
export type FlowData = { nodeType: string; schema: NodeSchema; params: Record<string, unknown>; status?: string; onParamChange?: (id: string, name: string, value: unknown) => void }
export type NodeRun = { node_id: string; node_type: string; status: string; error?: string; result?: { value: unknown; outputs: Record<string, unknown>; logs: string[]; metrics: Record<string, unknown>; child_runs?: RunResult[] } }
export type RunResult = { run_id: string; status: string; nodes: NodeRun[] }
export type GraphNode = { id: string; type: string; position: { x: number; y: number }; params: Record<string, unknown> }
export type GraphEdge = { id: string; source: string; target: string; source_handle: string; target_handle: string }
export type Subflow = { nodes: GraphNode[]; edges: GraphEdge[]; output_node: string; output_handle: string }
export type Graph = { id: string; name: string; nodes: GraphNode[]; edges: GraphEdge[]; subflows?: Record<string,Subflow> }
