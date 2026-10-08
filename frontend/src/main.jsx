import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import JSZip from "jszip";
import { jsPDF } from "jspdf";
import "./styles.css";

const tabs = [
  ["overview", "◈", "Business overview"],
  ["anomaly", "⌁", "Anomaly detection"],
  ["history", "◷", "Previous history"],
  ["evidence", "▤", "Evidence explorer"],
  ["causes", "◎", "Root-cause analysis"],
  ["solution", "✦", "Solution planner"],
  ["review", "✓", "Verification & report"],
  ["method", "⚙", "How it works"],
];

function App() {
  const [view, setView] = useState(() => window.location.hash.replace("#", "") || "overview");
  const [data, setData] = useState(null);
  const [decision, setDecision] = useState(() => {
    const saved = localStorage.getItem("pygenicArc.lastDecision");
    return saved === "approved" || saved === "rejected" ? saved : "";
  });
  const [report, setReport] = useState("");
  const [uploadStatus, setUploadStatus] = useState("");
  const [pipelineStage, setPipelineStage] = useState(0);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState([{ role: "bot", text: "I’m ready to explain this investigation. Ask me about the anomaly, evidence, root cause, conflict, or recommended action." }]);
  const [chatLoading, setChatLoading] = useState(false);
  const [selectedPreviousFiles, setSelectedPreviousFiles] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [selectedAnomaly, setSelectedAnomalyState] = useState(() => {
    try { return JSON.parse(localStorage.getItem("pygenicArc.selectedAnomaly") || "null"); } catch { return null; }
  });

  const load = async () => {
    setLoadError("");
    const uploads = JSON.parse(localStorage.getItem("pygenicArc.uploads") || "[]");
    const browserHistory = JSON.parse(localStorage.getItem("pygenicArc.history") || "[]");
    try {
      const health = await fetch("/api/health", { cache: "no-store" });
      if (!health.ok) throw new Error(`Backend health check failed (HTTP ${health.status}).`);
      const healthData = await health.json();
      let response = await fetch("/api/investigate", { cache: "no-store" });
      let body = await response.text();
      if (!response.ok) throw new Error(`Investigation service returned HTTP ${response.status}.`);
      if (!body.trim()) throw new Error("Investigation service returned an empty response.");
      let serverData;
      try {
        serverData = JSON.parse(body);
      } catch {
        throw new Error("Investigation service returned invalid JSON.");
      }
      if (serverData.ready === false) {
        setSelectedAnomalyState(null);
        localStorage.removeItem("pygenicArc.selectedAnomaly");
      } else if (!selectedAnomaly && serverData.anomalies?.length) {
        const highest = serverData.anomalies[0];
        setSelectedAnomalyState(highest);
        localStorage.setItem("pygenicArc.selectedAnomaly", JSON.stringify(highest));
      }
      setData({ ...serverData, monitor: healthData.monitor, uploads: serverData.ready === false ? [] : uploads, storedUploads: uploads, browserHistory, historyCount: browserHistory.length });
    } catch (error) {
      setLoadError(error.message || "The backend is unavailable. Start backend\\app.py and retry.");
    }
  };
  useEffect(() => {
    load();
    const monitorRefresh = window.setInterval(load, 3000);
    return () => window.clearInterval(monitorRefresh);
  }, []);
  useEffect(() => {
    const onHashChange = () => setView(window.location.hash.replace("#", "") || "overview");
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  if (!data && loadError) return <div className="loading"><div className="load-error"><b>Unable to load investigation workspace</b><p>{loadError}</p><button className="primary" onClick={load}>Retry</button></div></div>;
  if (!data) return <div className="loading">Loading investigation workspace…</div>;
  const hasInvestigation = data.ready !== false;
  const setSelectedAnomaly = (anomaly) => {
    setSelectedAnomalyState(anomaly);
    localStorage.setItem("pygenicArc.selectedAnomaly", JSON.stringify(anomaly));
  };

  const verify = async (value) => {
    if (value !== "rejected") {
      const history = JSON.parse(localStorage.getItem("pygenicArc.history") || "[]");
      const localCase = { case_id: `LOCAL-${String(history.length + 1).padStart(3, "0")}`, problem: data.anomaly.description, root_cause: data.causes[0].name, solution: data.solution.plan[0], decision: value, saved_at: new Date().toISOString() };
      localStorage.setItem("pygenicArc.history", JSON.stringify([...history, localCase]));
    }
    localStorage.setItem("pygenicArc.lastDecision", value);
    setDecision(value);
    setPipelineStage(value === "approved" ? 8 : 7);
    await load();
  };
  const generateReport = async () => {
    try {
      const response = await fetch(`/api/investigation/${data.id}/report`);
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || body.message || `Report request failed (HTTP ${response.status})`);
      setReport(JSON.stringify({ ...body, browser_history: data.browserHistory, browser_uploads: data.uploads }, null, 2));
    } catch (error) {
      setReport(`Report request failed: ${error.message}`);
    }
  };
  const downloadPdf = () => {
    const pdf = new jsPDF({ unit: "mm", format: "a4" });
    const pageWidth = 210;
    const margin = 17;
    const contentWidth = pageWidth - margin * 2;
    let y = 18;
    let page = 1;
    const addPageIfNeeded = (height = 8) => {
      if (y + height <= 280) return;
      pdf.addPage();
      page += 1;
      y = 18;
      drawHeader();
    };
    const drawHeader = () => {
      pdf.setFillColor(20, 46, 88);
      pdf.rect(0, 0, pageWidth, 10, "F");
      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(8);
      pdf.setTextColor(255, 255, 255);
      pdf.text("PYGENIC ARC  |  E-COMMERCE INVESTIGATION", margin, 6.5);
      pdf.setTextColor(20, 35, 61);
    };
    const footer = () => {
      pdf.setDrawColor(220, 226, 235);
      pdf.line(margin, 286, pageWidth - margin, 286);
      pdf.setFont("helvetica", "normal");
      pdf.setFontSize(8);
      pdf.setTextColor(114, 129, 155);
      pdf.text("Evidence-first analysis · Suggestions only · No production remediation executed", margin, 292);
      pdf.text(`Page ${page}`, pageWidth - margin - 14, 292);
      pdf.setTextColor(20, 35, 61);
    };
    const section = (title) => {
      addPageIfNeeded(16);
      y += 5;
      pdf.setFillColor(234, 242, 255);
      pdf.roundedRect(margin, y - 5, contentWidth, 9, 2, 2, "F");
      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(11);
      pdf.setTextColor(33, 103, 213);
      pdf.text(title, margin + 4, y + 1);
      pdf.setTextColor(20, 35, 61);
      y += 11;
    };
    const paragraph = (text, options = {}) => {
      const lines = pdf.splitTextToSize(text, contentWidth - (options.indent || 0));
      addPageIfNeeded(lines.length * 5 + 3);
      pdf.setFont("helvetica", options.bold ? "bold" : "normal");
      pdf.setFontSize(options.size || 9.5);
      pdf.text(lines, margin + (options.indent || 0), y);
      y += lines.length * 5 + 3;
    };
    const keyValue = (label, value) => {
      addPageIfNeeded(7);
      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(9);
      pdf.text(`${label}:`, margin, y);
      pdf.setFont("helvetica", "normal");
      pdf.text(String(value), margin + 39, y);
      y += 6;
    };
    const tableRow = (columns, widths, header = false) => {
      const rowHeight = header ? 8 : 10;
      addPageIfNeeded(rowHeight);
      let x = margin;
      pdf.setFillColor(...(header ? [20, 46, 88] : [248, 250, 253]));
      pdf.rect(margin, y - 5, contentWidth, rowHeight, "F");
      columns.forEach((column, index) => {
        pdf.setFont("helvetica", header ? "bold" : "normal");
        pdf.setFontSize(header ? 8 : 8.5);
        pdf.setTextColor(...(header ? [255, 255, 255] : [20, 35, 61]));
        pdf.text(pdf.splitTextToSize(String(column), widths[index] - 4), x + 2, y);
        x += widths[index];
      });
      pdf.setTextColor(20, 35, 61);
      y += rowHeight;
    };

    drawHeader();
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(21);
    pdf.text("Investigation Report", margin, y + 8);
    y += 15;
    pdf.setFont("helvetica", "normal");
    pdf.setFontSize(9);
    pdf.setTextColor(114, 129, 155);
    pdf.text("Pygenic Arc · E-commerce Business Process Investigator", margin, y);
    y += 8;
    pdf.setTextColor(20, 35, 61);

    section("1. Executive summary");
    paragraph(`The uploaded data shows ${data.anomaly.metric} changing from ${data.anomaly.baseline} to ${data.anomaly.current}, a ${Math.abs(data.anomaly.deviation_percent)}% deviation. The leading explanation is ${data.causes[0].name} with a ${data.causes[0].score}% confidence / evidence score. This conclusion uses only the evidence returned by the backend.`);
    keyValue("Investigation ID", data.id);
    keyValue("Severity", data.anomaly.severity);
    keyValue("Anomaly score", data.anomaly.anomaly_score);

    section("2. KPI impact");
    tableRow(["Metric", "Before / baseline", "During incident", "Change"], [57, 41, 41, 41], true);
    tableRow([data.anomaly.metric, `${data.anomaly.baseline}`, `${data.anomaly.current}`, `${data.anomaly.deviation_percent}%`], [57, 41, 41, 41]);

    section("3. Evidence trail");
    data.evidence.forEach((item) => {
      paragraph(`${item.id} · ${item.source} · ${item.conflict ? "CONFLICTING" : "SUPPORTING"}\n${item.description}\nRelevance score: ${item.relevance_score}`, { indent: 2 });
    });

    if (data.conflicts?.length) {
      section("4. Conflicting signals");
      data.conflicts.forEach((item) => paragraph(`${item.id} · ${item.description}`, { indent: 2 }));
    }

    section("5. Ranked root causes");
    data.causes.forEach((cause, index) => {
      paragraph(`${index + 1}. ${cause.name} — ${cause.score}% confidence / evidence score`, { bold: true });
      paragraph(`${cause.explanation} Supporting evidence: ${cause.evidence_ids.join(", ")}.`, { indent: 4 });
    });

    section("6. Recommended action plan");
    data.solution.plan.forEach((step, index) => paragraph(`${index + 1}. ${step}`, { indent: 3 }));
    paragraph(data.solution.disclaimer);

    section("7. Human verification");
    keyValue("Decision", decision || "Pending");
    paragraph("This report is advisory. No production system was changed automatically. An approved or modified result is saved only in the browser's local investigation history.");
    for (let currentPage = 1; currentPage <= page; currentPage += 1) {
      // Footer is added after content is complete to every page.
    }
    const totalPages = pdf.getNumberOfPages();
    for (let index = 1; index <= totalPages; index += 1) {
      pdf.setPage(index);
      page = index;
      footer();
    }
    pdf.save(`pygenic-arc-${data.id}.pdf`);
  };
  const askChatbot = async () => {
    const question = chatInput.trim();
    if (!question) return;
    setChatMessages((messages) => [...messages, { role: "user", text: question }]);
    setChatInput("");
    setChatLoading(true);
    try {
      const response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, context: { anomaly: data.anomaly, evidence: data.evidence, causes: data.causes, solution: data.solution, historical_cases: data.historical_cases, browser_history: data.browserHistory } }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Assistant request failed (HTTP ${response.status})`);
      setChatMessages((messages) => [...messages, { role: "bot", text: result.answer }]);
    } catch (error) { setChatMessages((messages) => [...messages, { role: "bot", text: `Assistant error: ${error.message}` }]); }
    finally { setChatLoading(false); }
  };
  const upload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!/\.(csv|json|zip)$/i.test(file.name)) {
      setUploadStatus("Only CSV, JSON, and ZIP files are supported.");
      return;
    }
    try {
      const files = [];
      if (file.name.toLowerCase().endsWith(".zip")) {
        const archive = await JSZip.loadAsync(await file.arrayBuffer());
        for (const [path, zippedFile] of Object.entries(archive.files)) {
          if (zippedFile.dir || !/\.(csv|json)$/i.test(path)) continue;
          files.push({ name: path.split("/").pop(), type: path.toLowerCase().endsWith(".json") ? "JSON" : "CSV", content: await zippedFile.async("string") });
        }
        if (!files.length) throw new Error("ZIP must contain at least one CSV or JSON file.");
      } else {
        files.push({ name: file.name, type: file.name.toLowerCase().endsWith(".json") ? "JSON" : "CSV", content: await file.text() });
      }
      const uploads = JSON.parse(localStorage.getItem("pygenicArc.uploads") || "[]");
      const added = [];
      for (const item of files) {
        const parsed = item.type === "JSON" ? JSON.parse(item.content) : item.content.split(/\r?\n/).filter(Boolean);
        const entry = { ...item, records: Array.isArray(parsed) ? parsed.length : 1, addedAt: new Date().toISOString() };
        added.push(entry);
        try {
          const response = await fetch("/api/data/upload", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename: entry.name, content: entry.content }) });
          if (!response.ok) throw new Error((await response.json()).error || `Backend rejected ${entry.name}.`);
        } catch {
          throw new Error(`Backend rejected ${entry.name}; no local-only result was created.`);
        }
      }
      const names = new Set(added.map((item) => item.name));
      const retained = uploads.filter((item) => !names.has(item.name));
      localStorage.setItem("pygenicArc.uploads", JSON.stringify([...retained, ...added]));
      setUploadStatus(`${file.name} added · extracted ${added.length} CSV/JSON file${added.length === 1 ? "" : "s"}. RCA context refreshed.`);
      setSelectedAnomaly(null);
      localStorage.removeItem("pygenicArc.lastDecision");
      setDecision("");
      await load();
      runPipeline();
    } catch (error) {
      setUploadStatus(error.message || "The selected file could not be read.");
    }
  };
  const usePreviousData = async () => {
    const previousUploads = data.storedUploads || [];
    if (!previousUploads.length) return;
    try {
      for (const upload of previousUploads) {
        const response = await fetch("/api/data/upload", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: upload.name, content: upload.content }),
        });
        if (!response.ok) throw new Error(`Could not restore ${upload.name}.`);
      }
      setUploadStatus(`${previousUploads.length} previous file${previousUploads.length === 1 ? "" : "s"} restored from browser storage.`);
      localStorage.removeItem("pygenicArc.lastDecision");
      setDecision("");
      await load();
    } catch (error) {
      setUploadStatus(error.message || "Previous files could not be restored by the backend.");
    }
  };
  const deletePreviousData = async () => {
    if (!selectedPreviousFiles.length) {
      setUploadStatus("Select at least one previous file to delete.");
      return;
    }
    if (!window.confirm(`Delete ${selectedPreviousFiles.length} selected file${selectedPreviousFiles.length === 1 ? "" : "s"}?`)) return;
    const names = new Set(selectedPreviousFiles);
    const remaining = (data.storedUploads || []).filter((upload) => !names.has(upload.name));
    localStorage.setItem("pygenicArc.uploads", JSON.stringify(remaining));
    try { await fetch("/api/data/upload", { method: "DELETE" }); } catch { /* browser storage remains authoritative */ }
    setSelectedPreviousFiles([]);
    setUploadStatus(`${selectedPreviousFiles.length} selected file${selectedPreviousFiles.length === 1 ? "" : "s"} deleted.`);
    await load();
  };
  const runPipeline = async () => {
    setPipelineRunning(true);
    setPipelineStage(0);
    const stageDelays = [1200, 1400, 1200, 1500, 1300, 1500, 1200, 1200];
    for (let stage = 1; stage <= 8; stage += 1) {
      await new Promise((resolve) => setTimeout(resolve, stageDelays[stage - 1]));
      setPipelineStage(stage);
    }
    await new Promise((resolve) => setTimeout(resolve, 600));
    setPipelineRunning(false);
  };
  const navigate = (nextView) => {
    window.location.hash = nextView;
    setView(nextView);
    window.setTimeout(() => document.getElementById(nextView)?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand"><span>PA</span> Pygenic Arc</div>
        <div className="workspace"><small>WORKSPACE</small><b>E-commerce Operations</b></div>
        <div className="nav-label">INVESTIGATION</div>
        <nav>{tabs.map(([id, icon, label]) => <button type="button" key={id} className={view === id ? "active" : ""} onClick={() => navigate(id)}><i>{icon}</i>{label}</button>)}</nav>
      </aside>
      <main className="main">
        <header className="topbar">
          <div><small>Investigation / {data.id}</small><h1>Business process control room</h1><strong className={`status ${hasInvestigation ? "" : "waiting"}`}>{hasInvestigation ? "● Investigation ready · uploaded data" : "● Waiting for uploaded data"}</strong></div>
          <div className="actions"><button type="button" className="outline" onClick={load}>↻ Refresh data</button><button type="button" className="primary" onClick={() => navigate("review")}>Review recommendation →</button></div>
        </header>
        <UploadPanel data={data} onUpload={upload} onUsePrevious={usePreviousData} onDeletePrevious={deletePreviousData} selectedPreviousFiles={selectedPreviousFiles} setSelectedPreviousFiles={setSelectedPreviousFiles} status={uploadStatus} />
        {view === "history" ? <section id="history"><History data={data} /></section> : hasInvestigation ? <><section className="hero"><div><h2>Full e-commerce investigation</h2><p>Uploaded data is analyzed through anomaly detection, evidence scoring, Hybrid RCA, solution planning, human approval, PDF reporting, and the final causal graph.</p></div><div className="incident"><small>UPLOADED FILES</small><b>{data.uploads.length}</b><small>All stages active</small></div></section>
          <div className="backend-monitor"><b>Backend monitor:</b> {data.monitor?.running ? "running" : "starting"} · watching <code>{data.monitor?.source || "backend/incoming"}</code> · last file: {data.monitor?.last_file || "none"}{data.monitor?.anomaly_detected ? " · anomaly detected" : ""}{data.monitor?.last_error ? ` · error: ${data.monitor.last_error.message}` : ""}</div>{pipelineRunning && <InvestigationPipeline data={data} currentStage={pipelineStage} running={pipelineRunning} decision={decision} onRun={runPipeline} />}
          {view === "overview" && <section id="overview"><AnomalySelection data={data} selected={selectedAnomaly} onSelect={setSelectedAnomaly} /></section>}
          {view === "anomaly" && <section id="anomaly"><AnomalySelection data={data} selected={selectedAnomaly} onSelect={setSelectedAnomaly} /></section>}
          {view === "evidence" && <section id="evidence"><Evidence data={data} /></section>}
          {view === "causes" && <section id="causes"><Causes data={data} /></section>}
          {view === "solution" && <section id="solution"><Solution data={data} /></section>}
          {view === "review" && <section id="review"><Review data={data} decision={decision} verify={verify} report={report} generateReport={generateReport} downloadPdf={downloadPdf} /></section>}
          {view === "method" && <section id="method"><Method data={data} /></section>}
          {pipelineStage >= 8 && <FinalResult data={data} onPdf={downloadPdf} onChat={() => setChatOpen(true)} />}
        </> : <section className="upload-required"><h2>{view === "anomaly" ? "Upload data to detect anomalies" : "Upload data to begin"}</h2><p>The investigation is paused until you upload an e-commerce CSV, JSON, or ZIP containing CSV/JSON files. Results, evidence, causes, recommendations, PDF reports, and graphs will be calculated from those files only.</p></section>}
        <button className="chat-launcher" onClick={() => setChatOpen((open) => !open)}>✦ Ask investigator</button>
        {chatOpen && <Chatbot messages={chatMessages} input={chatInput} setInput={setChatInput} onAsk={askChatbot} onClose={() => setChatOpen(false)} loading={chatLoading} />}
      </main>
    </div>
  );
}

const Panel = ({ title, children }) => <section className="panel"><h3>{title}</h3>{children}</section>;
const Bar = ({ value, color = "var(--blue)" }) => <div className="bar"><div className="fill" style={{ width: `${value}%`, background: color }} /></div>;
const pipelineStages = [
  ["01", "Automatic Anomaly Detection", "Compare KPIs against historical baseline"],
  ["02", "Evidence Collection & Scoring", "Collect, filter, and rank source signals"],
  ["03", "Noisy & Conflicting Signals", "Flag unreliable and contradictory evidence"],
  ["04", "HybridRCA-Inspired Investigation", "Generate and rank competing causes"],
  ["05", "RAG / Investigation Memory", "Compare with historical incidents"],
  ["06", "Multi-Agent Decision Engine", "Plan and verify the recommendation"],
  ["07", "Human Verification / Approval", "Review before accepting any action"],
  ["08", "Final Investigation Report & Feedback Loop", "Save approved learning to browser history"],
];
function InvestigationPipeline({ data, currentStage, running, decision, onRun }) {
  const output = [
    `${data.anomaly.metric} changed by ${data.anomaly.deviation_percent}%`,
    `${data.evidence.length} evidence signals scored`,
    `${data.conflicts.length} conflicting signal flagged and down-weighted`,
    `${data.causes.length} plausible causes ranked`,
    `${data.historical_cases.length} historical cases retrieved`,
    `Top recommendation: ${data.solution.root_cause}`,
    "Waiting for a human decision",
    "Report ready; approval saves local browser history",
  ];
  const messages = [`Anomaly detected in ${data.anomaly.metric}: ${data.anomaly.deviation_percent}% deviation.`, `Evidence is collected from ${data.uploads.length} uploaded file(s).`, `${data.conflicts.length} conflicting signal(s) were returned by the backend.`, `${data.causes.length} plausible causes were compared using the evidence trail.`, `${data.historical_cases.length} historical case(s) were retrieved.`, "The solution plan is ready for review; no action is executed automatically.", "Please approve, modify, or reject the recommendation.", "The report is complete and approved results can be saved to browser history."];
  return <section className="pipeline-panel"><div className="section-title"><div><h2>Investigation in progress</h2><small>Upload → explainable RCA → human approval → feedback</small></div><button className="pipeline-run" onClick={onRun} disabled={running}>{running ? "Investigation running…" : "Run investigation again"}</button></div><div className="pipeline-steps">{pipelineStages.map(([number, title, description], index) => { const complete = running && index < currentStage; const active = running && currentStage === index; return <div className={`pipeline-step ${complete ? "complete" : ""} ${active ? "active" : ""}`} key={title}><div className="step-line"><span className="step-number">{number}</span>{index < pipelineStages.length - 1 && <i />}</div><div className="step-content"><div className="step-title"><b>{title}</b><span>{complete ? "Complete" : active ? "Running" : "Waiting"}</span></div><small>{description}</small>{(complete || active) && <><div className="step-output">{output[index]}</div><div className="stage-message">{active ? "Processing evidence…" : messages[index]}</div></>}</div></div>})}</div></section>;
}
function FinalResult({ data, onPdf, onChat }) {
  return <section className="final-result"><div className="final-heading"><div><span className="eyebrow">Investigation complete</span><h2>Short conclusion</h2><p><b>{data.causes[0].name}</b> is the leading cause with a <b>{data.causes[0].score}% confidence/evidence score</b>, based on the uploaded evidence returned by the backend.</p></div><div className="final-actions"><button className="primary" onClick={onPdf}>▣ Generate PDF</button><button className="outline" onClick={onChat}>✦ Ask chatbot</button></div></div><div className="mini-graph"><span className="graph-node blue">Anomaly<br /><b>{data.anomaly.metric} {data.anomaly.deviation_percent}%</b></span><i>→</i><span className="graph-node red">Evidence<br /><b>{data.evidence.length} signals</b></span><i>→</i><span className="graph-node orange">Conflicts<br /><b>{data.conflicts.length} returned</b></span><i>→</i><span className="graph-node green">Root cause<br /><b>{data.causes[0].name}</b></span><i>→</i><span className="graph-node purple">Action<br /><b>{data.solution.plan[0]}</b></span></div></section>;
}
function Chatbot({ messages, input, setInput, onAsk, onClose, loading }) {
  return <aside className="chatbot"><header><b>Pygenic Arc assistant</b><button onClick={onClose}>×</button></header><div className="chat-messages">{messages.map((message, index) => <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>{message.text}</div>)}{loading && <div className="chat-message bot">Analyzing the investigation context…</div>}</div><div className="chat-input"><input value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => event.key === "Enter" && onAsk()} placeholder="Ask about this report…" /><button onClick={onAsk} disabled={loading}>→</button></div><small>Gemini answers are grounded in the current e-commerce investigation; offline fallback is available.</small></aside>;
}
function UploadPanel({ data, onUpload, onUsePrevious, onDeletePrevious, selectedPreviousFiles, setSelectedPreviousFiles, status }) {
  const previousUploads = data.storedUploads || [];
  const toggleFile = (name) => setSelectedPreviousFiles((files) => files.includes(name) ? files.filter((file) => file !== name) : [...files, name]);
  return <section className="upload-panel"><div><span className="upload-icon">⇧</span><div><h3>Add business data</h3><p>Upload CSV, JSON, or a ZIP containing CSV/JSON evidence. Files are stored only in this browser.</p><small>Supported: metrics, transactions, tickets, logs, process events, and historical cases</small></div></div><label className="upload-button">Choose CSV / JSON / ZIP<input type="file" accept=".csv,.json,.zip, text/csv, application/json, application/zip" onChange={onUpload} /></label>{previousUploads.length > 0 && data.ready === false && <><button type="button" className="outline previous-data" onClick={onUsePrevious}>Use previous data ({previousUploads.length} file{previousUploads.length === 1 ? "" : "s"})</button><button type="button" className="delete-data" onClick={onDeletePrevious}>Delete selected ({selectedPreviousFiles.length})</button><div className="previous-file-list">{previousUploads.map((file) => <label key={file.name}><input type="checkbox" checked={selectedPreviousFiles.includes(file.name)} onChange={() => toggleFile(file.name)} /><span>{file.name} · {file.records} records</span></label>)}</div></>}{status && <div className="upload-status">{status}</div>}{data.uploads?.length > 0 && <div className="uploaded-files">{data.uploads.map((file) => <span key={file.name}>✓ {file.name} · {file.records} records</span>)}</div>}{previousUploads.length > 0 && data.ready === false && <div className="previous-files">Previous files are available locally but are not active in this investigation.</div>}</section>;
}

function AnomalySelection({ data, selected, onSelect }) {
  const anomalies = data.anomalies || [];
  return <section className="anomaly-selection"><div className="section-title"><div><h2>Automatic anomaly detection</h2><small>{anomalies.length} numeric anomaly candidates found from uploaded data</small></div><span className="step-badge">STEP 1 OF 8</span></div>{anomalies.length === 0 ? <div className="finding">No numeric anomalies could be calculated. Upload records with numeric business fields such as order value, completion rate, latency, failures, or inventory.</div> : <div className="anomaly-candidates">{anomalies.map((anomaly) => <button type="button" className={`anomaly-candidate ${anomaly.severity.toLowerCase()} ${selected?.id === anomaly.id ? "selected" : ""}`} key={anomaly.id} onClick={() => onSelect(anomaly)}><div><b>{anomaly.metric}</b><small>{anomaly.description}</small><small>Source: {anomaly.source} · value {anomaly.value} · average {anomaly.average}</small></div><strong>{anomaly.score}%<small>{anomaly.severity}</small></strong></button>)}</div>}{selected && <div className="selected-anomaly"><b>Selected anomaly: {selected.metric}</b><span>{selected.description}</span><small>High-severity anomaly selected. Later investigation stages will use this signal.</small></div>}</section>;
}
function History({ data }) {
  const history = data.browserHistory || [];
  return <><div className="section-title"><div><h2>Previous investigation history</h2><small>Saved only in this browser</small></div><span className="step-badge">{history.length} CASES</span></div><section className="history-list">{history.length === 0 ? <div className="finding">No approved investigation history exists yet. Complete an investigation and approve its recommendation to save a case here.</div> : history.slice().reverse().map((item) => <article className="history-card" key={`${item.case_id}-${item.saved_at}`}><div><b>{item.case_id}</b><small>{new Date(item.saved_at).toLocaleString()}</small></div><strong className={`history-decision ${item.decision}`}>{item.decision}</strong><p><b>Problem:</b> {item.problem}</p><p><b>Root cause:</b> {item.root_cause}</p><p><b>Solution:</b> {item.solution}</p></article>)}</section></>;
}

function Overview({ data, setView }) {
  const anomaly = data.anomaly;
  const cards = [[anomaly.metric, String(anomaly.current), "down", `${anomaly.deviation_percent}% vs baseline`], ["Records analyzed", String(data.uploads.reduce((total, file) => total + file.records, 0)), "up", `${data.uploads.length} uploaded file(s)`], ["Evidence signals", String(data.evidence.length), "up", "Backend-linked evidence"], ["Anomaly candidates", String(data.anomalies.length), "down", "Statistical detection"]];
  return <><div className="cards">{cards.map(([label, value, color, note]) => <div className="card" key={label}><small>{label}</small><strong className={color}>{value}</strong><span className={color}>{note}</span></div>)}</div>
    <div className="section-title"><h2>Investigation pipeline</h2><small>4 agents · evidence-first reasoning</small></div>
    <Panel title=""><div className="pipeline">{[["⌕", "Automatic detection", "Baseline comparison"], ["▤", "Evidence collection", "Filter + score signals"], ["!", "Conflict analysis", "Preserve noisy data"], ["◈", "Hybrid RCA", "Rank plausible causes"]].map(([icon, title, note]) => <div className="stage" key={title}><span>{icon}</span><b>{title}</b><small>{note}</small></div>)}</div></Panel>
    <div className="section-title"><h2>Business signal overview</h2><small>Current incident window vs baseline</small></div>
    <div className="two-col"><Panel title="Detected deviation"><div className="bar-row"><label>{anomaly.metric}</label><Bar value={Math.min(100, Math.abs(anomaly.deviation_percent))} color="var(--red)" /><em className="down">{anomaly.deviation_percent}%</em></div></Panel><Panel title="Investigation timeline"><Timeline data={data} /></Panel></div>
  </>;
}
function Timeline({ data }) { return <div className="timeline">{data.evidence.slice(0, 6).map((item) => <div className="event" key={item.id}><b>{item.timestamp} · {item.id}</b><small>{item.description}</small></div>)}</div>; }
function Anomaly({ data }) { return <><SectionHeading title="Anomaly detection" note="Deterministic statistical baseline" /><div className="two-col"><Panel title={data.anomaly.metric}><div className="outcome"><div><small>Historical baseline</small><b>{data.anomaly.baseline}</b></div><div><small>Observed value</small><b className="down">{data.anomaly.current}</b></div></div><Bar value={Math.min(100, Math.abs(data.anomaly.deviation_percent))} color="var(--red)" /><p>Deviation <b className="down">{data.anomaly.deviation_percent}%</b> · score <b>{data.anomaly.anomaly_score}</b> · <b className="down">{data.anomaly.severity}</b></p></Panel><Panel title="Why this is an anomaly"><p>{data.anomaly.description}</p><div className="finding"><b>Trigger condition</b><br />The backend detected the deviation from the uploaded records.</div></Panel></div></>; }
function Evidence({ data }) { return <><SectionHeading title="Evidence explorer" note={`${data.evidence.length} signals · 5 sources`} /><Panel title="Filtered and relevance-scored signals"><div className="evidence-list">{data.evidence.map((item) => <div className="evidence" key={item.id}><span className={`badge ${item.conflict ? "conflict" : "support"}`}>{item.conflict ? "conflict" : "supports"}</span><div><b>{item.description}</b><small>{item.source} · {item.timestamp} · relevance {item.relevance_score}</small>{item.conflict && <span className="warning">⚠ {item.conflict_explanation}</span>}</div><span className="badge">{item.severity}</span></div>)}</div></Panel></>; }
function Causes({ data }) { return <><SectionHeading title="Root-cause investigation" note="Evidence-guided ranking" /><div className="two-col"><Panel title="Ranked probable causes">{data.causes.map((cause) => <div className="cause" key={cause.id}><div className="cause-head"><b>{cause.name}</b><strong>{cause.score}%</strong></div><Bar value={cause.score} /><small>{cause.explanation}<br />Evidence: {cause.evidence_ids.join(", ") || "None"}</small></div>)}</Panel><Panel title="Conflict and causal reasoning">{data.conflicts.length ? data.conflicts.map((item) => <div className="conflict" key={item.id}><b>⚠ {item.id}</b> {item.description}</div>) : <div className="finding">No conflicting signals were returned by the backend.</div>}<div className="causal"><span>{data.anomaly.metric} {data.anomaly.deviation_percent}%</span> → <span>{data.evidence.length} evidence signals</span> → <strong>{data.causes[0].name}</strong></div></Panel></div></>; }
function Solution({ data }) { return <><SectionHeading title="Solution planner" note="Human-safe recommendation · no automatic remediation" /><div className="two-col"><Panel title="Recommended implementation plan"><p><b>{data.solution.root_cause}</b> · <strong className="score">{data.causes[0].score}% confidence / evidence</strong></p><ol>{data.solution.plan.map((step) => <li key={step}>{step}</li>)}</ol></Panel><Panel title="Projected / expected outcome"><div className="outcome">{Object.entries(data.solution.expected_outcome).map(([name, values]) => <div key={name}><small>{name.replaceAll("_", " ")}</small>{values.current} → <b className="ok">{values.projected}</b></div>)}</div><p className="muted">{data.solution.disclaimer}</p><h3>Historical investigation memory</h3>{data.historical_cases.map((item) => <div className="rag" key={item.case_id}><b>{item.case_id}</b> · {item.problem}<small>Root cause: {item.root_cause}<br />Solution: {item.solution}</small></div>)}</Panel></div></>; }
function Review({ data, decision, verify, report, generateReport, downloadPdf }) {
  const labels = { approved: "Approved", rejected: "Rejected" };
  const topCause = data.causes[0];
  const conflictText = data.conflicts?.length ? data.conflicts.map((item) => `${item.id}: ${item.description}`).join(" ") : "No conflicting signals were returned by the backend.";
  return <><SectionHeading title="Verification & final report" note={decision ? "Decision saved in this browser" : "Human decision required"} /><div className="two-col"><Panel title="AI investigation result"><div className="review"><div className={`decision-status ${decision || "pending"}`}><span>{decision ? "✓" : "!"}</span><div><b>{decision ? `Recommendation ${labels[decision]}` : "Awaiting your decision"}</b><small>{decision === "approved" ? "Accepted recommendation saved to browser history." : decision === "rejected" ? "This recommendation was rejected and was not saved to history." : "Choose Approve or Reject after reviewing the evidence."}</small></div></div><div className="history-mode"><b>{data.history.match_found ? "Historical comparison found" : "Fresh RCA investigation"}</b><small>{data.history.match_found ? "Similar incidents inform this recommendation." : "No sufficiently similar local incident was found; RCA reasoning is active."}</small><small>Browser history cases saved: {data.historyCount}</small></div><p><b>Root cause:</b> {topCause.name}</p><p><b>Confidence / evidence:</b> <span className="score">{topCause.score}%</span></p><p><b>Supporting evidence:</b> {topCause.evidence_ids.join(", ") || "None returned"}</p><p><b>Conflicting signals:</b> {conflictText}</p><div className="finding">Review evidence, assumptions, and projected outcome before accepting.</div><div className="decision"><button className="primary" disabled={decision === "approved"} onClick={() => verify("approved")}>{decision === "approved" ? "✓ Approved" : "Approve & save history"}</button><button className="reject" disabled={decision === "rejected"} onClick={() => verify("rejected")}>{decision === "rejected" ? "✓ Rejected" : "Reject"}</button></div></div></Panel><Panel title="Final investigation report"><p className="muted">Create a readable PDF report or inspect the structured JSON report.</p><div className="final-actions"><button className="primary" onClick={downloadPdf}>▣ Generate PDF</button><button className="outline" onClick={generateReport}>View JSON report</button></div>{report && <pre className="report">{report}</pre>}</Panel></div></>; }
function Method({ data }) { const details = data.method.agent_details || data.pipeline || []; return <><SectionHeading title="How Pygenic Arc works" note="Backend agents and evidence flow" /><Panel title="Executed investigation agents"><div className="pipeline">{details.map((agent, index) => <div className="stage" key={agent.name || agent}><span>{index + 1}</span><b>{agent.name || agent} </b><small>{agent.output || "Backend investigation stage"}</small></div>)}</div><div className="finding"><b>Data flow:</b> Browser uploads CSV/JSON/ZIP → backend validates records → Anomaly Detection Agent calculates numeric deviations → Evidence Collection Agent links findings to source files → Conflict Analysis preserves contradictory signals → Hybrid RCA Agent ranks plausible causes → RAG Memory Agent compares backend historical cases → Solution Planner proposes verification-first actions → Human Verification Gate waits for approval.</div><p className="muted">No stage invents telemetry. A missing or non-numeric dataset returns insufficient evidence instead of a fabricated diagnosis.</p></Panel></>; }
function SectionHeading({ title, note }) { return <div className="section-title"><h2>{title}</h2><small>{note}</small></div>; }

createRoot(document.getElementById("root")).render(<App />);
