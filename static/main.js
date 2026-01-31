let lastSiteData = null;
let allDocuments = [];
let selectedDocuments = [];
let chatHistory = [];
let currentDsn = null;
let sessionId = null;
let extractedDocuments = [];
let combinedExtractedText = "";

function showError(msg) {
  const banner = document.getElementById("error-banner");
  if (!banner) return;
  banner.textContent = msg || "";
  banner.style.display = msg ? "block" : "none";
}

function setAnalyzeLoading(isLoading) {
  const btn = document.getElementById("analyze-btn");
  if (!btn) return;
  btn.disabled = isLoading;
  btn.textContent = isLoading ? "Analyzing..." : "Analyze Site";
}

function setDocsLoading(isLoading) {
  const btn = document.getElementById("fetch-docs-btn");
  if (!btn) return;
  btn.disabled = isLoading;
  btn.innerHTML = isLoading 
    ? '<span class="loading-spinner"></span>Fetching...' 
    : "Fetch Documents";
}

function setExtractLoading(isLoading) {
  const btn = document.getElementById("extract-text-btn");
  if (!btn) return;
  btn.disabled = isLoading;
  btn.innerHTML = isLoading 
    ? '<span class="loading-spinner"></span>Extracting...' 
    : "Extract Text from Selected";
}

function setAutoAnalyzeLoading(isLoading, statusText = "") {
  const btn = document.getElementById("auto-analyze-btn");
  if (btn) {
    btn.disabled = isLoading;
    btn.innerHTML = isLoading 
      ? '<span class="loading-spinner"></span>Analyzing...' 
      : "Auto-Analyze All Documents";
  }
  
  const statusEl = document.getElementById("extraction-status");
  const statusTextEl = document.getElementById("extraction-status-text");
  if (statusEl && statusTextEl) {
    if (isLoading && statusText) {
      statusEl.style.display = "block";
      statusTextEl.innerHTML = '<span class="loading-spinner"></span>' + statusText;
    } else if (!isLoading) {
      statusEl.style.display = statusText ? "block" : "none";
      if (statusText) statusTextEl.textContent = statusText;
    }
  }
}

function fillSiteInfo(info) {
  const fields = {
    "site-dsn": info.dsn,
    "site-activity-number": info.activity_number,
    "site-status": info.status,
    "site-activity-type": info.activity_type,
    "site-location-name": info.location_name,
    "site-address": info.address,
    "site-municipality": info.municipality,
    "site-county": info.county,
    "site-region": info.dnr_region,
    "site-start-date": info.start_date,
    "site-end-date": info.end_date,
  };

  for (const [id, value] of Object.entries(fields)) {
    const el = document.getElementById(id);
    if (el) {
      el.textContent =
        value === undefined || value === null || value === ""
          ? "Not available"
          : value;
    }
  }
}

function updateRiskIndicators(flags) {
  const statusEl = document.getElementById("risk-status");
  const pfasEl = document.getElementById("risk-pfas");
  const petEl = document.getElementById("risk-petroleum");
  const metEl = document.getElementById("risk-metals");
  const offEl = document.getElementById("risk-offsite");

  if (statusEl) {
    statusEl.textContent = `Status: ${flags.status_label || "UNKNOWN"}`;
  }

  function mark(el, active) {
    if (!el) return;
    el.classList.remove("highlight", "good");
    if (active === true) {
      el.classList.add("highlight");
    } else if (active === false) {
      el.classList.add("good");
    }
  }

  mark(pfasEl, flags.pfas);
  mark(petEl, flags.petroleum);
  mark(metEl, flags.heavy_metals);
  mark(offEl, flags.offsite_impact);
}

function updateSelectedCount() {
  const countEl = document.getElementById("selected-count");
  const extractBtn = document.getElementById("extract-text-btn");
  
  if (countEl) {
    if (selectedDocuments.length > 0) {
      countEl.textContent = `${selectedDocuments.length} selected`;
    } else {
      countEl.textContent = "";
    }
  }
  
  // Show/hide extract button based on selection
  if (extractBtn) {
    extractBtn.style.display = selectedDocuments.length > 0 ? "inline-block" : "none";
  }
}

function renderDocuments() {
  const listEl = document.getElementById("doc-list");
  const countEl = document.getElementById("doc-count");
  
  if (!listEl) return;
  
  if (allDocuments.length === 0) {
    listEl.innerHTML = '<div class="empty-docs">No documents found for this site.</div>';
    if (countEl) countEl.textContent = "";
    return;
  }
  
  if (countEl) {
    countEl.textContent = `${allDocuments.length} document(s) found`;
  }
  
  let html = "";
  
  for (const doc of allDocuments) {
    const isSelected = selectedDocuments.some(d => d.id === doc.id);
    const name = doc.name || doc.action_code || "Unnamed Document";
    const meta = [doc.category, doc.date].filter(Boolean).join(" | ");
    
    html += `
      <div class="doc-item">
        <input type="checkbox" 
               id="doc-${doc.id}" 
               ${isSelected ? "checked" : ""} 
               onchange="toggleDocument(${doc.id})">
        <div class="doc-info">
          <div class="doc-name">${escapeHtml(name)}</div>
          <div class="doc-meta">${escapeHtml(meta)}</div>
          ${doc.comment ? `<div class="doc-meta">${escapeHtml(doc.comment)}</div>` : ""}
          ${doc.download_url ? `<a href="${doc.download_url}" target="_blank" class="doc-link">View Document</a>` : ""}
        </div>
      </div>
    `;
  }
  
  listEl.innerHTML = html;
  updateSelectedCount();
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}

function toggleDocument(docId) {
  const doc = allDocuments.find(d => d.id === docId);
  if (!doc) return;
  
  const isSelected = selectedDocuments.some(d => d.id === docId);
  
  if (isSelected) {
    selectedDocuments = selectedDocuments.filter(d => d.id !== docId);
  } else {
    selectedDocuments.push(doc);
  }
  
  updateSelectedCount();
}

function selectAllDocs() {
  selectedDocuments = [...allDocuments];
  renderDocuments();
}

function deselectAllDocs() {
  selectedDocuments = [];
  renderDocuments();
}

async function addManualDocument() {
  const input = document.getElementById("manual-doc-seq");
  if (!input) return;
  
  const docSeqNo = input.value.trim();
  if (!docSeqNo) {
    showError("Please enter a docSeqNo.");
    return;
  }
  
  showError("");
  
  try {
    const resp = await fetch("/api/documents/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        docSeqNo: docSeqNo,
        dsn: currentDsn 
      }),
    });
    
    const data = await resp.json();
    
    if (!resp.ok) {
      showError(data.error || "Failed to add document.");
      return;
    }
    
    if (data.document) {
      // Add to documents list with unique ID
      const newDoc = {
        ...data.document,
        id: allDocuments.length
      };
      allDocuments.push(newDoc);
      selectedDocuments.push(newDoc);
      renderDocuments();
      
      // Clear input
      input.value = "";
      
      // Show select all button
      const selectAllBtn = document.getElementById("select-all-btn");
      if (selectAllBtn) {
        selectAllBtn.style.display = "inline-block";
      }
    }
    
  } catch (err) {
    console.error(err);
    showError("Unexpected error while adding document.");
  }
}

async function extractDocumentText() {
  if (selectedDocuments.length === 0) {
    showError("Please select documents to extract text from.");
    return;
  }
  
  showError("");
  setExtractLoading(true);
  
  const statusEl = document.getElementById("extraction-status");
  const statusTextEl = document.getElementById("extraction-status-text");
  
  if (statusEl && statusTextEl) {
    statusEl.style.display = "block";
    statusTextEl.innerHTML = '<span class="loading-spinner"></span>Downloading and extracting text from PDFs...';
  }
  
  try {
    const resp = await fetch("/api/documents/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ documents: selectedDocuments }),
    });
    
    const data = await resp.json();
    
    if (!resp.ok) {
      showError(data.error || "Failed to extract documents.");
      if (statusEl) statusEl.style.display = "none";
      return;
    }
    
    extractedDocuments = data.documents || [];
    combinedExtractedText = data.combined_text || "";
    
    const summary = data.extraction_summary || {};
    const riskAnalysis = data.risk_analysis || {};
    
    // Update status
    if (statusTextEl) {
      statusTextEl.textContent = `Extracted text from ${summary.successful || 0} of ${summary.total || 0} documents (${(summary.total_text_length || 0).toLocaleString()} characters)`;
    }
    
    // Show extracted content section
    showExtractedContent(data);
    
    // Update risk indicators based on document analysis
    if (riskAnalysis.risk_flags) {
      updateRiskIndicators({
        ...lastSiteData?.risk_flags,
        ...riskAnalysis.risk_flags,
        status_label: riskAnalysis.inferred_status || lastSiteData?.risk_flags?.status_label
      });
    }
    
  } catch (err) {
    console.error(err);
    showError("Unexpected error while extracting documents.");
    if (statusEl) statusEl.style.display = "none";
  } finally {
    setExtractLoading(false);
  }
}

function showExtractedContent(data) {
  const section = document.getElementById("extracted-content-section");
  const badgesEl = document.getElementById("doc-risk-badges");
  const summaryEl = document.getElementById("extracted-summary");
  const textEl = document.getElementById("extracted-text-content");
  
  if (!section) return;
  
  section.classList.remove("hidden");
  
  const riskFlags = data.risk_analysis?.risk_flags || {};
  const summary = data.extraction_summary || {};
  
  // Build risk badges
  if (badgesEl) {
    let badgesHtml = "";
    
    const riskItems = [
      { key: "pfas", label: "PFAS" },
      { key: "petroleum", label: "Petroleum" },
      { key: "heavy_metals", label: "Heavy Metals" },
      { key: "chlorinated_solvents", label: "Chlorinated Solvents" },
      { key: "offsite_impact", label: "Off-site Impact" },
      { key: "groundwater_impact", label: "Groundwater" },
      { key: "soil_contamination", label: "Soil" },
    ];
    
    for (const item of riskItems) {
      const isActive = riskFlags[item.key];
      const badgeClass = isActive ? "highlight" : "good";
      badgesHtml += `<span class="badge ${badgeClass}">${item.label}: ${isActive ? "FOUND" : "Not Found"}</span>`;
    }
    
    badgesEl.innerHTML = badgesHtml;
  }
  
  // Build summary
  if (summaryEl) {
    const concentrations = data.risk_analysis?.concentrations_found || 0;
    summaryEl.innerHTML = `
      <strong>Extraction Results:</strong><br>
      Documents processed: ${summary.total || 0}<br>
      Successfully extracted: ${summary.successful || 0}<br>
      Total text extracted: ${(summary.total_text_length || 0).toLocaleString()} characters<br>
      ${concentrations > 0 ? `Concentration values found: ${concentrations}` : ""}
    `;
  }
  
  // Show extracted text
  if (textEl && data.combined_text) {
    textEl.textContent = data.combined_text;
  } else if (textEl) {
    textEl.textContent = "No text could be extracted from the selected documents.";
  }
}

async function analyzeSite() {
  const input = document.getElementById("site-input");
  if (!input) return;

  const brrts = input.value.trim();
  if (!brrts) {
    showError("Please enter a BRRTS activity ID.");
    return;
  }

  showError("");
  setAnalyzeLoading(true);
  
  allDocuments = [];
  selectedDocuments = [];
  chatHistory = [];
  sessionId = crypto.randomUUID();
  
  const docListEl = document.getElementById("doc-list");
  if (docListEl) {
    docListEl.innerHTML = '<div class="empty-docs">Click "Fetch Documents" to load available documents.</div>';
  }
  const docCountEl = document.getElementById("doc-count");
  if (docCountEl) docCountEl.textContent = "";
  const selCountEl = document.getElementById("selected-count");
  if (selCountEl) selCountEl.textContent = "";
  
  const chatMsgsEl = document.getElementById("chat-messages");
  if (chatMsgsEl) {
    chatMsgsEl.innerHTML = '<div class="empty-chat">Select documents and ask a question about the environmental data for this site.</div>';
  }

  try {
    const resp = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ brrts }),
    });

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      const msg = errData.error || `Analysis failed (HTTP ${resp.status}).`;
      showError(msg);
      return;
    }

    const data = await resp.json();
    lastSiteData = data || {};
    currentDsn = (data.site_info || {}).dsn || brrts;

    const info = data.site_info || {};
    const flags = data.risk_flags || {};
    const summary = data.summary || "No summary available.";

    fillSiteInfo(info);
    updateRiskIndicators(flags);

    const summaryEl = document.getElementById("summary-content");
    if (summaryEl) {
      summaryEl.textContent = summary;
    }
  } catch (err) {
    console.error(err);
    showError("Unexpected error while analyzing site.");
  } finally {
    setAnalyzeLoading(false);
  }
}

async function autoAnalyzeDocuments() {
  if (!currentDsn) {
    showError("Please analyze a site first.");
    return;
  }
  
  showError("");
  setAutoAnalyzeLoading(true, "Step 1/3: Fetching documents from DNR...");
  
  // Reset state
  extractedDocuments = [];
  combinedExtractedText = "";
  const extractedSection = document.getElementById("extracted-content-section");
  if (extractedSection) extractedSection.classList.add("hidden");
  const aiSection = document.getElementById("ai-summary-section");
  if (aiSection) aiSection.classList.add("hidden");
  
  try {
    // Step 1: Fetch documents
    const docsResp = await fetch("/api/documents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dsn: currentDsn }),
    });
    
    const docsData = await docsResp.json();
    
    if (!docsResp.ok || !docsData.documents || docsData.documents.length === 0) {
      setAutoAnalyzeLoading(false, "No documents found for this site.");
      showError(docsData.error || "No documents found for this site.");
      return;
    }
    
    allDocuments = docsData.documents || [];
    selectedDocuments = [...allDocuments]; // Select all
    renderDocuments();
    
    // Show select all button
    const selectAllBtn = document.getElementById("select-all-btn");
    if (selectAllBtn) selectAllBtn.style.display = "inline-block";
    
    setAutoAnalyzeLoading(true, `Step 2/3: Downloading and extracting text from ${allDocuments.length} document(s)...`);
    
    // Step 2: Extract text from all documents
    const extractResp = await fetch("/api/documents/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ documents: selectedDocuments }),
    });
    
    const extractData = await extractResp.json();
    
    if (!extractResp.ok) {
      setAutoAnalyzeLoading(false, "");
      showError(extractData.error || "Failed to extract document text.");
      return;
    }
    
    extractedDocuments = extractData.documents || [];
    combinedExtractedText = extractData.combined_text || "";
    
    const extractSummary = extractData.extraction_summary || {};
    
    // Show extraction results
    showExtractedContent(extractData);
    
    if (!combinedExtractedText) {
      setAutoAnalyzeLoading(false, `Extracted ${extractSummary.successful || 0} documents, but no text could be extracted.`);
      return;
    }
    
    setAutoAnalyzeLoading(true, `Step 3/3: Generating AI summary of ${(extractSummary.total_text_length || 0).toLocaleString()} characters...`);
    
    // Step 3: Generate AI summary
    const aiResp = await fetch("/api/documents/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        combined_text: combinedExtractedText,
        site_data: lastSiteData,
        documents: extractedDocuments
      }),
    });
    
    const aiData = await aiResp.json();
    
    if (!aiResp.ok) {
      setAutoAnalyzeLoading(false, `Extracted ${extractSummary.successful || 0} documents. AI summary unavailable.`);
      // Still show extraction results even if AI fails
      return;
    }
    
    // Show AI summary
    const aiSummarySection = document.getElementById("ai-summary-section");
    const aiSummaryContent = document.getElementById("ai-summary-content");
    
    if (aiSummarySection && aiSummaryContent) {
      aiSummarySection.classList.remove("hidden");
      aiSummaryContent.textContent = aiData.summary || "No summary generated.";
    }
    
    setAutoAnalyzeLoading(false, `Complete! Analyzed ${extractSummary.successful || 0} documents (${(extractSummary.total_text_length || 0).toLocaleString()} characters).`);
    
  } catch (err) {
    console.error(err);
    setAutoAnalyzeLoading(false, "");
    showError("Unexpected error during auto-analysis.");
  }
}

async function fetchDocuments() {
  if (!currentDsn) {
    showError("Please analyze a site first.");
    return;
  }
  
  showError("");
  setDocsLoading(true);
  
  // Reset extraction state
  extractedDocuments = [];
  combinedExtractedText = "";
  const extractedSection = document.getElementById("extracted-content-section");
  if (extractedSection) extractedSection.classList.add("hidden");
  const statusEl = document.getElementById("extraction-status");
  if (statusEl) statusEl.style.display = "none";
  
  try {
    const resp = await fetch("/api/documents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dsn: currentDsn }),
    });
    
    const data = await resp.json();
    
    if (!resp.ok) {
      showError(data.error || "Failed to fetch documents.");
      return;
    }
    
    allDocuments = data.documents || [];
    selectedDocuments = [];
    renderDocuments();
    
    // Show select all button if documents found
    const selectAllBtn = document.getElementById("select-all-btn");
    if (selectAllBtn) {
      selectAllBtn.style.display = allDocuments.length > 0 ? "inline-block" : "none";
    }
    
  } catch (err) {
    console.error(err);
    showError("Unexpected error while fetching documents.");
  } finally {
    setDocsLoading(false);
  }
}

function appendChatMessage(text, who) {
  const container = document.getElementById("chat-messages");
  if (!container) return;

  const empty = container.querySelector(".empty-chat");
  if (empty) empty.remove();

  const div = document.createElement("div");
  div.className = `chat-msg ${who}`;
  div.innerHTML = who === "ai" ? formatMarkdown(text) : escapeHtml(text);
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function formatMarkdown(text) {
  let escaped = escapeHtml(text);
  escaped = escaped.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  escaped = escaped.replace(/\n/g, "<br>");
  return escaped;
}

async function sendMessage() {
  const input = document.getElementById("chat-input");
  if (!input) return;

  const question = input.value.trim();
  if (!question) return;

  appendChatMessage(question, "user");
  input.value = "";

  const btn = document.getElementById("chat-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Thinking...";
  }

  try {
    // Include extracted documents if available
    const docsToSend = extractedDocuments.length > 0 
      ? extractedDocuments.filter(d => selectedDocuments.some(s => s.id === d.id))
      : selectedDocuments;
    
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        site_data: lastSiteData || {},
        selected_documents: docsToSend,
        history: chatHistory,
        session_id: sessionId,
      }),
    });

    const data = await resp.json();
    
    if (data.session_id) {
      sessionId = data.session_id;
    }
    
    if (data.history) {
      chatHistory = data.history;
    }
    
    let answer = data.answer || "No answer returned.";
    if (data.documents_processed > 0) {
      answer = `[Analyzed ${data.documents_processed} document(s)]\n\n${answer}`;
    }
    appendChatMessage(answer, "ai");
    
  } catch (err) {
    console.error(err);
    appendChatMessage("Unexpected error while calling chat endpoint.", "ai");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Ask AI";
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("site-form");
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      analyzeSite();
    });
  }

  const fetchDocsBtn = document.getElementById("fetch-docs-btn");
  if (fetchDocsBtn) {
    fetchDocsBtn.addEventListener("click", () => {
      fetchDocuments();
    });
  }
  
  const autoAnalyzeBtn = document.getElementById("auto-analyze-btn");
  if (autoAnalyzeBtn) {
    autoAnalyzeBtn.addEventListener("click", () => {
      autoAnalyzeDocuments();
    });
  }
  
  const extractBtn = document.getElementById("extract-text-btn");
  if (extractBtn) {
    extractBtn.addEventListener("click", () => {
      extractDocumentText();
    });
  }
  
  const selectAllBtn = document.getElementById("select-all-btn");
  if (selectAllBtn) {
    selectAllBtn.addEventListener("click", () => {
      selectAllDocs();
    });
  }
  
  const addDocBtn = document.getElementById("add-doc-btn");
  if (addDocBtn) {
    addDocBtn.addEventListener("click", () => {
      addManualDocument();
    });
  }

  const chatBtn = document.getElementById("chat-btn");
  if (chatBtn) {
    chatBtn.addEventListener("click", () => {
      sendMessage();
    });
  }
  
  const chatInput = document.getElementById("chat-input");
  if (chatInput) {
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }
});
