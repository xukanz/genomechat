/**
 * Landing page copy, in Chinese and English.
 *
 * The dictionary is split by locale so neither file outgrows the project's
 * size limit: see ./copy.types.ts for the shape both must satisfy.
 */

import type { Locale } from '../../store/localeStore'
import type { LandingCopy } from './copy.types'
import { zh } from './copy.zh'
import { en } from './copy.en'

export type { LandingCopy }

export const LANDING_COPY: Record<Locale, LandingCopy> = { zh, en }
