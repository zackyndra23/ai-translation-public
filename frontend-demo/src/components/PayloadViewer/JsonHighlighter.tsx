import { cn } from '@/lib/cn'

interface Props {
  value: unknown
  className?: string
}

// Custom syntax highlighter — no external dep. Renders JSON with token-typed
// spans (string=rose, number=amber, bool=emerald, null=gray, key=white).
// Palette aligned with Integrity Indonesia brand — see tailwind.config.ts.
export function JsonHighlighter({ value, className }: Props) {
  const json = JSON.stringify(value, null, 2)
  const lines = json.split('\n')

  return (
    <pre className={cn('overflow-x-auto p-4 font-mono text-xs leading-relaxed', className)}>
      {lines.map((line, i) => (
        <div key={i} className="flex">
          <span className="mr-4 w-8 shrink-0 select-none text-right text-fg-placeholder">
            {i + 1}
          </span>
          <span dangerouslySetInnerHTML={{ __html: highlight(line) }} />
        </div>
      ))}
    </pre>
  )
}

function highlight(line: string): string {
  // Escape HTML first to prevent XSS in rendered JSON values
  const escaped = line
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Order matters: keys first, then strings, numbers, bools, null.
  // Keys match the "key": pattern; string values match the : "value" pattern.
  // Processing keys before string values avoids double-wrapping the key token.
  return escaped
    .replace(
      /"([^"\\]*(\\.[^"\\]*)*)"\s*:/g,
      '<span style="color:#ffffff">"$1"</span>:',
    )
    .replace(
      /:\s*"([^"\\]*(\\.[^"\\]*)*)"/g,
      ': <span style="color:#f43f5e">"$1"</span>',
    )
    .replace(
      /:\s*(-?\d+\.?\d*([eE][+-]?\d+)?)/g,
      ': <span style="color:#f59e0b">$1</span>',
    )
    .replace(/:\s*(true|false)/g, ': <span style="color:#10b981">$1</span>')
    .replace(/:\s*null/g, ': <span style="color:#71717a">null</span>')
}
