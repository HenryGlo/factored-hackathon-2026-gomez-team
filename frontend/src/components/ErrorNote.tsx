// Error visible con el código de referencia (X-Request-ID) para cruzar con los logs y las trazas.
export default function ErrorNote({ message, requestId, label, onRetry, retryLabel }: {
  message: string;
  requestId: string | null;
  label: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div className="notice error" role="alert">
      <span>{message}</span>
      {requestId && <span className="ref">{label}: <code>{requestId}</code></span>}
      {onRetry && <button className="btn small" onClick={onRetry}>{retryLabel}</button>}
    </div>
  );
}
