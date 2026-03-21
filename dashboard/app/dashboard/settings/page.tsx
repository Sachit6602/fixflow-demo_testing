"use client"

import { useState } from "react"
import { PageHeader } from "@/components/dashboard/page-header"
import { defaultSettings } from "@/lib/sample-data"
import { toast } from "sonner"
import { X, Plus, GripVertical } from "lucide-react"
import { cn } from "@/lib/utils"

// ─── Small shared components ───────────────────────────────────────────────

function Section({ title, description, children, onSave }: {
  title: string
  description?: string
  children: React.ReactNode
  onSave: () => void
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          {description && <p className="text-xs text-muted-foreground mt-0.5">{description}</p>}
        </div>
        <button
          onClick={onSave}
          className="shrink-0 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
        >
          Save
        </button>
      </div>
      {children}
    </div>
  )
}

function Field({ label, helper, children }: { label: string; helper?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium text-foreground">{label}</label>
      {children}
      {helper && <p className="text-[11px] text-muted-foreground">{helper}</p>}
    </div>
  )
}

function TextInput({ value, onChange, placeholder, type = "text" }: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="px-3 py-2 text-sm rounded-md border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
    />
  )
}

function NumberInput({ value, onChange, min, max, step = 1, prefix, suffix }: {
  value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; prefix?: string; suffix?: string
}) {
  return (
    <div className="flex items-center gap-1.5">
      {prefix && <span className="text-sm text-muted-foreground">{prefix}</span>}
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        min={min}
        max={max}
        step={step}
        className="px-3 py-2 text-sm rounded-md border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring w-24 tabular-nums"
      />
      {suffix && <span className="text-sm text-muted-foreground">{suffix}</span>}
    </div>
  )
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-ring",
        checked ? "bg-primary" : "bg-border"
      )}
    >
      <span
        className={cn(
          "pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-lg transform transition-transform",
          checked ? "translate-x-4" : "translate-x-0"
        )}
      />
    </button>
  )
}

function TagList({ tags, onChange }: { tags: string[]; onChange: (t: string[]) => void }) {
  const [input, setInput] = useState("")
  function add() {
    const trimmed = input.trim()
    if (trimmed && !tags.includes(trimmed)) {
      onChange([...tags, trimmed])
      setInput("")
    }
  }
  return (
    <div className="flex flex-wrap gap-2">
      {tags.map((tag) => (
        <span key={tag} className="flex items-center gap-1 text-xs bg-accent text-accent-foreground px-2.5 py-1 rounded-full font-medium">
          {tag}
          <button onClick={() => onChange(tags.filter((t) => t !== tag))} className="hover:text-destructive transition-colors">
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
      <div className="flex items-center gap-1">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="Add..."
          className="px-2.5 py-1 text-xs rounded-full border border-dashed border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring w-24"
        />
        <button onClick={add} className="text-muted-foreground hover:text-primary transition-colors">
          <Plus className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

function BulletList({ items, onChange }: { items: string[]; onChange: (items: string[]) => void }) {
  const [input, setInput] = useState("")
  function add() {
    const trimmed = input.trim()
    if (trimmed) { onChange([...items, trimmed]); setInput("") }
  }
  return (
    <div className="flex flex-col gap-2">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-2 group">
          <GripVertical className="w-3.5 h-3.5 text-muted-foreground/40 shrink-0" />
          <span className="flex-1 text-sm text-foreground">{item}</span>
          <button onClick={() => onChange(items.filter((_, idx) => idx !== i))} className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
      <div className="flex items-center gap-2 mt-1">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="Add new point..."
          className="flex-1 px-3 py-2 text-sm rounded-md border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <button onClick={add} className="px-3 py-2 text-xs font-semibold border border-border rounded-md hover:bg-secondary transition-colors text-foreground">
          Add
        </button>
      </div>
    </div>
  )
}

// ─── Main page ──────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const [biz, setBiz] = useState(defaultSettings.businessInfo)
  const [hours, setHours] = useState(defaultSettings.operatingHours)
  const [brands, setBrands] = useState(defaultSettings.supportedBrands)
  const [jobs, setJobs] = useState(defaultSettings.jobTypes)
  const [multipliers, setMultipliers] = useState(defaultSettings.urgencyMultipliers)
  const [ulez, setUlez] = useState(defaultSettings.ulez)
  const [authority, setAuthority] = useState(defaultSettings.authority)
  const [discount, setDiscount] = useState(defaultSettings.discountRules)
  const [valueProps, setValueProps] = useState(defaultSettings.valuePropositions)
  const [safety, setSafety] = useState(defaultSettings.safety)

  function saved(section: string) {
    toast.success(`${section} saved`)
  }

  function updateJob<K extends keyof typeof jobs[0]>(i: number, key: K, value: typeof jobs[0][K]) {
    setJobs(jobs.map((j, idx) => idx === i ? { ...j, [key]: value } : j))
  }

  return (
    <div className="p-6 max-w-[900px] mx-auto">
      <PageHeader title="Settings" description="Configure your FixFlow agent and business rules" />

      <div className="flex flex-col gap-4">

        {/* Section 1: Business Info */}
        <Section title="Business Information" onSave={() => saved("Business Information")}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Business Name">
              <TextInput value={biz.name} onChange={(v) => setBiz({ ...biz, name: v })} />
            </Field>
            <Field label="Phone Number">
              <TextInput value={biz.phone} onChange={(v) => setBiz({ ...biz, phone: v })} />
            </Field>
            <Field label="Email">
              <TextInput value={biz.email} onChange={(v) => setBiz({ ...biz, email: v })} />
            </Field>
            <Field label="Coverage Area" helper="The region the agent will accept jobs from">
              <TextInput value={biz.location} onChange={(v) => setBiz({ ...biz, location: v })} />
            </Field>
          </div>
        </Section>

        {/* Section 2: Operating Hours */}
        <Section title="Operating Hours" onSave={() => saved("Operating Hours")}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Weekday Start">
              <TextInput type="time" value={hours.weekdayStart} onChange={(v) => setHours({ ...hours, weekdayStart: v })} />
            </Field>
            <Field label="Weekday End">
              <TextInput type="time" value={hours.weekdayEnd} onChange={(v) => setHours({ ...hours, weekdayEnd: v })} />
            </Field>
            <Field label="Weekend Start">
              <TextInput type="time" value={hours.weekendStart} onChange={(v) => setHours({ ...hours, weekendStart: v })} />
            </Field>
            <Field label="Weekend End">
              <TextInput type="time" value={hours.weekendEnd} onChange={(v) => setHours({ ...hours, weekendEnd: v })} />
            </Field>
          </div>
        </Section>

        {/* Section 3: Supported Brands */}
        <Section title="Supported Brands" description="The boiler brands your engineers work on" onSave={() => saved("Supported Brands")}>
          <TagList tags={brands} onChange={setBrands} />
        </Section>

        {/* Section 4: Job Types & Pricing */}
        <Section title="Job Types & Pricing" description="Configure pricing ranges for each job type" onSave={() => saved("Job Types & Pricing")}>
          <div className="overflow-x-auto -mx-5 px-5">
            <table className="w-full text-xs min-w-[900px]">
              <thead>
                <tr className="border-b border-border">
                  {["Job Type", "Base £", "Floor £", "Med Min", "Med Max", "Low Min", "Low Max", "Parts?", "Parts £", "Escalate?"].map((h) => (
                    <th key={h} className="text-left text-xs text-muted-foreground font-medium py-2 pr-3 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {jobs.map((job, i) => (
                  <tr key={job.name} className="border-b border-border last:border-0">
                    <td className="py-2.5 pr-3 font-medium text-foreground whitespace-nowrap">{job.name}</td>
                    {(["basePrice", "floorPrice", "medMin", "medMax", "lowMin", "lowMax"] as const).map((key) => (
                      <td key={key} className="py-2.5 pr-3">
                        <input
                          type="number"
                          value={job[key]}
                          onChange={(e) => updateJob(i, key, Number(e.target.value))}
                          className="w-16 px-2 py-1 rounded border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring tabular-nums"
                        />
                      </td>
                    ))}
                    <td className="py-2.5 pr-3">
                      <Toggle checked={job.includesParts} onChange={(v) => updateJob(i, "includesParts", v)} />
                    </td>
                    <td className="py-2.5 pr-3">
                      <input
                        type="number"
                        value={job.partsEstimate}
                        onChange={(e) => updateJob(i, "partsEstimate", Number(e.target.value))}
                        disabled={!job.includesParts}
                        className="w-16 px-2 py-1 rounded border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring tabular-nums disabled:opacity-40"
                      />
                    </td>
                    <td className="py-2.5">
                      <Toggle checked={job.alwaysEscalate} onChange={(v) => updateJob(i, "alwaysEscalate", v)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        {/* Section 5: Urgency Multipliers */}
        <Section title="Urgency Multipliers" onSave={() => saved("Urgency Multipliers")}>
          <div className="flex flex-col gap-3">
            {multipliers.map((m, i) => (
              <div key={m.name} className="flex items-center gap-4 p-3 rounded-lg bg-secondary/50">
                <div className="flex-1">
                  <div className="text-sm font-medium text-foreground">{m.name}</div>
                  <div className="text-xs text-muted-foreground">{m.description}</div>
                </div>
                <div className="flex items-center gap-1.5">
                  <input
                    type="number"
                    value={m.multiplier}
                    onChange={(e) => setMultipliers(multipliers.map((x, idx) => idx === i ? { ...x, multiplier: Number(e.target.value) } : x))}
                    step={0.1}
                    min={1}
                    max={3}
                    className="w-16 px-2 py-1.5 text-sm rounded border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring tabular-nums text-center"
                  />
                  <span className="text-sm text-muted-foreground">×</span>
                </div>
              </div>
            ))}
          </div>
        </Section>

        {/* Section 6: ULEZ Surcharges */}
        <Section title="ULEZ Surcharges" description="Added to quotes for jobs within ULEZ zones" onSave={() => saved("ULEZ Surcharges")}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Inner London Surcharge" helper="Zone 1–2 and inner boroughs">
              <NumberInput value={ulez.inner} onChange={(v) => setUlez({ ...ulez, inner: v })} min={0} prefix="£" />
            </Field>
            <Field label="Outer London Surcharge" helper="Zone 3–6 and outer boroughs">
              <NumberInput value={ulez.outer} onChange={(v) => setUlez({ ...ulez, outer: v })} min={0} prefix="£" />
            </Field>
          </div>
        </Section>

        {/* Section 7: Authority Thresholds */}
        <Section title="Authority Thresholds" description="Controls when the agent auto-confirms, pauses for review, or hard-blocks" onSave={() => saved("Authority Thresholds")}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Auto-confirm below" helper="Agent confirms quotes under this amount without review">
              <NumberInput value={authority.autoConfirmBelow} onChange={(v) => setAuthority({ ...authority, autoConfirmBelow: v })} prefix="£" />
            </Field>
            <Field label="Hard block above" helper="Agent blocks and escalates quotes above this amount">
              <NumberInput value={authority.hardBlockAbove} onChange={(v) => setAuthority({ ...authority, hardBlockAbove: v })} prefix="£" />
            </Field>
            <Field label="Human review — from" helper="Lower bound of the manual review range">
              <NumberInput value={authority.humanReviewMin} onChange={(v) => setAuthority({ ...authority, humanReviewMin: v })} prefix="£" />
            </Field>
            <Field label="Human review — to">
              <NumberInput value={authority.humanReviewMax} onChange={(v) => setAuthority({ ...authority, humanReviewMax: v })} prefix="£" />
            </Field>
          </div>
        </Section>

        {/* Section 8: Discount Rules */}
        <Section title="Discount Rules" onSave={() => saved("Discount Rules")}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="New customer max discount">
              <NumberInput value={discount.newCustomerMax} onChange={(v) => setDiscount({ ...discount, newCustomerMax: v })} min={0} max={50} suffix="%" />
            </Field>
            <Field label="Returning customer max discount">
              <NumberInput value={discount.returningCustomerMax} onChange={(v) => setDiscount({ ...discount, returningCustomerMax: v })} min={0} max={50} suffix="%" />
            </Field>
            <Field label="Max negotiation rounds" helper="How many back-and-forth rounds before final offer">
              <NumberInput value={discount.maxNegotiationRounds} onChange={(v) => setDiscount({ ...discount, maxNegotiationRounds: v })} min={1} max={10} />
            </Field>
            <Field label="Competitor price matching" helper="Allow agent to match competitor prices">
              <div className="flex items-center gap-2 mt-1">
                <Toggle checked={discount.competitorMatching} onChange={(v) => setDiscount({ ...discount, competitorMatching: v })} />
                <span className="text-sm text-muted-foreground">{discount.competitorMatching ? "Enabled" : "Disabled"}</span>
              </div>
            </Field>
          </div>
        </Section>

        {/* Section 9: Value Propositions */}
        <Section title="Value Propositions" description="Talking points the agent uses during price negotiation" onSave={() => saved("Value Propositions")}>
          <BulletList items={valueProps} onChange={setValueProps} />
        </Section>

        {/* Section 10: Safety Configuration */}
        <Section title="Safety Configuration" description="Gas smell detection and emergency protocol settings" onSave={() => saved("Safety Configuration")}>
          <div className="flex flex-col gap-4">
            <Field label="Emergency Line Number" helper="Displayed to customers when a gas smell is detected">
              <TextInput value={safety.emergencyLine} onChange={(v) => setSafety({ ...safety, emergencyLine: v })} />
            </Field>
            <Field label="Hard Stop Message" helper="Sent immediately when a gas safety keyword is detected">
              <textarea
                value={safety.hardStopMessage}
                onChange={(e) => setSafety({ ...safety, hardStopMessage: e.target.value })}
                rows={4}
                className="px-3 py-2 text-sm rounded-md border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-y"
              />
            </Field>
            <Field label="Gas Safety Keywords" helper="Messages containing these phrases trigger the hard stop">
              <TagList tags={safety.gasKeywords} onChange={(v) => setSafety({ ...safety, gasKeywords: v })} />
            </Field>
          </div>
        </Section>

      </div>
    </div>
  )
}
