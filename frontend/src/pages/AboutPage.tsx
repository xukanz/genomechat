import { useNavigate } from "react-router-dom"
import { useAuthStore } from "../store/authStore"
import { useLocaleStore } from "../store/localeStore"
import { LandingNav } from "../components/about/sections/LandingNav"
import { HeroSection } from "../components/about/sections/HeroSection"
import { TrustBadges } from "../components/about/sections/TrustBadges"
import { ImpactStatement } from "../components/about/sections/ImpactStatement"
import { ArchitectureSection } from "../components/about/sections/ArchitectureSection"
import { DataScaleSection } from "../components/about/sections/DataScaleSection"
import { ComparisonSection } from "../components/about/sections/ComparisonSection"
import { DatabaseSection } from "../components/about/sections/DatabaseSection"
import { UseCaseSection } from "../components/about/sections/UseCaseSection"
import { SecuritySection } from "../components/about/sections/SecuritySection"
import { CtaSection } from "../components/about/sections/CtaSection"
import { LandingFooter } from "../components/about/sections/LandingFooter"

export function AboutPage() {
  const navigate = useNavigate()
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const locale = useLocaleStore((state) => state.locale)

  const handleCTA = () => {
    navigate(isAuthenticated ? "/app" : "/login")
  }

  return (
    <div className="min-h-screen bg-white" lang={locale === "zh" ? "zh-CN" : "en"}>
      <LandingNav isAuthenticated={isAuthenticated} onCTA={handleCTA} />
      <HeroSection onCTA={handleCTA} />
      <TrustBadges />
      <ImpactStatement />
      <ArchitectureSection />
      <DataScaleSection />
      <ComparisonSection />
      <DatabaseSection />
      <UseCaseSection />
      <SecuritySection />
      <CtaSection onCTA={handleCTA} />
      <LandingFooter />
    </div>
  )
}
