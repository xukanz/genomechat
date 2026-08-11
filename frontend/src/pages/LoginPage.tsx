import { LoginForm } from '@/components/auth/LoginForm'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import logoMark from '../assets/logo.svg'
import { BRANDING } from '../config/branding'

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <img
            src={logoMark}
            alt={`${BRANDING.name} logo`}
            className="h-16 w-16 rounded-full object-cover shadow-lg shadow-indigo-500/20 mb-4 mx-auto"
          />
          <h1 className="text-3xl font-bold text-slate-900">{BRANDING.name}</h1>
          <p className="text-slate-600 mt-2">Welcome back</p>
        </div>

        <Card className="border-slate-200 shadow-xl">
          <CardHeader className="space-y-1">
            <CardTitle className="text-2xl">Log in</CardTitle>
            <CardDescription>
              Enter your email and password to access your account
            </CardDescription>
          </CardHeader>
          <CardContent>
            <LoginForm />
          </CardContent>
        </Card>

        <p className="text-center text-sm text-slate-500 mt-4">
          © {new Date().getFullYear()} {BRANDING.name}
        </p>
      </div>
    </div>
  )
}
