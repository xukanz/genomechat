import { Settings, Sparkles } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu"
import { useUIStore } from "../../store/uiStore"
import type { AgentBackend } from "../../types/conversation"

/**
 * Phase 2 — developer/pilot overrides for worker backends.
 * Hidden behind a settings icon so the composer stays clean for everyday use.
 * Whichever backend is overridden to SDK shows up as an amber dot on the
 * trigger so the state stays visible at a glance without opening the menu.
 *
 * Orchestrator section is gated behind VITE_EXPOSE_ORCHESTRATOR_PROTOTYPE.
 * The Phase 2 plan calls the SDK orchestrator a "branch-only prototype, NOT
 * merged in Phase 2" — and the prototype lacks plan/todos parity with the
 * LangChain path, so end users hitting it would see no live plan UI. Until
 * Phase 3 wires SDK TodoWrite back into AgentState.plan, only operators
 * running evaluations should see this toggle.
 */
const SHOW_ORCHESTRATOR_TOGGLE =
  import.meta.env.VITE_EXPOSE_ORCHESTRATOR_PROTOTYPE === "true"

export function BackendSettingsMenu() {
  const {
    coderBackendOverride,
    setCoderBackendOverride,
    orchestratorBackendOverride,
    setOrchestratorBackendOverride,
  } = useUIStore()

  const anyOverrideActive =
    coderBackendOverride === "sdk" ||
    (SHOW_ORCHESTRATOR_TOGGLE && orchestratorBackendOverride === "sdk")

  const coderValue: string = coderBackendOverride ?? "default"
  const orchValue: string = orchestratorBackendOverride ?? "default"

  const handleCoderChange = (value: string) => {
    const next: AgentBackend | null = value === "sdk" ? "sdk" : null
    setCoderBackendOverride(next)
  }

  const handleOrchChange = (value: string) => {
    const next: AgentBackend | null = value === "sdk" ? "sdk" : null
    setOrchestratorBackendOverride(next)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={`flex h-[22px] items-center gap-1 rounded-full border px-2 py-0.5 shadow-inner transition-colors ${
            anyOverrideActive
              ? "border-amber-300 bg-amber-50"
              : "border-slate-200 bg-slate-100/80"
          }`}
          title={
            anyOverrideActive
              ? "Worker backend overrides active for this chat. Click to change."
              : "Developer/pilot worker-backend overrides (Phase 2)."
          }
        >
          <Settings
            className={`h-3 w-3 ${anyOverrideActive ? "text-amber-700" : "text-slate-500"}`}
          />
          {anyOverrideActive && (
            <Sparkles className="h-2.5 w-2.5 text-amber-600" />
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel className="text-xs text-muted-foreground">
          Worker backends (pilot)
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        <DropdownMenuLabel className="text-xs font-medium">
          Coder
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup value={coderValue} onValueChange={handleCoderChange}>
          <DropdownMenuRadioItem value="default" className="text-xs">
            Default (server)
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="sdk" className="text-xs">
            Claude Agent SDK
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>

        {SHOW_ORCHESTRATOR_TOGGLE && (
          <>
            <DropdownMenuSeparator />

            <DropdownMenuLabel className="text-xs font-medium">
              Orchestrator
            </DropdownMenuLabel>
            <DropdownMenuRadioGroup value={orchValue} onValueChange={handleOrchChange}>
              <DropdownMenuRadioItem value="default" className="text-xs">
                Default (LangChain)
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="sdk" className="text-xs">
                Claude Agent SDK (prototype)
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </>
        )}

        <DropdownMenuSeparator />
        <p className="px-2 py-1.5 text-[10px] leading-tight text-muted-foreground">
          Per-chat only — not persisted across refresh.
        </p>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
