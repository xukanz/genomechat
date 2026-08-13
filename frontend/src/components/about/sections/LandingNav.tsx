import { Menu } from "lucide-react"
import { Button } from "../../ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../ui/dropdown-menu"
import { LanguageToggle } from "../LanguageToggle"
import { useLandingCopy } from "../../../hooks/useLandingCopy"
import { BRANDING } from "../../../config/branding"
import { SECTION_IDS } from "./anchors"
import logoMark from "../../../assets/logo.svg"

interface LandingNavProps {
  isAuthenticated: boolean
  onCTA: () => void
}

export function LandingNav({ isAuthenticated, onCTA }: LandingNavProps) {
  const copy = useLandingCopy()

  const links = [
    { href: `#${SECTION_IDS.architecture}`, label: copy.nav.architecture },
    { href: `#${SECTION_IDS.data}`, label: copy.nav.data },
    { href: `#${SECTION_IDS.useCases}`, label: copy.nav.useCases },
    { href: `#${SECTION_IDS.security}`, label: copy.nav.security },
  ]

  return (
    <nav className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-slate-100">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
        <a href="#top" className="flex items-center gap-2.5 flex-shrink-0">
          <img src={logoMark} alt={`${BRANDING.name} logo`} className="h-8 w-8 rounded-lg" />
          <span className="font-semibold text-slate-900 tracking-tight">{BRANDING.name}</span>
        </a>

        <div className="hidden md:flex items-center gap-7">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm text-slate-500 hover:text-slate-900 transition-colors"
            >
              {link.label}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <LanguageToggle />

          <DropdownMenu>
            <DropdownMenuTrigger asChild className="md:hidden">
              <Button variant="ghost" size="icon" aria-label={copy.nav.menu}>
                <Menu className="w-5 h-5 text-slate-600" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {links.map((link) => (
                <DropdownMenuItem key={link.href} asChild>
                  <a href={link.href}>{link.label}</a>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <Button
            onClick={onCTA}
            className="bg-slate-900 hover:bg-slate-800 text-white rounded-full px-6 text-sm font-medium shadow-none"
          >
            {isAuthenticated ? copy.nav.openApp : copy.nav.getStarted}
          </Button>
        </div>
      </div>
    </nav>
  )
}
