import { useQuery } from '@tanstack/react-query'
import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import { AlertTriangle, Download } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AssumptionsBar } from '../components/assumptions-bar'
import { ProvenancePopover } from '../components/provenance'
import { Button, Empty, ErrorNote, Loading, PageHeader, Pill, QualityPill, Segmented } from '../components/ui'
import { api, fileUrl } from '../lib/api'
import { cn } from '../lib/cn'
import { compact, rupees } from '../lib/format'
import type { GridLine, GridVendor, QuoteCell } from '../lib/types'

type View = 'normalised' | 'raw'
type Filter = 'all' | 'needs_review' | 'not_quoted'

function cellClasses(cell: QuoteCell): string {
  if (cell.excluded || cell.state === 'not_quoted') return 'text-[var(--cell-missing-ink)] [background:var(--cell-missing-bg)]'
  if (cell.state === 'needs_review') return 'bg-[var(--cell-review-bg)] text-[var(--cell-review-ink)]'
  if (cell.is_lowest) return 'bg-[var(--cell-lowest-bg)] text-[var(--cell-lowest-ink)]'
  return 'bg-[var(--cell-confident-bg)] text-[var(--cell-confident-ink)]'
}

function CellBody({ cell, view }: { cell: QuoteCell; view: View }) {
  if (cell.excluded) return <span className="font-sans italic">excluded</span>
  if (cell.state === 'not_quoted') return <span className="font-sans italic">not quoted</span>
  const shown = cell.inr_per_base ?? cell.display_inr
  const main = view === 'raw' ? (cell.raw_display ?? '–') : shown !== null ? rupees(shown) : (cell.raw_display ?? 'in review')
  const note = cell.state === 'overridden' ? 'overridden' : cell.annotation
  return (
    <span className="flex flex-col items-end leading-tight">
      <span className={cn(cell.state === 'overridden' && 'underline decoration-[var(--cell-override-underline)] decoration-2 underline-offset-2')}>
        {main}
        {cell.state === 'needs_review' && view === 'normalised' && shown !== null ? '?' : ''}
      </span>
      {note && <span className="font-sans text-[10px] opacity-80">{note}</span>}
    </span>
  )
}

function VendorHeader({ vendor }: { vendor: GridVendor }) {
  return (
    <div className="flex flex-col items-end gap-1 py-1 text-right normal-case tracking-normal">
      <span className="font-medium normal-case text-ink">{vendor.name}</span>
      <span className="flex flex-wrap justify-end gap-1">
        {vendor.format_label && <Pill>{vendor.format_label}</Pill>}
        <Pill mono tone={vendor.lines_quoted === 30 ? 'neutral' : 'warning'}>Lines {vendor.lines_quoted}/30</Pill>
        <QualityPill quality={vendor.quality} />
      </span>
      {vendor.extraction_error && <Pill tone="danger" title={vendor.extraction_error}>extraction failed</Pill>}
    </div>
  )
}

const freightText = (vendor: GridVendor) =>
  vendor.freight.kind === 'included' ? 'included'
    : vendor.freight.kind === 'lump_sum' ? compact(vendor.freight.amount_inr)
    : vendor.freight.kind === 'extra_unpriced' ? 'extra, unpriced'
    : 'not stated'

const totalsNote = (vendor: GridVendor) =>
  [
    vendor.totals.needs_review ? `${vendor.totals.needs_review} in review` : '',
    vendor.totals.not_quoted ? `${vendor.totals.not_quoted} not quoted` : '',
    vendor.totals.excluded ? `${vendor.totals.excluded} excluded` : '',
  ].filter(Boolean).join(' · ')

const helper = createColumnHelper<GridLine>()

export function Compare() {
  const { rfxId = '' } = useParams()
  const [view, setView] = useState<View>('normalised')
  const [filter, setFilter] = useState<Filter>('all')
  const { data: grid, error, isPending } = useQuery({ queryKey: ['grid', rfxId], queryFn: () => api.grid(rfxId) })

  const rows = useMemo(() => {
    if (!grid) return []
    if (filter === 'all') return grid.lines
    return grid.lines.filter((line) =>
      Object.values(line.cells).some((cell) => (filter === 'not_quoted' ? cell.state === 'not_quoted' || cell.excluded : cell.state === 'needs_review')),
    )
  }, [grid, filter])

  const columns = useMemo(() => {
    if (!grid) return []
    return [
      helper.accessor('line_id', { header: '#', cell: (info) => <span className="font-mono text-ink-muted">{info.getValue()}</span>, size: 44 }),
      helper.accessor('description', {
        header: 'Line item',
        cell: (info) => <span className="block max-w-[330px] truncate" title={info.getValue()}>{info.getValue()}</span>,
        size: 330,
      }),
      helper.accessor('qty', { header: 'Qty', cell: (info) => <span className="font-mono">{info.getValue().toLocaleString('en-IN')}</span>, size: 76 }),
      helper.accessor('uom', { header: 'Unit', cell: (info) => <span className="whitespace-nowrap text-ink-muted">1,000 {info.getValue()}</span>, size: 84 }),
      ...grid.vendors.map((vendor) =>
        helper.display({
          id: vendor.vendor_id,
          header: () => <VendorHeader vendor={vendor} />,
          cell: ({ row }) => {
            const cell = row.original.cells[vendor.vendor_id]
            return (
              <ProvenancePopover rfxId={rfxId} vendorId={vendor.vendor_id} lineId={row.original.line_id}>
                <button
                  type="button"
                  aria-label={`${vendor.name} ${row.original.line_id}: ${cell.excluded ? 'excluded' : cell.state.replace('_', ' ')}. Open provenance`}
                  className={cn('flex min-h-[34px] w-full items-center justify-end px-3 py-1 text-right font-mono text-table hover:outline hover:outline-1 hover:-outline-offset-1 hover:outline-border-strong focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent', cellClasses(cell))}
                >
                  <CellBody cell={cell} view={view} />
                </button>
              </ProvenancePopover>
            )
          },
          size: 168,
        }),
      ),
    ]
  }, [grid, rfxId, view])

  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel() })

  if (isPending) return <Loading label="Building the comparison…" />
  if (error) return <ErrorNote error={error} />
  if (!grid.vendors.some((v) => v.has_reply))
    return (
      <Empty title="No replies have been read yet">
        Go to <Link className="text-accent-ink underline" to={`/rfx/${rfxId}/responses`}>Responses</Link> to receive and read the vendor replies.
      </Empty>
    )

  const vendorCount = grid.vendors.length
  return (
    <div>
      <AssumptionsBar rfxId={rfxId} assumptions={grid.assumptions} />
      <PageHeader title="Compare quotes" sub={`${vendorCount} vendors · ${grid.lines.length} lines · normalised to ${grid.assumptions.base_unit}`}>
        <Segmented label="Price view" value={view} onChange={setView} options={[{ value: 'normalised', label: 'Normalised' }, { value: 'raw', label: 'Raw as quoted' }]} />
        <Segmented
          label="Line filter"
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'all', label: 'All lines' },
            { value: 'needs_review', label: `Needs review ${grid.counts.needs_review}` },
            { value: 'not_quoted', label: `Not quoted ${grid.counts.not_quoted}` },
          ]}
        />
        <a href={fileUrl(`/rfx/${rfxId}/export.xlsx`)}><Button><Download className="size-3.5" /> Export XLSX</Button></a>
        <a href={fileUrl(`/rfx/${rfxId}/export.csv`)}><Button variant="ghost">CSV</Button></a>
      </PageHeader>

      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-meta text-ink-muted" aria-label="Legend">
        <Legend className="bg-[var(--cell-confident-bg)]" label="Confident" />
        <Legend className="bg-[var(--cell-lowest-bg)]" label="Lowest on line" />
        <Legend className="bg-[var(--cell-review-bg)]" label="Needs review (value shown with ?, not counted)" />
        <Legend className="[background:var(--cell-missing-bg)]" label="Not quoted" />
        <Legend className="bg-surface-1 underline decoration-[var(--cell-override-underline)] decoration-2" label="Overridden" text="₹" />
        <span className="ml-auto">Click any cell for its source, both readings and the arithmetic.</span>
      </div>

      <div className="overflow-x-auto rounded-card border border-border bg-surface-1">
        <table className="w-full border-collapse text-table">
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id} className="bg-surface-2">
                {group.headers.map((header, index) => (
                  <th
                    key={header.id}
                    scope="col"
                    style={{ width: header.getSize() }}
                    className={cn('border-b border-border px-3 py-2 align-bottom text-meta font-medium uppercase tracking-wide text-ink-muted', index < 2 ? 'text-left' : 'text-right')}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b border-border">
                {row.getVisibleCells().map((cell, index) => (
                  <td key={cell.id} className={cn(index < 4 ? 'px-3 py-1' : 'border-l border-border p-0', index >= 2 && index < 4 && 'text-right')}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={4 + vendorCount} className="p-6 text-center text-ink-muted">No lines match this filter.</td></tr>
            )}
          </tbody>
          <tfoot>
            <tr className="bg-surface-2">
              <td colSpan={4} className="px-3 py-2">
                <div className="font-medium">Extended total, {grid.lines.length} lines</div>
                <div className="text-meta text-ink-muted">cells in review, not quoted or excluded are left out</div>
              </td>
              {grid.vendors.map((vendor) => (
                <td key={vendor.vendor_id} className="border-l border-border px-3 py-2 text-right">
                  <div className="font-mono text-emphasis font-medium">{compact(vendor.totals.extended_inr)}</div>
                  <div className="text-meta text-ink-muted">{vendor.totals.lines_counted} lines counted{totalsNote(vendor) ? ` · ${totalsNote(vendor)}` : ''}</div>
                </td>
              ))}
            </tr>
            <tr>
              <td colSpan={4} className="px-3 py-2 text-ink-muted">Freight, as stated by vendor</td>
              {grid.vendors.map((vendor) => (
                <td key={vendor.vendor_id} title={vendor.freight.statement ?? undefined} className={cn('border-l border-border px-3 py-2 text-right font-mono', vendor.freight.kind === 'extra_unpriced' || vendor.freight.kind === 'not_stated' ? 'text-warning-ink' : '')}>
                  {freightText(vendor)}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>

      {grid.review_open > 0 && (
        <div role="status" className="mt-4 flex flex-wrap items-center gap-3 rounded-card border border-warning-border bg-warning-bg px-4 py-3 text-warning-ink">
          <AlertTriangle className="size-4 shrink-0" />
          <p className="min-w-0 flex-1">
            <span className="font-medium">{grid.review_open} {grid.review_open === 1 ? 'item needs' : 'items need'} a decision before this comparison can go to award.</span>{' '}
            {grid.review_blocking_cells} {grid.review_blocking_cells === 1 ? 'cell is' : 'cells are'} excluded from every total above and from the analyst until resolved.
          </p>
          <Link to={`/rfx/${rfxId}/review`}><Button variant="primary">Open review queue</Button></Link>
        </div>
      )}
    </div>
  )
}

function Legend({ className, label, text }: { className: string; label: string; text?: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn('inline-flex size-3.5 items-center justify-center rounded-[3px] border border-border-strong text-[9px]', className)}>{text}</span>
      {label}
    </span>
  )
}
