'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'

export default function Register() {
  const router = useRouter()
  
  const [step, setStep] = useState<'register' | 'otp'>('register')
  
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [otp, setOtp] = useState('')
  
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')
  const [loading, setLoading] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  useEffect(() => {
    let timer: any
    if (cooldown > 0) {
      timer = setInterval(() => setCooldown((prev) => prev - 1), 1000)
    }
    return () => clearInterval(timer)
  }, [cooldown])

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccessMsg('')
    setLoading(true)

    try {
      await api.post('/auth/register', { email, username: username || undefined, password })
      setSuccessMsg('Registration successful! Please check your email for the 6-digit verification code.')
      setStep('otp')
      setCooldown(60)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred during registration')
    } finally {
      setLoading(false)
    }
  }

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccessMsg('')
    setLoading(true)

    try {
      await api.post('/auth/verify-email', { email, otp })
      setSuccessMsg('Email verified successfully! Logging you in...')

      // Auto login after verification
      const res = await api.post('/auth/login', { email, password })
      if (res.data?.access_token) {
        localStorage.setItem('access_token', res.data.access_token)
      }
      setTimeout(() => {
        window.location.href = '/'
      }, 1000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid or expired verification code')
      setLoading(false)
    }
  }

  const handleResendOtp = async () => {
    if (cooldown > 0) return
    setError('')
    setSuccessMsg('')
    try {
      await api.post('/auth/resend-otp', { email, purpose: 'email_verification' })
      setSuccessMsg('A new 6-digit verification code has been sent to your email.')
      setCooldown(60)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to resend code')
    }
  }

  return (
    <div className="flex items-center justify-center min-h-[calc(100vh-3.5rem)] px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl text-center">
            {step === 'register' ? 'Join SolveNow' : 'Verify Your Email'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {successMsg && (
            <Alert className="mb-4 bg-green-500/10 text-green-600 border-green-500/20">
              <AlertDescription>{successMsg}</AlertDescription>
            </Alert>
          )}

          {step === 'register' ? (
            <form onSubmit={handleRegister} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">
                  Username <span className="text-muted-foreground text-xs">(optional)</span>
                </Label>
                <Input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="your_username"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Registering...' : 'Register'}
              </Button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <p className="text-sm text-muted-foreground text-center mb-2">
                We sent a 6-digit code to <strong className="text-foreground">{email}</strong>
              </p>
              <div className="space-y-2">
                <Label htmlFor="otp">6-Digit Verification Code</Label>
                <Input
                  id="otp"
                  type="text"
                  maxLength={6}
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                  placeholder="123456"
                  className="text-center text-lg tracking-widest font-mono"
                  required
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading || otp.length !== 6}>
                {loading ? 'Verifying...' : 'Verify Email'}
              </Button>

              <div className="pt-2 text-center">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={handleResendOtp}
                  disabled={cooldown > 0}
                  className="text-xs text-muted-foreground"
                >
                  {cooldown > 0 ? `Resend code in ${cooldown}s` : "Didn't receive a code? Resend"}
                </Button>
              </div>
            </form>
          )}
        </CardContent>
        <CardFooter className="flex justify-center">
          <p className="text-sm text-muted-foreground">
            Already have an account? <a href="/login" className="text-primary hover:underline">Login</a>
          </p>
        </CardFooter>
      </Card>
    </div>
  )
}
