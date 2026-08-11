/**
 * ProjectColorPicker - Color selection component with preset palette
 */

import { cn } from '../../lib/utils'

const PRESET_COLORS = [
  { name: 'Blue', value: '#3B82F6' },
  { name: 'Green', value: '#10B981' },
  { name: 'Yellow', value: '#F59E0B' },
  { name: 'Red', value: '#EF4444' },
  { name: 'Purple', value: '#8B5CF6' },
  { name: 'Pink', value: '#EC4899' },
  { name: 'Indigo', value: '#6366F1' },
  { name: 'Cyan', value: '#06B6D4' },
  { name: 'Orange', value: '#F97316' },
  { name: 'Emerald', value: '#059669' },
  { name: 'Violet', value: '#7C3AED' },
  { name: 'Gray', value: '#6B7280' },
]

interface ProjectColorPickerProps {
  value: string
  onChange: (color: string) => void
  disabled?: boolean
}

export function ProjectColorPicker({ value, onChange, disabled }: ProjectColorPickerProps) {
  return (
    <div className="space-y-3">
      {/* Preset Colors Grid */}
      <div className="grid grid-cols-6 gap-2">
        {PRESET_COLORS.map((color) => (
          <button
            key={color.value}
            type="button"
            onClick={() => onChange(color.value)}
            disabled={disabled}
            className={cn(
              'w-10 h-10 rounded-md border-2 transition-all',
              'hover:scale-110 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
              value === color.value
                ? 'border-foreground ring-2 ring-ring ring-offset-2'
                : 'border-transparent',
              disabled && 'opacity-50 cursor-not-allowed hover:scale-100'
            )}
            style={{ backgroundColor: color.value }}
            title={color.name}
            aria-label={`Select ${color.name} color`}
          />
        ))}
      </div>

      {/* Custom Color Input */}
      <div className="flex items-center gap-2">
        <label htmlFor="custom-color" className="text-sm text-muted-foreground">
          Custom:
        </label>
        <input
          id="custom-color"
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={cn(
            'w-16 h-8 rounded border border-border cursor-pointer',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        />
        <span className="text-xs text-muted-foreground font-mono">{value.toUpperCase()}</span>
      </div>
    </div>
  )
}
