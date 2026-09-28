'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'

export default function ForgotPassword() {
  const router = useRouter()
  const [step, setStep] = useState<'email' | 'otp' | 'new_password'>('email')

  // Form inputs
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [resetToken, setResetToken] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  // UI state
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

  // Step 1: Send reset OTP
  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccessMsg('')
    setLoading(true)

    try {
      await api.post('/auth/forgot-password', { email })
      setSuccessMsg('If an account exists with this email, a 6-digit reset code has been sent.')
      setStep('otp')
      setCooldown(60)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to send reset code. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  // Step 2: Verify reset OTP
  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccessMsg('')
    setLoading(true)

    try {
      const res = await api.post('/auth/verify-reset-otp', { email, otp })
      if (res.data?.reset_token) {
        setResetToken(res.data.reset_token)
        setSuccessMsg('Code verified! Please enter your new password.')
        setStep('new_password')
      } else {
        setError('Invalid server response during code verification.')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid or expired 6-digit reset code.')
    } finally {
      setLoading(false)
    }
  }

  // Step 3: Set new password
  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccessMsg('')

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters long.')
      return
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)

    try {
      await api.post('/auth/reset-password', {
        reset_token: resetToken,
        new_password: newPassword,
      })
      setSuccessMsg('Password reset successfully! Redirecting to login...')
      setTimeout(() => {
        router.push('/login')
      }, 1500)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to reset password. Please try again.')
      setLoading(false)
    }
  }

  // Resend code handler
  const handleResendOtp = async () => {
    if (cooldown > 0) return
    setError('')
    setSuccessMsg('')
    try {
      await api.post('/auth/resend-otp', { email, purpose: 'password_reset' })
      setSuccessMsg('A new 6-digit reset code has been sent to your email.')
      setCooldown(60)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to resend code.')
    }
  }

  return (
    <div className="flex items-center justify-center min-h-[calc(100vh-3.5rem)] px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl text-center">
            {step === 'email' && 'Forgot Password'}
            {step === 'otp' && 'Enter Verification Code'}
            {step === 'new_password' && 'Reset Password'}
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

          {step === 'email' && (
            <form onSubmit={handleRequestOtp} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email Address</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  required
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Sending Code...' : 'Send Reset Code'}
              </Button>
            </form>
          )}

          {step === 'otp' && (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="otp">6-Digit Code</Label>
                <Input
                  id="otp"
                  type="text"
                  maxLength={6}
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                  placeholder="123456"
                  className="text-center text-2xl letter-spacing-2"
                  required
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Verifying...' : 'Verify Code'}
              </Button>

              <div className="text-center pt-2">
                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={cooldown > 0}
                  className="text-xs text-primary hover:underline disabled:opacity-50 disabled:no-underline"
                >
                  {cooldown > 0
                    ? `Resend code in ${cooldown}s`
                    : "Didn't get a code? Resend"}
                </button>
              </div>
            </form>
          )}

          {step === 'new_password' && (
            <form onSubmit={handleResetPassword} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="newPassword">New Password</Label>
                <Input
                  id="newPassword"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirmPassword">Confirm New Password</Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-enter password"
                  required
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Resetting Password...' : 'Reset Password'}
              </Button>
            </form>
          )}
        </CardContent>
        <CardFooter className="justify-center border-t pt-4">
          <Link href="/login" className="text-sm text-muted-foreground hover:text-foreground">
            Back to Login
          </Link>
        </CardFooter>
      </Card>
    </div>
  )
}
