import { cn } from "../../lib/utils"
import type { ExampleQuestion, QuestionComplexity } from "../../types/database"

interface ExampleQuestionsProps {
  questions: ExampleQuestion[]
  onSelect: (text: string) => void
}

// Number of filled bars for each complexity level
const complexityBars: Record<QuestionComplexity, number> = {
  basic: 1,
  medium: 2,
  advanced: 3,
}

// Complexity indicator component - 3 bars like signal strength
function ComplexityIndicator({ complexity }: { complexity: QuestionComplexity }) {
  const filledBars = complexityBars[complexity]

  return (
    <div className="flex items-end gap-0.5 ml-1.5" title={`${complexity} complexity`}>
      {[1, 2, 3].map((bar) => (
        <div
          key={bar}
          className={cn(
            "w-[3px] rounded-sm transition-colors",
            bar === 1 ? "h-[6px]" : bar === 2 ? "h-[9px]" : "h-[12px]",
            bar <= filledBars ? "bg-slate-500" : "bg-slate-200"
          )}
        />
      ))}
    </div>
  )
}

export function ExampleQuestions({ questions, onSelect }: ExampleQuestionsProps) {
  if (!questions || questions.length === 0) {
    return null
  }

  return (
    <div className="flex flex-col items-center gap-2 mt-4">
      <div className="flex flex-wrap justify-center gap-2">
        {questions.map((question, index) => (
          <button
            key={`${question.label}-${index}`}
            type="button"
            onClick={() => onSelect(question.text)}
            className={cn(
              "inline-flex items-center rounded-full px-3 py-1.5 text-xs font-medium",
              "border shadow-sm cursor-pointer transition-colors duration-150",
              "bg-slate-100 text-slate-700 border-slate-200 hover:bg-slate-200"
            )}
            title={question.text}
          >
            {question.label}
            <ComplexityIndicator complexity={question.complexity} />
          </button>
        ))}
      </div>
      <p className="text-[10px] text-muted-foreground/50">
        More bars = deeper analysis (may take longer)
      </p>
    </div>
  )
}
