import { LANDING_COPY, type LandingCopy } from '../config/landing/copy'
import { useLocaleStore } from '../store/localeStore'

/**
 * Active landing-page copy. Section components call this directly instead of
 * threading a `copy` prop down, which keeps the page shell free of plumbing.
 */
export function useLandingCopy(): LandingCopy {
  return LANDING_COPY[useLocaleStore((state) => state.locale)]
}
