'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CheckCircle2, ArrowUp, ArrowDown, Download, FileText, Trash2, Activity, MessageSquare, Lightbulb, History, Settings } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { RoomChat } from '@/components/RoomChat'
import { FileUpload } from '@/components/FileUpload'
import { ExpertRequestBox } from '@/components/ExpertRequestBox'
import { ReportButton } from '@/components/ReportButton'
import { AIChatModal } from '@/components/AIChatModal'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'

function ProblemSkeleton() {
  return (
    <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      <div className="flex justify-between items-start">
        <div className="space-y-3 w-1/2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
        <Skeleton className="h-10 w-32" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <Skeleton className="h-64 lg:col-span-1" />
        <Skeleton className="h-96 lg:col-span-2" />
        <Skeleton className="h-96 lg:col-span-1" />
      </div>
    </div>
  )
}

export default function ProblemDetail() {
  const params = useParams()
  const router = useRouter()
  const publicId = params.publicId as string
  
  const [problem, setProblem] = useState<any>(null)
  const [solutions, setSolutions] = useState<any[]>([])
  const [currentUser, setCurrentUser] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  
  const [newSolution, setNewSolution] = useState('')
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editDesc, setEditDesc] = useState('')

  const [solvingWithAI, setSolvingWithAI] = useState(false)
  const [aiSolveResult, setAiSolveResult] = useState<any>(null)

  const handleRunAISolve = async () => {
    setSolvingWithAI(true)
    try {
      const res = await api.post('/ai/solve', {
        problem_id_or_public_id: publicId,
        include_files: true
      })
      setAiSolveResult(res.data)
      fetchData()
    } catch (err: any) {
      alert(err.response?.data?.detail || 'AI solve failed')
    } finally {
      setSolvingWithAI(false)
    }
  }

  const fetchData = async () => {
    try {
      const [authRes, probRes, solRes] = await Promise.all([
        api.get('/auth/me').catch(() => ({ data: null })),
        api.get(`/problems/${publicId}`),
        api.get(`/problems/${publicId}/solutions`)
      ])
      setCurrentUser(authRes.data)
      setProblem(probRes.data)
      setSolutions(solRes.data)
      setEditTitle(probRes.data.title)
      setEditDesc(probRes.data.description)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Problem not found or access denied')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [publicId])

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await api.patch(`/problems/${publicId}`, { title: editTitle, description: editDesc })
      fetchData()
      setEditing(false)
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Update failed')
    }
  }

  const handleCreateSolution = async (e: React.FormEvent) => {
    e.preventDefault()
    setActionError('')
    try {
      await api.post(`/problems/${publicId}/solutions`, { content: newSolution })
      fetchData()
      setNewSolution('')
    } catch (err: any) {
      setActionError(err.response?.data?.detail || 'Failed to post solution')
    }
  }

  const handleAction = async (action: () => Promise<any>) => {
    setActionError('')
    try {
      await action()
      fetchData()
    } catch (err: any) {
      setActionError(err.response?.data?.detail || 'Action failed')
    }
  }

  const handleDownload = async (fileId: string, filename: string) => {
    try {
      const response = await api.get(`/files/${fileId}/download`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', filename)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Download failed')
    }
  }

  if (loading) return <ProblemSkeleton />
  if (error || !problem) return (
    <div className="max-w-4xl mx-auto p-6 text-center">
      <Alert variant="destructive" className="mb-4"><AlertDescription>{error}</AlertDescription></Alert>
      <Button onClick={() => router.push('/explore')}>Browse Problems</Button>
    </div>
  )

  const isAuthor = currentUser?.id === problem.author_id

  // Modular components for columns/tabs
  const OverviewPanel = () => (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2"><History className="h-5 w-5" /> Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="whitespace-pre-wrap text-sm">{problem.description}</p>
          <div className="mt-4 pt-4 border-t flex flex-col gap-2 text-xs text-muted-foreground">
            <div className="flex justify-between"><span>Category</span> <span className="font-medium text-foreground">{problem.category?.name || 'General'}</span></div>
            <div className="flex justify-between"><span>Urgency</span> <span className="font-medium text-foreground capitalize">{problem.urgency}</span></div>
            <div className="flex justify-between"><span>Author</span> <span className="font-medium text-foreground">{problem.author_username ?? problem.author?.username ?? problem.author_id?.slice(0,8) ?? 'Unknown'}</span></div>
          </div>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Files</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {problem.files?.length > 0 ? problem.files.map((f: any) => (
            <div key={f.id} className="flex items-center justify-between p-2 border rounded bg-muted/30">
              <div className="flex items-center gap-2 overflow-hidden">
                <FileText className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                <span className="text-xs font-medium truncate">{f.original_name}</span>
              </div>
              <div className="flex">
                {f.scan_status !== 'INFECTED' && (
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => handleDownload(f.id, f.original_name)}><Download className="h-3 w-3" /></Button>
                )}
                {isAuthor && (
                  <Button variant="ghost" size="icon" className="h-6 w-6 text-red-500" onClick={() => handleAction(() => api.delete(`/files/${f.id}`))}><Trash2 className="h-3 w-3" /></Button>
                )}
              </div>
            </div>
          )) : <p className="text-xs text-muted-foreground">No files attached.</p>}
          {isAuthor && <div className="pt-2"><FileUpload publicId={publicId} onUploadComplete={fetchData} /></div>}
        </CardContent>
      </Card>
      
      <ExpertRequestBox problemId={problem.id} isAuthor={isAuthor} />
    </div>
  )

  const SolutionsPanel = () => (
    <Card className="h-full border-0 shadow-none sm:border sm:shadow-sm">
      <CardHeader className="pb-3 border-b">
        <CardTitle className="text-lg flex items-center gap-2 text-primary">
          <Lightbulb className="h-5 w-5" /> Collaborative Solutions
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-6">
        {actionError && (
          <div className="mb-4 p-3 rounded-md bg-destructive/15 text-destructive text-sm font-medium border border-destructive/20">
            {actionError}
          </div>
        )}
        
        {currentUser && (
          <form onSubmit={handleCreateSolution} className="space-y-3 pb-6 border-b">
            <Label>Propose a Solution</Label>
            <div className="flex gap-2">
              <Input value={newSolution} onChange={e => setNewSolution(e.target.value)} placeholder="Type your solution here..." required className="flex-1" />
              <Button type="submit">Post</Button>
            </div>
          </form>
        )}
        
        {solutions.length === 0 ? (
          <EmptyState title="No solutions yet" description="Review the problem summary and AI findings, then propose a solution." />
        ) : (
          <div className="space-y-4">
            {solutions.map((sol: any) => {
              const isOwnSolution = currentUser?.id === sol.author_id;
              
              return (
              <div key={sol.id} className={`flex gap-3 p-4 rounded-xl border ${sol.status === 'ACCEPTED' ? 'border-green-500 bg-green-50/20' : 'bg-card'}`}>
                <div className="flex flex-col items-center gap-1">
                  <button disabled={isOwnSolution} onClick={() => handleAction(() => api.post(`/solutions/${sol.id}/vote`, { value: sol.user_vote === 1 ? 0 : 1 }))} className={`p-1 rounded hover:bg-muted ${isOwnSolution ? 'opacity-50 cursor-not-allowed' : ''} ${sol.user_vote === 1 ? 'text-primary' : 'text-muted-foreground'}`}><ArrowUp className="h-4 w-4" /></button>
                  <span className="text-sm font-bold">{sol.upvotes - sol.downvotes}</span>
                  <button disabled={isOwnSolution} onClick={() => handleAction(() => api.post(`/solutions/${sol.id}/vote`, { value: sol.user_vote === -1 ? 0 : -1 }))} className={`p-1 rounded hover:bg-muted ${isOwnSolution ? 'opacity-50 cursor-not-allowed' : ''} ${sol.user_vote === -1 ? 'text-destructive' : 'text-muted-foreground'}`}><ArrowDown className="h-4 w-4" /></button>
                </div>
                <div className="flex-1 space-y-2">
                  <div className="flex justify-between items-start">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">{sol.author?.username || (typeof sol.author === 'string' ? sol.author : 'User')}</span>
                      <span className="text-xs text-muted-foreground">Â· {formatDistanceToNow(new Date(sol.created_at))} ago</span>
                    </div>
                    {sol.status === 'ACCEPTED' && <span className="flex items-center text-xs font-bold text-green-700 bg-green-100 px-2 py-0.5 rounded"><CheckCircle2 className="w-3 h-3 mr-1" /> Accepted</span>}
                  </div>
                  <p className="text-sm whitespace-pre-wrap">{sol.content}</p>
                  <div className="flex items-center gap-2 pt-2">
                    <Button disabled={isOwnSolution} variant="outline" size="sm" className="h-7 text-xs" onClick={() => handleAction(() => api.post(`/solutions/${sol.id}/verify`))}>
                      <CheckCircle2 className="w-3 h-3 mr-1" /> Verify ({sol.verification_count})
                    </Button>
                    {isAuthor && problem.status !== 'SOLVED' && (
                      <Button variant="default" size="sm" className="h-7 text-xs bg-green-600 hover:bg-green-700" onClick={() => handleAction(() => api.post(`/solutions/${sol.id}/accept`))}>Accept Solution</Button>
                    )}
                  </div>
                </div>
              </div>
            );})}
          </div>
        )}
      </CardContent>
    </Card>
  )

  const AIPanel = () => (
    <Card className="h-full border-0 shadow-none sm:border sm:shadow-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="text-lg flex items-center gap-2"><Activity className="h-5 w-5 text-primary" /> AI Multi-Agent</CardTitle>
        <Button
          size="sm"
          onClick={handleRunAISolve}
          disabled={solvingWithAI}
          className="h-8 text-xs font-semibold gap-1.5"
        >
          <Activity className={`h-3.5 w-3.5 ${solvingWithAI ? 'animate-spin' : ''}`} />
          {solvingWithAI ? 'Solving...' : 'Run AI Solve'}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {solvingWithAI && (
          <div className="flex items-center space-x-2 text-muted-foreground p-3 bg-primary/5 rounded-lg border border-primary/20 animate-pulse">
            <div className="relative flex h-3 w-3"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span><span className="relative inline-flex rounded-full h-3 w-3 bg-primary"></span></div>
            <span className="text-xs font-medium">Orchestrating agents, executing tools, and verifying solution...</span>
          </div>
        )}

        {aiSolveResult && (
          <div className="p-3 bg-card border rounded-lg space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-primary px-2 py-0.5 rounded bg-primary/10">
                {aiSolveResult.agent_role || 'Verified Solution'}
              </span>
              <Button
                variant="outline"
                size="sm"
                className="h-6 text-[11px]"
                onClick={() => {
                  setNewSolution(aiSolveResult.response)
                  alert('Solution copied to collaborative solutions draft box!')
                }}
              >
                Copy to Post Box
              </Button>
            </div>
            <p className="text-xs whitespace-pre-wrap leading-relaxed text-foreground bg-muted/20 p-2.5 rounded border">
              {aiSolveResult.response}
            </p>

            {aiSolveResult.activity_steps?.length > 0 && (
              <div className="border-t pt-2 space-y-1">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">AI Activity Trace:</span>
                {aiSolveResult.activity_steps.map((st: any, i: number) => (
                  <div key={i} className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
                    <CheckCircle2 className="h-3 w-3 text-green-500 shrink-0 mt-0.5" />
                    <span><strong className="text-foreground">[{st.step}]</strong> {st.description}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {['CREATED', 'ANALYZING', 'RESEARCHING', 'DIAGNOSING', 'GENERATING', 'REVIEWING'].includes(problem.investigation?.status || '') ? (
          <div className="flex items-center space-x-2 text-muted-foreground p-3 bg-muted/30 rounded-lg border">
            <div className="relative flex h-3 w-3"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span><span className="relative inline-flex rounded-full h-3 w-3 bg-primary"></span></div>
            <span className="text-sm font-medium">AI is {problem.investigation?.status.toLowerCase()}...</span>
          </div>
        ) : null}
        
        {problem.investigation?.findings?.length > 0 ? (
          <div className="space-y-4">
            {problem.investigation.clarifications?.filter((c: any) => !c.answer).length > 0 && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <h4 className="text-sm font-semibold text-amber-800 mb-2">Needs Clarification</h4>
                {problem.investigation.clarifications.filter((c: any) => !c.answer).map((c: any) => (
                  <div key={c.id} className="space-y-2">
                    <p className="text-xs text-amber-900">{c.question}</p>
                    {isAuthor && (
                      <form onSubmit={e => { e.preventDefault(); const v = (e.target as any).answer.value; if(v) handleAction(() => api.post(`/problems/${problem.public_id}/clarifications/${c.id}`, { answer: v })) }} className="flex gap-2">
                        <Input name="answer" size={1} className="h-7 text-xs" placeholder="Answer..." />
                        <Button size="sm" className="h-7 text-xs">Reply</Button>
                      </form>
                    )}
                  </div>
                ))}
              </div>
            )}
            
            <div className="space-y-2">
              <h4 className="text-sm font-semibold">Diagnostic Findings</h4>
              {problem.investigation.findings.map((f: any) => (
                <div key={f.id} className="p-2 border rounded-md text-xs bg-muted/10">
                  <p className="font-medium">{f.finding}</p>
                  <div className="flex justify-between items-center mt-2">
                    <span className="text-muted-foreground truncate w-3/4">Ev: {f.evidence}</span>
                    <span className={`px-1.5 py-0.5 rounded font-bold ${f.confidence > 0.8 ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>{Math.round(f.confidence*100)}%</span>
                  </div>
                </div>
              ))}
            </div>

            {problem.investigation.solutions?.length > 0 && (
              <div className="space-y-2 pt-2 border-t">
                <h4 className="text-sm font-semibold">AI Proposed Fixes</h4>
                {problem.investigation.solutions.map((sol: any) => (
                  <div key={sol.id} className="p-2 border rounded-md text-xs bg-blue-50/30">
                    <div className="flex justify-between font-semibold"><span>{sol.title}</span><span className="text-blue-700">{Math.round(sol.confidence*100)}%</span></div>
                    {sol.critic_review && (
                       <span className={`mt-1 inline-block px-1.5 py-0.5 rounded text-[10px] font-bold ${sol.critic_review.is_safe ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                         {sol.critic_review.is_safe ? 'Safe' : 'Unsafe'}
                       </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : !aiSolveResult && (
          <EmptyState title="No AI insights yet" description="Click 'Run AI Solve' or 'Ask AI' to orchestrate specialized agents." />
        )}
      </CardContent>
    </Card>
  )

  return (
    <div className="bg-muted/10 min-h-[calc(100vh-4rem)] pb-12">
      {/* Header Bar */}
      <div className="bg-background border-b px-4 py-6 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row justify-between items-start gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">{problem.title}</h1>
            <div className="flex flex-wrap items-center gap-3 mt-3 text-sm text-muted-foreground">
              <span className="bg-primary/10 text-primary px-2.5 py-1 rounded-md font-semibold tracking-wide">
                {problem.status}
              </span>
              <span className="flex items-center"><History className="h-3 w-3 mr-1"/> {formatDistanceToNow(new Date(problem.created_at))} ago</span>
              {!problem.is_public && <span className="text-amber-600 border border-amber-200 bg-amber-50 px-2 py-0.5 rounded text-xs font-medium">Private Workspace</span>}
              <ReportButton entityType="problem" entityId={problem.id} />
              <AIChatModal problemContext={`Title: ${problem.title}\nDescription: ${problem.description}`} />
            </div>
          </div>
          
          {isAuthor && (
            <Dialog open={editing} onOpenChange={setEditing}>
              <DialogTrigger render={<Button variant="outline" size="sm" />}>
                <Settings className="h-4 w-4 mr-2"/> Edit Problem
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>Edit Workspace</DialogTitle></DialogHeader>
                <form onSubmit={handleUpdate} className="space-y-4">
                  <div className="space-y-2"><Label>Title</Label><Input value={editTitle} onChange={e => setEditTitle(e.target.value)} required /></div>
                  <div className="space-y-2"><Label>Description</Label><Input value={editDesc} onChange={e => setEditDesc(e.target.value)} required /></div>
                  <Button type="submit" className="w-full">Save Changes</Button>
                </form>
              </DialogContent>
            </Dialog>
          )}
        </div>
      </div>

      {/* Main Workspace Layout */}
      <div className="max-w-7xl mx-auto px-0 sm:px-6 lg:px-8 mt-6">
        
        {/* Mobile Tabs */}
        <div className="lg:hidden">
          <Tabs defaultValue="solutions" className="w-full">
            <div className="px-4 mb-4 overflow-x-auto pb-2">
              <TabsList className="w-full justify-start sm:justify-center grid grid-cols-4 min-w-[320px]">
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="solutions">Solutions</TabsTrigger>
                <TabsTrigger value="chat">Chat</TabsTrigger>
              </TabsList>
            </div>
            <div className="px-4">
              <TabsContent value="overview" className="mt-0"><OverviewPanel /></TabsContent>
              <TabsContent value="solutions" className="mt-0"><SolutionsPanel /></TabsContent>
              <TabsContent value="chat" className="mt-0"><RoomChat publicId={publicId} currentUser={currentUser} aiPanel={<AIPanel />} /></TabsContent>
            </div>
          </Tabs>
        </div>

        {/* Desktop Multi-column */}
        <div className="hidden lg:grid grid-cols-4 gap-6 items-start">
          <div className="col-span-1 space-y-6 sticky top-24">
            <OverviewPanel />
          </div>
          
          <div className="col-span-2 space-y-6">
            <SolutionsPanel />
          </div>
          
          <div className="col-span-1 space-y-6 sticky top-24">
            <div className="h-[600px]">
              <RoomChat publicId={publicId} currentUser={currentUser} aiPanel={<AIPanel />} />
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
