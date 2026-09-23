import { FormEvent, useEffect, useMemo, useState } from 'react'
import './App.css'

type EquipmentModel = {
  id: number
  manufacturer: string
  model_code: string
  category: string | null
  aliases: string[] | null
  created_at: string
}

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
  equipment_models: EquipmentModel[]
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

type SearchHit = {
  score: number
  vector_score: number
  rerank_score: number
  final_score: number
  point_id: number | string
  document_id: number
  block_id: number
  evidence_id: string
  title: string
  version: string | null
  language: string | null
  block_type: string
  section_path: string | null
  page_start: number | null
  page_end: number | null
  asset_id: number | null
  text: string
}

type SearchResponse = {
  query: string
  equipment_model_id: number
  embedding_model: string
  collection_name: string
  rough_recall_limit: number
  hits: SearchHit[]
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body?.detail) {
        message =
          typeof body.detail === 'string'
            ? body.detail
            : JSON.stringify(body.detail)
      }
    } catch {
      // Keep status text when the response is not JSON.
    }
    throw new Error(message)
  }

  if (response.status === 204) {
    return undefined as T
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

function formatScore(value: number) {
  return value.toFixed(4)
}

function App() {
  const [page, setPage] = useState<'documents' | 'search'>('documents')
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [equipmentModels, setEquipmentModels] = useState<EquipmentModel[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [selectedEquipmentIds, setSelectedEquipmentIds] = useState<number[]>([])
  const [blocks, setBlocks] = useState<DocumentBlock[]>([])
  const [assets, setAssets] = useState<DocumentAsset[]>([])
  const [activePanel, setActivePanel] = useState<'blocks' | 'assets'>('blocks')
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [creatingModel, setCreatingModel] = useState(false)
  const [bindingModels, setBindingModels] = useState(false)
  const [statusUpdating, setStatusUpdating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [searchEquipmentId, setSearchEquipmentId] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchLimit, setSearchLimit] = useState(5)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null)

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

  async function loadEquipmentModels() {
    try {
      const data = await api<EquipmentModel[]>('/api/equipment-models')
      setEquipmentModels(data)
      setSearchEquipmentId((current) => {
        if (current && data.some((item) => item.id === current)) {
          return current
        }
        return data[0]?.id ?? null
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载设备型号失败')
    }
  }

  useEffect(() => {
    void Promise.all([loadDocuments(), loadEquipmentModels()])
  }, [])

  useEffect(() => {
    setSelectedEquipmentIds(
      selected?.equipment_models.map((model) => model.id) ?? [],
    )
  }, [selected])

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

  async function handleCreateEquipment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const formData = new FormData(form)
    const aliasesRaw = String(formData.get('aliases') ?? '')

    setCreatingModel(true)
    setError(null)
    setNotice(null)

    try {
      const model = await api<EquipmentModel>('/api/equipment-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          manufacturer: String(formData.get('manufacturer') ?? ''),
          model_code: String(formData.get('model_code') ?? ''),
          category: String(formData.get('category') ?? '') || null,
          aliases: aliasesRaw
            ? aliasesRaw
                .split(',')
                .map((item) => item.trim())
                .filter(Boolean)
            : null,
        }),
      })

      setNotice(`已创建设备型号 ${model.manufacturer} ${model.model_code}。`)
      form.reset()
      await loadEquipmentModels()
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建设备型号失败')
    } finally {
      setCreatingModel(false)
    }
  }

  async function handleDeleteEquipment(model: EquipmentModel) {
    if (
      !window.confirm(
        `确认删除设备型号 ${model.manufacturer} ${model.model_code}？关联文档会自动解绑。`,
      )
    ) {
      return
    }

    setError(null)
    setNotice(null)

    try {
      await api<void>(`/api/equipment-models/${model.id}`, {
        method: 'DELETE',
      })
      setNotice(`已删除设备型号 ${model.model_code}。`)
      await Promise.all([
        loadEquipmentModels(),
        loadDocuments(selectedId ?? undefined),
      ])
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除设备型号失败')
    }
  }

  function toggleEquipmentModel(id: number) {
    setSelectedEquipmentIds((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    )
  }

  async function saveDocumentBindings() {
    if (!selected) return

    setBindingModels(true)
    setError(null)
    setNotice(null)

    try {
      await api<DocumentItem>(
        `/api/documents/${selected.id}/equipment-models`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            equipment_model_ids: selectedEquipmentIds,
          }),
        },
      )
      setNotice('文档适用设备型号已更新。')
      await loadDocuments(selected.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存设备型号绑定失败')
    } finally {
      setBindingModels(false)
    }
  }

  async function updateDocumentStatus(action: 'publish' | 'archive') {
    if (!selected) return

    setStatusUpdating(true)
    setError(null)
    setNotice(null)

    try {
      const updated = await api<DocumentItem>(
        `/api/documents/${selected.id}/${action}`,
        { method: 'POST' },
      )
      setNotice(
        action === 'publish'
          ? '文档已发布，可进入后续检索索引流程。'
          : '文档已下架，后续检索应排除该版本。',
      )
      await loadDocuments(updated.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新发布状态失败')
    } finally {
      setStatusUpdating(false)
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!searchEquipmentId) {
      setSearchError('请先选择设备型号')
      return
    }

    if (!searchQuery.trim()) {
      setSearchError('请输入问题')
      return
    }

    setSearching(true)
    setSearchError(null)

    try {
      const result = await api<SearchResponse>('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: searchQuery.trim(),
          equipment_model_id: searchEquipmentId,
          limit: searchLimit,
        }),
      })
      setSearchResult(result)
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : '检索失败')
    } finally {
      setSearching(false)
    }
  }

  function renderDocumentPage() {
    return (
      <>
        <header className="topbar">
          <div>
            <p className="eyebrow">KNOWLEDGE INGESTION</p>
            <h1>文档管理</h1>
            <p className="subtitle">
              管理设备型号、文档版本、发布状态与 Docling 解析证据。
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

        <section className="equipment-card">
          <div className="equipment-card-head">
            <div>
              <h2>设备型号</h2>
              <p>用于后续按型号隔离检索，避免不同设备版本串答。</p>
            </div>
            <span>{equipmentModels.length} 个型号</span>
          </div>

          <form className="equipment-form" onSubmit={handleCreateEquipment}>
            <input name="manufacturer" placeholder="厂商，例如 Acme" required />
            <input name="model_code" placeholder="型号，例如 IM-1200" required />
            <input name="category" placeholder="类别，例如 Remote I/O" />
            <input name="aliases" placeholder="别名，逗号分隔" />
            <button type="submit" disabled={creatingModel}>
              {creatingModel ? '创建中…' : '新增型号'}
            </button>
          </form>

          <div className="equipment-list">
            {equipmentModels.length === 0 ? (
              <span className="muted-inline">尚未创建设备型号</span>
            ) : (
              equipmentModels.map((model) => (
                <div className="equipment-pill" key={model.id}>
                  <div>
                    <strong>{model.model_code}</strong>
                    <span>{model.manufacturer}</span>
                    {model.category && <small>{model.category}</small>}
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleDeleteEquipment(model)}
                    aria-label={`删除 ${model.model_code}`}
                  >
                    ×
                  </button>
                </div>
              ))
            )}
          </div>
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
                      <small>
                        {document.equipment_models.length > 0
                          ? document.equipment_models
                              .map((model) => model.model_code)
                              .join(' / ')
                          : '未绑定型号'}
                      </small>
                    </div>
                    <span className={`badge ${document.status}`}>
                      {document.status}
                    </span>
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
                      {selected.published_at && (
                        <span>发布于 {formatDate(selected.published_at)}</span>
                      )}
                    </div>
                  </div>
                  <div className="header-actions">
                    <span className={`badge detail-status ${selected.status}`}>
                      {selected.status}
                    </span>
                    <button
                      type="button"
                      className={
                        selected.status === 'published'
                          ? 'danger-button'
                          : 'primary-outline-button'
                      }
                      disabled={statusUpdating}
                      onClick={() =>
                        void updateDocumentStatus(
                          selected.status === 'published'
                            ? 'archive'
                            : 'publish',
                        )
                      }
                    >
                      {statusUpdating
                        ? '处理中…'
                        : selected.status === 'published'
                          ? '下架'
                          : '发布'}
                    </button>
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

                <div className="equipment-binding">
                  <div className="binding-title">
                    <div>
                      <strong>适用设备型号</strong>
                      <span>后续检索会基于这里的型号关系做候选集过滤。</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => void saveDocumentBindings()}
                      disabled={bindingModels}
                    >
                      {bindingModels ? '保存中…' : '保存绑定'}
                    </button>
                  </div>

                  <div className="model-checkboxes">
                    {equipmentModels.length === 0 ? (
                      <span className="muted-inline">
                        请先在上方创建设备型号
                      </span>
                    ) : (
                      equipmentModels.map((model) => (
                        <label
                          key={model.id}
                          className={
                            selectedEquipmentIds.includes(model.id)
                              ? 'model-check selected'
                              : 'model-check'
                          }
                        >
                          <input
                            type="checkbox"
                            checked={selectedEquipmentIds.includes(model.id)}
                            onChange={() => toggleEquipmentModel(model.id)}
                          />
                          <span>
                            <strong>{model.model_code}</strong>
                            <small>{model.manufacturer}</small>
                          </span>
                        </label>
                      ))
                    )}
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
                    <strong>
                      {
                        new Set(
                          blocks.map((item) => item.page_start).filter(Boolean),
                        ).size
                      }
                    </strong>
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
                              <span className="page-chip">
                                P{asset.page_number ?? '?'}
                              </span>
                            </div>
                            <strong>Asset #{asset.id}</strong>
                            <small>
                              {asset.sha256
                                ? shortHash(asset.sha256)
                                : '无 SHA-256'}
                            </small>
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
      </>
    )
  }

  function renderSearchPage() {
    const activeEquipment = equipmentModels.find(
      (model) => model.id === searchEquipmentId,
    )

    return (
      <>
        <header className="topbar">
          <div>
            <p className="eyebrow">RETRIEVAL DEBUG</p>
            <h1>检索问答</h1>
            <p className="subtitle">
              先选择设备型号，再执行 Top-20 粗召回与二阶段 Rerank。
            </p>
          </div>
          <a className="ghost-link" href="/docs" target="_blank" rel="noreferrer">
            Search API ↗
          </a>
        </header>

        {searchError && <div className="alert error">{searchError}</div>}

        <section className="search-card">
          <form onSubmit={handleSearch}>
            <div className="search-control">
              <label htmlFor="equipment-model">设备型号</label>
              <select
                id="equipment-model"
                value={searchEquipmentId ?? ''}
                onChange={(event) =>
                  setSearchEquipmentId(
                    event.target.value ? Number(event.target.value) : null,
                  )
                }
              >
                <option value="">请选择型号</option>
                {equipmentModels.map((model) => (
                  <option value={model.id} key={model.id}>
                    {model.model_code} · {model.manufacturer}
                  </option>
                ))}
              </select>
            </div>

            <div className="search-control query-control">
              <label htmlFor="search-query">问题</label>
              <textarea
                id="search-query"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="例如：设备没电时应该检查什么？"
                rows={3}
              />
            </div>

            <div className="search-control limit-control">
              <label htmlFor="search-limit">Top-K</label>
              <select
                id="search-limit"
                value={searchLimit}
                onChange={(event) => setSearchLimit(Number(event.target.value))}
              >
                {[3, 5, 8, 10].map((value) => (
                  <option value={value} key={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>

            <button
              className="search-submit"
              type="submit"
              disabled={searching || !searchEquipmentId}
            >
              {searching ? '检索中…' : '执行检索'}
            </button>
          </form>

          <div className="search-hints">
            <span>强过滤：published</span>
            <span>设备：{activeEquipment?.model_code ?? '未选择'}</span>
            <span>Rerank：vector 65% + rules 35%</span>
          </div>
        </section>

        {!searchResult ? (
          <section className="search-empty panel">
            <div>
              <strong>等待检索</strong>
              <span>
                结果将展示 Top-K Evidence、来源页码、Evidence ID 与三个调试分数。
              </span>
            </div>
          </section>
        ) : (
          <div className="search-layout">
            <aside className="debug-panel panel">
              <div className="debug-panel-head">
                <div>
                  <p className="eyebrow">DEBUG CONTEXT</p>
                  <h2>检索调试</h2>
                </div>
                <span className="result-count">
                  {searchResult.hits.length} hits
                </span>
              </div>

              <dl className="debug-metadata">
                <div>
                  <dt>设备型号</dt>
                  <dd>{activeEquipment?.model_code ?? searchResult.equipment_model_id}</dd>
                </div>
                <div>
                  <dt>粗召回</dt>
                  <dd>Top-{searchResult.rough_recall_limit}</dd>
                </div>
                <div>
                  <dt>Embedding</dt>
                  <dd title={searchResult.embedding_model}>
                    {searchResult.embedding_model.split('/').pop()}
                  </dd>
                </div>
                <div>
                  <dt>Collection</dt>
                  <dd>{searchResult.collection_name}</dd>
                </div>
              </dl>

              <div className="score-legend">
                <div>
                  <span className="score-dot vector" />
                  <div>
                    <strong>vector_score</strong>
                    <small>Qdrant cosine similarity</small>
                  </div>
                </div>
                <div>
                  <span className="score-dot rerank" />
                  <div>
                    <strong>rerank_score</strong>
                    <small>lexical / intent / section</small>
                  </div>
                </div>
                <div>
                  <span className="score-dot final" />
                  <div>
                    <strong>final_score</strong>
                    <small>最终排序分数</small>
                  </div>
                </div>
              </div>

              <div className="query-preview">
                <span>Query</span>
                <p>{searchResult.query}</p>
              </div>
            </aside>

            <section className="evidence-panel">
              <div className="evidence-title-row">
                <div>
                  <p className="eyebrow">TOP-K EVIDENCE</p>
                  <h2>召回证据</h2>
                </div>
                <span>
                  已按 final_score 从高到低排序
                </span>
              </div>

              <div className="evidence-list">
                {searchResult.hits.length === 0 ? (
                  <div className="search-empty panel">
                    没有符合当前设备型号和发布状态的证据。
                  </div>
                ) : (
                  searchResult.hits.map((hit, index) => (
                    <article className="evidence-card panel" key={`${hit.point_id}-${hit.block_id}`}>
                      <div className="evidence-rank">#{index + 1}</div>

                      <div className="evidence-main">
                        <div className="evidence-header">
                          <div>
                            <div className="evidence-tags">
                              <span className={`type-chip ${hit.block_type}`}>
                                {hit.block_type}
                              </span>
                              <span className="page-chip">
                                P{hit.page_start ?? '?'}
                                {hit.page_end && hit.page_end !== hit.page_start
                                  ? `–${hit.page_end}`
                                  : ''}
                              </span>
                              <span className="doc-chip">
                                {hit.title}
                                {hit.version ? ` · v${hit.version}` : ''}
                              </span>
                            </div>
                            <h3>{hit.section_path || '未命名章节'}</h3>
                          </div>
                          <code title={hit.evidence_id}>
                            {hit.evidence_id.slice(0, 18)}…
                          </code>
                        </div>

                        <p className="evidence-text">{hit.text}</p>

                        <div className="evidence-links">
                          <a
                            href={`/api/documents/${hit.document_id}/file`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            打开原始 PDF ↗
                          </a>
                          {hit.asset_id && (
                            <a
                              href={`/api/documents/${hit.document_id}/assets/${hit.asset_id}/file`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              查看关联 Asset #{hit.asset_id} ↗
                            </a>
                          )}
                          <span>Block #{hit.block_id}</span>
                        </div>
                      </div>

                      <div className="score-panel">
                        <div className="score-row">
                          <span>vector</span>
                          <strong>{formatScore(hit.vector_score)}</strong>
                          <div className="score-track">
                            <i
                              className="vector-bar"
                              style={{ width: `${Math.max(0, Math.min(100, hit.vector_score * 100))}%` }}
                            />
                          </div>
                        </div>
                        <div className="score-row">
                          <span>rerank</span>
                          <strong>{formatScore(hit.rerank_score)}</strong>
                          <div className="score-track">
                            <i
                              className="rerank-bar"
                              style={{ width: `${Math.max(0, Math.min(100, hit.rerank_score * 100))}%` }}
                            />
                          </div>
                        </div>
                        <div className="score-row final-score-row">
                          <span>final</span>
                          <strong>{formatScore(hit.final_score)}</strong>
                          <div className="score-track">
                            <i
                              className="final-bar"
                              style={{ width: `${Math.max(0, Math.min(100, hit.final_score * 100))}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    </article>
                  ))
                )}
              </div>
            </section>
          </div>
        )}
      </>
    )
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
          <button
            className={`nav-item ${page === 'documents' ? 'active' : ''}`}
            type="button"
            onClick={() => setPage('documents')}
          >
            <span>▦</span>
            文档管理
          </button>
          <button
            className={`nav-item ${page === 'search' ? 'active' : ''}`}
            type="button"
            onClick={() => setPage('search')}
          >
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
        {page === 'documents' ? renderDocumentPage() : renderSearchPage()}
      </main>
    </div>
  )
}

export default App
