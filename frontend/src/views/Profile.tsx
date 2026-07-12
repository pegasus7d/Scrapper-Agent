import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { apiPost } from '../api/client'
import type { ApplicantProfile, MatchScoreList } from '../api/types'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select'
import { useApi } from '../hooks/useApi'

// Real score distribution over scraped jobs (PHASE11.md step 4) -- lets
// the user see, on their own real data, what MATCH_SCORE_THRESHOLD's
// default would gate out before trusting it blindly. The fetch itself is
// skipped (useApi's path=null) until a resume exists, not just the
// rendered section.
function MatchScoreSection({ hasResume }: { hasResume: boolean }) {
  const scores = useApi<MatchScoreList>(hasResume ? '/profile/match-scores' : null)
  if (!hasResume || !scores.data || scores.data.items.length === 0) return null

  const { items, threshold } = scores.data
  const passing = items.filter((s) => s.score >= threshold).length

  return (
    <div className="mt-6 max-w-md rounded-xl border border-border bg-card p-5">
      <h2 className="text-sm font-semibold text-foreground">Match scores</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        {passing} of {items.length} scraped jobs meet the current threshold ({threshold.toFixed(2)}
        ).
      </p>
      <ul className="mt-3 divide-y divide-border text-sm">
        {items.slice(0, 10).map((s) => (
          <li key={s.job_id} className="flex items-center justify-between gap-2 py-1.5">
            <span className="truncate text-foreground">
              {s.title} · {s.company}
            </span>
            <Badge variant={s.score >= threshold ? 'secondary' : 'outline'}>
              {s.score.toFixed(2)}
            </Badge>
          </li>
        ))}
      </ul>
    </div>
  )
}

type RelocationChoice = 'unspecified' | 'yes' | 'no'

function relocationToChoice(relocation: boolean | null): RelocationChoice {
  if (relocation === true) return 'yes'
  if (relocation === false) return 'no'
  return 'unspecified'
}

function choiceToRelocation(choice: RelocationChoice): boolean | null {
  if (choice === 'yes') return true
  if (choice === 'no') return false
  return null
}

// The user's own real answers only (PHASE10.md step 5's hard stop) --
// every field starts blank/unspecified and nothing here is pre-filled or
// guessed. The auto-apply form-filler answer-tool system (step 7) reads
// from whatever is saved here.
export function Profile() {
  const profile = useApi<ApplicantProfile>('/profile')
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [linkedinUrl, setLinkedinUrl] = useState('')
  const [location, setLocation] = useState('')
  const [phone, setPhone] = useState('')
  const [currentSalary, setCurrentSalary] = useState('')
  const [expectedSalary, setExpectedSalary] = useState('')
  const [workAuthorization, setWorkAuthorization] = useState('')
  const [relocation, setRelocation] = useState<RelocationChoice>('unspecified')
  const [startDateAvailability, setStartDateAvailability] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!profile.data) return
    setFullName(profile.data.full_name ?? '')
    setEmail(profile.data.email ?? '')
    setLinkedinUrl(profile.data.linkedin_url ?? '')
    setLocation(profile.data.location ?? '')
    setPhone(profile.data.phone ?? '')
    setCurrentSalary(profile.data.current_salary ?? '')
    setExpectedSalary(profile.data.expected_salary ?? '')
    setWorkAuthorization(profile.data.work_authorization ?? '')
    setRelocation(relocationToChoice(profile.data.relocation))
    setStartDateAvailability(profile.data.start_date_availability ?? '')
  }, [profile.data])

  async function save() {
    setBusy(true)
    try {
      await apiPost('/profile', {
        full_name: fullName || null,
        email: email || null,
        linkedin_url: linkedinUrl || null,
        location: location || null,
        phone: phone || null,
        current_salary: currentSalary || null,
        expected_salary: expectedSalary || null,
        work_authorization: workAuthorization || null,
        relocation: choiceToRelocation(relocation),
        start_date_availability: startDateAvailability || null,
      })
      toast.success('Profile saved')
      profile.reload()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold text-foreground">Applicant profile</h1>
      <p className="mt-1 max-w-xl text-sm text-muted-foreground">
        Your own real answers, used by auto-apply's form-filler to answer application questions.
        Nothing here is pre-filled or guessed -- leave a field blank to answer it yourself when it
        comes up.
      </p>

      {profile.data && (
        <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
          Resume:
          <Badge variant={profile.data.has_resume ? 'secondary' : 'outline'}>
            {profile.data.has_resume ? 'uploaded' : 'not uploaded'}
          </Badge>
          {!profile.data.has_resume && 'upload one from the Resume view to enable auto-apply'}
        </p>
      )}

      <div className="mt-6 flex max-w-md flex-col gap-4 rounded-xl border border-border bg-card p-5">
        <label className="block text-sm font-medium text-muted-foreground">
          Full name
          <Input
            className="mt-1"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="e.g. Jane Doe"
          />
        </label>

        <label className="block text-sm font-medium text-muted-foreground">
          Email
          <Input
            className="mt-1"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="e.g. jane@example.com"
          />
        </label>

        <label className="block text-sm font-medium text-muted-foreground">
          LinkedIn profile URL
          <Input
            className="mt-1"
            value={linkedinUrl}
            onChange={(e) => setLinkedinUrl(e.target.value)}
            placeholder="e.g. https://linkedin.com/in/janedoe"
          />
        </label>

        <label className="block text-sm font-medium text-muted-foreground">
          Location
          <Input
            className="mt-1"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="e.g. San Francisco, CA"
          />
        </label>

        <label className="block text-sm font-medium text-muted-foreground">
          Phone
          <Input
            className="mt-1"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="e.g. 555-0100"
          />
        </label>

        <label className="block text-sm font-medium text-muted-foreground">
          Current salary
          <Input
            className="mt-1"
            value={currentSalary}
            onChange={(e) => setCurrentSalary(e.target.value)}
            placeholder="e.g. $120,000"
          />
        </label>

        <label className="block text-sm font-medium text-muted-foreground">
          Expected salary
          <Input
            className="mt-1"
            value={expectedSalary}
            onChange={(e) => setExpectedSalary(e.target.value)}
            placeholder="e.g. $140,000"
          />
        </label>

        <label className="block text-sm font-medium text-muted-foreground">
          Work authorization
          <Input
            className="mt-1"
            value={workAuthorization}
            onChange={(e) => setWorkAuthorization(e.target.value)}
            placeholder="e.g. US Citizen, requires visa sponsorship"
          />
        </label>

        <label className="block text-sm font-medium text-muted-foreground">
          Willing to relocate
          <Select value={relocation} onValueChange={(v) => setRelocation(v as RelocationChoice)}>
            <SelectTrigger className="mt-1 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="unspecified">Not specified</SelectItem>
              <SelectItem value="yes">Yes</SelectItem>
              <SelectItem value="no">No</SelectItem>
            </SelectContent>
          </Select>
        </label>

        <label className="block text-sm font-medium text-muted-foreground">
          Start-date availability
          <Input
            className="mt-1"
            value={startDateAvailability}
            onChange={(e) => setStartDateAvailability(e.target.value)}
            placeholder="e.g. 2 weeks notice"
          />
        </label>

        <Button className="w-fit" disabled={busy} onClick={() => void save()}>
          Save
        </Button>
      </div>

      <MatchScoreSection hasResume={profile.data?.has_resume ?? false} />
    </div>
  )
}
