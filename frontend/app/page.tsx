"use client";

import {
  Activity,
  AlertCircle,
  ArrowUpRight,
  Bot,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clock3,
  Database,
  FileCheck2,
  FileText,
  Gauge,
  LoaderCircle,
  Menu,
  MessageSquareText,
  Play,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Star,
  Ticket,
  UserRound,
  Wrench,
  X,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

type Tab = "chat" | "report" | "knowledge" | "tickets" | "monitoring" | "evaluation";
type Role = "user" | "assistant";

type Source = {
  source: string;
  excerpt: string;
  score: number;
  citation?: string | null;
  page?: number | null;
  chunk_id?: string | null;
  metadata?: Record<string, unknown>;
};

type Intent = {
  intent: string;
  confidence: number;
  entities?: Record<string, string>;
  reasons?: string[];
  secondary_intents?: string[];
  chain?: string[];
};

type Message = {
  role: Role;
  content: string;
  traceId?: string;
  intent?: Intent;
  escalationRequired?: boolean;
  ticketId?: string | null;
  evaluationId?: number | null;
  latencyMs?: number | null;
  sources?: Source[];
  question?: string;
  feedbackRating?: number;
};

type Report = {
  title: string;
  user_id: string;
  month: string;
  profile: string;
  efficiency: string;
  consumables: string;
  comparison: string;
  months: string[];
};

type Ticket = {
  id: string;
  user_id: string;
  conversation_id?: string | null;
  subject: string;
  description: string;
  category: string;
  priority: "low" | "normal" | "high" | "urgent";
  status: "open" | "pending" | "in_progress" | "resolved" | "closed";
  assigned_to?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type EventItem = {
  id: number;
  event_type: string;
  severity: "info" | "warning" | "error" | "critical";
  message: string;
  user_id?: string | null;
  conversation_id?: string | null;
  context?: Record<string, unknown>;
  created_at: string;
};

type Overview = {
  generated_at: string;
  events: number;
  errors: number;
  warnings: number;
  open_tickets: number;
  evaluations: number;
  average_score: number;
  average_latency_ms?: number | null;
  fallback_rate: number;
  intent_distribution: Record<string, number>;
};

type EvaluationMetrics = {
  count: number;
  average_score: number;
  average_rating?: number | null;
  by_intent: Record<string, number>;
};

type EvaluationRun = {
  run_id: string;
  count: number;
  average_score: number;
  cases: Array<{ id: number; question?: string; score: number; rating?: number | null; feedback?: string | null; created_at: string }>;
  metrics: EvaluationMetrics;
};

type Health = {
  status: string;
  model: string;
  dashscope_configured: boolean;
  knowledge_documents: number;
  knowledge_chunks?: number;
  records: number;
  retrieval?: Record<string, unknown>;
  loop_db?: string;
};

type KnowledgeIndex = {
  ready?: boolean;
  chunks?: number;
  sources?: number;
  files?: number;
  vocabulary?: number;
  dense_vectors?: boolean;
  built_at?: string | null;
  parse_errors?: Array<{ source: string; error: string }>;
  index_path?: string;
  [key: string]: unknown;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";
const USER_ID = "1001";
const quickPrompts = ["扫地机器人总是漏扫，怎么排查？", "拖布有异味需要怎么清洁？", "帮我生成本月使用报告"];

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = "请求失败";
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep the generic message when the server did not return JSON.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

function formatAnswer(content: string) {
  return content.split("\n").map((line, index, lines) => (
    <span key={`${line}-${index}`}>
      {line}
      {index < lines.length - 1 ? <br /> : null}
    </span>
  ));
}

function formatTime(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function intentLabel(intent?: string) {
  const labels: Record<string, string> = {
    support: "售后支持",
    usage_report: "使用报告",
    troubleshooting: "故障排查",
    maintenance: "维护保养",
    purchase: "选购咨询",
    product_advice: "选购咨询",
    after_sales: "售后服务",
    general_support: "通用支持",
    human_handoff: "转人工",
    safety_incident: "安全事故",
    unknown: "待确认",
  };
  return labels[intent ?? ""] ?? intent ?? "待确认";
}

function severityLabel(value: EventItem["severity"]) {
  return { info: "信息", warning: "警告", error: "错误", critical: "严重" }[value] ?? value;
}

function ticketStatusLabel(value: Ticket["status"]) {
  return { open: "待处理", pending: "等待用户", in_progress: "处理中", resolved: "已解决", closed: "已关闭" }[value];
}

function priorityLabel(value: Ticket["priority"]) {
  return { low: "低", normal: "普通", high: "高", urgent: "紧急" }[value];
}

export default function Home() {
  const [tab, setTab] = useState<Tab>("chat");
  const [mobileNav, setMobileNav] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: "你好，我是智扫通。可以帮你排查故障、查找使用建议，或生成扫地机器人的个性化使用报告。",
    },
  ]);
  const [conversationId, setConversationId] = useState<string>();
  const [sources, setSources] = useState<Source[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [selectedMonth, setSelectedMonth] = useState("2025-12");
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [knowledgeResults, setKnowledgeResults] = useState<Source[]>([]);
  const [knowledgeIndex, setKnowledgeIndex] = useState<KnowledgeIndex | null>(null);
  const [knowledgeStrategy, setKnowledgeStrategy] = useState("hybrid_tfidf_keyword_vector");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [evalMetrics, setEvalMetrics] = useState<EvaluationMetrics | null>(null);
  const [evalRun, setEvalRun] = useState<EvaluationRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [sectionLoading, setSectionLoading] = useState(false);
  const [apiOnline, setApiOnline] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void getJson<Health>(`${API_BASE}/health`)
      .then(() => setApiOnline(true))
      .catch(() => setApiOnline(false));
    void getJson<Report>(`${API_BASE}/reports/${USER_ID}`)
      .then((latestReport) => {
        setReport(latestReport);
        setSelectedMonth(latestReport.month);
      })
      .catch(() => undefined);
    void getJson<KnowledgeIndex>(`${API_BASE}/knowledge/index`)
      .then(setKnowledgeIndex)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (tab === "tickets") void loadTickets();
    if (tab === "monitoring") void loadMonitoring();
    if (tab === "evaluation") void loadEvaluationMetrics();
    if (tab === "knowledge") void loadKnowledgeIndex();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const completion = useMemo(() => {
    if (!report) return 0;
    const match = report.efficiency.match(/(\d+)%/);
    return match ? Number(match[1]) : 0;
  }, [report]);

  async function loadKnowledgeIndex() {
    try {
      setKnowledgeIndex(await getJson<KnowledgeIndex>(`${API_BASE}/knowledge/index`));
    } catch {
      // The search panel still remains usable if index status is unavailable.
    }
  }

  async function loadTickets() {
    setSectionLoading(true);
    try {
      setTickets(await getJson<Ticket[]>(`${API_BASE}/tickets?user_id=${USER_ID}&limit=100`));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "工单加载失败");
    } finally {
      setSectionLoading(false);
    }
  }

  async function loadMonitoring() {
    setSectionLoading(true);
    try {
      const [nextOverview, nextEvents] = await Promise.all([
        getJson<Overview>(`${API_BASE}/monitoring/overview`),
        getJson<EventItem[]>(`${API_BASE}/monitoring/events?limit=80`),
      ]);
      setOverview(nextOverview);
      setEvents(nextEvents);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "监控数据加载失败");
    } finally {
      setSectionLoading(false);
    }
  }

  async function loadEvaluationMetrics() {
    setSectionLoading(true);
    try {
      setEvalMetrics(await getJson<EvaluationMetrics>(`${API_BASE}/evaluations/metrics`));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "评测指标加载失败");
    } finally {
      setSectionLoading(false);
    }
  }

  async function sendMessage(event?: FormEvent) {
    event?.preventDefault();
    const message = input.trim();
    if (!message || loading) return;
    setInput("");
    setError("");
    const history = messages.slice(-10).map(({ role, content }) => ({ role, content }));
    setMessages((current) => [...current, { role: "user", content: message }]);
    setLoading(true);
    try {
      const data = await getJson<{
        trace_id: string;
        conversation_id: string;
        answer: string;
        intent: Intent;
        escalation_required?: boolean;
        ticket_id?: string | null;
        evaluation_id?: number | null;
        sources?: Source[];
        report?: Report | null;
        model?: string | null;
        fallback?: boolean;
        latency_ms?: number | null;
      }>(`${API_BASE}/agent/loop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, user_id: USER_ID, conversation_id: conversationId, history }),
      });
      setConversationId(data.conversation_id);
      setSources(data.sources ?? []);
      if (data.report) {
        setReport(data.report);
        setSelectedMonth(data.report.month);
      }
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: data.answer,
          traceId: data.trace_id,
          intent: data.intent,
          escalationRequired: data.escalation_required,
          ticketId: data.ticket_id,
          evaluationId: data.evaluation_id,
          sources: data.sources ?? [],
          latencyMs: data.latency_ms,
          question: message,
        },
      ]);
      if (data.escalation_required) void loadTickets();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "请求失败，请稍后重试");
      setMessages((current) => [
        ...current,
        { role: "assistant", content: "暂时无法连接客服服务。你仍可以查看已有使用报告，或稍后重试。" },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function submitFeedback(messageIndex: number, rating: number) {
    const target = messages[messageIndex];
    if (!target || target.role !== "assistant" || target.feedbackRating) return;
    try {
      await getJson(`${API_BASE}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: USER_ID,
          conversation_id: conversationId,
          question: target.question ?? "客服回答反馈",
          answer: target.content,
          rating,
        }),
      });
      setMessages((current) => current.map((item, index) => (index === messageIndex ? { ...item, feedbackRating: rating } : item)));
      if (tab === "evaluation") void loadEvaluationMetrics();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "反馈提交失败");
    }
  }

  async function searchKnowledge(event?: FormEvent) {
    event?.preventDefault();
    if (!knowledgeQuery.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await getJson<{ results?: Source[]; strategy?: string }>(`${API_BASE}/knowledge/search?query=${encodeURIComponent(knowledgeQuery)}`);
      setKnowledgeResults(data.results ?? []);
      if (data.strategy) setKnowledgeStrategy(data.strategy);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "搜索失败");
    } finally {
      setLoading(false);
    }
  }

  async function runEvaluation() {
    setSectionLoading(true);
    setError("");
    try {
      const run = await getJson<EvaluationRun>(`${API_BASE}/evaluations/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ include_default_cases: true, cases: [] }),
      });
      setEvalRun(run);
      setEvalMetrics(run.metrics);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "自动评测失败");
    } finally {
      setSectionLoading(false);
    }
  }

  async function updateTicket(ticketId: string, status: Ticket["status"]) {
    try {
      const updated = await getJson<Ticket>(`${API_BASE}/tickets/${encodeURIComponent(ticketId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      setTickets((current) => current.map((ticket) => (ticket.id === updated.id ? updated : ticket)));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "工单更新失败");
    }
  }

  async function loadReport(month: string) {
    setSelectedMonth(month);
    try {
      const nextReport = await getJson<Report>(`${API_BASE}/reports/${USER_ID}/${month}`);
      setReport(nextReport);
    } catch {
      setError("报告加载失败，请确认后端服务已启动");
    }
  }

  function clearConversation() {
    setMessages([{ role: "assistant", content: "你好，我是智扫通。可以帮你排查故障、查找使用建议，或生成扫地机器人的个性化使用报告。" }]);
    setSources([]);
    setConversationId(undefined);
  }

  const tabMeta: Record<Tab, { label: string; description: string }> = {
    chat: { label: "智能客服", description: "让每一次售后咨询，都有可执行的答案。" },
    report: { label: "使用报告", description: "查看设备表现、耗材状态与下一步保养建议。" },
    knowledge: { label: "知识库", description: "从已整理的扫地机器人资料中快速定位答案。" },
    tickets: { label: "售后工单", description: "跟进需要人工介入的售后事项与处理状态。" },
    monitoring: { label: "运行监控", description: "观察意图路由、延迟、错误与转人工事件。" },
    evaluation: { label: "自动评测", description: "用透明的测试集检查回答质量，并沉淀反馈。" },
  };

  function navigate(nextTab: Tab) {
    setTab(nextTab);
    setMobileNav(false);
    setError("");
  }

  return (
    <main className="app-shell">
      <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark"><Bot size={20} strokeWidth={2.5} /></div>
          <div><strong>智扫通</strong><span>SMART CARE OPS</span></div>
          <button className="icon-button mobile-close" onClick={() => setMobileNav(false)} aria-label="关闭菜单"><X size={18} /></button>
        </div>
        <div className="workspace-label">工作台</div>
        <nav className="nav-list" aria-label="主要导航">
          <button className={tab === "chat" ? "nav-item active" : "nav-item"} onClick={() => navigate("chat")}><CircleHelp size={18} /><span>智能客服</span><span className="nav-count">在线</span></button>
          <button className={tab === "report" ? "nav-item active" : "nav-item"} onClick={() => navigate("report")}><FileText size={18} /><span>使用报告</span><ChevronRight size={16} className="nav-arrow" /></button>
          <button className={tab === "knowledge" ? "nav-item active" : "nav-item"} onClick={() => navigate("knowledge")}><BookOpen size={18} /><span>知识库</span><ChevronRight size={16} className="nav-arrow" /></button>
          <div className="nav-divider" />
          <button className={tab === "tickets" ? "nav-item active" : "nav-item"} onClick={() => navigate("tickets")}><Ticket size={18} /><span>售后工单</span>{overview?.open_tickets ? <span className="nav-badge">{overview.open_tickets}</span> : <ChevronRight size={16} className="nav-arrow" />}</button>
          <button className={tab === "monitoring" ? "nav-item active" : "nav-item"} onClick={() => navigate("monitoring")}><Activity size={18} /><span>运行监控</span><ChevronRight size={16} className="nav-arrow" /></button>
          <button className={tab === "evaluation" ? "nav-item active" : "nav-item"} onClick={() => navigate("evaluation")}><Gauge size={18} /><span>自动评测</span><ChevronRight size={16} className="nav-arrow" /></button>
        </nav>
        <div className="sidebar-spacer" />
        <div className="system-card">
          <div className="system-card-title"><Activity size={16} />系统状态</div>
          <div className="system-row"><span>客服 API</span><span className={apiOnline ? "status-dot online" : "status-dot"}>{apiOnline ? "正常" : "离线"}</span></div>
          <div className="system-row"><span>知识资料</span><span className="status-value">{knowledgeIndex?.ready === false ? "构建中" : "已载入"}</span></div>
          <div className="system-row"><span>模型</span><span className="status-value">DeepSeek</span></div>
        </div>
        <div className="profile-row"><div className="avatar">1001</div><div><strong>演示用户</strong><span>65㎡ · 木地板</span></div><button className="icon-button" aria-label="更多用户设置"><ArrowUpRight size={16} /></button></div>
      </aside>

      <section className="content-area">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMobileNav(true)} aria-label="打开菜单"><Menu size={20} /></button>
          <div className="breadcrumb"><span>工作台</span><ChevronRight size={14} /><strong>{tabMeta[tab].label}</strong></div>
          <div className="topbar-actions"><span className="last-sync"><Clock3 size={14} />最后同步：刚刚</span><button className="icon-button" onClick={() => window.location.reload()} aria-label="刷新页面"><RefreshCw size={17} /></button></div>
        </header>

        <div className="page-content">
          <div className="page-heading"><div><div className="eyebrow">CUSTOMER SUCCESS / 01</div><h1>{tabMeta[tab].label}</h1><p>{tabMeta[tab].description}</p></div><div className="heading-meta"><ShieldCheck size={18} /><span>数据仅用于本地客服工作台</span></div></div>

          {error ? <div className="alert-banner"><AlertCircle size={17} />{error}<button onClick={() => setError("")} aria-label="关闭提示"><X size={16} /></button></div> : null}

          {tab === "chat" ? <div className="workspace-grid">
            <section className="panel chat-panel">
              <div className="panel-header"><div><div className="panel-kicker"><span className="live-indicator" />LIVE ASSIST</div><h2>对话工作区</h2></div><button className="subtle-button" onClick={clearConversation}><RefreshCw size={15} />新对话</button></div>
              <div className="chat-stream">
                {messages.map((message, index) => <div className={`message-row ${message.role}`} key={`${message.role}-${index}`}>
                  <div className="message-avatar">{message.role === "assistant" ? <Bot size={16} /> : <UserRound size={16} />}</div>
                  <div className="message-bubble">
                    <div className="message-label">{message.role === "assistant" ? "智扫通客服" : "你"}</div>
                    <div className="message-content">{formatAnswer(message.content)}</div>
                    {message.role === "assistant" && message.intent ? <div className="message-trace">
                      <span className="intent-chip">{intentLabel(message.intent.intent)} · {Math.round(message.intent.confidence * 100)}%</span>
                      {message.intent.chain && message.intent.chain.length > 1 ? <span className="trace-chain">链路：{message.intent.chain.map(intentLabel).join(" → ")}</span> : null}
                      {message.traceId ? <span className="trace-id">trace {message.traceId.slice(0, 12)}</span> : null}
                      {message.latencyMs != null ? <span className="trace-id">{Math.round(message.latencyMs)} ms</span> : null}
                    </div> : null}
                    {message.escalationRequired ? <div className="handoff-notice"><Ticket size={14} /><span>已转人工售后，工单号 <strong>{message.ticketId ?? "创建中"}</strong></span><button className="text-button" onClick={() => navigate("tickets")}>查看工单 <ArrowUpRight size={13} /></button></div> : null}
                    {message.role === "assistant" && message.intent && !message.feedbackRating && message.evaluationId ? <div className="feedback-row"><span>回答有帮助吗？</span><button onClick={() => void submitFeedback(index, 5)} aria-label="有帮助"><Star size={14} />有帮助</button><button onClick={() => void submitFeedback(index, 2)} aria-label="需要改进"><MessageSquareText size={14} />需要改进</button></div> : null}
                    {message.feedbackRating ? <div className="feedback-done"><Check size={13} />感谢反馈，已纳入评测闭环</div> : null}
                  </div>
                </div>)}
                {loading ? <div className="message-row assistant"><div className="message-avatar"><Bot size={16} /></div><div className="message-bubble loading-bubble"><div className="message-label">智扫通客服</div><span className="typing"><i /><i /><i /></span></div></div> : null}
              </div>
              <div className="quick-prompts">{quickPrompts.map((prompt) => <button key={prompt} onClick={() => setInput(prompt)}>{prompt}<ArrowUpRight size={13} /></button>)}</div>
              <form className="composer" onSubmit={sendMessage}><textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }} placeholder="描述设备型号、故障现象或想了解的功能…" rows={2} /><button className="send-button" type="submit" aria-label="发送消息"><Send size={18} /></button></form>
              <div className="composer-footer"><span><Sparkles size={14} />回答基于知识库与用户使用记录</span><span>Enter 发送 · Shift + Enter 换行</span></div>
            </section>
            <aside className="side-stack"><section className="panel context-panel"><div className="panel-header compact"><div><div className="panel-kicker">CURRENT CONTEXT</div><h3>演示设备档案</h3></div><button className="icon-button" aria-label="编辑演示设备档案"><Wrench size={16} /></button></div><div className="device-summary"><div className="device-icon"><Bot size={23} /></div><div><strong>智扫 S8 Pro</strong><span>扫拖一体 · 模拟在线</span></div><span className="device-status">演示数据</span></div><div className="context-stats"><div><span>居住面积</span><strong>65㎡</strong></div><div><span>地面类型</span><strong>木地板</strong></div><div><span>本月覆盖率</span><strong>{completion || 90}%</strong></div></div></section><section className="panel source-panel"><div className="panel-header compact"><div><div className="panel-kicker">EVIDENCE</div><h3>本次参考资料</h3></div><Database size={17} className="muted-icon" /></div>{sources.length ? sources.map((source) => <div className="source-item" key={`${source.source}-${source.chunk_id ?? source.score}`}><div><strong>{source.source.replace(/^data[\\/]/, "")}</strong><span>{source.citation ?? (source.page ? `第 ${source.page} 页` : "知识库片段")}</span><small>{source.excerpt}</small></div><span className="score">{Math.round(source.score * 100)}%</span></div>) : <div className="empty-state"><BookOpen size={20} /><span>发送问题后，这里会显示回答所依据的资料。</span></div>}</section></aside>
          </div> : null}

          {tab === "report" ? <section className="report-layout"><div className="report-main"><div className="report-toolbar"><div><div className="panel-kicker">PERSONAL USAGE REPORT</div><h2>智扫通扫地机器人使用情况报告</h2></div><label className="select-wrap">报告月份<select value={selectedMonth} onChange={(event) => void loadReport(event.target.value)}>{(report?.months ?? ["2025-12"]).map((month) => <option value={month} key={month}>{month}</option>)}</select></label></div>{report ? <><div className="metric-grid"><div className="metric-card primary"><span>清洁覆盖率</span><strong>{completion || "—"}<small>%</small></strong><div className="metric-bar"><i style={{ width: `${completion || 0}%` }} /></div><em>本月平均表现</em></div><div className="metric-card"><span>日均清扫</span><strong>{report.efficiency.match(/日均清扫:([^\n]+)/)?.[1] ?? "—"}</strong><em>来自演示使用记录</em></div><div className="metric-card"><span>同类用户对比</span><strong className="metric-text">{report.comparison.match(/优于[^（(]+/)?.[0] ?? "已生成"}</strong><em>基于演示样本</em></div></div><div className="report-columns"><div className="report-section"><div className="section-title"><Activity size={17} />清洁表现</div><p>{report.efficiency}</p><div className="section-title"><Wrench size={17} />耗材状态</div><p>{report.consumables}</p></div><div className="recommendation"><div className="recommendation-head"><Sparkles size={18} /><span>售后建议</span></div><h3>把下一次维护安排在问题发生之前</h3><p>根据本月耗材状态，建议按剩余寿命安排主刷与滤网更换，并保持每周一次深度清洁。若出现持续漏扫、异常噪音或回充失败，请在咨询时附上设备型号与故障视频。</p><button className="text-button" onClick={() => { navigate("chat"); setInput("根据我的使用报告，给我具体的保养建议"); }}>咨询客服 <ArrowUpRight size={15} /></button></div></div><div className="report-footnote"><CheckCircle2 size={15} />报告生成于 {report.month} · 记录来源：本地演示数据</div></> : <div className="empty-large"><FileText size={28} /><h3>暂无报告数据</h3><p>选择其他用户或月份后重试。</p></div>}</div><aside className="report-aside panel"><div className="panel-kicker">REPORT GUIDE</div><h3>本报告包含什么</h3><div className="guide-list"><div><span>01</span><p><strong>清洁表现</strong><br />覆盖率、清扫量和漏扫情况</p></div><div><span>02</span><p><strong>耗材状态</strong><br />主刷、边刷、滤网的维护提醒</p></div><div><span>03</span><p><strong>个性化建议</strong><br />结合家庭环境给出的售后动作</p></div></div></aside></section> : null}

          {tab === "knowledge" ? <section className="knowledge-layout"><div className="knowledge-main panel"><div className="panel-header"><div><div className="panel-kicker">KNOWLEDGE RETRIEVAL</div><h2>资料检索</h2></div><span className="knowledge-count">{knowledgeStrategy.replaceAll("_", " · ").toUpperCase()}</span></div><form className="search-form" onSubmit={searchKnowledge}><Search size={19} /><input value={knowledgeQuery} onChange={(event) => setKnowledgeQuery(event.target.value)} placeholder="搜索故障、维护、选购或功能关键词…" /><button type="submit" disabled={loading}>{loading ? "检索中" : "检索"}</button></form>{knowledgeResults.length ? <div className="results-list">{knowledgeResults.map((item) => <article className="result-item" key={`${item.source}-${item.chunk_id ?? item.score}`}><div className="result-title"><FileText size={16} /><strong>{item.source.replace(/^data[\\/]/, "")}</strong><span>{Math.round(item.score * 100)}% 匹配</span></div><div className="result-citation">{item.citation ?? (item.page ? `第 ${item.page} 页` : "知识库片段")}{item.chunk_id ? ` · ${item.chunk_id.slice(0, 12)}` : ""}</div><p>{item.excerpt}</p><button className="text-button" onClick={() => { navigate("chat"); setInput(`请结合资料“${item.source}”说明：${knowledgeQuery}`); }}>带入客服对话 <ArrowUpRight size={14} /></button></article>)}</div> : <div className="empty-large"><BookOpen size={31} /><h3>开始检索知识库</h3><p>输入一个故障现象或保养关键词，获取最相关的资料片段。</p></div>}</div><aside className="knowledge-aside"><div className="stat-strip"><div><strong>{knowledgeIndex?.sources ?? "—"}</strong><span>主题资料</span></div><div><strong>{knowledgeIndex?.chunks ?? "—"}</strong><span>索引片段</span></div><div><strong>{knowledgeIndex?.vocabulary ?? "—"}</strong><span>词汇量</span></div></div><section className="panel topic-panel"><div className="panel-kicker">TOPICS</div><h3>常用主题</h3><div className="topic-list">{["故障排除", "维护保养", "选购指南", "扫拖一体机器人", "常见问题"].map((topic) => <button key={topic} onClick={() => setKnowledgeQuery(topic)}><span>{topic}</span><ChevronRight size={15} /></button>)}</div></section><section className="panel index-panel"><div className="panel-kicker">INDEX STATUS</div><div className="index-status-row"><span className={knowledgeIndex?.ready ? "status-dot online" : "status-dot"}>{knowledgeIndex?.ready ? "可检索" : "未就绪"}</span><span>{knowledgeIndex?.built_at ? formatTime(knowledgeIndex.built_at) : "等待构建"}</span></div>{knowledgeIndex?.parse_errors?.length ? <p className="index-warning">解析告警 {knowledgeIndex.parse_errors.length} 条</p> : <p>PDF/TXT 文档已进行增量索引。</p>}</section></aside></section> : null}

          {tab === "tickets" ? <section className="operations-layout"><div className="panel operations-main"><div className="panel-header"><div><div className="panel-kicker">HUMAN HANDOFF</div><h2>售后工单</h2></div><button className="subtle-button" onClick={() => void loadTickets()}><RefreshCw size={15} />刷新</button></div>{sectionLoading ? <div className="loading-state"><LoaderCircle className="spin" size={20} />加载工单…</div> : tickets.length ? <div className="ticket-list">{tickets.map((ticket) => <article className="ticket-item" key={ticket.id}><div className="ticket-main"><div className="ticket-title"><Ticket size={16} /><strong>{ticket.subject}</strong><span className={`priority priority-${ticket.priority}`}>{priorityLabel(ticket.priority)}</span></div><p>{ticket.description}</p><div className="ticket-meta"><span>#{ticket.id}</span><span>{formatTime(ticket.created_at)}</span><span>{ticket.category}</span>{ticket.assigned_to ? <span>负责人：{ticket.assigned_to}</span> : null}</div></div><div className="ticket-actions"><span className={`status-pill status-${ticket.status}`}>{ticketStatusLabel(ticket.status)}</span><select value={ticket.status} onChange={(event) => void updateTicket(ticket.id, event.target.value as Ticket["status"])} aria-label={`更新工单 ${ticket.id} 状态`}><option value="open">待处理</option><option value="pending">等待用户</option><option value="in_progress">处理中</option><option value="resolved">已解决</option><option value="closed">已关闭</option></select></div></article>)}</div> : <div className="empty-large"><Ticket size={30} /><h3>暂无售后工单</h3><p>触发转人工或安全事故意图后，工单会自动出现在这里。</p></div>}</div><aside className="operations-aside"><div className="stat-strip"><div><strong>{tickets.filter((item) => ["open", "pending", "in_progress"].includes(item.status)).length}</strong><span>未关闭</span></div><div><strong>{tickets.filter((item) => item.priority === "urgent").length}</strong><span>紧急</span></div><div><strong>{tickets.length}</strong><span>总工单</span></div></div><section className="panel process-panel"><div className="panel-kicker">HANDOFF FLOW</div><h3>自动转人工链路</h3><div className="flow-step"><span>01</span><p><strong>意图识别</strong><br />识别投诉、安全和复杂售后意图</p></div><div className="flow-step"><span>02</span><p><strong>创建工单</strong><br />保留 trace、对话与设备上下文</p></div><div className="flow-step"><span>03</span><p><strong>人工跟进</strong><br />在状态变更后回写监控事件</p></div></section></aside></section> : null}

          {tab === "monitoring" ? <section className="monitoring-layout"><div className="monitoring-main"><div className="monitoring-toolbar"><div><div className="panel-kicker">OBSERVABILITY</div><h2>运行监控</h2></div><button className="subtle-button" onClick={() => void loadMonitoring()}><RefreshCw size={15} />刷新数据</button></div>{overview ? <div className="overview-grid"><div className="overview-card"><span>事件总数</span><strong>{overview.events}</strong><em>持久化运行事件</em></div><div className="overview-card danger"><span>错误 / 警告</span><strong>{overview.errors} / {overview.warnings}</strong><em>需要关注的信号</em></div><div className="overview-card"><span>平均延迟</span><strong>{overview.average_latency_ms != null ? `${Math.round(overview.average_latency_ms)}ms` : "—"}</strong><em>Agent 回合耗时</em></div><div className="overview-card accent"><span>回退率</span><strong>{Math.round((overview.fallback_rate ?? 0) * 100)}%</strong><em>模型不可用时的保底回答</em></div></div> : <div className="panel empty-large"><Activity size={28} /><h3>暂无监控数据</h3><p>完成一次对话后，这里会显示运行指标。</p></div>}<section className="panel event-panel"><div className="panel-header compact"><div><div className="panel-kicker">EVENT STREAM</div><h3>事件流</h3></div><span className="event-count">{events.length} 条</span></div>{sectionLoading ? <div className="loading-state"><LoaderCircle className="spin" size={20} />加载事件…</div> : events.length ? <div className="event-list">{events.map((item) => <div className="event-item" key={item.id}><span className={`severity severity-${item.severity}`}>{severityLabel(item.severity)}</span><div><strong>{item.message}</strong><span>{item.event_type} · {formatTime(item.created_at)}</span></div><code>{String(item.context?.trace_id ?? item.context?.ticket_id ?? "—").slice(0, 18)}</code></div>)}</div> : <div className="empty-state"><Activity size={18} /><span>暂时没有事件。</span></div>}</section></div><aside className="monitoring-aside"><section className="panel intent-panel"><div className="panel-kicker">INTENT ROUTING</div><h3>意图分布</h3>{overview && Object.keys(overview.intent_distribution).length ? <div className="intent-bars">{Object.entries(overview.intent_distribution).sort(([, a], [, b]) => b - a).map(([name, count]) => <div className="intent-bar" key={name}><div><span>{intentLabel(name)}</span><strong>{count}</strong></div><i style={{ width: `${Math.max(8, (count / Math.max(...Object.values(overview.intent_distribution))) * 100)}%` }} /></div>)}</div> : <p className="muted-copy">完成对话后显示路由分布。</p>}</section><section className="panel monitor-note"><FileCheck2 size={18} /><div><strong>可审计链路</strong><p>每个回合都会记录 trace、意图置信度、延迟、回退与工单事件。</p></div></section></aside></section> : null}

          {tab === "evaluation" ? <section className="evaluation-layout"><div className="evaluation-main"><div className="monitoring-toolbar"><div><div className="panel-kicker">QUALITY LOOP</div><h2>自动评测</h2></div><button className="primary-button" onClick={() => void runEvaluation()} disabled={sectionLoading}><Play size={15} />{sectionLoading ? "评测中…" : "运行默认评测"}</button></div><div className="evaluation-score-grid"><div className="score-card primary"><span>平均得分</span><strong>{evalMetrics ? `${Math.round(evalMetrics.average_score * 100)}%` : "—"}</strong><em>{evalMetrics?.count ?? 0} 条评测记录</em></div><div className="score-card"><span>平均星级</span><strong>{evalMetrics?.average_rating != null ? evalMetrics.average_rating.toFixed(1) : "—"}<small>/ 5</small></strong><em>来自用户反馈</em></div><div className="score-card"><span>最近运行</span><strong className="score-run">{evalRun?.run_id ? evalRun.run_id.slice(0, 8) : "—"}</strong><em>透明内置测试集</em></div></div><section className="panel evaluation-panel"><div className="panel-header compact"><div><div className="panel-kicker">RUN RESULTS</div><h3>评测结果</h3></div>{evalRun ? <span className="event-count">{evalRun.count} cases</span> : null}</div>{evalRun?.cases?.length ? <div className="evaluation-list">{evalRun.cases.map((item, index) => <div className="evaluation-item" key={`${item.id}-${index}`}><span className="case-number">{String(index + 1).padStart(2, "0")}</span><div><strong>{item.question ?? "内置测试问题"}</strong><span>{formatTime(item.created_at)}</span></div><b className={item.score >= 0.7 ? "score-good" : "score-low"}>{Math.round(item.score * 100)}%</b></div>)}</div> : <div className="empty-large"><Gauge size={29} /><h3>尚未运行评测</h3><p>运行默认评测集，检查意图识别与回答质量。</p></div>}</section></div><aside className="evaluation-aside"><section className="panel intent-panel"><div className="panel-kicker">SCORE BY INTENT</div><h3>按意图得分</h3>{evalMetrics && Object.keys(evalMetrics.by_intent).length ? <div className="intent-bars">{Object.entries(evalMetrics.by_intent).map(([name, score]) => <div className="intent-bar" key={name}><div><span>{intentLabel(name)}</span><strong>{Math.round(score * 100)}%</strong></div><i style={{ width: `${Math.max(8, score * 100)}%` }} /></div>)}</div> : <p className="muted-copy">运行评测后显示分项结果。</p>}</section><section className="panel evaluation-loop-note"><Sparkles size={18} /><div><strong>反馈会回流</strong><p>聊天页的星级反馈会写入同一评测表，并在这里汇总。</p></div></section></aside></section> : null}
        </div>
      </section>
    </main>
  );
}
