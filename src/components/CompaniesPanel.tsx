import { useState } from 'react'
import { BriefcaseBusiness, ChevronDown, ChevronRight, Pencil, Plus, Save, Trash2 } from 'lucide-react'
import { createCompany, deleteCompany, updateCompany } from '../api/client'
import { isApiError } from '../types/switchboard'
import type { Workspace } from '../types/switchboard'

const COMPANY_CRUD_ENABLED = false

interface Props {
  companies: Workspace[]
  offline: boolean
  onReload: () => void
}

export function CompaniesPanel({ companies, offline, onReload }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draftId, setDraftId] = useState('')
  const [draftName, setDraftName] = useState('')
  const [draftNotes, setDraftNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  function startAdd() {
    setAdding(true)
    setEditingId(null)
    setDraftId('')
    setDraftName('')
    setDraftNotes('')
    setError(null)
  }

  function startEdit(company: Workspace) {
    setAdding(false)
    setEditingId(company.workspace_id)
    setDraftId(company.workspace_id)
    setDraftName(company.display_name)
    setDraftNotes(company.notes ?? '')
    setError(null)
  }

  function cancel() {
    setAdding(false)
    setEditingId(null)
    setError(null)
  }

  async function handleSave() {
    if (!draftId.trim() || !draftName.trim()) {
      setError('Company ID and name are required.')
      return
    }
    if (adding) {
      const result = await createCompany({
        workspace_id: draftId.trim(),
        name: draftName.trim(),
        notes: draftNotes.trim(),
        tags: ['company'],
      })
      if (isApiError(result)) {
        setError(result.message)
        return
      }
      setAdding(false)
      onReload()
      return
    }
    if (!editingId) return
    const result = await updateCompany(editingId, {
      name: draftName.trim(),
      notes: draftNotes.trim(),
    })
    if (isApiError(result)) {
      setError(result.message)
      return
    }
    setEditingId(null)
    onReload()
  }

  async function handleDelete(company: Workspace) {
    if (!confirm(`Delete company ${company.display_name}? This only works when no servers or services are linked.`)) return
    const result = await deleteCompany(company.workspace_id)
    if (isApiError(result)) {
      setError(result.message)
      return
    }
    onReload()
  }

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900">
      <button onClick={() => setExpanded((open) => !open)} className="flex w-full items-center justify-between p-4">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-300">
          <BriefcaseBusiness className="h-4 w-4 text-amber-300" />
          Companies
        </div>
        {expanded ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
      </button>
      {expanded && (
        <div className="border-t border-gray-800 p-4">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-xs text-gray-500">Top-level companies you work for. Services and servers group under these.</p>
            {!offline && COMPANY_CRUD_ENABLED && !adding && !editingId && (
              <button onClick={startAdd} className="flex items-center gap-1 rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-1.5 text-xs text-amber-100 transition-colors hover:bg-amber-400/20">
                <Plus className="h-3 w-3" /> Add Company
              </button>
            )}
          </div>
          {error && <div className="mb-4 rounded bg-red-950/30 p-2 text-xs text-red-400">{error}</div>}
          {!COMPANY_CRUD_ENABLED && (
            <div className="mb-4 rounded-lg border border-amber-900/40 bg-amber-950/10 px-3 py-2 text-xs text-amber-100/80">
              Company editing is hidden in this build. Keep the current company list read-only until add/edit/delete is tested end to end.
            </div>
          )}
          {COMPANY_CRUD_ENABLED && (adding || editingId) && (
            <div className="mb-6 rounded-xl border border-gray-800 bg-gray-950 p-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs text-gray-500">Company ID</label>
                  <input value={draftId} onChange={(e) => setDraftId(e.target.value)} disabled={!adding} className="w-full rounded border border-gray-800 bg-gray-900 px-2 py-1.5 text-sm text-gray-200 focus:border-cyan-500 focus:outline-none disabled:opacity-50" />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-gray-500">Company Name</label>
                  <input value={draftName} onChange={(e) => setDraftName(e.target.value)} className="w-full rounded border border-gray-800 bg-gray-900 px-2 py-1.5 text-sm text-gray-200 focus:border-cyan-500 focus:outline-none" />
                </div>
                <div className="md:col-span-2">
                  <label className="mb-1 block text-xs text-gray-500">Notes</label>
                  <input value={draftNotes} onChange={(e) => setDraftNotes(e.target.value)} className="w-full rounded border border-gray-800 bg-gray-900 px-2 py-1.5 text-sm text-gray-200 focus:border-cyan-500 focus:outline-none" />
                </div>
              </div>
              <div className="mt-4 flex justify-end gap-2">
                <button onClick={cancel} className="px-3 py-1.5 text-xs text-gray-400 hover:text-white">Cancel</button>
                <button onClick={handleSave} className="flex items-center gap-1 rounded bg-cyan-600 px-3 py-1.5 text-xs text-white hover:bg-cyan-500">
                  <Save className="h-3 w-3" /> Save
                </button>
              </div>
            </div>
          )}
          <div className="grid gap-3 md:grid-cols-2">
            {companies.map((company) => (
              <div key={company.workspace_id} className="rounded-xl border border-amber-400/20 bg-gray-950 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-white">{company.display_name}</div>
                    <div className="mt-1 font-mono text-[10px] text-gray-500">{company.workspace_id}</div>
                  </div>
                  {!offline && COMPANY_CRUD_ENABLED && (
                    <div className="flex gap-2">
                      <button onClick={() => startEdit(company)} className="p-1 text-gray-500 hover:text-cyan-400"><Pencil className="h-3.5 w-3.5" /></button>
                      <button onClick={() => handleDelete(company)} className="p-1 text-gray-500 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
                    </div>
                  )}
                </div>
                <div className="mt-3 flex gap-2 text-[10px] uppercase tracking-[0.16em] text-amber-300">
                  <span>{company.server_count ?? company.server_ids.length} servers</span>
                  <span>{company.service_count ?? company.services.length} services</span>
                </div>
                {company.notes && <div className="mt-3 border-t border-gray-800 pt-3 text-xs text-gray-400">{company.notes}</div>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
