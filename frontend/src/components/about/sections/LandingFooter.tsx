import { BRANDING } from "../../../config/branding"

export function LandingFooter() {
  return (
    <footer className="bg-slate-950 py-8 text-center border-t border-slate-800/50">
      <p className="text-xs text-slate-600 tracking-wide">
        &copy; {new Date().getFullYear()} {BRANDING.name}
      </p>
    </footer>
  )
}
