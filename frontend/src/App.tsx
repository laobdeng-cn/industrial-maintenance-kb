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

type GroundedCitation = {
  index: number
  evidence_id: string
  document_id: number
  block_id: number
  title: string
  version: string | null
  section_path: string | null
  page_start: number | null
  page_end: number | null
  asset_id: number | null
  text: string
}

type GroundedAnswerResponse = {
  query_log_id: number | null
  query: string
  equipment_model_id: number
  grounded: boolean
  answer: string
  refusal_reason: string | null
  model: string | null
  grounding_threshold: number
  grounding_rerank_threshold: number
  top_final_score: number | null
  top_rerank_score: number | null
  decision_source: string
  deepseek_answerable: boolean | null
  deepseek_reason: string | null
  structured_evidence_support: boolean
  rerank_gate_bypassed: boolean
  embedding_model: string
  collection_name: string
  rough_recall_limit: number
  citations: GroundedCitation[]
  hits: SearchHit[]
}


type FeedbackRating = 'helpful' | 'unhelpful'

type AnswerFeedback = {
  id: number
  query_log_id: number
  rating: FeedbackRating
  reason: string | null
  comment: string | null
  created_at: string
  updated_at: string
}

type ReviewQueueItem = {
  id: number
  query_log_id: number
  status: 'pending' | 'accepted' | 'ignored'
  reviewer_note: string | null
  promoted_case_id: number | null
  created_at: string
  updated_at: string
}

type QueryTrace = {
  id: number
  query: string
  equipment_model_id: number
  grounded: boolean
  answer: string
  refusal_reason: string | null
  decision_source: string
  top_final_score: number | null
  top_rerank_score: number | null
  citations: GroundedCitation[]
  hits: SearchHit[]
  latency_ms: number
  created_at: string
  feedback: AnswerFeedback | null
  review_item: ReviewQueueItem | null
}

type AnalyticsBucket = {
  key: string
  label: string
  count: number
  percentage: number
}

type FeedbackTrendPoint = {
  date: string
  total_queries: number
  helpful: number
  unhelpful: number
  review_created: number
}

type ReviewSLAItem = {
  review_id: number
  query_log_id: number
  query: string
  equipment_model_id: number
  status: string
  created_at: string
  due_at: string
  age_hours: number
  sla_hours: number
  sla_state: 'on_track' | 'due_soon' | 'overdue' | 'resolved'
  feedback_rating: string | null
  feedback_reason: string | null
}

type FeedbackAnalytics = {
  window_days: number
  sla_hours: number
  total_queries: number
  grounded_count: number
  refused_count: number
  feedback_total: number
  helpful_count: number
  unhelpful_count: number
  helpful_rate: number | null
  avg_latency_ms: number | null
  review_total: number
  review_pending: number
  review_overdue: number
  review_due_soon: number
  review_resolved: number
  review_sla_met: number
  review_sla_breached: number
  review_sla_compliance_rate: number | null
  oldest_pending_hours: number | null
  decision_sources: AnalyticsBucket[]
  equipment_models: AnalyticsBucket[]
  trend: FeedbackTrendPoint[]
  review_sla_items: ReviewSLAItem[]
}

type QueryClusterMember = {
  query_log_id: number
  query: string
  equipment_model_id: number
  grounded: boolean
  feedback_rating: string | null
  review_status: string | null
  created_at: string
}

type QueryCluster = {
  cluster_id: number
  representative_query: string
  size: number
  unhelpful_count: number
  pending_review_count: number
  grounded_count: number
  equipment_model_ids: number[]
  members: QueryClusterMember[]
}

type QueryClusterResponse = {
  window_days: number
  similarity_threshold: number
  only_problematic: boolean
  sample_count: number
  cluster_count: number
  clusters: QueryCluster[]
}


type EvaluationCase = {
  id: number
  query: string
  equipment_model_id: number
  expected_evidence_ids: string[]
  allowed_citation_evidence_ids: string[]
  expected_answerable: boolean
  notes: string | null
  created_at: string
  updated_at: string
}

type EvaluationMetrics = {
  hit_at_k: number | null
  mrr: number | null
  refusal_accuracy: number | null
  answerability_accuracy: number | null
  citation_precision: number | null
  citation_recall: number | null
  citation_f1: number | null
  retrieval_case_count: number
  unanswerable_case_count: number
  error_count: number
}

type EvaluationResult = {
  id: number
  run_id: number
  case_id: number | null
  query: string
  equipment_model_id: number
  expected_evidence_ids: string[]
  allowed_citation_evidence_ids: string[]
  expected_answerable: boolean
  grounded: boolean
  refusal_reason: string | null
  answer: string
  hits: SearchHit[]
  citation_evidence_ids: string[]
  hit_at_k: boolean | null
  first_relevant_rank: number | null
  reciprocal_rank: number | null
  citation_precision: number | null
  citation_recall: number | null
  answerability_correct: boolean
  latency_ms: number
  error_message: string | null
  decision_trace: Record<string, unknown> | null
  created_at: string
}

type EvaluationRunParameterSnapshot = {
  snapshot_version?: number
  embedding_model?: string
  embedding_vector_size?: number
  collection_name?: string
  top_k?: number
  rough_recall_limit?: number
  vector_weight?: number
  rerank_weight?: number
  grounding_min_final_score?: number
  grounding_min_rerank_score?: number
  deepseek_model?: string
  app_env?: string
  [key: string]: string | number | boolean | null | undefined
}

type EvaluationRunSummary = {
  id: number
  status: string
  top_k: number
  total_cases: number
  completed_cases: number
  metrics: EvaluationMetrics | null
  parameter_snapshot: EvaluationRunParameterSnapshot | null
  started_at: string
  completed_at: string | null
  created_at: string
}

type EvaluationRun = EvaluationRunSummary & {
  results: EvaluationResult[]
}

type EvaluationComparisonValue = {
  baseline: number | null
  candidate: number | null
  delta: number | null
}

type EvaluationComparisonCount = {
  baseline: number
  candidate: number
  delta: number
}

type EvaluationComparisonResultSnapshot = {
  grounded: boolean
  answerability_correct: boolean
  hit_at_k: boolean | null
  first_relevant_rank: number | null
  reciprocal_rank: number | null
  citation_precision: number | null
  citation_recall: number | null
  latency_ms: number
  error_message: string | null
}

type EvaluationComparisonSample = {
  case_id: number | null
  query: string
  status: 'regressed' | 'improved' | 'mixed' | 'unchanged' | 'incomparable'
  comparable: boolean
  baseline_issue_codes: string[]
  candidate_issue_codes: string[]
  regression_reasons: string[]
  improvement_reasons: string[]
  baseline: EvaluationComparisonResultSnapshot
  candidate: EvaluationComparisonResultSnapshot
}

type EvaluationRunComparison = {
  baseline_run: EvaluationRunSummary
  candidate_run: EvaluationRunSummary
  metric_deltas: Record<string, EvaluationComparisonValue>
  failure_deltas: Record<string, EvaluationComparisonCount>
  matched_case_count: number
  baseline_only_case_count: number
  candidate_only_case_count: number
  regressed_count: number
  improved_count: number
  mixed_count: number
  unchanged_count: number
  incomparable_count: number
  samples: EvaluationComparisonSample[]
}


type EvaluationLeaderboardItem = {
  run_id: number
  status: string
  total_cases: number
  parameter_snapshot: EvaluationRunParameterSnapshot | null
  hit_at_k: number | null
  mrr: number | null
  refusal_accuracy: number | null
  answerability_accuracy: number | null
  citation_f1: number | null
  avg_latency_ms: number | null
  failure_count: number
  issue_counts: Record<string, number>
  created_at: string
}

type ThresholdEvidence = {
  rank: number
  evidence_id: string
  section_path: string | null
  text: string
  vector_score: number
  rerank_score: number
  final_score: number
}

type ThresholdErrorAnalysis = {
  result_id: number
  case_id: number | null
  query: string
  expected_answerable: boolean
  actual_grounded: boolean
  refusal_reason: string | null
  top_final_score: number | null
  top_rerank_score: number | null
  grounding_min_final_score: number | null
  grounding_min_rerank_score: number | null
  final_margin: number | null
  rerank_margin: number | null
  decision_source: string | null
  deepseek_answerable: boolean | null
  deepseek_reason: string | null
  structured_evidence_support: boolean | null
  rerank_gate_bypassed: boolean | null
  top_evidence: ThresholdEvidence[]
}

type EvaluationSweepResponse = {
  combination_count: number
  case_count: number
  estimated_case_executions: number
  runs: EvaluationRunSummary[]
}

type EvaluationHygieneGroup = {
  equipment_model_id: number
  normalized_query: string
  case_ids: number[]
  expected_answerable_values: boolean[]
  issue_codes: string[]
}

type EvaluationHygiene = {
  healthy: boolean
  total_cases: number
  duplicate_group_count: number
  conflict_group_count: number
  affected_case_ids: number[]
  groups: EvaluationHygieneGroup[]
}

type EvaluationSeedResponse = {
  equipment_model_id: number
  target_case_count: number
  created_count: number
  skipped_count: number
  created_case_ids: number[]
  skipped_case_ids: number[]
  cases: EvaluationCase[]
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

function formatPercent(value: number | null | undefined) {
  return value === null || value === undefined
    ? '—'
    : `${(value * 100).toFixed(1)}%`
}

function formatMetric(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value.toFixed(3)
}

function parseNumberGrid(
  value: string,
  options?: { integer?: boolean },
) {
  const values = value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .map(Number)

  if (
    values.length === 0 ||
    values.some((item) => !Number.isFinite(item)) ||
    (options?.integer && values.some((item) => !Number.isInteger(item)))
  ) {
    throw new Error('参数网格格式无效，请使用英文逗号分隔数字')
  }

  return Array.from(new Set(values))
}


type EvaluationIssueCode =
  | 'retrieval_miss'
  | 'ranking_error'
  | 'answerability_error'
  | 'citation_missing'
  | 'citation_false_positive'
  | 'execution_error'

type EvaluationIssue = {
  code: EvaluationIssueCode
  label: string
  description: string
  tone: 'danger' | 'warning'
}

const evaluationIssueMeta: Record<
  EvaluationIssueCode,
  Omit<EvaluationIssue, 'code'>
> = {
  retrieval_miss: {
    label: 'Retrieval Miss',
    description: '期望 Evidence 未进入当前 Top-K。',
    tone: 'danger',
  },
  ranking_error: {
    label: 'Ranking Error',
    description: '期望 Evidence 已召回，但没有排在第 1 位。',
    tone: 'warning',
  },
  answerability_error: {
    label: 'Answerability Error',
    description: '实际回答/拒答行为与 Golden Set 预期不一致。',
    tone: 'danger',
  },
  citation_missing: {
    label: 'Citation Missing',
    description: '期望 Evidence 已召回，但最终回答没有引用它。',
    tone: 'danger',
  },
  citation_false_positive: {
    label: 'Citation False Positive',
    description: '最终回答引用了 Allowed Citation Evidence 之外的 Evidence。',
    tone: 'warning',
  },
  execution_error: {
    label: 'Execution Error',
    description: '该样本在评测执行过程中发生异常。',
    tone: 'danger',
  },
}

function diagnoseEvaluationResult(
  result: EvaluationResult,
): EvaluationIssue[] {
  const issues: EvaluationIssue[] = []
  const expected = new Set(result.expected_evidence_ids)
  const allowed = new Set(
    result.allowed_citation_evidence_ids.length > 0
      ? result.allowed_citation_evidence_ids
      : result.expected_evidence_ids,
  )
  const hitIds = result.hits.map((hit) => hit.evidence_id)
  const citationIds = result.citation_evidence_ids
  const expectedHitRanks = hitIds
    .map((evidenceId, index) =>
      expected.has(evidenceId) ? index + 1 : null,
    )
    .filter((value): value is number => value !== null)
  const hasExpectedHit = expectedHitRanks.length > 0
  const hasExpectedCitation = citationIds.some((id) => expected.has(id))
  const hasExtraCitation = citationIds.some((id) => !allowed.has(id))

  const pushIssue = (code: EvaluationIssueCode) => {
    issues.push({ code, ...evaluationIssueMeta[code] })
  }

  if (result.error_message) {
    pushIssue('execution_error')
  }

  if (result.expected_answerable !== result.grounded) {
    pushIssue('answerability_error')
  }

  if (result.expected_answerable && expected.size > 0) {
    if (!hasExpectedHit) {
      pushIssue('retrieval_miss')
    } else if (Math.min(...expectedHitRanks) > 1) {
      pushIssue('ranking_error')
    }

    if (result.grounded && hasExpectedHit && !hasExpectedCitation) {
      pushIssue('citation_missing')
    }
  }

  if (result.grounded && citationIds.length > 0 && hasExtraCitation) {
    pushIssue('citation_false_positive')
  }

  return issues
}

function evaluationDiagnosisSummary(
  result: EvaluationResult,
  issues: EvaluationIssue[],
) {
  if (issues.length === 0) {
    return result.expected_answerable
      ? '链路健康：期望 Evidence 被正确召回、排序并用于引用。'
      : '链路健康：系统按预期拒答，未产生无依据引用。'
  }

  return issues.map((issue) => issue.description).join(' ')
}

function renderAnswerInline(text: string, keyPrefix: string) {
  return text
    .split(/(\[\d+\]|\*\*[^*]+\*\*|`[^`]+`)/g)
    .filter(Boolean)
    .map((part, index) => {
      const citationMatch = part.match(/^\[(\d+)\]$/)
      if (citationMatch) {
        const citation = Number(citationMatch[1])
        return (
          <a
            className="answer-citation"
            href={`#evidence-${citation}`}
            key={`${keyPrefix}-citation-${index}`}
          >
            {part}
          </a>
        )
      }

      if (part.startsWith('**') && part.endsWith('**')) {
        return (
          <strong key={`${keyPrefix}-strong-${index}`}>
            {renderAnswerInline(
              part.slice(2, -2),
              `${keyPrefix}-strong-${index}`,
            )}
          </strong>
        )
      }

      if (part.startsWith('`') && part.endsWith('`')) {
        return (
          <code
            className="answer-inline-code"
            key={`${keyPrefix}-code-${index}`}
          >
            {part.slice(1, -1)}
          </code>
        )
      }

      return <span key={`${keyPrefix}-text-${index}`}>{part}</span>
    })
}

function renderMarkdownAnswer(answer: string) {
  const lines = answer.replace(/\r\n/g, '\n').split('\n')
  const nodes: import('react').ReactNode[] = []
  let paragraph: string[] = []
  let listItems: string[] = []

  const flushParagraph = () => {
    if (paragraph.length === 0) return
    const text = paragraph.join(' ')
    const key = `paragraph-${nodes.length}`
    nodes.push(
      <p key={key}>
        {renderAnswerInline(text, key)}
      </p>,
    )
    paragraph = []
  }

  const flushList = () => {
    if (listItems.length === 0) return
    const key = `list-${nodes.length}`
    nodes.push(
      <ul key={key}>
        {listItems.map((item, index) => (
          <li key={`${key}-${index}`}>
            {renderAnswerInline(item, `${key}-${index}`)}
          </li>
        ))}
      </ul>,
    )
    listItems = []
  }

  lines.forEach((line) => {
    const trimmed = line.trim()

    if (!trimmed) {
      flushParagraph()
      flushList()
      return
    }

    const bulletMatch = trimmed.match(/^[-*]\s+(.+)$/)
    if (bulletMatch) {
      flushParagraph()
      listItems.push(bulletMatch[1])
      return
    }

    flushList()

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/)
    if (headingMatch) {
      flushParagraph()
      const key = `heading-${nodes.length}`
      nodes.push(
        <h3 className="answer-markdown-heading" key={key}>
          {renderAnswerInline(headingMatch[2], key)}
        </h3>,
      )
      return
    }

    paragraph.push(trimmed)
  })

  flushParagraph()
  flushList()

  return <div className="answer-markdown">{nodes}</div>
}

function App() {
  const [page, setPage] = useState<'documents' | 'search' | 'evaluation' | 'feedback'>('documents')
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
  const [answerResult, setAnswerResult] = useState<GroundedAnswerResponse | null>(null)
  const [answerFeedbackRating, setAnswerFeedbackRating] = useState<FeedbackRating | null>(null)

  const [feedbackLogs, setFeedbackLogs] = useState<QueryTrace[]>([])
  const [feedbackAnalytics, setFeedbackAnalytics] = useState<FeedbackAnalytics | null>(null)
  const [feedbackClusters, setFeedbackClusters] = useState<QueryClusterResponse | null>(null)
  const [feedbackAnalyticsDays, setFeedbackAnalyticsDays] = useState(7)
  const [feedbackClusterDays, setFeedbackClusterDays] = useState(30)
  const [feedbackLoading, setFeedbackLoading] = useState(false)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)
  const [feedbackNotice, setFeedbackNotice] = useState<string | null>(null)
  const [feedbackSubmittingId, setFeedbackSubmittingId] = useState<number | null>(null)
  const [reviewUpdatingId, setReviewUpdatingId] = useState<number | null>(null)

  const [evaluationCases, setEvaluationCases] = useState<EvaluationCase[]>([])
  const [evaluationRuns, setEvaluationRuns] = useState<EvaluationRunSummary[]>([])
  const [selectedEvaluationRun, setSelectedEvaluationRun] = useState<EvaluationRun | null>(null)
  const [evaluationLoading, setEvaluationLoading] = useState(false)
  const [evaluationRunning, setEvaluationRunning] = useState(false)
  const [evaluationError, setEvaluationError] = useState<string | null>(null)
  const [evaluationNotice, setEvaluationNotice] = useState<string | null>(null)
  const [evaluationTopK, setEvaluationTopK] = useState(5)
  const [editingEvaluationCaseId, setEditingEvaluationCaseId] = useState<number | null>(null)
  const [evaluationCaseQuery, setEvaluationCaseQuery] = useState('')
  const [evaluationCaseEquipmentId, setEvaluationCaseEquipmentId] = useState<number | null>(null)
  const [evaluationCaseAnswerable, setEvaluationCaseAnswerable] = useState(true)
  const [evaluationCaseNotes, setEvaluationCaseNotes] = useState('')
  const [evaluationEvidenceHits, setEvaluationEvidenceHits] = useState<SearchHit[]>([])
  const [selectedEvaluationEvidenceIds, setSelectedEvaluationEvidenceIds] = useState<string[]>([])
  const [selectedAllowedCitationIds, setSelectedAllowedCitationIds] = useState<string[]>([])
  const [evaluationHygiene, setEvaluationHygiene] = useState<EvaluationHygiene | null>(null)
  const [evaluationEvidenceLoading, setEvaluationEvidenceLoading] = useState(false)
  const [evaluationSaving, setEvaluationSaving] = useState(false)
  const [evaluationSeeding, setEvaluationSeeding] = useState(false)
  const [evaluationRunningCaseId, setEvaluationRunningCaseId] = useState<number | null>(null)
  const [baselineRunId, setBaselineRunId] = useState<number | null>(null)
  const [candidateRunId, setCandidateRunId] = useState<number | null>(null)
  const [runComparison, setRunComparison] = useState<EvaluationRunComparison | null>(null)
  const [comparisonLoading, setComparisonLoading] = useState(false)
  const [evaluationRoughRecallLimit, setEvaluationRoughRecallLimit] = useState(20)
  const [evaluationVectorWeight, setEvaluationVectorWeight] = useState(0.65)
  const [evaluationRerankWeight, setEvaluationRerankWeight] = useState(0.35)
  const [evaluationGroundingFinal, setEvaluationGroundingFinal] = useState(0.35)
  const [evaluationGroundingRerank, setEvaluationGroundingRerank] = useState(0.15)
  const [sweepTopKValues, setSweepTopKValues] = useState('2,3,5,8')
  const [sweepFinalValues, setSweepFinalValues] = useState('0.30,0.35,0.40,0.45')
  const [sweepRerankValues, setSweepRerankValues] = useState('0.10,0.15,0.20')
  const [sweepRunning, setSweepRunning] = useState(false)
  const [evaluationLeaderboard, setEvaluationLeaderboard] = useState<EvaluationLeaderboardItem[]>([])
  const [leaderboardSort, setLeaderboardSort] = useState<
    'citation_f1' | 'answerability_accuracy' | 'hit_at_k' | 'mrr' | 'avg_latency_ms' | 'failure_count'
  >('citation_f1')
  const [thresholdErrors, setThresholdErrors] = useState<ThresholdErrorAnalysis[]>([])

  const selected = useMemo(
    () => documents.find((item) => item.id === selectedId) ?? null,
    [documents, selectedId],
  )

  const sortedEvaluationLeaderboard = useMemo(() => {
    const direction =
      leaderboardSort === 'avg_latency_ms' ||
      leaderboardSort === 'failure_count'
        ? 1
        : -1

    return [...evaluationLeaderboard].sort((left, right) => {
      const a = left[leaderboardSort]
      const b = right[leaderboardSort]
      if (a === null && b === null) return right.run_id - left.run_id
      if (a === null) return 1
      if (b === null) return -1
      if (a === b) return right.run_id - left.run_id
      return (Number(a) - Number(b)) * direction
    })
  }, [evaluationLeaderboard, leaderboardSort])

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
    if (page !== 'evaluation') return

    let cancelled = false
    setEvaluationLoading(true)
    setEvaluationError(null)

    Promise.all([
      api<EvaluationCase[]>('/api/evaluation/cases'),
      api<EvaluationRunSummary[]>('/api/evaluation/runs'),
      api<EvaluationLeaderboardItem[]>('/api/evaluation/runs/leaderboard?limit=30'),
      api<EvaluationHygiene>('/api/evaluation/cases/hygiene'),
    ])
      .then(([cases, runs, leaderboard, hygiene]) => {
        if (cancelled) return
        setEvaluationCases(cases)
        setEvaluationRuns(runs)
        setEvaluationLeaderboard(leaderboard)
        setEvaluationHygiene(hygiene)
        if (runs.length > 0) {
          setCandidateRunId((current) => current ?? runs[0].id)
        }
        if (runs.length > 1) {
          setBaselineRunId((current) => current ?? runs[1].id)
        }
      })
      .catch((err) => {
        if (cancelled) return
        setEvaluationError(
          err instanceof Error ? err.message : '加载评测中心失败',
        )
      })
      .finally(() => {
        if (!cancelled) setEvaluationLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [page])


  async function loadFeedbackLogs() {
    setFeedbackLoading(true)
    setFeedbackError(null)
    try {
      const [logs, analytics, clusters] = await Promise.all([
        api<QueryTrace[]>('/api/feedback/query-logs?limit=50'),
        api<FeedbackAnalytics>(`/api/feedback/analytics?days=${feedbackAnalyticsDays}`),
        api<QueryClusterResponse>(
          `/api/feedback/clusters?days=${feedbackClusterDays}&limit=100&only_problematic=true`,
        ),
      ])
      setFeedbackLogs(logs)
      setFeedbackAnalytics(analytics)
      setFeedbackClusters(clusters)
    } catch (err) {
      setFeedbackError(err instanceof Error ? err.message : '加载反馈运营数据失败')
    } finally {
      setFeedbackLoading(false)
    }
  }

  async function submitAnswerFeedback(queryLogId: number, rating: FeedbackRating) {
    let comment: string | null = null
    if (rating === 'unhelpful') {
      comment = window.prompt('可选：说明问题原因或改进建议', '')
      if (comment === null) return
    }

    setFeedbackSubmittingId(queryLogId)
    setFeedbackError(null)
    setFeedbackNotice(null)
    try {
      const updated = await api<QueryTrace>(
        `/api/feedback/query-logs/${queryLogId}/feedback`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            rating,
            reason: rating === 'unhelpful' ? 'needs_review' : 'helpful',
            comment: comment?.trim() || null,
          }),
        },
      )
      if (answerResult?.query_log_id === queryLogId) {
        setAnswerFeedbackRating(rating)
      }
      setFeedbackLogs((current) => {
        const exists = current.some((item) => item.id === updated.id)
        return exists
          ? current.map((item) => (item.id === updated.id ? updated : item))
          : [updated, ...current]
      })
      setFeedbackNotice(
        rating === 'unhelpful'
          ? '已记录负反馈，并加入 Review Queue。'
          : '已记录有帮助反馈。',
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : '提交反馈失败'
      setFeedbackError(message)
      if (page === 'search') setSearchError(message)
    } finally {
      setFeedbackSubmittingId(null)
    }
  }

  async function updateReviewStatus(
    item: ReviewQueueItem,
    statusValue: 'pending' | 'accepted' | 'ignored',
  ) {
    const note = window.prompt('可选：填写 reviewer note', item.reviewer_note ?? '')
    if (note === null) return

    setReviewUpdatingId(item.id)
    setFeedbackError(null)
    setFeedbackNotice(null)
    try {
      await api<ReviewQueueItem>(`/api/feedback/review-queue/${item.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status: statusValue,
          reviewer_note: note.trim() || null,
        }),
      })
      setFeedbackNotice(`Review #${item.id} 已更新为 ${statusValue}。`)
      await loadFeedbackLogs()
    } catch (err) {
      setFeedbackError(err instanceof Error ? err.message : '更新 Review Queue 失败')
    } finally {
      setReviewUpdatingId(null)
    }
  }

  async function promoteReviewToGoldenSet(item: ReviewQueueItem) {
    setReviewUpdatingId(item.id)
    setFeedbackError(null)
    setFeedbackNotice(null)
    try {
      const updated = await api<ReviewQueueItem>(
        `/api/feedback/review-queue/${item.id}/promote`,
        { method: 'POST' },
      )
      setFeedbackNotice(
        updated.promoted_case_id
          ? `已加入 Golden Set：Case #${updated.promoted_case_id}。`
          : 'Review 已处理。',
      )
      await loadFeedbackLogs()
    } catch (err) {
      setFeedbackError(err instanceof Error ? err.message : '加入 Golden Set 失败')
    } finally {
      setReviewUpdatingId(null)
    }
  }

  useEffect(() => {
    if (page !== 'feedback') return
    void loadFeedbackLogs()
  }, [page, feedbackAnalyticsDays, feedbackClusterDays])

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
    setAnswerResult(null)
    setAnswerFeedbackRating(null)

    try {
      const result = await api<GroundedAnswerResponse>('/api/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: searchQuery.trim(),
          equipment_model_id: searchEquipmentId,
          limit: searchLimit,
        }),
      })
      setAnswerResult(result)
      setSearchResult({
        query: result.query,
        equipment_model_id: result.equipment_model_id,
        embedding_model: result.embedding_model,
        collection_name: result.collection_name,
        rough_recall_limit: result.rough_recall_limit,
        hits: result.hits,
      })
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : '问答失败')
    } finally {
      setSearching(false)
    }
  }


  async function refreshEvaluationData() {
    const [cases, runs, leaderboard, hygiene] = await Promise.all([
      api<EvaluationCase[]>('/api/evaluation/cases'),
      api<EvaluationRunSummary[]>('/api/evaluation/runs'),
      api<EvaluationLeaderboardItem[]>('/api/evaluation/runs/leaderboard?limit=30'),
      api<EvaluationHygiene>('/api/evaluation/cases/hygiene'),
    ])
    setEvaluationCases(cases)
    setEvaluationRuns(runs)
    setEvaluationLeaderboard(leaderboard)
    setEvaluationHygiene(hygiene)
    if (runs.length > 0) {
      setCandidateRunId((current) => current ?? runs[0].id)
    }
    if (runs.length > 1) {
      setBaselineRunId((current) => current ?? runs[1].id)
    }
  }

  function resetEvaluationEditor() {
    setEditingEvaluationCaseId(null)
    setEvaluationCaseQuery('')
    setEvaluationCaseEquipmentId(null)
    setEvaluationCaseAnswerable(true)
    setEvaluationCaseNotes('')
    setEvaluationEvidenceHits([])
    setSelectedEvaluationEvidenceIds([])
    setSelectedAllowedCitationIds([])
  }

  function beginEditEvaluationCase(item: EvaluationCase) {
    setEditingEvaluationCaseId(item.id)
    setEvaluationCaseQuery(item.query)
    setEvaluationCaseEquipmentId(item.equipment_model_id)
    setEvaluationCaseAnswerable(item.expected_answerable)
    setEvaluationCaseNotes(item.notes ?? '')
    setSelectedEvaluationEvidenceIds(item.expected_evidence_ids)
    setSelectedAllowedCitationIds(
      item.allowed_citation_evidence_ids.length > 0
        ? item.allowed_citation_evidence_ids
        : item.expected_evidence_ids,
    )
    setEvaluationEvidenceHits([])
    setEvaluationError(null)
    setEvaluationNotice(`正在编辑评测用例 #${item.id}。`)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function toggleEvaluationEvidence(evidenceId: string) {
    setSelectedEvaluationEvidenceIds((current) => {
      const selecting = !current.includes(evidenceId)
      if (selecting) {
        setSelectedAllowedCitationIds((allowed) =>
          allowed.includes(evidenceId)
            ? allowed
            : [...allowed, evidenceId],
        )
        return [...current, evidenceId]
      }
      return current.filter((value) => value !== evidenceId)
    })
  }

  function toggleAllowedCitationEvidence(evidenceId: string) {
    if (selectedEvaluationEvidenceIds.includes(evidenceId)) {
      return
    }
    setSelectedAllowedCitationIds((current) =>
      current.includes(evidenceId)
        ? current.filter((value) => value !== evidenceId)
        : [...current, evidenceId],
    )
  }

  async function handleRetrieveEvaluationEvidence() {
    if (!evaluationCaseEquipmentId) {
      setEvaluationError('请先选择设备型号')
      return
    }
    if (!evaluationCaseQuery.trim()) {
      setEvaluationError('请先输入问题')
      return
    }

    setEvaluationEvidenceLoading(true)
    setEvaluationError(null)
    setEvaluationNotice(null)

    try {
      const result = await api<SearchResponse>('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: evaluationCaseQuery.trim(),
          equipment_model_id: evaluationCaseEquipmentId,
          limit: 10,
        }),
      })
      setEvaluationEvidenceHits(result.hits)
      setEvaluationNotice(
        result.hits.length
          ? `已召回 ${result.hits.length} 条 Evidence，可勾选作为 Golden Set 标注。`
          : '当前条件没有召回 Evidence。',
      )
    } catch (err) {
      setEvaluationError(
        err instanceof Error ? err.message : '召回 Evidence 失败',
      )
    } finally {
      setEvaluationEvidenceLoading(false)
    }
  }

  async function handleSaveEvaluationCase(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    if (!evaluationCaseEquipmentId) {
      setEvaluationError('请选择设备型号')
      return
    }
    if (!evaluationCaseQuery.trim()) {
      setEvaluationError('请输入评测问题')
      return
    }
    if (
      evaluationCaseAnswerable &&
      selectedEvaluationEvidenceIds.length === 0
    ) {
      setEvaluationError(
        '期望可回答的用例请至少选择一条 Expected Evidence。',
      )
      return
    }

    setEvaluationSaving(true)
    setEvaluationError(null)
    setEvaluationNotice(null)

    const payload = {
      query: evaluationCaseQuery.trim(),
      equipment_model_id: evaluationCaseEquipmentId,
      expected_evidence_ids: evaluationCaseAnswerable
        ? selectedEvaluationEvidenceIds
        : [],
      allowed_citation_evidence_ids: evaluationCaseAnswerable
        ? selectedAllowedCitationIds
        : [],
      expected_answerable: evaluationCaseAnswerable,
      notes: evaluationCaseNotes.trim() || null,
    }

    try {
      if (editingEvaluationCaseId) {
        await api<EvaluationCase>(
          `/api/evaluation/cases/${editingEvaluationCaseId}`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          },
        )
        setEvaluationNotice(
          `评测用例 #${editingEvaluationCaseId} 已更新。`,
        )
      } else {
        await api<EvaluationCase>('/api/evaluation/cases', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
        setEvaluationNotice('评测用例已创建。')
      }

      resetEvaluationEditor()
      await refreshEvaluationData()
    } catch (err) {
      setEvaluationError(
        err instanceof Error
          ? err.message
          : editingEvaluationCaseId
            ? '更新评测用例失败'
            : '创建评测用例失败',
      )
    } finally {
      setEvaluationSaving(false)
    }
  }

  async function handleSeedGoldenSet() {
    setEvaluationSeeding(true)
    setEvaluationError(null)
    setEvaluationNotice(null)

    try {
      const result = await api<EvaluationSeedResponse>(
        '/api/evaluation/cases/seed-im1200',
        { method: 'POST' },
      )
      setEvaluationNotice(
        result.created_count > 0
          ? `已补充 ${result.created_count} 条 IM-1200 Golden Set，用例总数目标为 ${result.target_case_count} 条。`
          : 'IM-1200 Golden Set 已经包含这组基准用例。',
      )
      await refreshEvaluationData()
    } catch (err) {
      setEvaluationError(
        err instanceof Error ? err.message : '补充 Golden Set 失败',
      )
    } finally {
      setEvaluationSeeding(false)
    }
  }

  async function handleDeleteEvaluationCase(caseId: number) {
    if (!window.confirm('确认删除这条评测用例？历史评测结果会保留快照。')) {
      return
    }

    setEvaluationError(null)
    setEvaluationNotice(null)

    try {
      await api<void>(`/api/evaluation/cases/${caseId}`, {
        method: 'DELETE',
      })
      setEvaluationNotice('评测用例已删除。')
      await refreshEvaluationData()
    } catch (err) {
      setEvaluationError(
        err instanceof Error ? err.message : '删除评测用例失败',
      )
    }
  }

  function currentEvaluationRunPayload(caseIds?: number[]) {
    return {
      top_k: evaluationTopK,
      case_ids: caseIds,
      rough_recall_limit: evaluationRoughRecallLimit,
      vector_weight: evaluationVectorWeight,
      rerank_weight: evaluationRerankWeight,
      grounding_min_final_score: evaluationGroundingFinal,
      grounding_min_rerank_score: evaluationGroundingRerank,
    }
  }

  async function loadThresholdErrors(runId: number) {
    const rows = await api<ThresholdErrorAnalysis[]>(
      `/api/evaluation/runs/${runId}/threshold-errors`,
    )
    setThresholdErrors(rows)
  }

  async function openEvaluationRun(runId: number) {
    setEvaluationError(null)
    try {
      const [run, errors] = await Promise.all([
        api<EvaluationRun>(`/api/evaluation/runs/${runId}`),
        api<ThresholdErrorAnalysis[]>(
          `/api/evaluation/runs/${runId}/threshold-errors`,
        ),
      ])
      setSelectedEvaluationRun(run)
      setThresholdErrors(errors)
    } catch (err) {
      setEvaluationError(
        err instanceof Error ? err.message : '加载评测运行详情失败',
      )
    }
  }

  async function handleRunEvaluation() {
    if (evaluationCases.length === 0) {
      setEvaluationError('请先创建至少一条评测用例')
      return
    }

    setEvaluationRunning(true)
    setEvaluationError(null)
    setEvaluationNotice(null)

    try {
      const run = await api<EvaluationRun>('/api/evaluation/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentEvaluationRunPayload()),
      })
      setSelectedEvaluationRun(run)
      await loadThresholdErrors(run.id)
      setBaselineRunId((current) => current ?? candidateRunId ?? evaluationRuns[0]?.id ?? null)
      setCandidateRunId(run.id)
      setRunComparison(null)
      setEvaluationNotice(`评测 Run #${run.id} 已完成。`)
      await refreshEvaluationData()
    } catch (err) {
      setEvaluationError(
        err instanceof Error ? err.message : '执行评测失败',
      )
    } finally {
      setEvaluationRunning(false)
    }
  }


  async function handleRunSingleEvaluation(item: EvaluationCase) {
    setEvaluationRunningCaseId(item.id)
    setEvaluationError(null)
    setEvaluationNotice(null)

    try {
      const run = await api<EvaluationRun>('/api/evaluation/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentEvaluationRunPayload([item.id])),
      })
      setSelectedEvaluationRun(run)
      await loadThresholdErrors(run.id)
      setBaselineRunId((current) => current ?? candidateRunId ?? evaluationRuns[0]?.id ?? null)
      setCandidateRunId(run.id)
      setRunComparison(null)
      setEvaluationNotice(
        `用例 #${item.id} 已完成单条评测，Run #${run.id}。`,
      )
      await refreshEvaluationData()
    } catch (err) {
      setEvaluationError(
        err instanceof Error ? err.message : '执行单条评测失败',
      )
    } finally {
      setEvaluationRunningCaseId(null)
    }
  }


  async function handleRunSweep() {
    if (evaluationCases.length === 0) {
      setEvaluationError('请先创建至少一条评测用例')
      return
    }

    let topKValues: number[]
    let finalValues: number[]
    let rerankValues: number[]
    try {
      topKValues = parseNumberGrid(sweepTopKValues, { integer: true })
      finalValues = parseNumberGrid(sweepFinalValues)
      rerankValues = parseNumberGrid(sweepRerankValues)
    } catch (err) {
      setEvaluationError(
        err instanceof Error ? err.message : '参数网格格式错误',
      )
      return
    }

    const combinationCount =
      topKValues.length * finalValues.length * rerankValues.length
    const caseExecutions = combinationCount * evaluationCases.length

    if (combinationCount > 64) {
      setEvaluationError('单次 Sweep 最多 64 组参数组合')
      return
    }

    if (
      caseExecutions > 48 &&
      !window.confirm(
        `本次 Sweep 将执行 ${combinationCount} 个 Run，共约 ${caseExecutions} 个样本调用，可能产生较多 DeepSeek 请求。确认继续？`,
      )
    ) {
      return
    }

    setSweepRunning(true)
    setEvaluationError(null)
    setEvaluationNotice(null)

    try {
      const result = await api<EvaluationSweepResponse>(
        '/api/evaluation/sweeps',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            top_k_values: topKValues,
            grounding_min_final_score_values: finalValues,
            grounding_min_rerank_score_values: rerankValues,
            rough_recall_limit: evaluationRoughRecallLimit,
            vector_weight: evaluationVectorWeight,
            rerank_weight: evaluationRerankWeight,
          }),
        },
      )

      const latest = result.runs[result.runs.length - 1]
      setEvaluationNotice(
        `Sweep 完成：${result.combination_count} 个 Run，${result.estimated_case_executions} 次样本执行。`,
      )
      await refreshEvaluationData()
      if (latest) {
        await openEvaluationRun(latest.id)
        setCandidateRunId(latest.id)
      }
    } catch (err) {
      setEvaluationError(
        err instanceof Error ? err.message : '参数 Sweep 执行失败',
      )
    } finally {
      setSweepRunning(false)
    }
  }

  async function handleCompareEvaluationRuns() {
    if (!baselineRunId || !candidateRunId) {
      setEvaluationError('请选择 Baseline 和 Candidate Run')
      return
    }
    if (baselineRunId === candidateRunId) {
      setEvaluationError('Baseline 和 Candidate 不能是同一个 Run')
      return
    }

    setComparisonLoading(true)
    setEvaluationError(null)

    try {
      const comparison = await api<EvaluationRunComparison>(
        `/api/evaluation/runs/compare?baseline_run_id=${baselineRunId}&candidate_run_id=${candidateRunId}`,
      )
      setRunComparison(comparison)
    } catch (err) {
      setEvaluationError(
        err instanceof Error ? err.message : 'Run 对比失败',
      )
    } finally {
      setComparisonLoading(false)
    }
  }


  function renderFeedbackPage() {
    const pendingCount = feedbackLogs.filter(
      (item) => item.review_item?.status === 'pending',
    ).length
    const helpfulCount = feedbackLogs.filter(
      (item) => item.feedback?.rating === 'helpful',
    ).length
    const unhelpfulCount = feedbackLogs.filter(
      (item) => item.feedback?.rating === 'unhelpful',
    ).length

    return (
      <>
        <header className="topbar">
          <div>
            <p className="eyebrow">PHASE D.1 · FEEDBACK LOOP</p>
            <h1>反馈与审查</h1>
            <p className="subtitle">
              查看 Query Trace、用户反馈与 Review Queue，并将失败样本沉淀到 Golden Set。
            </p>
          </div>
          <button
            className="ghost-link trace-refresh"
            type="button"
            onClick={() => void loadFeedbackLogs()}
            disabled={feedbackLoading}
          >
            {feedbackLoading ? '刷新中…' : '刷新 Trace ↻'}
          </button>
        </header>

        {feedbackError && <div className="alert error">{feedbackError}</div>}
        {feedbackNotice && <div className="alert success">{feedbackNotice}</div>}

        <section className="trace-summary-grid">
          <div className="panel trace-summary-card">
            <span>QUERY TRACE</span>
            <strong>{feedbackLogs.length}</strong>
            <small>最近 50 条</small>
          </div>
          <div className="panel trace-summary-card warning">
            <span>PENDING REVIEW</span>
            <strong>{pendingCount}</strong>
            <small>等待人工审查</small>
          </div>
          <div className="panel trace-summary-card success">
            <span>HELPFUL</span>
            <strong>{helpfulCount}</strong>
            <small>正反馈</small>
          </div>
          <div className="panel trace-summary-card danger">
            <span>UNHELPFUL</span>
            <strong>{unhelpfulCount}</strong>
            <small>负反馈</small>
          </div>
        </section>

        <section className="trace-board">
          <div className="trace-board-head">
            <div>
              <p className="eyebrow">QUERY TRACE + REVIEW QUEUE</p>
              <h2>最近问答</h2>
            </div>
            <span>负反馈自动进入 pending Review Queue</span>
          </div>

          {feedbackLoading && feedbackLogs.length === 0 ? (
            <div className="search-empty panel">正在加载 Query Trace…</div>
          ) : feedbackLogs.length === 0 ? (
            <div className="search-empty panel">
              还没有 Query Trace。先到“检索问答”生成一次回答。
            </div>
          ) : (
            <div className="trace-list">
              {feedbackLogs.map((trace) => {
                const equipment = equipmentModels.find(
                  (model) => model.id === trace.equipment_model_id,
                )
                const review = trace.review_item
                return (
                  <article className="panel trace-card" key={trace.id}>
                    <div className="trace-card-head">
                      <div>
                        <div className="trace-badges">
                          <span className="trace-id">Trace #{trace.id}</span>
                          <span className={`answer-status ${trace.grounded ? 'ok' : 'warning'}`}>
                            {trace.grounded ? 'Grounded' : 'Refused'}
                          </span>
                          {trace.feedback && (
                            <span className={`feedback-chip ${trace.feedback.rating}`}>
                              {trace.feedback.rating === 'helpful' ? '👍 helpful' : '👎 unhelpful'}
                            </span>
                          )}
                          {review && (
                            <span className={`review-chip ${review.status}`}>
                              Review · {review.status}
                            </span>
                          )}
                        </div>
                        <h3>{trace.query}</h3>
                        <span>
                          {equipment?.model_code ?? `Equipment #${trace.equipment_model_id}`}
                          {' · '}
                          {formatDate(trace.created_at)}
                          {' · '}
                          {trace.latency_ms} ms
                        </span>
                      </div>
                      <div className="trace-score-box">
                        <span>FINAL</span>
                        <strong>{trace.top_final_score === null ? '—' : formatScore(trace.top_final_score)}</strong>
                        <span>RERANK</span>
                        <strong>{trace.top_rerank_score === null ? '—' : formatScore(trace.top_rerank_score)}</strong>
                      </div>
                    </div>

                    <div className="trace-grid">
                      <section>
                        <h4>AI 回答</h4>
                        <div className="trace-answer">{renderMarkdownAnswer(trace.answer)}</div>
                        {trace.refusal_reason && (
                          <code className="trace-refusal">reason: {trace.refusal_reason}</code>
                        )}
                      </section>
                      <section>
                        <h4>Gate 决策</h4>
                        <dl className="trace-decision">
                          <div>
                            <dt>Decision source</dt>
                            <dd>{trace.decision_source}</dd>
                          </div>
                          <div>
                            <dt>Evidence</dt>
                            <dd>{trace.citations.length} citations / {trace.hits.length} hits</dd>
                          </div>
                        </dl>
                      </section>
                    </div>

                    <div className="trace-evidence">
                      <strong>Evidence</strong>
                      {trace.citations.length > 0 ? (
                        trace.citations.map((citation) => (
                          <span key={citation.evidence_id}>
                            [{citation.index}] {citation.section_path || citation.title}
                            {' · '}P{citation.page_start ?? '?'}
                            {' · '}<code>{citation.evidence_id.slice(0, 12)}…</code>
                          </span>
                        ))
                      ) : (
                        <span>当前回答没有 Citation Evidence。</span>
                      )}
                    </div>

                    {trace.feedback?.comment && (
                      <div className="trace-comment">
                        <strong>反馈说明</strong>
                        <span>{trace.feedback.comment}</span>
                      </div>
                    )}

                    <div className="trace-actions">
                      <button
                        type="button"
                        className="primary-outline-button"
                        disabled={feedbackSubmittingId === trace.id}
                        onClick={() => void submitAnswerFeedback(trace.id, 'helpful')}
                      >
                        👍 有帮助
                      </button>
                      <button
                        type="button"
                        className="danger-button"
                        disabled={feedbackSubmittingId === trace.id}
                        onClick={() => void submitAnswerFeedback(trace.id, 'unhelpful')}
                      >
                        👎 需审查
                      </button>

                      {review?.status === 'pending' && (
                        <>
                          <button
                            type="button"
                            className="primary-outline-button"
                            disabled={reviewUpdatingId === review.id}
                            onClick={() => void promoteReviewToGoldenSet(review)}
                          >
                            加入 Golden Set
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            disabled={reviewUpdatingId === review.id}
                            onClick={() => void updateReviewStatus(review, 'ignored')}
                          >
                            忽略
                          </button>
                        </>
                      )}

                      {review?.status === 'ignored' && (
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={reviewUpdatingId === review.id}
                          onClick={() => void updateReviewStatus(review, 'pending')}
                        >
                          重新打开
                        </button>
                      )}

                      {review?.status === 'accepted' && (
                        <span className="promoted-case">
                          {review.promoted_case_id
                            ? `Golden Set Case #${review.promoted_case_id}`
                            : '已接受'}
                        </span>
                      )}
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </section>
      </>
    )
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
              {searching ? '生成中…' : '生成回答'}
            </button>
          </form>

          <div className="search-hints">
            <span>强过滤：published</span>
            <span>设备：{activeEquipment?.model_code ?? '未选择'}</span>
            <span>Rerank：vector 65% + rules 35%</span>
            <span>Answer：DeepSeek + grounded citations</span>
          </div>
        </section>

        {answerResult && (
          <section className={`answer-card panel ${answerResult.grounded ? 'grounded' : 'refused'}`}>
            <div className="answer-card-head">
              <div>
                <p className="eyebrow">GROUNDED ANSWER</p>
                <h2>AI 回答</h2>
              </div>
              <div className="answer-status-group">
                <span className={`answer-status ${answerResult.grounded ? 'ok' : 'warning'}`}>
                  {answerResult.grounded ? 'Grounded' : 'Evidence insufficient'}
                </span>
                {answerResult.model && <span className="answer-model">{answerResult.model}</span>}
              </div>
            </div>

            <div className="answer-body">
              <div className="answer-text">{renderMarkdownAnswer(answerResult.answer)}</div>
              <div className="answer-confidence">
                <div className="answer-confidence-metric">
                  <span>Top final_score</span>
                  <strong>
                    {answerResult.top_final_score === null
                      ? '—'
                      : formatScore(answerResult.top_final_score)}
                  </strong>
                  <small>
                    阈值 {formatScore(answerResult.grounding_threshold)}
                  </small>
                </div>
                <div className="answer-confidence-metric">
                  <span>Top rerank_score</span>
                  <strong>
                    {answerResult.top_rerank_score === null
                      ? '—'
                      : formatScore(answerResult.top_rerank_score)}
                  </strong>
                  <small>
                    软阈值 {formatScore(answerResult.grounding_rerank_threshold)}
                  </small>
                </div>
                <div className="answer-confidence-metric">
                  <span>Decision source</span>
                  <strong>{answerResult.decision_source}</strong>
                  <small>
                    {answerResult.structured_evidence_support
                      ? 'structured support · '
                      : ''}
                    {answerResult.rerank_gate_bypassed
                      ? 'rerank soft-gate bypassed'
                      : 'rerank within soft threshold'}
                  </small>
                </div>
              </div>
            </div>

            {answerResult.citations.length > 0 && (
              <div className="citation-map">
                <div className="citation-map-title">
                  <strong>Evidence Citation 映射</strong>
                  <span>回答中的 [n] 与下方 Evidence 一一对应</span>
                </div>
                <div className="citation-map-items">
                  {answerResult.citations.map((citation) => (
                    <a
                      href={`#evidence-${citation.index}`}
                      className="citation-map-item"
                      key={citation.index}
                    >
                      <strong>[{citation.index}]</strong>
                      <span>
                        {citation.section_path || citation.title}
                        {' · '}
                        P{citation.page_start ?? '?'}
                      </span>
                      <code>{citation.evidence_id.slice(0, 14)}…</code>
                    </a>
                  ))}
                </div>
              </div>
            )}

            {!answerResult.grounded && answerResult.refusal_reason && (
              <div className="refusal-reason">reason: {answerResult.refusal_reason}</div>
            )}

            {answerResult.query_log_id && (
              <div className="answer-feedback-bar">
                <div>
                  <strong>这次回答有帮助吗？</strong>
                  <span>负反馈会自动进入 Review Queue。</span>
                </div>
                <div className="answer-feedback-actions">
                  <button
                    type="button"
                    className={answerFeedbackRating === 'helpful' ? 'selected helpful' : ''}
                    disabled={feedbackSubmittingId === answerResult.query_log_id}
                    onClick={() => void submitAnswerFeedback(answerResult.query_log_id!, 'helpful')}
                  >
                    👍 有帮助
                  </button>
                  <button
                    type="button"
                    className={answerFeedbackRating === 'unhelpful' ? 'selected unhelpful' : ''}
                    disabled={feedbackSubmittingId === answerResult.query_log_id}
                    onClick={() => void submitAnswerFeedback(answerResult.query_log_id!, 'unhelpful')}
                  >
                    👎 需审查
                  </button>
                  <code>Trace #{answerResult.query_log_id}</code>
                </div>
              </div>
            )}
          </section>
        )}

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
                    <article
                      id={`evidence-${index + 1}`}
                      className="evidence-card panel"
                      key={`${hit.point_id}-${hit.block_id}`}
                    >
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

  function renderEvaluationPage() {
    const metrics = selectedEvaluationRun?.metrics
    const equipmentName = (id: number) =>
      equipmentModels.find((model) => model.id === id)?.model_code ?? `#${id}`
    const runDiagnoses =
      selectedEvaluationRun?.results.map((result) => ({
        result,
        issues: diagnoseEvaluationResult(result),
      })) ?? []
    const failureSummary = (
      [
        'retrieval_miss',
        'ranking_error',
        'answerability_error',
        'citation_missing',
        'citation_false_positive',
      ] as EvaluationIssueCode[]
    ).map((code) => ({
      code,
      label: evaluationIssueMeta[code].label,
      count: runDiagnoses.filter(({ issues }) =>
        issues.some((issue) => issue.code === code),
      ).length,
    }))
    const healthySampleCount = runDiagnoses.filter(
      ({ issues }) => issues.length === 0,
    ).length
    const snapshotRows: Array<{
      key: keyof EvaluationRunParameterSnapshot
      label: string
      format?: (value: unknown) => string
    }> = [
      { key: 'embedding_model', label: 'Embedding' },
      { key: 'collection_name', label: 'Collection' },
      { key: 'rough_recall_limit', label: 'Rough Recall' },
      { key: 'top_k', label: 'Top-K' },
      {
        key: 'vector_weight',
        label: 'Vector Weight',
        format: (value) =>
          typeof value === 'number' ? value.toFixed(2) : '—',
      },
      {
        key: 'rerank_weight',
        label: 'Rerank Weight',
        format: (value) =>
          typeof value === 'number' ? value.toFixed(2) : '—',
      },
      {
        key: 'grounding_min_final_score',
        label: 'Grounding Final',
        format: (value) =>
          typeof value === 'number' ? value.toFixed(3) : '—',
      },
      {
        key: 'grounding_min_rerank_score',
        label: 'Grounding Rerank (soft)',
        format: (value) =>
          typeof value === 'number' ? value.toFixed(3) : '—',
      },
      { key: 'deepseek_model', label: 'DeepSeek' },
    ]
    const metricCompareRows = [
      ['hit_at_k', 'Hit@K', 'percent'],
      ['mrr', 'MRR', 'metric'],
      ['refusal_accuracy', '拒答准确率', 'percent'],
      ['answerability_accuracy', 'Answerability', 'percent'],
      ['citation_f1', 'Citation F1', 'percent'],
      ['avg_latency_ms', 'Avg Latency', 'latency'],
    ] as const

    return (
      <>
        <header className="topbar">
          <div>
            <p className="eyebrow">RAG EVALUATION</p>
            <h1>评测中心</h1>
            <p className="subtitle">
              管理 Golden Set，批量验证检索、拒答与 Evidence Citation 质量。
            </p>
          </div>
          <a className="ghost-link" href="/docs" target="_blank" rel="noreferrer">
            Evaluation API ↗
          </a>
        </header>

        {evaluationError && <div className="alert error">{evaluationError}</div>}
        {evaluationNotice && (
          <div className="alert success">{evaluationNotice}</div>
        )}

        {evaluationHygiene && !evaluationHygiene.healthy && (
          <section className="evaluation-hygiene panel">
            <div className="evaluation-section-title">
              <div>
                <p className="eyebrow">GOLDEN SET HYGIENE</p>
                <h2>评测基准存在重复 / 冲突</h2>
              </div>
              <span>
                批量 Run 与 Sweep 已暂停，先修复受影响用例。
              </span>
            </div>
            <div className="hygiene-summary">
              <span>重复组 {evaluationHygiene.duplicate_group_count}</span>
              <span>冲突组 {evaluationHygiene.conflict_group_count}</span>
              <span>受影响 Case {evaluationHygiene.affected_case_ids.length}</span>
            </div>
            <div className="hygiene-groups">
              {evaluationHygiene.groups.map((group) => (
                <div
                  key={`${group.equipment_model_id}-${group.normalized_query}`}
                  className={
                    group.issue_codes.includes('conflicting_answerability')
                      ? 'hygiene-group conflict'
                      : 'hygiene-group'
                  }
                >
                  <strong>
                    {equipmentName(group.equipment_model_id)} · Cases {group.case_ids.join(', ')}
                  </strong>
                  <span>{group.normalized_query}</span>
                  <small>
                    {group.issue_codes.includes('conflicting_answerability')
                      ? '同一问题同时被标成“应回答”和“应拒答”，必须保留正确标签并删除/改写其余用例。'
                      : '同一设备下问题重复，请合并 Evidence 标注后只保留一条用例。'}
                  </small>
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="evaluation-toolbar panel">
          <div>
            <p className="eyebrow">BATCH RUN</p>
            <h2>批量评测</h2>
            <span>
              当前 Golden Set：{evaluationCases.length} 条 · 单次最多 50 条
            </span>
          </div>
          <div className="evaluation-run-actions">
            {evaluationCases.length < 8 && (
              <button
                type="button"
                onClick={() => void handleSeedGoldenSet()}
                disabled={
                  evaluationSeeding ||
                  evaluationLoading ||
                  evaluationHygiene?.healthy === false
                }
                title="基于已发布的 IM-1200 测试手册，幂等补齐 8 条基础 Golden Set"
              >
                {evaluationSeeding ? '补充中…' : '补齐到 8 条'}
              </button>
            )}
            <label>
              Top-K
              <select
                value={evaluationTopK}
                onChange={(event) =>
                  setEvaluationTopK(Number(event.target.value))
                }
              >
                {[2, 3, 5, 8, 10].map((value) => (
                  <option value={value} key={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void handleRunEvaluation()}
              disabled={
                evaluationRunning ||
                evaluationLoading ||
                evaluationHygiene?.healthy === false ||
                Math.abs(
                  evaluationVectorWeight +
                    evaluationRerankWeight -
                    1,
                ) >= 0.000001
              }
            >
              {evaluationRunning ? '评测运行中…' : '按当前参数运行'}
            </button>
          </div>
        </section>

        <section className="evaluation-tuning panel">
          <div className="evaluation-section-title">
            <div>
              <p className="eyebrow">PHASE C.4 · PARAMETER LAB</p>
              <h2>参数实验与阈值调优</h2>
            </div>
            <span>
              参数会真实作用于 Retrieval / Rerank / Answerability Gate，并固化进 Run 快照。
            </span>
          </div>

          <div className="tuning-parameter-grid">
            <label>
              Rough Recall
              <input
                type="number"
                min="1"
                max="100"
                value={evaluationRoughRecallLimit}
                onChange={(event) =>
                  setEvaluationRoughRecallLimit(Number(event.target.value))
                }
              />
            </label>
            <label>
              Vector Weight
              <input
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={evaluationVectorWeight}
                onChange={(event) =>
                  setEvaluationVectorWeight(Number(event.target.value))
                }
              />
            </label>
            <label>
              Rerank Weight
              <input
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={evaluationRerankWeight}
                onChange={(event) =>
                  setEvaluationRerankWeight(Number(event.target.value))
                }
              />
            </label>
            <label>
              Grounding Final
              <input
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={evaluationGroundingFinal}
                onChange={(event) =>
                  setEvaluationGroundingFinal(Number(event.target.value))
                }
              />
            </label>
            <label>
              Grounding Rerank (soft)
              <input
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={evaluationGroundingRerank}
                onChange={(event) =>
                  setEvaluationGroundingRerank(Number(event.target.value))
                }
              />
            </label>
            <div className="tuning-weight-check">
              <span>Weight Sum</span>
              <strong
                className={
                  Math.abs(
                    evaluationVectorWeight +
                      evaluationRerankWeight -
                      1,
                  ) < 0.000001
                    ? 'ok'
                    : 'bad'
                }
              >
                {(evaluationVectorWeight + evaluationRerankWeight).toFixed(2)}
              </strong>
              <small>必须等于 1.00</small>
            </div>
          </div>

          <div className="sweep-lab">
            <div>
              <p className="eyebrow">EXPERIMENT SWEEP</p>
              <h3>参数网格</h3>
              <span>
                英文逗号分隔；组合数 × Golden Set 数量 = 实际样本执行次数。
              </span>
            </div>
            <div className="sweep-grid">
              <label>
                Top-K
                <input
                  value={sweepTopKValues}
                  onChange={(event) => setSweepTopKValues(event.target.value)}
                />
              </label>
              <label>
                Final Threshold
                <input
                  value={sweepFinalValues}
                  onChange={(event) => setSweepFinalValues(event.target.value)}
                />
              </label>
              <label>
                Rerank Soft Threshold
                <input
                  value={sweepRerankValues}
                  onChange={(event) => setSweepRerankValues(event.target.value)}
                />
              </label>
              <button
                type="button"
                disabled={
                  sweepRunning ||
                  evaluationRunning ||
                  evaluationHygiene?.healthy === false ||
                  Math.abs(
                    evaluationVectorWeight +
                      evaluationRerankWeight -
                      1,
                  ) >= 0.000001
                }
                onClick={() => void handleRunSweep()}
              >
                {sweepRunning ? 'Sweep 运行中…' : '运行 Sweep'}
              </button>
            </div>
          </div>
        </section>

        <section className="evaluation-leaderboard panel">
          <div className="evaluation-section-title">
            <div>
              <p className="eyebrow">EXPERIMENT LEADERBOARD</p>
              <h2>实验排行榜</h2>
            </div>
            <label className="leaderboard-sort">
              排序
              <select
                value={leaderboardSort}
                onChange={(event) =>
                  setLeaderboardSort(
                    event.target.value as typeof leaderboardSort,
                  )
                }
              >
                <option value="citation_f1">Citation F1 ↓</option>
                <option value="answerability_accuracy">Answerability ↓</option>
                <option value="hit_at_k">Hit@K ↓</option>
                <option value="mrr">MRR ↓</option>
                <option value="avg_latency_ms">Latency ↑</option>
                <option value="failure_count">Failure ↑</option>
              </select>
            </label>
          </div>

          <div className="leaderboard-table">
            <div className="leaderboard-row leaderboard-head">
              <span>Run / Params</span>
              <span>Hit@K</span>
              <span>MRR</span>
              <span>拒答</span>
              <span>Answerability</span>
              <span>Citation F1</span>
              <span>Latency</span>
              <span>Failures</span>
            </div>
            {sortedEvaluationLeaderboard.slice(0, 20).map((item, index) => (
              <button
                type="button"
                className="leaderboard-row"
                key={item.run_id}
                onClick={() => void openEvaluationRun(item.run_id)}
              >
                <span className="leaderboard-run">
                  <b>#{index + 1} · Run #{item.run_id}</b>
                  <small>
                    K {item.parameter_snapshot?.top_k ?? '—'}
                    {' · '}F {item.parameter_snapshot?.grounding_min_final_score === undefined
                      ? '—'
                      : Number(item.parameter_snapshot.grounding_min_final_score).toFixed(2)}
                    {' · '}R {item.parameter_snapshot?.grounding_min_rerank_score === undefined
                      ? '—'
                      : Number(item.parameter_snapshot.grounding_min_rerank_score).toFixed(2)}
                    {' · '}V/RW {item.parameter_snapshot?.vector_weight === undefined
                      ? '—'
                      : Number(item.parameter_snapshot.vector_weight).toFixed(2)}
                    /
                    {item.parameter_snapshot?.rerank_weight === undefined
                      ? '—'
                      : Number(item.parameter_snapshot.rerank_weight).toFixed(2)}
                  </small>
                </span>
                <span>{formatPercent(item.hit_at_k)}</span>
                <span>{formatMetric(item.mrr)}</span>
                <span>{formatPercent(item.refusal_accuracy)}</span>
                <span>{formatPercent(item.answerability_accuracy)}</span>
                <span>{formatPercent(item.citation_f1)}</span>
                <span>
                  {item.avg_latency_ms === null
                    ? '—'
                    : `${Math.round(item.avg_latency_ms)} ms`}
                </span>
                <span className={item.failure_count ? 'leaderboard-failures' : ''}>
                  {item.failure_count}
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="evaluation-create panel">
          <div className="evaluation-section-title">
            <div>
              <p className="eyebrow">GOLDEN SET</p>
              <h2>
                {editingEvaluationCaseId
                  ? `编辑评测用例 #${editingEvaluationCaseId}`
                  : '新增评测用例'}
              </h2>
            </div>
            <span>
              先召回 Top-10 Evidence，再勾选真实支持答案的证据。
            </span>
          </div>

          <form onSubmit={handleSaveEvaluationCase}>
            <div className="evaluation-field evaluation-query-field">
              <label>问题</label>
              <textarea
                rows={3}
                required
                value={evaluationCaseQuery}
                onChange={(event) =>
                  setEvaluationCaseQuery(event.target.value)
                }
                placeholder="例如：设备没电时应该检查什么？"
              />
            </div>

            <div className="evaluation-field">
              <label>设备型号</label>
              <select
                required
                value={evaluationCaseEquipmentId ?? ''}
                onChange={(event) => {
                  setEvaluationCaseEquipmentId(
                    event.target.value
                      ? Number(event.target.value)
                      : null,
                  )
                  setEvaluationEvidenceHits([])
                  setSelectedEvaluationEvidenceIds([])
                  setSelectedAllowedCitationIds([])
                }}
              >
                <option value="">请选择</option>
                {equipmentModels.map((model) => (
                  <option value={model.id} key={model.id}>
                    {model.model_code} · {model.manufacturer}
                  </option>
                ))}
              </select>
            </div>

            <div className="evaluation-field">
              <label>备注</label>
              <input
                value={evaluationCaseNotes}
                onChange={(event) =>
                  setEvaluationCaseNotes(event.target.value)
                }
                placeholder="可选：测试意图 / 场景"
              />
            </div>

            <label className="evaluation-answerable">
              <input
                type="checkbox"
                checked={evaluationCaseAnswerable}
                onChange={(event) => {
                  const checked = event.target.checked
                  setEvaluationCaseAnswerable(checked)
                  if (!checked) {
                    setSelectedEvaluationEvidenceIds([])
                    setSelectedAllowedCitationIds([])
                  }
                }}
              />
              <span>
                <strong>期望可回答</strong>
                <small>
                  关闭后用于验证拒答；Expected Evidence 会自动清空。
                </small>
              </span>
            </label>

            <div className="evaluation-editor-actions">
              <button
                className="evaluation-retrieve-button"
                type="button"
                disabled={
                  evaluationEvidenceLoading ||
                  !evaluationCaseEquipmentId ||
                  !evaluationCaseQuery.trim()
                }
                onClick={() => void handleRetrieveEvaluationEvidence()}
              >
                {evaluationEvidenceLoading
                  ? '召回中…'
                  : '召回 Evidence'}
              </button>
              <button
                className="evaluation-save-button"
                type="submit"
                disabled={evaluationSaving}
              >
                {evaluationSaving
                  ? '保存中…'
                  : editingEvaluationCaseId
                    ? '保存修改'
                    : '保存用例'}
              </button>
              {editingEvaluationCaseId && (
                <button
                  className="evaluation-cancel-button"
                  type="button"
                  onClick={resetEvaluationEditor}
                >
                  取消编辑
                </button>
              )}
            </div>
          </form>

          <div className="evaluation-annotation">
            <div className="evaluation-annotation-head">
              <div>
                <strong>Evidence 可视化标注</strong>
                <span>
                  核心 {selectedEvaluationEvidenceIds.length} 条 · 允许引用 {selectedAllowedCitationIds.length} 条
                </span>
              </div>
              {!evaluationCaseAnswerable && (
                <span className="evaluation-refusal-hint">
                  拒答用例无需标注 Evidence
                </span>
              )}
            </div>

            {selectedEvaluationEvidenceIds.length > 0 && (
              <div className="evaluation-selected-group">
                <span className="evaluation-selected-label">Expected · 核心召回</span>
                <div className="evaluation-selected-evidence">
                  {selectedEvaluationEvidenceIds.map((evidenceId) => {
                    const hit = evaluationEvidenceHits.find(
                      (item) => item.evidence_id === evidenceId,
                    )
                    return (
                      <button
                        type="button"
                        key={evidenceId}
                        onClick={() =>
                          toggleEvaluationEvidence(evidenceId)
                        }
                        title="点击移除此 Expected Evidence"
                      >
                        <strong>
                          {hit?.section_path || '已标注 Evidence'}
                        </strong>
                        <code>{shortHash(evidenceId)}</code>
                        <span>×</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {selectedAllowedCitationIds.filter(
              (id) => !selectedEvaluationEvidenceIds.includes(id),
            ).length > 0 && (
              <div className="evaluation-selected-group">
                <span className="evaluation-selected-label">Allowed Citation · 可选支持证据</span>
                <div className="evaluation-selected-evidence citation-allowed">
                  {selectedAllowedCitationIds
                    .filter(
                      (id) => !selectedEvaluationEvidenceIds.includes(id),
                    )
                    .map((evidenceId) => {
                      const hit = evaluationEvidenceHits.find(
                        (item) => item.evidence_id === evidenceId,
                      )
                      return (
                        <button
                          type="button"
                          key={evidenceId}
                          onClick={() =>
                            toggleAllowedCitationEvidence(evidenceId)
                          }
                          title="点击移除此 Allowed Citation Evidence"
                        >
                          <strong>
                            {hit?.section_path || '允许引用 Evidence'}
                          </strong>
                          <code>{shortHash(evidenceId)}</code>
                          <span>×</span>
                        </button>
                      )
                    })}
                </div>
              </div>
            )}

            {evaluationCaseAnswerable &&
              evaluationEvidenceHits.length === 0 && (
                <div className="evaluation-annotation-empty">
                  输入问题并选择设备后点击“召回 Evidence”，无需手动复制
                  SHA-256。
                </div>
              )}

            {evaluationCaseAnswerable &&
              evaluationEvidenceHits.length > 0 && (
                <div className="evaluation-annotation-list">
                  {evaluationEvidenceHits.map((hit, index) => {
                    const checked =
                      selectedEvaluationEvidenceIds.includes(
                        hit.evidence_id,
                      )
                    const citationAllowed =
                      selectedAllowedCitationIds.includes(
                        hit.evidence_id,
                      )
                    return (
                      <div
                        className={
                          checked
                            ? 'evaluation-evidence-option selected'
                            : citationAllowed
                              ? 'evaluation-evidence-option citation-selected'
                              : 'evaluation-evidence-option'
                        }
                        key={hit.evidence_id}
                      >
                        <label
                          className="evaluation-core-toggle"
                          title="用于 Hit@K / MRR / Citation Recall"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() =>
                              toggleEvaluationEvidence(hit.evidence_id)
                            }
                          />
                          <span>核心</span>
                        </label>
                        <div className="evaluation-evidence-rank">
                          #{index + 1}
                        </div>
                        <div className="evaluation-evidence-copy">
                          <div>
                            <strong>
                              {hit.section_path || '未命名章节'}
                            </strong>
                            <span>
                              {hit.block_type} · P
                              {hit.page_start ?? '?'}
                              {hit.page_end &&
                              hit.page_end !== hit.page_start
                                ? `–${hit.page_end}`
                                : ''}
                            </span>
                          </div>
                          <p>{hit.text}</p>
                          <small title={hit.evidence_id}>
                            {hit.title}
                            {hit.version
                              ? ` · v${hit.version}`
                              : ''}{' '}
                            · {shortHash(hit.evidence_id)}
                          </small>
                        </div>
                        <div className="evaluation-evidence-score">
                          <span>FINAL</span>
                          <strong>
                            {formatScore(hit.final_score)}
                          </strong>
                          <small>
                            V {formatScore(hit.vector_score)} · R{' '}
                            {formatScore(hit.rerank_score)}
                          </small>
                          <button
                            type="button"
                            className={
                              citationAllowed
                                ? 'citation-allow-button active'
                                : 'citation-allow-button'
                            }
                            disabled={checked}
                            onClick={() =>
                              toggleAllowedCitationEvidence(
                                hit.evidence_id,
                              )
                            }
                            title={
                              checked
                                ? '核心 Evidence 自动允许引用'
                                : '允许模型引用该 Evidence，但不要求它作为核心检索命中'
                            }
                          >
                            {checked
                              ? '核心 + 允许'
                              : citationAllowed
                                ? '允许引用 ✓'
                                : '允许引用'}
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
          </div>
        </section>

        <div className="evaluation-grid">
          <section className="evaluation-cases panel">
            <div className="panel-header">
              <div>
                <h2>测试用例</h2>
                <span>{evaluationCases.length} 条</span>
              </div>
            </div>

            {evaluationLoading ? (
              <div className="empty">加载中…</div>
            ) : evaluationCases.length === 0 ? (
              <div className="empty">还没有评测用例</div>
            ) : (
              <div className="evaluation-case-list">
                {evaluationCases.map((item) => (
                  <article className="evaluation-case-row" key={item.id}>
                    <div className="evaluation-case-main">
                      <div className="evaluation-case-tags">
                        <span>#{item.id}</span>
                        <span>{equipmentName(item.equipment_model_id)}</span>
                        <span className={item.expected_answerable ? 'answerable' : 'refusal'}>
                          {item.expected_answerable ? '应回答' : '应拒答'}
                        </span>
                      </div>
                      <strong>{item.query}</strong>
                      <small>
                        {item.expected_evidence_ids.length > 0
                          ? `Expected Evidence: ${item.expected_evidence_ids
                              .map((value) => shortHash(value))
                              .join(', ')}`
                          : 'Expected Evidence: —'}
                      </small>
                      <small>
                        {(item.allowed_citation_evidence_ids.length > 0
                          ? item.allowed_citation_evidence_ids
                          : item.expected_evidence_ids
                        ).length > 0
                          ? `Allowed Citation: ${(
                              item.allowed_citation_evidence_ids.length > 0
                                ? item.allowed_citation_evidence_ids
                                : item.expected_evidence_ids
                            )
                              .map((value) => shortHash(value))
                              .join(', ')}`
                          : 'Allowed Citation: —'}
                      </small>
                      {item.notes && <p>{item.notes}</p>}
                    </div>
                    <div className="evaluation-case-actions">
                      <button
                        type="button"
                        onClick={() => beginEditEvaluationCase(item)}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className="evaluation-run-one"
                        disabled={
                          evaluationRunningCaseId === item.id ||
                          evaluationRunning
                        }
                        onClick={() =>
                          void handleRunSingleEvaluation(item)
                        }
                      >
                        {evaluationRunningCaseId === item.id
                          ? '运行中…'
                          : '单条运行'}
                      </button>
                      <button
                        className="evaluation-delete"
                        type="button"
                        onClick={() =>
                          void handleDeleteEvaluationCase(item.id)
                        }
                      >
                        删除
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="evaluation-runs panel">
            <div className="panel-header">
              <div>
                <h2>运行历史</h2>
                <span>最近 {evaluationRuns.length} 次</span>
              </div>
            </div>
            {evaluationRuns.length === 0 ? (
              <div className="empty">尚未运行评测</div>
            ) : (
              <div className="evaluation-run-list">
                {evaluationRuns.map((run) => (
                  <button
                    type="button"
                    key={run.id}
                    className={
                      selectedEvaluationRun?.id === run.id
                        ? 'evaluation-run-row selected'
                        : 'evaluation-run-row'
                    }
                    onClick={() => void openEvaluationRun(run.id)}
                  >
                    <div>
                      <strong>Run #{run.id}</strong>
                      <span>
                        Top-{run.top_k} · {run.completed_cases}/{run.total_cases}
                      </span>
                      {run.parameter_snapshot && (
                        <small className="run-snapshot-hint">
                          V {Number(run.parameter_snapshot.vector_weight ?? 0).toFixed(2)}
                          {' · '}R {Number(run.parameter_snapshot.rerank_weight ?? 0).toFixed(2)}
                          {' · '}Gate {Number(
                            run.parameter_snapshot.grounding_min_final_score ?? 0,
                          ).toFixed(2)}
                        </small>
                      )}
                    </div>
                    <div>
                      <span className={`run-status ${run.status}`}>
                        {run.status}
                      </span>
                      <small>{formatDate(run.created_at)}</small>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>

        <section className="evaluation-experiment panel">
          <div className="evaluation-section-title">
            <div>
              <p className="eyebrow">EXPERIMENT COMPARE</p>
              <h2>Baseline / Candidate 对比</h2>
            </div>
            <span>
              新 Run 会固化检索、Rerank、Gate 与模型参数快照。
            </span>
          </div>

          <div className="evaluation-compare-controls">
            <label>
              Baseline
              <select
                value={baselineRunId ?? ''}
                onChange={(event) => {
                  setBaselineRunId(
                    event.target.value ? Number(event.target.value) : null,
                  )
                  setRunComparison(null)
                }}
              >
                <option value="">选择 Run</option>
                {evaluationRuns.map((run) => (
                  <option value={run.id} key={run.id}>
                    Run #{run.id} · Top-{run.top_k} · {run.total_cases} cases
                  </option>
                ))}
              </select>
            </label>
            <span className="evaluation-compare-arrow">→</span>
            <label>
              Candidate
              <select
                value={candidateRunId ?? ''}
                onChange={(event) => {
                  setCandidateRunId(
                    event.target.value ? Number(event.target.value) : null,
                  )
                  setRunComparison(null)
                }}
              >
                <option value="">选择 Run</option>
                {evaluationRuns.map((run) => (
                  <option value={run.id} key={run.id}>
                    Run #{run.id} · Top-{run.top_k} · {run.total_cases} cases
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void handleCompareEvaluationRuns()}
              disabled={
                comparisonLoading ||
                !baselineRunId ||
                !candidateRunId ||
                baselineRunId === candidateRunId
              }
            >
              {comparisonLoading ? '对比中…' : '生成对比'}
            </button>
          </div>

          {runComparison && (
            <div className="evaluation-comparison">
              <div className="comparison-overview">
                <span>
                  matched <strong>{runComparison.matched_case_count}</strong>
                </span>
                <span>
                  regressed <strong>{runComparison.regressed_count}</strong>
                </span>
                <span>
                  improved <strong>{runComparison.improved_count}</strong>
                </span>
                <span>
                  mixed <strong>{runComparison.mixed_count}</strong>
                </span>
                <span>
                  unchanged <strong>{runComparison.unchanged_count}</strong>
                </span>
                <span>
                  incomparable <strong>{runComparison.incomparable_count}</strong>
                </span>
                {(runComparison.baseline_only_case_count > 0 ||
                  runComparison.candidate_only_case_count > 0) && (
                  <span className="comparison-warning">
                    unmatched B {runComparison.baseline_only_case_count} / C{' '}
                    {runComparison.candidate_only_case_count}
                  </span>
                )}
              </div>

              <div className="comparison-snapshot-grid">
                <section>
                  <div className="comparison-column-head">
                    <strong>Baseline · Run #{runComparison.baseline_run.id}</strong>
                    <span>{formatDate(runComparison.baseline_run.created_at)}</span>
                  </div>
                  {runComparison.baseline_run.parameter_snapshot ? (
                    <div className="snapshot-list">
                      {snapshotRows.map((row) => {
                        const baselineValue =
                          runComparison.baseline_run.parameter_snapshot?.[row.key]
                        const candidateValue =
                          runComparison.candidate_run.parameter_snapshot?.[row.key]
                        const changed =
                          candidateValue !== undefined &&
                          baselineValue !== candidateValue
                        return (
                          <div
                            className={changed ? 'snapshot-row changed' : 'snapshot-row'}
                            key={String(row.key)}
                          >
                            <span>{row.label}</span>
                            <strong title={String(baselineValue ?? '—')}>
                              {row.format
                                ? row.format(baselineValue)
                                : String(baselineValue ?? '—')}
                            </strong>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div className="snapshot-empty">
                      旧 Run：创建时尚未保存参数快照。
                    </div>
                  )}
                </section>

                <section>
                  <div className="comparison-column-head candidate">
                    <strong>Candidate · Run #{runComparison.candidate_run.id}</strong>
                    <span>{formatDate(runComparison.candidate_run.created_at)}</span>
                  </div>
                  {runComparison.candidate_run.parameter_snapshot ? (
                    <div className="snapshot-list">
                      {snapshotRows.map((row) => {
                        const baselineValue =
                          runComparison.baseline_run.parameter_snapshot?.[row.key]
                        const candidateValue =
                          runComparison.candidate_run.parameter_snapshot?.[row.key]
                        const changed =
                          baselineValue !== undefined &&
                          baselineValue !== candidateValue
                        return (
                          <div
                            className={changed ? 'snapshot-row changed' : 'snapshot-row'}
                            key={String(row.key)}
                          >
                            <span>{row.label}</span>
                            <strong title={String(candidateValue ?? '—')}>
                              {row.format
                                ? row.format(candidateValue)
                                : String(candidateValue ?? '—')}
                            </strong>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div className="snapshot-empty">
                      旧 Run：创建时尚未保存参数快照。
                    </div>
                  )}
                </section>
              </div>

              <div className="comparison-metrics">
                <div className="comparison-table-head">
                  <span>Metric</span>
                  <span>Baseline</span>
                  <span>Candidate</span>
                  <span>Δ</span>
                </div>
                {metricCompareRows.map(([key, label, kind]) => {
                  const item = runComparison.metric_deltas[key]
                  if (!item) return null
                  const formatValue = (value: number | null) => {
                    if (value === null) return '—'
                    if (kind === 'percent') return formatPercent(value)
                    if (kind === 'latency') return `${Math.round(value)} ms`
                    return formatMetric(value)
                  }
                  const deltaGood =
                    item.delta !== null &&
                    (kind === 'latency' ? item.delta < 0 : item.delta > 0)
                  const deltaBad =
                    item.delta !== null &&
                    (kind === 'latency' ? item.delta > 0 : item.delta < 0)

                  return (
                    <div className="comparison-table-row" key={key}>
                      <strong>{label}</strong>
                      <span>{formatValue(item.baseline)}</span>
                      <span>{formatValue(item.candidate)}</span>
                      <span
                        className={
                          deltaGood
                            ? 'delta-good'
                            : deltaBad
                              ? 'delta-bad'
                              : ''
                        }
                      >
                        {item.delta === null
                          ? '—'
                          : `${item.delta > 0 ? '+' : ''}${
                              kind === 'percent'
                                ? (item.delta * 100).toFixed(1) + 'pp'
                                : kind === 'latency'
                                  ? Math.round(item.delta) + ' ms'
                                  : item.delta.toFixed(3)
                            }`}
                      </span>
                    </div>
                  )
                })}
              </div>

              <div className="comparison-failures">
                <div className="comparison-table-head">
                  <span>Failure Type</span>
                  <span>Baseline</span>
                  <span>Candidate</span>
                  <span>Δ</span>
                </div>
                {Object.entries(runComparison.failure_deltas)
                  .filter(([key]) => key !== 'execution_error')
                  .map(([key, item]) => (
                    <div className="comparison-table-row" key={key}>
                      <strong>
                        {evaluationIssueMeta[key as EvaluationIssueCode]?.label ??
                          key}
                      </strong>
                      <span>{item.baseline}</span>
                      <span>{item.candidate}</span>
                      <span
                        className={
                          item.delta < 0
                            ? 'delta-good'
                            : item.delta > 0
                              ? 'delta-bad'
                              : ''
                        }
                      >
                        {item.delta > 0 ? '+' : ''}
                        {item.delta}
                      </span>
                    </div>
                  ))}
              </div>

              <div className="regression-analysis">
                <div className="evaluation-section-title">
                  <div>
                    <p className="eyebrow">REGRESSION SAMPLES</p>
                    <h3>样本级变化</h3>
                  </div>
                  <span>
                    优先展示 regressed / mixed / improved；Golden Set 被修改的样本标记 incomparable。
                  </span>
                </div>

                <div className="regression-sample-list">
                  {runComparison.samples
                    .filter((sample) => sample.status !== 'unchanged')
                    .map((sample) => (
                      <article
                        className={`regression-sample ${sample.status}`}
                        key={`${sample.case_id ?? 'snapshot'}-${sample.query}`}
                      >
                        <div className="regression-sample-head">
                          <div>
                            <span className={`regression-status ${sample.status}`}>
                              {sample.status.toUpperCase()}
                            </span>
                            <strong>{sample.query}</strong>
                          </div>
                          <span>
                            Case {sample.case_id ? `#${sample.case_id}` : 'snapshot'}
                          </span>
                        </div>

                        {!sample.comparable ? (
                          <p className="regression-note">
                            两个 Run 中该 Case 的 Query、设备、Answerability 或 Expected Evidence 已变化，不能作为严格回归样本。
                          </p>
                        ) : (
                          <>
                            <div className="regression-reasons">
                              {sample.regression_reasons.map((reason) => (
                                <span className="reason-regressed" key={reason}>
                                  ↓ {reason.replace(/_/g, ' ')}
                                </span>
                              ))}
                              {sample.improvement_reasons.map((reason) => (
                                <span className="reason-improved" key={reason}>
                                  ↑ {reason.replace(/_/g, ' ')}
                                </span>
                              ))}
                            </div>

                            <div className="regression-sample-grid">
                              <div>
                                <strong>Baseline</strong>
                                <span>
                                  Grounded {sample.baseline.grounded ? 'yes' : 'no'}
                                </span>
                                <span>
                                  Hit {sample.baseline.hit_at_k === null
                                    ? '—'
                                    : sample.baseline.hit_at_k
                                      ? 'yes'
                                      : 'no'}
                                </span>
                                <span>
                                  Rank {sample.baseline.first_relevant_rank ?? '—'}
                                </span>
                                <span>
                                  Citation P/R{' '}
                                  {sample.baseline.citation_precision === null
                                    ? '—'
                                    : `${formatPercent(
                                        sample.baseline.citation_precision,
                                      )} / ${formatPercent(
                                        sample.baseline.citation_recall,
                                      )}`}
                                </span>
                                <span>{sample.baseline.latency_ms} ms</span>
                              </div>
                              <div>
                                <strong>Candidate</strong>
                                <span>
                                  Grounded {sample.candidate.grounded ? 'yes' : 'no'}
                                </span>
                                <span>
                                  Hit {sample.candidate.hit_at_k === null
                                    ? '—'
                                    : sample.candidate.hit_at_k
                                      ? 'yes'
                                      : 'no'}
                                </span>
                                <span>
                                  Rank {sample.candidate.first_relevant_rank ?? '—'}
                                </span>
                                <span>
                                  Citation P/R{' '}
                                  {sample.candidate.citation_precision === null
                                    ? '—'
                                    : `${formatPercent(
                                        sample.candidate.citation_precision,
                                      )} / ${formatPercent(
                                        sample.candidate.citation_recall,
                                      )}`}
                                </span>
                                <span>{sample.candidate.latency_ms} ms</span>
                              </div>
                            </div>

                            <div className="regression-issue-transition">
                              <span>
                                B:{' '}
                                {sample.baseline_issue_codes.length
                                  ? sample.baseline_issue_codes.join(', ')
                                  : 'healthy'}
                              </span>
                              <span>→</span>
                              <span>
                                C:{' '}
                                {sample.candidate_issue_codes.length
                                  ? sample.candidate_issue_codes.join(', ')
                                  : 'healthy'}
                              </span>
                            </div>
                          </>
                        )}
                      </article>
                    ))}

                  {runComparison.samples.every(
                    (sample) => sample.status === 'unchanged',
                  ) && (
                    <div className="comparison-empty">
                      所有匹配样本均为 UNCHANGED，未检测到回归或提升。
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </section>

        {selectedEvaluationRun && (
          <>
            <section className="evaluation-metrics">
              <article className="metric-card">
                <span>Hit@{selectedEvaluationRun.top_k}</span>
                <strong>{formatPercent(metrics?.hit_at_k)}</strong>
                <small>{metrics?.retrieval_case_count ?? 0} retrieval cases</small>
              </article>
              <article className="metric-card">
                <span>MRR</span>
                <strong>{formatMetric(metrics?.mrr)}</strong>
                <small>Mean Reciprocal Rank</small>
              </article>
              <article className="metric-card">
                <span>拒答准确率</span>
                <strong>{formatPercent(metrics?.refusal_accuracy)}</strong>
                <small>{metrics?.unanswerable_case_count ?? 0} refusal cases</small>
              </article>
              <article className="metric-card">
                <span>Answerability</span>
                <strong>{formatPercent(metrics?.answerability_accuracy)}</strong>
                <small>回答 / 拒答整体判断</small>
              </article>
              <article className="metric-card">
                <span>Citation F1</span>
                <strong>{formatPercent(metrics?.citation_f1)}</strong>
                <small>
                  P {formatPercent(metrics?.citation_precision)} · R{' '}
                  {formatPercent(metrics?.citation_recall)}
                </small>
              </article>
            </section>

            <section className="evaluation-failure-summary panel">
              <div className="evaluation-section-title">
                <div>
                  <p className="eyebrow">FAILURE ANALYSIS</p>
                  <h2>失败样本摘要</h2>
                </div>
                <span>
                  当前 Run · {healthySampleCount}/{runDiagnoses.length} healthy
                </span>
              </div>
              <div className="evaluation-failure-grid">
                <article className="evaluation-failure-card healthy">
                  <span>Healthy / Pass</span>
                  <strong>{healthySampleCount}</strong>
                  <small>未检测到检索、排序、应答或引用异常</small>
                </article>
                {failureSummary.map((item) => (
                  <article
                    className={`evaluation-failure-card ${item.count > 0 ? 'active' : ''}`}
                    key={item.code}
                  >
                    <span>{item.label}</span>
                    <strong>{item.count}</strong>
                    <small>{evaluationIssueMeta[item.code].description}</small>
                  </article>
                ))}
              </div>
            </section>

            <section className="threshold-analysis panel">
              <div className="evaluation-section-title">
                <div>
                  <p className="eyebrow">THRESHOLD ERROR ANALYSIS</p>
                  <h2>Answerability 阈值误差</h2>
                </div>
                <span>
                  Run #{selectedEvaluationRun.id} · {thresholdErrors.length} 个 Answerability Error
                </span>
              </div>

              {thresholdErrors.length === 0 ? (
                <div className="threshold-empty">
                  当前 Run 没有 Answerability Error。
                </div>
              ) : (
                <div className="threshold-error-list">
                  {thresholdErrors.map((item) => (
                    <article className="threshold-error-card" key={item.result_id}>
                      <div className="threshold-error-head">
                        <div>
                          <span className="diagnosis-chip danger">
                            Answerability Error
                          </span>
                          <strong>{item.query}</strong>
                        </div>
                        <span>
                          Expected {item.expected_answerable ? 'answer' : 'refuse'}
                          {' → '}
                          Actual {item.actual_grounded ? 'grounded' : 'refused'}
                        </span>
                      </div>

                      <div className="threshold-score-grid">
                        <div>
                          <span>top_final_score</span>
                          <strong>
                            {item.top_final_score === null
                              ? '—'
                              : formatScore(item.top_final_score)}
                          </strong>
                          <small>
                            gate {item.grounding_min_final_score === null
                              ? '—'
                              : formatScore(item.grounding_min_final_score)}
                            {' · '}margin {item.final_margin === null
                              ? '—'
                              : item.final_margin.toFixed(4)}
                          </small>
                        </div>
                        <div>
                          <span>top_rerank_score</span>
                          <strong>
                            {item.top_rerank_score === null
                              ? '—'
                              : formatScore(item.top_rerank_score)}
                          </strong>
                          <small>
                            soft {item.grounding_min_rerank_score === null
                              ? '—'
                              : formatScore(item.grounding_min_rerank_score)}
                            {' · '}margin {item.rerank_margin === null
                              ? '—'
                              : item.rerank_margin.toFixed(4)}
                          </small>
                        </div>
                        <div>
                          <span>Decision Source</span>
                          <strong>{item.decision_source ?? 'legacy / unknown'}</strong>
                          <small>
                            DeepSeek:{' '}
                            {item.deepseek_answerable === null
                              ? 'not called / unknown'
                              : item.deepseek_answerable
                                ? 'answerable'
                                : 'not answerable'}
                            {' · '}
                            {item.structured_evidence_support
                              ? 'structured support'
                              : 'no structured support'}
                            {item.rerank_gate_bypassed
                              ? ' · rerank soft-gate bypassed'
                              : ''}
                          </small>
                        </div>
                      </div>

                      <div className="threshold-reason">
                        <span>refusal_reason</span>
                        <code>{item.refusal_reason ?? '—'}</code>
                        <span>DeepSeek reason</span>
                        <p>{item.deepseek_reason ?? '—'}</p>
                      </div>

                      <div className="threshold-evidence">
                        {item.top_evidence.map((hit) => (
                          <div key={hit.evidence_id}>
                            <strong>
                              #{hit.rank} · {hit.section_path || '未命名章节'}
                            </strong>
                            <span>
                              F {formatScore(hit.final_score)}
                              {' · '}R {formatScore(hit.rerank_score)}
                              {' · '}V {formatScore(hit.vector_score)}
                            </span>
                            <p>{hit.text}</p>
                          </div>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="evaluation-results panel">
              <div className="evaluation-section-title">
                <div>
                  <p className="eyebrow">RUN #{selectedEvaluationRun.id}</p>
                  <h2>逐条结果</h2>
                </div>
                <span>
                  {selectedEvaluationRun.status} · errors{' '}
                  {metrics?.error_count ?? 0}
                </span>
              </div>

              <div className="evaluation-result-list">
                {selectedEvaluationRun.results.map((result) => {
                  const issues = diagnoseEvaluationResult(result)
                  const healthy = issues.length === 0
                  const expectedSet = new Set(result.expected_evidence_ids)
                  const allowedCitationSet = new Set(
                    result.allowed_citation_evidence_ids.length > 0
                      ? result.allowed_citation_evidence_ids
                      : result.expected_evidence_ids,
                  )
                  const citationSet = new Set(result.citation_evidence_ids)
                  const hitRankByEvidence = new Map(
                    result.hits.map((hit, index) => [
                      hit.evidence_id,
                      index + 1,
                    ]),
                  )

                  return (
                  <article
                    className={`evaluation-result-row ${healthy ? 'diagnostic-healthy' : 'diagnostic-issue'}`}
                    key={result.id}
                  >
                    <div className="evaluation-result-head">
                      <div>
                        <span className={healthy ? 'eval-pass' : 'eval-fail'}>
                          {healthy ? 'PASS' : 'FAIL'}
                        </span>
                        <strong>{result.query}</strong>
                      </div>
                      <span>{result.latency_ms} ms</span>
                    </div>

                    <div className="evaluation-diagnosis">
                      <div className="evaluation-diagnosis-tags">
                        {healthy ? (
                          <span className="diagnosis-chip healthy">
                            Healthy
                          </span>
                        ) : (
                          issues.map((issue) => (
                            <span
                              className={`diagnosis-chip ${issue.tone}`}
                              key={issue.code}
                            >
                              {issue.label}
                            </span>
                          ))
                        )}
                      </div>
                      <p>
                        {evaluationDiagnosisSummary(result, issues)}
                      </p>
                    </div>

                    <div className="evaluation-result-metrics">
                      <span>
                        Expected: {result.expected_answerable ? 'answer' : 'refuse'}
                      </span>
                      <span>
                        Actual: {result.grounded ? 'grounded' : 'refused'}
                      </span>
                      <span>
                        Hit@K:{' '}
                        {result.hit_at_k === null
                          ? '—'
                          : result.hit_at_k
                            ? 'yes'
                            : 'no'}
                      </span>
                      <span>
                        Rank: {result.first_relevant_rank ?? '—'}
                      </span>
                      <span>
                        RR:{' '}
                        {result.reciprocal_rank === null
                          ? '—'
                          : formatMetric(result.reciprocal_rank)}
                      </span>
                      <span>
                        Citation P/R:{' '}
                        {result.citation_precision === null
                          ? '—'
                          : `${formatPercent(result.citation_precision)} / ${formatPercent(
                              result.citation_recall,
                            )}`}
                      </span>
                    </div>

                    {result.error_message ? (
                      <div className="evaluation-result-error">
                        {result.error_message}
                      </div>
                    ) : (
                      <details>
                        <summary>
                          查看 Expected / Top-K / Citation 失败对比
                        </summary>
                        <div className="evaluation-result-detail diagnostic-detail">
                          <div className="evaluation-result-answer">
                            <strong>Answer</strong>
                            <div>
                              {renderMarkdownAnswer(result.answer || '—')}
                            </div>
                          </div>

                          <div className="evaluation-compare-grid">
                            <section className="evaluation-compare-column">
                              <div className="evaluation-compare-title">
                                <strong>Expected Evidence</strong>
                                <span>
                                  {result.expected_evidence_ids.length}
                                </span>
                              </div>
                              {result.expected_evidence_ids.length === 0 ? (
                                <div className="evaluation-compare-empty">
                                  拒答用例，无 Expected Evidence
                                </div>
                              ) : (
                                <div className="evaluation-compare-list">
                                  {result.expected_evidence_ids.map(
                                    (evidenceId) => {
                                      const rank =
                                        hitRankByEvidence.get(evidenceId)
                                      const hit = result.hits.find(
                                        (item) =>
                                          item.evidence_id === evidenceId,
                                      )
                                      const cited =
                                        citationSet.has(evidenceId)

                                      return (
                                        <div
                                          className={`evaluation-compare-item ${rank ? 'expected-hit' : 'expected-missed'}`}
                                          key={evidenceId}
                                        >
                                          <div>
                                            <strong>
                                              {hit?.section_path ||
                                                'Expected Evidence'}
                                            </strong>
                                            <code
                                              title={evidenceId}
                                            >
                                              {shortHash(evidenceId)}
                                            </code>
                                          </div>
                                          <div className="evaluation-status-tags">
                                            <span>
                                              {rank
                                                ? `HIT #${rank}`
                                                : 'MISSED'}
                                            </span>
                                            {cited && (
                                              <span className="cited-correct">
                                                CITED
                                              </span>
                                            )}
                                          </div>
                                        </div>
                                      )
                                    },
                                  )}
                                </div>
                              )}
                            </section>

                            <section className="evaluation-compare-column">
                              <div className="evaluation-compare-title">
                                <strong>Actual Top-K</strong>
                                <span>{result.hits.length}</span>
                              </div>
                              {result.hits.length === 0 ? (
                                <div className="evaluation-compare-empty">
                                  没有召回结果
                                </div>
                              ) : (
                                <div className="evaluation-compare-list">
                                  {result.hits.map((hit, index) => {
                                    const expected =
                                      expectedSet.has(hit.evidence_id)
                                    const allowed =
                                      allowedCitationSet.has(hit.evidence_id)
                                    const cited =
                                      citationSet.has(hit.evidence_id)
                                    const stateClass = expected
                                      ? 'expected-hit'
                                      : cited && allowed
                                        ? 'cited-correct'
                                        : cited
                                          ? 'cited-extra'
                                          : allowed
                                            ? 'citation-allowed-hit'
                                            : ''

                                    return (
                                      <div
                                        className={`evaluation-compare-item topk-item ${stateClass}`}
                                        key={hit.evidence_id}
                                      >
                                        <div className="topk-main">
                                          <span className="topk-rank">
                                            #{index + 1}
                                          </span>
                                          <div>
                                            <strong>
                                              {hit.section_path ||
                                                hit.title}
                                            </strong>
                                            <code
                                              title={hit.evidence_id}
                                            >
                                              {shortHash(hit.evidence_id)}
                                            </code>
                                          </div>
                                        </div>
                                        <div className="evaluation-status-tags">
                                          {expected && (
                                            <span className="expected-label">
                                              EXPECTED
                                            </span>
                                          )}
                                          {!expected && allowed && (
                                            <span className="allowed-label">
                                              ALLOWED
                                            </span>
                                          )}
                                          {cited && (
                                            <span
                                              className={
                                                allowed
                                                  ? 'cited-correct'
                                                  : 'cited-extra'
                                              }
                                            >
                                              {allowed
                                                ? 'CITED ✓'
                                                : 'EXTRA CITATION'}
                                            </span>
                                          )}
                                        </div>
                                        <div className="topk-score-grid">
                                          <span>
                                            final{' '}
                                            <b>
                                              {formatScore(
                                                hit.final_score,
                                              )}
                                            </b>
                                          </span>
                                          <span>
                                            vector{' '}
                                            <b>
                                              {formatScore(
                                                hit.vector_score,
                                              )}
                                            </b>
                                          </span>
                                          <span>
                                            rerank{' '}
                                            <b>
                                              {formatScore(
                                                hit.rerank_score,
                                              )}
                                            </b>
                                          </span>
                                        </div>
                                      </div>
                                    )
                                  })}
                                </div>
                              )}
                            </section>

                            <section className="evaluation-compare-column">
                              <div className="evaluation-compare-title">
                                <strong>Actual Citations</strong>
                                <span>
                                  {result.citation_evidence_ids.length}
                                </span>
                              </div>
                              {result.citation_evidence_ids.length === 0 ? (
                                <div className="evaluation-compare-empty">
                                  未产生 Citation
                                </div>
                              ) : (
                                <div className="evaluation-compare-list">
                                  {result.citation_evidence_ids.map(
                                    (evidenceId) => {
                                      const expected =
                                        expectedSet.has(evidenceId)
                                      const correct =
                                        allowedCitationSet.has(evidenceId)
                                      const hit = result.hits.find(
                                        (item) =>
                                          item.evidence_id === evidenceId,
                                      )

                                      return (
                                        <div
                                          className={`evaluation-compare-item ${correct ? 'cited-correct' : 'cited-extra'}`}
                                          key={evidenceId}
                                        >
                                          <div>
                                            <strong>
                                              {hit?.section_path ||
                                                'Citation Evidence'}
                                            </strong>
                                            <code
                                              title={evidenceId}
                                            >
                                              {shortHash(evidenceId)}
                                            </code>
                                          </div>
                                          <span
                                            className={
                                              correct
                                                ? 'citation-verdict correct'
                                                : 'citation-verdict extra'
                                            }
                                          >
                                            {correct
                                              ? expected
                                                ? 'CORE CORRECT'
                                                : 'ALLOWED SUPPORT'
                                              : 'FALSE POSITIVE'}
                                          </span>
                                        </div>
                                      )
                                    },
                                  )}
                                </div>
                              )}
                            </section>
                          </div>
                        </div>
                      </details>
                    )}
                  </article>
                  )
                })}
              </div>
            </section>
          </>
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
          <button
            className={`nav-item ${page === 'evaluation' ? 'active' : ''}`}
            type="button"
            onClick={() => setPage('evaluation')}
          >
            <span>◎</span>
            评测中心
          </button>
          <button
            className={`nav-item ${page === 'feedback' ? 'active' : ''}`}
            type="button"
            onClick={() => setPage('feedback')}
          >
            <span>↺</span>
            反馈与审查
          </button>
        </nav>

        <div className="sidebar-footer">
          <span className="status-dot" />
          本地开发环境
        </div>
      </aside>

      <main className="main">
        {page === 'documents'
          ? renderDocumentPage()
          : page === 'search'
            ? renderSearchPage()
            : page === 'evaluation'
              ? renderEvaluationPage()
              : renderFeedbackPage()}
      </main>
    </div>
  )
}

export default App
