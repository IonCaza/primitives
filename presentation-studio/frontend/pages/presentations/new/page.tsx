"use client";

import { use, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Sparkles, Loader2, LayoutDashboard, ArrowLeft, Pipette, Check, Sun, Moon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { useCreatePresentation } from "@/hooks/use-presentations";
import Link from "next/link";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Color utility helpers                                              */
/* ------------------------------------------------------------------ */

function hexToHsl(hex: string): [number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l * 100];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
  else if (max === g) h = ((b - r) / d + 2) / 6;
  else h = ((r - g) / d + 4) / 6;
  return [Math.round(h * 360), Math.round(s * 100), Math.round(l * 100)];
}

function hslToHex(h: number, s: number, l: number): string {
  s /= 100; l /= 100;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * color).toString(16).padStart(2, "0");
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

function buildSwatchFromPrimary(primary: string): PaletteColors {
  const [h, s, l] = hexToHsl(primary);
  return {
    primary,
    secondary: hslToHex((h + 150) % 360, Math.min(s + 5, 100), l),
    tertiary: hslToHex((h + 210) % 360, Math.min(s + 10, 100), Math.max(l - 5, 25)),
    accent: hslToHex((h + 60) % 360, Math.min(s, 90), Math.min(l + 10, 70)),
    danger: "#ef4444",
  };
}

/* ------------------------------------------------------------------ */
/*  Palette types and presets                                          */
/* ------------------------------------------------------------------ */

interface PaletteColors {
  primary: string;
  secondary: string;
  tertiary: string;
  accent: string;
  danger: string;
}

type PaletteMode = "default" | "dark" | "custom";
type ThemeMode = "light" | "dark";

const DEFAULT_PALETTE: PaletteColors = {
  primary: "#f97316",
  secondary: "#10b981",
  tertiary: "#3b82f6",
  accent: "#8b5cf6",
  danger: "#ef4444",
};

const DARK_PALETTE: PaletteColors = {
  primary: "#8b5cf6",
  secondary: "#06b6d4",
  tertiary: "#10b981",
  accent: "#f59e0b",
  danger: "#ef4444",
};

const THEME_GUIDELINES: Record<ThemeMode, string> = {
  dark:
    "Background should be dark (bg-gray-950 / bg-gray-900). " +
    "Use text-white for headings, text-gray-400 for secondary text. " +
    "Cards use bg-gray-900 or bg-gray-800 with border-gray-700/800.",
  light:
    "Background should be light (bg-white / bg-gray-50). " +
    "Use text-gray-900 for headings, text-gray-500 for secondary text. " +
    "Cards use bg-white with border-gray-200 and shadow-sm. " +
    "Chart tooltip backgrounds should be bg-white with border-gray-200.",
};

function paletteToPromptSuffix(
  mode: PaletteMode,
  colors: PaletteColors,
  theme: ThemeMode,
): string {
  const label = mode === "default" ? "Default" : mode === "dark" ? "Dark" : "Custom";
  return (
    `\n\n[color-palette: "${label}" — ` +
    `primary=${colors.primary}, secondary=${colors.secondary}, ` +
    `tertiary=${colors.tertiary}, accent=${colors.accent}, danger=${colors.danger}. ` +
    `Use these exact hex colors for all charts, cards, and highlights. ` +
    `${THEME_GUIDELINES[theme]}]`
  );
}

/* ------------------------------------------------------------------ */
/*  Swatch circle                                                      */
/* ------------------------------------------------------------------ */

function Swatch({ color, size = 20 }: { color: string; size?: number }) {
  return (
    <span
      className="inline-block rounded-full border border-white/10 shrink-0"
      style={{ backgroundColor: color, width: size, height: size }}
    />
  );
}

/* ------------------------------------------------------------------ */
/*  Custom Color Picker Dialog                                         */
/* ------------------------------------------------------------------ */

function CustomColorDialog({
  open,
  onOpenChange,
  colors,
  theme,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  colors: PaletteColors;
  theme: ThemeMode;
  onConfirm: (colors: PaletteColors) => void;
}) {
  const [primary, setPrimary] = useState(colors.primary);
  const computed = buildSwatchFromPrimary(primary);
  const isLight = theme === "light";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Custom Color Palette</DialogTitle>
        </DialogHeader>
        <div className="space-y-5 py-2">
          <div className="space-y-2">
            <Label>Primary Color</Label>
            <div className="flex items-center gap-3">
              <input
                type="color"
                value={primary}
                onChange={(e) => setPrimary(e.target.value)}
                className="h-10 w-14 rounded cursor-pointer border border-border bg-transparent"
              />
              <Input
                value={primary}
                onChange={(e) => {
                  const v = e.target.value;
                  if (/^#[0-9a-fA-F]{6}$/.test(v)) setPrimary(v);
                }}
                className="font-mono w-28 text-sm"
                placeholder="#8b5cf6"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-muted-foreground text-xs">Computed palette</Label>
            <div className="flex items-center gap-3 bg-muted/50 rounded-lg p-3">
              {(["primary", "secondary", "tertiary", "accent", "danger"] as const).map((key) => (
                <div key={key} className="flex flex-col items-center gap-1.5">
                  <Swatch color={computed[key]} size={32} />
                  <span className="text-[10px] text-muted-foreground capitalize">{key}</span>
                  <span className="text-[10px] font-mono text-muted-foreground/60">{computed[key]}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg overflow-hidden border border-border">
            <div
              className={cn("h-16 flex items-center justify-center gap-2 px-4", isLight ? "bg-gray-50" : "bg-gray-950")}
            >
              {[computed.primary, computed.secondary, computed.tertiary, computed.accent].map((c, i) => (
                <div key={i} className="h-6 flex-1 rounded" style={{ backgroundColor: c }} />
              ))}
            </div>
            <div className={cn("px-4 py-2 flex items-center gap-2", isLight ? "bg-white" : "bg-gray-900")}>
              <span className={cn("text-xs", isLight ? "text-gray-500" : "text-gray-400")}>
                Preview on {theme} background
              </span>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => { onConfirm(computed); onOpenChange(false); }}>
            <Check className="mr-2 h-4 w-4" />
            Apply Palette
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/*  Palette Selector                                                   */
/* ------------------------------------------------------------------ */

function PaletteSelector({
  mode,
  onModeChange,
  theme,
  onThemeChange,
  customColors,
  onCustomColorsChange,
}: {
  mode: PaletteMode;
  onModeChange: (mode: PaletteMode) => void;
  theme: ThemeMode;
  onThemeChange: (theme: ThemeMode) => void;
  customColors: PaletteColors;
  onCustomColorsChange: (colors: PaletteColors) => void;
}) {
  const [dialogOpen, setDialogOpen] = useState(false);

  const options: { id: PaletteMode; label: string; sublabel: string; colors: PaletteColors }[] = [
    { id: "dark", label: "Dark", sublabel: "Violet, cyan & emerald on dark", colors: DARK_PALETTE },
    { id: "default", label: "Default", sublabel: "Warm & balanced palette", colors: DEFAULT_PALETTE },
    { id: "custom", label: "Custom", sublabel: "Pick your own", colors: customColors },
  ];

  return (
    <>
      <div className="space-y-3">
        <div className="space-y-2">
          <Label>Theme</Label>
          <div className="grid grid-cols-2 gap-2">
            {([
              { id: "light" as ThemeMode, icon: Sun, label: "Light", bg: "bg-gray-50", fg: "text-gray-900", border: "border-gray-200" },
              { id: "dark" as ThemeMode, icon: Moon, label: "Dark", bg: "bg-gray-950", fg: "text-white", border: "border-gray-700" },
            ]).map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => onThemeChange(t.id)}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg border p-2.5 transition-all",
                  theme === t.id
                    ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                    : "border-border hover:border-muted-foreground/30 hover:bg-muted/30",
                )}
              >
                <div className={cn("w-8 h-8 rounded-md flex items-center justify-center shrink-0", t.bg, t.border, "border")}>
                  <t.icon className={cn("h-4 w-4", t.fg)} />
                </div>
                <span className="text-sm font-medium">{t.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <Label>Color Palette</Label>
          <div className="grid grid-cols-3 gap-2">
            {options.map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => {
                  onModeChange(opt.id);
                  if (opt.id === "custom") setDialogOpen(true);
                }}
                className={cn(
                  "relative flex flex-col items-center gap-2 rounded-lg border p-3 transition-all text-center",
                  mode === opt.id
                    ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                    : "border-border hover:border-muted-foreground/30 hover:bg-muted/30",
                )}
              >
                <div className={cn(
                  "flex items-center gap-1 rounded-md px-2 py-1",
                  theme === "light" ? "bg-gray-100" : "bg-gray-800",
                )}>
                  {Object.values(opt.colors).map((c, i) => (
                    <Swatch key={i} color={c} size={16} />
                  ))}
                </div>
                <span className="text-xs font-medium">{opt.label}</span>
                <span className="text-[10px] text-muted-foreground leading-tight">{opt.sublabel}</span>
                {opt.id === "custom" && (
                  <Pipette className="absolute top-2 right-2 h-3 w-3 text-muted-foreground" />
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      <CustomColorDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        colors={customColors}
        theme={theme}
        onConfirm={(c) => {
          onCustomColorsChange(c);
          onModeChange("custom");
        }}
      />
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

const EXAMPLE_PROMPTS = [
  "Create a dashboard showing key project metrics with charts for trends over the last 30 days.",
  "Build an overview of recent activity with a timeline and breakdown by category.",
  "Show a summary dashboard with top items, progress bars, and metric cards.",
  "Create a comparison dashboard showing metrics side by side across time periods.",
];

export default function NewPresentationPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);
  const router = useRouter();
  const createMutation = useCreatePresentation(projectId);
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [themeMode, setThemeMode] = useState<ThemeMode>("dark");
  const [paletteMode, setPaletteMode] = useState<PaletteMode>("dark");
  const [customColors, setCustomColors] = useState<PaletteColors>(() =>
    buildSwatchFromPrimary("#8b5cf6"),
  );

  const activePalette = paletteMode === "default"
    ? DEFAULT_PALETTE
    : paletteMode === "dark"
      ? DARK_PALETTE
      : customColors;

  const handleCreate = useCallback(async () => {
    const finalTitle = title.trim() || prompt.slice(0, 80) || "Untitled Presentation";
    const fullPrompt = prompt + paletteToPromptSuffix(paletteMode, activePalette, themeMode);
    const pres = await createMutation.mutateAsync({
      title: finalTitle,
      prompt: fullPrompt,
    });
    router.push(`/projects/${projectId}/presentations/${pres.id}`);
  }, [title, prompt, paletteMode, activePalette, themeMode, createMutation, projectId, router]);

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <Link
        href={`/projects/${projectId}/presentations`}
        className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="mr-1.5 h-4 w-4" />
        Back to Presentations
      </Link>

      <div className="space-y-1">
        <h2 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <LayoutDashboard className="h-6 w-6" />
          New Presentation
        </h2>
        <p className="text-muted-foreground">
          Describe the dashboard you want and AI will generate it from your project data.
        </p>
      </div>

      <Card>
        <CardContent className="pt-6 space-y-5">
          <div className="space-y-2">
            <Label htmlFor="title">Title (optional)</Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Q1 Summary Dashboard"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prompt">What would you like to visualize?</Label>
            <Textarea
              id="prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the dashboard you'd like to create..."
              rows={5}
              className="resize-none"
            />
          </div>

          <PaletteSelector
            mode={paletteMode}
            onModeChange={setPaletteMode}
            theme={themeMode}
            onThemeChange={setThemeMode}
            customColors={customColors}
            onCustomColorsChange={setCustomColors}
          />

          <Button
            onClick={handleCreate}
            disabled={!prompt.trim() || createMutation.isPending}
            className="w-full"
          >
            {createMutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Creating...
              </>
            ) : (
              <>
                <Sparkles className="mr-2 h-4 w-4" />
                Create &amp; Open Studio
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-3">
        <p className="text-sm font-medium text-muted-foreground">Example prompts</p>
        <div className="grid gap-2">
          {EXAMPLE_PROMPTS.map((example, i) => (
            <button
              key={i}
              onClick={() => setPrompt(example)}
              className="text-left text-sm p-3 rounded-lg border border-border hover:border-primary/50 hover:bg-muted/50 transition-all text-muted-foreground hover:text-foreground"
            >
              &ldquo;{example}&rdquo;
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
