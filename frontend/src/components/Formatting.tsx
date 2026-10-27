import { useState } from "react";
import { Check, Copy } from "lucide-react";

export function ShortId({
  value,
  prefix = 10,
}: {
  value: string;
  prefix?: number;
}) {
  return (
    <span className="mono" title={value}>
      {value.length > prefix ? `${value.slice(0, prefix)}…` : value}
    </span>
  );
}

export function CopyButton({
  value,
  label = "Copy",
}: {
  value: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setCopyFailed(false);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
      setCopyFailed(true);
    }
  }

  return (
    <>
      <button
        type="button"
        className="icon-button"
        onClick={copy}
        aria-label={
          copied
            ? "Copied to clipboard"
            : copyFailed
              ? "Could not copy to clipboard"
              : label
        }
        title={copied ? "Copied" : copyFailed ? "Copy failed" : label}
      >
        {copied ? <Check size={15} /> : <Copy size={15} />}
      </button>
      <span className="sr-only" aria-live="polite">
        {copied
          ? "Copied to clipboard"
          : copyFailed
            ? "Could not copy to clipboard"
            : ""}
      </span>
    </>
  );
}
