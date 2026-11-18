import { useEffect, useRef, useState, type FormEvent } from "react";
import PipelineInspector from "./PipelineInspector";
import type {
  Catalogue,
  Health,
  Preferences,
  Product,
  Reply,
  Session,
  Turn,
} from "./types";

const emptyPreferences: Preferences = {
  occasion: null,
  style: null,
  budget_gbp: null,
};
const money = (pence: number) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(
    pence / 100,
  );

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  const body: unknown = await response.json();
  if (!response.ok) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? (body as { detail: unknown }).detail
        : null;
    throw new Error(
      typeof detail === "string"
        ? detail
        : "Please check your message or image and try again.",
    );
  }
  return body as T;
}

function Garment({ product }: { product: Product }) {
  const tone =
    product.tags.find((tag) =>
      ["sky", "cream", "sand", "ink", "denim", "olive", "cocoa"].includes(tag),
    ) ?? "sand";
  const paths = {
    top: "M51 32 31 43 12 74 36 89 46 73 46 140 114 140 114 73 124 89 148 74 129 43 109 32 96 42 64 42Z",
    bottom: "M42 28H118L126 145H91L80 76 69 145H34Z",
    layer:
      "M51 27 27 44 12 143H42L49 67 49 149H111L111 67 118 143H148L133 44 109 27 95 36 80 83 65 36Z",
    shoes: "M24 101 40 77 60 80 72 99 122 111 141 125 141 141H18L18 117Z",
    accessory: "M43 50H117V137H43ZM59 50V34H101V50",
  };
  return (
    <svg
      className={`garment tone-${tone}`}
      viewBox="0 0 160 180"
      role="img"
      aria-label={`Schematic ${product.category}; not a product photograph`}
    >
      <path d={paths[product.category]} />
    </svg>
  );
}

function ProductCard({
  product,
  sample,
}: {
  product: Product;
  sample: boolean;
}) {
  return (
    <article className="product-card">
      <div className="product-drawing">
        <Garment product={product} />
        <span>{product.category}</span>
      </div>
      <div className="product-details">
        <p className="eyebrow">{product.brand}</p>
        <h3>{product.name}</h3>
        <p className="product-price">
          {money(product.price_pence)}{" "}
          <span>{sample ? "illustrative price" : "recorded price"}</span>
        </p>
        <p className="product-origin">{product.retailer}</p>
        {product.url ? (
          <a href={product.url} target="_blank" rel="noreferrer">
            View source listing ↗
          </a>
        ) : (
          <p className="sample-link">Sample item · no purchase link</p>
        )}
        <p className="snapshot">
          Snapshot: {new Date(product.captured_at).toLocaleDateString("en-GB")}
        </p>
      </div>
    </article>
  );
}

export default function App() {
  const [messages, setMessages] = useState<Turn[]>([]);
  const [preferences, setPreferences] = useState<Preferences>(emptyPreferences);
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [reply, setReply] = useState<Reply | null>(null);
  const [input, setInput] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [imageName, setImageName] = useState("");
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const historyLimit = useRef(20);
  const bottom = useRef<HTMLDivElement | null>(null);
  const field = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    let active = true;
    void Promise.all([api<Session>("/api/session"), api<Health>("/api/health")])
      .then(([session, status]) => {
        if (!active) return;
        setMessages(session.history);
        setPreferences(session.preferences);
        setCatalogue(session.catalogue);
        setHealth(status);
        historyLimit.current = session.history_limit;
        setReady(true);
      })
      .catch(() => {
        if (active)
          setError(
            "The assistant could not connect. Check the server and reload.",
          );
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, busy]);

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!input.trim() || busy || !ready) return;
    const text = input.trim();
    const uploadedImage = image;
    const requestId = ++sequence.current;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setError("");
    setInput("");
    setImage(null);
    setImageName("");
    try {
      const result = await api<Reply>("/api/chat", {
        method: "POST",
        body: JSON.stringify({ message: text, image: uploadedImage }),
        signal: controller.signal,
      });
      if (requestId !== sequence.current) return;
      setReply(result);
      setCatalogue(result.catalogue);
      setPreferences(result.preferences);
      setMessages((old) =>
        [
          ...old,
          { role: "user" as const, content: text },
          { role: "assistant" as const, content: result.answer },
        ].slice(-historyLimit.current),
      );
    } catch (failure) {
      if (
        requestId !== sequence.current ||
        (failure instanceof DOMException && failure.name === "AbortError")
      )
        return;
      setError(
        failure instanceof Error
          ? failure.message
          : "The request could not complete.",
      );
      setInput(text);
    } finally {
      if (requestId === sequence.current) {
        setBusy(false);
        pending.current = null;
        field.current?.focus();
      }
    }
  }

  async function clear() {
    sequence.current += 1;
    pending.current?.abort();
    pending.current = null;
    setBusy(false);
    try {
      await api("/api/clear", { method: "POST", body: "{}" });
      setMessages([]);
      setPreferences(emptyPreferences);
      setReply(null);
      setInput("");
      setImage(null);
      setImageName("");
      setError("");
      field.current?.focus();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Conversation could not be reset.",
      );
    }
  }

  function upload(file: File | undefined) {
    if (!file) return;
    if (
      !["image/png", "image/jpeg", "image/webp"].includes(file.type) ||
      file.size > 4_000_000
    ) {
      setError("Choose a PNG, JPEG or WebP image under 4 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setImage(String(reader.result));
      setImageName(file.name);
      setError("");
    };
    reader.onerror = () => setError("That image could not be read.");
    reader.readAsDataURL(file);
  }

  const selected = reply?.products ?? [];
  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="wordmark" href="/">
          <span className="wordmark-icon" aria-hidden="true">
            ro<span>↗</span>
          </span>
          <span>
            Retail Odyssey <small>OPEN</small>
          </span>
        </a>
        <div className="header-right">
          <span
            className={`status-dot ${health?.status === "ready" ? "is-ready" : ""}`}
          />
          <span>
            {health?.engine !== "catalogue" && health?.engine !== undefined
              ? health.status === "ready"
                ? health.engine === "cloudflare"
                  ? "Cloud model connected"
                  : "Local model connected"
                : "Catalogue fallback available"
              : "Catalogue assistant"}
          </span>
          <a
            className="source-link"
            href="https://github.com/skkagolanu/retail-odyssey-open"
            target="_blank"
            rel="noreferrer"
          >
            Source ↗
          </a>
        </div>
      </header>
      <main>
        <section className="intro">
          <div>
            <p className="eyebrow">
              A little direction. A look that feels like you.
            </p>
            <h1>
              Find your next
              <br />
              <em>good combination.</em>
            </h1>
          </div>
          <p className="intro-note">
            Start with an occasion, a style, or a piece you already own. We’ll
            explore a few thoughtful combinations from the catalogue.
          </p>
        </section>
        <div className="workspace">
          <section className="conversation" aria-labelledby="chat-title">
            <div className="panel-heading">
              <div>
                <span className="section-number">01</span>
                <h2 id="chat-title">Your styling conversation</h2>
              </div>
              <button
                className="quiet-button"
                onClick={() => void clear()}
                disabled={!ready}
              >
                Clear conversation
              </button>
            </div>
            <div
              className="chat-log"
              tabIndex={0}
              role="log"
              aria-label="Conversation"
              aria-live="polite"
            >
              {messages.length === 0 && (
                <div className="empty-chat">
                  <span className="spark">✳</span>
                  <h3>What are you dressing for?</h3>
                  <p>
                    Tell me what you have in mind. Occasion, colour, budget—any
                    starting point works.
                  </p>
                  <div className="suggestions">
                    {[
                      "A classic business outfit under £100",
                      "A casual minimalist look under £70",
                      "Something sporty for a workout",
                    ].map((prompt) => (
                      <button
                        key={prompt}
                        onClick={() => {
                          setInput(prompt);
                          field.current?.focus();
                        }}
                      >
                        {prompt}
                        <span aria-hidden="true">↗</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((message, index) => (
                <article
                  key={`${index}-${message.role}`}
                  className={`message ${message.role}`}
                >
                  <p className="message-label">
                    {message.role === "user" ? "YOU" : "ODYSSEY"}
                  </p>
                  <p>{message.content}</p>
                </article>
              ))}
              {busy && (
                <p className="thinking" role="status">
                  Putting a few ideas together…
                </p>
              )}
              <div ref={bottom} />
            </div>
            {error && (
              <p className="error-message" role="alert">
                {error}
              </p>
            )}
            <form className="composer" onSubmit={(event) => void send(event)}>
              <label className="sr-only" htmlFor="chat-input">
                Your message
              </label>
              <textarea
                id="chat-input"
                ref={field}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                maxLength={2000}
                placeholder="An occasion, a budget, a fresh idea…"
                rows={2}
                disabled={!ready}
              />
              <div className="composer-actions">
                <label
                  className="upload-button"
                  title="Optional local vision model required"
                >
                  <input
                    className="sr-only"
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    disabled={busy || !ready}
                    onChange={(event) => {
                      upload(event.target.files?.[0]);
                      event.target.value = "";
                    }}
                  />
                  ＋ Wardrobe image
                </label>
                {imageName && (
                  <button
                    type="button"
                    className="attachment"
                    onClick={() => {
                      setImage(null);
                      setImageName("");
                    }}
                    aria-label="Remove uploaded image"
                  >
                    {imageName.slice(0, 22)} ×
                  </button>
                )}
                <button
                  className="send-button"
                  disabled={busy || !ready || !input.trim()}
                  type="submit"
                >
                  {busy ? "Working…" : "Find my look"}
                  <span aria-hidden="true">↗</span>
                </button>
              </div>
            </form>
            <p className="privacy-note">
              Your browser has its own conversation. History expires after
              inactivity; clearing also resets saved preferences. Uploaded
              images are not retained in history.
            </p>
          </section>
          <aside className="look-panel" aria-labelledby="look-title">
            <div className="panel-heading">
              <div>
                <span className="section-number">02</span>
                <h2 id="look-title">The edit</h2>
              </div>
              <span className="item-count">
                {selected.length
                  ? `${selected.length} pieces`
                  : "Your starting point"}
              </span>
            </div>
            <div className="catalogue-notice">
              <span className="notice-mark">i</span>
              <div>
                <strong>
                  {catalogue?.mode === "snapshot"
                    ? "Catalogue snapshot"
                    : "Illustrative sample catalogue"}
                </strong>
                <p>
                  {catalogue?.mode === "snapshot"
                    ? "Recorded listings and prices. Live stock and current checkout prices are not verified."
                    : "Fictional pieces and example prices. No real stock, retailer affiliation or purchase availability is implied."}
                </p>
              </div>
            </div>
            <div className="preference-chips" aria-label="Saved preferences">
              {preferences.occasion && <span>{preferences.occasion}</span>}
              {preferences.style && <span>{preferences.style}</span>}
              {preferences.budget_gbp !== null && (
                <span>
                  Outfit budget{" "}
                  {money(Math.round(preferences.budget_gbp * 100))}
                </span>
              )}
            </div>
            {selected.length > 0 ? (
              <>
                <div className="product-grid">
                  {selected.map((product) => (
                    <ProductCard
                      key={product.id}
                      product={product}
                      sample={catalogue?.mode === "sample"}
                    />
                  ))}
                </div>
                <div className="selection-total">
                  <span>Selected pieces</span>
                  <strong>
                    {money(
                      selected.reduce(
                        (total, product) => total + product.price_pence,
                        0,
                      ),
                    )}
                  </strong>
                </div>
                <p className="drawing-note">
                  Garment drawings are schematic moodboard illustrations, not
                  photographs of the listed items.
                </p>
              </>
            ) : (
              <div className="empty-edit">
                <div className="outline-look">
                  <span>✳</span>
                </div>
                <h3>
                  Make a little room
                  <br />
                  for something new.
                </h3>
                <p>
                  Your selected pieces will appear here, with their source
                  details and recorded prices.
                </p>
              </div>
            )}
            {reply?.image && (
              <figure className="generated-image">
                <img
                  src={reply.image}
                  alt="AI-generated outfit illustration, not a photograph of catalogue products"
                />
                <figcaption>
                  Generated outfit illustration · not an exact product rendering
                </figcaption>
              </figure>
            )}
            {reply?.warnings.map((warning) => (
              <p className="capability-notice" key={warning}>
                {warning}
              </p>
            ))}
            {reply && (
              <details className="response-details">
                <summary>Response details</summary>
                <p>
                  {reply.engine !== "catalogue"
                    ? reply.engine === "cloudflare"
                      ? "Cloud agent selection"
                      : "Local model selection"
                    : "Deterministic catalogue styling"}{" "}
                  · {Math.round(reply.timings.total_ms)} ms server processing
                </p>
                <p>
                  Server time includes routing, retrieval and requested provider
                  stages. Browser/network time is additional.
                </p>
                {reply.timings.stages.map((stage, index) => (
                  <p key={`${stage.name}-${index}`}>
                    {stage.name}: {stage.duration_ms.toFixed(1)} ms ·{" "}
                    {stage.status}
                  </p>
                ))}
              </details>
            )}
          </aside>
        </div>
        <PipelineInspector reply={reply} />
      </main>
      <footer>
        <span>Retail Odyssey Open</span>
        <p>
          A local-first fashion project. Independent of the retailers mentioned.
        </p>
        <a
          href="https://github.com/skkagolanu/Retail-Odyssey"
          target="_blank"
          rel="noreferrer"
        >
          Original team project ↗
        </a>
      </footer>
    </div>
  );
}
