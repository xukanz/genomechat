import type { Locale } from '../store/localeStore'

/**
 * Abbreviate a row count the way each language actually does it.
 *
 * English groups by thousands (K/M); Chinese groups by 万. Running both
 * through the same "11.7M" template would read as a translation rather than
 * as Chinese, so the two branches differ on purpose.
 */
export function formatCount(value: number, locale: Locale): string {
  if (locale === 'zh') {
    if (value >= 100_000_000) return `${trim(value / 100_000_000)}亿`
    if (value >= 10_000) return `${trim(value / 10_000)}万`
    return value.toLocaleString('zh-CN')
  }

  if (value >= 1_000_000) return `${trim(value / 1_000_000)}M`
  if (value >= 1_000) return `${trim(value / 1_000)}K`
  return value.toLocaleString('en-US')
}

/** Three significant figures, with a trailing ".0" dropped. */
function trim(scaled: number): string {
  const decimals = scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2
  return scaled.toFixed(decimals).replace(/\.0+$/, '')
}

/** Full count with thousands separators, e.g. "4,480,843" / "4,480,843". */
export function formatExact(value: number, locale: Locale): string {
  return value.toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US')
}
