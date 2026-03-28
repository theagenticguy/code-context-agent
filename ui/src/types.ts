export interface GraphNode {
  id: string
  name: string
  node_type: string
  file_path: string
  line_start: number
  line_end: number
  lsp_kind?: number
}

export interface GraphEdge {
  source: string
  target: string
  edge_type: string
  weight: number
  confidence?: number
}

export interface CodeGraph {
  directed: boolean
  multigraph: boolean
  graph: Record<string, unknown>
  nodes: GraphNode[]
  links: GraphEdge[]
}

export interface BusinessLogicItem {
  rank: number
  name: string
  role: string
  location: string
  score: number
  category: string
}

export interface ArchitecturalRisk {
  description: string
  severity: string
  location?: string
  mitigation?: string
}

export interface RefactoringCandidate {
  type: string
  pattern: string
  files: string[]
  occurrence_count: number
  duplicated_lines: number
  score: number
}

export interface CodeHealth {
  duplication_percentage: number
  total_clone_groups: number
  unused_symbol_count: number
  code_smell_count: number
}

export interface PhaseTiming {
  phase: number
  name: string
  duration_seconds: number
  tool_count: number
}

export interface AnalysisResult {
  status?: string
  summary?: string
  total_files_analyzed?: number
  analysis_mode?: string
  business_logic_items?: BusinessLogicItem[]
  risks?: ArchitecturalRisk[]
  refactoring_candidates?: RefactoringCandidate[]
  code_health?: CodeHealth
  phase_timings?: PhaseTiming[]
  graph_stats?: Record<string, number>
  generated_files?: Array<{ path: string; line_count: number; description: string }>
}
