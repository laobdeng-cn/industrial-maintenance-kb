import { FormEvent, useEffect, useMemo, useState } from 'react'
import './App.css'

type DocumentItem = {
  id: number
  title: string
  version: string | null
  language: string | null
  source_url: string | null
  original_filename: string | null
  file_hash: string
  status: string
  created_at: string
  published_at: string | null
}

type DocumentBlock = {
  id: number
  evidence_id: string
  document_version_id: number
  block_type: string
  section_path: string | null
  page_start: number | null
  page_end: number | null
  bbox: Record<string, unknown> | null
  text: string | null
  asset_id: number | null
  ordinal: number
  extra_metadata: Record<string, unknown> | null
}

type DocumentAsset = {
  id: number
  document_version_id: number
  asset_type: string
  page_number: number | null
  mime_type: string | null
  sha256: string | null
  bbox: Record<string, unknown> | null
  caption: string | null
  storage_path: string
  created_at: string
}

type UploadResponse = {
  duplicate: boolean
  document: DocumentItem
  ingestion_job: {
    id: number
    stage: string
    status: string
  } | null
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body?.detail) message = String(body.detail)
    } catch {
      // Keep status text when the response is not JSON.
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function shortHash(value: string) {
  return `${value.slice(0, 10)}…${value.slice(-8)}`
}

function App() {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [blocks, setBlocks] = useState<DocumentBlock[]>([])
  const [assets, setAssets] = useState<DocumentAsset[]>([])
  const [activePanel, setActivePanel] = useState<'blocks' | 'assets'>('blocks')
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const selected = useMemo(
    () => documents.find((item) => item.id === selectedId) ?? null,
    [documents, selectedId],
  )

  async function loadDocuments(preferredId?: number) {
    setLoading(true)
    setError(null)
    try {
      const data = await api<DocumentItem[]>('/api/documents')
      setDocuments(data)
      setSelectedId((current) => {
        if (preferredId && data.some((item) => item.id === preferredId)) {
          return preferredId
        }
        if (current && data.some((item) => item.id === current)) {
          return current
        }
        return data[0]?.id ?? null
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载文档失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadDocuments()
  }, [])

  useEffect(() => {
    if (!selectedId) {
      setBlocks([])
      setAssets([])
      return
    }

    let cancelled = false
    setDetailLoading(true)
    setError(null)

    Promise.all([
      api<DocumentBlock[]>(`/api/documents/${selectedId}/blocks`),
      api<DocumentAsset[]>(`/api/documents/${selectedId}/assets`),
    ])
      .then(([blockData, assetData]) => {
        if (cancelled) return
        setBlocks(blockData)
        setAssets(assetData)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '加载解析结果失败')
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [selectedId])

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const formData = new FormData(form)
    const file = formData.get('file')

    if (!(file instanceof File) || file.size === 0) {
      setError('请选择 PDF 文件')
      return
    }

    setUploading(true)
    setError(null)
    setNotice(null)

    try {
      const result = await api<UploadResponse>('/api/documents/upload', {
        method: 'POST',
        body: formData,
      })

      setNotice(
        result.duplicate
          ? '检测到相同文件，已定位到现有文档。'
          : `上传成功，解析任务 #${result.ingestion_job?.id ?? '-'} 已进入队列。`,
      )
      form.reset()
      await loadDocuments(result.document.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传失败')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">IM</div>
          <div>
            <strong>Industrial KB</strong>
            <span>工业检修知识库</span>
          </div>
        </div>

        <nav>
          <button className="nav-item active" type="button">
            <span>▦</span>
            文档管理
          </button>
          <button className="nav-item" type="button" disabled>
            <span>⌕</span>
            检索问答
          </button>
          <button className="nav-item" type="button" disabled>
            <span>◎</span>
            评测中心
          </button>
        </nav>

        <div className="sidebar-footer">
          <span className="status-dot" />
          本地开发环境
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">KNOWLEDGE INGESTION</p>
            <h1>文档管理</h1>
            <p className="subtitle">
              上传工业 PDF，检查 Docling 解析块、页码、证据 ID 与图表资源。
            </p>
          </div>
          <a className="ghost-link" href="/docs" target="_blank" rel="noreferrer">
            API Docs ↗
          </a>
        </header>

        {error && <div className="alert error">{error}</div>}
        {notice && <div className="alert success">{notice}</div>}

        <section className="upload-card">
          <div>
            <h2>上传文档</h2>
            <p>当前仅接受 PDF。相同 SHA-256 文件不会重复入库。</p>
          </div>
          <form onSubmit={handleUpload}>
            <input name="file" type="file" accept="application/pdf,.pdf" required />
            <input name="title" placeholder="文档标题（可选）" />
            <input name="version" placeholder="版本，例如 1.0" />
            <input name="language" placeholder="语言，例如 zh-CN" />
            <button type="submit" disabled={uploading}>
              {uploading ? '上传中…' : '上传并解析'}
            </button>
          </form>
        </section>

        <div className="workspace">
          <section className="document-list panel">
            <div className="panel-header">
              <div>
                <h2>文档</h2>
                <span>{documents.length} 个版本</span>
              </div>
              <button
                className="icon-button"
                type="button"
                onClick={() => void loadDocuments()}
                aria-label="刷新文档列表"
              >
                ↻
              </button>
            </div>

            {loading ? (
              <div className="empty">正在加载…</div>
            ) : documents.length === 0 ? (
              <div className="empty">还没有文档</div>
            ) : (
              <div className="document-items">
                {documents.map((document) => (
                  <button
                    key={document.id}
                    type="button"
                    className={`document-row ${selectedId === document.id ? 'selected' : ''}`}
                    onClick={() => setSelectedId(document.id)}
                  >
                    <div className="file-icon">PDF</div>
                    <div className="document-copy">
                      <strong>{document.title}</strong>
                      <span>
                        {document.version ? `v${document.version}` : '无版本'}
                        {' · '}
                        {document.language ?? '未标注语言'}
                      </span>
                      <small>{formatDate(document.created_at)}</small>
                    </div>
                    <span className={`badge ${document.status}`}>{document.status}</span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="detail panel">
            {!selected ? (
              <div className="empty large">选择一个文档查看解析结果</div>
            ) : (
              <>
                <div className="document-detail-header">
                  <div>
                    <p className="eyebrow">DOCUMENT #{selected.id}</p>
                    <h2>{selected.title}</h2>
                    <div className="meta-line">
                      <span>{selected.original_filename ?? '未知文件名'}</span>
                      <span>{shortHash(selected.file_hash)}</span>
                    </div>
                  </div>
                  <div className="header-actions">
                    <a
                      className="secondary-button"
                      href={`/api/documents/${selected.id}/file`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      打开原始 PDF
                    </a>
                  </div>
                </div>

                <div className="stats">
                  <div>
                    <strong>{blocks.length}</strong>
                    <span>解析块</span>
                  </div>
                  <div>
                    <strong>{assets.length}</strong>
                    <span>图表资源</span>
                  </div>
                  <div>
                    <strong>{new Set(blocks.map((item) => item.page_start).filter(Boolean)).size}</strong>
                    <span>已识别页</span>
                  </div>
                </div>

                <div className="tabs">
                  <button
                    type="button"
                    className={activePanel === 'blocks' ? 'active' : ''}
                    onClick={() => setActivePanel('blocks')}
                  >
                    Blocks
                  </button>
                  <button
                    type="button"
                    className={activePanel === 'assets' ? 'active' : ''}
                    onClick={() => setActivePanel('assets')}
                  >
                    Assets
                  </button>
                </div>

                {detailLoading ? (
                  <div className="empty large">正在读取解析结果…</div>
                ) : activePanel === 'blocks' ? (
                  <div className="blocks">
                    {blocks.map((block) => (
                      <article className="block-card" key={block.id}>
                        <div className="block-head">
                          <div>
                            <span className={`type-chip ${block.block_type}`}>
                              {block.block_type}
                            </span>
                            <span className="page-chip">
                              P{block.page_start ?? '?'}
                              {block.page_end && block.page_end !== block.page_start
                                ? `–${block.page_end}`
                                : ''}
                            </span>
                          </div>
                          <code>{block.evidence_id.slice(0, 16)}…</code>
                        </div>
                        {block.section_path && (
                          <p className="section-path">{block.section_path}</p>
                        )}
                        <p className="block-text">
                          {block.text || '(该块没有文本内容)'}
                        </p>
                        {block.asset_id && (
                          <a
                            className="asset-inline"
                            href={`/api/documents/${selected.id}/assets/${block.asset_id}/file`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            查看关联图像 #{block.asset_id} ↗
                          </a>
                        )}
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="assets-grid">
                    {assets.length === 0 ? (
                      <div className="empty large">该文档没有图表资源</div>
                    ) : (
                      assets.map((asset) => (
                        <article className="asset-card" key={asset.id}>
                          <a
                            href={`/api/documents/${selected.id}/assets/${asset.id}/file`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <img
                              src={`/api/documents/${selected.id}/assets/${asset.id}/file`}
                              alt={asset.caption ?? `${asset.asset_type} asset`}
                            />
                          </a>
                          <div className="asset-meta">
                            <div>
                              <span className="type-chip">{asset.asset_type}</span>
                              <span className="page-chip">P{asset.page_number ?? '?'}</span>
                            </div>
                            <strong>Asset #{asset.id}</strong>
                            <small>{asset.sha256 ? shortHash(asset.sha256) : '无 SHA-256'}</small>
                            {asset.caption && <p>{asset.caption}</p>}
                          </div>
                        </article>
                      ))
                    )}
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}

export default App
