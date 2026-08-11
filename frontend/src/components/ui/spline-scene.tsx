import { Suspense, lazy } from "react"
import { Loader2 } from "lucide-react"

const Spline = lazy(() => import("@splinetool/react-spline"))

interface SplineSceneProps {
  scene: string
  className?: string
}

export function SplineScene({ scene, className }: SplineSceneProps) {
  return (
    <Suspense
      fallback={
        <div className="w-full h-full flex items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
        </div>
      }
    >
      <Spline scene={scene} className={className} />
    </Suspense>
  )
}
