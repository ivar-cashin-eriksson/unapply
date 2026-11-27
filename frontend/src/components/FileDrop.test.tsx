import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { FileDrop } from '@/components/FileDrop'

const cv = () => new File(['# CV'], 'cv.md', { type: 'text/markdown' })
const photo = () => new File(['png'], 'photo.png', { type: 'image/png' })

describe('FileDrop', () => {
  it('takes dropped files and says why others are refused', () => {
    const onFiles = vi.fn()
    const onRefused = vi.fn()
    render(<FileDrop onFiles={onFiles} onRefused={onRefused} />)
    const zone = screen.getByRole('button', { name: 'Upload files' })
    fireEvent.dragOver(zone, { dataTransfer: { files: [] } })
    expect(zone).toHaveTextContent('Drop to upload')
    fireEvent.drop(zone, { dataTransfer: { files: [cv(), photo()] } })
    expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ name: 'cv.md' })])
    expect(onRefused).toHaveBeenCalledWith(['photo.png: not a file type we read'])
    expect(zone).toHaveTextContent('Drag files here, or click to choose')
  })

  it('takes chosen files from the file picker', async () => {
    const user = userEvent.setup()
    const onFiles = vi.fn()
    render(<FileDrop onFiles={onFiles} onRefused={() => {}} />)
    await user.upload(screen.getByTestId('file-input'), cv())
    expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ name: 'cv.md' })])
  })

  it('opens the file picker with Enter or Space', async () => {
    const user = userEvent.setup()
    render(<FileDrop onFiles={() => {}} onRefused={() => {}} />)
    const click = vi.spyOn(screen.getByTestId('file-input'), 'click').mockImplementation(() => {})
    await user.tab()
    expect(screen.getByRole('button', { name: 'Upload files' })).toHaveFocus()
    await user.keyboard('{Enter}')
    await user.keyboard(' ')
    expect(click).toHaveBeenCalledTimes(2)
  })

  it('ignores files while disabled, and is out of the tab order', () => {
    const onFiles = vi.fn()
    render(<FileDrop onFiles={onFiles} onRefused={() => {}} disabled />)
    const zone = screen.getByRole('button', { name: 'Upload files' })
    expect(zone).toHaveAttribute('tabindex', '-1')
    fireEvent.drop(zone, { dataTransfer: { files: [cv()] } })
    expect(onFiles).not.toHaveBeenCalled()
  })
})
