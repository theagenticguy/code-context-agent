import { create } from 'zustand'
import type { AnalysisResult, CodeGraph } from '../types'

function countByField<T>(items: T[], field: keyof T): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const item of items) {
    const val = String(item[field] ?? 'unknown')
    counts[val] = (counts[val] || 0) + 1
  }
  return counts
}

export interface AppState {
  // Data artifacts
  graph: CodeGraph | null
  analysisResult: AnalysisResult | null
  narrative: string | null
  bundle: string | null
  signatures: string | null
  filesList: string | null

  // Computed from graph
  nodeTypes: Record<string, number>
  edgeTypes: Record<string, number>

  // UI state
  theme: 'light' | 'dark'
  isLoading: boolean
  error: string | null
  pendingSearch: string | null

  // Actions
  setGraph: (graph: CodeGraph) => void
  setAnalysisResult: (result: AnalysisResult) => void
  setNarrative: (text: string) => void
  setBundle: (text: string) => void
  setSignatures: (text: string) => void
  setFilesList: (text: string) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  setPendingSearch: (query: string | null) => void
  toggleTheme: () => void
}

export const useStore = create<AppState>((set) => ({
  graph: null,
  analysisResult: null,
  narrative: null,
  bundle: null,
  signatures: null,
  filesList: null,
  nodeTypes: {},
  edgeTypes: {},
  theme: (localStorage.getItem('theme') as 'light' | 'dark') || 'light',
  isLoading: false,
  error: null,
  pendingSearch: null,

  setGraph: (graph) =>
    set({
      graph,
      nodeTypes: countByField(graph.nodes, 'node_type'),
      edgeTypes: countByField(graph.links, 'edge_type'),
    }),

  setAnalysisResult: (result) => set({ analysisResult: result }),
  setNarrative: (text) => set({ narrative: text }),
  setBundle: (text) => set({ bundle: text }),
  setSignatures: (text) => set({ signatures: text }),
  setFilesList: (text) => set({ filesList: text }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  setPendingSearch: (query) => set({ pendingSearch: query }),

  toggleTheme: () =>
    set((state) => {
      const next = state.theme === 'dark' ? 'light' : 'dark'
      localStorage.setItem('theme', next)
      document.documentElement.classList.toggle('dark', next === 'dark')
      return { theme: next }
    }),
}))
