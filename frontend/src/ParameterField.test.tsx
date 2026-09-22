import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ParameterField } from './ParameterField'

it('edits Any as JSON without converting objects into strings', () => {
  const onChange=vi.fn(),onValidity=vi.fn()
  render(<ParameterField port={{name:'value',type:'any',required:true,default:null}} value={null} disabled={false} connected={false} onChange={onChange} onValidity={onValidity}/>)
  fireEvent.change(screen.getByLabelText('value'),{target:{value:'{"name":"한국어"}'}})
  expect(onChange).toHaveBeenLastCalledWith({name:'한국어'})
  fireEvent.change(screen.getByLabelText('value'),{target:{value:'{broken'}})
  expect(onChange).toHaveBeenCalledTimes(1)
  expect(onValidity).toHaveBeenLastCalledWith(false)
  expect(screen.getByRole('alert').textContent).toContain('Invalid JSON')
})
it('prevents editing connected values', () => {
  render(<ParameterField port={{name:'value',type:'any',required:true,default:null}} value={null} disabled={false} connected onChange={vi.fn()} onValidity={vi.fn()}/>)
  expect(screen.queryByRole('textbox')).toBeNull()
  expect(screen.getByText('Value supplied by connection')).toBeTruthy()
})
it('rejects fractional integer input', () => {
  const onChange=vi.fn()
  render(<ParameterField port={{name:'size',type:'int',required:false,default:400}} value={400} disabled={false} connected={false} onChange={onChange} onValidity={vi.fn()}/>)
  fireEvent.change(screen.getByLabelText('size'),{target:{value:'1.5'}})
  expect(onChange).not.toHaveBeenCalled()
})
