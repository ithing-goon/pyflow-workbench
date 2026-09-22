import { useEffect, useState } from 'react'
import type { PortSchema } from './types'

export function ParameterField({port, value, connected, disabled, onChange, onValidity}: {port: PortSchema; value: unknown; connected: boolean; disabled: boolean; onChange: (value: unknown) => void; onValidity: (valid: boolean) => void}) {
  const json = !['str','int','float','bool'].includes(port.type)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {setDraft(value === undefined ? '' : json ? JSON.stringify(value, null, 2) : String(value ?? '')); setError('')}, [value, json])
  const update = (text: string) => {
    setDraft(text)
    try {
      const parsed = json ? JSON.parse(text) : port.type === 'str' ? text : Number(text)
      if (!json && port.type !== 'str' && (text.trim() === '' || !Number.isFinite(parsed) || (port.type === 'int' && !Number.isInteger(parsed)))) throw new Error('Enter a valid number')
      setError(''); onValidity(true); onChange(parsed)
    } catch {setError(json ? 'Invalid JSON — strings need double quotes' : 'Enter a valid number'); onValidity(false)}
  }
  return <label className="field"><span>{port.name}<small>{connected ? 'connected' : port.type}</small></span>
    {connected ? <div className="connected">Value supplied by connection</div> : port.type === 'bool' ? <select aria-label={port.name} disabled={disabled} value={String(value ?? false)} onChange={e => onChange(e.target.value === 'true')}><option value="true">true</option><option value="false">false</option></select> : <textarea aria-label={port.name} disabled={disabled} value={draft} onChange={e => update(e.target.value)} placeholder={json ? 'JSON value' : port.type} />}
    {error && <small role="alert" className="field-error">{error}</small>}
  </label>
}
