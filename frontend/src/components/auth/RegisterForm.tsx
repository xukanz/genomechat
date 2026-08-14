import { useState, FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Loader2, Check, X } from 'lucide-react'
import { cn } from '@/lib/utils'

// Password validation rules
const passwordRules = [
  { label: 'At least 8 characters', test: (pwd: string) => pwd.length >= 8 },
  { label: 'One uppercase letter', test: (pwd: string) => /[A-Z]/.test(pwd) },
  { label: 'One lowercase letter', test: (pwd: string) => /[a-z]/.test(pwd) },
  { label: 'One number', test: (pwd: string) => /\d/.test(pwd) },
  { label: 'One special character', test: (pwd: string) => /[!@#$%^&*()_+\-=[\]{}';:"\\|,.<>/?]/.test(pwd) },
]

export function RegisterForm() {
  const navigate = useNavigate()
  const { register, isLoading, error, clearError } = useAuthStore()
  
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [showPasswordHints, setShowPasswordHints] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    clearError()

    // Client-side validation
    const allRulesPassed = passwordRules.every(rule => rule.test(password))
    if (!allRulesPassed) {
      return // Don't submit if password doesn't meet requirements
    }

    try {
      await register(email, name, password)
      navigate('/app') // Redirect to app on success
    } catch (err) {
      // Error is already set in store
      console.error('Registration failed:', err)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="p-3 rounded-lg bg-red-50 border border-red-200">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
          required
          disabled={isLoading}
          autoComplete="email"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="name">Full Name</Label>
        <Input
          id="name"
          type="text"
          placeholder="John Doe"
          value={name}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
          required
          disabled={isLoading}
          autoComplete="name"
          minLength={1}
          maxLength={100}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
          onFocus={() => setShowPasswordHints(true)}
          required
          disabled={isLoading}
          autoComplete="new-password"
        />
        
        {showPasswordHints && password && (
          <div className="mt-2 p-3 rounded-lg bg-slate-50 border border-slate-200">
            <p className="text-xs font-medium text-slate-700 mb-2">Password requirements:</p>
            <ul className="space-y-1">
              {passwordRules.map((rule, idx) => {
                const passed = rule.test(password)
                return (
                  <li
                    key={idx}
                    className={cn(
                      "flex items-center gap-2 text-xs",
                      passed ? "text-green-600" : "text-slate-500"
                    )}
                  >
                    {passed ? (
                      <Check className="h-3 w-3" />
                    ) : (
                      <X className="h-3 w-3" />
                    )}
                    {rule.label}
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </div>

      <Button
        type="submit"
        className="w-full"
        disabled={isLoading}
      >
        {isLoading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Creating account...
          </>
        ) : (
          'Create Account'
        )}
      </Button>

      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{' '}
        <Link
          to="/login"
          className="font-medium text-primary hover:underline"
        >
          Log in
        </Link>
      </p>
    </form>
  )
}
