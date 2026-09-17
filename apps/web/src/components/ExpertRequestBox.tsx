import { useState, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'

export function ExpertRequestBox({ problemId, isAuthor }: { problemId: string, isAuthor: boolean }) {
  const [experts, setExperts] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!problemId) return
    api.get(`/experts/match/${problemId}`).then(res => {
      setExperts(res.data)
    }).catch(console.error)
  }, [problemId])

  const handleRequest = async (expertId: string) => {
    setLoading(true)
    try {
      await api.post(`/experts/problems/${problemId}/request-expert`, {
        expert_id: expertId,
        message
      })
      alert('Request sent to expert!')
      setMessage('')
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to request expert')
    }
    setLoading(false)
  }

  if (experts.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Recommended Experts</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {experts.map(expert => (
          <div key={expert.id} className="p-3 border rounded-lg bg-card">
            <div className="flex justify-between items-start mb-2">
              <div>
                <h4 className="font-semibold text-sm">{expert.username}</h4>
                <p className="text-xs text-muted-foreground">{expert.years_experience} YOE • {expert.reputation_score} Rep</p>
              </div>
              <span className="bg-primary/10 text-primary text-xs font-bold px-2 py-0.5 rounded">
                {Math.round(expert.match_score)} Match
              </span>
            </div>
            
            {isAuthor && (
              <div className="space-y-2 mt-3">
                <Input 
                  placeholder="Optional message..." 
                  className="text-xs h-8"
                  value={message}
                  onChange={e => setMessage(e.target.value)}
                />
                <Button 
                  size="sm" 
                  className="w-full text-xs" 
                  onClick={() => handleRequest(expert.user_id)}
                  disabled={loading}
                >
                  Request Help
                </Button>
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

