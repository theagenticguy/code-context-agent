import { useStore } from '../store/use-store'
import type { CodeGraph } from '../types'

export function parseGraph(raw: Record<string, unknown>): CodeGraph {
  const rawNodes = (raw.nodes as Array<Record<string, unknown>>) || []
  const rawLinks = (raw.links as Array<Record<string, unknown>>) || (raw.edges as Array<Record<string, unknown>>) || []

  const nodes = rawNodes.map((n) => ({
    id: String(n.id),
    name: (n.name as string) || String(n.id),
    node_type: (n.node_type as string) || 'unknown',
    file_path: (n.file_path as string) || '',
    line_start: (n.line_start as number) ?? 0,
    line_end: (n.line_end as number) ?? 0,
    ...(n.lsp_kind !== undefined ? { lsp_kind: n.lsp_kind as number } : {}),
  }))

  const links = rawLinks.map((e) => ({
    source: String(e.source),
    target: String(e.target),
    edge_type: (e.edge_type as string) || (e.key as string) || 'unknown',
    weight: (e.weight as number) ?? 1,
    ...(e.confidence !== undefined ? { confidence: e.confidence as number } : {}),
  }))

  return {
    directed: (raw.directed as boolean) ?? true,
    multigraph: (raw.multigraph as boolean) ?? false,
    graph: (raw.graph as Record<string, unknown>) || {},
    nodes,
    links,
  }
}

const FILE_MAP: Record<
  string,
  {
    setter: keyof Pick<
      ReturnType<typeof useStore.getState>,
      'setGraph' | 'setAnalysisResult' | 'setNarrative' | 'setBundle' | 'setBundles' | 'setSignatures' | 'setFilesList'
    >
    isGraph?: boolean
    isJson?: boolean
  }
> = {
  'code_graph.json': { setter: 'setGraph', isGraph: true, isJson: true },
  'analysis_result.json': { setter: 'setAnalysisResult', isJson: true },
  'CONTEXT.md': { setter: 'setNarrative' },
  'CONTEXT.bundle.md': { setter: 'setBundle' },
  'CONTEXT.signatures.md': { setter: 'setSignatures' },
  'files.all.txt': { setter: 'setFilesList' },
}

/** Extract a bundle area name from a filename like BUNDLE.auth.md → "auth" */
function parseBundleArea(filename: string): string | null {
  const match = /^BUNDLE\.(.+)\.md$/i.exec(filename)
  return match ? match[1] : null
}

export async function loadFromFiles(fileList: FileList): Promise<void> {
  const store = useStore.getState()
  store.setLoading(true)
  store.setError(null)

  try {
    const promises: Promise<void>[] = []
    const bundleEntries: Record<string, string> = {}

    for (const file of fileList) {
      // Check for individual bundle files (BUNDLE.{area}.md)
      const area = parseBundleArea(file.name)
      if (area) {
        promises.push(
          file.text().then((text) => {
            bundleEntries[area] = text
          }),
        )
        continue
      }

      const mapping = FILE_MAP[file.name]
      if (!mapping) continue

      promises.push(
        file.text().then((text) => {
          const s = useStore.getState()
          if (mapping.isGraph) {
            s.setGraph(parseGraph(JSON.parse(text)))
          } else if (mapping.isJson) {
            ;(s[mapping.setter] as (v: unknown) => void)(JSON.parse(text))
          } else {
            ;(s[mapping.setter] as (v: string) => void)(text)
          }
        }),
      )
    }

    await Promise.all(promises)

    // If individual bundle files were found, store them (takes priority over CONTEXT.bundle.md)
    if (Object.keys(bundleEntries).length > 0) {
      useStore.getState().setBundles(bundleEntries)
    }
  } catch (err) {
    useStore.getState().setError(`File load error: ${(err as Error).message}`)
  } finally {
    useStore.getState().setLoading(false)
  }
}

export async function loadFromServer(baseUrl: string): Promise<void> {
  const store = useStore.getState()
  store.setLoading(true)
  store.setError(null)

  const urls: Record<string, string> = {
    'code_graph.json': `${baseUrl}/data/code_graph.json`,
    'analysis_result.json': `${baseUrl}/data/analysis_result.json`,
    'CONTEXT.md': `${baseUrl}/data/CONTEXT.md`,
    'CONTEXT.bundle.md': `${baseUrl}/data/CONTEXT.bundle.md`,
    'CONTEXT.signatures.md': `${baseUrl}/data/CONTEXT.signatures.md`,
  }

  try {
    const promises = Object.entries(urls).map(async ([fileName, url]) => {
      try {
        const resp = await fetch(url)
        if (!resp.ok) return
        const text = await resp.text()
        const mapping = FILE_MAP[fileName]
        if (!mapping) return
        const s = useStore.getState()
        if (mapping.isGraph) {
          s.setGraph(parseGraph(JSON.parse(text)))
        } else if (mapping.isJson) {
          ;(s[mapping.setter] as (v: unknown) => void)(JSON.parse(text))
        } else {
          ;(s[mapping.setter] as (v: string) => void)(text)
        }
      } catch {
        // silently skip per-artifact errors
      }
    })

    await Promise.all(promises)

    // Discover and load individual bundle files from the bundles directory
    try {
      const listResp = await fetch(`${baseUrl}/data/bundles/`)
      if (listResp.ok) {
        const filenames = (await listResp.json()) as string[]
        if (filenames.length > 0) {
          const bundleEntries: Record<string, string> = {}
          const bundlePromises = filenames.map(async (filename) => {
            try {
              const area = parseBundleArea(filename)
              if (!area) return
              const resp = await fetch(`${baseUrl}/data/bundles/${filename}`)
              if (!resp.ok) return
              bundleEntries[area] = await resp.text()
            } catch {
              // silently skip individual bundle errors
            }
          })
          await Promise.all(bundlePromises)
          if (Object.keys(bundleEntries).length > 0) {
            useStore.getState().setBundles(bundleEntries)
          }
        }
      }
    } catch {
      // bundles directory listing not available; fall back to CONTEXT.bundle.md loaded above
    }
  } catch (err) {
    useStore.getState().setError(`Server load error: ${(err as Error).message}`)
  } finally {
    useStore.getState().setLoading(false)
  }
}
