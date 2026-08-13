import { useState, FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Loader2 } from 'lucide-react'

interface LoginFormProps {
  /** Seeds the email field. Used by the demo build to pre-fill credentials. */
  defaultEmail?: string
  /** Seeds the password field. Used by the demo build to pre-fill credentials. */
  defaultPassword?: string
}

export function LoginForm({ defaultEmail = '', defaultPassword = '' }: LoginFormProps = {}) {
  const navigate = useNavigate()
  const { login, isLoading, error, clearError } = useAuthStore()

  const [email, setEmail] = useState(defaultEmail)
  const [password, setPassword] = useState(defaultPassword)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    clearError()

    try {
      await login(email, password)
      navigate('/app') // Redirect to app on success
    } catch (err) {
      // Error is already set in store
      console.error('Login failed:', err)
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
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
          required
          disabled={isLoading}
          autoComplete="current-password"
        />
        <p className="text-xs text-muted-foreground">
          Forgot your password? Contact your administrator.
        </p>
      </div>

      <Button
        type="submit"
        className="w-full"
        disabled={isLoading}
      >
        {isLoading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Logging in...
          </>
        ) : (
          'Log In'
        )}
      </Button>

      <p className="text-center text-sm text-muted-foreground">
        Don't have an account?{' '}
        <Link
          to="/register"
          className="font-medium text-primary hover:underline"
        >
          Sign up
        </Link>
      </p>
    </form>
  )
}
