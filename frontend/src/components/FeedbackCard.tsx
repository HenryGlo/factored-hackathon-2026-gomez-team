// "¿Te ayudé?" al cerrar la conversación (POST /api/conversations/{id}/feedback): 👍/👎, categoría y comentario opcional.
// Una valoración por conversación: un 409 feedback_exists se muestra como "ya enviada".
import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { FeedbackCategory, Lang } from "../api/types";
import { T } from "../lib/i18n";

const CATEGORIES: FeedbackCategory[] = ["no_me_entendio", "respuesta_incorrecta", "lento", "otro"];
const MAX_COMMENT = 500;

export default function FeedbackCard({ conversationId, lang, onUnauthorized }: { conversationId: string; lang: Lang; onUnauthorized?: () => void }) {
  const t = T[lang];
  const c = t.chat;
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [category, setCategory] = useState<FeedbackCategory | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<"sent" | "already" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!rating || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.feedback(conversationId, { rating, category: rating === "down" ? category : null, comment: comment.trim() || null });
      setDone("sent");
    } catch (err) {
      if (err instanceof ApiError && err.code === "feedback_exists") setDone("already");
      else if (err instanceof ApiError && err.status === 401) onUnauthorized?.();
      else if (err instanceof ApiError && err.status === 429 && err.retryAfter) setError(t.rateLimited(err.retryAfter));
      else setError(err instanceof ApiError && err.status === 0 ? t.networkError : t.genericError);
    } finally {
      setBusy(false);
    }
  }

  if (done) return <p className="card feedback done" role="status">{done === "sent" ? c.feedbackThanks : c.feedbackAlready}</p>;

  return (
    <form className="card feedback" onSubmit={submit} aria-labelledby="feedback-title">
      <h2 id="feedback-title">{c.feedbackTitle}</h2>
      <div className="feedback-rating" role="group" aria-labelledby="feedback-title">
        <button type="button" className="chip" aria-pressed={rating === "up"} onClick={() => setRating("up")}><span aria-hidden="true">👍</span> {c.feedbackUp}</button>
        <button type="button" className="chip" aria-pressed={rating === "down"} onClick={() => setRating("down")}><span aria-hidden="true">👎</span> {c.feedbackDown}</button>
      </div>
      {rating === "down" && (
        <fieldset className="feedback-why">
          <legend>{c.feedbackWhy}</legend>
          {CATEGORIES.map((k) => (
            <button key={k} type="button" className="chip" aria-pressed={category === k} onClick={() => setCategory(category === k ? null : k)}>{c.feedbackCategories[k]}</button>
          ))}
        </fieldset>
      )}
      {rating && (
        <>
          <label>
            {c.feedbackComment}
            <textarea rows={2} maxLength={MAX_COMMENT} value={comment} onChange={(e) => setComment(e.target.value)} aria-describedby="feedback-chars" />
          </label>
          <span id="feedback-chars" className="muted small">{t.charsLeft(MAX_COMMENT - comment.length)}</span>
          {error && <p className="notice error" role="alert">{error}</p>}
          <div className="actions"><button className="btn primary" type="submit" disabled={busy}>{c.feedbackSend}</button></div>
        </>
      )}
    </form>
  );
}
