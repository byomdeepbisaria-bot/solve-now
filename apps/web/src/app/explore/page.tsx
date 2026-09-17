'use client'

import { useEffect, useState, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { api } from '@/lib/api'
import Link from 'next/link'
import { formatDistanceToNow } from 'date-fns'
import { Search, Filter, AlertCircle, CheckCircle, Clock } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

function ExploreContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  
  const [problems, setProblems] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [categories, setCategories] = useState<any[]>([])
  
  const currentCategory = searchParams.get('category') || ''
  const currentStatus = searchParams.get('status') || ''
  const currentQuery = searchParams.get('q') || ''

  useEffect(() => {
    // Fetch categories for filter
    api.get('/problems/categories').then(res => setCategories(res.data)).catch(() => {})
  }, [])

  useEffect(() => {
    const fetchProblems = async () => {
      setLoading(true)
      try {
        let url = '/problems'
        const params = new URLSearchParams()
        if (currentCategory) params.append('category', currentCategory)
        if (currentStatus) params.append('status', currentStatus)

        if (currentQuery) {
          url = `/problems/search`
          params.append('q', currentQuery)
        }

        const res = await api.get(`${url}?${params.toString()}`)
        // Both /problems and /problems/search return PaginatedProblems {items, total, page, size}
        setProblems(res.data?.items ?? [])
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    fetchProblems()
  }, [currentCategory, currentStatus, currentQuery])

  const updateFilters = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams.toString())
    if (value) {
      params.set(key, value)
    } else {
      params.delete(key)
    }
    router.push(`/explore?${params.toString()}`)
  }

  const handleSearch = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    updateFilters('q', formData.get('q') as string)
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 flex flex-col md:flex-row gap-8">
      {/* Filters Sidebar */}
      <div className="w-full md:w-64 space-y-6 flex-shrink-0">
        <div>
          <h2 className="font-semibold text-lg flex items-center gap-2 mb-4">
            <Filter className="h-4 w-4" /> Filters
          </h2>
          
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Status</label>
              <div className="flex flex-col gap-1">
                <Button variant={currentStatus === '' ? 'secondary' : 'ghost'} className="justify-start" onClick={() => updateFilters('status', '')}>All</Button>
                <Button variant={currentStatus === 'OPEN' ? 'secondary' : 'ghost'} className="justify-start" onClick={() => updateFilters('status', 'OPEN')}>Open</Button>
                <Button variant={currentStatus === 'SOLVED' ? 'secondary' : 'ghost'} className="justify-start" onClick={() => updateFilters('status', 'SOLVED')}>Solved</Button>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Category</label>
              <div className="flex flex-col gap-1">
                <Button variant={currentCategory === '' ? 'secondary' : 'ghost'} className="justify-start" onClick={() => updateFilters('category', '')}>All</Button>
                {categories.map(c => (
                  <Button 
                    key={c.name} 
                    variant={currentCategory === c.name ? 'secondary' : 'ghost'} 
                    className="justify-start" 
                    onClick={() => updateFilters('category', c.name)}
                  >
                    {c.name}
                  </Button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 space-y-6">
        <div className="flex flex-col sm:flex-row gap-4 justify-between items-start sm:items-center">
          <h1 className="text-3xl font-bold tracking-tight">Explore Problems</h1>
          
          <form onSubmit={handleSearch} className="relative w-full sm:w-auto">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input 
              name="q" 
              defaultValue={currentQuery} 
              placeholder="Search problems..." 
              className="pl-9 w-full sm:w-64 bg-background"
            />
          </form>
        </div>

        {loading ? (
          <div className="space-y-4">
            {Array(5).fill(0).map((_, i) => (
              <div key={i} className="border rounded-xl p-5 bg-card animate-pulse">
                <div className="h-5 bg-muted rounded w-1/3 mb-2"></div>
                <div className="h-4 bg-muted rounded w-full mb-1"></div>
                <div className="h-4 bg-muted rounded w-2/3"></div>
              </div>
            ))}
          </div>
        ) : problems.length > 0 ? (
          <div className="space-y-4">
            {problems.map(problem => (
              <Link href={`/problems/${problem.public_id}`} key={problem.id} className="block group">
                <div className="border bg-card rounded-xl p-5 hover:border-primary/50 transition-colors shadow-sm">
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="font-semibold text-lg group-hover:text-primary transition-colors">{problem.title}</h3>
                    {problem.status === 'SOLVED' ? (
                      <span className="flex items-center text-xs font-medium text-green-700 bg-green-100 px-2 py-1 rounded-md">
                        <CheckCircle className="h-3 w-3 mr-1" /> Solved
                      </span>
                    ) : (
                      <span className="flex items-center text-xs font-medium text-blue-700 bg-blue-100 px-2 py-1 rounded-md">
                        <Clock className="h-3 w-3 mr-1" /> Open
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground mb-4 line-clamp-2">{problem.description}</p>
                  
                  <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground font-medium">
                    {problem.category && <span className="bg-secondary px-2 py-1 rounded-md">{problem.category.name}</span>}
                    <span>Posted {formatDistanceToNow(new Date(problem.created_at))} ago</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="text-center py-20 border border-dashed rounded-xl bg-card">
            <AlertCircle className="h-10 w-10 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold">No problems found</h3>
            <p className="text-muted-foreground mt-1">Try adjusting your filters or search query.</p>
            <Button variant="outline" className="mt-6" onClick={() => router.push('/explore')}>Clear Filters</Button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function ExplorePage() {
  return (
    <Suspense fallback={<div className="p-8 text-center">Loading explore...</div>}>
      <ExploreContent />
    </Suspense>
  )
}

