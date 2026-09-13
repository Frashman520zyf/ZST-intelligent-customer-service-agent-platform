"use client";

import {
  Activity,
  AlertCircle,
  ArrowUpRight,
  Bot,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clock3,
  Database,
  FileText,
  Menu,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  UserRound,
  Wrench,
  X,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

type Tab = "chat" | "report" | "knowledge";
type Message = { role: "user" | "assistant"; content: string };
type Source = { source: string; excerpt: string; score: number };
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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";
const quickPrompts = ["扫地机器人总是漏扫，怎么排查？", "拖布有异味需要怎么清洁？", "帮我生成本月使用报告"];

function formatAnswer(content: string) {
  return content.split("\n").map((line, index) => (
    <span key={`${line}-${index}`}>
      {line}
      {index < content.split("\n").length - 1 ? <br /> : null}
    </span>
  ));
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
  const [loading, setLoading] = useState(false);
  const [apiOnline, setApiOnline] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((response) => response.json())
      .then(() => setApiOnline(true))
      .catch(() => setApiOnline(false));
    fetch(`${API_BASE}/reports/1001`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (data) {
          setReport(data);
          setSelectedMonth(data.month);
        }
      })
      .catch(() => undefined);
  }, []);

  const activeReport = report;
  const completion = useMemo(() => {
    if (!activeReport) return 0;
    const match = activeReport.efficiency.match(/(\d+)%/);
    return match ? Number(match[1]) : 0;
  }, [activeReport]);

  async function sendMessage(event?: FormEvent) {
    event?.preventDefault();
    const message = input.trim();
    if (!message || loading) return;
    setInput("");
    setError("");
    setMessages((current) => [...current, { role: "user", content: message }]);
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          user_id: "1001",
          conversation_id: conversationId,
          history: messages.slice(-10),
        }),
      });
      if (!response.ok) throw new Error("客服服务暂时不可用");
      const data = await response.json();
      setConversationId(data.conversation_id);
      setMessages((current) => [...current, { role: "assistant", content: data.answer }]);
      setSources(data.sources ?? []);
      if (data.report) setReport(data.report);
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

  async function searchKnowledge(event?: FormEvent) {
    event?.preventDefault();
    if (!knowledgeQuery.trim()) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/knowledge/search?query=${encodeURIComponent(knowledgeQuery)}`);
      if (!response.ok) throw new Error("知识库暂时不可用");
      const data = await response.json();
      setKnowledgeResults(data.results ?? []);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "搜索失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadReport(month: string) {
    setSelectedMonth(month);
    try {
      const response = await fetch(`${API_BASE}/reports/1001/${month}`);
      if (response.ok) setReport(await response.json());
    } catch {
      setError("报告加载失败，请确认后端服务已启动");
    }
  }

  function clearConversation() {
    setMessages([
      { role: "assistant", content: "你好，我是智扫通。可以帮你排查故障、查找使用建议，或生成扫地机器人的个性化使用报告。" },
    ]);
    setSources([]);
    setConversationId(undefined);
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
          <button className={tab === "chat" ? "nav-item active" : "nav-item"} onClick={() => { setTab("chat"); setMobileNav(false); }}><CircleHelp size={18} /><span>智能客服</span><span className="nav-count">在线</span></button>
          <button className={tab === "report" ? "nav-item active" : "nav-item"} onClick={() => { setTab("report"); setMobileNav(false); }}><FileText size={18} /><span>使用报告</span><ChevronRight size={16} className="nav-arrow" /></button>
          <button className={tab === "knowledge" ? "nav-item active" : "nav-item"} onClick={() => { setTab("knowledge"); setMobileNav(false); }}><BookOpen size={18} /><span>知识库</span><ChevronRight size={16} className="nav-arrow" /></button>
        </nav>
        <div className="sidebar-spacer" />
        <div className="system-card">
          <div className="system-card-title"><Activity size={16} />系统状态</div>
          <div className="system-row"><span>客服 API</span><span className={apiOnline ? "status-dot online" : "status-dot"}>{apiOnline ? "正常" : "离线"}</span></div>
          <div className="system-row"><span>知识资料</span><span className="status-value">已载入</span></div>
          <div className="system-row"><span>模型</span><span className="status-value">DeepSeek</span></div>
        </div>
        <div className="profile-row"><div className="avatar">1001</div><div><strong>演示用户</strong><span>65㎡ · 木地板</span></div><button className="icon-button" aria-label="更多用户设置"><ArrowUpRight size={16} /></button></div>
      </aside>

      <section className="content-area">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMobileNav(true)} aria-label="打开菜单"><Menu size={20} /></button>
          <div className="breadcrumb"><span>工作台</span><ChevronRight size={14} /><strong>{tab === "chat" ? "智能客服" : tab === "report" ? "使用报告" : "知识库"}</strong></div>
          <div className="topbar-actions"><span className="last-sync"><Clock3 size={14} />最后同步：刚刚</span><button className="icon-button" onClick={() => window.location.reload()} aria-label="刷新页面"><RefreshCw size={17} /></button></div>
        </header>

        <div className="page-content">
          <div className="page-heading"><div><div className="eyebrow">CUSTOMER SUCCESS / 01</div><h1>{tab === "chat" ? "智能客服" : tab === "report" ? "使用报告" : "知识库"}</h1><p>{tab === "chat" ? "让每一次售后咨询，都有可执行的答案。" : tab === "report" ? "查看设备表现、耗材状态与下一步保养建议。" : "从已整理的扫地机器人资料中快速定位答案。"}</p></div><div className="heading-meta"><ShieldCheck size={18} /><span>数据仅用于本地客服工作台</span></div></div>

          {error ? <div className="alert-banner"><AlertCircle size={17} />{error}<button onClick={() => setError("")} aria-label="关闭提示"><X size={16} /></button></div> : null}

          {tab === "chat" ? <div className="workspace-grid">
            <section className="panel chat-panel">
              <div className="panel-header"><div><div className="panel-kicker"><span className="live-indicator" />LIVE ASSIST</div><h2>对话工作区</h2></div><button className="subtle-button" onClick={clearConversation}><RefreshCw size={15} />新对话</button></div>
              <div className="chat-stream">
                {messages.map((message, index) => <div className={`message-row ${message.role}`} key={`${message.role}-${index}`}><div className="message-avatar">{message.role === "assistant" ? <Bot size={16} /> : <UserRound size={16} />}</div><div className="message-bubble"><div className="message-label">{message.role === "assistant" ? "智扫通客服" : "你"}</div><div className="message-content">{formatAnswer(message.content)}</div></div></div>)}
                {loading ? <div className="message-row assistant"><div className="message-avatar"><Bot size={16} /></div><div className="message-bubble loading-bubble"><div className="message-label">智扫通客服</div><span className="typing"><i /><i /><i /></span></div></div> : null}
              </div>
              <div className="quick-prompts">{quickPrompts.map((prompt) => <button key={prompt} onClick={() => setInput(prompt)}>{prompt}<ArrowUpRight size={13} /></button>)}</div>
              <form className="composer" onSubmit={sendMessage}><textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="描述设备型号、故障现象或想了解的功能…" rows={2} /><button className="send-button" type="submit" aria-label="发送消息"><Send size={18} /></button></form>
              <div className="composer-footer"><span><Sparkles size={14} />回答基于知识库与用户使用记录</span><span>Enter 发送 · Shift + Enter 换行</span></div>
            </section>
            <aside className="side-stack"><section className="panel context-panel"><div className="panel-header compact"><div><div className="panel-kicker">CURRENT CONTEXT</div><h3>用户设备档案</h3></div><button className="icon-button" aria-label="编辑设备档案"><Wrench size={16} /></button></div><div className="device-summary"><div className="device-icon"><Bot size={23} /></div><div><strong>智扫 S8 Pro</strong><span>扫拖一体 · 在线</span></div><span className="device-status">已连接</span></div><div className="context-stats"><div><span>居住面积</span><strong>65㎡</strong></div><div><span>地面类型</span><strong>木地板</strong></div><div><span>本月覆盖率</span><strong>{completion || 90}%</strong></div></div></section><section className="panel source-panel"><div className="panel-header compact"><div><div className="panel-kicker">EVIDENCE</div><h3>本次参考资料</h3></div><Database size={17} className="muted-icon" /></div>{sources.length ? sources.map((source) => <div className="source-item" key={`${source.source}-${source.score}`}><div><strong>{source.source.replace("data/", "")}</strong><span>{source.excerpt}</span></div><span className="score">{Math.round(source.score * 100)}%</span></div>) : <div className="empty-state"><BookOpen size={20} /><span>发送问题后，这里会显示回答所依据的资料。</span></div>}</section></aside>
          </div> : null}

          {tab === "report" ? <section className="report-layout"><div className="report-main"><div className="report-toolbar"><div><div className="panel-kicker">PERSONAL USAGE REPORT</div><h2>智扫通扫地机器人使用情况报告</h2></div><label className="select-wrap">报告月份<select value={selectedMonth} onChange={(event) => loadReport(event.target.value)}>{(activeReport?.months ?? ["2025-12"]).map((month) => <option value={month} key={month}>{month}</option>)}</select></label></div>{activeReport ? <><div className="metric-grid"><div className="metric-card primary"><span>清洁覆盖率</span><strong>{completion || "--"}<small>%</small></strong><div className="metric-bar"><i style={{ width: `${completion || 0}%` }} /></div><em>本月平均表现</em></div><div className="metric-card"><span>日均清扫</span><strong>{activeReport.efficiency.match(/日均清扫:([^\n]+)/)?.[1] ?? "--"}</strong><em>来自设备使用记录</em></div><div className="metric-card"><span>同类用户对比</span><strong className="metric-text">{activeReport.comparison.match(/优于[^（(]+/)?.[0] ?? "已生成"}</strong><em>基于同面积用户</em></div></div><div className="report-columns"><div className="report-section"><div className="section-title"><Activity size={17} />清洁表现</div><p>{activeReport.efficiency}</p><div className="section-title"><Wrench size={17} />耗材状态</div><p>{activeReport.consumables}</p></div><div className="recommendation"><div className="recommendation-head"><Sparkles size={18} /><span>售后建议</span></div><h3>把下一次维护安排在问题发生之前</h3><p>根据本月耗材状态，建议按剩余寿命安排主刷与滤网更换，并保持每周一次深度清洁。若出现持续漏扫、异常噪音或回充失败，请在咨询时附上设备型号与故障视频。</p><button className="text-button" onClick={() => { setTab("chat"); setInput("根据我的使用报告，给我具体的保养建议"); }}>咨询客服 <ArrowUpRight size={15} /></button></div></div><div className="report-footnote"><CheckCircle2 size={15} />报告生成于 {activeReport.month} · 记录来源：设备使用数据</div></> : <div className="empty-large"><FileText size={28} /><h3>暂无报告数据</h3><p>选择其他用户或月份后重试。</p></div>}</div><aside className="report-aside panel"><div className="panel-kicker">REPORT GUIDE</div><h3>本报告包含什么</h3><div className="guide-list"><div><span>01</span><p><strong>清洁表现</strong><br />覆盖率、清扫量和漏扫情况</p></div><div><span>02</span><p><strong>耗材状态</strong><br />主刷、边刷、滤网的维护提醒</p></div><div><span>03</span><p><strong>个性化建议</strong><br />结合家庭环境给出的售后动作</p></div></div></aside></section> : null}

          {tab === "knowledge" ? <section className="knowledge-layout"><div className="knowledge-main panel"><div className="panel-header"><div><div className="panel-kicker">KNOWLEDGE RETRIEVAL</div><h2>资料检索</h2></div><span className="knowledge-count">TXT / PDF（TXT 已索引）</span></div><form className="search-form" onSubmit={searchKnowledge}><Search size={19} /><input value={knowledgeQuery} onChange={(event) => setKnowledgeQuery(event.target.value)} placeholder="搜索故障、维护、选购或功能关键词…" /><button type="submit">检索</button></form>{knowledgeResults.length ? <div className="results-list">{knowledgeResults.map((item) => <article className="result-item" key={`${item.source}-${item.score}`}><div className="result-title"><FileText size={16} /><strong>{item.source.replace("data/", "")}</strong><span>{Math.round(item.score * 100)}% 匹配</span></div><p>{item.excerpt}</p><button className="text-button" onClick={() => { setTab("chat"); setInput(`请结合资料“${item.source}”说明：${knowledgeQuery}`); }}>带入客服对话 <ArrowUpRight size={14} /></button></article>)}</div> : <div className="empty-large"><BookOpen size={31} /><h3>开始检索知识库</h3><p>输入一个故障现象或保养关键词，获取最相关的资料片段。</p></div>}</div><aside className="knowledge-aside"><div className="stat-strip"><div><strong>5</strong><span>主题资料</span></div><div><strong>1000+</strong><span>问答条目</span></div><div><strong>3</strong><span>检索结果上限</span></div></div><section className="panel topic-panel"><div className="panel-kicker">TOPICS</div><h3>常用主题</h3><div className="topic-list">{["故障排除", "维护保养", "选购指南", "扫拖一体机器人", "常见问题"].map((topic) => <button key={topic} onClick={() => setKnowledgeQuery(topic)}><span>{topic}</span><ChevronRight size={15} /></button>)}</div></section></aside></section> : null}
        </div>
      </section>
    </main>
  );
}
