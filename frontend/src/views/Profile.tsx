import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { apiPost } from '../api/client'
import type { ApplicantProfile } from '../api/types'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { useApi } from '../hooks/useApi'

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
  const [phone, setPhone] = useState('')
  const [currentSalary, setCurrentSalary] = useState('')
  const [expectedSalary, setExpectedSalary] = useState('')
  const [workAuthorization, setWorkAuthorization] = useState('')
  const [relocation, setRelocation] = useState<RelocationChoice>('unspecified')
  const [startDateAvailability, setStartDateAvailability] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!profile.data) return
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
        Your own real answers, used by auto-apply's form-filler to answer application
        questions. Nothing here is pre-filled or guessed -- leave a field blank to answer
        it yourself when it comes up.
      </p>

      <div className="mt-6 flex max-w-md flex-col gap-4 rounded-xl border border-border bg-card p-5">
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
    </div>
  )
}
