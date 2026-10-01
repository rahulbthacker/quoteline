import { createContext, useContext, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { setApiPersona } from './api'
import type { Persona } from './types'

export const PERSONAS: { id: Persona; label: string; can: string }[] = [
  { id: 'buyer', label: 'Category buyer', can: 'Drafts, compares, resolves, prepares the award' },
  { id: 'vp', label: 'VP Supply Chain', can: 'Reads everything, asks questions, signs off the award' },
  { id: 'evaluator', label: 'Technical evaluator', can: 'Scores the questionnaire' },
  { id: 'admin', label: 'Admin', can: 'Conversion table, FX policy, thresholds' },
]

type Value = { persona: Persona; label: string; setPersona: (p: Persona) => void; can: (...allowed: Persona[]) => boolean }
const PersonaContext = createContext<Value | null>(null)

export function PersonaProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [persona, setState] = useState<Persona>(() => (localStorage.getItem('quoteline-persona') as Persona) || 'buyer')
  const setPersona = (next: Persona) => {
    localStorage.setItem('quoteline-persona', next)
    setApiPersona(next)
    setState(next)
    void queryClient.invalidateQueries()
  }
  const value: Value = {
    persona,
    label: PERSONAS.find((p) => p.id === persona)!.label,
    setPersona,
    can: (...allowed) => allowed.includes(persona),
  }
  return <PersonaContext.Provider value={value}>{children}</PersonaContext.Provider>
}

export function usePersona(): Value {
  const value = useContext(PersonaContext)
  if (!value) throw new Error('usePersona outside PersonaProvider')
  return value
}
