import * as Dialog from '@radix-ui/react-dialog'
import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2, X } from 'lucide-react'
import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from 'react'
import { cn } from '../lib/cn'

const button = cva(
  'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-control text-table font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-on-accent hover:bg-accent-ink',
        secondary: 'border border-border-strong bg-surface-1 text-ink hover:bg-surface-2',
        ghost: 'text-ink-muted hover:bg-surface-3 hover:text-ink',
        danger: 'bg-danger-bg text-danger-ink hover:brightness-95',
      },
      size: { sm: 'h-7 px-2.5', md: 'h-8 px-3', lg: 'h-9 px-4' },
    },
    defaultVariants: { variant: 'secondary', size: 'md' },
  },
)

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof button> & { busy?: boolean }

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, busy, children, disabled, ...props }, ref,
) {
  return (
    <button ref={ref} type="button" className={cn(button({ variant, size }), className)} disabled={disabled || busy} {...props}>
      {busy && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
      {children}
    </button>
  )
})

const pill = cva('inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-meta font-medium', {
  variants: {
    tone: {
      neutral: 'bg-surface-3 text-ink-muted',
      info: 'bg-info-bg text-info-ink',
      success: 'bg-success-bg text-success-ink',
      warning: 'bg-warning-bg text-warning-ink',
      danger: 'bg-danger-bg text-danger-ink',
      accent: 'bg-accent-bg text-accent-ink',
    },
    mono: { true: 'font-mono', false: '' },
  },
  defaultVariants: { tone: 'neutral', mono: false },
})

export function Pill({ className, tone, mono, ...props }: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof pill>) {
  return <span className={cn(pill({ tone, mono }), className)} {...props} />
}

export function QualityPill({ quality }: { quality: string | null }) {
  if (!quality) return <Pill>Quality: not evaluated</Pill>
  const tone = quality === 'Pass' ? 'success' : quality === 'Partial' ? 'warning' : 'danger'
  return <Pill tone={tone}>Quality: {quality}</Pill>
}

export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T
  onChange: (value: T) => void
  options: { value: T; label: ReactNode }[]
  label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-control bg-surface-2 p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            'h-7 rounded-[5px] px-2.5 text-table font-medium text-ink-muted',
            value === option.value && 'bg-surface-1 text-ink ring-1 ring-border-strong',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('rounded-card border border-border bg-surface-1', className)} {...props} />
}

export function PageHeader({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-title font-semibold tracking-tight">{title}</h1>
        {sub && <p className="mt-0.5 text-ink-muted">{sub}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-ink-muted">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}
    </div>
  )
}

export function ErrorNote({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div role="alert" className="rounded-card border border-warning-border bg-warning-bg p-3 text-warning-ink">
      {message}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-card border border-dashed border-border-strong p-8 text-center">
      <p className="text-emphasis font-medium">{title}</p>
      {children && <div className="mt-1 text-ink-muted">{children}</div>}
    </div>
  )
}

export function Drawer({ open, onOpenChange, title, sub, children, width = 720 }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  sub?: ReactNode
  children: ReactNode
  width?: number
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/25" />
        <Dialog.Content
          style={{ width }}
          className="fixed inset-y-0 right-0 z-50 flex max-w-[96vw] flex-col border-l border-border bg-surface-0 shadow-popover focus:outline-none"
        >
          <div className="flex items-start justify-between gap-4 border-b border-border bg-surface-1 px-5 py-3">
            <div>
              <Dialog.Title className="text-section font-semibold">{title}</Dialog.Title>
              <Dialog.Description className="text-ink-muted">{sub}</Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="sm" aria-label="Close"><X className="size-4" /></Button>
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function Modal({ open, onOpenChange, title, sub, children }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  sub?: ReactNode
  children: ReactNode
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/25" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-[560px] max-w-[94vw] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-panel border border-border bg-surface-1 p-5 shadow-popover focus:outline-none">
          <Dialog.Title className="text-section font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="mb-3 text-ink-muted">{sub}</Dialog.Description>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export const inputClass =
  'h-8 w-full rounded-control border border-border-strong bg-surface-1 px-2.5 text-body text-ink placeholder:text-ink-faint focus:outline-2 focus:outline-offset-1 focus:outline-accent'

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-table font-medium text-ink-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-meta text-ink-faint">{hint}</span>}
    </label>
  )
}

export function Meta({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('text-meta font-medium uppercase tracking-wide text-ink-faint', className)}>{children}</div>
}
