import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Alert,
  App,
  Badge,
  Button,
  Card,
  Collapse,
  ConfigProvider,
  Empty,
  Input,
  Layout,
  List,
  Modal,
  Space,
  Spin,
  Tag,
  Typography,
  theme
} from "antd";
import {
  BookOpen,
  Cloud,
  FileText,
  History,
  Search,
  Send
} from "lucide-react";
import zhCN from "antd/locale/zh_CN";
import "./styles.css";

type Intent = "knowledge" | "doc_lookup" | "api_reference" | "permission" | "troubleshooting" | "cost" | "smalltalk";

interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
}

interface Citation {
  chunk_id: string;
  title: string;
  source_title: string;
  url: string;
  snippet?: string;
  score?: number;
  product?: string;
  category?: string;
  doc_type?: string;
  section?: string;
}

interface AgentState {
  intent?: Intent;
  tool_calls?: ToolCall[];
  citations?: Citation[];
  error?: string;
}

interface SupportSection {
  heading: string;
  kind: string;
  content: string;
  tags: string[];
}

interface SupportDocument {
  id: string;
  title: string;
  product: string;
  category: string;
  doc_type: string;
  url: string;
  tags: string[];
  related_apis: string[];
  common_errors: string[];
  summary: string;
  sections?: SupportSection[];
}

interface TopicItem {
  id: string;
  name: string;
  product: string;
  doc_count: number;
  tags: string[];
}

interface HealthState {
  status: string;
  chunks: number;
  documents: number;
  model: string;
  product: string;
  retrieval_mode?: string;
  vector_index_enabled?: number;
}

interface ChatMessage {
  id: string;
  question: string;
  answer: string;
  status: string;
  done: boolean;
  failed?: boolean;
  errorMessage?: string;
  intent?: Intent;
  toolCalls: ToolCall[];
  citations: Citation[];
  createdAt: string;
}

const { Header, Sider, Content } = Layout;
const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;
const HISTORY_STORAGE_KEY = "aliyun-oss-rag-history-v1";

const QUICK_QUESTIONS = [
  "OSS 403 AccessDenied 应该怎么排查？",
  "如何用 STS 临时访问凭证让浏览器上传 OSS？",
  "RAM Policy 和 Bucket Policy 有什么区别？",
  "SignatureDoesNotMatch 常见原因有哪些？",
  "OSS 生命周期规则如何降低日志存储成本？",
  "浏览器直传 OSS 为什么会出现跨域失败？"
];

function nowId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function cleanInlineMarkdown(text: string) {
  return text.replace(/\*\*/g, "").replace(/`/g, "");
}

function citationAnchorId(messageId: string, citationNumber: number) {
  return `citation-${messageId}-${citationNumber}`;
}

function renderInlineWithCitations(
  text: string,
  citations: Citation[],
  onCitationClick?: (citationNumber: number) => void
) {
  const cleaned = cleanInlineMarkdown(text);
  const parts: React.ReactNode[] = [];
  const citationPattern = /\[(\d+)\]/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = citationPattern.exec(cleaned)) !== null) {
    const [raw, numberText] = match;
    const citationNumber = Number(numberText);
    const citation = citations[citationNumber - 1];
    if (match.index > cursor) parts.push(cleaned.slice(cursor, match.index));
    parts.push(
      citation && onCitationClick ? (
        <button
          className="citation-ref"
          key={`${match.index}-${raw}`}
          type="button"
          title={`跳转到知识库依据 ${citationNumber}: ${citation.title}`}
          onClick={(event) => {
            event.stopPropagation();
            onCitationClick(citationNumber);
          }}
        >
          {raw}
        </button>
      ) : (
        <span className="citation-ref citation-ref-missing" key={`${match.index}-${raw}`}>
          {raw}
        </span>
      )
    );
    cursor = match.index + raw.length;
  }

  if (cursor < cleaned.length) parts.push(cleaned.slice(cursor));
  return parts.length ? parts : cleaned;
}

function renderAnswer(text: string, citations: Citation[] = [], onCitationClick?: (citationNumber: number) => void) {
  return text.split("\n").map((line, index) => {
    const trimmed = line.trim();
    const key = `${index}-${trimmed.slice(0, 12)}`;
    if (!trimmed) return <div className="answer-gap" key={key} />;
    if (trimmed.startsWith("### ") || trimmed.startsWith("## ")) {
      return (
        <Title className="answer-heading" level={5} key={key}>
          {renderInlineWithCitations(trimmed.replace(/^#{2,3}\s*/, ""), citations, onCitationClick)}
        </Title>
      );
    }
    if (/^[-*]\s+/.test(trimmed) || /^\d+[.、]\s*/.test(trimmed)) {
      return (
        <div className="answer-list-line" key={key}>
          {renderInlineWithCitations(trimmed.replace(/^[-*]\s+/, "• "), citations, onCitationClick)}
        </div>
      );
    }
    return (
      <Paragraph className="answer-line" key={key}>
        {renderInlineWithCitations(line, citations, onCitationClick)}
      </Paragraph>
    );
  });
}

function isFailureText(text: string) {
  return text.startsWith("模型接口调用失败") || text.startsWith("请求失败") || text.startsWith("生成失败");
}

function loadHistory(): ChatMessage[] {
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ChatMessage[];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item.id === "string" && typeof item.question === "string")
      .map((item) => {
        const answer = typeof item.answer === "string" ? item.answer : "";
        const status = typeof item.status === "string" ? item.status : "";
        const failed = Boolean(item.failed) || isFailureText(answer) || isFailureText(status);
        return {
          ...item,
          toolCalls: item.toolCalls ?? [],
          citations: (item.citations ?? []).map((citation) => ({
            ...citation,
            score: typeof citation.score === "number" && citation.score >= 100 ? 0 : citation.score
          })),
          failed,
          errorMessage: item.errorMessage ?? (failed ? answer || status : undefined)
        };
      })
      .slice(-30);
  } catch {
    return [];
  }
}

function saveHistory(messages: ChatMessage[]) {
  const stableMessages = messages.map((item) => ({
    ...item,
    done: true,
    status: item.done ? item.status : "生成被刷新中断"
  }));
  try {
    window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(stableMessages.slice(-30)));
  } catch {
    // localStorage 被禁用或容量已满时静默忽略，不影响问答功能。
  }
}

function evidenceTag(item: ChatMessage) {
  if (item.failed) return <Tag color="red">生成失败</Tag>;
  if (item.citations.length > 0) return <Tag color="green">OSS 文档 {item.citations.length}</Tag>;
  if (item.done) return <Tag color="orange">无引用</Tag>;
  return <Tag color="gold">检索中</Tag>;
}

function intentLabel(intent?: Intent) {
  const labels: Record<Intent, string> = {
    knowledge: "知识问答",
    doc_lookup: "文档查询",
    api_reference: "API 参考",
    permission: "权限/安全",
    troubleshooting: "故障排查",
    cost: "成本优化",
    smalltalk: "闲聊"
  };
  return intent ? labels[intent] : "识别中";
}

function toolLabel(name: string) {
  const labels: Record<string, string> = {
    troubleshoot_lookup: "故障排查",
    permission_lookup: "权限指南",
    api_lookup: "API 查询",
    cost_lookup: "成本优化",
    doc_lookup: "文档查询",
    topic_lookup: "主题检索"
  };
  return labels[name] ?? name;
}

function citationScoreLabel(score?: number) {
  if (typeof score !== "number" || score <= 0 || score >= 100) return "工具命中";
  const value = score >= 10 ? score.toFixed(1) : score.toFixed(2);
  return `相关度 ${value}`;
}

function sortCitationsByRelevance(citations: Citation[]) {
  // 展示顺序按相关度从高到低；保留原始引用编号，保证回答中 [n] 的跳转关系不变。
  return citations
    .map((citation, index) => ({ citation, number: index + 1 }))
    .sort((a, b) => {
      const left = typeof a.citation.score === "number" && a.citation.score < 100 ? a.citation.score : 0;
      const right = typeof b.citation.score === "number" && b.citation.score < 100 ? b.citation.score : 0;
      if (right !== left) return right - left;
      return a.number - b.number;
    });
}

function KnowledgeProof({ item }: { item: ChatMessage }) {
  const sourceTitles = Array.from(new Set(item.citations.map((citation) => citation.source_title))).slice(0, 2);
  if (item.failed) {
    return (
      <div className="rag-proof failed">
        <BookOpen size={15} />
        <span>
          OSS 文档检索已完成{item.citations.length ? `，命中 ${item.citations.length} 个片段` : ""}，但模型生成失败；这些片段仅作为排查依据。
        </span>
      </div>
    );
  }
  if (item.citations.length > 0) {
    return (
      <div className="rag-proof verified">
        <BookOpen size={15} />
        <span>
          本次回答已基于阿里云 OSS 支持知识库生成，命中 {item.citations.length} 个片段
          {sourceTitles.length ? `，来源：${sourceTitles.join("、")}` : ""}。
        </span>
      </div>
    );
  }
  return (
    <div className={item.done ? "rag-proof missing" : "rag-proof pending"}>
      <BookOpen size={15} />
      <span>{item.done ? "本次回答没有返回 OSS 文档引用，请换一个更具体的问题。" : "正在检索阿里云 OSS 支持知识库并等待引用。"}</span>
    </div>
  );
}

function MessageStatus({ item }: { item: ChatMessage }) {
  return (
    <div className="message-meta">
      <Tag color="blue">{intentLabel(item.intent)}</Tag>
      {evidenceTag(item)}
      <Text type="secondary">{item.createdAt}</Text>
      {!item.done && <Spin size="small" />}
    </div>
  );
}

async function readJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} ${response.status}`);
  return response.json() as Promise<T>;
}

const initialHistory = loadHistory();

function AppShell() {
  const { message } = App.useApp();
  const [documents, setDocuments] = useState<SupportDocument[]>([]);
  const [topics, setTopics] = useState<TopicItem[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [selectedDocument, setSelectedDocument] = useState<SupportDocument | null>(null);
  const [documentModalOpen, setDocumentModalOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [question, setQuestion] = useState("OSS 403 AccessDenied 应该怎么排查？");
  const [messages, setMessages] = useState<ChatMessage[]>(initialHistory);
  const [activeMessageId, setActiveMessageId] = useState(initialHistory[initialHistory.length - 1]?.id ?? "");
  const [openEvidenceKeys, setOpenEvidenceKeys] = useState<string[]>([]);
  const [highlightedCitationKey, setHighlightedCitationKey] = useState("");
  const [inFlight, setInFlight] = useState(0);
  const [health, setHealth] = useState<HealthState | null>(null);
  const busy = inFlight > 0;

  useEffect(() => {
    readJson<HealthState>("/health")
      .then(setHealth)
      .catch(() => setHealth(null));
    readJson<SupportDocument[]>("/documents")
      .then((items) => {
        setDocuments(items);
        setSelectedDocumentId(items[0]?.id ?? "");
      })
      .catch((error) => message.error(`OSS 文档清单加载失败：${error.message}`));
    readJson<TopicItem[]>("/topics")
      .then(setTopics)
      .catch(() => setTopics([]));
  }, [message]);

  useEffect(() => {
    if (!selectedDocumentId) return;
    readJson<{ found: boolean; document: SupportDocument }>(`/documents/${selectedDocumentId}`)
      .then((payload) => setSelectedDocument(payload.document))
      .catch((error) => message.error(`OSS 文档加载失败：${error.message}`));
  }, [message, selectedDocumentId]);

  useEffect(() => {
    saveHistory(messages);
  }, [messages]);

  const activeMessage = useMemo(
    () => messages.find((item) => item.id === activeMessageId) ?? messages[messages.length - 1],
    [activeMessageId, messages]
  );

  useEffect(() => {
    // 默认展开相关度最高的前两条知识库依据。
    setOpenEvidenceKeys(
      sortCitationsByRelevance(activeMessage?.citations ?? [])
        .slice(0, 2)
        .map(({ citation }) => citation.chunk_id)
    );
  }, [activeMessage?.id, activeMessage?.citations.length]);

  const filteredDocuments = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return documents;
    return documents.filter((doc) =>
      [doc.title, doc.category, doc.summary, ...doc.tags, ...doc.related_apis, ...doc.common_errors]
        .join(" ")
        .toLowerCase()
        .includes(keyword)
    );
  }, [documents, query]);

  function openDocument(documentId: string) {
    if (documentId !== selectedDocumentId) {
      // 切换文档时先清空旧详情，弹窗内显示加载状态而不是上一篇内容。
      setSelectedDocument(null);
      setSelectedDocumentId(documentId);
    }
    setDocumentModalOpen(true);
  }

  function jumpToCitation(messageId: string, citationNumber: number) {
    const messageItem = messages.find((item) => item.id === messageId);
    const citation = messageItem?.citations[citationNumber - 1];
    if (!citation) return;
    const anchorId = citationAnchorId(messageId, citationNumber);
    setActiveMessageId(messageId);
    setHighlightedCitationKey(anchorId);
    window.setTimeout(() => {
      setOpenEvidenceKeys((keys) => Array.from(new Set([...keys, citation.chunk_id])));
      document.getElementById(anchorId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
    window.setTimeout(() => {
      setHighlightedCitationKey((current) => (current === anchorId ? "" : current));
    }, 1800);
  }

  function applyStreamPayload(messageId: string, payload: Record<string, unknown>) {
    setMessages((items) =>
      items.map((item) => {
        if (item.id !== messageId) return item;
        if (payload.type === "status") {
          return { ...item, status: String(payload.content ?? "") };
        }
        if (payload.type === "reasoning") {
          return { ...item, status: "模型正在组织技术支持回答" };
        }
        if (payload.type === "meta") {
          const state = payload.state as AgentState;
          return {
            ...item,
            status: "大模型正在生成 OSS 支持回答",
            intent: state.intent,
            toolCalls: state.tool_calls ?? [],
            citations: state.citations ?? []
          };
        }
        if (payload.type === "token") {
          return { ...item, answer: item.answer + String(payload.delta ?? payload.content ?? "") };
        }
        if (payload.type === "final") {
          const state = payload.state as AgentState;
          const answer = String(payload.content ?? item.answer);
          const failed = Boolean(state.error) || isFailureText(answer);
          return {
            ...item,
            done: true,
            failed,
            errorMessage: state.error ?? (failed ? answer : item.errorMessage),
            status: failed ? "生成失败" : "生成完成",
            answer,
            intent: state.intent ?? item.intent,
            toolCalls: state.tool_calls ?? item.toolCalls,
            citations: state.citations ?? item.citations
          };
        }
        return item;
      })
    );
  }

  function consumeSseBuffer(messageId: string, rawBuffer: string) {
    const events = rawBuffer.split("\n\n");
    const rest = events.pop() ?? "";
    for (const rawEvent of events) {
      const line = rawEvent.split("\n").find((item) => item.startsWith("data:"));
      if (!line) continue;
      try {
        const payload = JSON.parse(line.replace(/^data:\s*/, "")) as Record<string, unknown>;
        if (payload.type !== "done") applyStreamPayload(messageId, payload);
      } catch {
        // 忽略无法解析的单个 SSE 事件，避免整条流中断。
      }
    }
    return rest;
  }

  async function streamAsk(prompt: string) {
    if (busy) return;
    const id = nowId();
    const next: ChatMessage = {
      id,
      question: prompt,
      answer: "",
      status: "正在连接 OSS 知识库",
      done: false,
      failed: false,
      toolCalls: [],
      citations: [],
      createdAt: new Date().toLocaleTimeString()
    };
    setMessages((items) => [...items, next]);
    setActiveMessageId(id);
    setInFlight((current) => current + 1);

    try {
      const response = await fetch("/ask/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: prompt, conversation_id: "web" })
      });
      if (!response.ok || !response.body) throw new Error(`请求失败：${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        buffer = consumeSseBuffer(id, buffer);
      }
      if (buffer.trim()) consumeSseBuffer(id, `${buffer}\n\n`);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "未知错误";
      setMessages((items) =>
        items.map((item) =>
          item.id === id
            ? {
                ...item,
                done: true,
                failed: true,
                errorMessage,
                status: `生成失败：${errorMessage}`,
                answer: `请求失败：${errorMessage}`
              }
            : item
        )
      );
      message.error(errorMessage);
    } finally {
      setInFlight((current) => Math.max(0, current - 1));
    }
  }

  return (
    <Layout className="app-shell">
      <Sider width={300} className="conversation-sider">
        <div className="brand">
          <div className="brand-mark"><Cloud size={22} /></div>
          <div>
            <Title level={4}>Aliyun OSS RAG</Title>
            <Text type="secondary">对象存储技术支持</Text>
          </div>
        </div>

        <div className="sider-stats">
          <Tag color="blue">文档 {health?.documents ?? documents.length}</Tag>
          <Tag color="green">Chunks {health?.chunks ?? "--"}</Tag>
          <Tag color="gold">主题 {topics.length || "--"}</Tag>
          <Tag color="purple">历史 {messages.length}</Tag>
        </div>

        <div className="sider-section-title">
          <History size={15} />
          <span>对话历史</span>
        </div>

        {messages.length === 0 ? (
          <div className="conversation-empty">
            <Empty description="暂无历史。发送问题后显示在这里。" />
          </div>
        ) : (
          <div className="conversation-rail" aria-label="对话历史列表">
            {[...messages].reverse().map((item) => (
              <button
                key={item.id}
                type="button"
                className={[
                  "conversation-item",
                  item.id === activeMessage?.id ? "active" : "",
                  item.failed ? "failed" : ""
                ].filter(Boolean).join(" ")}
                onClick={() => setActiveMessageId(item.id)}
              >
                <span className="conversation-title">{item.question}</span>
                <span className="conversation-subtitle">{item.status}</span>
                <span className="conversation-tags">
                  <Tag color="blue">{intentLabel(item.intent)}</Tag>
                  {evidenceTag(item)}
                  <Text type="secondary">{item.createdAt}</Text>
                  {!item.done && <Spin size="small" />}
                </span>
              </button>
            ))}
          </div>
        )}
      </Sider>

      <Layout>
        <Header className="app-header">
          <Space direction="vertical" size={0}>
            <Title level={3}>阿里云 OSS 技术 RAG 问答</Title>
            <Space wrap size={8} className="header-status">
              <Tag color="blue">产品 {health?.product ?? "Alibaba Cloud OSS"}</Tag>
              <Tag color="green">模型 {health?.model ?? "--"}</Tag>
              <Tag color="gold">本地知识库 {health?.chunks ?? "--"} chunks</Tag>
              <Tag color={health?.vector_index_enabled ? "cyan" : "default"}>
                检索 {health?.retrieval_mode === "hybrid_dense_vector_bm25" ? "向量+BM25" : "BM25回退"}
              </Tag>
            </Space>
          </Space>
        </Header>

        <Content className="workspace">
          <section className="chat-panel">
            <div className="chat-messages">
              {activeMessage ? (
                <article className={["chat-thread", activeMessage.failed ? "failed" : ""].filter(Boolean).join(" ")}>
                  <div className="chat-question-row">
                    <div className="chat-question-bubble">{activeMessage.question}</div>
                  </div>
                  <div className="chat-answer-card">
                    <MessageStatus item={activeMessage} />
                    <KnowledgeProof item={activeMessage} />
                    <div className={activeMessage.failed ? "answer-text answer-text-failed" : "answer-text"}>
                      {activeMessage.answer
                        ? renderAnswer(activeMessage.answer, activeMessage.citations, (citationNumber) => jumpToCitation(activeMessage.id, citationNumber))
                        : activeMessage.status}
                      {!activeMessage.done && <span className="cursor">|</span>}
                    </div>
                  </div>
                </article>
              ) : (
                <div className="chat-empty">
                  <Empty description="暂无对话。输入 OSS 技术支持问题，或点击下方示例开始。" />
                </div>
              )}
            </div>

            <Card className="composer-card">
              <Space direction="vertical" size={12} className="full-width">
                <div className="example-panel">
                  <div className="example-heading">
                    <Text strong>示例问题</Text>
                    <Text type="secondary">点击填入输入框，发送后仍会保留在这里</Text>
                  </div>
                  <div className="quick-row">
                    {QUICK_QUESTIONS.map((item) => (
                      <Button key={item} size="small" onClick={() => setQuestion(item)}>
                        {item}
                      </Button>
                    ))}
                  </div>
                </div>
                <div className="ask-grid">
                  <TextArea
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    autoSize={{ minRows: 2, maxRows: 6 }}
                    placeholder="输入 OSS 技术支持问题，例如：SignatureDoesNotMatch 怎么排查？"
                    onPressEnter={(event) => {
                      // Shift+Enter 换行；中文输入法选词回车（isComposing）不触发发送。
                      if (!event.shiftKey && !event.nativeEvent.isComposing) {
                        event.preventDefault();
                        if (!busy && question.trim()) streamAsk(question.trim());
                      }
                    }}
                  />
                  <Button
                    type="primary"
                    icon={<Send size={16} />}
                    disabled={busy || !question.trim()}
                    loading={busy}
                    onClick={() => streamAsk(question.trim())}
                  >
                    发送
                  </Button>
                </div>
              </Space>
            </Card>
          </section>

          <aside className="right-panel">
            <Card title={<Space><FileText size={18} />OSS 知识库</Space>} className="kb-card">
              <Input
                className="kb-search"
                prefix={<Search size={16} />}
                placeholder="搜索权限、错误码、API、CORS"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                allowClear
              />
              {filteredDocuments.length === 0 ? (
                <Empty description="没有匹配的 OSS 文档" />
              ) : (
                <List
                  className="kb-list"
                  dataSource={filteredDocuments}
                  renderItem={(item) => (
                    <List.Item
                      className={item.id === selectedDocumentId ? "kb-item active" : "kb-item"}
                      onClick={() => openDocument(item.id)}
                    >
                      <Space direction="vertical" size={4}>
                        <Space>
                          <Badge color={item.doc_type === "troubleshooting" ? "#d04f4f" : item.category.includes("权限") ? "#2f6f9f" : "#2f7d32"} />
                          <Text strong>{item.title}</Text>
                        </Space>
                        <Space size={4} wrap>
                          <Tag>{item.category}</Tag>
                          {item.related_apis.slice(0, 2).map((api) => <Tag key={api} color="blue">{api}</Tag>)}
                          {item.common_errors.slice(0, 1).map((err) => <Tag key={err} color="red">{err}</Tag>)}
                        </Space>
                      </Space>
                    </List.Item>
                  )}
                />
              )}
            </Card>

            <Card title={<Space><BookOpen size={18} />知识库依据</Space>} className="evidence-card">
              {!activeMessage ? (
                <Empty description="生成回答后显示检索依据" />
              ) : (
                <Space direction="vertical" size={14} className="full-width">
                  <Alert
                    type={activeMessage.failed ? "error" : activeMessage.citations.length ? "success" : "warning"}
                    showIcon
                    message={
                      activeMessage.failed
                        ? "模型生成失败，OSS 检索结果仅供排查"
                        : activeMessage.citations.length
                        ? `本次回答使用 ${activeMessage.citations.length} 条 OSS 文档片段`
                        : "尚未收到 OSS 文档引用"
                    }
                    description={activeMessage.failed ? activeMessage.errorMessage ?? activeMessage.status : activeMessage.status}
                  />
                  <div className="state-panel">
                    <Text strong>Agent 调用状态</Text>
                    <div className="state-tags">
                      <Tag color="blue">意图：{intentLabel(activeMessage.intent)}</Tag>
                      {activeMessage.toolCalls.length ? (
                        activeMessage.toolCalls.map((call, index) => (
                          <Tag color="cyan" key={`${activeMessage.id}-${call.name}-${index}`}>
                            工具：{toolLabel(call.name)}
                          </Tag>
                        ))
                      ) : (
                        <Tag>工具：无</Tag>
                      )}
                      <Tag color={activeMessage.citations.length ? "gold" : "default"}>引用：{activeMessage.citations.length}</Tag>
                      <Tag color={activeMessage.done ? (activeMessage.failed ? "red" : "green") : "processing"}>
                        状态：{activeMessage.done ? (activeMessage.failed ? "生成失败" : "生成完成") : "生成中"}
                      </Tag>
                    </div>
                  </div>
                  <Collapse
                    size="small"
                    activeKey={openEvidenceKeys}
                    onChange={(keys) => setOpenEvidenceKeys(Array.isArray(keys) ? keys.map(String) : [String(keys)])}
                    items={sortCitationsByRelevance(activeMessage.citations).map(({ citation: item, number }) => ({
                      key: item.chunk_id,
                      label: (
                        <div
                          id={citationAnchorId(activeMessage.id, number)}
                          className={[
                            "citation-evidence-label",
                            highlightedCitationKey === citationAnchorId(activeMessage.id, number) ? "highlighted" : ""
                          ].filter(Boolean).join(" ")}
                        >
                          <span>[{number}] {item.title}</span>
                          <Tag color="blue">{item.category ?? "OSS"}</Tag>
                          <Tag>{citationScoreLabel(item.score)}</Tag>
                        </div>
                      ),
                      children: (
                        <Space direction="vertical" size={8}>
                          <Text>{item.snippet}</Text>
                          <a href={item.url} target="_blank" rel="noreferrer">{item.source_title}</a>
                        </Space>
                      )
                    }))}
                  />
                </Space>
              )}
            </Card>
          </aside>
        </Content>
      </Layout>

      <Modal
        open={documentModalOpen}
        onCancel={() => setDocumentModalOpen(false)}
        footer={null}
        width={760}
        title={
          <Space>
            <FileText size={18} />
            <span>{selectedDocument?.title ?? "OSS 文档详情"}</span>
          </Space>
        }
      >
        {selectedDocument ? (
          <Space direction="vertical" size={12} className="full-width document-modal-body">
            <Text type="secondary">{selectedDocument.category} · {selectedDocument.doc_type}</Text>
            <Paragraph>{selectedDocument.summary}</Paragraph>
            <Space wrap size={6}>
              {selectedDocument.tags.slice(0, 10).map((tag) => <Tag key={tag}>{tag}</Tag>)}
            </Space>
            <Collapse
              key={selectedDocument.id}
              size="small"
              defaultActiveKey={selectedDocument.sections?.[0]?.heading}
              items={(selectedDocument.sections ?? []).map((section) => ({
                key: section.heading,
                label: `${section.heading} · ${section.kind}`,
                children: <Paragraph>{section.content}</Paragraph>
              }))}
            />
            <a href={selectedDocument.url} target="_blank" rel="noreferrer">打开官方来源</a>
          </Space>
        ) : (
          <div className="document-modal-loading">
            <Spin tip="正在加载 OSS 文档详情" />
          </div>
        )}
      </Modal>
    </Layout>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#1f6feb",
          borderRadius: 6,
          fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
        }
      }}
    >
      <App>
        <AppShell />
      </App>
    </ConfigProvider>
  </React.StrictMode>
);
