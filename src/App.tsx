import { useEffect, useRef, useState } from "react";

type Page = { id: string; filename: string; preview_url: string; text?: string };
type Manifest = { selected_text?: string; selected_text_url?: string | null; layout_report_url?: string | null; review_fallback_available?: boolean; review_warnings?: string[]; source_type?: "images" | "pdf" | "docx"; source_name?: string; title: string; pages: Page[]; manuscript_text: string; final_text: string; manuscript_url: string | null; final_text_url: string | null; audio_url: string | null; book_status: string; book_error: string | null; progress: string; review_ready: boolean };
type ReferencePreparation = {id: string; status: string; progress: string; transcript: string; audio_url: string | null; error: string | null};
type Preview = { id: string | null; status: string; progress: string; audio_url: string | null; error: string | null; text?: string };
type Health = { ollama: { available: boolean; model_found?: boolean; model: string } };
type AdvancedField = { key: string; label: string; default: number; min: number; max: number; step: number };
type SpeechModel = { advanced?: AdvancedField[]; requires_reference?: boolean; requires_reference_text?: boolean; id: string; label: string; note: string; available: boolean; supports_reference?: boolean; voices: { id: string; label: string }[] };
const running = (m: Manifest | null) => !!m && ["assembling", "refining", "audio"].includes(m.book_status);
const editorText = (m: Manifest) => m.review_ready ? m.final_text : m.manuscript_text;
async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`);
  }
  return response.json();
}

export function App() {
  const [book, setBook] = useState<Manifest>({
    title: "Local Audible", pages: [], manuscript_text: "", final_text: "",
    manuscript_url: null, final_text_url: null, audio_url: null,
    book_status: "ready", book_error: null, progress: "", review_ready: false,
  });
  const [health, setHealth] = useState<Health | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewSelection, setPreviewSelection] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [previewText, setPreviewText] = useState("The morning light fell softly across the library. I opened a book and began to read. Every page offered a new idea, a quiet discovery, and a reason to keep listening. Outside, the world was waking up, but here there was time to pause, imagine, and enjoy the story. A good story invites us to see familiar things in a different way.");
  const previewPlayer = useRef<HTMLAudioElement>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(0);
  const [models, setModels] = useState<SpeechModel[]>([]);
  const [model, setModel] = useState("kokoro");
  const [narrator, setNarrator] = useState("af_heart");
  const [samples, setSamples] = useState<{id: string; label: string}[]>([]);
  const [sampleVoice, setSampleVoice] = useState("");
  const [referenceText, setReferenceText] = useState("");
  const [referencePrep, setReferencePrep] = useState<ReferencePreparation | null>(null);
  const [referenceBusy, setReferenceBusy] = useState(false);
  const [referenceRetry, setReferenceRetry] = useState(0);
  const [advanced, setAdvanced] = useState<Record<string, number>>({});
  const [cover, setCover] = useState<{id: string; url: string} | null>(null);
  const speechModel = models.find(m => m.id === model);
  const picker = useRef<HTMLInputElement>(null);
  const documentPicker = useRef<HTMLInputElement>(null);
  const referenceSeconds = model === "fish" ? 30 : 10;
  const isDocument = !!book.source_type && book.source_type !== "images";
  const selectionKey = JSON.stringify({model, narrator, sampleVoice, referenceText, advanced, previewText});
  const blocked = busy || referenceBusy || running(book) || preview?.status === "running";
  const invalidVoice = !speechModel?.available || (!!speechModel.requires_reference && !sampleVoice) || (!!sampleVoice && !!speechModel.requires_reference_text && !referenceText.trim()) || (speechModel?.advanced || []).some(f => {const v = advanced[f.key] ?? f.default; return !Number.isFinite(v) || v < f.min || v > f.max || (f.step === 1 && !Number.isInteger(v));});
  const dirty = draft !== (book ? editorText(book) : "");
  const accept = (next: Manifest) => { setBook(next); setDraft(editorText(next)); };

  useEffect(() => {
    api<Health>("/api/health").then(setHealth).catch(() => {});
    api<SpeechModel[]>("/api/voices").then(setModels).catch(e => setError(`Cannot load narrators: ${e.message}`));
    api<{id: string; label: string}[]>("/api/sample-voices").then(setSamples).catch(e => setError(`Cannot load sample voices: ${e.message}`));
  }, []);
  useEffect(() => {
    if (!running(book)) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<Manifest>("/api/book");
        if (stopped) return;
        setBook(next); setError("");
        if (!running(next)) { setDraft(editorText(next)); return; }
      } catch (e) { if (!stopped) setError(`Connection interrupted; retrying. ${String(e)}`); }
      if (!stopped) timer = setTimeout(poll, 1500);
    };
    timer = setTimeout(poll, 1000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [book?.book_status]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => {
    if (preview?.status !== "running") return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<Preview>("/api/voice-preview");
        if (stopped) return;
        if (next.id !== preview.id) {
          setPreview({...preview, status: "error", error: "Preview was interrupted or replaced. Generate it again."});
          return;
        }
        setPreview(next); setPreviewError("");
        if (next.status !== "running") return;
      } catch (e) { if (!stopped) setPreviewError(`Connection interrupted; retrying. ${String(e)}`); }
      if (!stopped) timer = setTimeout(poll, 1500);
    };
    timer = setTimeout(poll, 1000);
    return () => {stopped = true; clearTimeout(timer);};
  }, [preview?.status, preview?.id]);

  useEffect(() => {
    setReferencePrep(null);
    if (!sampleVoice || !speechModel?.requires_reference_text) {setReferenceBusy(false); return;}
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    setReferenceBusy(true); setReferenceText("");
    const fail = (error: unknown) => {
      if (!stopped) {setReferenceBusy(false); setReferencePrep({id: "", status: "error", progress: "", transcript: "", audio_url: null, error: String(error)});}
    };
    const receive = (next: ReferencePreparation) => {
      if (stopped) return;
      setReferencePrep(next);
      if (next.status === "complete") {setReferenceText(next.transcript); setReferenceBusy(false);}
      else if (next.status === "error") setReferenceBusy(false);
      else timer = setTimeout(() => {
        api<ReferencePreparation>("/api/sample-voices/prepare").then(result => {
          if (result.id !== next.id) throw new Error("Reference preparation was interrupted. Try again.");
          receive(result);
        }).catch(fail);
      }, 1000);
    };
    api<ReferencePreparation>("/api/sample-voices/prepare", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({sample_voice: sampleVoice, model})}).then(receive).catch(fail);
    return () => {stopped = true; clearTimeout(timer);};
  }, [sampleVoice, model, speechModel?.requires_reference_text, referenceRetry]);

  async function generatePreview() {
    setBusy(true); setPreviewError(""); setPreview(null);
    setPreviewSelection(selectionKey);
    try {
      setPreview(await api<Preview>("/api/voice-preview", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({model, narrator, advanced, preview_text: previewText, sample_voice: speechModel?.supports_reference ? sampleVoice || null : null,
          reference_text: sampleVoice && speechModel?.requires_reference_text ? referenceText : ""})}));
    } catch (e) {setPreviewError(String(e));}
    finally {setBusy(false);}
  }

  async function upload(list: FileList | null) {
    if (!list?.length) return;
    const files = Array.from(list).filter(f => /\.(jpe?g|png|webp|heic|heif)$/i.test(f.name));
    if (!files.length) { setError("This folder contains no supported page images."); return; }
    if (book?.pages.length && !window.confirm("Start a new book workspace? Existing files are preserved, but this replaces the active book. Save any unsaved edits first.")) return;
    setBusy(true); setError("");
    try {
      const form = new FormData();
      files.forEach(f => form.append("files", f, f.webkitRelativePath || f.name));
      accept(await api<Manifest>("/api/book/upload", { method: "POST", body: form }));
      setSelected(0);
      setCover(null);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); if (picker.current) picker.current.value = ""; }
  }
  async function uploadDocument(file?: File) {
    if (!file) return;
    if (!/\.(pdf|docx)$/i.test(file.name)) {setError("Choose a PDF or Word .docx file."); return;}
    if (file.size > 50 * 1024 * 1024) {setError("Document limit: 50 MB."); return;}
    if (book.pages.length && !window.confirm("Start a new book workspace? Existing files are preserved, but this replaces the active book. Save any unsaved edits first.")) return;
    setBusy(true); setError("");
    try {
      const form = new FormData(); form.append("file", file);
      accept(await api<Manifest>("/api/book/document", {method: "POST", body: form}));
      setSelected(0); setCover(null);
    } catch (e) {setError(String(e));}
    finally {setBusy(false); if (documentPicker.current) documentPicker.current.value = "";}
  }

  async function uploadCover(file?: File) {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { setError("Cover image must be 5 MB or smaller."); return; }
    setBusy(true); setError("");
    try {
      const form = new FormData(); form.append("file", file);
      setCover(await api<{id: string; url: string}>("/api/book/cover", {method: "POST", body: form}));
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  async function action(kind: "prepare" | "save" | "audio" | "review-with-warnings") {
    if (kind === "prepare" && book?.review_ready && !window.confirm("Rebuild the prepared text? Your current edited version will not be used. Saved text files are preserved.")) return;
    if (kind === "review-with-warnings" && !window.confirm("Optimization did not pass validation. Open a manual-review draft using original text for unverified passages? You must check and edit it before approving audio.")) return;
    if (kind === "audio" && !window.confirm(book.review_warnings?.length ? "This draft has review warnings. Confirm that you have reviewed the warnings, checked and corrected the draft, and approve the current editor text for audio generation." : "Approve the text currently in the editor and generate its audiobook?")) return;
    setBusy(true); setError("");
    try {
      accept(await api<Manifest>(`/api/book/${kind === "save" ? "text" : kind}`, {
        method: kind === "save" ? "PUT" : "POST",
        ...(kind !== "prepare" ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: draft, ...(kind === "audio" ? { acknowledge_review_warnings: true, model, narrator, advanced, reference_text: sampleVoice && speechModel?.requires_reference_text ? referenceText : "", cover_id: cover?.id || null, sample_voice: speechModel?.supports_reference ? sampleVoice || null : null } : {}) }) } : {}),
      }));
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  if (!book) return <main className="loading"><h1>Local Audible</h1><p>{error || "Opening your workspace…"}</p></main>;
  const page = book.pages[selected];
  return <main className="shell">
    <header className="topbar"><div><span className="eyebrow">LOCAL AUDIBLE / MANUSCRIPT STUDIO</span><h1>{book.title}<span>.</span></h1></div><div className="connection"><span className={`signal ${health?.ollama.model_found ? "good" : "warn"}`} />{health?.ollama.model_found ? "Ollama connected" : "Check Ollama connection"}</div></header>
    <section className="workflow">
      <div><span className="eyebrow">01 / SOURCE</span><h2>Choose your book source</h2><p>Select a folder of JPG, PNG, WebP, or HEIC images, or upload a PDF or Word (.docx) file. PDFs use page images to identify layout and keep the original embedded text. Word uses embedded text—no OCR. Scanned PDFs need the image workflow. Save older .doc files as .docx first.</p><input ref={picker} type="file" multiple {...{ webkitdirectory: "" }} onChange={e => void upload(e.target.files)} hidden /><button className="secondary" disabled={blocked} onClick={() => picker.current?.click()}>Choose image folder</button><input ref={documentPicker} aria-label="PDF or Word document" type="file" accept=".pdf,.docx" hidden onChange={e => void uploadDocument(e.target.files?.[0])} /><button className="secondary document-upload-button" disabled={blocked} onClick={() => documentPicker.current?.click()}>Choose PDF or Word</button>{isDocument && <p>{book.source_name} · text extracted · OCR skipped</p>}</div>
      <div><span className="eyebrow">02 / PREPARE</span><h2>{book.review_ready ? book.review_warnings?.length ? "Review required · warnings" : "✓ Text preparation complete" : isDocument ? "Optimize document text" : "Extract & optimize"}</h2><p>{book.source_type === "pdf" ? "Analyze page images to select main text and headings, then optimize the original words for narration. Tables, figures and sidebars are excluded by their visual layout. Review uncertain regions before approval." : isDocument ? "Optimize extracted text with Ollama: remove page furniture and review punctuation, paragraph breaks and narration flow. Then review and edit before approval." : "Transcribe the main narrative, remove page furniture, combine pages, and review punctuation and flow with Ollama."}</p><button className="primary" disabled={blocked || !book.pages.length} onClick={() => void action("prepare")}>{isDocument ? "Optimize text" : "Convert & optimize text"}</button>{book.review_fallback_available && <button className="secondary review-text-button" disabled={blocked} onClick={() => void action("review-with-warnings")}>Review text with warnings</button>}<button className="primary review-text-button" disabled={blocked || !book.review_ready} onClick={() => { const editor = document.querySelector<HTMLTextAreaElement>('[aria-label="Narration text"]'); editor?.scrollIntoView({behavior: "smooth", block: "center"}); editor?.focus({preventScroll: true}); }}>Review text now</button></div>
    <div className="cover-step"><span className="eyebrow">03 / COVER · OPTIONAL</span><h2>MP3 cover / logo <small>optional</small></h2><p>Upload an image to embed as the audiobook’s cover art. Leave it blank for an MP3 without artwork. JPG, PNG or WebP, up to 5 MB.</p><label className="voice-field">Upload cover image<input aria-label="Upload cover image" type="file" accept="image/jpeg,image/png,image/webp" disabled={blocked || !book.pages.length} onChange={e => { void uploadCover(e.target.files?.[0]); e.target.value = ""; }} /></label>{cover && <div><img src={cover.url} alt="Selected MP3 cover" /><button className="secondary" disabled={blocked} onClick={() => setCover(null)}>Remove cover</button></div>}</div>
      <div><span className="eyebrow">04 / APPROVE</span><h2>Narrator & approval</h2><p>Review the text, then choose a local engine and English narrator. No British presets. Cloned voices follow the accent of your English sample.</p><label className="voice-field">Speech model<select aria-label="Speech model" value={model} disabled={blocked || !models.length} onChange={e => { setModel(e.target.value); setSampleVoice(""); setReferenceText(""); setAdvanced({}); setNarrator(models.find(m => m.id === e.target.value)!.voices[0].id); }}>{models.map(m => <option key={m.id} value={m.id}>{m.label}{m.available ? "" : " · setup required"}</option>)}</select></label><label className="voice-field">Narrator<select aria-label="Narrator" value={narrator} disabled={blocked || !speechModel || (!!speechModel.supports_reference && !!sampleVoice)} onChange={e => setNarrator(e.target.value)}>{speechModel?.voices.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}</select></label>{speechModel?.supports_reference && <div className="sample-choice"><h2>Sample voice <small>{speechModel.requires_reference ? "required" : "optional"}</small></h2><label className="voice-field">Sample voice<select aria-label="Sample voice" value={sampleVoice} disabled={blocked} onChange={e => {setSampleVoice(e.target.value); setReferenceText("");}}><option value="">{speechModel.requires_reference ? "Choose a sample voice" : "Use default voice (no sample)"}</option>{samples.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select></label><p>Files from data/sample_voice. Use a clear English recording you have permission to use; its accent carries into the output. {speechModel.requires_reference_text ? `The first ${referenceSeconds} seconds are extracted and transcribed automatically on this Mac. Listen to the excerpt and check the text below. Your original recording is unchanged.` : "Up to the first 30 seconds are used. Leave the default selected to skip reference conditioning."}</p>{sampleVoice && speechModel.requires_reference_text && <label className="voice-field">Reference recording transcript (for voice cloning)<textarea aria-label="Reference recording transcript" value={referenceText} disabled={blocked} onChange={e => setReferenceText(e.target.value)} placeholder={`The automatic transcript will appear here. Review it against the ${referenceSeconds}-second excerpt.`} /><small>Automatically transcribed from the first {referenceSeconds} seconds. Correct any mistakes before generating audio; do not enter the book or preview text here.</small></label>}{sampleVoice && speechModel.requires_reference_text && <div aria-live="polite"><p>{referencePrep?.progress || (referenceBusy ? `Preparing ${referenceSeconds}-second reference…` : "")}</p>{referencePrep?.error && <p role="alert">{referencePrep.error}</p>}<button className="secondary" disabled={blocked} onClick={() => setReferenceRetry(v => v + 1)}>Prepare reference again</button></div>}{sampleVoice && (!speechModel.requires_reference_text || referencePrep?.audio_url) && <audio aria-label="Selected reference recording" controls src={speechModel.requires_reference_text ? referencePrep!.audio_url! : `/api/sample-voices/audio?name=${encodeURIComponent(sampleVoice)}`} />}<button className="secondary" disabled={blocked} onClick={() => api<{id: string; label: string}[]>("/api/sample-voices").then(next => {setSamples(next); if (!next.some(s => s.id === sampleVoice)) setSampleVoice("");}).catch(e => setError(String(e)))}>Refresh sample list</button></div>}<details className="advanced-settings"><summary>Advanced settings</summary><p>Controls are specific to this model. Sampling variation is not an emotion control.</p>{speechModel?.advanced?.length ? speechModel.advanced.map(field => <label className="voice-field" key={field.key}>{field.label}<input type="number" aria-label={field.label} min={field.min} max={field.max} step={field.step} value={advanced[field.key] ?? field.default} disabled={blocked} onChange={e => setAdvanced({...advanced, [field.key]: e.target.valueAsNumber})} /><small>Default: {field.default} · Range: {field.min}–{field.max}</small></label>) : <p>No adjustable native controls are exposed by this adapter.</p>}<button className="secondary" disabled={blocked} onClick={() => setAdvanced({})}>Reset model defaults</button></details><div className="voice-preview"><h3>Try this voice · optional</h3><p>You can approve and generate your audiobook without creating a preview. This text is used only for previews and stays the same when switching models.</p><label className="voice-field">Preview text · optional<textarea aria-label="Preview text" value={previewText} maxLength={2000} disabled={blocked} onChange={e => setPreviewText(e.target.value)} /><small>Leave blank to use the default comparison passage. This never changes your book text.</small></label><div className="preview-actions"><button className="secondary" disabled={blocked || invalidVoice} onClick={() => void generatePreview()}>Generate 10-second preview</button><button className="secondary" disabled={blocked || previewSelection !== selectionKey || !preview?.audio_url} onClick={() => { const player = previewPlayer.current; if (player) {player.currentTime = 0; void player.play().catch(e => setPreviewError(`Cannot play preview: ${String(e)}`));} }}>Play</button></div>{previewSelection === selectionKey && <><p aria-live="polite">{preview?.progress}</p>{preview?.audio_url && <audio ref={previewPlayer} aria-label="Voice preview" controls src={preview.audio_url} />} {preview?.text && <details><summary>Comparison text</summary><p>{preview.text}</p></details>}{(previewError || preview?.error) && <p role="alert">{previewError || preview?.error}</p>}</>}{preview && previewSelection !== selectionKey && <p>Settings changed. Generate a new preview to hear this selection.</p>}</div><p className="voice-note">{speechModel?.note}{speechModel && !speechModel.available ? " Runtime setup required; see README.md." : ""}</p><button className="primary" disabled={blocked || !book.review_ready || !draft.trim() || !speechModel?.available || (!!speechModel.requires_reference && !sampleVoice) || (speechModel?.advanced || []).some(f => {const v = advanced[f.key] ?? f.default; return !Number.isFinite(v) || v < f.min || v > f.max || (f.step === 1 && !Number.isInteger(v));})} onClick={() => void action("audio")}>Approve text & generate audio</button></div>
    </section>
    {(book.pages.length > 0 || busy) && <section className="command-bar" aria-live="polite"><div className="metric"><strong>{book.pages.length}</strong><span>{book.source_type === "docx" ? "sections" : "pages"}</span></div><div className="metric"><strong>{draft.trim() ? draft.trim().split(/\s+/).length : 0}</strong><span>words</span></div><p className="progress">{busy ? "Saving or uploading…" : book.progress || "Check the page order, then convert and optimize the text."}</p><span className={`badge ${book.book_status}`}>{book.book_status.toUpperCase()}</span></section>}
    {(error || book.book_error) && <div className="workflow-error error-box" role="alert">{error || book.book_error}{book.book_status === "error" && <button className="secondary" disabled={busy} onClick={async () => {setBusy(true); try {accept(await api<Manifest>("/api/book")); setError("");} catch (e) {setError(String(e));} finally {setBusy(false);} }}>Check preparation status</button>}</div>}
    {!!book.review_warnings?.length && book.review_ready && <section className="review-warnings" role="status"><h2>Review warnings — check before approval</h2><ul>{book.review_warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul><p>Compare against the original text below. Edit the draft before explicitly approving audio generation.</p></section>}
    {book.layout_report_url && <details className="raw-text"><summary>PDF layout selection · inspect included text</summary><p>The model selected regions; their words come from the PDF. Check the original page images for mistaken exclusions.</p><a href={book.layout_report_url} download>Download region classification report</a>{book.selected_text_url && <p><a href={book.selected_text_url} download>Download selected text before optimization</a></p>}<pre>{book.selected_text || "Layout analysis is not complete yet."}</pre></details>}
    {book.pages.length > 0 && <div className="workspace"><aside className="image-column"><div className="column-heading"><span>{isDocument ? "Extracted source text · document order" : "Original pages · filename order"}</span></div><div className="page-stack">{book.pages.map((p, i) => <button key={p.id} className={`page-card ${i === selected ? "selected" : ""}`} onClick={() => setSelected(i)}>{p.preview_url ? <img src={p.preview_url} alt={`Page ${i + 1}`} loading="lazy" /> : <span className="document-excerpt">{p.text?.slice(0, 180) || "Blank page"}</span>}<span>{i + 1}. {p.filename}</span></button>)}</div>{page && isDocument && <pre className="document-source">{page.text || "No text on this page."}</pre>}{page?.preview_url && <a href={page.preview_url} target="_blank" rel="noreferrer" className="source-preview"><img src={page.preview_url} alt={`Full page: ${page.filename}`} /><span>Open full-size page ↗</span></a>}</aside>
      <section className="manuscript-column"><div className="manuscript-heading"><div><span className="eyebrow">YOUR NARRATION TEXT</span><h2>{book.review_ready ? "Review and make it yours" : "Prepared text will appear here"}</h2></div><span>{dirty ? "Unsaved edits" : "Saved"}</span></div><textarea aria-label="Narration text" className="manuscript" value={draft} disabled={blocked || !book.review_ready} onChange={e => setDraft(e.target.value)} placeholder="Upload images or a document, then optimize its text. Review the result here before approving narration." /><div className="manuscript-footer"><span>{draft.length.toLocaleString()} characters</span><div className="footer-actions"><button className="secondary" disabled={blocked || !book.review_ready} onClick={() => void action("save")}>Save draft</button>{book.final_text_url && <a className="download" href={book.final_text_url} download>Download saved text</a>}</div></div>{book.manuscript_text && <details className="raw-text"><summary>{isDocument ? "Compare extracted document text" : "Compare raw transcription"}</summary>{book.manuscript_url && <a className="download" href={book.manuscript_url} download>Download raw text</a>}<pre>{book.manuscript_text}</pre></details>}</section>
    </div>}
    {book.audio_url && <footer className="player-bar"><div className="player-title"><span className="eyebrow">BOOK AUDIO</span><strong>Approved manuscript audio</strong></div><audio key={book.audio_url} controls src={book.audio_url} /><a className="download" href={book.audio_url} download>Download MP3</a></footer>}
  </main>;
}
